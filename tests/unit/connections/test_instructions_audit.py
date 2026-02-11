import pytest
from unittest.mock import patch
from app.shared.connections.instructions import ConnectionInstructionService

@pytest.fixture
def mock_settings():
    with patch("app.shared.connections.instructions.get_settings") as mock:
        mock.return_value.API_URL = "https://api.valdrix.ai/"
        yield mock

def test_get_azure_setup_snippet(mock_settings):
    result = ConnectionInstructionService.get_azure_setup_snippet("tenant-123")
    assert result["issuer"] == "https://api.valdrix.ai"
    assert "tenant:tenant-123" in result["snippet"]
    assert "api://AzureADTokenExchange" in result["audience"]

def test_get_gcp_setup_snippet(mock_settings):
    result = ConnectionInstructionService.get_gcp_setup_snippet("tenant-456")
    assert result["issuer"] == "https://api.valdrix.ai"
    assert result["subject"] == "tenant:tenant-456"
    assert "valdrix-pool" in result["snippet"]
