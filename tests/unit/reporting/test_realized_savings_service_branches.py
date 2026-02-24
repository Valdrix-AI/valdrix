from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.models.realized_savings import RealizedSavingsEvent
from app.models.remediation import RemediationStatus
from app.modules.reporting.domain.realized_savings import (
    RealizedSavingsService,
    _decimal,
)


def _request(
    *,
    tenant_id,
    status: RemediationStatus = RemediationStatus.COMPLETED,
    executed_at: datetime | None = None,
    connection_id=None,
    resource_id: str = "i-123",
):
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=tenant_id,
        status=status,
        executed_at=executed_at,
        connection_id=connection_id,
        resource_id=resource_id,
        provider="aws",
        region="us-east-1",
        updated_at=executed_at,
        created_at=executed_at,
    )


def test_decimal_and_build_window_validation() -> None:
    assert _decimal(None) == Decimal("0")
    assert _decimal(Decimal("1.2")) == Decimal("1.2")
    assert _decimal("bad") == Decimal("0")

    executed_day = date(2026, 1, 10)
    window = RealizedSavingsService._build_windows(
        executed_day=executed_day,
        baseline_days=7,
        measurement_days=7,
        gap_days=-2,
    )
    assert window.baseline_start == date(2026, 1, 3)
    assert window.baseline_end == date(2026, 1, 9)
    assert window.measurement_start == date(2026, 1, 10)
    assert window.measurement_end == date(2026, 1, 16)

    with pytest.raises(ValueError):
        RealizedSavingsService._build_windows(
            executed_day=executed_day,
            baseline_days=0,
            measurement_days=7,
        )


@pytest.mark.asyncio
async def test_compute_for_request_returns_none_for_ineligible_inputs() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.scalar = AsyncMock()
    db.flush = AsyncMock()
    service = RealizedSavingsService(db)

    wrong_tenant = _request(
        tenant_id=uuid4(),
        executed_at=datetime.now(timezone.utc) - timedelta(days=30),
        connection_id=uuid4(),
    )
    with pytest.raises(ValueError):
        await service.compute_for_request(tenant_id=tenant_id, request=wrong_tenant)

    pending = _request(
        tenant_id=tenant_id,
        status=RemediationStatus.PENDING,
        executed_at=datetime.now(timezone.utc) - timedelta(days=30),
        connection_id=uuid4(),
    )
    assert await service.compute_for_request(tenant_id=tenant_id, request=pending) is None

    missing_executed = _request(
        tenant_id=tenant_id, executed_at=None, connection_id=uuid4()
    )
    assert (
        await service.compute_for_request(tenant_id=tenant_id, request=missing_executed)
        is None
    )

    missing_account = _request(
        tenant_id=tenant_id,
        executed_at=datetime.now(timezone.utc) - timedelta(days=30),
        connection_id=None,
    )
    assert (
        await service.compute_for_request(tenant_id=tenant_id, request=missing_account)
        is None
    )

    missing_resource = _request(
        tenant_id=tenant_id,
        executed_at=datetime.now(timezone.utc) - timedelta(days=30),
        connection_id=uuid4(),
        resource_id="  ",
    )
    assert (
        await service.compute_for_request(tenant_id=tenant_id, request=missing_resource)
        is None
    )


@pytest.mark.asyncio
async def test_compute_for_request_skips_future_measurement_or_incomplete_windows() -> None:
    tenant_id = uuid4()
    db = MagicMock()
    db.scalar = AsyncMock()
    db.flush = AsyncMock()
    service = RealizedSavingsService(db)

    executed_recent = _request(
        tenant_id=tenant_id,
        executed_at=datetime.now(timezone.utc) - timedelta(days=1),
        connection_id=uuid4(),
    )
    assert (
        await service.compute_for_request(
            tenant_id=tenant_id,
            request=executed_recent,
            baseline_days=7,
            measurement_days=7,
            gap_days=1,
        )
        is None
    )

    executed_old = _request(
        tenant_id=tenant_id,
        executed_at=datetime.now(timezone.utc) - timedelta(days=35),
        connection_id=uuid4(),
    )
    with patch.object(
        service,
        "_window_cost",
        new=AsyncMock(side_effect=[(Decimal("100"), 6), (Decimal("70"), 7)]),
    ):
        result = await service.compute_for_request(
            tenant_id=tenant_id,
            request=executed_old,
            baseline_days=7,
            measurement_days=7,
        )
    assert result is None
    db.scalar.assert_not_awaited()


@pytest.mark.asyncio
async def test_compute_for_request_updates_existing_event_and_clamps_negative_delta() -> None:
    tenant_id = uuid4()
    account_id = uuid4()
    request = _request(
        tenant_id=tenant_id,
        executed_at=datetime.now(timezone.utc) - timedelta(days=40),
        connection_id=account_id,
    )

    existing = SimpleNamespace(
        provider="old",
        account_id=None,
        resource_id=None,
        region=None,
        method=None,
        baseline_start_date=None,
        baseline_end_date=None,
        measurement_start_date=None,
        measurement_end_date=None,
        baseline_total_cost_usd=None,
        baseline_observed_days=None,
        measurement_total_cost_usd=None,
        measurement_observed_days=None,
        baseline_avg_daily_cost_usd=None,
        measurement_avg_daily_cost_usd=None,
        realized_avg_daily_savings_usd=None,
        realized_monthly_savings_usd=None,
        monthly_multiplier_days=None,
        confidence_score=None,
        details=None,
        computed_at=None,
    )

    db = MagicMock()
    db.scalar = AsyncMock(return_value=existing)
    db.flush = AsyncMock()
    db.add = MagicMock()
    service = RealizedSavingsService(db)

    with patch.object(
        service,
        "_window_cost",
        new=AsyncMock(side_effect=[(Decimal("10"), 7), (Decimal("70"), 7)]),
    ):
        result = await service.compute_for_request(
            tenant_id=tenant_id,
            request=request,
            baseline_days=7,
            measurement_days=7,
            require_final=False,
        )

    assert result is existing
    assert existing.provider == "aws"
    assert existing.account_id == account_id
    assert existing.realized_avg_daily_savings_usd == Decimal("0")
    assert existing.realized_monthly_savings_usd == Decimal("0")
    assert existing.details["clamped_at_zero"] is True
    db.add.assert_not_called()
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_compute_for_request_creates_new_event_when_missing() -> None:
    tenant_id = uuid4()
    account_id = uuid4()
    request = _request(
        tenant_id=tenant_id,
        executed_at=datetime.now(timezone.utc) - timedelta(days=40),
        connection_id=account_id,
    )

    db = MagicMock()
    db.scalar = AsyncMock(return_value=None)
    db.flush = AsyncMock()
    db.add = MagicMock()
    service = RealizedSavingsService(db)

    with patch.object(
        service,
        "_window_cost",
        new=AsyncMock(side_effect=[(Decimal("140"), 7), (Decimal("35"), 7)]),
    ):
        result = await service.compute_for_request(
            tenant_id=tenant_id,
            request=request,
            baseline_days=7,
            measurement_days=7,
            monthly_multiplier_days=30,
        )

    assert isinstance(result, RealizedSavingsEvent)
    assert result.realized_avg_daily_savings_usd == Decimal("15")
    assert result.realized_monthly_savings_usd == Decimal("450")
    db.add.assert_called_once_with(result)
    db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_window_cost_coerces_values() -> None:
    db = MagicMock()
    good_result = MagicMock()
    good_result.one.return_value = (Decimal("12.50"), 3)
    db.execute = AsyncMock(return_value=good_result)
    service = RealizedSavingsService(db)

    total, days = await service._window_cost(
        filters=[],
        start_day=date(2026, 1, 1),
        end_day=date(2026, 1, 7),
    )
    assert total == Decimal("12.50")
    assert days == 3

    bad_result = MagicMock()
    bad_result.one.return_value = ("bad", None)
    db.execute = AsyncMock(return_value=bad_result)
    total, days = await service._window_cost(
        filters=[],
        start_day=date(2026, 1, 1),
        end_day=date(2026, 1, 7),
    )
    assert total == Decimal("0")
    assert days == 0
