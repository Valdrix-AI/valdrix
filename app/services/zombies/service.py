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
from typing import Dict, Any, List
import structlog
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.services.zombies.factory import ZombieDetectorFactory
from app.core.tier_guard import TierGuard, FeatureFlag

logger = structlog.get_logger()

class ZombieService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def scan_for_tenant(
        self, 
        tenant_id: Any, 
        user: Any, 
        region: str = "us-east-1", 
        analyze: bool = False
    ) -> Dict[str, Any]:
        """
        Scan all cloud accounts (AWS, Azure, GCP) for a tenant and return aggregated results.
        """
        # 1. Fetch all cloud connections
        aws_q = await self.db.execute(select(AWSConnection).where(AWSConnection.tenant_id == tenant_id))
        azure_q = await self.db.execute(select(AzureConnection).where(AzureConnection.tenant_id == tenant_id))
        gcp_q = await self.db.execute(select(GCPConnection).where(GCPConnection.tenant_id == tenant_id))
        
        aws_connections = aws_q.scalars().all()
        azure_connections = azure_q.scalars().all()
        gcp_connections = gcp_q.scalars().all()

        all_connections = list(aws_connections) + list(azure_connections) + list(gcp_connections)

        if not all_connections:
            return {
                "resources": {},
                "total_monthly_waste": 0.0,
                "error": "No cloud connections found."
            }

        # 2. Execute scans across all providers
        all_zombies = {
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
            "scanned_connections": len(all_connections)
        }
        total_waste = 0.0

        # Mapping cloud-specific keys to frontend category keys
        category_mapping = {
            "unattached_disks": "unattached_volumes",  # Azure/GCP Disk -> Volume
            "orphaned_ips": "unused_elastic_ips",     # Azure/GCP IP -> EIP
        }

        async def run_scan(conn):
            nonlocal total_waste
            try:
                # Use standard us-east-1 if connection is AWS, or use global/region accordingly
                # Azure/GCP detectors handle 'global' themselves if needed.
                scan_region = region if isinstance(conn, AWSConnection) else "global"
                
                # AWSCrossAccount logic for creds if needed, though DetectorFactory/Detector handle it
                detector = ZombieDetectorFactory.get_detector(conn, region=scan_region)
                
                # Execute detector scan (runs all plugins for that provider)
                results = await detector.scan_all()
                
                for category, items in results.items():
                    # Map to frontend key if necessary
                    ui_key = category_mapping.get(category, category)
                    
                    if ui_key in all_zombies:
                        # Append and tag with provider/connection info
                        for item in items:
                            item["provider"] = detector.provider_name
                            item["connection_id"] = str(conn.id)
                            item["connection_name"] = getattr(conn, "name", "Other")
                            item["resource_id"] = item.get("id") or item.get("resource_id")
                            
                            cost = float(item.get("monthly_waste") or item.get("monthly_cost") or 0)
                            item["monthly_cost"] = cost # Ensure legacy compatibility
                            
                            all_zombies[ui_key].append(item)
                            total_waste += cost
            except Exception as e:
                logger.error("scan_provider_failed", error=str(e), provider=type(conn).__name__)

        # Execute all scans in parallel
        await asyncio.gather(*(run_scan(c) for c in all_connections))

        all_zombies["total_monthly_waste"] = round(total_waste, 2)

        # 3. AI Analysis
        if analyze:
            await self._enrich_with_ai(all_zombies, user)

        # 4. Notifications
        await self._send_notifications(all_zombies)

        return all_zombies

    async def _enrich_with_ai(self, zombies: Dict[str, Any], user: Any):
        """Enrich results with AI insights if tier allows."""
        try:
            async with TierGuard(user, self.db) as guard:
                if not guard.has(FeatureFlag.AI_INSIGHTS):
                    zombies["ai_analysis"] = {
                        "error": "AI Insights requires Starter tier or higher.",
                        "summary": "Upgrade to unlock AI-powered analysis.",
                        "upgrade_required": True
                    }
                else:
                    from app.services.llm.factory import LLMFactory
                    from app.services.llm.zombie_analyzer import ZombieAnalyzer

                    llm = LLMFactory.create()
                    analyzer = ZombieAnalyzer(llm)

                    ai_analysis = await analyzer.analyze(
                        detection_results=zombies,
                        tenant_id=user.tenant_id,
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
            from app.services.notifications import get_slack_service
            slack = get_slack_service()
            if slack:
                estimated_savings = zombies.get("total_monthly_waste", 0.0)
                await slack.notify_zombies(zombies, estimated_savings)
        except Exception as e:
            logger.error("service_zombie_notification_failed", error=str(e))
