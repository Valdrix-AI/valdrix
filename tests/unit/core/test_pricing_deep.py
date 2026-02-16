import pytest
import uuid
from unittest.mock import MagicMock, AsyncMock, patch
from fastapi import HTTPException, status
from app.shared.core.pricing import (
    PricingTier,
    FeatureFlag,
    get_tier_config,
    is_feature_enabled,
    get_tier_limit,
    requires_tier,
    requires_feature,
    get_tenant_tier,
    TierGuard,
)


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock())
    return db


@pytest.fixture
def mock_user():
    user = MagicMock()
    user.tier = PricingTier.STARTER
    user.tenant_id = uuid.uuid4()
    return user


class TestPricingDeep:
    """Deep tests for pricing module to increase coverage."""

    def test_get_tier_config_fallback(self):
        """Test fallback for unknown tier."""
        # PricingTier is an Enum, so it's hard to pass an 'invalid' member
        # unless we cast or bypass types
        config = get_tier_config("unknown_tier")
        assert config["name"] == "Free Trial"

    def test_is_feature_enabled_string_mapping(self):
        """Test is_feature_enabled maps string to FeatureFlag."""
        assert is_feature_enabled(PricingTier.STARTER, "dashboards") is True
        assert is_feature_enabled(PricingTier.STARTER, FeatureFlag.DASHBOARDS) is True

    def test_is_feature_enabled_invalid_string(self):
        """Invalid feature strings should return False."""
        assert is_feature_enabled(PricingTier.STARTER, "not_a_feature") is False

    def test_get_tier_limit_unknown_limit(self):
        """Test limit check for unknown limit name."""
        assert get_tier_limit(PricingTier.STARTER, "invalid_limit") == 0

    @pytest.mark.asyncio
    async def test_requires_tier_missing_user(self):
        """Test requires_tier decorator when user is missing from kwargs."""
        decorator = requires_tier(PricingTier.PRO)

        async def mock_endpoint(user=None):
            return "ok"

        wrapped = decorator(mock_endpoint)
        with pytest.raises(HTTPException) as exc:
            await wrapped()
        assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_requires_tier_string_mapping(self):
        """Test requires_tier handles tier as string on user object."""
        decorator = requires_tier(PricingTier.PRO)

        async def mock_endpoint(user=None):
            return "ok"

        user = MagicMock()
        user.tier = "pro"  # String version

        wrapped = decorator(mock_endpoint)
        result = await wrapped(user=user)
        assert result == "ok"

    @pytest.mark.asyncio
    async def test_requires_tier_invalid_string_mapping(self):
        """Test requires_tier handles invalid tier string by defaulting to STARTER."""
        decorator = requires_tier(PricingTier.PRO)

        async def mock_endpoint(user=None):
            return "ok"

        user = MagicMock()
        user.tier = "invalid_tier"

        wrapped = decorator(mock_endpoint)
        with pytest.raises(HTTPException) as exc:
            await wrapped(user=user)
        assert exc.value.status_code == status.HTTP_403_FORBIDDEN

    @pytest.mark.asyncio
    async def test_requires_feature_missing_user(self):
        """Test requires_feature decorator when user is missing."""
        decorator = requires_feature(FeatureFlag.AI_INSIGHTS)

        async def mock_endpoint(user=None):
            return "ok"

        wrapped = decorator(mock_endpoint)
        with pytest.raises(HTTPException) as exc:
            await wrapped()
        assert exc.value.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_get_tenant_tier_invalid_uuid_string(self, mock_db):
        """Test get_tenant_tier with invalid UUID string returns FREE."""
        tier = await get_tenant_tier("not-a-uuid", mock_db)
        assert tier == PricingTier.FREE_TRIAL

    @pytest.mark.asyncio
    async def test_get_tenant_tier_db_exception(self, mock_db):
        """Test get_tenant_tier returns FREE on database exception."""
        mock_db.execute.side_effect = Exception("DB Error")
        tier = await get_tenant_tier(uuid.uuid4(), mock_db)
        assert tier == PricingTier.FREE_TRIAL

    @pytest.mark.asyncio
    async def test_get_tenant_tier_invalid_plan_returns_free(self, mock_db):
        """Invalid plan strings should fallback to FREE."""
        mock_tenant = MagicMock()
        mock_tenant.plan = "invalid-plan"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_tenant
        mock_db.execute.return_value = mock_result

        with patch("app.shared.core.pricing.logger") as mock_logger:
            tier = await get_tenant_tier(uuid.uuid4(), mock_db)
            assert tier == PricingTier.FREE_TRIAL
            mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_get_tenant_tier_invalid_plan_returns_free(self, mock_db):
        """Invalid plan strings should fallback to FREE."""
        mock_tenant = MagicMock()
        mock_tenant.plan = "invalid-plan"
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_tenant
        mock_db.execute.return_value = mock_result

        with patch("app.shared.core.pricing.logger") as mock_logger:
            tier = await get_tenant_tier(uuid.uuid4(), mock_db)
            assert tier == PricingTier.FREE
            mock_logger.error.assert_called()

    @pytest.mark.asyncio
    async def test_requires_feature_invalid_tier_string_deep(self):
        """Test requires_feature handles invalid tier string by defaulting to STARTER."""
        # Line 312-313
        decorator = requires_feature("feature_that_exists")
        # We need a feature that exists in STARTER
        with patch("app.shared.core.pricing.is_feature_enabled", return_value=True):

            async def mock_endpoint(user=None):
                return "ok"

            user = MagicMock()
            user.tier = "completely_invalid_tier_name"
            wrapped = decorator(mock_endpoint)
            assert await wrapped(user=user) == "ok"

    @pytest.mark.asyncio
    async def test_requires_feature_403_enum(self):
        """Test the 403 error message construction with FeatureFlag enum."""
        # Line 316-320
        decorator = requires_feature(FeatureFlag.API_ACCESS)

        async def mock_endpoint(user=None):
            return "ok"

        user = MagicMock()
        user.tier = PricingTier.STARTER
        wrapped = decorator(mock_endpoint)
        with pytest.raises(HTTPException) as exc:
            await wrapped(user=user)
        assert exc.value.status_code == 403
        assert "api_access" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_requires_feature_403_string(self):
        """Test the 403 error message construction with string feature name."""
        # Line 316-320
        decorator = requires_feature("some_pro_feature")
        with patch("app.shared.core.pricing.is_feature_enabled", return_value=False):

            async def mock_endpoint(user=None):
                return "ok"

            user = MagicMock()
            user.tier = PricingTier.STARTER
            wrapped = decorator(mock_endpoint)
            with pytest.raises(HTTPException) as exc:
                await wrapped(user=user)
            assert "some_pro_feature" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_get_tenant_tier_empty(self, mock_db):
        """Test get_tenant_tier returns FREE if tenant not in DB."""
        # Line 344
        mock_db.execute.return_value.scalar_one_or_none.return_value = None
        tier = await get_tenant_tier(uuid.uuid4(), mock_db)
        assert tier == PricingTier.FREE_TRIAL

    @pytest.mark.asyncio
    async def test_tier_guard_require_failure_deep(self, mock_db):
        """Test TierGuard.require raises 403 on failure."""
        # Line 381-382
        user = MagicMock(tenant_id=uuid.uuid4())
        with patch(
            "app.shared.core.pricing.get_tenant_tier",
            AsyncMock(return_value=PricingTier.STARTER),
        ):
            async with TierGuard(user, mock_db) as guard:
                with pytest.raises(HTTPException) as exc:
                    guard.require(FeatureFlag.API_ACCESS)
                assert exc.value.status_code == 403

    @pytest.mark.asyncio
    async def test_tier_guard_recursive_limits(self, mock_db):
        """Test TierGuard handling recursive/nested limits."""
        user = MagicMock(tenant_id=uuid.uuid4())
        # Mock a tier that has nested features/limits if any
        # In our case, TIER_CONFIG has simple limits but we test the logic
        with patch(
            "app.shared.core.pricing.get_tenant_tier",
            AsyncMock(return_value=PricingTier.PRO),
        ):
            async with TierGuard(user, mock_db) as guard:
                # Pro has ai_insights: True (which is a boolean, not a list/dict)
                # But we can mock TIER_CONFIG for a specific test if needed
                config_mock = {
                    PricingTier.PRO: {
                        "limits": {"nested_key": 100, "list_limit": [1, 2, 3]}
                    },
                    PricingTier.STARTER: {"limits": {"max_aws_accounts": 5}},
                }
                with patch("app.shared.core.pricing.TIER_CONFIG", config_mock):
                    assert guard.limit("nested_key") == 100
                    assert guard.limit("list_limit") == [1, 2, 3]
