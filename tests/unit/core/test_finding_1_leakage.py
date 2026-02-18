import pytest
from fastapi import Request
from app.main import value_error_handler
from unittest.mock import patch, MagicMock

@pytest.mark.asyncio
async def test_value_error_leakage_production():
    """
    Finding #1: Verify ValueError is sanitized in production.
    """
    mock_request = Request({"type": "http", "method": "GET", "path": "/test-leak", "headers": []})
    exc = ValueError("Secret: hunter2")
    
    with patch("app.shared.core.config.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.ENVIRONMENT = "production"
        mock_get_settings.return_value = mock_settings
        
        response = await value_error_handler(mock_request, exc)
        content = response.body.decode()
        assert "Invalid request parameters" in content
        assert "hunter2" not in content

@pytest.mark.asyncio
async def test_value_error_leakage_development():
    """
    Finding #1: Verify ValueError is NOT sanitized in development.
    """
    mock_request = Request({"type": "http", "method": "GET", "path": "/test-leak", "headers": []})
    exc = ValueError("Secret: hunter2")
    
    with patch("app.shared.core.config.get_settings") as mock_get_settings:
        mock_settings = MagicMock()
        mock_settings.ENVIRONMENT = "development"
        mock_get_settings.return_value = mock_settings
        
        response = await value_error_handler(mock_request, exc)
        content = response.body.decode()
        assert "Secret: hunter2" in content
