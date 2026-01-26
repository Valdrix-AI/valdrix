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
from typing import Dict, Any, List, Optional, Union, Callable, Awaitable
from uuid import UUID
import structlog
import time
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.modules.optimization.domain.factory import ZombieDetectorFactory
from app.shared.core.pricing import PricingTier, FeatureFlag, is_feature_enabled

logger = structlog.get_logger()

class ZombieService:
    def __init__(self, db: AsyncSession):
        self.db = db
    async def scan_for_tenant(
        self, 
        tenant_id: UUID, 
        _user: Optional[Any] = None,
        region: str = "us-east-1",  
        analyze: bool = False,
        on_category_complete: Optional[Callable[[str, List[Dict[str, Any]]], Awaitable[None]]] = None
    ) -> Dict[str, Any]:
        """
        Scan all cloud accounts (AWS, Azure, GCP) for a tenant and return aggregated results.
        """
        # 1. Fetch all cloud connections generically
        # Phase 21: Decoupling from concrete models
        all_connections: List[Union[AWSConnection, AzureConnection, GCPConnection]] = []
        for model in [AWSConnection, AzureConnection, GCPConnection]:
            # Use cast or ignore if mypy cannot verify tenant_id exists on all models
            # but they all do in this codebase.
            q = await self.db.execute(select(model).where(model.tenant_id == tenant_id)) # type: ignore
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
            "load_balancer": [],
            "rds": [],
            "nat_gateway": [],
            "idle_s3_buckets": [],
            "legacy_ecr_images": [],
            "idle_sagemaker_endpoints": [],
            "cold_redshift_clusters": [],
        }
        all_zombies["scanned_connections"] = len(all_connections)
        total_waste = 0.0

        # Mapping cloud-specific keys to frontend category keys
        category_mapping = {
            "unattached_disks": "unattached_volumes",  # Azure/GCP Disk -> Volume
            "orphaned_ips": "unused_elastic_ips",     # Azure/GCP IP -> EIP
        }

        from app.shared.core.pricing import get_tenant_tier
        tier = await get_tenant_tier(tenant_id, self.db)
        has_precision = is_feature_enabled(tier, FeatureFlag.PRECISION_DISCOVERY)
        has_attribution = is_feature_enabled(tier, FeatureFlag.OWNER_ATTRIBUTION)

        async def run_scan(conn: Union[AWSConnection, AzureConnection, GCPConnection]) -> None:
            nonlocal total_waste
            try:
                scan_region = region if isinstance(conn, AWSConnection) else "global"
                detector = ZombieDetectorFactory.get_detector(conn, region=scan_region, db=self.db)
                results = await detector.scan_all(on_category_complete=on_category_complete)
                
                for category, items in results.items():
                    ui_key = category_mapping.get(category, category)
                    
                    if ui_key in all_zombies:
                        for item in items:
                            # Standardize resource fields
                            res_id = item.get("resource_id") or item.get("id")
                            cost = float(item.get("monthly_cost") or item.get("monthly_waste") or 0)
                            
                            item.update({
                                "provider": detector.provider_name,
                                "connection_id": str(conn.id),
                                "connection_name": getattr(conn, "name", "Other"),
                                "resource_id": res_id,
                                "monthly_cost": cost,
                                "is_gpu": bool(item.get("is_gpu", False)) if has_precision else "Upgrade to Growth",
                                "owner": item.get("owner", "unknown") if has_attribution else "Upgrade to Growth"
                            })
                            
                            all_zombies[ui_key].append(item)
                            total_waste += cost
            except Exception as e:
                logger.error("scan_provider_failed", error=str(e), provider=type(conn).__name__)

        # Execute all scans in parallel with a hard 5-minute timeout for the entire operation
        # BE-SCHED-3: Resilience - Prevent hanging API requests
        from app.shared.core.ops_metrics import SCAN_LATENCY, SCAN_TIMEOUTS
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
            SCAN_TIMEOUTS.labels(level="overall").inc()

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

    async def _enrich_with_ai(self, zombies: Dict[str, Any], tenant_id: Any, tier: PricingTier):
        """Enrich results with AI insights if tier allows."""
        try:
            if not is_feature_enabled(tier, FeatureFlag.LLM_ANALYSIS):
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

    async def _send_notifications(self, zombies: Dict[str, Any]):
        """Send notifications about detected zombies."""
        try:
            from app.modules.notifications.domain import get_slack_service
            slack = get_slack_service()
            if slack:
                estimated_savings = zombies.get("total_monthly_waste", 0.0)
                await slack.notify_zombies(zombies, estimated_savings)
        except Exception as e:
            logger.error("service_zombie_notification_failed", error=str(e))
