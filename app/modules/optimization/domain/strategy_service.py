from __future__ import annotations

from typing import Any, Dict, List, TYPE_CHECKING
from uuid import UUID

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.shared.core.service import BaseService

if TYPE_CHECKING:
    from app.models.optimization import StrategyRecommendation

logger = structlog.get_logger()


class OptimizationService(BaseService):
    """
    Orchestrates FinOps optimization strategies (RIs, Savings Plans).
    """

    def __init__(self, db: AsyncSession):
        super().__init__(db)

    async def generate_recommendations(
        self, tenant_id: UUID
    ) -> List["StrategyRecommendation"]:
        """
        Runs available optimization strategies against tenant usage.

        Production contract:
        - Strategies are DB-backed (no dummy configs).
        - Each scan is idempotent per (tenant_id, strategy_id): we replace existing OPEN recs.
        """
        import sqlalchemy as sa

        from app.models.optimization import OptimizationStrategy, StrategyRecommendation

        # 1) Fetch active strategies (seed defaults once if missing).
        strategies_q = await self.db.execute(
            select(OptimizationStrategy).where(OptimizationStrategy.is_active.is_(True))
        )
        strategies = list(strategies_q.scalars().all())
        if not strategies:
            strategies = await self._seed_default_strategies()

        usage_cache: dict[tuple[str | None, str | None], Dict[str, Any]] = {}
        all_recommendations: list[StrategyRecommendation] = []

        for strategy in strategies:
            strategy_impl = self._get_strategy_impl(strategy)
            if strategy_impl is None:
                continue

            provider = (
                str(getattr(strategy, "provider", "") or "").strip().lower() or None
            )
            raw_type = getattr(strategy, "type", None)
            type_value = (
                raw_type.value
                if raw_type is not None and hasattr(raw_type, "value")
                else str(raw_type or "")
            )
            strategy_type = type_value.strip().lower() or None

            # Commitment strategies should only use compute spend for baseline.
            canonical_charge_category = (
                "compute"
                if strategy_type
                in {
                    "savings_plan",
                    "reserved_instance",
                    "azure_reservation",
                    "committed_use_discount",
                }
                else None
            )
            usage_key = (provider, canonical_charge_category)
            if usage_key not in usage_cache:
                usage_cache[usage_key] = await self._aggregate_usage(
                    tenant_id,
                    provider=provider,
                    canonical_charge_category=canonical_charge_category,
                )
            usage_data = usage_cache[usage_key]

            try:
                recs = await strategy_impl.analyze(tenant_id, usage_data)
            except (
                RuntimeError,
                ValueError,
                TypeError,
                KeyError,
                AttributeError,
            ) as exc:
                logger.error(
                    "strategy_analysis_failed",
                    strategy=str(getattr(strategy, "name", "unknown")),
                    strategy_type=strategy_type,
                    provider=provider,
                    error=str(exc),
                )
                continue

            if not recs:
                continue

            # Replace existing OPEN recs for this strategy (idempotent scan behavior).
            await self.db.execute(
                sa.delete(StrategyRecommendation).where(
                    StrategyRecommendation.tenant_id == tenant_id,
                    StrategyRecommendation.strategy_id == strategy.id,
                    StrategyRecommendation.status == "open",
                )
            )
            all_recommendations.extend(recs)

        if all_recommendations:
            self.db.add_all(all_recommendations)
            await self.db.commit()

        return all_recommendations

    def _get_strategy_impl(self, strategy: Any) -> Any | None:
        """
        Instantiate a concrete strategy implementation for a DB-backed OptimizationStrategy.
        """
        raw_type = getattr(strategy, "type", None)
        type_value = (
            raw_type.value
            if raw_type is not None and hasattr(raw_type, "value")
            else str(raw_type or "")
        )
        strategy_type = type_value.strip().lower()

        if strategy_type == "savings_plan":
            from app.modules.optimization.domain.strategies.compute_savings import (
                ComputeSavingsStrategy,
            )

            return ComputeSavingsStrategy(strategy)

        if strategy_type in {
            "reserved_instance",
            "azure_reservation",
            "committed_use_discount",
        }:
            from app.modules.optimization.domain.strategies.baseline_commitment import (
                BaselineCommitmentStrategy,
            )

            return BaselineCommitmentStrategy(strategy)

        logger.warning(
            "optimization_strategy_unsupported",
            strategy_id=str(getattr(strategy, "id", "")),
            strategy_type=strategy_type,
            provider=str(getattr(strategy, "provider", "")),
        )
        return None

    async def _seed_default_strategies(self) -> list[Any]:
        """
        Seed a minimal set of default strategies so the product works out-of-the-box.

        This keeps the initial strategy surface deterministic without per-tenant overrides.
        """
        from app.models.optimization import OptimizationStrategy, StrategyType

        existing_q = await self.db.execute(
            select(OptimizationStrategy).where(OptimizationStrategy.is_active.is_(True))
        )
        existing = list(existing_q.scalars().all())
        if existing:
            return existing

        defaults = [
            OptimizationStrategy(
                name="AWS Compute Savings Plan",
                description="Baseline-based compute commitment recommendation (Savings Plans).",
                type=StrategyType.SAVINGS_PLAN.value,
                provider="aws",
                config={
                    "min_hourly_threshold": 0.05,
                    "hours_per_month": 730.0,
                    "savings_rate": 0.25,
                    "savings_rate_low": 0.20,
                    "savings_rate_high": 0.30,
                    "backtest_tolerance": 0.30,
                },
                is_active=True,
            ),
            OptimizationStrategy(
                name="AWS EC2 Reserved Instances",
                description="Baseline-based EC2 Reserved Instance guidance (regional).",
                type=StrategyType.RI.value,
                provider="aws",
                config={
                    "commitment_label": "EC2 Reserved Instances",
                    "region_scope": "top_region",
                    "min_hourly_threshold": 0.05,
                    "hours_per_month": 730.0,
                    "backtest_tolerance": 0.30,
                    "offers": [
                        {
                            "term": "1_year",
                            "payment_option": "no_upfront",
                            "savings_rate": 0.30,
                            "savings_rate_low": 0.25,
                            "savings_rate_high": 0.35,
                            "upfront_cost": 0.0,
                        },
                        {
                            "term": "3_year",
                            "payment_option": "all_upfront",
                            "savings_rate": 0.45,
                            "savings_rate_low": 0.38,
                            "savings_rate_high": 0.52,
                            "upfront_cost": 0.0,
                        },
                    ],
                },
                is_active=True,
            ),
            OptimizationStrategy(
                name="Azure VM Reservations",
                description="Baseline-based Azure reservation guidance (regional).",
                type=StrategyType.AZURE_RESERVATION.value,
                provider="azure",
                config={
                    "commitment_label": "Azure VM Reservations",
                    "region_scope": "top_region",
                    "min_hourly_threshold": 0.05,
                    "hours_per_month": 730.0,
                    "backtest_tolerance": 0.30,
                    "offers": [
                        {
                            "term": "1_year",
                            "payment_option": "no_upfront",
                            "savings_rate": 0.25,
                            "savings_rate_low": 0.20,
                            "savings_rate_high": 0.30,
                            "upfront_cost": 0.0,
                        },
                        {
                            "term": "3_year",
                            "payment_option": "all_upfront",
                            "savings_rate": 0.40,
                            "savings_rate_low": 0.32,
                            "savings_rate_high": 0.48,
                            "upfront_cost": 0.0,
                        },
                    ],
                },
                is_active=True,
            ),
            OptimizationStrategy(
                name="GCP Compute Engine CUD",
                description="Baseline-based GCP Committed Use Discount guidance (regional).",
                type=StrategyType.CUD.value,
                provider="gcp",
                config={
                    "commitment_label": "GCP CUD (Compute Engine)",
                    "region_scope": "top_region",
                    "min_hourly_threshold": 0.05,
                    "hours_per_month": 730.0,
                    "backtest_tolerance": 0.30,
                    "offers": [
                        {
                            "term": "1_year",
                            "payment_option": "no_upfront",
                            "savings_rate": 0.20,
                            "savings_rate_low": 0.15,
                            "savings_rate_high": 0.25,
                            "upfront_cost": 0.0,
                        },
                        {
                            "term": "3_year",
                            "payment_option": "all_upfront",
                            "savings_rate": 0.35,
                            "savings_rate_low": 0.28,
                            "savings_rate_high": 0.42,
                            "upfront_cost": 0.0,
                        },
                    ],
                },
                is_active=True,
            ),
        ]
        self.db.add_all(defaults)
        await self.db.commit()
        for seeded in defaults:
            await self.db.refresh(seeded)
            logger.info(
                "optimization_strategy_seeded",
                strategy_id=str(seeded.id),
                provider=seeded.provider,
                strategy_type=str(seeded.type),
            )
        return defaults

    async def _aggregate_usage(
        self,
        tenant_id: UUID,
        *,
        provider: str | None = None,
        canonical_charge_category: str | None = "compute",
        lookback_days: int = 30,
    ) -> Dict[str, Any]:
        """
        Aggregate recent ledger rows into a stable baseline for commitment strategies.

        This function explicitly handles daily-resolution ledgers by converting day-buckets into
        an hourly baseline to keep commitment math consistent.
        """
        from datetime import date, datetime, time as dt_time, timedelta, timezone
        from statistics import fmean, pstdev

        from app.models.cloud import CloudAccount, CostRecord

        provider_key = (
            provider.strip().lower()
            if isinstance(provider, str) and provider.strip()
            else None
        )
        category_key = (
            canonical_charge_category.strip().lower()
            if isinstance(canonical_charge_category, str)
            and canonical_charge_category.strip()
            else None
        )

        safe_lookback = max(1, min(int(lookback_days or 30), 365))
        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=safe_lookback)

        base_stmt = (
            select(
                CostRecord.timestamp,
                CostRecord.recorded_at,
                CostRecord.region,
                CostRecord.cost_usd,
            )
            .select_from(CostRecord)
            .join(CloudAccount, CostRecord.account_id == CloudAccount.id)
            .where(CostRecord.tenant_id == tenant_id)
            .where(CostRecord.recorded_at >= thirty_days_ago.date())
        )
        if provider_key:
            base_stmt = base_stmt.where(CloudAccount.provider == provider_key)
        if category_key:
            base_stmt = base_stmt.where(
                CostRecord.canonical_charge_category == category_key
            )

        # Prefer FINAL-only for commitment baselines; fall back to whatever exists if FINAL is missing.
        stmt = base_stmt.where(CostRecord.cost_status == "FINAL")
        result = await self.db.execute(stmt)
        rows = result.all()
        source_status = "FINAL"
        if not rows:
            result = await self.db.execute(base_stmt)
            rows = result.all()
            source_status = "any"

        bucket_totals: Dict[datetime, float] = {}
        region_totals: Dict[str, float] = {}
        total_spend = 0.0
        for timestamp_value, recorded_at, region_value, cost_raw in rows:
            if cost_raw is None:
                continue
            cost = float(cost_raw)
            total_spend += cost

            region_key = str(region_value or "Unknown")
            region_totals[region_key] = region_totals.get(region_key, 0.0) + cost

            if timestamp_value is not None:
                bucket_key = timestamp_value
                if bucket_key.tzinfo is None:
                    bucket_key = bucket_key.replace(tzinfo=timezone.utc)
                bucket_key = bucket_key.astimezone(timezone.utc).replace(
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            else:
                bucket_key = datetime.combine(
                    recorded_at, dt_time.min, tzinfo=timezone.utc
                )

            bucket_totals[bucket_key] = bucket_totals.get(bucket_key, 0.0) + cost

        observed_buckets = len(bucket_totals)
        unique_days = {key.date() for key in bucket_totals}

        # Heuristic: if we have ~1-2 buckets per day, treat it as daily-resolution.
        is_daily_resolution = observed_buckets <= max(1, len(unique_days) * 2)

        if is_daily_resolution:
            daily_totals: Dict[date, float] = {}
            for key, cost in bucket_totals.items():
                daily_totals[key.date()] = daily_totals.get(key.date(), 0.0) + float(
                    cost
                )

            values = list(daily_totals.values())
            non_zero = [v for v in values if v > 0]
            expected_days = 30
            observed_days = len(daily_totals)
            coverage_ratio = (
                min(1.0, observed_days / expected_days) if expected_days else 0.0
            )

            average_daily = float(fmean(values)) if values else 0.0
            baseline_daily = self._percentile(non_zero, 0.25) if non_zero else 0.0
            average_hourly_spend = average_daily / 24.0
            baseline_hourly_spend = baseline_daily / 24.0
            volatility = (
                float(pstdev(values) / average_daily)
                if len(values) > 1 and average_daily > 0
                else 0.0
            )
            granularity = "daily"
            expected_buckets = expected_days
            observed_buckets = observed_days

            hourly_cost_series: list[float] = []
            for day_key in sorted(daily_totals):
                per_hour = float(daily_totals[day_key]) / 24.0
                hourly_cost_series.extend([per_hour] * 24)
        else:
            values = list(bucket_totals.values())
            non_zero = [v for v in values if v > 0]
            expected_hours = 30 * 24
            coverage_ratio = (
                min(1.0, observed_buckets / expected_hours) if expected_hours else 0.0
            )

            average_hourly_spend = float(fmean(values)) if values else 0.0
            baseline_hourly_spend = (
                self._percentile(non_zero, 0.25) if non_zero else 0.0
            )
            volatility = (
                float(pstdev(values) / average_hourly_spend)
                if len(values) > 1 and average_hourly_spend > 0
                else 0.0
            )
            granularity = "hourly"
            expected_buckets = expected_hours

            hourly_cost_series = []
            sorted_keys = sorted(bucket_totals)
            if sorted_keys:
                cursor = sorted_keys[0]
                end = sorted_keys[-1]
                while cursor <= end:
                    hourly_cost_series.append(
                        float(bucket_totals.get(cursor, 0.0) or 0.0)
                    )
                    cursor = cursor + timedelta(hours=1)

        confidence_score = round(
            max(
                0.0,
                min(
                    1.0,
                    (coverage_ratio * 0.6) + ((1.0 - min(volatility, 1.0)) * 0.4),
                ),
            ),
            3,
        )

        top_region = "Unknown"
        if region_totals:
            top_region = max(region_totals.items(), key=lambda kv: kv[1])[0]

        return {
            "total_monthly_spend": float(total_spend),
            "average_hourly_spend": float(average_hourly_spend),
            "baseline_hourly_spend": float(baseline_hourly_spend),
            "observed_buckets": int(observed_buckets),
            "expected_buckets": int(expected_buckets),
            "coverage_ratio": float(coverage_ratio),
            "volatility": float(volatility),
            "confidence_score": float(confidence_score),
            "granularity": granularity,
            "provider": provider_key,
            "canonical_charge_category": category_key,
            "source_status": source_status,
            "region": "global",
            "top_region": top_region,
            "region_totals": region_totals,
            "hourly_cost_series": hourly_cost_series,
        }

    def _percentile(self, values: List[float], percentile: float) -> float:
        """Return linear interpolation percentile for deterministic baseline computation."""
        if not values:
            return 0.0
        ordered = sorted(float(v) for v in values)
        if len(ordered) == 1:
            return ordered[0]

        pct = max(0.0, min(percentile, 1.0))
        rank = pct * (len(ordered) - 1)
        lower_idx = int(rank)
        upper_idx = min(lower_idx + 1, len(ordered) - 1)
        frac = rank - lower_idx
        return ordered[lower_idx] + ((ordered[upper_idx] - ordered[lower_idx]) * frac)
