import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.modules.optimization.domain.service import OptimizationService


@pytest.mark.asyncio
async def test_generate_recommendations_persists_results():
    db = AsyncMock()
    db.add_all = MagicMock()
    db.commit = AsyncMock()

    result = MagicMock()
    scalars_result = MagicMock()
    scalars_result.all.return_value = []
    result.scalars.return_value = scalars_result
    db.execute = AsyncMock(return_value=result)

    recs = [MagicMock(name="rec1"), MagicMock(name="rec2")]

    with patch(
        "app.modules.optimization.domain.strategies.compute_savings.ComputeSavingsStrategy"
    ) as mock_strategy_cls:
        mock_strategy = mock_strategy_cls.return_value
        mock_strategy.analyze = AsyncMock(return_value=recs)

        service = OptimizationService(db)
        with patch.object(service, "_aggregate_usage", AsyncMock(return_value={"avg": 1.0})):
            out = await service.generate_recommendations(uuid4())

    assert out == recs
    db.add_all.assert_called_once_with(recs)
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_generate_recommendations_handles_strategy_error():
    db = AsyncMock()
    db.add_all = MagicMock()
    db.commit = AsyncMock()

    result = MagicMock()
    scalars_result = MagicMock()
    scalars_result.all.return_value = []
    result.scalars.return_value = scalars_result
    db.execute = AsyncMock(return_value=result)

    with patch(
        "app.modules.optimization.domain.strategies.compute_savings.ComputeSavingsStrategy"
    ) as mock_strategy_cls, patch(
        "app.modules.optimization.domain.service.logger"
    ) as mock_logger:
        mock_strategy = mock_strategy_cls.return_value
        mock_strategy.analyze = AsyncMock(side_effect=Exception("boom"))

        service = OptimizationService(db)
        with patch.object(service, "_aggregate_usage", AsyncMock(return_value={"avg": 1.0})):
            out = await service.generate_recommendations(uuid4())

    assert out == []
    db.add_all.assert_not_called()
    db.commit.assert_not_awaited()
    mock_logger.error.assert_called()


@pytest.mark.asyncio
async def test_aggregate_usage_computes_spend_metrics():
    db = AsyncMock()
    result = MagicMock()
    result.scalar.return_value = 720.0
    db.execute = AsyncMock(return_value=result)

    service = OptimizationService(db)
    out = await service._aggregate_usage(uuid4())

    assert out["total_monthly_spend"] == 720.0
    assert out["average_hourly_spend"] == pytest.approx(1.0, rel=1e-6)
    assert out["min_hourly_spend"] == pytest.approx(0.4, rel=1e-6)
    assert out["region"] == "global"
