"""
LLM Budget Management Service

PRODUCTION: Ensures LLM requests are pre-authorized and within budget limits.
Implements atomic budget reservation/debit pattern to prevent cost overages.
"""

import structlog
import asyncio
from decimal import Decimal, InvalidOperation
from datetime import datetime
from uuid import UUID
from enum import Enum
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm import LLMBudget, LLMUsage  # noqa: F401
from app.shared.core.exceptions import (  # noqa: F401
    BudgetExceededError,
    LLMFairUseExceededError,
)
from app.shared.llm.pricing_data import LLM_PRICING
from app.shared.llm.pricing_data import ProviderCost
from app.shared.core.cache import get_cache_service  # noqa: F401
from app.shared.core.config import get_settings  # noqa: F401

# Moved BudgetStatus here
from app.shared.core.ops_metrics import (  # noqa: F401
    LLM_PRE_AUTH_DENIALS,
    LLM_SPEND_USD,
    LLM_FAIR_USE_DENIALS,
    LLM_FAIR_USE_EVALUATIONS,
    LLM_FAIR_USE_OBSERVED,
)
from app.shared.core.pricing import get_tenant_tier, PricingTier  # noqa: F401
from app.shared.core.logging import audit_log  # noqa: F401

__all__ = [
    "LLMBudget",
    "LLMUsage",
    "BudgetExceededError",
    "LLMFairUseExceededError",
    "get_cache_service",
    "get_settings",
    "LLM_PRE_AUTH_DENIALS",
    "LLM_SPEND_USD",
    "LLM_FAIR_USE_DENIALS",
    "LLM_FAIR_USE_EVALUATIONS",
    "LLM_FAIR_USE_OBSERVED",
    "get_tenant_tier",
    "PricingTier",
    "audit_log",
]

logger = structlog.get_logger()


class BudgetStatus(str, Enum):
    OK = "ok"
    SOFT_LIMIT = "soft_limit"
    HARD_LIMIT = "hard_limit"


class LLMBudgetManager:
    """
    Thread-safe budget management with atomic operations.

    Guarantees:
    1. No request executes without pre-authorization
    2. Budget state is always consistent (no double-spending)
    3. All operations are logged for audit trail
    """

    # Conservative estimate: 1 prompt ≈ 500 tokens
    AVG_PROMPT_TOKENS = 500
    AVG_RESPONSE_TOKENS = 500

    # BYOK policy: no surcharge; platform pricing is tier-based.
    BYOK_PLATFORM_FEE_USD = Decimal("0.00")
    _local_inflight_counts: dict[str, int] = {}
    _local_inflight_lock = asyncio.Lock()

    @staticmethod
    def _to_decimal(v: Any) -> Decimal:
        """Safe conversion to Decimal for currency math."""
        if v is None:
            return Decimal("0")
        try:
            return Decimal(str(v))
        except (ValueError, TypeError, InvalidOperation):
            logger.warning("invalid_decimal_conversion", value=str(v))
            return Decimal("0")

    @classmethod
    def estimate_cost(
        cls,
        prompt_tokens: int,
        completion_tokens: int,
        model: str,
        provider: str = "openai",
    ) -> Decimal:
        """
        Estimate LLM request cost in USD using shared pricing data.
        """
        # Find pricing data for provider and model
        provider_data = LLM_PRICING.get(provider, {})
        pricing = provider_data.get(model)

        # PRODUCTION: Fallback to provider default if model is unknown
        if not pricing:
            pricing = provider_data.get("default")

        # PRODUCTION: Global Fallback ($10 per 1M tokens) if still not found
        if not pricing:
            logger.warning(
                "llm_pricing_using_global_fallback", provider=provider, model=model
            )
            pricing = ProviderCost(input=10.0, output=10.0, free_tier_tokens=0)

        # Calculate cost
        input_cost = (
            Decimal(str(prompt_tokens)) * Decimal(str(pricing["input"]))
        ) / Decimal("1000000")
        output_cost = (
            Decimal(str(completion_tokens)) * Decimal(str(pricing["output"]))
        ) / Decimal("1000000")

        return (input_cost + output_cost).quantize(Decimal("0.0001"))

    @classmethod
    async def _enforce_daily_analysis_limit(
        cls,
        tenant_id: UUID,
        db: AsyncSession,
    ) -> None:
        from app.shared.llm.budget_fair_use import enforce_daily_analysis_limit

        await enforce_daily_analysis_limit(cls, tenant_id, db)

    @staticmethod
    def _fair_use_inflight_key(tenant_id: UUID) -> str:
        from app.shared.llm.budget_fair_use import fair_use_inflight_key

        return fair_use_inflight_key(tenant_id)

    @staticmethod
    def _fair_use_tier_allowed(tier: PricingTier) -> bool:
        from app.shared.llm.budget_fair_use import fair_use_tier_allowed

        return fair_use_tier_allowed(tier)

    @staticmethod
    def _fair_use_daily_soft_cap(tier: PricingTier) -> int | None:
        from app.shared.llm.budget_fair_use import fair_use_daily_soft_cap

        return fair_use_daily_soft_cap(tier)

    @staticmethod
    async def _count_requests_in_window(
        tenant_id: UUID,
        db: AsyncSession,
        start: datetime,
        end: datetime | None = None,
    ) -> int:
        from app.shared.llm.budget_fair_use import count_requests_in_window

        return await count_requests_in_window(
            tenant_id=tenant_id,
            db=db,
            start=start,
            end=end,
        )

    @classmethod
    async def _acquire_fair_use_inflight_slot(
        cls, tenant_id: UUID, max_inflight: int, ttl_seconds: int
    ) -> tuple[bool, int]:
        from app.shared.llm.budget_fair_use import acquire_fair_use_inflight_slot

        return await acquire_fair_use_inflight_slot(
            cls,
            tenant_id=tenant_id,
            max_inflight=max_inflight,
            ttl_seconds=ttl_seconds,
        )

    @classmethod
    async def _release_fair_use_inflight_slot(cls, tenant_id: UUID) -> None:
        from app.shared.llm.budget_fair_use import release_fair_use_inflight_slot

        await release_fair_use_inflight_slot(cls, tenant_id)

    @classmethod
    async def _enforce_fair_use_guards(
        cls,
        tenant_id: UUID,
        db: AsyncSession,
        tier: PricingTier,
    ) -> bool:
        from app.shared.llm.budget_fair_use import enforce_fair_use_guards

        return await enforce_fair_use_guards(
            manager_cls=cls,
            tenant_id=tenant_id,
            db=db,
            tier=tier,
        )

    @classmethod
    async def check_and_reserve(
        cls,
        tenant_id: UUID,
        db: AsyncSession,
        provider: str = "openai",
        model: str = "gpt-4o",
        prompt_tokens: int = AVG_PROMPT_TOKENS,
        completion_tokens: int = AVG_RESPONSE_TOKENS,
        operation_id: str | None = None,
    ) -> Decimal:
        from app.shared.llm.budget_execution import check_and_reserve_budget

        return await check_and_reserve_budget(
            manager_cls=cls,
            tenant_id=tenant_id,
            db=db,
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            operation_id=operation_id,
        )

    @classmethod
    async def record_usage(
        cls,
        tenant_id: UUID,
        db: AsyncSession,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        provider: str = "openai",
        actual_cost_usd: Decimal | None = None,
        is_byok: bool = False,
        operation_id: str | None = None,
        request_type: str = "unknown",
    ) -> None:
        from app.shared.llm.budget_execution import record_usage_entry

        await record_usage_entry(
            manager_cls=cls,
            tenant_id=tenant_id,
            db=db,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            provider=provider,
            actual_cost_usd=actual_cost_usd,
            is_byok=is_byok,
            operation_id=operation_id,
            request_type=request_type,
        )

    @classmethod
    async def check_budget(cls, tenant_id: UUID, db: AsyncSession) -> BudgetStatus:
        from app.shared.llm.budget_execution import check_budget_state

        return await check_budget_state(
            manager_cls=cls,
            tenant_id=tenant_id,
            db=db,
        )

    @classmethod
    async def _check_budget_and_alert(
        cls, tenant_id: UUID, db: AsyncSession, last_cost: Decimal
    ) -> None:
        from app.shared.llm.budget_execution import check_budget_and_alert

        await check_budget_and_alert(
            manager_cls=cls,
            tenant_id=tenant_id,
            db=db,
            last_cost=last_cost,
        )
