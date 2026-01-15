"""
Scheduler Service - Package Entry Point

This file maintains backward compatibility by proxying calls to the 
refactored SchedulerOrchestrator in the .orchestrator sub-module.
"""

import structlog
from app.services.scheduler.orchestrator import SchedulerOrchestrator
from app.services.scheduler.cohorts import TenantCohort, get_tenant_cohort

logger = structlog.get_logger()

__all__ = ["SchedulerService", "SchedulerOrchestrator", "TenantCohort", "get_tenant_cohort"]

class SchedulerService(SchedulerOrchestrator):
    """
    Proxy class for backward compatibility. 
    Inherits from refactored Orchestrator to maintain existing API.
    """
    
    def __init__(self, session_maker):
        super().__init__(session_maker)
        logger.info("scheduler_proxy_initialized", refactor_version="1.0-modular")

    # Inherits start(), stop(), get_status(), cohort_analysis_job(), etc.
    # daily_analysis_job is replaced by cohort-based scanning in the new model,
    # but we can keep a stub if needed for legacy tests.
    
    async def daily_analysis_job(self):
        """Legacy entry point, proxies to a full scan if still needed."""
        logger.warning("legacy_daily_job_called", suggestion="Use cohort-based jobs instead")
        # For safety, we can run all cohorts or just HIGH_VALUE
        await self.cohort_analysis_job(TenantCohort.HIGH_VALUE)
        await self.cohort_analysis_job(TenantCohort.ACTIVE)
