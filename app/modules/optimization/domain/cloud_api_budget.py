from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from datetime import datetime, timezone

import structlog

from app.shared.core.config import get_settings
from app.shared.core.ops_metrics import (
    CLOUD_API_BUDGET_DECISIONS_TOTAL,
    CLOUD_API_BUDGET_REMAINING,
    CLOUD_API_CALLS_TOTAL,
    CLOUD_API_ESTIMATED_COST_USD,
)

logger = structlog.get_logger()


@dataclass(frozen=True)
class CloudAPIScanContext:
    tenant_id: str
    provider: str
    connection_id: str
    region: str
    plugin: str


_SCAN_CONTEXT: ContextVar[CloudAPIScanContext | None] = ContextVar(
    "cloud_api_scan_context", default=None
)


def _provider_from_api(api: str) -> str:
    prefix, _, _ = api.partition("_")
    return prefix or "unknown"


def _utc_day_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


@contextmanager
def cloud_api_scan_context(
    *,
    tenant_id: str,
    provider: str,
    connection_id: str,
    region: str,
    plugin: str,
):
    token = _SCAN_CONTEXT.set(
        CloudAPIScanContext(
            tenant_id=tenant_id,
            provider=provider,
            connection_id=connection_id,
            region=region,
            plugin=plugin,
        )
    )
    try:
        yield
    finally:
        _SCAN_CONTEXT.reset(token)


def get_cloud_api_scan_context() -> CloudAPIScanContext | None:
    return _SCAN_CONTEXT.get()


class CloudAPIBudgetGovernor:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._day = _utc_day_key()
        self._usage_calls: dict[str, int] = {}
        self._usage_cost: dict[str, float] = {}

    @staticmethod
    def _budget_for_api(api: str) -> int:
        settings = get_settings()
        budgets = {
            "aws_cloudwatch": settings.AWS_CLOUDWATCH_DAILY_CALL_BUDGET,
            "gcp_monitoring": settings.GCP_MONITORING_DAILY_CALL_BUDGET,
            "azure_monitor": settings.AZURE_MONITOR_DAILY_CALL_BUDGET,
        }
        return int(budgets.get(api, 0))

    @staticmethod
    def _cost_per_call_for_api(api: str) -> float:
        settings = get_settings()
        per_call = {
            "aws_cloudwatch": settings.AWS_CLOUDWATCH_ESTIMATED_COST_PER_CALL_USD,
            "gcp_monitoring": settings.GCP_MONITORING_ESTIMATED_COST_PER_CALL_USD,
            "azure_monitor": settings.AZURE_MONITOR_ESTIMATED_COST_PER_CALL_USD,
        }
        return float(per_call.get(api, 0.0))

    def _tenant_bucket_key(self, tenant_id: str, api: str) -> str:
        return f"{self._day}:{tenant_id}:{api}"

    def _refresh_day_if_needed(self) -> None:
        today = _utc_day_key()
        if today == self._day:
            return
        self._day = today
        self._usage_calls.clear()
        self._usage_cost.clear()

    async def consume(
        self,
        api: str,
        *,
        units: int = 1,
        operation: str | None = None,
        estimated_cost_usd: float | None = None,
        context: CloudAPIScanContext | None = None,
    ) -> bool:
        if units <= 0:
            return True

        settings = get_settings()
        if not settings.CLOUD_API_BUDGET_GOVERNOR_ENABLED:
            provider = (context.provider if context else _provider_from_api(api)).lower()
            CLOUD_API_CALLS_TOTAL.labels(provider=provider, api=api).inc(units)
            total_cost = (
                float(estimated_cost_usd)
                if estimated_cost_usd is not None
                else self._cost_per_call_for_api(api) * units
            )
            if total_cost > 0:
                CLOUD_API_ESTIMATED_COST_USD.labels(provider=provider, api=api).inc(
                    total_cost
                )
            CLOUD_API_BUDGET_DECISIONS_TOTAL.labels(
                provider=provider,
                api=api,
                decision="allow",
            ).inc()
            return True

        ctx = context or get_cloud_api_scan_context()
        tenant_id = (ctx.tenant_id if ctx else "unknown")
        provider = (ctx.provider if ctx else _provider_from_api(api)).lower()

        budget = self._budget_for_api(api)
        enforce = settings.CLOUD_API_BUDGET_ENFORCE
        total_cost = (
            float(estimated_cost_usd)
            if estimated_cost_usd is not None
            else self._cost_per_call_for_api(api) * units
        )

        async with self._lock:
            self._refresh_day_if_needed()
            key = self._tenant_bucket_key(tenant_id, api)
            current_calls = self._usage_calls.get(key, 0)
            next_calls = current_calls + units
            budget_exceeded = budget > 0 and next_calls > budget

            if budget_exceeded and enforce:
                remaining = max(budget - current_calls, 0)
                CLOUD_API_BUDGET_REMAINING.labels(provider=provider, api=api).set(
                    remaining
                )
                CLOUD_API_BUDGET_DECISIONS_TOTAL.labels(
                    provider=provider,
                    api=api,
                    decision="deny",
                ).inc()
                logger.warning(
                    "cloud_api_budget_denied",
                    provider=provider,
                    api=api,
                    tenant_id=tenant_id,
                    connection_id=(ctx.connection_id if ctx else "unknown"),
                    plugin=(ctx.plugin if ctx else "unknown"),
                    region=(ctx.region if ctx else "unknown"),
                    operation=operation,
                    current_calls=current_calls,
                    requested_units=units,
                    budget=budget,
                )
                return False

            self._usage_calls[key] = next_calls
            if total_cost > 0:
                self._usage_cost[key] = self._usage_cost.get(key, 0.0) + total_cost

            remaining = max(budget - next_calls, 0) if budget > 0 else 0
            CLOUD_API_BUDGET_REMAINING.labels(provider=provider, api=api).set(remaining)

            decision = "would_deny" if (budget_exceeded and not enforce) else "allow"
            CLOUD_API_BUDGET_DECISIONS_TOTAL.labels(
                provider=provider,
                api=api,
                decision=decision,
            ).inc()
            CLOUD_API_CALLS_TOTAL.labels(provider=provider, api=api).inc(units)
            if total_cost > 0:
                CLOUD_API_ESTIMATED_COST_USD.labels(provider=provider, api=api).inc(
                    total_cost
                )
            return True


_governor = CloudAPIBudgetGovernor()


async def allow_expensive_cloud_api_call(
    api: str,
    *,
    units: int = 1,
    operation: str | None = None,
    estimated_cost_usd: float | None = None,
) -> bool:
    return await _governor.consume(
        api,
        units=units,
        operation=operation,
        estimated_cost_usd=estimated_cost_usd,
    )
