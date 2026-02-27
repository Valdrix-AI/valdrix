from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.remediation import RemediationAction
from app.shared.remediation.autonomous import AutonomousRemediationEngine


def _db_result(value: object | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.mark.asyncio
async def test_process_candidate_skips_duplicate_open_request() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_db_result(uuid.uuid4()))
    engine = AutonomousRemediationEngine(db, uuid.uuid4())

    mock_service = AsyncMock()
    with patch("app.shared.remediation.autonomous.logger.info") as logger_info:
        was_auto = await engine._process_candidate(
            service=mock_service,
            resource_id="vol-dup",
            resource_type="EBS Volume",
            provider="aws",
            connection_id=None,
            action=RemediationAction.DELETE_VOLUME,
            savings=10.0,
            confidence=0.99,
            reason="duplicate candidate",
        )

    assert was_auto is False
    mock_service.create_request.assert_not_awaited()
    logger_info.assert_called()


def test_autonomous_helper_parsers_cover_invalid_branches() -> None:
    assert AutonomousRemediationEngine._coerce_uuid(None) is None
    assert AutonomousRemediationEngine._coerce_uuid("not-a-uuid") is None
    parsed = AutonomousRemediationEngine._coerce_uuid(str(uuid.uuid4()))
    assert parsed is not None

    assert AutonomousRemediationEngine._as_float("1.25", default=0.0) == 1.25
    assert AutonomousRemediationEngine._as_float("bad", default=0.8) == 0.8

    assert (
        AutonomousRemediationEngine._resolve_action(
            "saas",
            "unused_license_seats",
            {"resource_type": "GitHub Seat", "action": ""},
        )
        == RemediationAction.REVOKE_GITHUB_SEAT
    )
    assert (
        AutonomousRemediationEngine._resolve_action(
            "aws",
            "unknown_category",
            {"resource_type": "EC2", "action": ""},
        )
        is None
    )
    assert (
        AutonomousRemediationEngine._resolve_action(
            "saas",
            "weird_category",
            {"resource_type": "SaaS Subscription", "action": ""},
        )
        is None
    )


@pytest.mark.asyncio
async def test_execute_automatic_filters_inputs_and_counts_auto_executed() -> None:
    engine = AutonomousRemediationEngine(AsyncMock(), uuid.uuid4())
    engine._process_candidate = AsyncMock(side_effect=[True, False])  # type: ignore[method-assign]

    recommendations = [
        "not-a-dict",
        {"provider": None, "category": "idle_instances", "resource_id": "i-invalid"},
        {"provider": "aws", "category": "unknown", "resource_id": "i-skip"},
        {"provider": "aws", "category": "unattached_volumes"},
        {
            "provider": "aws",
            "category": "unattached_volumes",
            "resource_id": "vol-1",
            "connection_id": "not-a-uuid",
            "confidence_score": "bad",
            "monthly_waste": "bad",
        },
        {
            "provider": "platform",
            "category": "idle_platform_services",
            "id": "svc-1",
            "monthly_cost": 3.5,
        },
    ]

    with patch("app.shared.remediation.autonomous.logger.warning") as logger_warning:
        auto_executed = await engine.execute_automatic(recommendations)

    assert auto_executed == 1
    assert engine._process_candidate.await_count == 2  # type: ignore[attr-defined]
    first_call = engine._process_candidate.await_args_list[0].kwargs  # type: ignore[attr-defined]
    assert first_call["connection_id"] is None
    assert first_call["confidence"] == 0.8
    assert first_call["savings"] == 0.0
    logger_warning.assert_called_once()


@pytest.mark.asyncio
async def test_run_autonomous_sweep_invalid_scan_payload_returns_scan_failed() -> None:
    engine = AutonomousRemediationEngine(AsyncMock(), uuid.uuid4())

    with patch("app.shared.remediation.autonomous.ZombieService") as service_cls:
        service_cls.return_value.scan_for_tenant = AsyncMock(return_value=["not-a-dict"])
        result = await engine.run_autonomous_sweep(region="us-east-1", credentials={})

    assert result == {
        "mode": "dry_run",
        "scanned": 0,
        "auto_executed": 0,
        "error": "scan_failed",
    }


@pytest.mark.asyncio
async def test_run_autonomous_sweep_skips_invalid_candidates_and_counts_auto_executed() -> None:
    engine = AutonomousRemediationEngine(AsyncMock(), uuid.uuid4())
    engine._process_candidate = AsyncMock(return_value=True)  # type: ignore[method-assign]

    scan_payload = {
        "non_list_category": "ignore",
        "idle_platform_services": [
            "not-a-dict",
            {"provider": None, "resource_id": "bad-provider"},
            {"provider": "aws", "id": "no-action"},  # category comes from outer key -> no AWS action mapping
            {"provider": "platform"},  # missing resource_id
            {
                "provider": "platform",
                "resource_id": "svc-1",
                "monthly_cost": 7.5,
                "confidence_score": 0.91,
            },
        ],
        "non_actionable_category": [
            {"provider": "aws", "resource_id": "skip-no-action"}
        ],
    }

    with patch("app.shared.remediation.autonomous.ZombieService") as service_cls:
        service_cls.return_value.scan_for_tenant = AsyncMock(return_value=scan_payload)
        result = await engine.run_autonomous_sweep(region="global", credentials=None)

    assert result["mode"] == "dry_run"
    assert result["scanned"] == 1
    assert result["auto_executed"] == 1
    engine._process_candidate.assert_awaited_once()  # type: ignore[attr-defined]
