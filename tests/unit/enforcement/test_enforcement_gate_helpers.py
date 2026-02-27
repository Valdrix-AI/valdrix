from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.models.enforcement import EnforcementDecisionType, EnforcementSource
from app.models.tenant import UserRole
from app.modules.enforcement.api.v1 import enforcement
from app.modules.enforcement.api.v1.schemas import (
    CloudEventGateRequest,
    GateRequest,
)
from app.modules.enforcement.domain.service import GateEvaluationResult, GateInput
from app.shared.core.auth import CurrentUser


class _CounterStub:
    def __init__(self) -> None:
        self.calls: list[dict[str, str]] = []
        self._labels: dict[str, str] = {}

    def labels(self, **labels: str) -> "_CounterStub":
        self._labels = dict(labels)
        return self

    def inc(self) -> None:
        self.calls.append(dict(self._labels))


class _HistogramStub:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, str], float]] = []
        self._labels: dict[str, str] = {}

    def labels(self, **labels: str) -> "_HistogramStub":
        self._labels = dict(labels)
        return self

    def observe(self, value: float) -> None:
        self.calls.append((dict(self._labels), float(value)))


def _build_result(*, decision: EnforcementDecisionType, reason_codes: list[str]) -> GateEvaluationResult:
    decision_row = SimpleNamespace(
        decision=decision,
        reason_codes=reason_codes,
        id=uuid4(),
        policy_version=3,
        approval_required=False,
        request_fingerprint="f" * 64,
        reservation_active=True,
        response_payload={"computed_context": {"risk_class": "low"}},
    )
    return GateEvaluationResult(
        decision=decision_row,
        approval=None,
        approval_token=None,
        ttl_seconds=900,
    )


def test_enforcement_gate_config_and_metric_helpers(monkeypatch) -> None:
    monkeypatch.setattr(
        enforcement,
        "get_settings",
        lambda: SimpleNamespace(ENFORCEMENT_GATE_TIMEOUT_SECONDS="bad"),
    )
    assert enforcement._gate_timeout_seconds() == 2.0

    monkeypatch.setattr(
        enforcement,
        "get_settings",
        lambda: SimpleNamespace(ENFORCEMENT_GATE_TIMEOUT_SECONDS=0.0001),
    )
    assert enforcement._gate_timeout_seconds() == 0.05

    monkeypatch.setattr(
        enforcement,
        "get_settings",
        lambda: SimpleNamespace(ENFORCEMENT_GATE_TIMEOUT_SECONDS=99),
    )
    assert enforcement._gate_timeout_seconds() == 30.0

    monkeypatch.setattr(
        enforcement,
        "get_settings",
        lambda: SimpleNamespace(
            ENFORCEMENT_GLOBAL_ABUSE_GUARD_ENABLED=False,
            ENFORCEMENT_GLOBAL_GATE_PER_MINUTE_CAP=42,
        ),
    )
    assert enforcement._enforcement_global_gate_limit(SimpleNamespace()) == "1000000/minute"

    monkeypatch.setattr(
        enforcement,
        "get_settings",
        lambda: SimpleNamespace(
            ENFORCEMENT_GLOBAL_ABUSE_GUARD_ENABLED=True,
            ENFORCEMENT_GLOBAL_GATE_PER_MINUTE_CAP="bad",
        ),
    )
    assert enforcement._enforcement_global_gate_limit(SimpleNamespace()) == "1200/minute"

    assert enforcement._metric_reason("") == "unknown"
    assert enforcement._metric_reason("Bad Reason!*") == "bad_reason__"
    assert enforcement._http_detail_mapping("x") == {}
    assert enforcement._http_detail_mapping({"a": 1, "": 2}) == {"a": 1}

    lock_exc = HTTPException(status_code=503, detail={"code": "gate_lock_timeout"})
    assert enforcement._lock_failure_reason_from_http_exception(lock_exc) == "gate_lock_timeout"


def test_enforcement_gate_input_builders_and_parsers() -> None:
    payload = GateRequest(
        project_id=" Proj ",
        environment="nonprod",
        action=" Terraform.Apply ",
        resource_reference=" module.app.aws_instance.x ",
        estimated_monthly_delta_usd=Decimal("1"),
        estimated_hourly_delta_usd=Decimal("0.1"),
        metadata={"a": 1},
        dry_run=True,
    )
    gate_input = enforcement._build_gate_input(payload=payload, idempotency_key="idem-1")
    assert gate_input.project_id == "proj"
    assert gate_input.action == "terraform.apply"
    assert gate_input.resource_reference == "module.app.aws_instance.x"
    assert gate_input.dry_run is True

    assert enforcement._annotation_decimal({}, key="x", default=Decimal("7")) == Decimal("7")
    assert (
        enforcement._annotation_decimal({"k": "2.5"}, key="k", default=Decimal("0"))
        == Decimal("2.5")
    )
    with pytest.raises(HTTPException):
        enforcement._annotation_decimal({"k": "bad"}, key="k", default=Decimal("0"))

    labels, annotations, name, namespace = enforcement._extract_k8s_labels_annotations(
        {"metadata": {"labels": {"a": 1}, "annotations": {"b": 2}, "name": "obj", "namespace": "ns"}}
    )
    assert labels == {"a": "1"}
    assert annotations == {"b": "2"}
    assert name == "obj"
    assert namespace == "ns"


def test_build_cloud_event_gate_input_derivation_and_extensions() -> None:
    payload = CloudEventGateRequest.model_validate(
        {
            "cloud_event": {
                "specversion": "1.0",
                "id": "evt-1",
                "source": "aws.ec2",
                "type": "instance.update",
                "subject": "i-123",
                "data": {"k": "v"},
                "customAttr": "x",
            },
            "project_id": "TeamA",
            "environment": "prod",
            "action": "cloud_event.observe",
            "estimated_monthly_delta_usd": "0",
            "estimated_hourly_delta_usd": "0",
            "metadata": {"origin": "cloud"},
        }
    )
    gate_input = enforcement._build_cloud_event_gate_input(
        payload=payload,
        idempotency_key="cloud-idem-1",
    )
    assert gate_input.project_id == "teama"
    assert gate_input.resource_reference == "i-123"
    assert gate_input.metadata["cloud_event_id"] == "evt-1"
    assert "cloud_event_data_sha256" in gate_input.metadata
    assert gate_input.metadata["cloud_event_extensions"] == {"customAttr": "x"}

    no_reference = CloudEventGateRequest.model_validate(
        {
            "cloud_event": {
                "specversion": "1.0",
                "id": "evt-2",
                "source": "  ",
                "type": "instance.update",
                "subject": "  ",
                "data": None,
            }
        }
    )
    with pytest.raises(HTTPException):
        enforcement._build_cloud_event_gate_input(
            payload=no_reference,
            idempotency_key="cloud-idem-2",
        )


@pytest.mark.asyncio
async def test_run_gate_input_handles_fingerprint_and_failsafe_paths(monkeypatch) -> None:
    current_user = CurrentUser(
        id=uuid4(),
        email="member@valdrix.local",
        tenant_id=uuid4(),
        role=UserRole.MEMBER,
    )
    gate_input = GateInput(
        project_id="default",
        environment="nonprod",
        action="terraform.apply",
        resource_reference="module.app.aws_instance.x",
        estimated_monthly_delta_usd=Decimal("1"),
        estimated_hourly_delta_usd=Decimal("0.1"),
        metadata={},
        idempotency_key="idem-1",
    )

    failure_counter = _CounterStub()
    decision_counter = _CounterStub()
    reason_counter = _CounterStub()
    latency_hist = _HistogramStub()
    monkeypatch.setattr(enforcement, "ENFORCEMENT_GATE_FAILURES_TOTAL", failure_counter)
    monkeypatch.setattr(enforcement, "ENFORCEMENT_GATE_DECISIONS_TOTAL", decision_counter)
    monkeypatch.setattr(enforcement, "ENFORCEMENT_GATE_DECISION_REASONS_TOTAL", reason_counter)
    monkeypatch.setattr(enforcement, "ENFORCEMENT_GATE_LATENCY_SECONDS", latency_hist)
    monkeypatch.setattr(enforcement.time, "perf_counter", lambda: 100.0)

    class _FakeService:
        def __init__(self, _db) -> None:
            self.evaluate_gate = AsyncMock(return_value=_build_result(decision=EnforcementDecisionType.ALLOW, reason_codes=["normal_allow"]))
            self.resolve_fail_safe_gate = AsyncMock(return_value=_build_result(decision=EnforcementDecisionType.REQUIRE_APPROVAL, reason_codes=["failsafe"]))

        def compute_request_fingerprint(self, *, source: EnforcementSource, gate_input: GateInput) -> str:
            del source
            del gate_input
            return "fingerprint-a"

    monkeypatch.setattr(enforcement, "EnforcementService", _FakeService)

    with pytest.raises(HTTPException):
        await enforcement._run_gate_input(
            source=EnforcementSource.TERRAFORM,
            gate_input=gate_input,
            expected_request_fingerprint="fingerprint-b",
            current_user=current_user,
            db=SimpleNamespace(),
        )

    async def _raise_timeout(coro, timeout):  # type: ignore[no-untyped-def]
        del timeout
        coro.close()
        raise TimeoutError

    with patch.object(enforcement.asyncio, "wait_for", side_effect=_raise_timeout):
        timeout_response = await enforcement._run_gate_input(
            source=EnforcementSource.TERRAFORM,
            gate_input=gate_input,
            expected_request_fingerprint=None,
            current_user=current_user,
            db=SimpleNamespace(),
        )
    assert timeout_response.decision == "REQUIRE_APPROVAL"

    lock_exc = HTTPException(
        status_code=503,
        detail={"code": "gate_lock_timeout", "lock_timeout_seconds": 1.0},
    )
    async def _raise_lock(coro, timeout):  # type: ignore[no-untyped-def]
        del timeout
        coro.close()
        raise lock_exc

    with patch.object(enforcement.asyncio, "wait_for", side_effect=_raise_lock):
        lock_response = await enforcement._run_gate_input(
            source=EnforcementSource.K8S_ADMISSION,
            gate_input=gate_input,
            expected_request_fingerprint=None,
            current_user=current_user,
            db=SimpleNamespace(),
        )
    assert lock_response.decision == "REQUIRE_APPROVAL"

    async def _raise_runtime(coro, timeout):  # type: ignore[no-untyped-def]
        del timeout
        coro.close()
        raise RuntimeError("boom")

    with patch.object(enforcement.asyncio, "wait_for", side_effect=_raise_runtime):
        error_response = await enforcement._run_gate_input(
            source=EnforcementSource.CLOUD_EVENT,
            gate_input=gate_input,
            expected_request_fingerprint=None,
            current_user=current_user,
            db=SimpleNamespace(),
        )
    assert error_response.decision == "REQUIRE_APPROVAL"
    assert len(failure_counter.calls) >= 3


@pytest.mark.asyncio
async def test_run_gate_input_non_lock_http_exception_bubbles(monkeypatch) -> None:
    current_user = CurrentUser(
        id=uuid4(),
        email="member@valdrix.local",
        tenant_id=uuid4(),
        role=UserRole.MEMBER,
    )
    gate_input = GateInput(
        project_id="default",
        environment="nonprod",
        action="terraform.apply",
        resource_reference="module.app.aws_instance.y",
        estimated_monthly_delta_usd=Decimal("1"),
        estimated_hourly_delta_usd=Decimal("0.1"),
        metadata={},
        idempotency_key="idem-2",
    )

    class _Service:
        def __init__(self, _db) -> None:
            self.evaluate_gate = AsyncMock(
                return_value=_build_result(
                    decision=EnforcementDecisionType.ALLOW,
                    reason_codes=["normal_allow"],
                )
            )
            self.resolve_fail_safe_gate = AsyncMock()

        def compute_request_fingerprint(self, *, source: EnforcementSource, gate_input: GateInput) -> str:
            del source
            del gate_input
            return "ok"

    monkeypatch.setattr(enforcement, "EnforcementService", _Service)
    non_lock_http = HTTPException(status_code=400, detail={"code": "other"})

    async def _raise_non_lock(coro, timeout):  # type: ignore[no-untyped-def]
        del timeout
        coro.close()
        raise non_lock_http

    with patch.object(enforcement.asyncio, "wait_for", side_effect=_raise_non_lock):
        with pytest.raises(HTTPException) as exc:
            await enforcement._run_gate_input(
                source=EnforcementSource.TERRAFORM,
                gate_input=gate_input,
                expected_request_fingerprint=None,
                current_user=current_user,
                db=SimpleNamespace(),
            )
    assert exc.value.status_code == 400
