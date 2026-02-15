import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from app.modules.governance.domain.jobs.handlers.finops import FinOpsAnalysisHandler


@pytest.mark.asyncio
async def test_finops_analysis_handler():
    """Test FinOps analysis background job."""
    handler = FinOpsAnalysisHandler()
    job = MagicMock(tenant_id=uuid4(), payload={})
    db = MagicMock()
    aws_conn = MagicMock(id=uuid4(), provider="aws")
    aws_result = MagicMock()
    aws_result.scalars.return_value.all.return_value = [aws_conn]
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(
        side_effect=[
            aws_result,  # AWS
            empty_result,  # Azure
            empty_result,  # GCP
            empty_result,  # SaaS
            empty_result,  # License
            empty_result,  # Platform
            empty_result,  # Hybrid
        ]
    )

    with (
        patch(
            "app.modules.governance.domain.jobs.handlers.finops.AdapterFactory"
        ) as mock_factory,
        patch("app.modules.governance.domain.jobs.handlers.finops.LLMFactory.create"),
        patch(
            "app.modules.governance.domain.jobs.handlers.finops.FinOpsAnalyzer"
        ) as MockAnalyzer,
    ):
        adapter = MagicMock()
        usage_summary = MagicMock()
        usage_summary.records = [MagicMock()]
        adapter.get_daily_costs = AsyncMock(return_value=usage_summary)
        mock_factory.get_adapter.return_value = adapter

        analyzer = MockAnalyzer.return_value
        analyzer.analyze = AsyncMock(
            return_value={"insights": [], "recommendations": []}
        )

        res = await handler.execute(job, db)

        assert res["status"] == "completed"
        assert res["analysis_runs"] == 1
        analyzer.analyze.assert_awaited()
