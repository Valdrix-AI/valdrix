"""
FinOps Analysis Job Handler
"""
from typing import Dict, Any
from datetime import date, timedelta
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.background_job import BackgroundJob
from app.modules.governance.domain.jobs.handlers.base import BaseJobHandler


class FinOpsAnalysisHandler(BaseJobHandler):
    """Handle multi-tenant FinOps analysis with normalized components."""
    
    async def execute(self, job: BackgroundJob, db: AsyncSession) -> Dict[str, Any]:
        from app.shared.llm.analyzer import FinOpsAnalyzer
        from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
        from app.models.aws_connection import AWSConnection
        from app.shared.llm.factory import LLMFactory
        from app.shared.core.config import get_settings
        
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
        settings = get_settings()
        llm = LLMFactory.create(settings.LLM_PROVIDER)
        analyzer = FinOpsAnalyzer(llm=llm)
        analysis = await analyzer.analyze(usage_summary, tenant_id=tenant_id, db=db)
        
        return {"status": "completed", "analysis_length": len(analysis)}
