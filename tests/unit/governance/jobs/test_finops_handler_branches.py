from datetime import date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.governance.domain.jobs.handlers.finops import (
    FinOpsAnalysisHandler,
    _as_datetime,
    _normalize_rows,
)


def _scalar_result(items: list[object]) -> MagicMock:
    result = MagicMock()
    result.scalars.return_value.all.return_value = items
    return result


def test_as_datetime_handles_date_and_naive_datetime() -> None:
    naive = datetime(2026, 1, 1, 12, 0, 0)
    normalized = _as_datetime(naive)
    assert normalized.tzinfo is not None

    from_date = _as_datetime(date(2026, 1, 2))
    assert from_date.tzinfo is not None
    assert from_date.date().isoformat() == "2026-01-02"


def test_normalize_rows_skips_non_positive_and_normalizes_tags() -> None:
    rows = [
        {"cost_usd": 0, "service": "skip"},
        {
            "cost_usd": "12.5",
            "amount_raw": "3",
            "currency": "USD",
            "service": "Compute",
            "region": "us-east-1",
            "usage_type": "hours",
            "timestamp": "2026-01-01T00:00:00Z",
            "tags": "invalid",
        },
    ]
    records = _normalize_rows(rows)
    assert len(records) == 1
    assert records[0].amount == Decimal("12.5")
    assert records[0].amount_raw == Decimal("3")
    assert records[0].tags == {}


@pytest.mark.asyncio
async def test_execute_requires_tenant_id() -> None:
    handler = FinOpsAnalysisHandler()
    job = MagicMock(tenant_id=None, payload={})
    db = MagicMock()

    with pytest.raises(ValueError):
        await handler.execute(job, db)


@pytest.mark.asyncio
async def test_execute_skips_when_no_connections() -> None:
    handler = FinOpsAnalysisHandler()
    job = MagicMock(tenant_id=uuid4(), payload={})
    db = MagicMock()
    empty = _scalar_result([])
    db.execute = AsyncMock(
        side_effect=[empty, empty, empty, empty, empty, empty, empty]
    )

    result = await handler.execute(job, db)
    assert result == {"status": "skipped", "reason": "no_connections"}


@pytest.mark.asyncio
async def test_execute_non_aws_path_and_exception_continue() -> None:
    handler = FinOpsAnalysisHandler()
    job = MagicMock(tenant_id=uuid4(), payload={})
    db = MagicMock()

    aws_empty = _scalar_result([])
    azure_conn = MagicMock(provider="azure")
    gcp_conn = MagicMock(provider="gcp")
    azure_result = _scalar_result([azure_conn])
    gcp_result = _scalar_result([gcp_conn])
    saas_empty = _scalar_result([])
    license_empty = _scalar_result([])
    platform_empty = _scalar_result([])
    hybrid_empty = _scalar_result([])
    db.execute = AsyncMock(
        side_effect=[
            aws_empty,
            azure_result,
            gcp_result,
            saas_empty,
            license_empty,
            platform_empty,
            hybrid_empty,
        ]
    )

    azure_adapter = MagicMock()
    azure_adapter.get_cost_and_usage = AsyncMock(
        return_value=[
            {
                "timestamp": "2026-01-03T00:00:00Z",
                "cost_usd": "14.2",
                "service": "VM",
                "region": "westeurope",
                "usage_type": "compute",
                "tags": {"env": "dev"},
            },
            {"timestamp": "2026-01-03T00:00:00Z", "cost_usd": 0},
        ]
    )
    gcp_adapter = MagicMock()
    gcp_adapter.get_cost_and_usage = AsyncMock(
        side_effect=RuntimeError("provider failure")
    )

    analyzer = MagicMock()
    analyzer.analyze = AsyncMock(return_value={"insights": ["ok"]})

    with (
        patch(
            "app.modules.governance.domain.jobs.handlers.finops.AdapterFactory.get_adapter",
            side_effect=[azure_adapter, gcp_adapter],
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.finops.LLMFactory.create",
            return_value=MagicMock(),
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.finops.FinOpsAnalyzer",
            return_value=analyzer,
        ),
    ):
        result = await handler.execute(job, db)

    assert result["status"] == "completed"
    assert result["analysis_runs"] == 1
    assert result["providers_analyzed"] == ["azure"]
    assert result["analysis_length"] > 0
    analyzer.analyze.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_skips_when_no_analysis_payloads() -> None:
    handler = FinOpsAnalysisHandler()
    job = MagicMock(tenant_id=uuid4(), payload={})
    db = MagicMock()

    aws_conn = MagicMock(provider="aws")
    aws_result = _scalar_result([aws_conn])
    empty = _scalar_result([])
    db.execute = AsyncMock(
        side_effect=[aws_result, empty, empty, empty, empty, empty, empty]
    )

    usage_summary = MagicMock()
    usage_summary.records = [MagicMock()]
    aws_adapter = MagicMock()
    aws_adapter.get_daily_costs = AsyncMock(return_value=usage_summary)

    analyzer = MagicMock()
    analyzer.analyze = AsyncMock(return_value="non-dict-result")

    with (
        patch(
            "app.modules.governance.domain.jobs.handlers.finops.AdapterFactory.get_adapter",
            return_value=aws_adapter,
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.finops.LLMFactory.create",
            return_value=MagicMock(),
        ),
        patch(
            "app.modules.governance.domain.jobs.handlers.finops.FinOpsAnalyzer",
            return_value=analyzer,
        ),
    ):
        result = await handler.execute(job, db)

    assert result == {"status": "skipped", "reason": "no_cost_data"}
