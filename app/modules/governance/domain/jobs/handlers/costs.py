"""
Cost Management Job Handlers
"""
import structlog
from typing import Dict, Any
from datetime import datetime, timezone, timedelta, date
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.background_job import BackgroundJob
from app.modules.governance.domain.jobs.handlers.base import BaseJobHandler

logger = structlog.get_logger()


class CostIngestionHandler(BaseJobHandler):
    """Processes high-fidelity cost ingestion for cloud accounts (Multi-Cloud)."""
    
    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.shared.adapters.factory import AdapterFactory
        from app.modules.reporting.domain.persistence import CostPersistenceService
        from app.models.aws_connection import AWSConnection
        from app.models.azure_connection import AzureConnection
        from app.models.gcp_connection import GCPConnection
        from app.models.cloud import CloudAccount
        from sqlalchemy.dialects.postgresql import insert as pg_insert
        
        tenant_id = job.tenant_id
        if not tenant_id:
            raise ValueError("tenant_id required for cost_ingestion")
            
        # 1. Get Connections from all providers
        connections = []
        
        # AWS
        aws_result = await db.execute(select(AWSConnection).where(AWSConnection.tenant_id == tenant_id))
        connections.extend(aws_result.scalars().all())
        # Azure
        azure_result = await db.execute(select(AzureConnection).where(AzureConnection.tenant_id == tenant_id))
        connections.extend(azure_result.scalars().all())
        # GCP
        gcp_result = await db.execute(select(GCPConnection).where(GCPConnection.tenant_id == tenant_id))
        connections.extend(gcp_result.scalars().all())
        
        if not connections:
            return {"status": "skipped", "reason": "no_active_connections"}

        persistence = CostPersistenceService(db)
        results = []
        
        for conn in connections:
            stmt = pg_insert(CloudAccount).values(
                id=conn.id,
                tenant_id=conn.tenant_id,
                provider=conn.provider,
                name=getattr(conn, "name", f"{conn.provider.upper()} Connection"),
                is_active=True
            ).on_conflict_do_update(
                index_elements=['id'],
                set_={
                    "provider": conn.provider,
                    "name": getattr(conn, "name", f"{conn.provider.upper()} Connection")
                }
            )
            await db.execute(stmt)
        # Removed redundant commit here as JobProcessor handles it (BE-TRANS-1)
        
        # 2. Process each connection via its appropriate adapter
        checkpoint = job.payload.get("checkpoint", {}) if job.payload else {}
        completed_conns = checkpoint.get("completed_connections", [])
        
        for conn in connections:
            conn_id_str = str(conn.id)
            if conn_id_str in completed_conns:
                logger.info("skipping_already_ingested_connection", connection_id=conn_id_str)
                continue
                
            try:
                adapter = AdapterFactory.get_adapter(conn)
                
                # Default range: Last 7 days
                end_date = datetime.now(timezone.utc)
                start_date = end_date - timedelta(days=7)
                
                # Stream costs using normalized interface
                cost_stream = adapter.stream_cost_and_usage(
                    start_date=start_date,
                    end_date=end_date,
                    granularity="HOURLY"
                )
                
                records_ingested = 0
                total_cost_acc = 0.0
                
                async def tracking_wrapper(stream):
                    nonlocal records_ingested, total_cost_acc
                    async for r in stream:
                        records_ingested += 1
                        total_cost_acc += float(r.get("cost_usd", 0) or 0)
                        yield r

                save_result = await persistence.save_records_stream(
                    records=tracking_wrapper(cost_stream),
                    tenant_id=tenant_id,  # Use UUID object
                    account_id=conn.id  # Use UUID object (BE-UUID-1)
                )
                
                conn.last_ingested_at = datetime.now(timezone.utc)
                db.add(conn) 
                
                results.append({
                    "connection_id": str(conn.id),
                    "provider": conn.provider,
                    "records_ingested": save_result.get("records_saved", 0),
                    "total_cost": total_cost_acc
                })
                    
            except Exception as e:
                logger.error("cost_ingestion_connection_failed", connection_id=str(conn.id), error=str(e))
                if hasattr(conn, "error_message"):
                    conn.error_message = str(e)[:255]
                    db.add(conn)
                results.append({"connection_id": str(conn.id), "status": "failed", "error": str(e)})
            
            if "completed_connections" not in completed_conns:
                completed_conns.append(conn_id_str)
                job.payload = {**checkpoint, "completed_connections": completed_conns}
                # Redundant commit removed (BE-TRANS-1)
        
        # 3. Trigger Attribution Engine (FinOps Audit 2)
        try:
            from app.modules.reporting.domain.attribution_engine import AttributionEngine
            engine = AttributionEngine(db)
            # Use last 30 days for attribution context (FinOps Audit 2)
            now = datetime.now(timezone.utc).date()
            thirty_days_ago = now - timedelta(days=30)
            await engine.apply_rules_to_tenant(tenant_id, start_date=thirty_days_ago, end_date=now)
            logger.info("attribution_applied_post_ingestion", tenant_id=str(tenant_id))
        except Exception as e:
            logger.error("attribution_trigger_failed", tenant_id=str(tenant_id), error=str(e))

        return {
            "status": "completed",
            "connections_processed": len(connections),
            "details": results
        }


class CostForecastHandler(BaseJobHandler):
    """Handle multi-tenant cost forecasting as a background job."""
    
    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.modules.reporting.domain.aggregator import CostAggregator
        from app.shared.analysis.forecaster import SymbolicForecaster
        
        payload = job.payload or {}
        tenant_id = job.tenant_id
        start_date = date.fromisoformat(payload.get("start_date"))
        end_date = date.fromisoformat(payload.get("end_date"))
        days = payload.get("days", 30)
        provider = payload.get("provider")
        
        # 1. Fetch full summary for forecasting
        summary = await CostAggregator.get_summary(
            db, tenant_id, start_date, end_date, provider
        )
        
        if not summary.records:
            return {"status": "skipped", "reason": "no_data"}
            
        # 2. Run deterministic forecast
        # Phase 3: Symbolic Forecast
        result = await SymbolicForecaster.forecast(
            summary.records, 
            days=days,
            db=db,
            tenant_id=tenant_id
        )
        
        return {
            "status": "completed",
            "forecast": result,
            "tenant_id": str(tenant_id)
        }


class CostExportHandler(BaseJobHandler):
    """Handle large cost data exports asynchronously."""
    
    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.modules.reporting.domain.aggregator import CostAggregator
        
        payload = job.payload or {}
        tenant_id = job.tenant_id
        start_date = date.fromisoformat(payload.get("start_date"))
        end_date = date.fromisoformat(payload.get("end_date"))
        export_format = payload.get("format", "json")
        
        logger.info("cost_export_started", 
                    tenant_id=str(tenant_id),
                    start_date=str(start_date),
                    end_date=str(end_date))
        
        # 1. Get cached breakdown for fast aggregation
        breakdown = await CostAggregator.get_cached_breakdown(
            db, tenant_id, start_date, end_date
        )
        
        # 2. For detailed export, fetch full records
        summary = await CostAggregator.get_summary(
            db, tenant_id, start_date, end_date
        )
        
        # 3. Prepare export data
        export_data = {
            "tenant_id": str(tenant_id),
            "date_range": {
                "start": str(start_date),
                "end": str(end_date)
            },
            "summary": breakdown,
            "records_count": len(summary.records) if summary.records else 0,
            "total_cost": float(summary.total_cost) if summary.total_cost else 0
        }
        
        logger.info("cost_export_completed", 
                    tenant_id=str(tenant_id),
                    records_exported=export_data["records_count"])
        
        return {
            "status": "completed",
            "export_format": export_format,
            "records_exported": export_data["records_count"],
            "total_cost_usd": export_data["total_cost"],
            "download_url": None  # In production: S3 presigned URL
        }
class CostAggregationHandler(BaseJobHandler):
    """Handle large cost data aggregations asynchronously."""
    
    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.modules.reporting.domain.aggregator import CostAggregator
        
        payload = job.payload or {}
        tenant_id = job.tenant_id
        start_date = date.fromisoformat(payload.get("start_date"))
        end_date = date.fromisoformat(payload.get("end_date"))
        provider = payload.get("provider")
        
        logger.info("cost_aggregation_job_started", 
                    tenant_id=str(tenant_id),
                    start_date=str(start_date),
                    end_date=str(end_date))
        
        # 1. Run the intensive aggregation (which is now protected by timeout/limits)
        # In a background job, we might relax the timeout slightly if needed, 
        # but here we follow the same production rules.
        result = await CostAggregator.get_summary(
            db, tenant_id, start_date, end_date, provider
        )
        
        # 2. Store the result in the job's result field (serialized)
        # Note: Summary includes a list of potentially many records.
        # For very large results, we'd normally store in S3/Redis.
        # But for this implementation, we store a summary.
        
        return {
            "status": "completed",
            "total_cost_usd": float(result.total_cost),
            "record_count": len(result.records),
            "by_service": {k: float(v) for k, v in result.by_service.items()}
        }
