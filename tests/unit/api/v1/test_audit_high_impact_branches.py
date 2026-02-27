import io
import json
import zipfile
from datetime import date, datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.governance.api.v1 import audit_partitioning as audit_partitioning_api
from app.modules.governance.api.v1.audit import (
    _compute_partitioning_evidence,
    _rowcount,
    _sanitize_csv_cell,
    export_audit_logs,
    list_load_test_evidence,
)
from app.shared.core.auth import CurrentUser, UserRole, get_current_user
from app.shared.core.pricing import PricingTier


class _ScalarRows:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def scalars(self) -> "_ScalarRows":
        return self

    def all(self) -> list[object]:
        return self._rows


class _Rows:
    def __init__(self, rows: list[tuple[object, ...]]) -> None:
        self._rows = rows

    def all(self) -> list[tuple[object, ...]]:
        return self._rows


def _owner_user(tenant_id: object) -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email="owner-audit@valdrix.io",
        tenant_id=tenant_id,
        role=UserRole.OWNER,
        tier=PricingTier.PRO,
    )


def _admin_user(tenant_id: object | None) -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email="admin-audit@valdrix.io",
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )


def test_sanitize_csv_cell_and_rowcount_branches() -> None:
    assert _sanitize_csv_cell(None) == ""
    assert _sanitize_csv_cell("") == ""
    assert _sanitize_csv_cell("=2+2") == "'=2+2"
    assert _sanitize_csv_cell("@cmd") == "'@cmd"
    assert _sanitize_csv_cell("-5") == "-5"

    assert _rowcount(SimpleNamespace(rowcount=3)) == 3
    assert _rowcount(SimpleNamespace(rowcount=None)) == 0
    assert _rowcount(SimpleNamespace(rowcount="3")) == 0


@pytest.mark.asyncio
async def test_export_audit_logs_escapes_formula_cells() -> None:
    mock_db = AsyncMock()
    log = SimpleNamespace(
        id=uuid4(),
        event_type="=cmd",
        event_timestamp=datetime.now(timezone.utc),
        actor_email="+attacker@example.com",
        resource_type="@resource",
        resource_id="123",
        success=True,
        correlation_id="\ttrace",
    )
    execute_result = MagicMock()
    execute_result.scalars.return_value.all.return_value = [log]
    mock_db.execute.return_value = execute_result

    response = await export_audit_logs(_admin_user(uuid4()), mock_db)

    chunks: list[str] = []
    async for chunk in response.body_iterator:
        chunks.append(chunk if isinstance(chunk, str) else chunk.decode("utf-8"))
    csv_payload = "".join(chunks)
    assert "'=cmd" in csv_payload
    assert "'+attacker@example.com" in csv_payload
    assert "'@resource" in csv_payload
    assert "'\ttrace" in csv_payload


@pytest.mark.asyncio
async def test_list_load_test_evidence_requires_tenant_context() -> None:
    with pytest.raises(HTTPException) as exc:
        await list_load_test_evidence(_admin_user(None), AsyncMock(), limit=10)
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_list_load_test_evidence_skips_invalid_payloads() -> None:
    mock_db = AsyncMock()
    execute_result = MagicMock()
    now = datetime.now(timezone.utc)
    execute_result.scalars.return_value.all.return_value = [
        SimpleNamespace(
            id=uuid4(),
            correlation_id="run-ignored-1",
            event_timestamp=now,
            actor_id=uuid4(),
            actor_email="bad1@example.com",
            success=True,
            details={"load_test": "not-a-dict"},
        ),
        SimpleNamespace(
            id=uuid4(),
            correlation_id="run-ignored-2",
            event_timestamp=now,
            actor_id=uuid4(),
            actor_email="bad2@example.com",
            success=True,
            details={"load_test": {"total_requests": "wrong-shape"}},
        ),
        SimpleNamespace(
            id=uuid4(),
            correlation_id="run-ok",
            event_timestamp=now,
            actor_id=uuid4(),
            actor_email="ok@example.com",
            success=True,
            details={
                "load_test": {
                    "profile": "smoke",
                    "target_url": "https://api.example.com",
                    "endpoints": ["/health"],
                    "duration_seconds": 60,
                    "concurrent_users": 25,
                    "ramp_up_seconds": 5,
                    "request_timeout": 2.0,
                    "results": {
                        "total_requests": 500,
                        "successful_requests": 499,
                        "failed_requests": 1,
                        "throughput_rps": 8.33,
                        "avg_response_time": 120.0,
                        "median_response_time": 100.0,
                        "p95_response_time": 200.0,
                        "p99_response_time": 300.0,
                        "min_response_time": 20.0,
                        "max_response_time": 500.0,
                        "errors_sample": ["timeout"],
                    },
                }
            },
        ),
    ]
    mock_db.execute.return_value = execute_result

    response = await list_load_test_evidence(_admin_user(uuid4()), mock_db, limit=200)
    assert response.total == 1
    assert response.items[0].run_id == "run-ok"
    assert response.items[0].load_test.profile == "smoke"


@pytest.mark.asyncio
async def test_compute_partitioning_evidence_postgres_path(monkeypatch) -> None:
    class _FixedDate(date):
        @classmethod
        def today(cls) -> "_FixedDate":
            return cls(2026, 1, 15)

    monkeypatch.setattr(audit_partitioning_api, "date", _FixedDate)

    mock_db = AsyncMock()
    mock_db.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    mock_db.execute = AsyncMock(
        side_effect=[
            _ScalarRows(["audit_logs", "cost_records"]),
            _Rows([("audit_logs_2026_01",), ("audit_logs_2026_02",)]),
        ]
    )
    mock_db.scalar = AsyncMock(side_effect=["p", "r"])

    payload = await _compute_partitioning_evidence(mock_db)
    assert payload.dialect == "postgresql"
    assert payload.partitioning_supported is True

    by_table = {item.table: item for item in payload.tables}
    assert by_table["audit_logs"].partitioned is True
    assert "audit_logs_2026_03" in by_table["audit_logs"].missing_partitions
    assert "audit_logs_2026_04" in by_table["audit_logs"].missing_partitions

    assert by_table["cost_records"].partitioned is False
    assert by_table["cost_records"].missing_partitions == []


@pytest.mark.asyncio
async def test_compute_partitioning_evidence_handles_catalog_errors() -> None:
    mock_db = AsyncMock()
    mock_db.bind = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    mock_db.execute = AsyncMock(side_effect=Exception("catalog unavailable"))
    mock_db.scalar = AsyncMock()

    payload = await _compute_partitioning_evidence(mock_db)
    assert payload.dialect == "postgresql"
    assert payload.partitioning_supported is True
    assert all(item.exists is False for item in payload.tables)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "needle"),
    [
        ("focus_provider=bad-provider", "unsupported focus_provider"),
        ("savings_provider=bad-provider", "unsupported savings_provider"),
        ("realized_provider=bad-provider", "unsupported realized_provider"),
        ("close_provider=bad-provider", "unsupported close_provider"),
    ],
)
async def test_export_compliance_pack_rejects_unsupported_providers(
    async_client, app, test_tenant, query: str, needle: str
) -> None:
    owner_user = _owner_user(test_tenant.id)
    app.dependency_overrides[get_current_user] = lambda: owner_user
    try:
        response = await async_client.get(f"/api/v1/audit/compliance-pack?{query}")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 400
    assert needle in json.dumps(response.json()).lower()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("query", "needle"),
    [
        (
            "focus_start_date=2026-02-01&focus_end_date=2026-01-01",
            "start_date must be <= end_date",
        ),
        (
            "savings_start_date=2026-02-01&savings_end_date=2026-01-01",
            "savings_start_date must be <= savings_end_date",
        ),
        (
            "realized_start_date=2026-02-01&realized_end_date=2026-01-01",
            "realized_start_date must be <= realized_end_date",
        ),
        (
            "close_start_date=2026-02-01&close_end_date=2026-01-01",
            "close_start_date must be <= close_end_date",
        ),
    ],
)
async def test_export_compliance_pack_rejects_invalid_windows(
    async_client, app, test_tenant, query: str, needle: str
) -> None:
    owner_user = _owner_user(test_tenant.id)
    app.dependency_overrides[get_current_user] = lambda: owner_user
    try:
        response = await async_client.get(f"/api/v1/audit/compliance-pack?{query}")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 400
    assert needle in json.dumps(response.json()).lower()


@pytest.mark.asyncio
async def test_export_compliance_pack_records_error_artifacts_for_failed_exports(
    async_client, app, monkeypatch, test_tenant
) -> None:
    from app.modules.reporting.domain import focus_export as focus_export_module
    from app.modules.reporting.domain import reconciliation as reconciliation_module
    from app.modules.reporting.domain import savings_proof as savings_proof_module
    import app.models.realized_savings as realized_savings_module

    class BrokenFocusExportService:
        def __init__(self, _db: object) -> None:
            pass

        async def export_rows(self, **_kwargs: object):  # pragma: no cover
            raise RuntimeError("focus export failed")
            yield {}

    class BrokenSavingsProofService:
        def __init__(self, _db: object) -> None:
            pass

        async def generate(self, **_kwargs: object) -> object:
            raise RuntimeError("savings proof failed")

        @staticmethod
        def render_csv(_payload: object) -> str:
            return ""

        async def drilldown(self, **_kwargs: object) -> object:
            raise RuntimeError("savings drilldown failed")

        @staticmethod
        def render_drilldown_csv(_payload: object) -> str:
            return ""

    class BrokenCloseService:
        def __init__(self, _db: object) -> None:
            pass

        async def generate_close_package(self, **_kwargs: object) -> dict[str, object]:
            raise RuntimeError("close package failed")

    class BrokenRealizedEvent:
        pass

    monkeypatch.setattr(
        focus_export_module, "FocusV13ExportService", BrokenFocusExportService
    )
    monkeypatch.setattr(
        savings_proof_module, "SavingsProofService", BrokenSavingsProofService
    )
    monkeypatch.setattr(
        reconciliation_module, "CostReconciliationService", BrokenCloseService
    )
    monkeypatch.setattr(
        realized_savings_module, "RealizedSavingsEvent", BrokenRealizedEvent
    )

    owner_user = _owner_user(test_tenant.id)
    app.dependency_overrides[get_current_user] = lambda: owner_user
    try:
        response = await async_client.get(
            "/api/v1/audit/compliance-pack"
            "?include_focus_export=true"
            "&include_savings_proof=true"
            "&include_realized_savings=true"
            "&include_close_package=true"
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = set(archive.namelist())
    assert "exports/focus-v1.3-core.error.json" in names
    assert "exports/savings-proof.error.json" in names
    assert "exports/realized-savings.error.json" in names
    assert "exports/close-package.error.json" in names

    manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
    assert manifest["focus_export"]["status"] == "error"
    assert manifest["savings_proof"]["status"] == "error"
    assert manifest["realized_savings"]["status"] == "error"
    assert manifest["close_package"]["status"] == "error"
