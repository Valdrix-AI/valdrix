from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
import io
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4
import zipfile

from fastapi import HTTPException
import pytest
from starlette.requests import Request

from app.models.enforcement import (
    EnforcementActionStatus,
    EnforcementApprovalStatus,
    EnforcementCreditPoolType,
    EnforcementMode,
    EnforcementSource,
)
from app.models.tenant import UserRole
from app.modules.enforcement.api.v1 import actions as actions_api
from app.modules.enforcement.api.v1 import approvals as approvals_api
from app.modules.enforcement.api.v1 import common as common_api
from app.modules.enforcement.api.v1 import enforcement as enforcement_api
from app.modules.enforcement.api.v1 import exports as exports_api
from app.modules.enforcement.api.v1 import ledger as ledger_api
from app.modules.enforcement.api.v1 import policy_budget_credit as policy_api
from app.modules.enforcement.api.v1 import reservations as reservations_api
from app.modules.enforcement.api.v1.schemas import (
    ActionCancelRequest,
    ActionCompleteRequest,
    ActionCreateRequest,
    ActionFailRequest,
    ActionLeaseRequest,
    ApprovalCreateRequest,
    ApprovalReviewRequest,
    ApprovalTokenConsumeRequest,
    BudgetUpsertRequest,
    CreditCreateRequest,
    GateDecisionResponse,
    GateRequest,
    K8sAdmissionReviewPayload,
    PolicyUpdateRequest,
    ReservationReconcileOverdueRequest,
    ReservationReconcileRequest,
    TerraformPreflightRequest,
)
from app.modules.enforcement.domain.policy_document import PolicyDocument
from app.shared.core.auth import CurrentUser
from app.shared.core.pricing import PricingTier


def _request(method: str = "POST") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "path": "/",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "client": ("127.0.0.1", 54321),
            "server": ("testserver", 80),
        }
    )


def _unwrap(func):  # type: ignore[no-untyped-def]
    return getattr(func, "__wrapped__", func)


def _actor(role: UserRole = UserRole.ADMIN) -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email="enforcement-wrapper@test.local",
        tenant_id=uuid4(),
        role=role,
        tier=PricingTier.PRO,
    )


def _action_row(
    *,
    status: EnforcementActionStatus = EnforcementActionStatus.QUEUED,
) -> SimpleNamespace:
    now = datetime.now(timezone.utc)
    return SimpleNamespace(
        id=uuid4(),
        decision_id=uuid4(),
        approval_request_id=None,
        action_type="terraform.apply.execute",
        target_reference="module.app.aws_instance.test",
        idempotency_key="idem-key-1234",
        request_payload={"provider": "terraform"},
        request_payload_sha256="a" * 64,
        status=status,
        attempt_count=1,
        max_attempts=3,
        retry_backoff_seconds=60,
        lease_ttl_seconds=300,
        next_retry_at=now,
        locked_by_worker_id=None,
        lease_expires_at=None,
        last_error_code=None,
        last_error_message=None,
        result_payload={"ok": True},
        result_payload_sha256="b" * 64,
        started_at=now,
        completed_at=now if status == EnforcementActionStatus.SUCCEEDED else None,
        created_at=now,
        updated_at=now,
    )


class _GaugeStub:
    def __init__(self) -> None:
        self._labels: dict[str, str] = {}
        self.values: list[tuple[dict[str, str], float]] = []

    def labels(self, **labels: str) -> "_GaugeStub":
        self._labels = dict(labels)
        return self

    def set(self, value: float) -> None:
        self.values.append((dict(self._labels), float(value)))


class _CounterStub:
    def __init__(self) -> None:
        self._labels: dict[str, str] = {}
        self.calls: list[dict[str, str]] = []

    def labels(self, **labels: str) -> "_CounterStub":
        self._labels = dict(labels)
        return self

    def inc(self, amount: float = 1.0) -> None:
        del amount
        self.calls.append(dict(self._labels))


def _gate_response(
    *,
    decision: str = "ALLOW",
    reason_codes: list[str] | None = None,
    approval_required: bool = False,
) -> GateDecisionResponse:
    return GateDecisionResponse(
        decision=decision,
        reason_codes=list(reason_codes or []),
        decision_id=uuid4(),
        policy_version=3,
        approval_required=approval_required,
        approval_request_id=(uuid4() if approval_required else None),
        approval_token=None,
        approval_token_contract="approval_flow_only",
        ttl_seconds=900,
        request_fingerprint="f" * 64,
        reservation_active=True,
        computed_context={
            "context_version": "v1",
            "month_start": "2026-02-01",
            "month_end": "2026-02-28",
            "data_source_mode": "forecast",
        },
    )


@pytest.mark.asyncio
async def test_actions_endpoint_wrappers_cover_all_return_paths(monkeypatch) -> None:
    action = _action_row()
    leased = _action_row(status=EnforcementActionStatus.RUNNING)
    completed = _action_row(status=EnforcementActionStatus.SUCCEEDED)
    failed = _action_row(status=EnforcementActionStatus.QUEUED)
    failed.last_error_code = "provider_timeout"
    canceled = _action_row(status=EnforcementActionStatus.CANCELLED)
    canceled.last_error_code = "cancelled"
    lease_results = [None, leased]

    class _FakeOrchestrator:
        def __init__(self, _db) -> None:
            del _db

        async def create_action_request(self, **kwargs) -> SimpleNamespace:
            del kwargs
            return action

        async def list_actions(self, **kwargs) -> list[SimpleNamespace]:
            del kwargs
            return [action]

        async def get_action(self, **kwargs) -> SimpleNamespace:
            del kwargs
            return completed

        async def lease_next_action(self, **kwargs) -> SimpleNamespace | None:
            del kwargs
            return lease_results.pop(0)

        async def complete_action(self, **kwargs) -> SimpleNamespace:
            del kwargs
            return completed

        async def fail_action(self, **kwargs) -> SimpleNamespace:
            del kwargs
            return failed

        async def cancel_action(self, **kwargs) -> SimpleNamespace:
            del kwargs
            return canceled

    monkeypatch.setattr(actions_api, "EnforcementActionOrchestrator", _FakeOrchestrator)

    user = _actor(UserRole.ADMIN)
    db = SimpleNamespace()
    create = await _unwrap(actions_api.create_action_request)(
        request=_request(),
        payload=ActionCreateRequest(
            decision_id=action.decision_id,
            action_type=action.action_type,
            target_reference=action.target_reference,
            request_payload={"provider": "terraform"},
            idempotency_key="idem-key-1234",
        ),
        current_user=user,
        db=db,
    )
    assert create.status == EnforcementActionStatus.QUEUED

    listed = await _unwrap(actions_api.list_action_requests)(
        request=_request(method="GET"),
        status=None,
        decision_id=None,
        limit=50,
        current_user=user,
        db=db,
    )
    assert len(listed) == 1

    fetched = await _unwrap(actions_api.get_action_request)(
        request=_request(method="GET"),
        action_id=completed.id,
        current_user=user,
        db=db,
    )
    assert fetched.status == EnforcementActionStatus.SUCCEEDED

    lease_none = await _unwrap(actions_api.lease_action_request)(
        request=_request(),
        payload=ActionLeaseRequest(action_type=action.action_type),
        current_user=user,
        db=db,
    )
    assert lease_none is None

    lease_value = await _unwrap(actions_api.lease_action_request)(
        request=_request(),
        payload=ActionLeaseRequest(action_type=action.action_type),
        current_user=user,
        db=db,
    )
    assert lease_value is not None
    assert lease_value.status == EnforcementActionStatus.RUNNING

    completed_resp = await _unwrap(actions_api.complete_action_request)(
        request=_request(),
        action_id=completed.id,
        payload=ActionCompleteRequest(result_payload={"provider_request_id": "run-1"}),
        current_user=user,
        db=db,
    )
    assert completed_resp.status == EnforcementActionStatus.SUCCEEDED

    failed_resp = await _unwrap(actions_api.fail_action_request)(
        request=_request(),
        action_id=failed.id,
        payload=ActionFailRequest(
            error_code="provider_timeout",
            error_message="provider timeout",
            retryable=True,
        ),
        current_user=user,
        db=db,
    )
    assert failed_resp.last_error_code == "provider_timeout"

    canceled_resp = await _unwrap(actions_api.cancel_action_request)(
        request=_request(),
        action_id=canceled.id,
        payload=ActionCancelRequest(reason="manual intervention"),
        current_user=user,
        db=db,
    )
    assert canceled_resp.status == EnforcementActionStatus.CANCELLED


@pytest.mark.asyncio
async def test_approvals_endpoint_wrappers_cover_queue_and_consume_paths(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    approval_pending = SimpleNamespace(
        id=uuid4(),
        decision_id=uuid4(),
        status=EnforcementApprovalStatus.PENDING,
        routing_rule_id="rule-1",
        approval_token_expires_at=now,
        approval_token_consumed_at=now,
        expires_at=now,
        created_at=now,
    )
    decision = SimpleNamespace(
        id=approval_pending.decision_id,
        source=EnforcementSource.TERRAFORM,
        environment="prod",
        project_id="default",
        action="terraform.apply",
        resource_reference="module.app.aws_instance.test",
        estimated_monthly_delta_usd=Decimal("10"),
        estimated_hourly_delta_usd=Decimal("0.01"),
        reason_codes=["require_approval"],
        request_fingerprint="f" * 64,
        token_expires_at=now,
    )

    class _FakeService:
        def __init__(self, _db) -> None:
            del _db

        async def create_or_get_approval_request(self, **kwargs) -> SimpleNamespace:
            del kwargs
            return approval_pending

        async def list_pending_approvals(self, **kwargs) -> list[tuple[SimpleNamespace, SimpleNamespace]]:
            del kwargs
            return [(approval_pending, decision)]

        async def approve_request(self, **kwargs):
            del kwargs
            approved = SimpleNamespace(
                **{
                    **approval_pending.__dict__,
                    "status": EnforcementApprovalStatus.APPROVED,
                }
            )
            return approved, decision, "t" * 64, now

        async def consume_approval_token(self, **kwargs):
            del kwargs
            return approval_pending, decision

        async def deny_request(self, **kwargs):
            del kwargs
            denied = SimpleNamespace(
                **{
                    **approval_pending.__dict__,
                    "status": EnforcementApprovalStatus.DENIED,
                }
            )
            return denied, decision

    monkeypatch.setattr(approvals_api, "EnforcementService", _FakeService)
    queue_gauge = _GaugeStub()
    monkeypatch.setattr(approvals_api, "ENFORCEMENT_APPROVAL_QUEUE_BACKLOG", queue_gauge)

    # Exercise unknown-role normalization branch in queue metrics.
    user = SimpleNamespace(
        id=uuid4(),
        email="member@test.local",
        tenant_id=uuid4(),
        role="",
        tier=PricingTier.PRO,
    )
    db = SimpleNamespace()

    created = await approvals_api.create_approval_request(
        payload=ApprovalCreateRequest(decision_id=decision.id, notes="create"),
        current_user=user,
        db=db,
    )
    assert created.status == EnforcementApprovalStatus.PENDING.value

    queue = await approvals_api.get_approval_queue(
        limit=25,
        current_user=user,
        db=db,
    )
    assert len(queue) == 1
    assert queue_gauge.values[-1][0]["viewer_role"] == "unknown"

    approved = await approvals_api.approve_approval_request(
        approval_id=approval_pending.id,
        payload=ApprovalReviewRequest(notes="approved"),
        current_user=user,
        db=db,
    )
    assert approved.approval_token == "t" * 64

    consumed = await _unwrap(approvals_api.consume_approval_token)(
        request=_request(),
        payload=ApprovalTokenConsumeRequest(approval_token="x" * 64),
        current_user=user,
        db=db,
    )
    assert consumed.status == "consumed"

    denied = await approvals_api.deny_approval_request(
        approval_id=approval_pending.id,
        payload=ApprovalReviewRequest(notes="deny"),
        current_user=user,
        db=db,
    )
    assert denied.status == EnforcementApprovalStatus.DENIED.value


@pytest.mark.asyncio
async def test_policy_budget_credit_endpoint_wrappers_cover_response_paths(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    policy_document = PolicyDocument()
    policy_row = SimpleNamespace(
        terraform_mode=EnforcementMode.SOFT,
        terraform_mode_prod=EnforcementMode.HARD,
        terraform_mode_nonprod=EnforcementMode.SOFT,
        k8s_admission_mode=EnforcementMode.SOFT,
        k8s_admission_mode_prod=EnforcementMode.HARD,
        k8s_admission_mode_nonprod=EnforcementMode.SOFT,
        require_approval_for_prod=True,
        require_approval_for_nonprod=False,
        enforce_prod_requester_reviewer_separation=True,
        enforce_nonprod_requester_reviewer_separation=False,
        plan_monthly_ceiling_usd=Decimal("100"),
        enterprise_monthly_ceiling_usd=Decimal("1000"),
        auto_approve_below_monthly_usd=Decimal("10"),
        hard_deny_above_monthly_usd=Decimal("500"),
        default_ttl_seconds=900,
        approval_routing_rules=[],
        policy_document_schema_version=policy_document.schema_version,
        policy_document_sha256="c" * 64,
        policy_document=policy_document,
        policy_version=5,
        updated_at=now,
    )
    budget_row = SimpleNamespace(
        id=uuid4(),
        scope_key="default",
        monthly_limit_usd=Decimal("250"),
        active=True,
        created_at=now,
        updated_at=now,
    )
    credit_row = SimpleNamespace(
        id=uuid4(),
        pool_type=EnforcementCreditPoolType.RESERVED,
        scope_key="default",
        total_amount_usd=Decimal("100"),
        remaining_amount_usd=Decimal("75"),
        expires_at=now,
        reason="promo",
        active=True,
        created_at=now,
    )

    class _FakeService:
        def __init__(self, _db) -> None:
            del _db

        async def get_or_create_policy(self, _tenant_id):
            return policy_row

        async def update_policy(self, **kwargs):
            del kwargs
            return policy_row

        async def list_budgets(self, _tenant_id):
            return [budget_row]

        async def upsert_budget(self, **kwargs):
            del kwargs
            return budget_row

        async def list_credits(self, _tenant_id):
            return [credit_row]

        async def create_credit_grant(self, **kwargs):
            del kwargs
            return credit_row

    monkeypatch.setattr(policy_api, "EnforcementService", _FakeService)

    user = _actor(UserRole.ADMIN)
    db = SimpleNamespace(commit=AsyncMock(), refresh=AsyncMock())

    get_policy_resp = await policy_api.get_policy(current_user=user, db=db)
    assert get_policy_resp.policy_document_sha256 == "c" * 64

    upsert_policy_resp = await policy_api.upsert_policy(
        payload=PolicyUpdateRequest(policy_document=policy_document),
        current_user=user,
        db=SimpleNamespace(),
    )
    assert upsert_policy_resp.policy_version == 5

    listed_budgets = await policy_api.list_budgets(current_user=user, db=SimpleNamespace())
    assert listed_budgets[0].scope_key == "default"

    upsert_budget_resp = await policy_api.upsert_budget(
        payload=BudgetUpsertRequest(scope_key="default", monthly_limit_usd=Decimal("250")),
        current_user=user,
        db=SimpleNamespace(),
    )
    assert upsert_budget_resp.monthly_limit_usd == Decimal("250")

    listed_credits = await policy_api.list_credits(current_user=user, db=SimpleNamespace())
    assert listed_credits[0].remaining_amount_usd == Decimal("75")

    create_credit_resp = await policy_api.create_credit(
        payload=CreditCreateRequest(total_amount_usd=Decimal("100")),
        current_user=user,
        db=SimpleNamespace(),
    )
    assert create_credit_resp.pool_type == EnforcementCreditPoolType.RESERVED


@pytest.mark.asyncio
async def test_exports_endpoint_wrappers_cover_limits_and_archive_contract(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    bundle = SimpleNamespace(
        generated_at=now,
        window_start=now,
        window_end=now,
        decision_count_db=2,
        decision_count_exported=2,
        approval_count_db=1,
        approval_count_exported=1,
        decisions_sha256="d" * 64,
        approvals_sha256="e" * 64,
        policy_lineage_sha256="f" * 64,
        policy_lineage=[{"version": 1}],
        computed_context_lineage_sha256="1" * 64,
        computed_context_lineage=[{"decision_id": str(uuid4())}],
        parity_ok=True,
        decisions_csv="decision_id\n1\n",
        approvals_csv="approval_id\n1\n",
    )

    class _SignedManifest:
        content_sha256 = "2" * 64
        signature = "3" * 64
        signature_algorithm = "hmac-sha256"
        signature_key_id = "kid-1"
        canonical_content_json = '{"k":"v"}'

        def to_payload(self) -> dict[str, object]:
            return {
                "content_sha256": self.content_sha256,
                "signature": self.signature,
                "signature_algorithm": self.signature_algorithm,
                "signature_key_id": self.signature_key_id,
            }

    class _FakeService:
        def __init__(self, _db) -> None:
            del _db

        async def build_export_bundle(self, **kwargs):
            del kwargs
            return bundle

        def build_signed_export_manifest(self, **kwargs):
            del kwargs
            return _SignedManifest()

    monkeypatch.setattr(exports_api, "EnforcementService", _FakeService)
    monkeypatch.setattr(
        exports_api,
        "get_settings",
        lambda: SimpleNamespace(
            ENFORCEMENT_EXPORT_MAX_DAYS="invalid",
            ENFORCEMENT_EXPORT_MAX_ROWS="invalid",
        ),
    )
    counter = _CounterStub()
    monkeypatch.setattr(exports_api, "ENFORCEMENT_EXPORT_EVENTS_TOTAL", counter)

    assert exports_api._export_max_days() == 366
    assert exports_api._export_max_rows() == 10000

    monkeypatch.setattr(
        exports_api,
        "get_settings",
        lambda: SimpleNamespace(
            ENFORCEMENT_EXPORT_MAX_DAYS=100_000,
            ENFORCEMENT_EXPORT_MAX_ROWS=100_000,
        ),
    )
    assert exports_api._export_max_days() == 3650
    assert exports_api._export_max_rows() == 50000

    user = _actor(UserRole.ADMIN)
    parity = await exports_api.get_export_parity(
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 1),
        max_rows=10,
        current_user=user,
        db=SimpleNamespace(),
    )
    assert parity.parity_ok is True
    assert counter.calls[-1]["artifact"] == "parity"

    archive_response = await exports_api.download_export_archive(
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 1),
        max_rows=10,
        current_user=user,
        db=SimpleNamespace(),
    )
    assert archive_response.media_type == "application/zip"
    assert "attachment; filename=" in archive_response.headers["Content-Disposition"]

    with zipfile.ZipFile(io.BytesIO(archive_response.body), mode="r") as zf:
        names = set(zf.namelist())
        assert {
            "manifest.json",
            "manifest.canonical.json",
            "manifest.sha256",
            "manifest.sig",
            "decisions.csv",
            "approvals.csv",
        }.issubset(names)
        manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest["signature_key_id"] == "kid-1"

    assert counter.calls[-1]["artifact"] == "archive"


@pytest.mark.asyncio
async def test_reservations_and_ledger_endpoint_wrappers_and_common_guard(monkeypatch) -> None:
    now = datetime.now(timezone.utc)
    tenant_id = uuid4()
    user = CurrentUser(
        id=uuid4(),
        email="admin@test.local",
        tenant_id=tenant_id,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    class _FakeService:
        def __init__(self, _db) -> None:
            del _db

        async def list_active_reservations(self, **kwargs):
            del kwargs
            return [
                SimpleNamespace(
                    id=uuid4(),
                    source=EnforcementSource.TERRAFORM,
                    environment="nonprod",
                    project_id="default",
                    action="terraform.apply",
                    resource_reference="module.app.aws_instance.res",
                    reason_codes=["budget_ok"],
                    reserved_allocation_usd=Decimal("3"),
                    reserved_credit_usd=Decimal("2"),
                    created_at=now,
                )
            ]

        async def reconcile_reservation(self, **kwargs):
            del kwargs
            return SimpleNamespace(
                decision=SimpleNamespace(id=uuid4(), reservation_active=False),
                status="reconciled",
                released_reserved_usd=Decimal("5"),
                actual_monthly_delta_usd=Decimal("7"),
                drift_usd=Decimal("2"),
                reconciled_at=now,
            )

        async def reconcile_overdue_reservations(self, **kwargs):
            del kwargs
            return SimpleNamespace(
                released_count=2,
                total_released_usd=Decimal("12"),
                decision_ids=[uuid4(), uuid4()],
                older_than_seconds=3600,
            )

        async def list_reconciliation_exceptions(self, **kwargs):
            del kwargs
            return [
                SimpleNamespace(
                    decision=SimpleNamespace(
                        id=uuid4(),
                        source=EnforcementSource.TERRAFORM,
                        environment="prod",
                        project_id="default",
                        action="terraform.apply",
                        resource_reference="module.db.aws_db_instance.main",
                    ),
                    expected_reserved_usd=Decimal("10"),
                    actual_monthly_delta_usd=Decimal("15"),
                    drift_usd=Decimal("5"),
                    status="overage",
                    reconciled_at=now,
                    notes="needs review",
                    credit_settlement=[{"grant_id": "g1", "applied_usd": "2.0"}],
                )
            ]

        async def list_decision_ledger(self, **kwargs):
            del kwargs
            return [
                SimpleNamespace(
                    entry=SimpleNamespace(
                        id=uuid4(),
                        decision_id=uuid4(),
                        source=EnforcementSource.TERRAFORM,
                        environment="nonprod",
                        project_id="default",
                        action="terraform.apply",
                        resource_reference="module.app.aws_instance.ledger",
                        decision=SimpleNamespace(value="ALLOW"),
                        reason_codes=["within_budget"],
                        policy_version=3,
                        policy_document_schema_version="valdrics.enforcement.policy.v1",
                        policy_document_sha256="9" * 64,
                        request_fingerprint="a" * 64,
                        idempotency_key="idem-ledger",
                        estimated_monthly_delta_usd=Decimal("6"),
                        estimated_hourly_delta_usd=Decimal("0.01"),
                        burn_rate_daily_usd=Decimal("1.2"),
                        forecast_eom_usd=Decimal("40"),
                        risk_class="low",
                        risk_score=12,
                        anomaly_signal=False,
                        reserved_total_usd=Decimal("6"),
                        approval_required=False,
                        approval_request_id=None,
                        approval_status=None,
                        request_payload_sha256="b" * 64,
                        response_payload_sha256="c" * 64,
                        decision_created_at=now,
                        recorded_at=now,
                    )
                )
            ]

    monkeypatch.setattr(reservations_api, "EnforcementService", _FakeService)
    monkeypatch.setattr(ledger_api, "EnforcementService", _FakeService)

    # Cover 403 guard branch in shared helper.
    with pytest.raises(HTTPException):
        common_api.tenant_or_403(SimpleNamespace(tenant_id=None))

    active = await reservations_api.list_active_reservations(
        limit=100,
        current_user=user,
        db=SimpleNamespace(),
    )
    assert len(active) == 1
    assert active[0].reserved_total_usd == Decimal("5")

    reconciled = await reservations_api.reconcile_reservation(
        decision_id=uuid4(),
        request=_request(),
        payload=ReservationReconcileRequest(actual_monthly_delta_usd=Decimal("7")),
        current_user=user,
        db=SimpleNamespace(),
    )
    assert reconciled.status == "reconciled"

    overdue = await reservations_api.reconcile_overdue_reservations(
        payload=ReservationReconcileOverdueRequest(limit=5),
        current_user=user,
        db=SimpleNamespace(),
    )
    assert overdue.released_count == 2

    exceptions = await reservations_api.list_reconciliation_exceptions(
        limit=10,
        current_user=user,
        db=SimpleNamespace(),
    )
    assert exceptions[0].status == "overage"

    ledger = await ledger_api.list_decision_ledger(
        limit=10,
        start_at=None,
        end_at=None,
        current_user=user,
        db=SimpleNamespace(),
    )
    assert ledger[0].decision == "ALLOW"


@pytest.mark.asyncio
async def test_enforcement_endpoint_wrappers_cover_preflight_and_k8s_review_branches(
    monkeypatch,
) -> None:
    user = _actor(UserRole.ADMIN)
    db = SimpleNamespace()

    # Cover simple wrapper forwarding path in gate_k8s_admission (line ~400).
    run_gate_mock = AsyncMock(return_value=_gate_response(decision="ALLOW"))
    monkeypatch.setattr(enforcement_api, "_run_gate", run_gate_mock)
    gate_result = await _unwrap(enforcement_api.gate_k8s_admission)(
        request=_request(),
        payload=GateRequest(
            project_id="default",
            environment="nonprod",
            action="admission.create",
            resource_reference="deploy/default/web",
            estimated_monthly_delta_usd=Decimal("0"),
            estimated_hourly_delta_usd=Decimal("0"),
            metadata={},
        ),
        current_user=user,
        db=db,
    )
    assert gate_result.decision == "ALLOW"
    assert run_gate_mock.await_args.kwargs["source"] == EnforcementSource.K8S_ADMISSION

    # Cover terraform preflight optional metadata branches + continuation binding.
    preflight_gate_mock = AsyncMock(
        return_value=_gate_response(
            decision="REQUIRE_APPROVAL",
            reason_codes=["requires_approval"],
            approval_required=True,
        )
    )
    monkeypatch.setattr(enforcement_api, "_run_gate_input", preflight_gate_mock)
    preflight = await _unwrap(enforcement_api.gate_terraform_preflight)(
        request=_request(),
        payload=TerraformPreflightRequest(
            run_id="run-123",
            stage="pre_apply",
            workspace_id="ws-1",
            workspace_name="prod-core",
            callback_url="https://ci.example.com/callback",
            run_url="https://app.terraform.io/runs/run-123",
            project_id="Finance",
            environment="prod",
            action="terraform.apply",
            resource_reference="module.db.aws_db_instance.main",
            estimated_monthly_delta_usd=Decimal("120"),
            estimated_hourly_delta_usd=Decimal("0.17"),
            metadata={"resource_type": "aws_db_instance"},
        ),
        current_user=user,
        db=db,
    )
    assert preflight.continuation.approval_consume_endpoint == "/api/v1/enforcement/approvals/consume"
    assert preflight.continuation.binding.expected_source == EnforcementSource.TERRAFORM
    assert preflight.continuation.binding.expected_project_id == "finance"
    assert preflight.continuation.binding.expected_environment == "prod"
    preflight_gate_input = preflight_gate_mock.await_args.kwargs["gate_input"]
    assert preflight_gate_input.metadata["terraform_callback_url"] == "https://ci.example.com/callback"
    assert preflight_gate_input.metadata["terraform_run_url"] == "https://app.terraform.io/runs/run-123"
    assert preflight_gate_input.metadata["terraform_workspace_id"] == "ws-1"
    assert preflight_gate_input.metadata["terraform_workspace_name"] == "prod-core"

    # Cover k8s admission review deny + allow shaping branches.
    review_gate_mock = AsyncMock(
        side_effect=[
            _gate_response(decision="DENY", reason_codes=["budget_exceeded"]),
            _gate_response(decision="ALLOW_WITH_CREDITS", reason_codes=["credit_pool_applied"]),
        ]
    )
    monkeypatch.setattr(enforcement_api, "_run_gate_input", review_gate_mock)

    review_payload = K8sAdmissionReviewPayload.model_validate(
        {
            "apiVersion": "admission.k8s.io/v1",
            "kind": "AdmissionReview",
            "request": {
                "uid": "uid-1",
                "kind": {"group": "apps", "version": "v1", "kind": "Deployment"},
                "resource": {
                    "group": "apps",
                    "version": "v1",
                    "resource": "deployments",
                },
                "operation": "CREATE",
                "namespace": "payments",
                "userInfo": {"username": "platform-bot"},
                "object": {
                    "metadata": {
                        "name": "web",
                        "labels": {"valdrics.io/project-id": "billing"},
                        "annotations": {
                            "valdrics.io/environment": "prod",
                            "valdrics.io/estimated-monthly-delta-usd": "25",
                            "valdrics.io/estimated-hourly-delta-usd": "0.03",
                        },
                    }
                },
                "dryRun": False,
            },
        }
    )

    deny_review = await _unwrap(enforcement_api.gate_k8s_admission_review)(
        request=_request(),
        payload=review_payload,
        current_user=user,
        db=db,
    )
    assert deny_review.response.allowed is False
    assert deny_review.response.status is not None
    assert deny_review.response.status.code == 403
    assert "budget_exceeded" in str(deny_review.response.status.message)
    assert deny_review.response.warnings == ["valdrics:budget_exceeded"]
    assert deny_review.response.audit_annotations["valdrics.io/decision"] == "DENY"

    allow_review = await _unwrap(enforcement_api.gate_k8s_admission_review)(
        request=_request(),
        payload=review_payload,
        current_user=user,
        db=db,
    )
    assert allow_review.response.allowed is True
    assert allow_review.response.status is None
    assert allow_review.response.audit_annotations["valdrics.io/decision"] == "ALLOW_WITH_CREDITS"
