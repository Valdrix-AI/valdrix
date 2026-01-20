"""
Zombie Resource Scan Job Handlers
"""
import structlog
from typing import Dict, Any
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.background_job import BackgroundJob
from app.services.jobs.handlers.base import BaseJobHandler

logger = structlog.get_logger()


class ZombieScanHandler(BaseJobHandler):
    """Handle zombie resource scan job (Multi-Cloud)."""
    
    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.services.zombies.factory import ZombieDetectorFactory
        from app.models.aws_connection import AWSConnection
        from app.models.azure_connection import AzureConnection
        from app.models.gcp_connection import GCPConnection
        
        tenant_id = job.tenant_id
        if not tenant_id:
            raise ValueError("tenant_id required for zombie_scan")
            
        payload = job.payload or {}
        regions = payload.get("regions")
        
        # 1. Gather all connections
        connections = []
        
        # AWS
        aws_result = await db.execute(select(AWSConnection).where(AWSConnection.tenant_id == tenant_id))
        connections.extend(aws_result.scalars().all())
        # Azure
        az_result = await db.execute(select(AzureConnection).where(AzureConnection.tenant_id == tenant_id))
        connections.extend(az_result.scalars().all())
        # GCP
        gcp_result = await db.execute(select(GCPConnection).where(GCPConnection.tenant_id == tenant_id))
        connections.extend(gcp_result.scalars().all())

        if not connections:
            return {"status": "skipped", "reason": "no_connections_found"}
        
        total_zombies = 0
        total_waste = 0.0
        scan_results = []

        async def checkpoint_result(category_key, items):
            """Durable checkpoint: save partial results to DB."""
            if not job.payload:
                job.payload = {}
            if "partial_scan" not in job.payload:
                job.payload["partial_scan"] = {}
            
            job.payload["partial_scan"][category_key] = items

        # 2. Iterate and Scan
        checkpoint = payload.get("partial_scan", {})
        
        for conn in connections:
            conn_id_str = str(conn.id)
            if conn_id_str in checkpoint.get("completed_connections", []):
                logger.info("skipping_already_completed_connection", connection_id=conn_id_str)
                continue
                
            try:
                # Determine regions to scan for this connection
                target_regions = regions if regions and hasattr(conn, "region") else [getattr(conn, "region", "global")]
                
                for region in target_regions:
                    if region in checkpoint.get(conn_id_str, {}).get("completed_regions", []):
                        continue
                    detector = ZombieDetectorFactory.get_detector(conn, region=region)
                    
                    # Run Scan
                    results = await detector.scan_all(on_category_complete=checkpoint_result)
                    
                    # Aggregate
                    conn_waste = results.get("total_monthly_waste", 0)
                    total_waste += conn_waste
                    
                    # Count items (flat list of dicts in result values)
                    count = sum(len(val) for key, val in results.items() if isinstance(val, list))
                    total_zombies += count
                    
                    scan_results.append({
                        "connection_id": str(conn.id),
                        "provider": detector.provider_name,
                        "region": region,
                        "waste": float(conn_waste),
                        "zombies": count
                    })

            except Exception as e:
                logger.error("zombie_scan_connection_failed", connection_id=str(conn.id), error=str(e))
                scan_results.append({"connection_id": str(conn.id), "status": "failed", "error": str(e)})

        return {
            "status": "completed",
            "zombies_found": total_zombies,
            "total_waste": float(total_waste),
            "details": scan_results
        }
