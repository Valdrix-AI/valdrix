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
from app.services.cache import get_cache_service
from enum import Enum

class BudgetStatus(str, Enum):
    OK = "ok"
    SOFT_LIMIT = "soft_limit"
    HARD_LIMIT = "hard_limit"


logger = structlog.get_logger()

# Prices per 1 MILLION tokens (input/output) in USD
# Source: Official pricing pages as of 2026
LLM_PRICING = {
    "groq": {
        "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
        "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
        "deepseek-v3": {"input": 0.14, "output": 0.28},
    },
    "openai": {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "o1-mini": {"input": 3.00, "output": 12.00},
        "o1-preview": {"input": 15.00, "output": 60.00},
    },
    "anthropic": {
        "claude-3-7-sonnet": {"input": 3.00, "output": 15.00},
        "claude-3-5-sonnet": {"input": 3.00, "output": 15.00},
        "claude-3-5-haiku": {"input": 0.25, "output": 1.25},
        "claude-3-opus": {"input": 15.00, "output": 75.00},
    },
    "google": {
        "gemini-2.0-flash": {"input": 0.10, "output": 0.40},
        "gemini-1.5-pro": {"input": 1.00, "output": 3.00},
        "gemini-1.5-flash": {"input": 0.05, "output": 0.15},
    },
}


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
        Calculate USD cost based on provider, model, and token counts.

        Formula: (input_tokens * input_price / 1M) + (output_tokens * output_price / 1M)

        Returns 0 if model not found (fail gracefully, don't break the app)
        """
        pricing = LLM_PRICING.get(provider, {}).get(model)

        if not pricing:
            logger.warning(
                "llm_pricing_not_found",
                provider=provider,
                model=model,
            )
            return Decimal("0")

        # Price is per million tokens, so divide by 1,000,000
        input_cost = Decimal(str(input_tokens)) * Decimal(str(pricing["input"])) / Decimal("1000000")
        output_cost = Decimal(str(output_tokens)) * Decimal(str(pricing["output"])) / Decimal("1000000")

        return input_cost + output_cost

    async def record(
        self,
        tenant_id: UUID,
        provider: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
        is_byok: bool = False,
        request_type: str = "unknown",
    ) -> LLMUsage:
        """
        Record an LLM API call to the database.
        """
        cost = self.calculate_cost(provider, model, input_tokens, output_tokens)

        # Update cache if it was a pre-authorized request
        cache = get_cache_service()
        if cache.enabled:
            # We don't necessarily clear here, but we could update the estimate
            pass

        usage = LLMUsage(
            tenant_id=tenant_id,
            provider=provider,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            cost_usd=cost,
            is_byok=is_byok,
            request_type=request_type,
        )

        self.db.add(usage)
        # Track in Prometheus for real-time spend monitoring (Phase 2)
        from app.core.ops_metrics import LLM_SPEND_USD
        # We would need the tenant's tier here, either pass it or fetch it.
        # For now, we increment with generic labels if unknown.
        LLM_SPEND_USD.labels(
            tenant_tier="growth", # Default or fetched
            provider=provider,
            model=model
        ).inc(float(cost))

        await self.db.commit()
        await self.db.refresh(usage)

        logger.info(
            "llm_usage_recorded",
            tenant_id=str(tenant_id),
            provider=provider,
            model=model,
            tokens=input_tokens + output_tokens,
            cost_usd=float(cost),
        )

        # Check budget and alert if threshold crossed
        await self._check_budget_and_alert(tenant_id)

        return usage

    async def authorize_request(
        self,
        tenant_id: UUID,
        provider: str,
        model: str,
        input_text: str,
        max_output_tokens: int = 1000
    ) -> bool:
        """
        BE-LLM-4: Hard Cost Protection. 
        Authorizes an LLM request BEFORE it is sent to the provider.
        
        Logic:
        1. Count input tokens.
        2. Estimate output tokens (using max_output_tokens as buffer).
        3. Calculate estimated cost.
        4. If (current_month_usage + estimated_cost) > hard_limit: REJECT.
        """
        from app.models.llm import LLMBudget
        from app.core.exceptions import BudgetExceededError
        from sqlalchemy import select

        # 1. Fetch Budgetource of Truth
        result = await self.db.execute(
            select(LLMBudget).where(LLMBudget.tenant_id == tenant_id)
        )
        budget = result.scalar_one_or_none()

        if not budget:
            return True # No budget = no restriction (or default platform limit)

        if not budget.hard_limit:
            return True # Not enforcing hard limits

        # 2. Token Estimation
        input_tokens = count_tokens(input_text, model)
        # Safety buffer for output
        estimated_output = max_output_tokens
        
        estimated_cost = self.calculate_cost(provider, model, input_tokens, estimated_output)
        
        # 3. Current Usage
        current_usage = await self.get_monthly_usage(tenant_id)
        limit = Decimal(str(budget.monthly_limit_usd))

        projected_total = current_usage + estimated_cost
        
        if projected_total > limit:
            from app.core.ops_metrics import LLM_PRE_AUTH_DENIALS
            # Assuming a default tier or fetching it if available
            LLM_PRE_AUTH_DENIALS.labels(reason="hard_limit_exceeded", tenant_tier="growth").inc()

            logger.error(
                "llm_request_pre_authorization_rejected",
                tenant_id=str(tenant_id),
                estimated_cost=float(estimated_cost),
                current_usage=float(current_usage),
                limit=float(limit)
            )
            raise BudgetExceededError(
                message=f"Request rejected: Projected cost ${projected_total:.4f} exceeds monthly limit ${limit:.2f}.",
                details={
                    "estimated_request_cost": float(estimated_cost),
                    "current_monthly_usage": float(current_usage),
                    "monthly_limit": float(limit)
                }
            )

        logger.info(
            "llm_request_pre_authorized",
            tenant_id=str(tenant_id),
            estimated_cost=float(estimated_cost),
            projected_total=float(projected_total)
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
            .where(extract('year', LLMUsage.created_at) == now.year)
            .where(extract('month', LLMUsage.created_at) == now.month)
        )

        total = result.scalar() or Decimal("0")
        return Decimal(str(total))

    async def check_budget(self, tenant_id: UUID) -> BudgetStatus:
        """
        Synchronously check if tenant has exceeded their monthly budget.
        Returns BudgetStatus.
        Raises BudgetExceededError only on HARD_LIMIT if logic requires it, 
        but here we return status and let the caller decide.
        
        Optimized: Checks Redis first for "Blocked" status (O(1)) before hitting DB.
        Hardened: Uses a fail-closed pattern. If Redis or DB is down, we block (HARD_LIMIT).
        """
        from sqlalchemy import select
        from app.models.llm import LLMBudget
        from app.core.exceptions import BudgetExceededError
        import aiobreaker


        # Define the budget check logic as a nested function to be protected by a circuit breaker
        async def _perform_check():
            # 1. Fast Cache Check (Resilience against DB saturation)
            cache = get_cache_service()
            if cache.enabled:
                try:
                    is_blocked = await cache.client.get(f"budget_blocked:{tenant_id}")
                    if is_blocked:
                        logger.warning("llm_budget_cache_hit_blocked", tenant_id=str(tenant_id))
                        raise BudgetExceededError(
                            message="Monthly LLM budget exceeded (cached).",
                            details={"cached": True}
                        )
                except BudgetExceededError:
                    raise
                except Exception as e:
                    logger.error("llm_budget_cache_error", tenant_id=str(tenant_id), error=str(e))
                    # In a fail-closed model, cache error = assume blocked if we can't verify
                    # However, we allow falling back to DB once, unless circuit is open.
                    raise

            # 2. Database Check (Source of Truth)
            try:
                result = await self.db.execute(
                    select(LLMBudget).where(LLMBudget.tenant_id == tenant_id)
                )
                budget = result.scalar_one_or_none()

                if not budget or not budget.hard_limit:
                    return

                current_usage = await self.get_monthly_usage(tenant_id)
                limit = Decimal(str(budget.monthly_limit_usd))

                if current_usage >= limit:
                    logger.error(
                        "llm_budget_hard_limit_exceeded",
                        tenant_id=str(tenant_id),
                        usage_usd=float(current_usage),
                        limit_usd=float(limit)
                    )
                    
                    # Cache the blocked status to protect the DB
                    if cache.enabled:
                        try:
                            await cache.client.set(f"budget_blocked:{tenant_id}", "1", ex=600)
                        except Exception:
                            pass
                        
                    raise BudgetExceededError(
                        message=f"Monthly LLM budget of ${limit:.2f} has been exceeded.",
                        details={"usage": float(current_usage), "limit": float(limit)}
                    )
            except BudgetExceededError:
                raise
            except Exception as e:
                logger.error("llm_budget_db_error", tenant_id=str(tenant_id), error=str(e))
                raise

        # Initialize or get a circuit breaker for budget operations
        try:
            return await self._perform_check_v2(tenant_id)
        except Exception as e:
            # FAIL-CLOSED: Any technical error (Redis/DB down) results in a block
            logger.critical(
                "llm_budget_verification_system_failure", 
                tenant_id=str(tenant_id), 
                error=str(e),
                resolution="fail_closed_blocked"
            )
            # Raise for fail-closed behavior as expected by tests
            raise BudgetExceededError(
                message="Monthly LLM budget exceeded (Fail-Closed).",
                details={"error": "service_unavailable", "fail_closed": True}
            )

    async def _perform_check_v2(self, tenant_id: UUID):
        """Internal helper for check_budget with soft-limit logic."""
        from sqlalchemy import select
        from app.models.llm import LLMBudget
        from app.core.exceptions import BudgetExceededError

        # 1. Fast Cache Check
        cache = get_cache_service()
        if cache.enabled:
            try:
                is_blocked = await cache.client.get(f"budget_blocked:{tenant_id}")
                if is_blocked:
                    return BudgetStatus.HARD_LIMIT
                
                is_soft = await cache.client.get(f"budget_soft:{tenant_id}")
                if is_soft:
                    return BudgetStatus.SOFT_LIMIT
            except Exception as e:
                # FAIL-CLOSED: Cache failures should block to prevent budget overruns
                logger.error("llm_cache_check_failed", tenant_id=str(tenant_id), error=str(e))
                raise  # Let outer handler convert to BudgetExceededError

        # 2. Database Check
        try:
            result = await self.db.execute(
                select(LLMBudget).where(LLMBudget.tenant_id == tenant_id)
            )
            budget = result.scalar_one_or_none()

            if not budget:
                return BudgetStatus.OK

            current_usage = await self.get_monthly_usage(tenant_id)
            limit = Decimal(str(budget.monthly_limit_usd))
            threshold = Decimal(str(budget.alert_threshold_percent)) / 100

            if current_usage >= limit:
                if budget.hard_limit:
                    if cache.enabled:
                        await cache.client.set(f"budget_blocked:{tenant_id}", "1", ex=600)
                    raise BudgetExceededError(
                        message=f"Monthly LLM budget of ${limit:.2f} has been exceeded.",
                        details={"usage": float(current_usage), "limit": float(limit)}
                    )
                else:
                    return BudgetStatus.SOFT_LIMIT # Treat as soft if hard_limit is False

            if current_usage >= (limit * threshold):
                if cache.enabled:
                    await cache.client.set(f"budget_soft:{tenant_id}", "1", ex=300)
                return BudgetStatus.SOFT_LIMIT

            return BudgetStatus.OK
        except Exception as e:
            logger.error("llm_budget_check_failed", error=str(e))
            raise # Let caller handle fail-closed


    async def _check_budget_and_alert(self, tenant_id: UUID) -> None:
        """
        Check if tenant has exceeded budget threshold and send Slack alert.
        """
        from sqlalchemy import select
        from app.models.llm import LLMBudget
        from app.core.config import get_settings

        # Get tenant's budget settings
        result = await self.db.execute(
            select(LLMBudget).where(LLMBudget.tenant_id == tenant_id)
        )
        budget = result.scalar_one_or_none()

        if not budget:
            return  # No budget set, skip

        # Get current month's usage
        current_usage = await self.get_monthly_usage(tenant_id)
        limit = Decimal(str(budget.monthly_limit_usd))
        threshold_percent = budget.alert_threshold_percent

        # Calculate percentage used
        if limit > 0:
            usage_percent = (current_usage / limit) * 100
        else:
            usage_percent = Decimal("0")

        # Check if threshold crossed and alert not already sent this month
        now = datetime.now(timezone.utc)

        # Check if we already sent an alert this month
        already_sent_this_month = False
        if budget.alert_sent_at:
            # Type safety: if it's still a string (pre-migration data), handle it
            # But normally it will be a datetime object now
            if isinstance(budget.alert_sent_at, datetime):
                if budget.alert_sent_at.year == now.year and budget.alert_sent_at.month == now.month:
                    already_sent_this_month = True
            else:
                # Fallback for string month format if migration is pending
                current_month_str = f"{now.year}-{now.month:02d}"
                if str(budget.alert_sent_at) == current_month_str:
                    already_sent_this_month = True

        if usage_percent >= threshold_percent and not already_sent_this_month:
            # Item 13: Audit log for budget alert
            from app.core.logging import audit_log
            audit_log(
                event="llm_budget_alert",
                user_id="system",
                tenant_id=str(tenant_id),
                details={
                    "status": "exceeded" if usage_percent >= 100 else "warning",
                    "usage_usd": float(current_usage),
                    "budget_usd": float(limit),
                    "usage_percent": float(usage_percent)
                }
            )

            # Send Slack alert
            settings = get_settings()
            if settings.SLACK_BOT_TOKEN and settings.SLACK_CHANNEL_ID:
                try:
                    from app.services.notifications import SlackService
                    slack = SlackService(settings.SLACK_BOT_TOKEN, settings.SLACK_CHANNEL_ID)

                    severity = "critical" if usage_percent >= 100 else "warning"
                    await slack.send_alert(
                        title="LLM Budget Alert",
                        message=f"*Usage:* ${current_usage:.2f} / ${limit:.2f} ({usage_percent:.0f}%)\n*Threshold:* {threshold_percent}%\n*Status:* {'EXCEEDED' if usage_percent >= 100 else 'Warning'}",
                        severity=severity,
                    )
                except Exception as e:
                    # Log but DON'T block the usage record (Fail-soft for alerts)
                    logger.error("llm_budget_alert_failed", tenant_id=str(tenant_id), error=str(e))

                logger.warning(
                    "llm_budget_threshold_crossed",
                    tenant_id=str(tenant_id),
                    usage_usd=float(current_usage),
                    limit_usd=float(limit),
                    usage_percent=float(usage_percent),
                )

            # Update alert_sent_at to now
            budget.alert_sent_at = now
            await self.db.commit()
