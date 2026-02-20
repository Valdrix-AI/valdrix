
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys

# -----------------------------------------------------------------------------
# Test: IdleOpenSearchPlugin
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_idle_opensearch_plugin_scan(mock_aws_creds):
    """
    TDD: Verify detecting an Idle OpenSearch Domain (Data exists, but 0 search requests).
    """
    # Mock AWS SDKs globally/lazily
    with patch.dict(sys.modules, {
        "aioboto3": MagicMock(),
        "botocore.exceptions": MagicMock(),
    }):
        from app.modules.optimization.adapters.aws.plugins.search import IdleOpenSearchPlugin
        
        plugin = IdleOpenSearchPlugin()
        assert plugin.category_key == "idle_opensearch_domains"
        
        # Mock Session and Clients
        mock_session = MagicMock()
        mock_opensearch_client = AsyncMock()
        mock_cloudwatch_client = AsyncMock()
        
        # Determine the client based on service_name
        def client_side_effect(service_name, **kwargs):
            ctx = AsyncMock()
            if service_name == "opensearch":
                ctx.__aenter__.return_value = mock_opensearch_client
            elif service_name == "cloudwatch":
                ctx.__aenter__.return_value = mock_cloudwatch_client
            return ctx
            
        mock_session.client.side_effect = client_side_effect

        # Mock Domain List
        mock_domain = {
            "DomainName": "unused-search-domain",
            "DomainId": "12345/unused-search-domain",
            "ARN": "arn:aws:es:us-east-1:12345:domain/unused-search-domain",
            "Created": True,
            "Deleted": False,
            "ClusterConfig": {"InstanceType": "t3.small.search", "InstanceCount": 1}
        }
        mock_opensearch_client.list_domain_names.return_value = {
            "DomainNames": [{"DomainName": "unused-search-domain"}]
        }
        mock_opensearch_client.describe_domain.return_value = {
            "DomainStatus": mock_domain
        }
        
        # Mock Metrics 
        # 1. SearchableDocuments > 0 (indexes exist)
        # 2. SearchRequestRate == 0 (unused)
        
        async def get_metric_statistics_side_effect(**kwargs):
            metric_name = kwargs.get("MetricName")
            if metric_name == "SearchableDocuments":
                return {"Datapoints": [{"Average": 1000}]} # Has data
            elif metric_name == "SearchRequestRate": # or CPUUtilization
                return {"Datapoints": []} # No requests
            return {"Datapoints": []}

        mock_cloudwatch_client.get_metric_statistics.side_effect = get_metric_statistics_side_effect

        zombies = await plugin.scan(
            session=mock_session,
            credentials=mock_aws_creds,
            region="us-east-1"
        )

    assert len(zombies) == 1
    z = zombies[0]
    assert z["resource_id"] == mock_domain["ARN"]
    assert z["resource_type"] == "AWS OpenSearch Domain"
    assert z["action"] == "snapshot_and_delete_opensearch"
    assert "monthly_cost" in z


@pytest.mark.asyncio
async def test_idle_opensearch_plugin_uses_pricing_service(mock_aws_creds):
    with patch.dict(
        sys.modules,
        {
            "aioboto3": MagicMock(),
            "botocore.exceptions": MagicMock(),
        },
    ):
        from app.modules.optimization.adapters.aws.plugins.search import IdleOpenSearchPlugin

        plugin = IdleOpenSearchPlugin()
        mock_session = MagicMock()
        mock_opensearch_client = AsyncMock()
        mock_cloudwatch_client = AsyncMock()

        def client_side_effect(service_name, **kwargs):
            del kwargs
            ctx = AsyncMock()
            if service_name == "opensearch":
                ctx.__aenter__.return_value = mock_opensearch_client
            elif service_name == "cloudwatch":
                ctx.__aenter__.return_value = mock_cloudwatch_client
            return ctx

        mock_session.client.side_effect = client_side_effect
        mock_opensearch_client.list_domain_names.return_value = {
            "DomainNames": [{"DomainName": "unused-search-domain"}]
        }
        mock_opensearch_client.describe_domain.return_value = {
            "DomainStatus": {
                "DomainName": "unused-search-domain",
                "DomainId": "12345/unused-search-domain",
                "ARN": "arn:aws:es:us-east-1:12345:domain/unused-search-domain",
                "Deleted": False,
                "ClusterConfig": {"InstanceType": "t3.small.search", "InstanceCount": 1},
            }
        }

        async def get_metric_statistics_side_effect(**kwargs):
            metric_name = kwargs.get("MetricName")
            if metric_name == "SearchableDocuments":
                return {"Datapoints": [{"Average": 10}]}
            return {"Datapoints": []}

        mock_cloudwatch_client.get_metric_statistics.side_effect = (
            get_metric_statistics_side_effect
        )

        with patch(
            "app.modules.optimization.adapters.aws.plugins.search.PricingService.estimate_monthly_waste",
            return_value=42.0,
        ) as estimate:
            zombies = await plugin.scan(
                session=mock_session,
                credentials=mock_aws_creds,
                region="us-east-1",
            )

    assert len(zombies) == 1
    assert zombies[0]["monthly_cost"] == 42.0
    estimate.assert_called()
