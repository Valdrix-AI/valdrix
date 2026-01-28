import pytest
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException
from app.modules.governance.api.v1.settings.onboard import onboard, OnboardRequest
from app.models.tenant import UserRole, User
from app.shared.core.auth import CurrentUser
from app.shared.core.pricing import PricingTier

@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db

@pytest.fixture
def current_user():
    # Simplest valid CurrentUser
    return CurrentUser(
        id=uuid4(), 
        email="owner@example.com"
    )

@pytest.mark.asyncio
async def test_onboard_success(mock_db, current_user):
    # User does not exist
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    
    req = OnboardRequest(tenant_name="Acme Corp")
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/governance/onboard",
        "raw_path": b"/api/v1/governance/onboard",
        "query_string": b"",
        "headers": [],
        "server": ("testserver", 80),
        "scheme": "http",
    }
    from fastapi import Request
    request_obj = Request(scope=scope)
    
    with patch("app.modules.governance.api.v1.settings.onboard.audit_log") as mock_audit:
        with patch("app.shared.core.rate_limit.get_limiter") as mock_limiter:
            mock_limiter.return_value.limit.return_value = lambda x: x
            
            response = await onboard(request_obj, req, current_user, mock_db)
            
            assert response.status == "onboarded"
            assert response.tenant_id is not None
            mock_db.commit.assert_awaited_once()

@pytest.mark.asyncio
async def test_onboard_already_exists(mock_db, current_user):
    # User already exists
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = MagicMock(spec=User)
    mock_db.execute.return_value = mock_result
    
    req = OnboardRequest(tenant_name="Acme Corp")
    from fastapi import Request
    request_obj = Request(scope={
        "type": "http", "method": "POST", "path": "/onboard", "raw_path": b"/onboard", "query_string": b"", "headers": [], "server": ("testserver", 80), "scheme": "http"
    })
    
    with patch("app.shared.core.rate_limit.get_limiter") as mock_limiter:
        mock_limiter.return_value.limit.return_value = lambda x: x
        with pytest.raises(HTTPException) as exc:
            await onboard(request_obj, req, current_user, mock_db)
    
    assert exc.value.status_code == 400
    assert "Already onboarded" in exc.value.detail

@pytest.mark.asyncio
async def test_onboard_invalid_name(mock_db, current_user):
    req = OnboardRequest(tenant_name="Acme Corp")
    req.tenant_name = "ab" 
    
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    
    from fastapi import Request
    request_obj = Request(scope={
        "type": "http", "method": "POST", "path": "/onboard", "raw_path": b"/onboard", "query_string": b"", "headers": [], "server": ("testserver", 80), "scheme": "http"
    })

    with patch("app.shared.core.rate_limit.get_limiter") as mock_limiter:
        mock_limiter.return_value.limit.return_value = lambda x: x
        with pytest.raises(HTTPException) as exc:
            await onboard(request_obj, req, current_user, mock_db)
    
    assert exc.value.status_code == 400
    assert "at least 3 characters" in exc.value.detail
