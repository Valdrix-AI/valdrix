"""
Zombie Service

Orchestrates zombie resource detection across different cloud providers.
Handles:
- Fetching connections/accounts.
- Executing scans via adapters.
- Optional AI analysis.
- Notifications (Slack).
"""

import asyncio
from typing import Dict, Any, List, Optional, Union, Callable, Awaitable, TYPE_CHECKING
from uuid import UUID
import structlog
import time
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.core.service import BaseService

if TYPE_CHECKING:
    from app.models.optimization import StrategyRecommendation

from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.modules.optimization.domain.architectural_inefficiency import (
    build_architectural_inefficiency_payload,
)
from app.modules.optimization.domain.factory import ZombieDetectorFactory
from app.modules.optimization.domain.waste_rightsizing import (
    build_waste_rightsizing_payload,
)
from app.shared.core.pricing import PricingTier, FeatureFlag, is_feature_enabled

logger = structlog.get_logger()


class ZombieService(BaseService):
    def __init__(self, db: AsyncSession):
        super().__init__(db)

    async def scan_for_tenant(
        self,
        tenant_id: UUID,
        _user: Optional[Any] = None,
        region: str = "us-east-1",
        analyze: bool = False,
        on_category_complete: Optional[
            Callable[[str, List[Dict[str, Any]]], Awaitable[None]]
        ] = None,
    ) -> Dict[str, Any]:
        """
        Scan all cloud accounts (IaaS + Cloud+) for a tenant and return aggregated results.
        """
        # 1. Fetch all cloud connections generically
        # Phase 21: Decoupling from concrete models
        all_connections: List[Union[AWSConnection, AzureConnection, GCPConnection]] = []
        for model in [AWSConnection, AzureConnection, GCPConnection]:
            # Use centralized scoping
            q = await self.db.execute(self._scoped_query(model, tenant_id))
            all_connections.extend(q.scalars().all())

        if not all_connections:
            return {
                "resources": {},
                "total_monthly_waste": 0.0,
                "error": "No cloud connections found.",
            }

        # 2. Execute scans across all providers
        all_zombies: Dict[str, Any] = {
            "unattached_volumes": [],
            "old_snapshots": [],
            "unused_elastic_ips": [],
            "idle_instances": [],
            "orphan_load_balancers": [],
            "idle_rds_databases": [],
            "underused_nat_gateways": [],
            "idle_s3_buckets": [],
            "stale_ecr_images": [],
            "idle_sagemaker_endpoints": [],
            "cold_redshift_clusters": [],
            "idle_saas_subscriptions": [],
            "unused_license_seats": [],
            # Expansion beyond classic "zombies": container + serverless + network hygiene.
            "idle_container_clusters": [],
            "unused_app_service_plans": [],
            "idle_serverless_services": [],
            "idle_serverless_functions": [],
            "orphan_network_components": [],
        }
        all_zombies["scanned_connections"] = len(all_connections)
        total_waste = 0.0

        # Mapping provider/plugin category keys to canonical frontend keys.
        category_mapping = {
            "unattached_azure_disks": "unattached_volumes",
            "unattached_gcp_disks": "unattached_volumes",
            "unattached_disks": "unattached_volumes",
            "orphan_azure_ips": "unused_elastic_ips",
            "orphan_gcp_ips": "unused_elastic_ips",
            "orphaned_ips": "unused_elastic_ips",
            "idle_azure_vms": "idle_instances",
            "idle_azure_gpu_vms": "idle_instances",
            "idle_gcp_vms": "idle_instances",
            "idle_gcp_gpu_instances": "idle_instances",
            "old_azure_snapshots": "old_snapshots",
            "old_gcp_snapshots": "old_snapshots",
            "idle_azure_sql": "idle_rds_databases",
            "idle_gcp_cloud_sql": "idle_rds_databases",
            "idle_azure_aks": "idle_container_clusters",
            "empty_gke_clusters": "idle_container_clusters",
            "unused_azure_app_service_plans": "unused_app_service_plans",
            "idle_cloud_run": "idle_serverless_services",
            "idle_cloud_functions": "idle_serverless_functions",
            "orphan_azure_nics": "orphan_network_components",
            "orphan_azure_nsgs": "orphan_network_components",
        }

        from app.shared.core.pricing import get_tenant_tier

        tier = await get_tenant_tier(tenant_id, self.db)
        has_precision = is_feature_enabled(tier, FeatureFlag.PRECISION_DISCOVERY)
        has_attribution = is_feature_enabled(tier, FeatureFlag.OWNER_ATTRIBUTION)

        def merge_scan_results(
            provider_name: str,
            connection_id: str,
            connection_name: str,
            scan_results: Dict[str, Any],
            region_override: Optional[str] = None,
        ) -> None:
            nonlocal total_waste
            for category, items in scan_results.items():
                if not isinstance(items, list):
                    continue
                ui_key = category_mapping.get(category, category)
                bucket = all_zombies.setdefault(ui_key, [])
                for item in items:
                    if not isinstance(item, dict):
                        continue
                    res_id = item.get("resource_id") or item.get("id")
                    cost = float(
                        item.get("monthly_cost") or item.get("monthly_waste") or 0
                    )
                    normalized_region = (
                        region_override or item.get("region") or item.get("zone")
                    )
                    item.update(
                        {
                            "provider": provider_name,
                            "connection_id": connection_id,
                            "connection_name": connection_name,
                            "resource_id": res_id,
                            "monthly_cost": cost,
                            "is_gpu": bool(item.get("is_gpu", False))
                            if has_precision
                            else "Upgrade to Growth",
                            "owner": item.get("owner", "unknown")
                            if has_attribution
                            else "Upgrade to Growth",
                        }
                    )
                    if normalized_region:
                        item["region"] = normalized_region
                    bucket.append(item)
                    total_waste += cost

        async def run_scan(
            conn: Union[AWSConnection, AzureConnection, GCPConnection],
        ) -> None:
            nonlocal total_waste
            try:
                if isinstance(conn, AWSConnection):
                    # H-2: Parallel Regional Scanning for AWS
                    from app.modules.optimization.adapters.aws.region_discovery import (
                        RegionDiscovery,
                    )

                    # Fix: Use detector factory to get a temporary detector for credentials
                    temp_detector = ZombieDetectorFactory.get_detector(
                        conn, region="us-east-1", db=self.db
                    )
                    raw_credentials = (
                        await temp_detector.get_credentials()
                        if hasattr(temp_detector, "get_credentials")
                        else None
                    )
                    credentials: dict[str, str] | None
                    if isinstance(raw_credentials, dict):
                        credentials = {
                            str(k): str(v)
                            for k, v in raw_credentials.items()
                            if v is not None
                        }
                    else:
                        credentials = None
                    rd = RegionDiscovery(credentials=credentials)
                    enabled_regions = await rd.get_enabled_regions()

                    logger.info(
                        "aws_parallel_scan_starting",
                        tenant_id=str(tenant_id),
                        region_count=len(enabled_regions),
                    )

                    async def scan_single_region(reg: str) -> None:
                        nonlocal total_waste
                        try:
                            regional_detector = ZombieDetectorFactory.get_detector(
                                conn, region=reg, db=self.db
                            )
                            reg_results = await regional_detector.scan_all(
                                on_category_complete=on_category_complete
                            )
                            merge_scan_results(
                                provider_name=regional_detector.provider_name,
                                connection_id=str(conn.id),
                                connection_name=getattr(conn, "name", "Other"),
                                scan_results=reg_results,
                                region_override=reg,
                            )
                        except Exception as e:
                            logger.error(
                                "regional_scan_failed", region=reg, error=str(e)
                            )

                    await asyncio.gather(
                        *(scan_single_region(r) for r in enabled_regions)
                    )
                else:
                    # Generic logic for Azure/GCP (global for now)
                    detector = ZombieDetectorFactory.get_detector(
                        conn, region="global", db=self.db
                    )
                    results = await detector.scan_all(
                        on_category_complete=on_category_complete
                    )
                    merge_scan_results(
                        provider_name=detector.provider_name,
                        connection_id=str(conn.id),
                        connection_name=getattr(conn, "name", "Other"),
                        scan_results=results,
                    )
            except Exception as e:
                logger.error(
                    "scan_provider_failed", error=str(e), provider=type(conn).__name__
                )

        # Execute all scans in parallel with a hard 5-minute timeout for the entire operation
        # BE-SCHED-3: Resilience - Prevent hanging API requests
        from app.shared.core.ops_metrics import SCAN_LATENCY, SCAN_TIMEOUTS

        start_time = time.perf_counter()
        try:
            await asyncio.wait_for(
                asyncio.gather(*(run_scan(c) for c in all_connections)),
                timeout=300,  # 5 minutes
            )
            # Record overall scan latency
            latency = time.perf_counter() - start_time
            SCAN_LATENCY.labels(provider="multi", region="aggregated").observe(latency)
        except asyncio.TimeoutError:
            logger.error("scan_overall_timeout", tenant_id=str(tenant_id))
            all_zombies["scan_timeout"] = True
            all_zombies["partial_results"] = True
            SCAN_TIMEOUTS.labels(level="overall", provider="multi").inc()

        all_zombies["total_monthly_waste"] = round(total_waste, 2)
        all_zombies["waste_rightsizing"] = build_waste_rightsizing_payload(all_zombies)
        all_zombies["architectural_inefficiency"] = (
            build_architectural_inefficiency_payload(all_zombies)
        )

        # 3. AI Analysis (BE-LLM-1: Decoupled Async Analysis)
        if analyze and not all_zombies.get("scan_timeout"):
            # Enqueue AI analysis as a background job instead of blocking the scan
            from app.models.background_job import BackgroundJob, JobType, JobStatus
            from sqlalchemy.dialects.postgresql import insert
            from datetime import datetime, timezone

            now = datetime.now(timezone.utc)
            job_id = None
            try:
                # Deduplicate by tenant_id + scan_time_bucket
                bucket_str = now.strftime("%Y-%m-%d-%H")
                dedup_key = f"{tenant_id}:zombie_analysis:{bucket_str}"

                stmt = (
                    insert(BackgroundJob)
                    .values(
                        job_type=JobType.ZOMBIE_ANALYSIS.value,
                        tenant_id=tenant_id,
                        status=JobStatus.PENDING,
                        scheduled_for=now,
                        created_at=now,
                        deduplication_key=dedup_key,
                        payload={"zombies": all_zombies},  # Pass the results to analyze
                    )
                    .on_conflict_do_nothing(index_elements=["deduplication_key"])
                    .returning(BackgroundJob.id)
                )

                result = await self.db.execute(stmt)
                job_id = result.scalar_one_or_none()
                await self.db.commit()

                if job_id:
                    from app.shared.core.ops_metrics import BACKGROUND_JOBS_ENQUEUED
                    from app.models.background_job import JobType

                    BACKGROUND_JOBS_ENQUEUED.labels(
                        job_type=JobType.ZOMBIE_ANALYSIS.value, priority="normal"
                    ).inc()

                all_zombies["ai_analysis"] = {
                    "status": "pending",
                    "job_id": str(job_id) if job_id else "already_queued",
                    "summary": "AI Analysis has been queued and will be available shortly.",
                }
            except Exception as e:
                logger.error("failed_to_enqueue_ai_analysis", error=str(e))
                all_zombies["ai_analysis"] = {
                    "status": "error",
                    "error": "Failed to queue analysis",
                }

        # 4. Notifications
        await self._send_notifications(all_zombies, tenant_id)

        return all_zombies

    async def _enrich_with_ai(
        self, zombies: Dict[str, Any], tenant_id: Any, tier: PricingTier
    ) -> None:
        """Enrich results with AI insights if tier allows."""
        try:
            tier_value = str(getattr(tier, "value", tier)).strip().lower()
            tier_allows_ai = tier_value in {
                PricingTier.GROWTH.value,
                PricingTier.PRO.value,
                PricingTier.ENTERPRISE.value,
            }

            if (not tier_allows_ai) or (
                not is_feature_enabled(tier, FeatureFlag.LLM_ANALYSIS)
            ):
                zombies["ai_analysis"] = {
                    "error": "AI Insights requires Growth tier or higher.",
                    "summary": "Upgrade to unlock AI-powered analysis.",
                    "upgrade_required": True,
                }
            else:
                from app.shared.llm.factory import LLMFactory
                from app.shared.llm.zombie_analyzer import ZombieAnalyzer

                llm = LLMFactory.create()
                analyzer = ZombieAnalyzer(llm)

                ai_analysis = await analyzer.analyze(
                    detection_results=zombies,
                    tenant_id=tenant_id,
                    db=self.db,
                )
                zombies["ai_analysis"] = ai_analysis
                logger.info("service_zombie_ai_analysis_complete")
        except Exception as e:
            logger.error("service_zombie_ai_analysis_failed", error=str(e))
            zombies["ai_analysis"] = {
                "error": f"AI analysis failed: {str(e)}",
                "summary": "AI analysis unavailable. Rule-based detection completed.",
            }

    async def _send_notifications(
        self, zombies: Dict[str, Any], tenant_id: UUID
    ) -> None:
        """Send notifications about detected zombies."""
        try:
            from app.shared.core.notifications import NotificationDispatcher

            estimated_savings = zombies.get("total_monthly_waste", 0.0)
            await NotificationDispatcher.notify_zombies(
                zombies,
                estimated_savings,
                tenant_id=str(tenant_id),
                db=self.db,
            )
        except Exception as e:
            logger.error("service_zombie_notification_failed", error=str(e))


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
            except Exception as exc:
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

        This is safe for a new project: no backward-compat logic, no per-tenant strategy config yet.
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
