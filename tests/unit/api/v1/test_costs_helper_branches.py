from __future__ import annotations

from datetime import datetime, timedelta, timezone, date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.background_job import JobStatus
from app.modules.reporting.api.v1 import costs as costs_api
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.pricing import PricingTier


def _user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email=f"member-{uuid4().hex[:8]}@example.com",
        tenant_id=uuid4(),
        role=UserRole.MEMBER,
        tier=PricingTier.PRO,
    )


@pytest.mark.asyncio
async def test_get_or_create_unit_settings_returns_existing() -> None:
    existing = SimpleNamespace(id=uuid4())
    db = MagicMock()
    db.scalar = AsyncMock(return_value=existing)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    out = await costs_api._get_or_create_unit_settings(db, uuid4())

    assert out is existing
    db.add.assert_not_called()
    db.commit.assert_not_awaited()
    db.refresh.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_or_create_unit_settings_creates_defaults() -> None:
    db = MagicMock()
    db.scalar = AsyncMock(return_value=None)
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    tenant_id = uuid4()
    out = await costs_api._get_or_create_unit_settings(db, tenant_id)

    assert out.tenant_id == tenant_id
    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(out)


@pytest.mark.asyncio
async def test_window_total_cost_returns_zero_for_none_scalar() -> None:
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    total = await costs_api._window_total_cost(
        db=db,
        tenant_id=uuid4(),
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 2),
        provider="aws",
    )

    assert total == Decimal("0")


@pytest.mark.asyncio
async def test_get_ingestion_sla_includes_dead_letter_and_duration_filters() -> None:
    user = _user()
    now = datetime.now(timezone.utc)

    jobs = [
        SimpleNamespace(
            status=JobStatus.COMPLETED.value,
            started_at=now,
            completed_at=now + timedelta(seconds=120),
            result={"ingested": 10.7},
        ),
        SimpleNamespace(
            status=JobStatus.COMPLETED.value,
            started_at=now,
            completed_at=now
            - timedelta(seconds=10),  # negative duration should be ignored
            result={"ingested": "bad"},
        ),
        SimpleNamespace(
            status=JobStatus.DEAD_LETTER.value,
            started_at=now,
            completed_at=now + timedelta(seconds=30),
            result={},
        ),
        SimpleNamespace(
            status=JobStatus.FAILED.value,
            started_at=None,
            completed_at=None,
            result=None,
        ),
    ]

    result = MagicMock()
    scalars = MagicMock()
    scalars.all.return_value = jobs
    result.scalars.return_value = scalars

    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    response = await costs_api.get_ingestion_sla(
        window_hours=6,
        target_success_rate_percent=20.0,
        user=user,
        db=db,
    )

    assert response.total_jobs == 4
    assert response.successful_jobs == 2
    assert response.failed_jobs == 2
    assert response.records_ingested == 10
    assert response.avg_duration_seconds == 75.0
    assert response.p95_duration_seconds == 120.0
    assert response.meets_sla is True
    assert response.latest_completed_at is not None


def test_build_provider_recency_summary_counts_recent_stale_and_never() -> None:
    now = datetime.now(timezone.utc)
    connections = [
        SimpleNamespace(status="active", last_ingested_at=now - timedelta(hours=2)),
        SimpleNamespace(status="active", last_ingested_at=now - timedelta(hours=96)),
        SimpleNamespace(status="active", last_ingested_at=None),
        SimpleNamespace(status="pending", last_ingested_at=now - timedelta(hours=1)),
    ]

    summary = costs_api._build_provider_recency_summary(
        "aws",
        connections,
        now=now,
        recency_target_hours=48,
    )

    assert summary.provider == "aws"
    assert summary.active_connections == 3
    assert summary.recently_ingested == 1
    assert summary.stale_connections == 1
    assert summary.never_ingested == 1
    assert summary.meets_recency_target is False
