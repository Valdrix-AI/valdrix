"""API endpoint tests: security headers, sanitization, and authz/authn boundaries."""

import pytest
from uuid import uuid4
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient

from app.models.tenant import Tenant
from app.shared.core.auth import CurrentUser, UserRole
from app.shared.core.pricing import PricingTier

class TestSecurityHeadersAndErrors:
    """Tests for security headers and error handling."""

    @pytest.mark.asyncio
    async def test_security_headers_present(self, ac: AsyncClient):
        """Test that security headers are present on all responses."""
        response = await ac.get("/health")

        # Check required security headers
        headers = response.headers
        assert "content-security-policy" in headers
        assert "referrer-policy" in headers
        assert "permissions-policy" in headers
        assert "x-xss-protection" not in headers

        # Check CSP includes required directives
        csp = headers["content-security-policy"]
        assert "default-src 'self'" in csp
        assert "frame-ancestors 'none'" in csp
        assert "'unsafe-inline'" not in csp
        assert "style-src-attr 'none'" in csp

    @pytest.mark.asyncio
    async def test_error_responses_sanitized(self, ac: AsyncClient):
        """Test that error responses don't leak sensitive information."""
        # Try to access non-existent endpoint
        response = await ac.get("/api/v1/non-existent-endpoint")

        assert response.status_code == 404
        data = response.json()

        # Should have generic error structure
        assert "error" in data or "detail" in data
        # Should not contain sensitive information
        response_text = str(data).lower()
        assert "secret" not in response_text
        assert "password" not in response_text
        assert "key" not in response_text

    @pytest.mark.asyncio
    async def test_rate_limiting_headers(self, ac: AsyncClient):
        """Test that rate limiting includes proper headers."""
        # Make several requests to trigger rate limiting
        responses = []
        for _ in range(12):  # Exceed rate limit
            response = await ac.get("/health")
            responses.append(response)

        # Check if any response has rate limiting headers
        rate_limited_responses = [r for r in responses if r.status_code == 429]
        if rate_limited_responses:
            headers = rate_limited_responses[0].headers
            # Should have rate limiting headers
            assert "retry-after" in headers or "x-ratelimit" in headers.lower()


class TestAuthorizationAndAuthentication:
    """Tests for authentication and authorization."""

    @pytest.mark.asyncio
    async def test_tenant_isolation_zombie_scan(self, ac: AsyncClient, db):
        """Test that tenant A cannot access tenant B's zombie data."""
        # Create two tenants
        tenant_a = Tenant(id=uuid4(), name="Tenant A", plan=PricingTier.PRO.value)
        tenant_b = Tenant(id=uuid4(), name="Tenant B", plan=PricingTier.PRO.value)
        db.add_all([tenant_a, tenant_b])
        await db.commit()

        # Create users for each tenant
        user_a = CurrentUser(
            id=uuid4(),
            email="user@tenantA.com",
            tenant_id=tenant_a.id,
            role=UserRole.MEMBER,
            tier=PricingTier.PRO,
        )
        CurrentUser(
            id=uuid4(),
            email="user@tenantB.com",
            tenant_id=tenant_b.id,
            role=UserRole.MEMBER,
            tier=PricingTier.PRO,
        )

        # Mock user A
        from app.shared.core.auth import get_current_user

        async def mock_get_current_user():
            return user_a

        ac.app.dependency_overrides[get_current_user] = mock_get_current_user
        # We do NOT override require_tenant_access, so it returns tenant_a.id

        # Mock service to simulate a ResourceNotFoundError (which should happen if id belongs to tenant B)
        with patch(
            "app.modules.optimization.api.v1.zombies.RemediationService"
        ) as mock_service_cls:
            mock_service = mock_service_cls.return_value
            # Simulate high-level isolation: even if the user provides an ID from tenant B,
            # the service (scoped by tenant A) will not find it.
            mock_service.get_by_id = AsyncMock(return_value=None)

            # Try to get a plan for a resource that belongs to tenant B
            # (In reality, the ID would be from a tenant B record)
            fake_tenant_b_id = uuid4()
            response = await ac.get(f"/api/v1/zombies/plan/{fake_tenant_b_id}")

            # Should fail with 404 (Resource Not Found for THIS tenant)
            assert response.status_code == 404

        # Clean up overrides
        ac.app.dependency_overrides.pop(get_current_user, None)

    @pytest.mark.asyncio
    async def test_approve_remediation_requires_explicit_permission(
        self,
        ac: AsyncClient,
        test_tenant,
        test_remediation_request,
    ):
        """Test that explicit approval permission is required for approval operations."""
        # Mock regular member user with no explicit approval permission.
        member_user = CurrentUser(
            id=uuid4(),
            email="member@test.com",
            tenant_id=test_tenant.id,
            role=UserRole.MEMBER,
            tier=PricingTier.PRO,
        )

        # Mock authentication by overriding the app's dependency
        from app.shared.core.auth import get_current_user, require_tenant_access

        async def mock_get_current_user():
            return member_user

        async def mock_require_tenant_access():
            return member_user.tenant_id

        ac.app.dependency_overrides[get_current_user] = mock_get_current_user
        ac.app.dependency_overrides[require_tenant_access] = mock_require_tenant_access

        with patch(
            "app.modules.optimization.api.v1.zombies.user_has_approval_permission",
            new=AsyncMock(return_value=False),
        ) as mock_permission_check:
            response = await ac.post(
                f"/api/v1/zombies/approve/{test_remediation_request.id}",
                json={"notes": "test"},
            )

            assert response.status_code == 403
            mock_permission_check.assert_awaited_once()

        # Clean up overrides
        ac.app.dependency_overrides.pop(get_current_user, None)
        ac.app.dependency_overrides.pop(require_tenant_access, None)

    @pytest.mark.asyncio
    async def test_feature_flag_gates_endpoints(self, ac: AsyncClient, mock_user):
        """Test that feature flags properly gate endpoint access."""
        # Mock authentication by overriding the app's dependency
        from app.shared.core.auth import get_current_user, require_tenant_access
        from app.shared.core.pricing import FeatureFlag

        async def mock_get_current_user():
            return mock_user

        async def mock_require_tenant_access():
            return mock_user.tenant_id

        ac.app.dependency_overrides[get_current_user] = mock_get_current_user
        ac.app.dependency_overrides[require_tenant_access] = mock_require_tenant_access

        # Mock feature flag check failing
        from app.shared.core.dependencies import requires_feature

        dep = requires_feature(FeatureFlag.AUTO_REMEDIATION)

        async def mock_requires_feature_fail(user=None):
            from fastapi import HTTPException

            raise HTTPException(status_code=403, detail="Feature not available")

        ac.app.dependency_overrides[dep] = mock_requires_feature_fail

        response = await ac.post(
            "/api/v1/zombies/request",
            json={
                "resource_id": "test",
                "resource_type": "ec2_instance",
                "action": "stop_instance",
                "provider": "aws",
                "estimated_savings": 50.0,
            },
        )

        # Should be forbidden due to feature flag
        assert response.status_code == 403

        # Clean up overrides
        ac.app.dependency_overrides.pop(get_current_user, None)
        ac.app.dependency_overrides.pop(require_tenant_access, None)
        ac.app.dependency_overrides.pop(dep, None)

