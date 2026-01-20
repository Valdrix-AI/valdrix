"""
Job Handlers Registry
"""
from typing import Dict, Type
from app.models.background_job import JobType
from app.services.jobs.handlers.base import BaseJobHandler
from app.services.jobs.handlers.finops import FinOpsAnalysisHandler
from app.services.jobs.handlers.zombie import ZombieScanHandler
from app.services.jobs.handlers.remediation import RemediationHandler
from app.services.jobs.handlers.billing import RecurringBillingHandler
from app.services.jobs.handlers.costs import CostIngestionHandler, CostForecastHandler, CostExportHandler
from app.services.jobs.handlers.notifications import NotificationHandler, WebhookRetryHandler


# Global registry of job handlers
# Maps JobType value to Handler Class
HANDLER_REGISTRY: Dict[str, Type[BaseJobHandler]] = {
    JobType.FINOPS_ANALYSIS.value: FinOpsAnalysisHandler,
    JobType.ZOMBIE_SCAN.value: ZombieScanHandler,
    JobType.REMEDIATION.value: RemediationHandler,
    JobType.RECURRING_BILLING.value: RecurringBillingHandler,
    JobType.COST_INGESTION.value: CostIngestionHandler,
    JobType.COST_FORECAST.value: CostForecastHandler,
    JobType.COST_EXPORT.value: CostExportHandler,
    JobType.NOTIFICATION.value: NotificationHandler,
    JobType.WEBHOOK_RETRY.value: WebhookRetryHandler,
}


def get_handler_factory(job_type: str) -> Type[BaseJobHandler]:
    """
    Get the handler class for a given job type.
    """
    handler_cls = HANDLER_REGISTRY.get(job_type)
    if not handler_cls:
        raise ValueError(f"No handler registered for job type: {job_type}")
    return handler_cls
