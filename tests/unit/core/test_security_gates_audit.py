import pytest
from unittest.mock import MagicMock, patch
from fastapi import HTTPException
from uuid import uuid4
from app.shared.core.auth import requires_role, CurrentUser
from app.models.tenant import UserRole
from app.shared.core.dependencies import requires_feature
from app.shared.core.pricing import PricingTier

@pytest.fixture
def member_user():
    return CurrentUser(id=uuid4(), email="mem@ex.com", role=UserRole.MEMBER, tier=PricingTier.STARTER)

@pytest.fixture
def admin_user():
    return CurrentUser(id=uuid4(), email="adm@ex.com", role=UserRole.ADMIN, tier=PricingTier.PRO)

@pytest.fixture
def owner_user():
    return CurrentUser(id=uuid4(), email="own@ex.com", role=UserRole.OWNER, tier=PricingTier.ENTERPRISE)

@pytest.mark.asyncio
async def test_requires_role_enforcement(member_user, admin_user, owner_user):
    # Test Member accessing Admin-only
    checker = requires_role("admin")
    with pytest.raises(HTTPException) as exc:
        checker(member_user)
    assert exc.value.status_code == 403

    # Test Admin accessing Admin-only
    assert checker(admin_user) == admin_user

    # Test Owner accessing Admin-only (Bypass)
    assert checker(owner_user) == owner_user

@pytest.mark.asyncio
async def test_requires_role_hierarchy(member_user):
    # Member accessing Member-only should pass
    checker = requires_role("member")
    assert checker(member_user) == member_user
    
    # Member accessing Owner-only should fail
    checker = requires_role("owner")
    with pytest.raises(HTTPException) as exc:
        checker(member_user)
    assert exc.value.status_code == 403

@pytest.mark.asyncio
async def test_requires_feature_enforcement(member_user, owner_user):
    # Assuming "sso" is an Enterprise feature
    # We might need to mock is_feature_enabled if we don't want to rely on hardcoded pricing logic
    # But relying on the real logic is better for an audit.
    
    from unittest.mock import patch
    
    # Mocking is_feature_enabled to test the dependency wrapper primarily
    with patch("app.shared.core.dependencies.is_feature_enabled") as mock_check:
        # Case 1: Feature Disabled for Tier
        mock_check.return_value = False
        checker = requires_feature("advanced_security")
        
        with pytest.raises(HTTPException) as exc:
            await checker(member_user)
        assert exc.value.status_code == 403
        assert "requires an upgrade" in exc.value.detail
        
        # Case 2: Feature Enabled for Tier
        mock_check.return_value = True
        result = await checker(owner_user)
        assert result == owner_user

@pytest.mark.asyncio
async def test_get_analyzer_and_provider_dependency():
    """Verify get_analyzer and get_llm_provider dependencies."""
    from app.shared.core.dependencies import get_llm_provider, get_analyzer
    
    with patch("app.shared.core.dependencies.get_settings") as mock_settings:
        mock_settings.return_value = MagicMock()
        mock_settings.return_value.LLM_PROVIDER = "openai"
        
        provider = get_llm_provider()
        assert provider == "openai"
        
        with patch("app.shared.llm.factory.LLMFactory.create") as mock_create:
            mock_create.return_value = MagicMock()
            analyzer = get_analyzer(provider="openai")
            assert analyzer is not None
            mock_create.assert_called_with("openai")
