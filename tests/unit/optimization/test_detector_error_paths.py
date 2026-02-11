import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json

from app.modules.optimization.adapters.azure.detector import AzureZombieDetector
from app.modules.optimization.adapters.gcp.detector import GCPZombieDetector


@pytest.mark.asyncio
async def test_azure_detector_missing_credentials_returns_empty():
    plugin = MagicMock()
    plugin.category_key = "test"
    plugin.scan = AsyncMock()

    detector = AzureZombieDetector(region="eastus", credentials={})
    results = await detector._execute_plugin_scan(plugin)

    assert results == []
    plugin.scan.assert_not_called()


def test_azure_detector_initialization_skips_noncanonical_plugins():
    class Plugin:
        def __init__(self, category_key: str):
            self._category_key = category_key

        @property
        def category_key(self) -> str:
            return self._category_key

    with patch(
        "app.modules.optimization.adapters.azure.detector.registry.get_plugins_for_provider",
        return_value=[Plugin("idle_vms"), Plugin("idle_azure_vms")],
    ):
        detector = AzureZombieDetector(region="eastus", credentials={})
        detector._initialize_plugins()
    assert [p.category_key for p in detector.plugins] == ["idle_azure_vms"]


@pytest.mark.asyncio
async def test_azure_detector_handles_none_results():
    creds = {
        "tenant_id": "tenant",
        "client_id": "client",
        "client_secret": "secret",
        "subscription_id": "sub"
    }
    plugin = MagicMock()
    plugin.category_key = "test"
    plugin.scan = AsyncMock(return_value=None)

    with patch("app.modules.optimization.adapters.azure.detector.ClientSecretCredential", return_value=MagicMock()):
        detector = AzureZombieDetector(region="eastus", credentials=creds)
        results = await detector._execute_plugin_scan(plugin)

    assert results == []
    plugin.scan.assert_awaited_once()

@pytest.mark.asyncio
async def test_azure_detector_handles_invalid_result_type():
    creds = {
        "tenant_id": "tenant",
        "client_id": "client",
        "client_secret": "secret",
        "subscription_id": "sub"
    }
    plugin = MagicMock()
    plugin.category_key = "test"
    plugin.scan = AsyncMock(return_value={"not": "a-list"})

    with patch("app.modules.optimization.adapters.azure.detector.ClientSecretCredential", return_value=MagicMock()):
        detector = AzureZombieDetector(region="eastus", credentials=creds)
        results = await detector._execute_plugin_scan(plugin)

    assert results == []

@pytest.mark.asyncio
async def test_azure_detector_connection_initialization_sets_subscription():
    conn = MagicMock()
    conn.subscription_id = "sub-123"
    conn.azure_tenant_id = "tenant"
    conn.client_id = "client"
    conn.client_secret = "secret"

    with patch("app.modules.optimization.adapters.azure.detector.ClientSecretCredential") as mock_cred:
        detector = AzureZombieDetector(region="eastus", connection=conn)

    assert detector.subscription_id == "sub-123"
    mock_cred.assert_called_once_with(
        tenant_id="tenant",
        client_id="client",
        client_secret="secret"
    )

@pytest.mark.asyncio
async def test_azure_detector_missing_subscription_logs_error_path():
    creds = {"tenant_id": "tenant", "client_id": "client", "client_secret": "secret"}
    with patch("app.modules.optimization.adapters.azure.detector.ClientSecretCredential", return_value=MagicMock()):
        detector = AzureZombieDetector(region="eastus", credentials=creds)

    assert detector.subscription_id is None
    plugin = MagicMock()
    plugin.category_key = "test"
    plugin.scan = AsyncMock()
    results = await detector._execute_plugin_scan(plugin)
    assert results == []

@pytest.mark.asyncio
async def test_azure_detector_aexit_closes_resources():
    creds = {
        "tenant_id": "tenant",
        "client_id": "client",
        "client_secret": "secret",
        "subscription_id": "sub"
    }
    with patch("app.modules.optimization.adapters.azure.detector.ClientSecretCredential", return_value=MagicMock()):
        detector = AzureZombieDetector(region="eastus", credentials=creds)

    detector._compute_client = AsyncMock()
    detector._network_client = AsyncMock()
    detector._monitor_client = AsyncMock()
    detector._credential = AsyncMock()

    await detector.__aexit__(None, None, None)

    detector._compute_client.close.assert_awaited_once()
    detector._network_client.close.assert_awaited_once()
    detector._monitor_client.close.assert_awaited_once()
    detector._credential.close.assert_awaited_once()

@pytest.mark.asyncio
async def test_gcp_detector_invalid_service_account_json_blocks_scan():
    plugin = MagicMock()
    plugin.category_key = "test"
    plugin.scan = AsyncMock()

    detector = GCPZombieDetector(
        region="us-central1-a",
        credentials={
            "project_id": "proj",
            "service_account_json": "{bad-json"
        }
    )

    results = await detector._execute_plugin_scan(plugin)
    assert results == []
    plugin.scan.assert_not_called()

def test_gcp_detector_initialization_skips_noncanonical_plugins():
    class Plugin:
        def __init__(self, category_key: str):
            self._category_key = category_key

        @property
        def category_key(self) -> str:
            return self._category_key

    with patch(
        "app.modules.optimization.adapters.gcp.detector.registry.get_plugins_for_provider",
        return_value=[Plugin("idle_instances"), Plugin("idle_gcp_vms")],
    ):
        detector = GCPZombieDetector(region="us-central1-a", credentials={"project_id": "proj"})
        detector._initialize_plugins()
    assert [p.category_key for p in detector.plugins] == ["idle_gcp_vms"]


@pytest.mark.asyncio
async def test_gcp_detector_missing_project_id_returns_empty():
    plugin = MagicMock()
    plugin.category_key = "test"
    plugin.scan = AsyncMock()

    detector = GCPZombieDetector(region="us-central1-a", credentials={})
    results = await detector._execute_plugin_scan(plugin)

    assert results == []
    plugin.scan.assert_not_called()

@pytest.mark.asyncio
async def test_gcp_detector_connection_initialization_parses_json():
    payload = {"project_id": "proj-123", "client_email": "x@y", "private_key": "key"}
    conn = MagicMock()
    conn.project_id = "proj-123"
    conn.service_account_json = json.dumps(payload)

    with patch("google.oauth2.service_account.Credentials.from_service_account_info", return_value=MagicMock()) as mock_creds:
        detector = GCPZombieDetector(region="us-central1-a", connection=conn)

    assert detector.project_id == "proj-123"
    assert detector._credentials_obj is not None
    mock_creds.assert_called_once()

@pytest.mark.asyncio
async def test_gcp_detector_connection_invalid_json_sets_error():
    conn = MagicMock()
    conn.project_id = "proj-123"
    conn.service_account_json = "{bad-json"

    detector = GCPZombieDetector(region="us-central1-a", connection=conn)
    assert detector._credentials_error is not None

    plugin = MagicMock()
    plugin.category_key = "test"
    plugin.scan = AsyncMock()
    results = await detector._execute_plugin_scan(plugin)
    assert results == []
    plugin.scan.assert_not_called()

@pytest.mark.asyncio
async def test_gcp_detector_credentials_project_id_fallback():
    payload = {"project_id": "proj-fallback", "client_email": "x@y", "private_key": "key"}
    with patch("google.oauth2.service_account.Credentials.from_service_account_info", return_value=MagicMock()):
        detector = GCPZombieDetector(
            region="us-central1-a",
            credentials={"service_account_json": json.dumps(payload)}
        )

    assert detector.project_id == "proj-fallback"

@pytest.mark.asyncio
async def test_gcp_detector_handles_invalid_result_type():
    plugin = MagicMock()
    plugin.category_key = "test"
    plugin.scan = AsyncMock(return_value={"bad": "type"})

    detector = GCPZombieDetector(region="us-central1-a", credentials={"project_id": "proj"})
    results = await detector._execute_plugin_scan(plugin)

    assert results == []
