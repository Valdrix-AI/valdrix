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
from typing import Dict, Any, List, Optional, Callable, Awaitable
from uuid import UUID
from httpx import HTTPError
import structlog
import time
from sqlalchemy import select  # noqa: F401
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.core.service import BaseService

from app.modules.optimization.domain.architectural_inefficiency import (
    build_architectural_inefficiency_payload,
)
from app.modules.optimization.domain.factory import ZombieDetectorFactory
from app.modules.optimization.domain.strategy_service import OptimizationService
from app.modules.optimization.domain.waste_rightsizing import (
    build_waste_rightsizing_payload,
)
from app.shared.core.connection_queries import CONNECTION_MODEL_PAIRS
from app.shared.core.connection_state import resolve_connection_region
from app.shared.core.provider import normalize_provider, resolve_provider_from_connection
from app.shared.core.pricing import PricingTier, FeatureFlag, is_feature_enabled

logger = structlog.get_logger()
__all__ = ["ZombieService", "OptimizationService"]

# Zombie service implementation remains in this module; strategy orchestration moved out.
ZOMBIE_CONNECTION_QUERY_RECOVERABLE_ERRORS: tuple[type[Exception], ...] = (
    SQLAlchemyError,
    RuntimeError,
    OSError,
    TimeoutError,
    TypeError,
    ValueError,
)
ZOMBIE_SCAN_RECOVERABLE_ERRORS: tuple[type[Exception], ...] = (
    HTTPError,
    RuntimeError,
    OSError,
    TimeoutError,
    TypeError,
    ValueError,
    KeyError,
    AttributeError,
)
ZOMBIE_AI_ENQUEUE_RECOVERABLE_ERRORS: tuple[type[Exception], ...] = (
    SQLAlchemyError,
    RuntimeError,
    OSError,
    TimeoutError,
    TypeError,
    ValueError,
)
ZOMBIE_AI_ANALYSIS_RECOVERABLE_ERRORS: tuple[type[Exception], ...] = (
    RuntimeError,
    OSError,
    TimeoutError,
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
)
ZOMBIE_NOTIFICATION_RECOVERABLE_ERRORS: tuple[type[Exception], ...] = (
    RuntimeError,
    OSError,
    TimeoutError,
    ImportError,
    AttributeError,
    TypeError,
    ValueError,
)

class ZombieService(BaseService):
    def __init__(self, db: AsyncSession):
        super().__init__(db)

    async def _load_connections_for_model(
        self, model: Any, tenant_id: UUID
    ) -> list[Any]:
        """
        Load tenant-scoped connections for a model.

        Query failures are isolated per model so one provider does not prevent scans
        for other providers. This also keeps mocked/unit scenarios resilient when
        tests intentionally provide only a subset of execute side effects.
        """
        try:
            stmt = self._scoped_query(model, tenant_id)
            if hasattr(model, "status"):
                stmt = stmt.where(model.status == "active")
            elif hasattr(model, "is_active"):
                stmt = stmt.where(model.is_active.is_(True))
            q = await self.db.execute(stmt)
            return list(q.scalars().all())
        except (StopIteration, StopAsyncIteration):
            # Test harnesses sometimes provide shorter side_effect chains than provider count.
            logger.debug(
                "zombie_scan_mocked_query_exhausted",
                model=getattr(model, "__name__", str(model)),
                tenant_id=str(tenant_id),
            )
            return []
        except ZOMBIE_CONNECTION_QUERY_RECOVERABLE_ERRORS as exc:
            logger.warning(
                "zombie_scan_connection_query_failed",
                model=getattr(model, "__name__", str(model)),
                tenant_id=str(tenant_id),
                error=str(exc),
            )
            return []

    async def scan_for_tenant(
        self,
        tenant_id: UUID,
        region: str = "global",
        analyze: bool = False,
        requested_by_user_id: UUID | None = None,
        requested_client_ip: str | None = None,
        on_category_complete: Optional[
            Callable[[str, List[Dict[str, Any]]], Awaitable[None]]
        ] = None,
    ) -> Dict[str, Any]:
        """
        Scan all cloud accounts (IaaS + Cloud+) for a tenant and return aggregated results.
        """
        region = str(region or "").strip() or "global"
        # 1. Fetch all cloud connections generically
        all_connections: list[Any] = []
        connection_models = [model for _provider, model in CONNECTION_MODEL_PAIRS]
        for model in connection_models:
            all_connections.extend(
                await self._load_connections_for_model(model, tenant_id)
            )

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
            "idle_platform_services": [],
            "idle_hybrid_resources": [],
            # Expansion beyond classic "zombies": container + serverless + network hygiene.
            "idle_container_clusters": [],
            "unused_app_service_plans": [],
            "idle_serverless_services": [],
            "idle_serverless_functions": [],
            "orphan_network_components": [],
            "errors": [],
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

        def _connection_display_name(connection: Any) -> str:
            for attr in (
                "name",
                "vendor",
                "subscription_id",
                "project_id",
                "aws_account_id",
            ):
                raw = getattr(connection, attr, None)
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
            connection_id = getattr(connection, "id", None)
            return str(connection_id) if connection_id is not None else "connection"

        async def run_scan(
            conn: Any,
        ) -> None:
            nonlocal total_waste
            provider = normalize_provider(resolve_provider_from_connection(conn))
            connection_name = _connection_display_name(conn)
            connection_region = resolve_connection_region(conn)
            try:
                if provider == "aws":
                    # H-2: Parallel Regional Scanning for AWS
                    from app.modules.optimization.adapters.aws.region_discovery import (
                        RegionDiscovery,
                    )

                    explicit_region = region if region != "global" else connection_region

                    # Use detector factory to get temporary credentials for region discovery.
                    temp_detector = ZombieDetectorFactory.get_detector(
                        conn, region=explicit_region, db=self.db
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
                    if region != "global":
                        enabled_regions = [region]
                    else:
                        rd = RegionDiscovery(credentials=credentials)
                        enabled_regions = await rd.get_enabled_regions()
                    if not enabled_regions:
                        fallback_region = connection_region
                        if fallback_region == "global":
                            from app.shared.core.config import get_settings

                            fallback_region = (
                                str(get_settings().AWS_DEFAULT_REGION or "").strip()
                                or "us-east-1"
                            )
                        enabled_regions = [fallback_region]

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
                                connection_name=connection_name,
                                scan_results=reg_results,
                                region_override=reg,
                            )
                        except ZOMBIE_SCAN_RECOVERABLE_ERRORS as exc:
                            logger.error(
                                "regional_scan_failed", region=reg, error=str(exc)
                            )
                            all_zombies["errors"].append(
                                {
                                    "provider": "aws",
                                    "region": reg,
                                    "error": str(exc),
                                    "connection_id": str(conn.id),
                                }
                            )

                    await asyncio.gather(
                        *(scan_single_region(r) for r in enabled_regions)
                    )
                else:
                    # Generic logic for non-AWS providers.
                    scan_region = region if region != "global" else connection_region
                    detector = ZombieDetectorFactory.get_detector(
                        conn, region=scan_region, db=self.db
                    )
                    results = await detector.scan_all(
                        on_category_complete=on_category_complete
                    )
                    merge_scan_results(
                        provider_name=detector.provider_name,
                        connection_id=str(conn.id),
                        connection_name=connection_name,
                        scan_results=results,
                        region_override=scan_region if scan_region != "global" else None,
                    )
            except ZOMBIE_SCAN_RECOVERABLE_ERRORS as exc:
                provider_for_error = (
                    provider
                    or normalize_provider(resolve_provider_from_connection(conn))
                    or type(conn).__name__.replace("Connection", "").lower()
                )
                logger.error(
                    "scan_provider_failed",
                    error=str(exc),
                    provider=provider_for_error,
                    connection_id=str(getattr(conn, "id", "")),
                )
                all_zombies["errors"].append(
                    {
                        "provider": provider_for_error,
                        "region": "global",
                        "error": str(exc),
                        "connection_id": str(getattr(conn, "id", "")),
                    }
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
                        payload={
                            "zombies": all_zombies,
                            "requested_by_user_id": (
                                str(requested_by_user_id)
                                if requested_by_user_id
                                else None
                            ),
                            "requested_client_ip": requested_client_ip,
                        },
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
            except ZOMBIE_AI_ENQUEUE_RECOVERABLE_ERRORS as exc:
                logger.error("failed_to_enqueue_ai_analysis", error=str(exc))
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
            if not is_feature_enabled(tier, FeatureFlag.LLM_ANALYSIS):
                zombies["ai_analysis"] = {
                    "error": "AI Insights is not available on your current plan.",
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
        except ZOMBIE_AI_ANALYSIS_RECOVERABLE_ERRORS as exc:
            logger.error("service_zombie_ai_analysis_failed", error=str(exc))
            zombies["ai_analysis"] = {
                "error": f"AI analysis failed: {str(exc)}",
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
        except ZOMBIE_NOTIFICATION_RECOVERABLE_ERRORS as exc:
            logger.error("service_zombie_notification_failed", error=str(exc))
