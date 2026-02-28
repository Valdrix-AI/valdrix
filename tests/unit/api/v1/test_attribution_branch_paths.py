from __future__ import annotations

from datetime import date
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.modules.reporting.api.v1 import attribution as attribution_api
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.pricing import PricingTier


def _user(*, tenant_id: object | None = None) -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email="attribution@example.com",
        tenant_id=tenant_id if tenant_id is not None else uuid4(),
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )


def _request(path: str) -> SimpleNamespace:
    return SimpleNamespace(method="POST", url=SimpleNamespace(path=path))


def _rule(**overrides: object) -> SimpleNamespace:
    base = {
        "id": uuid4(),
        "name": "Rule A",
        "priority": 10,
        "rule_type": "DIRECT",
        "conditions": {"service": "AmazonEC2"},
        "allocation": {"bucket": "Platform"},
        "is_active": True,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_tenant_id_or_403_rejects_missing_tenant() -> None:
    user = CurrentUser(
        id=uuid4(),
        email="attribution-no-tenant@example.com",
        tenant_id=None,
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )
    with pytest.raises(HTTPException) as exc:
        attribution_api._tenant_id_or_403(user)
    assert exc.value.status_code == 403
    assert exc.value.detail == "Tenant context is required"


@pytest.mark.asyncio
async def test_list_rules_returns_model_validated_payload() -> None:
    db = MagicMock()
    user = _user()
    rule = _rule()

    with patch.object(attribution_api, "AttributionEngine") as engine_cls:
        engine = MagicMock()
        engine.list_rules = AsyncMock(return_value=[rule])
        engine_cls.return_value = engine

        response = await attribution_api.list_rules(
            include_inactive=False,
            db=db,
            current_user=user,
        )

    assert len(response) == 1
    assert str(response[0].id) == str(rule.id)
    assert response[0].name == "Rule A"
    engine.list_rules.assert_awaited_once_with(user.tenant_id, include_inactive=False)


@pytest.mark.asyncio
async def test_create_rule_rejects_invalid_payload() -> None:
    db = MagicMock()
    user = _user()
    payload = attribution_api.RuleCreateRequest(
        name="Invalid",
        priority=5,
        rule_type="PERCENTAGE",
        conditions={},
        allocation=[{"bucket": "A", "percentage": 70}, {"bucket": "B", "percentage": 20}],
        is_active=True,
    )

    with patch.object(attribution_api, "AttributionEngine") as engine_cls:
        engine = MagicMock()
        engine.validate_rule_payload = MagicMock(return_value=["Percentages must sum to 100"])
        engine_cls.return_value = engine
        with pytest.raises(HTTPException) as exc:
            await attribution_api.create_rule(
                request=_request("/api/v1/attribution/rules"),
                payload=payload,
                db=db,
                current_user=user,
            )
    assert exc.value.status_code == 422
    assert "sum to 100" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_create_rule_success_logs_and_commits() -> None:
    db = MagicMock()
    db.commit = AsyncMock()
    user = _user()
    payload = attribution_api.RuleCreateRequest(
        name="EC2 Direct",
        priority=1,
        rule_type="DIRECT",
        conditions={"service": "AmazonEC2"},
        allocation={"bucket": "Platform"},
        is_active=True,
    )
    created_rule = _rule(name="EC2 Direct", priority=1)

    with (
        patch.object(attribution_api, "AttributionEngine") as engine_cls,
        patch.object(attribution_api, "AuditLogger") as audit_cls,
    ):
        engine = MagicMock()
        engine.validate_rule_payload = MagicMock(return_value=[])
        engine.create_rule = AsyncMock(return_value=created_rule)
        engine_cls.return_value = engine

        audit = MagicMock()
        audit.log = AsyncMock()
        audit_cls.return_value = audit

        response = await attribution_api.create_rule(
            request=_request("/api/v1/attribution/rules"),
            payload=payload,
            db=db,
            current_user=user,
        )

    assert response.name == "EC2 Direct"
    assert response.priority == 1
    audit.log.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_rule_returns_404_when_missing() -> None:
    db = MagicMock()
    user = _user()
    payload = attribution_api.RuleUpdateRequest(priority=5)

    with patch.object(attribution_api, "AttributionEngine") as engine_cls:
        engine = MagicMock()
        engine.get_rule = AsyncMock(return_value=None)
        engine_cls.return_value = engine

        with pytest.raises(HTTPException) as exc:
            await attribution_api.update_rule(
                request=_request("/api/v1/attribution/rules/x"),
                rule_id=uuid4(),
                payload=payload,
                db=db,
                current_user=user,
            )
    assert exc.value.status_code == 404
    assert "Attribution rule not found" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_update_rule_rejects_invalid_updated_payload() -> None:
    db = MagicMock()
    user = _user()
    rule_id = uuid4()
    payload = attribution_api.RuleUpdateRequest(
        rule_type="PERCENTAGE",
        allocation=[{"bucket": "A", "percentage": 70}, {"bucket": "B", "percentage": 20}],
    )

    with patch.object(attribution_api, "AttributionEngine") as engine_cls:
        engine = MagicMock()
        engine.get_rule = AsyncMock(return_value=_rule(id=rule_id))
        engine.validate_rule_payload = MagicMock(return_value=["Invalid allocation"])
        engine_cls.return_value = engine

        with pytest.raises(HTTPException) as exc:
            await attribution_api.update_rule(
                request=_request("/api/v1/attribution/rules/x"),
                rule_id=rule_id,
                payload=payload,
                db=db,
                current_user=user,
            )
    assert exc.value.status_code == 422
    assert "Invalid allocation" in str(exc.value.detail)


@pytest.mark.asyncio
async def test_update_rule_returns_404_when_update_misses() -> None:
    db = MagicMock()
    user = _user()
    rule_id = uuid4()
    payload = attribution_api.RuleUpdateRequest(priority=2)

    with patch.object(attribution_api, "AttributionEngine") as engine_cls:
        engine = MagicMock()
        engine.get_rule = AsyncMock(return_value=_rule(id=rule_id))
        engine.update_rule = AsyncMock(return_value=None)
        engine_cls.return_value = engine

        with pytest.raises(HTTPException) as exc:
            await attribution_api.update_rule(
                request=_request("/api/v1/attribution/rules/x"),
                rule_id=rule_id,
                payload=payload,
                db=db,
                current_user=user,
            )
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_update_rule_success_logs_and_commits() -> None:
    db = MagicMock()
    db.commit = AsyncMock()
    user = _user()
    rule_id = uuid4()
    payload = attribution_api.RuleUpdateRequest(priority=2, is_active=False)
    updated_rule = _rule(id=rule_id, priority=2, is_active=False)

    with (
        patch.object(attribution_api, "AttributionEngine") as engine_cls,
        patch.object(attribution_api, "AuditLogger") as audit_cls,
    ):
        engine = MagicMock()
        engine.get_rule = AsyncMock(return_value=_rule(id=rule_id))
        engine.update_rule = AsyncMock(return_value=updated_rule)
        engine_cls.return_value = engine

        audit = MagicMock()
        audit.log = AsyncMock()
        audit_cls.return_value = audit

        response = await attribution_api.update_rule(
            request=_request("/api/v1/attribution/rules/x"),
            rule_id=rule_id,
            payload=payload,
            db=db,
            current_user=user,
        )

    assert response.priority == 2
    assert response.is_active is False
    audit.log.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_rule_success_with_rule_type_change_validation_path() -> None:
    db = MagicMock()
    db.commit = AsyncMock()
    user = _user()
    rule_id = uuid4()
    payload = attribution_api.RuleUpdateRequest(
        rule_type="PERCENTAGE",
        allocation=[{"bucket": "A", "percentage": 50}, {"bucket": "B", "percentage": 50}],
    )
    updated_rule = _rule(
        id=rule_id,
        rule_type="PERCENTAGE",
        allocation=[{"bucket": "A", "percentage": 50}, {"bucket": "B", "percentage": 50}],
    )

    with (
        patch.object(attribution_api, "AttributionEngine") as engine_cls,
        patch.object(attribution_api, "AuditLogger") as audit_cls,
    ):
        engine = MagicMock()
        engine.get_rule = AsyncMock(return_value=_rule(id=rule_id))
        engine.validate_rule_payload = MagicMock(return_value=[])
        engine.update_rule = AsyncMock(return_value=updated_rule)
        engine_cls.return_value = engine

        audit = MagicMock()
        audit.log = AsyncMock()
        audit_cls.return_value = audit

        response = await attribution_api.update_rule(
            request=_request("/api/v1/attribution/rules/x"),
            rule_id=rule_id,
            payload=payload,
            db=db,
            current_user=user,
        )

    assert response.rule_type == "PERCENTAGE"
    engine.validate_rule_payload.assert_called_once()
    audit.log.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_delete_rule_not_found_and_success_paths() -> None:
    user = _user()

    # not found
    db_missing = MagicMock()
    with patch.object(attribution_api, "AttributionEngine") as engine_cls:
        engine = MagicMock()
        engine.delete_rule = AsyncMock(return_value=False)
        engine_cls.return_value = engine
        with pytest.raises(HTTPException) as exc:
            await attribution_api.delete_rule(
                request=_request("/api/v1/attribution/rules/x"),
                rule_id=uuid4(),
                db=db_missing,
                current_user=user,
            )
    assert exc.value.status_code == 404

    # success
    db = MagicMock()
    db.commit = AsyncMock()
    with (
        patch.object(attribution_api, "AttributionEngine") as engine_cls,
        patch.object(attribution_api, "AuditLogger") as audit_cls,
    ):
        engine = MagicMock()
        engine.delete_rule = AsyncMock(return_value=True)
        engine_cls.return_value = engine
        audit = MagicMock()
        audit.log = AsyncMock()
        audit_cls.return_value = audit

        response = await attribution_api.delete_rule(
            request=_request("/api/v1/attribution/rules/x"),
            rule_id=uuid4(),
            db=db,
            current_user=user,
        )
    assert response["status"] == "deleted"
    audit.log.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_simulate_rule_validation_and_window_errors() -> None:
    user = _user()
    payload = attribution_api.RuleSimulationRequest(
        rule_type="PERCENTAGE",
        conditions={},
        allocation=[{"bucket": "A", "percentage": 70}, {"bucket": "B", "percentage": 20}],
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 1),
        sample_limit=100,
    )
    with patch.object(attribution_api, "AttributionEngine") as engine_cls:
        engine = MagicMock()
        engine.validate_rule_payload = MagicMock(return_value=["invalid allocation"])
        engine_cls.return_value = engine
        with pytest.raises(HTTPException) as exc:
            await attribution_api.simulate_rule(
                request=_request("/api/v1/attribution/simulate"),
                payload=payload,
                db=MagicMock(),
                current_user=user,
            )
    assert exc.value.status_code == 422

    payload_bad_window = attribution_api.RuleSimulationRequest(
        rule_type="DIRECT",
        conditions={},
        allocation={"bucket": "A"},
        start_date=date(2026, 2, 2),
        end_date=date(2026, 2, 1),
        sample_limit=100,
    )
    with patch.object(attribution_api, "AttributionEngine") as engine_cls:
        engine = MagicMock()
        engine.validate_rule_payload = MagicMock(return_value=[])
        engine_cls.return_value = engine
        with pytest.raises(HTTPException) as exc:
            await attribution_api.simulate_rule(
                request=_request("/api/v1/attribution/simulate"),
                payload=payload_bad_window,
                db=MagicMock(),
                current_user=user,
            )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_simulate_rule_success_logs_and_commits() -> None:
    user = _user()
    db = MagicMock()
    db.commit = AsyncMock()
    payload = attribution_api.RuleSimulationRequest(
        rule_type="DIRECT",
        conditions={"service": "AmazonEC2"},
        allocation={"bucket": "Platform"},
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 1),
        sample_limit=100,
    )
    simulated = {"matched_records": 1, "projected_allocation_total": 50.0}

    with (
        patch.object(attribution_api, "AttributionEngine") as engine_cls,
        patch.object(attribution_api, "AuditLogger") as audit_cls,
    ):
        engine = MagicMock()
        engine.validate_rule_payload = MagicMock(return_value=[])
        engine.simulate_rule = AsyncMock(return_value=simulated)
        engine_cls.return_value = engine
        audit = MagicMock()
        audit.log = AsyncMock()
        audit_cls.return_value = audit

        response = await attribution_api.simulate_rule(
            request=_request("/api/v1/attribution/simulate"),
            payload=payload,
            db=db,
            current_user=user,
        )

    assert response["matched_records"] == 1
    audit.log.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_apply_rules_invalid_window_and_success() -> None:
    user = _user()
    payload_bad = attribution_api.ApplyAttributionRequest(
        start_date=date(2026, 2, 2),
        end_date=date(2026, 2, 1),
    )
    with pytest.raises(HTTPException) as exc:
        await attribution_api.apply_rules(
            request=_request("/api/v1/attribution/apply"),
            payload=payload_bad,
            db=MagicMock(),
            current_user=user,
        )
    assert exc.value.status_code == 400

    db = MagicMock()
    db.commit = AsyncMock()
    payload_ok = attribution_api.ApplyAttributionRequest(
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 1),
    )
    with (
        patch.object(attribution_api, "AttributionEngine") as engine_cls,
        patch.object(attribution_api, "AuditLogger") as audit_cls,
    ):
        engine = MagicMock()
        engine.apply_rules_to_tenant = AsyncMock(
            return_value={"records_processed": 1, "allocations_created": 1}
        )
        engine_cls.return_value = engine
        audit = MagicMock()
        audit.log = AsyncMock()
        audit_cls.return_value = audit

        response = await attribution_api.apply_rules(
            request=_request("/api/v1/attribution/apply"),
            payload=payload_ok,
            db=db,
            current_user=user,
        )
    assert response["status"] == "completed"
    assert response["records_processed"] == 1
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_coverage_and_unallocated_endpoints_validation_and_success() -> None:
    user = _user()

    with pytest.raises(HTTPException):
        await attribution_api.get_coverage_kpis(
            start_date=date(2026, 2, 2),
            end_date=date(2026, 2, 1),
            target_percentage=90.0,
            db=MagicMock(),
            current_user=user,
        )

    with patch.object(attribution_api, "AttributionEngine") as engine_cls:
        engine = MagicMock()
        engine.get_allocation_coverage = AsyncMock(return_value={"status": "ok"})
        engine_cls.return_value = engine
        coverage = await attribution_api.get_coverage_kpis(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 2),
            target_percentage=90.0,
            db=MagicMock(),
            current_user=user,
        )
    assert coverage["status"] == "ok"

    with pytest.raises(HTTPException):
        await attribution_api.get_unallocated_analysis(
            start_date=date(2026, 2, 2),
            end_date=date(2026, 2, 1),
            db=MagicMock(),
            current_user=user,
        )

    with patch.object(attribution_api, "AttributionEngine") as engine_cls:
        engine = MagicMock()
        engine.get_unallocated_analysis = AsyncMock(return_value=[{"service": "AmazonS3"}])
        engine_cls.return_value = engine
        analysis = await attribution_api.get_unallocated_analysis(
            start_date=date(2026, 2, 1),
            end_date=date(2026, 2, 1),
            db=MagicMock(),
            current_user=user,
        )
    assert analysis["status"] == "success"
    assert analysis["items"][0]["service"] == "AmazonS3"
