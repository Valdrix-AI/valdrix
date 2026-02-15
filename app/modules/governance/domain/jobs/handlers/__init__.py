"""
Job Handlers Registry
"""

from typing import Dict, Type
from app.models.background_job import JobType
from app.modules.governance.domain.jobs.handlers.base import BaseJobHandler
from app.modules.governance.domain.jobs.handlers.finops import FinOpsAnalysisHandler
from app.modules.governance.domain.jobs.handlers.zombie import ZombieScanHandler
from app.modules.governance.domain.jobs.handlers.remediation import RemediationHandler
from app.modules.governance.domain.jobs.handlers.billing import RecurringBillingHandler
from app.modules.governance.domain.jobs.handlers.costs import (
    CostIngestionHandler,
    CostForecastHandler,
    CostExportHandler,
    CostAggregationHandler,
    CostAnomalyDetectionHandler,
)
from app.modules.governance.domain.jobs.handlers.notifications import (
    NotificationHandler,
    WebhookRetryHandler,
)
from app.modules.governance.domain.jobs.handlers.dunning import DunningHandler
from app.modules.governance.domain.jobs.handlers.acceptance import (
    AcceptanceSuiteCaptureHandler,
)


# Global registry of job handlers
# Maps JobType value to Handler Class
HANDLER_REGISTRY: Dict[str, Type[BaseJobHandler]] = {
    JobType.FINOPS_ANALYSIS.value: FinOpsAnalysisHandler,
    JobType.ZOMBIE_SCAN.value: ZombieScanHandler,
    JobType.REMEDIATION.value: RemediationHandler,
    JobType.ACCEPTANCE_SUITE_CAPTURE.value: AcceptanceSuiteCaptureHandler,
    JobType.RECURRING_BILLING.value: RecurringBillingHandler,
    JobType.COST_INGESTION.value: CostIngestionHandler,
    JobType.COST_ANOMALY_DETECTION.value: CostAnomalyDetectionHandler,
    JobType.COST_FORECAST.value: CostForecastHandler,
    JobType.COST_EXPORT.value: CostExportHandler,
    JobType.COST_AGGREGATION.value: CostAggregationHandler,
    JobType.NOTIFICATION.value: NotificationHandler,
    JobType.WEBHOOK_RETRY.value: WebhookRetryHandler,
    JobType.DUNNING.value: DunningHandler,
}


def get_handler_factory(job_type: str) -> Type[BaseJobHandler]:
    """
    Get the handler class for a given job type.
    """
    handler_cls = HANDLER_REGISTRY.get(job_type)
    if not handler_cls:
        raise ValueError(f"No handler registered for job type: {job_type}")
    return handler_cls
