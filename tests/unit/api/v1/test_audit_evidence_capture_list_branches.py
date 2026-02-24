import io
import json
import zipfile
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.governance.api.v1 import audit as audit_api
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.pricing import PricingTier


class _ScalarOneResult:
    def __init__(self, value: object) -> None:
        self._value = value

    def scalar_one_or_none(self) -> object:
        return self._value


class _ScalarsResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> "_ScalarsResult":
        return self

    def all(self) -> list[object]:
        return self._rows


class _RowsResult:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self._rows


class _RecordingAuditLogger:
    calls: list[dict[str, object]] = []

    def __init__(self, db: object, tenant_id: object, correlation_id: str) -> None:
        _ = (db, tenant_id, correlation_id)

    async def log(self, **kwargs: object) -> object:
        _RecordingAuditLogger.calls.append(kwargs)
        return SimpleNamespace(
            id=uuid4(),
            event_timestamp=datetime.now(timezone.utc),
        )


def _admin_user(tenant_id: object | None) -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email="admin-audit-branches@example.com",
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )


def _owner_user(tenant_id: object) -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email="owner-audit-branches@example.com",
        tenant_id=tenant_id,
        role=UserRole.OWNER,
        tier=PricingTier.ENTERPRISE,
    )


def _audit_row(*, details: dict[str, object]) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        event_type="integration_test.slack",
        event_timestamp=now,
        actor_id=uuid4(),
        actor_email="ops@example.com",
        resource_type="integration",
        resource_id="resource-123",
        correlation_id=str(uuid4()),
        success=True,
        error_message=None,
        details=details,
    )


def _load_test_payload(meets_targets: bool | None = None) -> audit_api.LoadTestEvidencePayload:
    return audit_api.LoadTestEvidencePayload(
        profile="smoke",
        target_url="https://api.example.com",
        endpoints=["/health"],
        duration_seconds=30,
        concurrent_users=10,
        ramp_up_seconds=3,
        request_timeout=2.0,
        results=audit_api.LoadTestEvidenceResults(
            total_requests=120,
            successful_requests=119,
            failed_requests=1,
            throughput_rps=4.0,
            avg_response_time=100.0,
            median_response_time=90.0,
            p95_response_time=180.0,
            p99_response_time=250.0,
            min_response_time=30.0,
            max_response_time=300.0,
            errors_sample=["timeout"],
        ),
        meets_targets=meets_targets,
    )


def _ingestion_persistence_payload(
    meets_targets: bool | None,
) -> audit_api.IngestionPersistenceEvidencePayload:
    return audit_api.IngestionPersistenceEvidencePayload(
        records_requested=100,
        records_saved=95,
        duration_seconds=2.5,
        records_per_second=38.0,
        meets_targets=meets_targets,
    )


def _ingestion_soak_payload(
    meets_targets: bool | None,
    *,
    jobs_failed: int,
) -> audit_api.IngestionSoakEvidencePayload:
    jobs_total = 5
    jobs_succeeded = max(0, jobs_total - jobs_failed)
    success_rate = float(jobs_succeeded / jobs_total * 100.0)
    return audit_api.IngestionSoakEvidencePayload(
        jobs_enqueued=jobs_total,
        results=audit_api.IngestionSoakEvidenceResults(
            jobs_total=jobs_total,
            jobs_succeeded=jobs_succeeded,
            jobs_failed=jobs_failed,
            success_rate_percent=success_rate,
        ),
        meets_targets=meets_targets,
    )


def _identity_smoke_payload(passed: bool) -> audit_api.IdentityIdpSmokeEvidencePayload:
    return audit_api.IdentityIdpSmokeEvidencePayload(
        passed=passed,
        checks=[audit_api.IdentityIdpSmokeEvidenceCheck(name="ping", passed=passed)],
    )


def _sso_validation_payload(
    passed: bool,
) -> audit_api.SsoFederationValidationEvidencePayload:
    return audit_api.SsoFederationValidationEvidencePayload(
        passed=passed,
        federation_mode="provider_id",
        checks=[audit_api.IdentityIdpSmokeEvidenceCheck(name="cfg", passed=passed)],
    )


def _tenant_isolation_payload(passed: bool) -> audit_api.TenantIsolationEvidencePayload:
    return audit_api.TenantIsolationEvidencePayload(
        passed=passed,
        checks=["tenant filter", "row-level check"],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "func",
    [
        audit_api.list_load_test_evidence,
        audit_api.list_partitioning_evidence,
        audit_api.list_ingestion_persistence_evidence,
        audit_api.list_ingestion_soak_evidence,
        audit_api.list_identity_idp_smoke_evidence,
        audit_api.list_sso_federation_validation_evidence,
        audit_api.list_job_slo_evidence,
        audit_api.list_tenant_isolation_evidence,
        audit_api.list_carbon_assurance_evidence,
    ],
)
async def test_list_evidence_requires_tenant_context(func) -> None:
    with pytest.raises(HTTPException) as exc:
        await func(_admin_user(None), AsyncMock(), limit=50)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("func", "payload_key", "valid_payload", "item_attr"),
    [
        (
            audit_api.list_load_test_evidence,
            "load_test",
            _load_test_payload().model_dump(),
            "load_test",
        ),
        (
            audit_api.list_partitioning_evidence,
            "partitioning",
            {
                "dialect": "sqlite",
                "partitioning_supported": False,
                "tables": [],
            },
            "partitioning",
        ),
        (
            audit_api.list_ingestion_persistence_evidence,
            "benchmark",
            _ingestion_persistence_payload(None).model_dump(),
            "benchmark",
        ),
        (
            audit_api.list_ingestion_soak_evidence,
            "ingestion_soak",
            _ingestion_soak_payload(None, jobs_failed=0).model_dump(),
            "ingestion_soak",
        ),
        (
            audit_api.list_identity_idp_smoke_evidence,
            "identity_smoke",
            _identity_smoke_payload(True).model_dump(),
            "identity_smoke",
        ),
        (
            audit_api.list_sso_federation_validation_evidence,
            "sso_federation_validation",
            _sso_validation_payload(True).model_dump(),
            "sso_federation_validation",
        ),
        (
            audit_api.list_job_slo_evidence,
            "job_slo",
            {
                "window_hours": 24,
                "target_success_rate_percent": 95.0,
                "overall_meets_slo": True,
                "metrics": [
                    {
                        "job_type": "ingestion",
                        "window_hours": 24,
                        "target_success_rate_percent": 95.0,
                        "total_jobs": 10,
                        "successful_jobs": 10,
                        "failed_jobs": 0,
                        "success_rate_percent": 100.0,
                        "meets_slo": True,
                    }
                ],
                "backlog": {
                    "captured_at": "2026-01-01T00:00:00+00:00",
                    "pending": 0,
                    "running": 0,
                    "completed": 10,
                    "failed": 0,
                    "dead_letter": 0,
                },
            },
            "job_slo",
        ),
        (
            audit_api.list_tenant_isolation_evidence,
            "tenant_isolation",
            _tenant_isolation_payload(True).model_dump(),
            "tenant_isolation",
        ),
        (
            audit_api.list_carbon_assurance_evidence,
            "carbon_assurance",
            {
                "runner": "api",
                "captured_at": "2026-01-01T00:00:00+00:00",
                "snapshot": {"method": "ghg-protocol"},
            },
            "carbon_assurance",
        ),
    ],
)
async def test_list_evidence_skips_invalid_and_returns_valid_payload(
    func,
    payload_key: str,
    valid_payload: dict[str, object],
    item_attr: str,
) -> None:
    rows = [
        _audit_row(details={payload_key: "not-a-dict"}),
        _audit_row(details={payload_key: {}}),
        _audit_row(details={payload_key: valid_payload}),
    ]
    mock_db = AsyncMock()
    mock_db.execute.return_value = _ScalarsResult(rows)

    response = await func(_admin_user(uuid4()), mock_db, limit=200)

    assert response.total == 1
    assert len(response.items) == 1
    assert getattr(response.items[0], item_attr) is not None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("func", "payload"),
    [
        (audit_api.capture_load_test_evidence, _load_test_payload()),
        (
            audit_api.capture_ingestion_persistence_evidence,
            _ingestion_persistence_payload(None),
        ),
        (
            audit_api.capture_ingestion_soak_evidence,
            _ingestion_soak_payload(None, jobs_failed=0),
        ),
        (audit_api.capture_identity_idp_smoke_evidence, _identity_smoke_payload(True)),
        (
            audit_api.capture_sso_federation_validation_evidence,
            _sso_validation_payload(True),
        ),
        (
            audit_api.capture_job_slo_evidence,
            audit_api.JobSLOEvidenceCaptureRequest(),
        ),
        (
            audit_api.capture_tenant_isolation_evidence,
            _tenant_isolation_payload(True),
        ),
        (
            audit_api.capture_carbon_assurance_evidence,
            audit_api.CarbonAssuranceEvidenceCaptureRequest(),
        ),
    ],
)
async def test_capture_evidence_requires_tenant_context(func, payload) -> None:
    with pytest.raises(HTTPException) as exc:
        await func(payload, _admin_user(None), AsyncMock())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_capture_partitioning_requires_tenant_context() -> None:
    with pytest.raises(HTTPException) as exc:
        await audit_api.capture_partitioning_evidence(_admin_user(None), AsyncMock())
    assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("func", "payload", "expected_success", "response_attr"),
    [
        (
            audit_api.capture_load_test_evidence,
            _load_test_payload(True),
            True,
            "load_test",
        ),
        (
            audit_api.capture_ingestion_persistence_evidence,
            _ingestion_persistence_payload(False),
            False,
            "benchmark",
        ),
        (
            audit_api.capture_ingestion_persistence_evidence,
            _ingestion_persistence_payload(None),
            True,
            "benchmark",
        ),
        (
            audit_api.capture_ingestion_soak_evidence,
            _ingestion_soak_payload(None, jobs_failed=1),
            False,
            "ingestion_soak",
        ),
        (
            audit_api.capture_ingestion_soak_evidence,
            _ingestion_soak_payload(True, jobs_failed=1),
            True,
            "ingestion_soak",
        ),
        (
            audit_api.capture_identity_idp_smoke_evidence,
            _identity_smoke_payload(False),
            False,
            "identity_smoke",
        ),
        (
            audit_api.capture_sso_federation_validation_evidence,
            _sso_validation_payload(True),
            True,
            "sso_federation_validation",
        ),
        (
            audit_api.capture_tenant_isolation_evidence,
            _tenant_isolation_payload(False),
            False,
            "tenant_isolation",
        ),
    ],
)
async def test_capture_evidence_logs_expected_success_signal(
    func,
    payload,
    expected_success: bool,
    response_attr: str,
    monkeypatch,
) -> None:
    from app.modules.governance.domain.security import audit_log as audit_log_module

    _RecordingAuditLogger.calls.clear()
    monkeypatch.setattr(audit_log_module, "AuditLogger", _RecordingAuditLogger)

    mock_db = AsyncMock()
    response = await func(payload, _admin_user(uuid4()), mock_db)

    assert response.status == "captured"
    assert getattr(response, response_attr) is not None
    assert _RecordingAuditLogger.calls[-1]["success"] is expected_success
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_capture_partitioning_uses_computed_payload(monkeypatch) -> None:
    from app.modules.governance.domain.security import audit_log as audit_log_module

    _RecordingAuditLogger.calls.clear()
    monkeypatch.setattr(audit_log_module, "AuditLogger", _RecordingAuditLogger)
    monkeypatch.setattr(
        audit_api,
        "_compute_partitioning_evidence",
        AsyncMock(
            return_value=audit_api.PartitioningEvidencePayload(
                dialect="sqlite",
                partitioning_supported=False,
                tables=[],
            )
        ),
    )

    mock_db = AsyncMock()
    response = await audit_api.capture_partitioning_evidence(
        _admin_user(uuid4()),
        mock_db,
    )

    assert response.status == "captured"
    assert response.partitioning.partitioning_supported is False
    assert _RecordingAuditLogger.calls[-1]["success"] is True
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_capture_job_slo_computes_metrics_and_logs(monkeypatch) -> None:
    from app.modules.governance.domain.jobs import metrics as metrics_module
    from app.modules.governance.domain.security import audit_log as audit_log_module

    _RecordingAuditLogger.calls.clear()
    monkeypatch.setattr(audit_log_module, "AuditLogger", _RecordingAuditLogger)
    monkeypatch.setattr(
        metrics_module,
        "compute_job_slo",
        AsyncMock(
            return_value={
                "window_hours": 24,
                "target_success_rate_percent": 95.0,
                "overall_meets_slo": True,
                "metrics": [
                    {
                        "job_type": "ingestion",
                        "window_hours": 24,
                        "target_success_rate_percent": 95.0,
                        "total_jobs": 50,
                        "successful_jobs": 50,
                        "failed_jobs": 0,
                        "success_rate_percent": 100.0,
                        "meets_slo": True,
                    }
                ],
            }
        ),
    )
    monkeypatch.setattr(
        metrics_module,
        "compute_job_backlog_snapshot",
        AsyncMock(
            return_value={
                "captured_at": "2026-01-01T00:00:00+00:00",
                "pending": 0,
                "running": 0,
                "completed": 50,
                "failed": 0,
                "dead_letter": 0,
            }
        ),
    )

    mock_db = AsyncMock()
    response = await audit_api.capture_job_slo_evidence(
        audit_api.JobSLOEvidenceCaptureRequest(window_hours=24),
        _admin_user(uuid4()),
        mock_db,
    )

    assert response.status == "captured"
    assert response.job_slo.overall_meets_slo is True
    assert _RecordingAuditLogger.calls[-1]["success"] is True
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_capture_carbon_assurance_uses_active_factor_payload(monkeypatch) -> None:
    from app.modules.governance.domain.security import audit_log as audit_log_module
    from app.modules.reporting.domain import calculator as calculator_module
    from app.modules.reporting.domain import carbon_factors as carbon_factor_module

    class _FactorService:
        def __init__(self, _db: object) -> None:
            pass

        async def ensure_active(self) -> object:
            return SimpleNamespace(id=uuid4(), status="active")

        async def get_active_payload(self) -> dict[str, object]:
            return {"source": "epa"}

    _RecordingAuditLogger.calls.clear()
    monkeypatch.setattr(audit_log_module, "AuditLogger", _RecordingAuditLogger)
    monkeypatch.setattr(carbon_factor_module, "CarbonFactorService", _FactorService)
    monkeypatch.setattr(
        calculator_module,
        "carbon_assurance_snapshot",
        lambda payload: {"payload_present": bool(payload)},
    )

    mock_db = AsyncMock()
    response = await audit_api.capture_carbon_assurance_evidence(
        audit_api.CarbonAssuranceEvidenceCaptureRequest(
            runner="api",
            notes="capture",
        ),
        _admin_user(uuid4()),
        mock_db,
    )

    assert response.status == "captured"
    assert response.carbon_assurance.factor_set_status == "active"
    assert response.carbon_assurance.snapshot["payload_present"] is True
    assert _RecordingAuditLogger.calls[-1]["success"] is True
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_capture_carbon_assurance_falls_back_when_factor_service_fails(
    monkeypatch,
) -> None:
    from app.modules.governance.domain.security import audit_log as audit_log_module
    from app.modules.reporting.domain import calculator as calculator_module
    from app.modules.reporting.domain import carbon_factors as carbon_factor_module

    class _BrokenFactorService:
        def __init__(self, _db: object) -> None:
            pass

        async def ensure_active(self) -> object:
            raise RuntimeError("factor service unavailable")

        async def get_active_payload(self) -> dict[str, object]:
            return {}

    _RecordingAuditLogger.calls.clear()
    monkeypatch.setattr(audit_log_module, "AuditLogger", _RecordingAuditLogger)
    monkeypatch.setattr(
        carbon_factor_module,
        "CarbonFactorService",
        _BrokenFactorService,
    )
    monkeypatch.setattr(
        calculator_module,
        "carbon_assurance_snapshot",
        lambda payload: {"fallback": payload is None},
    )

    mock_db = AsyncMock()
    response = await audit_api.capture_carbon_assurance_evidence(
        audit_api.CarbonAssuranceEvidenceCaptureRequest(runner="api"),
        _admin_user(uuid4()),
        mock_db,
    )

    assert response.status == "captured"
    assert response.carbon_assurance.factor_set_id is None
    assert response.carbon_assurance.factor_set_status is None
    assert response.carbon_assurance.snapshot["fallback"] is True
    assert _RecordingAuditLogger.calls[-1]["success"] is True
    mock_db.commit.assert_awaited()


@pytest.mark.asyncio
async def test_export_compliance_pack_optional_exports_success_paths(monkeypatch) -> None:
    from app.modules.governance.domain.security import audit_log as audit_log_module
    from app.modules.reporting.domain import focus_export as focus_export_module
    from app.modules.reporting.domain import reconciliation as reconciliation_module
    from app.modules.reporting.domain import savings_proof as savings_proof_module

    class _Dumpable:
        def __init__(self, payload: dict[str, object]) -> None:
            self._payload = payload

        def model_dump(self) -> dict[str, object]:
            return self._payload

    class _FocusExportService:
        def __init__(self, _db: object) -> None:
            pass

        async def export_rows(self, **_kwargs: object):
            yield {"BilledCost": 1.23, "ProviderName": "aws"}
            yield {"BilledCost": 2.34, "ProviderName": "aws"}

    class _SavingsProofService:
        def __init__(self, _db: object) -> None:
            pass

        async def generate(self, **_kwargs: object) -> _Dumpable:
            return _Dumpable({"summary": {"total": 2}})

        @staticmethod
        def render_csv(_payload: object) -> str:
            return "metric,value\ntotal,2\n"

        async def drilldown(self, **_kwargs: object) -> _Dumpable:
            return _Dumpable({"rows": [{"key": "resize", "value": 1}]})

        @staticmethod
        def render_drilldown_csv(_payload: object) -> str:
            return "key,value\nresize,1\n"

    class _CloseService:
        def __init__(self, _db: object) -> None:
            pass

        async def generate_close_package(self, **_kwargs: object) -> dict[str, object]:
            return {
                "csv": "field,value\nstatus,ok\n",
                "summary": {"status": "ok"},
            }

    tenant_id = uuid4()
    owner = _owner_user(tenant_id)

    now = datetime.now(timezone.utc)
    factor_set = SimpleNamespace(
        id=uuid4(),
        status="active",
        is_active=True,
        factor_source="epa",
        factor_version="2026.01",
        factor_timestamp=now,
        methodology_version="ghg-v1",
        factors_checksum_sha256="abc123",
        created_at=now,
        activated_at=now,
        deactivated_at=None,
        created_by_user_id=None,
        payload={"scope": "all"},
    )
    factor_update = SimpleNamespace(
        id=uuid4(),
        recorded_at=now,
        action="activated",
        message="Activated factor set",
        old_factor_set_id=None,
        new_factor_set_id=factor_set.id,
        old_checksum_sha256=None,
        new_checksum_sha256="abc123",
        details={"reason": "scheduled refresh"},
        actor_user_id=None,
    )
    realized_event = SimpleNamespace(
        remediation_request_id=uuid4(),
        provider="aws",
        account_id="123456789012",
        resource_id="i-abc",
        region="us-east-1",
        method="terminate",
        baseline_start_date=date(2025, 12, 1),
        baseline_end_date=date(2025, 12, 15),
        measurement_start_date=date(2025, 12, 16),
        measurement_end_date=date(2025, 12, 31),
        baseline_avg_daily_cost_usd=12.0,
        measurement_avg_daily_cost_usd=8.0,
        realized_monthly_savings_usd=120.0,
        confidence_score=0.98,
        computed_at=now,
    )

    execute_results: list[object] = [
        _ScalarOneResult(None),
        _ScalarOneResult(None),
        _ScalarOneResult(
            SimpleNamespace(
                sso_enabled=True,
                allowed_email_domains=["example.com"],
                scim_enabled=True,
                scim_bearer_token="secret",
                scim_last_rotated_at=now,
                scim_group_mappings=[{"group": "ops", "role": "admin"}],
            )
        ),
        _ScalarsResult(
            [
                _audit_row(
                    details={"channel": "slack", "status_code": 200, "result_message": "ok"}
                )
            ]
        ),
        _ScalarsResult(
            [_audit_row(details={"thresholds": {}, "acceptance_kpis": {"passed": True}})]
        ),
        _ScalarsResult(
            [_audit_row(details={"thresholds": {}, "leadership_kpis": {"passed": True}})]
        ),
        _ScalarsResult(
            [_audit_row(details={"thresholds": {}, "quarterly_report": {"status": "ok"}})]
        ),
        _ScalarsResult([_audit_row(details={"identity_smoke": _identity_smoke_payload(True).model_dump()})]),
        _ScalarsResult(
            [
                _audit_row(
                    details={
                        "sso_federation_validation": _sso_validation_payload(True).model_dump()
                    }
                )
            ]
        ),
        _ScalarsResult([_audit_row(details={"load_test": _load_test_payload().model_dump()})]),
        _ScalarsResult(
            [
                _audit_row(
                    details={"benchmark": _ingestion_persistence_payload(True).model_dump()}
                )
            ]
        ),
        _ScalarsResult(
            [_audit_row(details={"ingestion_soak": _ingestion_soak_payload(True, jobs_failed=0).model_dump()})]
        ),
        _ScalarsResult(
            [
                _audit_row(
                    details={
                        "partitioning": {
                            "dialect": "postgresql",
                            "partitioning_supported": True,
                            "tables": [],
                        }
                    }
                )
            ]
        ),
        _ScalarsResult(
            [
                _audit_row(
                    details={
                        "job_slo": {
                            "window_hours": 24,
                            "target_success_rate_percent": 95.0,
                            "overall_meets_slo": True,
                            "metrics": [],
                            "backlog": {
                                "captured_at": now.isoformat(),
                                "pending": 0,
                                "running": 0,
                                "completed": 1,
                                "failed": 0,
                                "dead_letter": 0,
                            },
                        }
                    }
                )
            ]
        ),
        _ScalarsResult(
            [_audit_row(details={"tenant_isolation": _tenant_isolation_payload(True).model_dump()})]
        ),
        _ScalarsResult(
            [
                _audit_row(
                    details={
                        "carbon_assurance": {
                            "runner": "api",
                            "captured_at": now.isoformat(),
                            "snapshot": {"method": "ghg"},
                        }
                    }
                )
            ]
        ),
        _ScalarsResult([factor_set]),
        _ScalarsResult([factor_update]),
        _ScalarsResult([_audit_row(details={"audit": True})]),
        _RowsResult([(realized_event, now)]),
    ]

    async def _execute(*_args: object, **_kwargs: object) -> object:
        if execute_results:
            return execute_results.pop(0)
        return _ScalarsResult([])

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(side_effect=_execute)
    mock_db.commit = AsyncMock()
    mock_db.rollback = AsyncMock()

    _RecordingAuditLogger.calls.clear()
    monkeypatch.setattr(audit_log_module, "AuditLogger", _RecordingAuditLogger)
    monkeypatch.setattr(
        focus_export_module,
        "FocusV13ExportService",
        _FocusExportService,
    )
    monkeypatch.setattr(
        savings_proof_module,
        "SavingsProofService",
        _SavingsProofService,
    )
    monkeypatch.setattr(
        reconciliation_module,
        "CostReconciliationService",
        _CloseService,
    )

    response = await audit_api.export_compliance_pack(
        user=owner,
        db=mock_db,
        start_date=None,
        end_date=None,
        evidence_limit=200,
        include_focus_export=True,
        focus_provider="aws",
        focus_include_preliminary=False,
        focus_max_rows=50000,
        focus_start_date=None,
        focus_end_date=None,
        include_savings_proof=True,
        savings_provider="aws",
        savings_start_date=None,
        savings_end_date=None,
        include_realized_savings=True,
        realized_provider="aws",
        realized_start_date=None,
        realized_end_date=None,
        realized_limit=5000,
        include_close_package=True,
        close_provider="aws",
        close_start_date=None,
        close_end_date=None,
        close_enforce_finalized=True,
        close_max_restatements=5000,
    )

    archive = zipfile.ZipFile(io.BytesIO(response.body))
    names = set(archive.namelist())

    assert "exports/focus-v1.3-core.csv" in names
    assert "exports/savings-proof.json" in names
    assert "exports/savings-proof-drilldown-strategy-type.csv" in names
    assert "exports/realized-savings.csv" in names
    assert "exports/close-package.json" in names

    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert manifest["focus_export"]["status"] == "ok"
    assert manifest["savings_proof"]["status"] == "ok"
    assert manifest["realized_savings"]["status"] == "ok"
    assert manifest["close_package"]["status"] == "ok"
