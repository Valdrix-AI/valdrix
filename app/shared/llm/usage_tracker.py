"""
LLM Usage Tracker Service

Calculates and persists LLM API costs for analytics and billing.
Called after every LLM API call to track token usage.
"""

from uuid import UUID
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
import structlog

from app.models.llm import LLMUsage
from app.shared.llm.budget_manager import LLMBudgetManager, BudgetStatus

__all__ = ["UsageTracker", "BudgetStatus", "LLMBudgetManager"]


logger = structlog.get_logger()


def count_tokens(text: str, model: str = "gpt-4") -> int:
    """
    BE-LLM-5: Accurate token counting using tiktoken.
    Falls back to character-based estimation if tiktoken unavailable.
    """
    try:
        import tiktoken

        # Map model names to tiktoken encodings
        encoding_map = {
            "gpt-4": "cl100k_base",
            "gpt-4o": "cl100k_base",
            "gpt-4o-mini": "cl100k_base",
            "gpt-3.5-turbo": "cl100k_base",
            "claude-3-5-sonnet": "cl100k_base",  # Claude uses similar encoding
            "claude-3-opus": "cl100k_base",
            "llama-3.3-70b-versatile": "cl100k_base",  # Approximate
        }
        encoding_name = encoding_map.get(model, "cl100k_base")
        encoding = tiktoken.get_encoding(encoding_name)
        return len(encoding.encode(text))
    except ImportError:
        logger.warning("tiktoken_not_installed_using_fallback")
        # Fallback: ~4 chars per token (rough estimate)
        return len(text) // 4
    except Exception as e:
        logger.error("tiktoken_error", error=str(e))
        return len(text) // 4


class UsageTracker:
    """
    Tracks LLM API usage for cost analytics.

    Usage:
        tracker = UsageTracker(db_session)
        await tracker.record(
            tenant_id=user.tenant_id,
            provider="groq",
            model="llama-3.3-70b-versatile",
            input_tokens=1500,
            output_tokens=800,
            request_type="daily_analysis"
        )
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    def calculate_cost(
        self,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> Decimal:
        """
        DELEGATED: Use LLMBudgetManager.estimate_cost
        """
        return LLMBudgetManager.estimate_cost(
            input_tokens, output_tokens, model, provider
        )

    async def record(
        self,
        tenant_id: UUID,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        is_byok: bool = False,
        request_type: str = "unknown",
        operation_id: str | None = None,
    ) -> None:
        """
        DELEGATED: Use LLMBudgetManager.record_usage
        """
        return await LLMBudgetManager.record_usage(
            tenant_id=tenant_id,
            db=self.db,
            model=model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            provider=provider,
            operation_id=operation_id,
            request_type=request_type,
        )

    async def authorize_request(
        self,
        tenant_id: UUID,
        provider: str,
        model: str,
        input_text: str,
        max_output_tokens: int = 1000,
    ) -> bool:
        """
        DELEGATED: Use LLMBudgetManager.check_and_reserve
        """
        from .usage_tracker import count_tokens

        input_tokens = count_tokens(input_text, model)
        await LLMBudgetManager.check_and_reserve(
            tenant_id=tenant_id,
            db=self.db,
            provider=provider,
            model=model,
            prompt_tokens=input_tokens,
            completion_tokens=max_output_tokens,
        )
        return True

    async def get_monthly_usage(self, tenant_id: UUID) -> Decimal:
        """
        Get total LLM cost for the current month for a tenant.

        Returns:
            Total cost in USD for current month
        """
        from sqlalchemy import select, func, extract

        now = datetime.now(timezone.utc)

        result = await self.db.execute(
            select(func.sum(LLMUsage.cost_usd))
            .where(LLMUsage.tenant_id == tenant_id)
            .where(extract("year", LLMUsage.created_at) == now.year)
            .where(extract("month", LLMUsage.created_at) == now.month)
        )

        total = result.scalar() or Decimal("0")
        return Decimal(str(total))

    async def check_budget(self, tenant_id: UUID) -> BudgetStatus:
        """
        DELEGATED: Use LLMBudgetManager.check_budget
        """
        return await LLMBudgetManager.check_budget(tenant_id, self.db)

    async def _check_budget_and_alert(
        self, tenant_id: UUID, last_cost: Decimal = Decimal("0")
    ) -> None:
        """Bridge method for delegating budget alerts to LLMBudgetManager."""
        await LLMBudgetManager._check_budget_and_alert(tenant_id, self.db, last_cost)

    async def _perform_check_v2(self, tenant_id: UUID) -> BudgetStatus:
        return await LLMBudgetManager.check_budget(tenant_id, self.db)
