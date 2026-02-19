import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import sys

# -----------------------------------------------------------------------------
# Test: IdleAzureOpenAIPlugin
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_idle_azure_openai_plugin_scan(mock_azure_creds):
    """
    TDD: Verify detecting an Azure OpenAI account with deployments that have 0 inference usage.
    """
    # Mock Azure SDKs globally for this test context due to top-level imports
    with patch.dict(sys.modules, {
        "azure.mgmt.cognitiveservices": MagicMock(),
        "azure.mgmt.search": MagicMock(),
        "azure.mgmt.monitor": MagicMock(),
    }):
        # Import INSIDE the patch context to avoid ModuleNotFoundError
        from app.modules.optimization.adapters.azure.plugins.ai import IdleAzureOpenAIPlugin
        
        plugin = IdleAzureOpenAIPlugin()
        assert plugin.category_key == "idle_azure_openai"

    # Mock Cognitive Services Account
    mock_account = MagicMock()
    mock_account.id = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.CognitiveServices/accounts/openai-test"
    mock_account.name = "openai-test"
    mock_account.type = "Microsoft.CognitiveServices/accounts"
    mock_account.kind = "OpenAI"
    mock_account.location = "eastus"

    # Mock Deployments
    mock_deployment = MagicMock()
    mock_deployment.id = f"{mock_account.id}/deployments/gpt-4-deployment"
    mock_deployment.name = "gpt-4-deployment"
    mock_deployment.properties = MagicMock()
    mock_deployment.properties.model.name = "gpt-4"
    mock_deployment.properties.model.version = "0613"

    # Mock Clients
    mock_mgmt_client = MagicMock()
    mock_mgmt_client.accounts.list.return_value = [mock_account]
    mock_mgmt_client.deployments.list.return_value = [mock_deployment]

    # Mock Monitor Client (Metrics)
    mock_monitor_client = MagicMock()
    mock_metrics_data = MagicMock()
    mock_metrics_data.value = [
        MagicMock(timeseries=[MagicMock(data=[MagicMock(total=0)])]) # 0 processed tokens
    ]
    mock_monitor_client.metrics.list.return_value = mock_metrics_data

    with patch("app.modules.optimization.adapters.azure.plugins.ai.CognitiveServicesManagementClient", return_value=mock_mgmt_client), \
         patch("app.modules.optimization.adapters.azure.plugins.ai.MonitorManagementClient", return_value=mock_monitor_client):
        
        zombies = await plugin.scan(
            session="sub-1",
            credentials=mock_azure_creds
        )

    assert len(zombies) == 1
    z = zombies[0]
    assert z["resource_id"] == mock_deployment.id
    assert z["resource_type"] == "Azure OpenAI Deployment"
    assert z["action"] == "delete_openai_deployment"
    # Ensure cost estimation logic is triggered (e.g. non-zero basic cost for provisioned or just based on hourly fixed?)
    # For TDD, we accept any cost >= 0, but checking existence of key is important.
    assert "monthly_cost" in z

# -----------------------------------------------------------------------------
# Test: IdleAISearchPlugin
# -----------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_idle_ai_search_plugin_scan(mock_azure_creds):
    """
    TDD: Verify detecting an Azure AI Search service with 0 search requests.
    """
    with patch.dict(sys.modules, {
        "azure.mgmt.cognitiveservices": MagicMock(),
        "azure.mgmt.search": MagicMock(),
        "azure.mgmt.monitor": MagicMock(),
    }):
        from app.modules.optimization.adapters.azure.plugins.ai import IdleAISearchPlugin
        
        plugin = IdleAISearchPlugin()
        assert plugin.category_key == "idle_ai_search"

    # Mock Search Service
    mock_service = MagicMock()
    mock_service.id = "/subscriptions/sub-1/resourceGroups/rg-1/providers/Microsoft.Search/searchServices/search-test"
    mock_service.name = "search-test"
    mock_service.location = "eastus"
    mock_service.sku.name = "standard" # Costs money

    # Mock Clients
    mock_mgmt_client = MagicMock()
    mock_mgmt_client.services.list_by_subscription.return_value = [mock_service]

    mock_monitor_client = MagicMock()
    mock_metrics_data = MagicMock()
    mock_metrics_data.value = [
        MagicMock(timeseries=[MagicMock(data=[MagicMock(total=0)])]) # 0 search queries
    ]
    mock_monitor_client.metrics.list.return_value = mock_metrics_data

    with patch("app.modules.optimization.adapters.azure.plugins.ai.SearchManagementClient", return_value=mock_mgmt_client), \
         patch("app.modules.optimization.adapters.azure.plugins.ai.MonitorManagementClient", return_value=mock_monitor_client):

        zombies = await plugin.scan(
            session="sub-1",
            credentials=mock_azure_creds
        )

    assert len(zombies) == 1
    z = zombies[0]
    assert z["resource_id"] == mock_service.id
    assert z["resource_type"] == "Azure AI Search Service"
    assert z["sku"] == "standard"
    assert z["monthly_cost"] > 0 # Standard SKU has base cost
    assert z["confidence_score"] > 0.9

