from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.enforcement.api.v1 import approvals as approvals_api
from app.modules.enforcement.api.v1.schemas import (
    ApprovalCreateRequest,
    ApprovalReviewRequest,
    ApprovalTokenConsumeRequest,
)
from app.shared.core.pricing import PricingTier


def _user(*, tenant_id=None, role=None, tier: PricingTier = PricingTier.PRO):
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=tenant_id or uuid4(),
        role=role if role is not None else SimpleNamespace(value="admin"),
        tier=tier,
    )


@pytest.mark.asyncio
async def test_create_approval_request_maps_service_result() -> None:
    payload = ApprovalCreateRequest(decision_id=uuid4(), notes="request approval")
    user = _user()
    now = datetime.now(timezone.utc)
    approval = SimpleNamespace(
        status=SimpleNamespace(value="pending"),
        id=uuid4(),
        decision_id=payload.decision_id,
        routing_rule_id="route-prod",
        approval_token_expires_at=now,
    )
    service = SimpleNamespace(
        create_or_get_approval_request=AsyncMock(return_value=approval)
    )

    with patch.object(approvals_api, "EnforcementService", return_value=service):
        response = await approvals_api.create_approval_request(
            payload=payload,
            current_user=user,
            db=AsyncMock(),
        )

    assert response.status == "pending"
    assert response.approval_id == approval.id
    assert response.decision_id == approval.decision_id
    assert response.routing_rule_id == "route-prod"
    assert response.token_expires_at == now
    service.create_or_get_approval_request.assert_awaited_once_with(
        tenant_id=user.tenant_id,
        actor_id=user.id,
        decision_id=payload.decision_id,
        notes="request approval",
    )


@pytest.mark.asyncio
async def test_get_approval_queue_maps_rows_and_records_unknown_role_metric() -> None:
    now = datetime.now(timezone.utc)
    approval = SimpleNamespace(
        id=uuid4(),
        decision_id=uuid4(),
        status=SimpleNamespace(value="pending"),
        routing_rule_id="route-1",
        expires_at=now,
        created_at=now,
    )
    decision = SimpleNamespace(
        id=approval.decision_id,
        source=SimpleNamespace(value="terraform"),
        environment="prod",
        project_id="project-a",
        action="terraform.apply",
        resource_reference="module.vpc.aws_vpc.main",
        estimated_monthly_delta_usd=Decimal("14.5"),
        reason_codes=None,
    )
    service = SimpleNamespace(
        list_pending_approvals=AsyncMock(return_value=[(approval, decision)])
    )
    metric_calls: list[str] = []
    gauge_calls: list[int] = []

    class _FakeGauge:
        def set(self, value: int) -> None:
            gauge_calls.append(value)

    class _FakeMetric:
        def labels(self, *, viewer_role: str) -> _FakeGauge:
            metric_calls.append(viewer_role)
            return _FakeGauge()

    user = _user(role="")

    with (
        patch.object(approvals_api, "EnforcementService", return_value=service),
        patch.object(
            approvals_api,
            "ENFORCEMENT_APPROVAL_QUEUE_BACKLOG",
            _FakeMetric(),
        ),
    ):
        response = await approvals_api.get_approval_queue(
            limit=25,
            current_user=user,
            db=AsyncMock(),
        )

    assert len(response) == 1
    assert response[0].approval_id == approval.id
    assert response[0].source == "terraform"
    assert response[0].reason_codes == []
    service.list_pending_approvals.assert_awaited_once_with(
        tenant_id=user.tenant_id,
        reviewer=user,
        limit=25,
    )
    assert metric_calls == ["unknown"]
    assert gauge_calls == [1]


@pytest.mark.asyncio
async def test_get_approval_queue_records_normalized_nonempty_role_metric() -> None:
    now = datetime.now(timezone.utc)
    approval = SimpleNamespace(
        id=uuid4(),
        decision_id=uuid4(),
        status=SimpleNamespace(value="pending"),
        routing_rule_id="route-2",
        expires_at=now,
        created_at=now,
    )
    decision = SimpleNamespace(
        id=approval.decision_id,
        source=SimpleNamespace(value="k8s_admission"),
        environment="nonprod",
        project_id="project-b",
        action="admission.review",
        resource_reference="namespace/default",
        estimated_monthly_delta_usd=Decimal("1.0"),
        reason_codes=["policy_soft_threshold"],
    )
    service = SimpleNamespace(
        list_pending_approvals=AsyncMock(return_value=[(approval, decision)])
    )
    metric_calls: list[str] = []
    gauge_calls: list[int] = []

    class _FakeGauge:
        def set(self, value: int) -> None:
            gauge_calls.append(value)

    class _FakeMetric:
        def labels(self, *, viewer_role: str) -> _FakeGauge:
            metric_calls.append(viewer_role)
            return _FakeGauge()

    user = _user(role=SimpleNamespace(value=" Admin "))

    with (
        patch.object(approvals_api, "EnforcementService", return_value=service),
        patch.object(
            approvals_api,
            "ENFORCEMENT_APPROVAL_QUEUE_BACKLOG",
            _FakeMetric(),
        ),
    ):
        response = await approvals_api.get_approval_queue(
            limit=10,
            current_user=user,
            db=AsyncMock(),
        )

    assert len(response) == 1
    assert response[0].source == "k8s_admission"
    assert response[0].reason_codes == ["policy_soft_threshold"]
    assert metric_calls == ["admin"]
    assert gauge_calls == [1]


@pytest.mark.asyncio
async def test_approve_and_deny_requests_map_service_results() -> None:
    payload = ApprovalReviewRequest(notes="reviewed")
    user = _user()
    now = datetime.now(timezone.utc)
    approval_approved = SimpleNamespace(
        status=SimpleNamespace(value="approved"),
        id=uuid4(),
        decision_id=uuid4(),
        routing_rule_id="rr-1",
    )
    approval_denied = SimpleNamespace(
        status=SimpleNamespace(value="denied"),
        id=uuid4(),
        decision_id=uuid4(),
        routing_rule_id=None,
    )
    decision_approved = SimpleNamespace(id=approval_approved.decision_id)
    decision_denied = SimpleNamespace(id=approval_denied.decision_id)

    service = SimpleNamespace(
        approve_request=AsyncMock(
            return_value=(
                approval_approved,
                decision_approved,
                "signed-token",
                now,
            )
        ),
        deny_request=AsyncMock(return_value=(approval_denied, decision_denied)),
    )

    with patch.object(approvals_api, "EnforcementService", return_value=service):
        approve_response = await approvals_api.approve_approval_request(
            approval_id=approval_approved.id,
            payload=payload,
            current_user=user,
            db=AsyncMock(),
        )
        deny_response = await approvals_api.deny_approval_request(
            approval_id=approval_denied.id,
            payload=payload,
            current_user=user,
            db=AsyncMock(),
        )

    assert approve_response.status == "approved"
    assert approve_response.approval_token == "signed-token"
    assert approve_response.token_expires_at == now
    assert deny_response.status == "denied"
    assert deny_response.approval_token is None
    assert deny_response.token_expires_at is None


@pytest.mark.asyncio
async def test_consume_approval_token_success_uses_decision_expiry_fallback() -> None:
    user = _user()
    approval_token = "a" * 32
    now = datetime.now(timezone.utc)
    expires_at = datetime.now(timezone.utc)
    payload = ApprovalTokenConsumeRequest(approval_token=approval_token)

    approval = SimpleNamespace(
        id=uuid4(),
        approval_token_expires_at=None,
        approval_token_consumed_at=now,
    )
    decision = SimpleNamespace(
        id=uuid4(),
        source=SimpleNamespace(value="terraform"),
        environment="prod",
        project_id="project-a",
        action="terraform.apply",
        resource_reference="module.eks",
        request_fingerprint="f" * 64,
        estimated_monthly_delta_usd=Decimal("99.0"),
        estimated_hourly_delta_usd=Decimal("0.14"),
        token_expires_at=expires_at,
    )
    service = SimpleNamespace(
        consume_approval_token=AsyncMock(return_value=(approval, decision))
    )

    with patch.object(approvals_api, "EnforcementService", return_value=service):
        response = await approvals_api.consume_approval_token(
            request=SimpleNamespace(),
            payload=payload,
            current_user=user,
            db=AsyncMock(),
        )

    assert response.status == "consumed"
    assert response.token_expires_at == expires_at
    assert response.consumed_at == now
    service.consume_approval_token.assert_awaited_once_with(
        tenant_id=user.tenant_id,
        approval_token=approval_token,
        actor_id=user.id,
        expected_source=None,
        expected_project_id=None,
        expected_environment=None,
        expected_request_fingerprint=None,
        expected_resource_reference=None,
    )


@pytest.mark.asyncio
async def test_consume_approval_token_raises_when_expiry_or_consumed_missing() -> None:
    user = _user()
    payload = ApprovalTokenConsumeRequest(approval_token="b" * 32)
    decision = SimpleNamespace(
        id=uuid4(),
        source=SimpleNamespace(value="terraform"),
        environment="prod",
        project_id="project-b",
        action="terraform.apply",
        resource_reference="module.db",
        request_fingerprint="z" * 64,
        estimated_monthly_delta_usd=Decimal("50.0"),
        estimated_hourly_delta_usd=Decimal("0.08"),
        token_expires_at=None,
    )

    service_no_expiry = SimpleNamespace(
        consume_approval_token=AsyncMock(
            return_value=(
                SimpleNamespace(
                    id=uuid4(),
                    approval_token_expires_at=None,
                    approval_token_consumed_at=datetime.now(timezone.utc),
                ),
                decision,
            )
        )
    )
    with patch.object(
        approvals_api,
        "EnforcementService",
        return_value=service_no_expiry,
    ):
        with pytest.raises(HTTPException, match="Approval token expiry is unavailable"):
            await approvals_api.consume_approval_token(
                request=SimpleNamespace(),
                payload=payload,
                current_user=user,
                db=AsyncMock(),
            )

    decision_with_expiry = SimpleNamespace(
        **{
            **decision.__dict__,
            "token_expires_at": datetime.now(timezone.utc),
        }
    )
    service_not_consumed = SimpleNamespace(
        consume_approval_token=AsyncMock(
            return_value=(
                SimpleNamespace(
                    id=uuid4(),
                    approval_token_expires_at=decision_with_expiry.token_expires_at,
                    approval_token_consumed_at=None,
                ),
                decision_with_expiry,
            )
        )
    )
    with patch.object(
        approvals_api,
        "EnforcementService",
        return_value=service_not_consumed,
    ):
        with pytest.raises(HTTPException, match="Approval token was not consumed"):
            await approvals_api.consume_approval_token(
                request=SimpleNamespace(),
                payload=payload,
                current_user=user,
                db=AsyncMock(),
            )
