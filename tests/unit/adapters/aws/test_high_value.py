import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from app.modules.optimization.adapters.aws.plugins.high_value import (
    IdleEksPlugin,
    IdleElastiCachePlugin,
    IdleSageMakerNotebooksPlugin
)

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

@pytest.fixture
def mock_pricing():
    with patch("app.modules.optimization.adapters.aws.plugins.high_value.PricingService") as mock:
        mock.estimate_monthly_waste.return_value = 100.0
        yield mock

@pytest.mark.asyncio
async def test_idle_eks_plugin_scan_success(mock_session):
    """Test EKS plugin finds clusters with 0 nodes."""
    plugin = IdleEksPlugin()
    
    # Client must handle both sync (get_paginator) and async (describe_cluster)
    mock_eks = MagicMock()
    mock_eks.describe_cluster = AsyncMock()
    mock_eks.describe_nodegroup = AsyncMock()
    mock_session.client.return_value.__aenter__.return_value = mock_eks
    
    # Mock list_clusters paginator
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = AsyncIterator([{"clusters": ["cluster-1"]}])
    mock_eks.get_paginator.side_effect = lambda name: mock_paginator
    
    # Mock describe_cluster
    mock_eks.describe_cluster.return_value = {"cluster": {"arn": "arn:eks:123"}}
    
    # Mock list_nodegroups paginator (0 nodes)
    mock_ng_paginator = MagicMock()
    mock_ng_paginator.paginate.return_value = AsyncIterator([{"nodegroups": ["ng-1"]}])
    
    mock_eks.get_paginator.side_effect = [mock_paginator, mock_ng_paginator]
    mock_eks.describe_nodegroup.return_value = {"nodegroup": {"scalingConfig": {"desiredSize": 0}}}
    
    results = await plugin.scan(mock_session, "us-east-1")
    
    assert len(results) == 1
    assert results[0]["resource_id"] == "cluster-1"

@pytest.mark.asyncio
async def test_idle_elasticache_plugin_scan_success(mock_session, mock_pricing):
    """Test ElastiCache plugin finds idle clusters via CloudWatch."""
    plugin = IdleElastiCachePlugin()
    
    mock_ec = MagicMock()
    mock_ec.get_paginator = MagicMock()
    mock_cw = MagicMock()
    mock_cw.get_metric_statistics = AsyncMock()
    
    mock_session.client.return_value.__aenter__.side_effect = [mock_ec, mock_cw]
    
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = AsyncIterator([{
        "CacheClusters": [{
            "CacheClusterId": "cache-1",
            "CacheNodeType": "cache.t3.micro",
            "Engine": "redis"
        }]
    }])
    mock_ec.get_paginator.return_value = mock_paginator
    mock_cw.get_metric_statistics.return_value = {"Datapoints": [{"Average": 1.5}]}
    
    results = await plugin.scan(mock_session, "us-east-1")
    
    assert len(results) == 1
    assert results[0]["resource_id"] == "cache-1"

@pytest.mark.asyncio
async def test_idle_sagemaker_notebooks_plugin_scan_success(mock_session, mock_pricing):
    """Test SageMaker plugin finds old notebooks."""
    plugin = IdleSageMakerNotebooksPlugin()
    
    mock_sm = MagicMock()
    mock_sm.get_paginator = MagicMock()
    mock_sm.describe_notebook_instance = AsyncMock()
    mock_session.client.return_value.__aenter__.return_value = mock_sm
    
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = AsyncIterator([{
        "NotebookInstances": [{
            "NotebookInstanceName": "notebook-1",
            "NotebookInstanceStatus": "InService",
            "InstanceType": "ml.t3.medium"
        }]
    }])
    mock_sm.get_paginator.return_value = mock_paginator
    
    old_date = datetime.now(timezone.utc) - timedelta(days=10)
    mock_sm.describe_notebook_instance.return_value = {"LastModifiedTime": old_date}
    
    results = await plugin.scan(mock_session, "us-east-1")
    
    assert len(results) == 1
    assert results[0]["resource_id"] == "notebook-1"

@pytest.mark.asyncio
async def test_plugins_cur_path():
    """Test CUR path."""
    plugin = IdleEksPlugin()
    mock_records = [{"line_item_product_code": "AmazonEKS"}]
    with patch("app.shared.analysis.cur_usage_analyzer.CURUsageAnalyzer") as mock_analyzer_cls:
        mock_analyzer = MagicMock()
        mock_analyzer.find_idle_eks_clusters.return_value = [{"resource_id": "cur-eks"}]
        mock_analyzer_cls.return_value = mock_analyzer
        results = await plugin.scan(None, "us-east-1", cur_records=mock_records)
        assert len(results) == 1
