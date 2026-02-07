import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.modules.optimization.adapters.aws.plugins.analytics import IdleSageMakerPlugin

class AsyncIterator:
    def __init__(self, items):
        self.items = items
        self.cursor = 0
    def __aiter__(self):
        return self
    async def __anext__(self):
        if self.cursor >= len(self.items):
            raise StopAsyncIteration
        item = self.items[self.cursor]
        self.cursor += 1
        return item

@pytest.fixture
def mock_session():
    session = MagicMock()
    return_mock = MagicMock()
    return_mock.__aenter__ = AsyncMock()
    return_mock.__aexit__ = AsyncMock()
    session.client.return_value = return_mock
    return session

@pytest.mark.asyncio
async def test_idle_sagemaker_plugin_scan_success(mock_session):
    """Test SageMaker plugin finds idle endpoints via CloudWatch."""
    plugin = IdleSageMakerPlugin()
    
    mock_sm = MagicMock()
    mock_sm.get_paginator = MagicMock()
    mock_cw = MagicMock()
    mock_cw.get_metric_statistics = AsyncMock()
    
    # Session returns SM then CW
    mock_session.client.return_value.__aenter__.side_effect = [mock_sm, mock_cw]
    
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = AsyncIterator([{
        "Endpoints": [{"EndpointName": "ep-1"}]
    }])
    mock_sm.get_paginator.return_value = mock_paginator
    
    # 0 invocations = idle
    mock_cw.get_metric_statistics.return_value = {"Datapoints": [{"Sum": 0}]}
    
    with patch("app.modules.reporting.domain.pricing.service.PricingService.estimate_monthly_waste") as mock_price:
        mock_price.return_value = 50.0
        results = await plugin.scan(mock_session, "us-east-1")
    
    assert len(results) == 1
    assert results[0]["resource_id"] == "ep-1"
    assert results[0]["confidence_score"] == 0.98

@pytest.mark.asyncio
async def test_sagemaker_plugin_cur_path():
    """Test SageMaker plugin CUR path."""
    plugin = IdleSageMakerPlugin()
    mock_records = [{"line_item_resource_id": "cur-sm"}]
    with patch("app.shared.analysis.cur_usage_analyzer.CURUsageAnalyzer") as mock_analyzer_cls:
        mock_analyzer = MagicMock()
        mock_analyzer.find_idle_sagemaker_endpoints.return_value = [{"resource_id": "cur-sm"}]
        mock_analyzer_cls.return_value = mock_analyzer
        
        results = await plugin.scan(None, "us-east-1", cur_records=mock_records)
        assert len(results) == 1
        assert results[0]["resource_id"] == "cur-sm"
