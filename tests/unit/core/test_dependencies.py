"""
Tests for app/shared/core/dependencies.py - FastAPI dependencies
"""
import pytest
from unittest.mock import AsyncMock, patch
from uuid import uuid4
from fastapi import HTTPException, status

from app.shared.core.dependencies import get_llm_provider, get_analyzer, requires_feature
from app.shared.core.auth import CurrentUser, requires_role
from app.shared.core.pricing import PricingTier, FeatureFlag


class TestDependencies:
    """Test FastAPI dependency functions."""

    def test_get_llm_provider(self):
        """Test getting LLM provider from settings."""
        with patch("app.shared.core.dependencies.get_settings") as mock_settings:
            mock_settings.return_value.LLM_PROVIDER = "openai"
            
            provider = get_llm_provider()
            assert provider == "openai"
            mock_settings.assert_called_once()

    def test_get_analyzer(self):
        """Test getting FinOps analyzer."""
        with patch("app.shared.core.dependencies.get_llm_provider", return_value="openai"):
            with patch("app.shared.core.dependencies.LLMFactory.create") as mock_create:
                mock_llm = AsyncMock()
                mock_create.return_value = mock_llm
                
                with patch("app.shared.core.dependencies.FinOpsAnalyzer") as mock_analyzer_class:
                    mock_analyzer = AsyncMock()
                    mock_analyzer_class.return_value = mock_analyzer
                    
                    analyzer = get_analyzer()
                    
                    assert analyzer == mock_analyzer
                    mock_analyzer_class.assert_called_once_with(mock_llm)

    @pytest.mark.asyncio
    async def test_requires_feature_enabled(self):
        """Test feature dependency when feature is enabled."""
        mock_user = CurrentUser(
            id=uuid4(),
            email="user@example.com",
            tenant_id=uuid4(),
            role="member",
            tier="growth"
        )
        
        with patch("app.shared.core.dependencies.is_feature_enabled", return_value=True):
            # Should not raise exception
            # Dependency functions return the user, not None, when successful
            feature_checker = requires_feature("advanced_analytics")
            result = await feature_checker(mock_user)
            assert result == mock_user

    @pytest.mark.asyncio
    async def test_requires_feature_disabled(self):
        """Test feature dependency when feature is disabled."""
        mock_user = CurrentUser(
            id=uuid4(),
            email="user@example.com",
            tenant_id=uuid4(),
            role="member",
            tier="starter"
        )
        
        with patch("app.shared.core.dependencies.is_feature_enabled", return_value=False):
            with pytest.raises(HTTPException) as exc:
                feature_checker = requires_feature("advanced_analytics")
                await feature_checker(mock_user)
            
            assert exc.value.status_code == status.HTTP_403_FORBIDDEN
            assert "advanced_analytics" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_requires_feature_with_enum(self):
        """Test feature dependency with FeatureFlag enum."""
        mock_user = CurrentUser(
            id=uuid4(),
            email="user@example.com",
            tenant_id=uuid4(),
            role="member",
            tier="starter"
        )
        
        with patch("app.shared.core.dependencies.is_feature_enabled", return_value=False):
            with pytest.raises(HTTPException) as exc:
                feature_checker = requires_feature(FeatureFlag.MULTI_CLOUD)
                await feature_checker(mock_user)
            
            assert exc.value.status_code == status.HTTP_403_FORBIDDEN
            assert "multi_cloud" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_requires_feature_invalid_tier(self):
        """Test feature dependency with invalid tier."""
        mock_user = CurrentUser(
            id=uuid4(),
            email="user@example.com",
            tenant_id=uuid4(),
            role="member",
            tier="starter" # Use valid tier here, but we'll mock the internal check to simulate invalidity if needed
            # Or better, if we want to test PricingTier(user_tier) ValueError, we can't use BaseModel validation.
            # But CurrentUser validation happens before this.
            # If we want to test the TRY/EXCEPT block in dependencies.py:
            # user_tier = getattr(user, "tier", "starter")
            # so we should use a mock object that doesn't enforce schema
        )
        mock_user = AsyncMock()
        mock_user.tier = "invalid_tier"
        
        with patch("app.shared.core.dependencies.is_feature_enabled") as mock_check:
            mock_check.return_value = False
            
            with pytest.raises(HTTPException) as exc:
                feature_checker = requires_feature("some_feature")
                await feature_checker(mock_user)
            
            # Should default to STARTER tier
            mock_check.assert_called_once_with(PricingTier.STARTER, "some_feature")
            assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_requires_feature_user_without_tier(self):
        """Test feature dependency when user has no tier attribute."""
        mock_user = AsyncMock()
        # Mock user without tier attribute
        del mock_user.tier
        
        with patch("app.shared.core.dependencies.is_feature_enabled") as mock_check:
            mock_check.return_value = False
            
            with pytest.raises(HTTPException) as exc:
                feature_checker = requires_feature("some_feature")
                await feature_checker(mock_user)
            
            # Should default to STARTER tier when tier is missing
            mock_check.assert_called_once_with(PricingTier.STARTER, "some_feature")
            assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_requires_feature_dependency_chaining(self):
        """Test that feature dependency can be chained with other dependencies."""
        mock_user = CurrentUser(
            id=uuid4(),
            email="admin@example.com",
            tenant_id=uuid4(),
            role="admin",
            tier="enterprise"
        )
        
        with patch("app.shared.core.dependencies.is_feature_enabled", return_value=True):
            # Feature dependency should work with role dependency
            feature_checker = requires_feature("advanced_analytics")
            result = await feature_checker(mock_user)
            assert result.id == mock_user.id
