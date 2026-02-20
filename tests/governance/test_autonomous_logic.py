import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from app.shared.remediation.autonomous import AutonomousRemediationEngine
from app.models.remediation import RemediationAction


@pytest.mark.asyncio
async def test_autonomous_dry_run_safety():
    """Verify that dry_run=True NEVER executes actions."""

    db = AsyncMock()
    tenant_id = uuid.uuid4()
    engine = AutonomousRemediationEngine(db, tenant_id)
    engine.auto_pilot_enabled = False  # Default is False (Dry run)
    no_duplicate_result = MagicMock()
    no_duplicate_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=no_duplicate_result)

    # Mock remediation service
    mock_service = AsyncMock()
    # Mock existing request check to return None (no duplicate)
    # create a synchronous Mock for the Result object
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_service.db.execute.return_value = mock_result

    # Process a high confidence candidate
    await engine._process_candidate(
        service=mock_service,
        resource_id="vol-123",
        resource_type="ebs_volume",
        provider="aws",
        connection_id=None,
        action=RemediationAction.DELETE_VOLUME,
        savings=10.0,
        confidence=1.0,  # 100% confidence
        reason="Test candidate",
    )

    # Should create request
    mock_service.create_request.assert_awaited_once()

    # Should NOT approve or execute
    mock_service.approve.assert_not_awaited()
    mock_service.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_autonomous_auto_pilot_execution():
    """Verify that auto-pilot executes high confidence items."""

    db = AsyncMock()
    tenant_id = uuid.uuid4()
    engine = AutonomousRemediationEngine(db, tenant_id)
    engine.auto_pilot_enabled = True  # Enable Auto-Pilot
    no_duplicate_result = MagicMock()
    no_duplicate_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=no_duplicate_result)

    mock_service = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_service.db.execute.return_value = mock_result

    # Process high confidence (above 0.95 threshold)
    await engine._process_candidate(
        service=mock_service,
        resource_id="snap-123",
        resource_type="ebs_snapshot",
        provider="aws",
        connection_id=None,
        action=RemediationAction.DELETE_SNAPSHOT,
        savings=5.0,
        confidence=0.99,
        reason="Test candidate",
    )

    # Should execute
    mock_service.create_request.assert_awaited_once()
    mock_service.approve.assert_awaited_once()
    mock_service.execute.assert_awaited_once()


@pytest.mark.asyncio
async def test_autonomous_low_confidence_safety():
    """Verify low confidence items are NOT auto-executed even in auto-pilot."""

    db = AsyncMock()
    tenant_id = uuid.uuid4()
    engine = AutonomousRemediationEngine(db, tenant_id)
    engine.auto_pilot_enabled = True  # Enable Auto-Pilot
    no_duplicate_result = MagicMock()
    no_duplicate_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=no_duplicate_result)

    mock_service = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_service.db.execute.return_value = mock_result

    # Process low confidence (below 0.95)
    await engine._process_candidate(
        service=mock_service,
        resource_id="vol-sus",
        resource_type="ebs_volume",
        provider="aws",
        connection_id=None,
        action=RemediationAction.DELETE_VOLUME,
        savings=10.0,
        confidence=0.80,
        reason="Test candidate",
    )

    # Should create request but NOT execute
    mock_service.create_request.assert_awaited_once()
    mock_service.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_run_autonomous_sweep_returns_scan_failure_payload():
    db = AsyncMock()
    tenant_id = uuid.uuid4()
    engine = AutonomousRemediationEngine(db, tenant_id)

    with patch("app.shared.remediation.autonomous.ZombieService") as service_cls:
        service = service_cls.return_value
        service.scan_for_tenant = AsyncMock(side_effect=RuntimeError("scan failed"))

        result = await engine.run_autonomous_sweep(
            region="us-east-1",
            credentials={"access_key_id": "x"},
        )

    assert result["mode"] == "dry_run"
    assert result["scanned"] == 0
    assert result["auto_executed"] == 0
    assert result["error"] == "scan_failed"


@pytest.mark.asyncio
async def test_run_autonomous_sweep_processes_actionable_categories_only():
    db = AsyncMock()
    tenant_id = uuid.uuid4()
    engine = AutonomousRemediationEngine(db, tenant_id)
    engine._process_candidate = AsyncMock(return_value=False)  # type: ignore[method-assign]

    scan_payload = {
        "unattached_volumes": [
            {
                "resource_id": "vol-1",
                "provider": "aws",
                "connection_id": str(uuid.uuid4()),
                "monthly_waste": 12.5,
                "confidence_score": 0.9,
            },
            {
                "resource_id": "vol-2",
                "provider": "aws",
                "connection_id": str(uuid.uuid4()),
                "monthly_waste": 2.0,
                "confidence_score": 0.5,
            },
        ],
        "idle_platform_services": [
            {
                "resource_id": "svc-1",
                "provider": "platform",
                "connection_id": str(uuid.uuid4()),
                "monthly_waste": 4.1,
                "confidence_score": 0.8,
            }
        ],
        "non_actionable_category": [{"resource_id": "x-1", "provider": "aws"}],
    }

    with patch("app.shared.remediation.autonomous.ZombieService") as service_cls:
        service = service_cls.return_value
        service.scan_for_tenant = AsyncMock(return_value=scan_payload)

        result = await engine.run_autonomous_sweep(
            region="us-east-1",
            credentials={"access_key_id": "x"},
        )

    assert result["mode"] == "dry_run"
    assert result["scanned"] == 3
    assert result["auto_executed"] == 0
    assert engine._process_candidate.await_count == 3  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_run_autonomous_sweep_no_connections_returns_specific_error():
    db = AsyncMock()
    tenant_id = uuid.uuid4()
    engine = AutonomousRemediationEngine(db, tenant_id)

    with patch("app.shared.remediation.autonomous.ZombieService") as service_cls:
        service = service_cls.return_value
        service.scan_for_tenant = AsyncMock(
            return_value={"error": "No cloud connections found.", "total_monthly_waste": 0.0}
        )

        result = await engine.run_autonomous_sweep(
            region="us-east-1",
            credentials={},
        )

    assert result["mode"] == "dry_run"
    assert result["scanned"] == 0
    assert result["auto_executed"] == 0
    assert result["error"] == "no_connections_found"


@pytest.mark.asyncio
async def test_run_autonomous_sweep_filters_connection_scope():
    db = AsyncMock()
    tenant_id = uuid.uuid4()
    engine = AutonomousRemediationEngine(db, tenant_id)
    engine._process_candidate = AsyncMock(return_value=False)  # type: ignore[method-assign]

    target_connection = uuid.uuid4()
    other_connection = uuid.uuid4()
    scan_payload = {
        "idle_platform_services": [
            {
                "resource_id": "svc-1",
                "provider": "platform",
                "connection_id": str(target_connection),
            },
            {
                "resource_id": "svc-2",
                "provider": "platform",
                "connection_id": str(other_connection),
            },
        ]
    }

    with patch("app.shared.remediation.autonomous.ZombieService") as service_cls:
        service = service_cls.return_value
        service.scan_for_tenant = AsyncMock(return_value=scan_payload)

        result = await engine.run_autonomous_sweep(
            region="us-east-1",
            credentials=None,
            connection_id=str(target_connection),
        )

    assert result["scanned"] == 1
    assert engine._process_candidate.await_count == 1  # type: ignore[attr-defined]


def test_resolve_action_handles_saas_github_and_manual_review():
    github_action = AutonomousRemediationEngine._resolve_action(
        "saas",
        "unused_license_seats",
        {"action": "revoke_github_seat", "resource_type": "GitHub Seat"},
    )
    generic_action = AutonomousRemediationEngine._resolve_action(
        "saas",
        "idle_saas_subscriptions",
        {"action": "review_saas_subscription", "resource_type": "SaaS Subscription"},
    )

    assert github_action == RemediationAction.REVOKE_GITHUB_SEAT
    assert generic_action == RemediationAction.MANUAL_REVIEW


@pytest.mark.parametrize(
    ("provider", "category", "expected"),
    [
        ("azure", "idle_instances", RemediationAction.DEALLOCATE_AZURE_VM),
        ("gcp", "idle_instances", RemediationAction.STOP_GCP_INSTANCE),
        ("azure", "unattached_volumes", RemediationAction.MANUAL_REVIEW),
        ("gcp", "old_snapshots", RemediationAction.MANUAL_REVIEW),
        ("hybrid", "idle_hybrid_resources", RemediationAction.MANUAL_REVIEW),
    ],
)
def test_resolve_action_covers_non_aws_provider_paths(
    provider: str, category: str, expected: RemediationAction
) -> None:
    action = AutonomousRemediationEngine._resolve_action(
        provider,
        category,
        {"action": "", "resource_type": "generic"},
    )
    assert action == expected
