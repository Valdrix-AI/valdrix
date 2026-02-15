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

    mock_service = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_service.db.execute.return_value = mock_result

    # Process high confidence (above 0.95 threshold)
    await engine._process_candidate(
        service=mock_service,
        resource_id="snap-123",
        resource_type="ebs_snapshot",
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

    mock_service = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_service.db.execute.return_value = mock_result

    # Process low confidence (below 0.95)
    await engine._process_candidate(
        service=mock_service,
        resource_id="vol-sus",
        resource_type="ebs_volume",
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

    with patch("app.shared.remediation.autonomous.AWSZombieDetector") as detector_cls:
        detector = detector_cls.return_value
        detector.scan_all = AsyncMock(side_effect=RuntimeError("scan failed"))

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
            {"resource_id": "vol-1", "monthly_waste": 12.5, "confidence_score": 0.9},
            {"resource_id": "vol-2", "monthly_waste": 2.0, "confidence_score": 0.5},
        ],
        "non_actionable_category": [{"resource_id": "x-1"}],
    }

    with patch("app.shared.remediation.autonomous.AWSZombieDetector") as detector_cls:
        detector = detector_cls.return_value
        detector.scan_all = AsyncMock(return_value=scan_payload)

        result = await engine.run_autonomous_sweep(
            region="us-east-1",
            credentials={"access_key_id": "x"},
        )

    assert result["mode"] == "dry_run"
    assert result["scanned"] == 2
    assert result["auto_executed"] == 0
    assert engine._process_candidate.await_count == 2  # type: ignore[attr-defined]
