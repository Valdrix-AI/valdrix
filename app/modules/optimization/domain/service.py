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
from app.modules.optimization.domain.factory import ZombieDetectorFactory
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
        on_category_complete: Optional[Callable[[str, List[Dict[str, Any]]], Awaitable[None]]] = None
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
                "error": "No cloud connections found."
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
            "idle_gcp_vms": "idle_instances",
            "old_azure_snapshots": "old_snapshots",
            "old_gcp_snapshots": "old_snapshots",
            "idle_azure_sql": "idle_rds_databases",
            "idle_gcp_cloud_sql": "idle_rds_databases",
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
                    cost = float(item.get("monthly_cost") or item.get("monthly_waste") or 0)
                    normalized_region = region_override or item.get("region") or item.get("zone")
                    item.update({
                        "provider": provider_name,
                        "connection_id": connection_id,
                        "connection_name": connection_name,
                        "resource_id": res_id,
                        "monthly_cost": cost,
                        "is_gpu": bool(item.get("is_gpu", False)) if has_precision else "Upgrade to Growth",
                        "owner": item.get("owner", "unknown") if has_attribution else "Upgrade to Growth",
                    })
                    if normalized_region:
                        item["region"] = normalized_region
                    bucket.append(item)
                    total_waste += cost

        async def run_scan(conn: Union[AWSConnection, AzureConnection, GCPConnection]) -> None:
            nonlocal total_waste
            try:
                if isinstance(conn, AWSConnection):
                    # H-2: Parallel Regional Scanning for AWS
                    from app.modules.optimization.adapters.aws.region_discovery import RegionDiscovery
                    # Fix: Use detector factory to get a temporary detector for credentials
                    temp_detector = ZombieDetectorFactory.get_detector(conn, region="us-east-1", db=self.db)
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
                    
                    logger.info("aws_parallel_scan_starting", tenant_id=str(tenant_id), region_count=len(enabled_regions))
                    
                    async def scan_single_region(reg: str) -> None:
                        nonlocal total_waste
                        try:
                            regional_detector = ZombieDetectorFactory.get_detector(conn, region=reg, db=self.db)
                            reg_results = await regional_detector.scan_all(on_category_complete=on_category_complete)
                            merge_scan_results(
                                provider_name=regional_detector.provider_name,
                                connection_id=str(conn.id),
                                connection_name=getattr(conn, "name", "Other"),
                                scan_results=reg_results,
                                region_override=reg,
                            )
                        except Exception as e:
                            logger.error("regional_scan_failed", region=reg, error=str(e))

                    await asyncio.gather(*(scan_single_region(r) for r in enabled_regions))
                else:
                    # Generic logic for Azure/GCP (global for now)
                    detector = ZombieDetectorFactory.get_detector(conn, region="global", db=self.db)
                    results = await detector.scan_all(on_category_complete=on_category_complete)
                    merge_scan_results(
                        provider_name=detector.provider_name,
                        connection_id=str(conn.id),
                        connection_name=getattr(conn, "name", "Other"),
                        scan_results=results,
                    )
            except Exception as e:
                logger.error("scan_provider_failed", error=str(e), provider=type(conn).__name__)

        # Execute all scans in parallel with a hard 5-minute timeout for the entire operation
        # BE-SCHED-3: Resilience - Prevent hanging API requests
        from app.shared.core.ops_metrics import SCAN_LATENCY, SCAN_TIMEOUTS
        
        start_time = time.perf_counter()
        try:
            await asyncio.wait_for(
                asyncio.gather(*(run_scan(c) for c in all_connections)),
                timeout=300 # 5 minutes
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
                
                stmt = insert(BackgroundJob).values(
                    job_type=JobType.ZOMBIE_ANALYSIS.value,
                    tenant_id=tenant_id,
                    status=JobStatus.PENDING,
                    scheduled_for=now,
                    created_at=now,
                    deduplication_key=dedup_key,
                    payload={"zombies": all_zombies} # Pass the results to analyze
                ).on_conflict_do_nothing(index_elements=["deduplication_key"]).returning(BackgroundJob.id)
                
                result = await self.db.execute(stmt)
                job_id = result.scalar_one_or_none()
                await self.db.commit()

                if job_id:
                    from app.shared.core.ops_metrics import BACKGROUND_JOBS_ENQUEUED
                    from app.models.background_job import JobType
                    BACKGROUND_JOBS_ENQUEUED.labels(
                        job_type=JobType.ZOMBIE_ANALYSIS.value,
                        priority="normal"
                    ).inc()
                
                all_zombies["ai_analysis"] = {
                    "status": "pending",
                    "job_id": str(job_id) if job_id else "already_queued",
                    "summary": "AI Analysis has been queued and will be available shortly."
                }
            except Exception as e:
                logger.error("failed_to_enqueue_ai_analysis", error=str(e))
                all_zombies["ai_analysis"] = {"status": "error", "error": "Failed to queue analysis"}

        # 4. Notifications
        await self._send_notifications(all_zombies)

        return all_zombies

    async def _enrich_with_ai(self, zombies: Dict[str, Any], tenant_id: Any, tier: PricingTier) -> None:
        """Enrich results with AI insights if tier allows."""
        try:
            tier_value = str(getattr(tier, "value", tier)).strip().lower()
            tier_allows_ai = tier_value in {
                PricingTier.GROWTH.value,
                PricingTier.PRO.value,
                PricingTier.ENTERPRISE.value,
            }

            if (not tier_allows_ai) or (not is_feature_enabled(tier, FeatureFlag.LLM_ANALYSIS)):
                zombies["ai_analysis"] = {
                    "error": "AI Insights requires Growth tier or higher.",
                    "summary": "Upgrade to unlock AI-powered analysis.",
                    "upgrade_required": True
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
                "summary": "AI analysis unavailable. Rule-based detection completed."
            }

    async def _send_notifications(self, zombies: Dict[str, Any]) -> None:
        """Send notifications about detected zombies."""
        try:
            from app.shared.core.notifications import NotificationDispatcher
            estimated_savings = zombies.get("total_monthly_waste", 0.0)
            await NotificationDispatcher.notify_zombies(zombies, estimated_savings)
        except Exception as e:
            logger.error("service_zombie_notification_failed", error=str(e))


class OptimizationService(BaseService):
    """
    Orchestrates FinOps optimization strategies (RIs, Savings Plans).
    """
    def __init__(self, db: AsyncSession):
        super().__init__(db)

    async def generate_recommendations(self, tenant_id: UUID) -> List["StrategyRecommendation"]:
        """
        Runs available optimization strategies against tenant usage.
        """
        from app.models.optimization import OptimizationStrategy
        from app.modules.optimization.domain.strategies.compute_savings import ComputeSavingsStrategy
        
        # 1. Fetch active strategies
        # For production, these should be seeded or active by default.
        # We'll simulate fetching them or use a default list if DB is empty.
        strategies_q = await self.db.execute(
            select(OptimizationStrategy).where(OptimizationStrategy.is_active.is_(True))
        )
        strategies = strategies_q.scalars().all()
        
        # Fallback if no strategies defined in DB yet (Bootstrap)
        if not strategies:
           # In a real scenario, we might return empty or bootstrap default strategies
           pass

        # 2. Aggregate Usage Data (Production: SQL Aggregation)
        usage_data = await self._aggregate_usage(tenant_id)
        
        all_recommendations = []
        
        # Hardcode strategy for this phase if DB is empty, to ensure "Production Implementation" works
        # In reality, we'd iterate over `strategies`
        # But let's assume we want to run ComputeSavingsStrategy always for now
        
        # Instantiate Strategy directly for this phase
        # In future: StrategyFactory.get_strategy(opt_strategy)
        # We create a dummy config for now to pass to the strategy
        dummy_config = OptimizationStrategy(
            id=UUID("00000000-0000-0000-0000-000000000000"), # distinct from DB
            name="Compute Savings",
            type="savings_plan",
            provider="aws",
            config={}
        )
        
        strategy_impl = ComputeSavingsStrategy(dummy_config) 
        
        try:
            recs = await strategy_impl.analyze(tenant_id, usage_data)
            all_recommendations.extend(recs)
        except Exception as e:
            logger.error("strategy_analysis_failed", strategy="ComputeSavings", error=str(e))

        # 3. Persist Recommendations
        if all_recommendations:
            self.db.add_all(all_recommendations)
            await self.db.commit()
            
        return all_recommendations

    async def _aggregate_usage(self, tenant_id: UUID) -> Dict[str, Any]:
        """
        Aggregates last 30 days of CostRecords to compute hourly baseline and confidence.
        """
        from app.models.cloud import CostRecord
        from datetime import datetime, time as dt_time, timedelta, timezone
        from statistics import fmean, pstdev

        thirty_days_ago = datetime.now(timezone.utc) - timedelta(days=30)
        q = self._scoped_query(CostRecord, tenant_id).where(
            CostRecord.recorded_at >= thirty_days_ago.date()
        ).with_only_columns(
            CostRecord.timestamp,
            CostRecord.recorded_at,
            CostRecord.cost_usd,
        )

        result = await self.db.execute(q)
        rows = result.all()

        hourly_totals: Dict[datetime, float] = {}
        total_spend = 0.0
        for row in rows:
            timestamp_value = row[0]
            recorded_at = row[1]
            cost_raw = row[2]
            if cost_raw is None:
                continue

            cost = float(cost_raw)
            total_spend += cost
            if timestamp_value is not None:
                hour_key = timestamp_value
                if hour_key.tzinfo is None:
                    hour_key = hour_key.replace(tzinfo=timezone.utc)
                hour_key = hour_key.astimezone(timezone.utc).replace(
                    minute=0,
                    second=0,
                    microsecond=0,
                )
            else:
                hour_key = datetime.combine(recorded_at, dt_time.min, tzinfo=timezone.utc)

            hourly_totals[hour_key] = hourly_totals.get(hour_key, 0.0) + cost

        hourly_values = list(hourly_totals.values())
        non_zero_hourly = [value for value in hourly_values if value > 0]
        observed_hours = len(hourly_values)
        expected_hours = 30 * 24
        coverage_ratio = min(1.0, (observed_hours / expected_hours)) if expected_hours else 0.0

        average_hourly_spend = float(fmean(hourly_values)) if hourly_values else 0.0
        baseline_hourly_spend = self._percentile(non_zero_hourly, 0.25) if non_zero_hourly else 0.0

        volatility = 0.0
        if len(hourly_values) > 1 and average_hourly_spend > 0:
            volatility = float(pstdev(hourly_values) / average_hourly_spend)

        confidence_score = round(
            max(
                0.0,
                min(
                    1.0,
                    (coverage_ratio * 0.6)
                    + ((1.0 - min(volatility, 1.0)) * 0.4),
                ),
            ),
            3,
        )

        return {
            "total_monthly_spend": float(total_spend),
            "average_hourly_spend": average_hourly_spend,
            "baseline_hourly_spend": baseline_hourly_spend,
            # Backward-compatible alias for older strategy code paths.
            "min_hourly_spend": baseline_hourly_spend,
            "observed_hours": observed_hours,
            "coverage_ratio": coverage_ratio,
            "volatility": volatility,
            "confidence_score": confidence_score,
            "region": "global",
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
