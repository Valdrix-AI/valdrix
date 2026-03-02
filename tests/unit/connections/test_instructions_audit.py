import pytest
from unittest.mock import patch
from app.shared.connections.instructions import ConnectionInstructionService


@pytest.fixture
def mock_settings():
    with patch("app.shared.connections.instructions.get_settings") as mock:
        mock.return_value.API_URL = "https://api.valdrics.ai/"
        yield mock


def test_get_azure_setup_snippet(mock_settings):
    result = ConnectionInstructionService.get_azure_setup_snippet("tenant-123")
    assert result["issuer"] == "https://api.valdrics.ai"
    assert "tenant:tenant-123" in result["snippet"]
    assert "api://AzureADTokenExchange" in result["audience"]


def test_get_gcp_setup_snippet(mock_settings):
    result = ConnectionInstructionService.get_gcp_setup_snippet("tenant-456")
    assert result["issuer"] == "https://api.valdrics.ai"
    assert result["subject"] == "tenant:tenant-456"
    assert "valdrics-pool" in result["snippet"]


def test_get_saas_setup_snippet(mock_settings):
    result = ConnectionInstructionService.get_saas_setup_snippet("tenant-789")
    assert result["subject"] == "tenant:tenant-789"
    assert "settings/connections/saas" in result["snippet"]
    assert "sample_feed" in result
    assert "native_connectors" in result
    assert isinstance(result["native_connectors"], list)
    assert result["native_connectors"][0]["vendor"] == "stripe"
    assert "manual_feed_schema" in result


def test_get_license_setup_snippet(mock_settings):
    result = ConnectionInstructionService.get_license_setup_snippet("tenant-901")
    assert result["subject"] == "tenant:tenant-901"
    assert "settings/connections/license" in result["snippet"]
    assert "sample_feed" in result
    assert "native_connectors" in result
    assert isinstance(result["native_connectors"], list)
    assert result["native_connectors"][0]["vendor"] == "microsoft_365"
    assert any(
        connector["vendor"] == "google_workspace"
        for connector in result["native_connectors"]
    )
    assert any(
        connector["vendor"] == "salesforce"
        for connector in result["native_connectors"]
    )
    assert "manual_feed_schema" in result
