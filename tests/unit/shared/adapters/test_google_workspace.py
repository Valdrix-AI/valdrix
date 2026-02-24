import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime, timezone
from app.shared.adapters.license import LicenseAdapter
from app.shared.core.credentials import LicenseCredentials
from app.shared.core.exceptions import UnsupportedVendorError
from pydantic import SecretStr

@pytest.fixture
def google_credentials():
    return LicenseCredentials(
        vendor="google_workspace",
        auth_method="api_key",
        api_key=SecretStr("test-token"),
        connector_config={
            "sku_prices": {"Google-Apps-For-Business": 12.0},
            "currency": "USD"
        }
    )

@pytest.mark.asyncio
async def test_verify_google_workspace_success(google_credentials):
    adapter = LicenseAdapter(google_credentials)
    
    with patch.object(adapter, "_get_json", AsyncMock(return_value={"id": "cust-1"})) as mock_get:
        result = await adapter.verify_connection()
        
    assert result is True
    mock_get.assert_called_once()
    assert "directory/v1/customer/my_customer" in mock_get.call_args[0][0]

@pytest.mark.asyncio
async def test_stream_google_workspace_costs(google_credentials):
    adapter = LicenseAdapter(google_credentials)
    
    mock_payload = {
        "totalUnits": 100
    }
    
    start_date = datetime(2024, 1, 1, tzinfo=timezone.utc)
    end_date = datetime(2024, 1, 31, tzinfo=timezone.utc)

    with patch.object(adapter, "_get_json", AsyncMock(return_value=mock_payload)):
        records = []
        async for record in adapter.stream_cost_and_usage(start_date, end_date):
            records.append(record)
            
    assert len(records) > 0
    assert records[0]["usage_amount"] == 100.0
    assert records[0]["cost_usd"] == 1200.0 # 100 * 12
    assert records[0]["service"] == "Google-Apps-For-Business"

@pytest.mark.asyncio
async def test_revoke_license_success(google_credentials):
    adapter = LicenseAdapter(google_credentials)
    
    with patch("app.shared.core.http.get_http_client") as mock_get_client:
        mock_client = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 204
        mock_client.delete.return_value = mock_resp
        mock_get_client.return_value = mock_client
        
        result = await adapter.revoke_license("user-1", sku_id="Google-Apps-For-Business")
        
    assert result is True
    mock_client.delete.assert_called_once()
    assert "user/user-1" in mock_client.delete.call_args[0][0]

@pytest.mark.asyncio
async def test_revoke_license_not_implemented(google_credentials):
    google_credentials.vendor = "unknown"
    adapter = LicenseAdapter(google_credentials)
    
    with pytest.raises(UnsupportedVendorError):
        await adapter.revoke_license("user-1")


@pytest.mark.asyncio
async def test_verify_github_native_success():
    credentials = LicenseCredentials(
        vendor="github",
        auth_method="api_key",
        api_key=SecretStr("gh-token"),
        connector_config={},
    )
    adapter = LicenseAdapter(credentials)

    with patch.object(adapter, "_get_json", AsyncMock(return_value={"login": "octocat"})) as mock_get:
        result = await adapter.verify_connection()

    assert result is True
    mock_get.assert_called_once()
    assert "api.github.com/user" in mock_get.call_args[0][0]


@pytest.mark.asyncio
async def test_verify_salesforce_requires_instance_url():
    credentials = LicenseCredentials(
        vendor="salesforce",
        auth_method="oauth",
        api_key=SecretStr("sf-token"),
        connector_config={},
    )
    adapter = LicenseAdapter(credentials)

    result = await adapter.verify_connection()

    assert result is False
    assert adapter.last_error is not None
    assert "salesforce_instance_url" in adapter.last_error
