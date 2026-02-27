"""
Audit API router composition module.

This module keeps route wiring thin and delegates implementation to focused
submodules:
- audit_access.py
- audit_evidence.py
- audit_partitioning.py
- audit_compliance.py
"""

from fastapi import APIRouter

from app.modules.governance.api.v1.audit_access import (  # noqa: F401
    export_audit_logs,
    get_audit_log_detail,
    get_audit_logs,
    get_event_types,
    request_data_erasure,
    router as access_router,
)
from app.modules.governance.api.v1.audit_common import (  # noqa: F401
    _rowcount,
    _sanitize_csv_cell,
)
from app.modules.governance.api.v1.audit_compliance import (  # noqa: F401
    export_compliance_pack,
    router as compliance_router,
)
from app.modules.governance.api.v1.audit_evidence import (  # noqa: F401
    capture_carbon_assurance_evidence,
    capture_identity_idp_smoke_evidence,
    capture_ingestion_persistence_evidence,
    capture_ingestion_soak_evidence,
    capture_job_slo_evidence,
    capture_load_test_evidence,
    capture_sso_federation_validation_evidence,
    capture_tenant_isolation_evidence,
    list_carbon_assurance_evidence,
    list_identity_idp_smoke_evidence,
    list_ingestion_persistence_evidence,
    list_ingestion_soak_evidence,
    list_job_slo_evidence,
    list_load_test_evidence,
    list_sso_federation_validation_evidence,
    list_tenant_isolation_evidence,
    router as evidence_router,
)
from app.modules.governance.api.v1.audit_partitioning import (  # noqa: F401
    _compute_partitioning_evidence,
    capture_partitioning_evidence,
    list_partitioning_evidence,
    router as partitioning_router,
)
from app.modules.governance.api.v1.audit_schemas import *  # noqa: F401,F403

router = APIRouter(tags=["Audit"])
router.include_router(access_router)
router.include_router(evidence_router)
router.include_router(partitioning_router)
router.include_router(compliance_router)
