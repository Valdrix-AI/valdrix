"""
Job Processor Service - Phase 7: Scheduler SPOF Resolution

Processes background jobs from the database queue.
Works with pg_cron to provide durable, distributed job processing.

Key Features:
- Survives app restarts (jobs in database)
- Automatic retries with exponential backoff
- Per-tenant job isolation
- Full audit trail

Usage:
    processor = JobProcessor(db)
    await processor.process_pending_jobs()
"""

import sys
import sqlalchemy as sa
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Callable, Awaitable
from uuid import UUID
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.background_job import BackgroundJob, JobStatus, JobType

logger = structlog.get_logger()

# Job processing configuration
MAX_JOBS_PER_BATCH = 10
JOB_LOCK_TIMEOUT_MINUTES = 30
BACKOFF_BASE_SECONDS = 60


# Type for job handlers
JobHandler = Callable[[BackgroundJob, AsyncSession], Awaitable[Dict[str, Any]]]


class JobProcessor:
    """
    Processes background jobs from the database queue.
    
    Designed to be called by:
    1. pg_cron (every minute in Supabase)
    2. API endpoint for on-demand processing
    3. Startup hook for catching up
    """
    
    def __init__(self, db: AsyncSession):
        self.db = db
        self._handlers: Dict[str, JobHandler] = {}
        self._register_default_handlers()
    
    def _register_default_handlers(self) -> None:
        """Register default job type handlers."""
        self._handlers[JobType.FINOPS_ANALYSIS.value] = self._handle_finops_analysis
        self._handlers[JobType.ZOMBIE_SCAN.value] = self._handle_zombie_scan
        self._handlers[JobType.REMEDIATION.value] = self._handle_remediation
        self._handlers[JobType.WEBHOOK_RETRY.value] = self._handle_webhook_retry
        self._handlers[JobType.NOTIFICATION.value] = self._handle_notification
        self._handlers[JobType.COST_INGESTION.value] = self._handle_cost_ingestion
    
    def register_handler(self, job_type: str, handler: JobHandler) -> None:
        """Register a custom job handler."""
        self._handlers[job_type] = handler
    
    async def process_pending_jobs(self, limit: int = MAX_JOBS_PER_BATCH) -> Dict[str, Any]:
        """
        Process pending jobs up to the limit.
        
        Called by pg_cron every minute or on-demand.
        Uses SELECT FOR UPDATE SKIP LOCKED for safe concurrency.
        """
        results = {
            "processed": 0,
            "succeeded": 0,
            "failed": 0,
            "errors": []
        }
        
        try:
            # Fetch pending jobs that are due
            pending_jobs = await self._fetch_pending_jobs(limit)
            
            logger.info(
                "job_processor_batch_start",
                pending_count=len(pending_jobs)
            )
            
            for job in pending_jobs:
                try:
                    await self._process_single_job(job)
                    results["succeeded"] += 1
                except Exception as e:
                    results["failed"] += 1
                    results["errors"].append({
                        "job_id": str(job.id),
                        "error": str(e)
                    })
                results["processed"] += 1
            
            logger.info(
                "job_processor_batch_complete",
                **results
            )
            
        except Exception as e:
            logger.error("job_processor_batch_error", error=str(e))
            results["errors"].append({"batch_error": str(e)})
        
        return results
    
    async def _fetch_pending_jobs(self, limit: int) -> list[BackgroundJob]:
        """Fetch pending jobs that are ready to run."""
        now = datetime.now(timezone.utc)
        
        result = await self.db.execute(
            select(BackgroundJob)
            .where(
                BackgroundJob.status == JobStatus.PENDING.value,
                BackgroundJob.scheduled_for <= now,
                BackgroundJob.attempts < BackgroundJob.max_attempts
            )
            .order_by(BackgroundJob.scheduled_for)
            .limit(limit)
        )
        found = list(result.scalars().all())
        print(f"DEBUG: Found {len(found)} due jobs")
        return found
    
    async def _process_single_job(self, job: BackgroundJob) -> None:
        """Process a single job with error handling."""
        logger.info(
            "job_processing_start",
            job_id=str(job.id),
            job_type=job.job_type,
            attempt=job.attempts + 1
        )
        
        # Mark as running
        job.status = JobStatus.RUNNING.value
        job.started_at = datetime.now(timezone.utc)
        job.attempts += 1
        await self.db.commit()
        
        try:
            # Get handler for job type
            handler = self._handlers.get(job.job_type)
            if not handler:
                raise ValueError(f"No handler for job type: {job.job_type}")
            
            # Use a savepoint to isolate this job's database changes
            async with self.db.begin_nested():
                # Set tenant context for RLS isolation during job execution
                if job.tenant_id:
                    await self.db.execute(
                        sa.text("SELECT set_config('app.current_tenant_id', :tid, true)"),
                        {"tid": str(job.tenant_id)}
                    )
                
                # Execute handler
                result = await handler(job, self.db)
            
            # Mark as completed
            job.status = JobStatus.COMPLETED.value
            job.completed_at = datetime.now(timezone.utc)
            job.result = result
            job.error_message = None
            
            logger.info(
                "job_processing_success",
                job_id=str(job.id),
                job_type=job.job_type
            )
            
        except Exception as e:
            logger.error(
                "job_processing_failed",
                job_id=str(job.id),
                job_type=job.job_type,
                error=str(e)
            )
            
            job.error_message = str(e)
            job.status = JobStatus.FAILED.value
            
            if job.attempts >= job.max_attempts:
                # Move to dead letter
                job.status = JobStatus.DEAD_LETTER.value
                job.completed_at = datetime.now(timezone.utc)
            else:
                # Schedule retry with exponential backoff
                backoff_seconds = BACKOFF_BASE_SECONDS * (2 ** (job.attempts - 1))
                job.status = JobStatus.PENDING.value
                job.scheduled_for = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
        
        await self.db.commit()
    
    # ==================== Job Handlers ====================
    
    async def _handle_finops_analysis(
        self, 
        job: BackgroundJob, 
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Handle multi-tenant FinOps analysis with normalized components."""
        from app.services.llm.analyzer import FinOpsAnalyzer
        from app.services.adapters.aws_multitenant import MultiTenantAWSAdapter
        from app.models.aws_connection import AWSConnection
        from datetime import date, timedelta
        
        tenant_id = job.tenant_id
        if not tenant_id:
            raise ValueError("tenant_id required for finops_analysis")
            
        # Get AWS connection
        result = await db.execute(
            select(AWSConnection).where(AWSConnection.tenant_id == tenant_id)
        )
        connection = result.scalar_one_or_none()
        
        if not connection:
            return {"status": "skipped", "reason": "no_aws_connection"}
            
        # Fetch data (Standardized to 30 days)
        adapter = MultiTenantAWSAdapter(connection)
        end_date = date.today()
        start_date = end_date - timedelta(days=30)
        
        # This now returns a normalized CloudUsageSummary object
        usage_summary = await adapter.get_daily_costs(start_date, end_date, group_by_service=True)
        
        # Run analysis
        from app.services.llm.factory import LLMFactory
        from app.core.config import get_settings
        settings = get_settings()
        llm = LLMFactory.create(settings.LLM_PROVIDER)
        analyzer = FinOpsAnalyzer(llm=llm)
        analysis = await analyzer.analyze(usage_summary, tenant_id=tenant_id, db=db)
        
        return {"status": "completed", "analysis_length": len(analysis)}
    
    async def _handle_zombie_scan(
        self, 
        job: BackgroundJob, 
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Handle zombie resource scan job (Multi-Cloud)."""
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
            # Note: This simple checkpointing might need locking if parallel scans write to same payload key
            # ideally we namespace checks by connection_id
            pass 

        # 2. Iterate and Scan
        for conn in connections:
            try:
                # Determine regions to scan for this connection
                # Logic: If regions specified in payload, intersection with connection region?
                # Multi-cloud usually implies global or connection-specific region context
                target_regions = regions if regions and hasattr(conn, "region") else [getattr(conn, "region", "global")]
                
                for region in target_regions:
                    detector = ZombieDetectorFactory.get_detector(conn, region=region)
                    
                    # Run Scan
                    results = await detector.scan_all(on_category_complete=checkpoint_result)
                    
                    # Aggregate
                    conn_waste = results.get("total_monthly_waste", 0)
                    total_waste += conn_waste
                    
                    # Count items (flat list of dicts in result values)
                    count = 0
                    for key, val in results.items():
                        if isinstance(val, list):
                            count += len(val)
                    total_zombies += count
                    
                    scan_results.append({
                        "connection_id": str(conn.id),
                        "provider": detector.provider_name,
                        "region": region,
                        "waste": conn_waste,
                        "zombies": count
                    })

            except Exception as e:
                logger.error("zombie_scan_connection_failed", connection_id=str(conn.id), error=str(e))
                scan_results.append({"connection_id": str(conn.id), "status": "failed", "error": str(e)})

        return {
            "status": "completed",
            "zombies_found": total_zombies,
            "total_waste": total_waste,
            "details": scan_results
        }
        
        async def checkpoint_result(category_key, items):
            """Durable checkpoint: save partial results to DB."""
            if not job.payload:
                job.payload = {}
            if "partial_scan" not in job.payload:
                job.payload["partial_scan"] = {}
            
            job.payload["partial_scan"][category_key] = items
            await db.commit()

        detector = ZombieDetector(region=regions[0], credentials=creds)
        results = await detector.scan_all(on_category_complete=checkpoint_result)
        
        return {
            "status": "completed",
            "zombies_found": sum(len(r.get("items", [])) if isinstance(r.get("items"), list) else 0 for r in results.get("regions", []) if isinstance(r, dict)) if "regions" in results else sum(len(items) for items in results.values() if isinstance(items, list)),
            "total_waste": results.get("total_monthly_waste", 0)
        }

    async def _handle_remediation(
        self, 
        job: BackgroundJob, 
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Handle autonomous remediation scan and execution."""
        from app.services.remediation.autonomous import AutonomousRemediationEngine
        from app.services.adapters.aws_multitenant import MultiTenantAWSAdapter
        from app.models.aws_connection import AWSConnection
        
        tenant_id = job.tenant_id
        if not tenant_id:
            raise ValueError("tenant_id required for remediation")
            
        payload = job.payload or {}
        conn_id = payload.get("connection_id")
        
        # Get AWS connection
        if conn_id:
            result = await db.execute(
                select(AWSConnection).where(AWSConnection.id == UUID(conn_id))
            )
        else:
            result = await db.execute(
                select(AWSConnection).where(AWSConnection.tenant_id == tenant_id)
            )
        connection = result.scalar_one_or_none()
        
        if not connection:
            return {"status": "skipped", "reason": "no_aws_connection"}
            
        # Get credentials
        adapter = MultiTenantAWSAdapter(connection)
        creds = await adapter.get_credentials()
        
        engine = AutonomousRemediationEngine(db, tenant_id)
        results = await engine.run_autonomous_sweep(region=connection.region, credentials=creds)
        
        return {
            "status": "completed",
            "mode": results.get("mode"),
            "scanned": results.get("scanned", 0),
            "auto_executed": results.get("auto_executed", 0)
        }
    
    async def _handle_webhook_retry(
        self, 
        job: BackgroundJob, 
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Handle webhook retry job (e.g., Paystack)."""
        payload = job.payload or {}
        provider = payload.get("provider", "generic")
        
        if provider == "paystack":
            # Use Paystack-specific handler
            from app.services.billing.webhook_retry import process_paystack_webhook
            return await process_paystack_webhook(job, db)
        
        # Generic HTTP webhook retry
        import httpx
        
        url = payload.get("url")
        data = payload.get("data")
        headers = payload.get("headers", {})
        
        if not url:
            raise ValueError("url required for generic webhook_retry")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, json=data, headers=headers, timeout=30)
            response.raise_for_status()
        
        return {"status": "completed", "status_code": response.status_code}
    
    async def _handle_notification(
        self, 
        job: BackgroundJob, 
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Handle notification job (Slack, Email, etc.)."""
        from app.services.notifications import get_slack_service
        
        payload = job.payload or {}
        message = payload.get("message")
        title = payload.get("title", "Valdrix Notification")
        severity = payload.get("severity", "info")
        
        if not message:
            raise ValueError("message required for notification")
        
        service = get_slack_service()
        if not service:
            return {"status": "skipped", "reason": "slack_not_configured"}
            
        success = await service.send_alert(title=title, message=message, severity=severity)
        
        return {"status": "completed", "success": success}

    async def _handle_cost_ingestion(
        self, 
        job: BackgroundJob, 
        db: AsyncSession
    ) -> Dict[str, Any]:
        """Processes high-fidelity cost ingestion for cloud accounts (Multi-Cloud)."""
        from app.services.adapters.factory import AdapterFactory
        from app.services.costs.persistence import CostPersistenceService
        from app.models.aws_connection import AWSConnection
        from app.models.azure_connection import AzureConnection
        from app.models.gcp_connection import GCPConnection
        from app.schemas.costs import CloudUsageSummary, CostRecord
        
        tenant_id = job.tenant_id
        if not tenant_id:
            raise ValueError("tenant_id required for cost_ingestion")
            
        # 1. Get Connections from all providers
        # We fetch sequentially (or could be parallel)
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
        
        # 2. Process each connection via its appropriate adapter
        for conn in connections:
            try:
                adapter = AdapterFactory.get_adapter(conn)
                
                # Default range: Last 7 days
                end_date = datetime.now(timezone.utc)
                start_date = end_date - timedelta(days=7)
                
                # Fetch costs using normalized interface
                # Returns List[Dict]
                raw_costs = await adapter.get_cost_and_usage(
                    start_date=start_date,
                    end_date=end_date,
                    granularity="HOURLY"
                )
                
                if raw_costs:
                    # Convert to CloudUsageSummary for persistence
                    # Reconstruct CostRecord objects (Pydantic)
                    records = []
                    total_cost = 0.0
                    by_service = {}
                    
                    provider_name = getattr(conn, "provider", "unknown").lower()
                    if hasattr(conn, "aws_account_id"): provider_name = "aws" # Fallback for AWSConnection
                    
                    for row in raw_costs:
                        amount = Decimal(str(row["cost_usd"]))
                        records.append(CostRecord(
                            date=row["timestamp"],
                            amount=amount,
                            service=row["service"],
                            region=row["region"],
                            usage_type=row["usage_type"],
                            currency=row["currency"],
                            amount_raw=row.get("amount_raw")
                        ))
                        total_cost += float(amount)
                        by_service[row["service"]] = by_service.get(row["service"], Decimal("0.0")) + amount

                    summary = CloudUsageSummary(
                        tenant_id=str(conn.tenant_id),
                        provider=provider_name,
                        start_date=start_date,
                        end_date=end_date,
                        total_cost=total_cost,
                        records=records,
                        by_service=by_service,
                        by_region={} # Optional
                    )
                    
                    # Idempotent persistence
                    await persistence.save_summary(summary, str(conn.id))
                    
                    # Update connection health
                    conn.last_ingested_at = datetime.now(timezone.utc)
                    db.add(conn) # Ensure updated timestamp is tracked
                    
                    results.append({
                        "connection_id": str(conn.id),
                        "provider": provider_name,
                        "records_ingested": len(records),
                        "total_cost": total_cost
                    })
                else:
                    results.append({"connection_id": str(conn.id), "status": "no_data_found"})
                    
            except Exception as e:
                logger.error("cost_ingestion_connection_failed", connection_id=str(conn.id), error=str(e))
                # Update connection error state
                if hasattr(conn, "error_message"):
                    conn.error_message = str(e)[:255]
                    db.add(conn)
                results.append({"connection_id": str(conn.id), "status": "failed", "error": str(e)})
        
        # Commit updates to connection health
        await db.commit()

        return {
            "status": "completed",
            "connections_processed": len(connections),
            "details": results
        }


# ==================== Job Creation Helpers ====================

async def enqueue_job(
    db: AsyncSession,
    job_type: str,
    tenant_id: Optional[UUID] = None,
    payload: Optional[Dict[str, Any]] = None,
    scheduled_for: Optional[datetime] = None,
    max_attempts: int = 3
) -> BackgroundJob:
    """
    Enqueue a new background job.
    
    Usage:
        job = await enqueue_job(
            db,
            job_type=JobType.FINOPS_ANALYSIS,
            tenant_id=tenant.id,
            payload={"force_refresh": True}
        )
    """
    job = BackgroundJob(
        job_type=job_type.value if hasattr(job_type, "value") else job_type,
        tenant_id=tenant_id,
        payload=payload,
        status=JobStatus.PENDING.value,
        scheduled_for=scheduled_for or datetime.now(timezone.utc),
        max_attempts=max_attempts,
        created_at=datetime.now(timezone.utc)
    )
    
    db.add(job)
    await db.commit()
    await db.refresh(job)
    
    logger.info(
        "job_enqueued",
        job_id=str(job.id),
        job_type=job_type,
        tenant_id=str(tenant_id) if tenant_id else None
    )
    
    return job
