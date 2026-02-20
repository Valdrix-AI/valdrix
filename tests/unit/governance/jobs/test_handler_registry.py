from app.models.background_job import JobType
from app.modules.governance.domain.jobs.handlers import get_handler_factory
from app.modules.governance.domain.jobs.handlers.analysis import (
    ReportGenerationHandler,
    ZombieAnalysisHandler,
)
from app.modules.governance.domain.jobs.handlers.license_governance import (
    LicenseGovernanceHandler,
)


def test_license_governance_handler_registered() -> None:
    handler_cls = get_handler_factory(JobType.LICENSE_GOVERNANCE.value)
    assert handler_cls is LicenseGovernanceHandler


def test_zombie_analysis_handler_registered() -> None:
    handler_cls = get_handler_factory(JobType.ZOMBIE_ANALYSIS.value)
    assert handler_cls is ZombieAnalysisHandler


def test_report_generation_handler_registered() -> None:
    handler_cls = get_handler_factory(JobType.REPORT_GENERATION.value)
    assert handler_cls is ReportGenerationHandler
