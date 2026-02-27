from datetime import datetime, timezone
from typing import Annotated, Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.governance.api.v1.audit_schemas import (
    CarbonAssuranceEvidenceCaptureRequest,
    CarbonAssuranceEvidenceCaptureResponse,
    CarbonAssuranceEvidenceItem,
    CarbonAssuranceEvidenceListResponse,
    CarbonAssuranceEvidencePayload,
    IdentityIdpSmokeEvidenceCaptureResponse,
    IdentityIdpSmokeEvidenceItem,
    IdentityIdpSmokeEvidenceListResponse,
    IdentityIdpSmokeEvidencePayload,
    IngestionPersistenceEvidenceCaptureResponse,
    IngestionPersistenceEvidenceItem,
    IngestionPersistenceEvidenceListResponse,
    IngestionPersistenceEvidencePayload,
    IngestionSoakEvidenceCaptureResponse,
    IngestionSoakEvidenceItem,
    IngestionSoakEvidenceListResponse,
    IngestionSoakEvidencePayload,
    JobSLOEvidenceCaptureRequest,
    JobSLOEvidenceCaptureResponse,
    JobSLOEvidenceItem,
    JobSLOEvidenceListResponse,
    JobSLOEvidencePayload,
    LoadTestEvidenceCaptureResponse,
    LoadTestEvidenceItem,
    LoadTestEvidenceListResponse,
    LoadTestEvidencePayload,
    SsoFederationValidationEvidenceCaptureResponse,
    SsoFederationValidationEvidenceItem,
    SsoFederationValidationEvidenceListResponse,
    SsoFederationValidationEvidencePayload,
    TenantIsolationEvidenceCaptureResponse,
    TenantIsolationEvidenceItem,
    TenantIsolationEvidenceListResponse,
    TenantIsolationEvidencePayload,
)
from app.shared.core.auth import CurrentUser
from app.shared.core.dependencies import requires_feature
from app.shared.core.pricing import FeatureFlag
from app.shared.db.session import get_db

logger = structlog.get_logger()
router = APIRouter(tags=["Audit"])

@router.post(
    "/performance/load-test/evidence", response_model=LoadTestEvidenceCaptureResponse
)
async def capture_load_test_evidence(
    payload: LoadTestEvidencePayload,
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> LoadTestEvidenceCaptureResponse:
    """
    Persist a load-test evidence snapshot into the tenant audit log.

    Intended for operator-driven performance sign-off (procurement evidence).
    """
    from uuid import uuid4

    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    run_id = str(uuid4())
    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.PERFORMANCE_LOAD_TEST_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="load_test",
        resource_id=str(payload.profile or "custom"),
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "load_test": payload.model_dump(),
        },
        success=True,
        request_method="POST",
        request_path="/api/v1/audit/performance/load-test/evidence",
    )
    await db.commit()

    return LoadTestEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        load_test=payload,
    )


@router.get(
    "/performance/load-test/evidence", response_model=LoadTestEvidenceListResponse
)
async def list_load_test_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> LoadTestEvidenceListResponse:
    """
    List persisted load-test evidence snapshots for this tenant (latest first).
    """
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(
            AuditLog.event_type == AuditEventType.PERFORMANCE_LOAD_TEST_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[LoadTestEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("load_test")
        if not isinstance(raw, dict):
            continue
        try:
            load_test = LoadTestEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "load_test_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            LoadTestEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                load_test=load_test,
            )
        )

    return LoadTestEvidenceListResponse(total=len(items), items=items)


@router.post(
    "/performance/ingestion/persistence/evidence",
    response_model=IngestionPersistenceEvidenceCaptureResponse,
)
async def capture_ingestion_persistence_evidence(
    payload: IngestionPersistenceEvidencePayload,
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> IngestionPersistenceEvidenceCaptureResponse:
    """
    Persist ingestion persistence benchmark evidence into the tenant audit log.

    Intended for operator-driven performance sign-off (10x ingestion write-path proof).
    """
    from uuid import uuid4

    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    run_id = str(uuid4())
    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.PERFORMANCE_INGESTION_PERSISTENCE_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="ingestion_persistence",
        resource_id=str(payload.provider or "unknown"),
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "benchmark": payload.model_dump(),
        },
        success=bool(payload.meets_targets)
        if payload.meets_targets is not None
        else True,
        request_method="POST",
        request_path="/api/v1/audit/performance/ingestion/persistence/evidence",
    )
    await db.commit()

    return IngestionPersistenceEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        benchmark=payload,
    )


@router.get(
    "/performance/ingestion/persistence/evidence",
    response_model=IngestionPersistenceEvidenceListResponse,
)
async def list_ingestion_persistence_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> IngestionPersistenceEvidenceListResponse:
    """
    List persisted ingestion benchmark evidence snapshots for this tenant (latest first).
    """
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.PERFORMANCE_INGESTION_PERSISTENCE_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[IngestionPersistenceEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("benchmark")
        if not isinstance(raw, dict):
            continue
        try:
            benchmark = IngestionPersistenceEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "ingestion_persistence_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            IngestionPersistenceEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                benchmark=benchmark,
            )
        )

    return IngestionPersistenceEvidenceListResponse(total=len(items), items=items)


@router.post(
    "/performance/ingestion/soak/evidence",
    response_model=IngestionSoakEvidenceCaptureResponse,
)
async def capture_ingestion_soak_evidence(
    payload: IngestionSoakEvidencePayload,
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> IngestionSoakEvidenceCaptureResponse:
    """
    Persist end-to-end ingestion soak evidence into the tenant audit log.

    Intended for operator-driven performance + reliability sign-off ("10x ingestion" readiness).
    """
    from uuid import uuid4

    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    run_id = str(uuid4())
    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    success = (
        bool(payload.meets_targets)
        if payload.meets_targets is not None
        else bool(payload.results.jobs_failed == 0)
    )
    event = await audit.log(
        event_type=AuditEventType.PERFORMANCE_INGESTION_SOAK_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="ingestion_soak",
        resource_id=str(payload.jobs_enqueued),
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "ingestion_soak": payload.model_dump(),
        },
        success=success,
        request_method="POST",
        request_path="/api/v1/audit/performance/ingestion/soak/evidence",
    )
    await db.commit()

    return IngestionSoakEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        ingestion_soak=payload,
    )


@router.get(
    "/performance/ingestion/soak/evidence",
    response_model=IngestionSoakEvidenceListResponse,
)
async def list_ingestion_soak_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> IngestionSoakEvidenceListResponse:
    """List persisted ingestion soak evidence snapshots for this tenant (latest first)."""
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.PERFORMANCE_INGESTION_SOAK_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[IngestionSoakEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("ingestion_soak")
        if not isinstance(raw, dict):
            continue
        try:
            evidence = IngestionSoakEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "ingestion_soak_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            IngestionSoakEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                ingestion_soak=evidence,
            )
        )

    return IngestionSoakEvidenceListResponse(total=len(items), items=items)


@router.post(
    "/identity/idp-smoke/evidence",
    response_model=IdentityIdpSmokeEvidenceCaptureResponse,
)
async def capture_identity_idp_smoke_evidence(
    payload: IdentityIdpSmokeEvidencePayload,
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> IdentityIdpSmokeEvidenceCaptureResponse:
    """
    Persist IdP interoperability smoke-test evidence into the tenant audit log.

    This endpoint is meant to store operator-run evidence (Okta/Entra/etc) without transmitting secrets.
    """
    from uuid import uuid4

    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    run_id = str(uuid4())
    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.IDENTITY_IDP_SMOKE_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="identity_idp_smoke",
        resource_id=str(payload.idp or ""),
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "identity_smoke": payload.model_dump(),
        },
        success=bool(payload.passed),
        request_method="POST",
        request_path="/api/v1/audit/identity/idp-smoke/evidence",
    )
    await db.commit()

    return IdentityIdpSmokeEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        identity_smoke=payload,
    )


@router.get(
    "/identity/idp-smoke/evidence",
    response_model=IdentityIdpSmokeEvidenceListResponse,
)
async def list_identity_idp_smoke_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> IdentityIdpSmokeEvidenceListResponse:
    """List persisted IdP interoperability smoke-test evidence snapshots (latest first)."""
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(AuditLog.event_type == AuditEventType.IDENTITY_IDP_SMOKE_CAPTURED.value)
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[IdentityIdpSmokeEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("identity_smoke")
        if not isinstance(raw, dict):
            continue
        try:
            evidence = IdentityIdpSmokeEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "identity_idp_smoke_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            IdentityIdpSmokeEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                identity_smoke=evidence,
            )
        )

    return IdentityIdpSmokeEvidenceListResponse(total=len(items), items=items)


@router.post(
    "/identity/sso-federation/evidence",
    response_model=SsoFederationValidationEvidenceCaptureResponse,
)
async def capture_sso_federation_validation_evidence(
    payload: SsoFederationValidationEvidencePayload,
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> SsoFederationValidationEvidenceCaptureResponse:
    """
    Persist SSO federation validation evidence into the tenant audit log.

    This stores operator-run configuration validation (no secrets) to support onboarding/procurement sign-off.
    """
    from uuid import uuid4

    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    run_id = str(uuid4())
    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.IDENTITY_SSO_FEDERATION_VALIDATION_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="identity_sso_federation_validation",
        resource_id=str(payload.federation_mode or ""),
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "sso_federation_validation": payload.model_dump(),
        },
        success=bool(payload.passed),
        request_method="POST",
        request_path="/api/v1/audit/identity/sso-federation/evidence",
    )
    await db.commit()

    return SsoFederationValidationEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        sso_federation_validation=payload,
    )


@router.get(
    "/identity/sso-federation/evidence",
    response_model=SsoFederationValidationEvidenceListResponse,
)
async def list_sso_federation_validation_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> SsoFederationValidationEvidenceListResponse:
    """List persisted SSO federation validation evidence snapshots (latest first)."""
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.IDENTITY_SSO_FEDERATION_VALIDATION_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[SsoFederationValidationEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("sso_federation_validation")
        if not isinstance(raw, dict):
            continue
        try:
            evidence = SsoFederationValidationEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "sso_federation_validation_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            SsoFederationValidationEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                sso_federation_validation=evidence,
            )
        )

    return SsoFederationValidationEvidenceListResponse(total=len(items), items=items)


@router.post("/jobs/slo/evidence", response_model=JobSLOEvidenceCaptureResponse)
async def capture_job_slo_evidence(
    payload: JobSLOEvidenceCaptureRequest,
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> JobSLOEvidenceCaptureResponse:
    """
    Persist job reliability + backlog evidence into the tenant audit log.

    This is computed server-side (audit-grade) and intended for availability/reliability sign-off.
    """
    from uuid import uuid4

    from app.modules.governance.domain.jobs.metrics import (
        compute_job_backlog_snapshot,
        compute_job_slo,
    )
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    run_id = str(uuid4())
    computed_slo = await compute_job_slo(
        db,
        tenant_id=tenant_id,
        window_hours=int(payload.window_hours),
        target_success_rate_percent=float(payload.target_success_rate_percent),
    )
    backlog = await compute_job_backlog_snapshot(db, tenant_id=tenant_id)
    computed_payload = {
        **computed_slo,
        "backlog": backlog,
    }
    evidence = JobSLOEvidencePayload.model_validate(computed_payload)

    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.JOBS_SLO_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="jobs",
        resource_id=f"{payload.window_hours}h",
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "job_slo": evidence.model_dump(),
        },
        success=bool(evidence.overall_meets_slo),
        request_method="POST",
        request_path="/api/v1/audit/jobs/slo/evidence",
    )
    await db.commit()

    return JobSLOEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        job_slo=evidence,
    )


@router.get("/jobs/slo/evidence", response_model=JobSLOEvidenceListResponse)
async def list_job_slo_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> JobSLOEvidenceListResponse:
    """List persisted job SLO evidence snapshots for this tenant (latest first)."""
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(AuditLog.event_type == AuditEventType.JOBS_SLO_CAPTURED.value)
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[JobSLOEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("job_slo")
        if not isinstance(raw, dict):
            continue
        try:
            job_slo = JobSLOEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "job_slo_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            JobSLOEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                job_slo=job_slo,
            )
        )

    return JobSLOEvidenceListResponse(total=len(items), items=items)


@router.post(
    "/tenancy/isolation/evidence", response_model=TenantIsolationEvidenceCaptureResponse
)
async def capture_tenant_isolation_evidence(
    payload: TenantIsolationEvidencePayload,
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> TenantIsolationEvidenceCaptureResponse:
    """
    Persist a tenant isolation verification evidence snapshot into the tenant audit log.

    Intended for enterprise procurement/security reviews.
    """
    from uuid import uuid4

    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    run_id = str(uuid4())
    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.TENANCY_ISOLATION_VERIFICATION_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="tenancy",
        resource_id="tenant_isolation_verification",
        details={
            "run_id": run_id,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "tenant_isolation": payload.model_dump(),
        },
        success=bool(payload.passed),
        request_method="POST",
        request_path="/api/v1/audit/tenancy/isolation/evidence",
    )
    await db.commit()

    return TenantIsolationEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        tenant_isolation=payload,
    )


@router.get(
    "/tenancy/isolation/evidence", response_model=TenantIsolationEvidenceListResponse
)
async def list_tenant_isolation_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> TenantIsolationEvidenceListResponse:
    """List persisted tenant isolation evidence snapshots for this tenant (latest first)."""
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.TENANCY_ISOLATION_VERIFICATION_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[TenantIsolationEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("tenant_isolation")
        if not isinstance(raw, dict):
            continue
        try:
            tenant_isolation = TenantIsolationEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "tenant_isolation_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            TenantIsolationEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                tenant_isolation=tenant_isolation,
            )
        )

    return TenantIsolationEvidenceListResponse(total=len(items), items=items)


@router.post(
    "/carbon/assurance/evidence", response_model=CarbonAssuranceEvidenceCaptureResponse
)
async def capture_carbon_assurance_evidence(
    request: CarbonAssuranceEvidenceCaptureRequest,
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
) -> CarbonAssuranceEvidenceCaptureResponse:
    """Capture an auditable carbon methodology + factor snapshot into the tenant audit log."""
    from uuid import uuid4

    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLogger,
    )
    from app.modules.reporting.domain.carbon_factors import CarbonFactorService
    from app.modules.reporting.domain.calculator import carbon_assurance_snapshot

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    run_id = str(uuid4())
    active_factor_set_id: str | None = None
    active_factor_set_status: str | None = None
    factor_payload: dict[str, Any] | None = None
    try:
        factor_service = CarbonFactorService(db)
        active_factor_set = await factor_service.ensure_active()
        factor_payload = await factor_service.get_active_payload()
        active_factor_set_id = str(active_factor_set.id)
        active_factor_set_status = str(active_factor_set.status)
    except Exception as exc:  # noqa: BLE001
        # We still capture evidence using static calculator payload if factor-set
        # infrastructure is temporarily unavailable.
        logger.warning(
            "carbon_assurance_factor_payload_fallback",
            tenant_id=str(tenant_id),
            error=str(exc),
        )

    snapshot = carbon_assurance_snapshot(factor_payload)
    payload = CarbonAssuranceEvidencePayload(
        runner=str(request.runner or "api"),
        notes=str(request.notes) if request.notes else None,
        captured_at=datetime.now(timezone.utc).isoformat(),
        snapshot=snapshot,
        factor_set_id=active_factor_set_id,
        factor_set_status=active_factor_set_status,
    )

    audit = AuditLogger(db=db, tenant_id=tenant_id, correlation_id=run_id)
    event = await audit.log(
        event_type=AuditEventType.CARBON_ASSURANCE_SNAPSHOT_CAPTURED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="carbon",
        resource_id="carbon_assurance_snapshot",
        details={
            "run_id": run_id,
            "captured_at": payload.captured_at,
            "carbon_assurance": payload.model_dump(),
        },
        success=True,
        request_method="POST",
        request_path="/api/v1/audit/carbon/assurance/evidence",
    )
    await db.commit()

    return CarbonAssuranceEvidenceCaptureResponse(
        status="captured",
        event_id=str(event.id),
        run_id=run_id,
        captured_at=event.event_timestamp.isoformat(),
        carbon_assurance=payload,
    )


@router.get(
    "/carbon/assurance/evidence", response_model=CarbonAssuranceEvidenceListResponse
)
async def list_carbon_assurance_evidence(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    limit: int = Query(default=200, ge=1, le=2000),
) -> CarbonAssuranceEvidenceListResponse:
    """List persisted carbon assurance evidence snapshots for this tenant (latest first)."""
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    tenant_id = user.tenant_id
    if tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")

    stmt = (
        select(AuditLog)
        .where(AuditLog.tenant_id == tenant_id)
        .where(
            AuditLog.event_type
            == AuditEventType.CARBON_ASSURANCE_SNAPSHOT_CAPTURED.value
        )
        .order_by(desc(AuditLog.event_timestamp))
        .limit(int(limit))
    )
    rows = (await db.execute(stmt)).scalars().all()

    items: list[CarbonAssuranceEvidenceItem] = []
    for row in rows:
        details = row.details or {}
        raw = details.get("carbon_assurance")
        if not isinstance(raw, dict):
            continue
        try:
            carbon_assurance = CarbonAssuranceEvidencePayload.model_validate(raw)
        except Exception:
            logger.warning(
                "carbon_assurance_evidence_invalid_payload",
                event_id=str(row.id),
                tenant_id=str(tenant_id),
            )
            continue

        items.append(
            CarbonAssuranceEvidenceItem(
                event_id=str(row.id),
                run_id=row.correlation_id,
                captured_at=row.event_timestamp.isoformat(),
                actor_id=str(row.actor_id) if row.actor_id else None,
                actor_email=row.actor_email,
                success=bool(row.success),
                carbon_assurance=carbon_assurance,
            )
        )

    return CarbonAssuranceEvidenceListResponse(total=len(items), items=items)


