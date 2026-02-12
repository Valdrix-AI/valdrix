import pytest
from uuid import uuid4
from fastapi import HTTPException
from app.shared.core.auth import (
    CurrentUser,
    requires_role,
    create_access_token,
    decode_jwt,
    get_current_user_from_jwt,
    UserRole
)
from app.shared.core.pricing import PricingTier
from unittest.mock import MagicMock

class TestAuthLogic:
    """Thoroughly test authentication and JWT logic."""

    def test_jwt_lifecycle(self):
        """Test creating and then decoding a token."""
        user_id = uuid4()
        data = {"sub": str(user_id), "email": "test@valdrix.io", "role": "admin"}
        
        token = create_access_token(data)
        assert isinstance(token, str)
        
        decoded = decode_jwt(token)
        assert decoded["sub"] == str(user_id)
        assert decoded["email"] == "test@valdrix.io"
        assert decoded["role"] == "admin"
        assert "exp" in decoded

    def test_decode_invalid_token(self):
        """Rejects malformed or poorly signed tokens."""
        with pytest.raises(HTTPException) as exc:
            decode_jwt("definitely.not.a.token")
        assert exc.value.status_code == 401
        assert "Invalid token" in str(exc.value.detail)

    @pytest.mark.asyncio
    async def test_get_current_user_from_jwt(self):
        """Test dependency that extracts user from JWT without DB."""
        user_id = uuid4()
        token = create_access_token({"sub": str(user_id), "email": "onboard@valdrix.io"})
        
        credentials = MagicMock()
        credentials.credentials = token
        
        user = await get_current_user_from_jwt(credentials)
        assert user.id == user_id
        assert user.email == "onboard@valdrix.io"

    def test_role_hierarchy_enforcement(self):
        """Verify owner > admin > member logic."""
        # Setup users
        owner = CurrentUser(id=uuid4(), email="o@v.io", role=UserRole.OWNER)
        admin = CurrentUser(id=uuid4(), email="a@v.io", role=UserRole.ADMIN)
        member = CurrentUser(id=uuid4(), email="m@v.io", role=UserRole.MEMBER)
        
        # Test Admin requirement
        admin_dependency = requires_role(UserRole.ADMIN.value)
        
        # Owner pass
        assert admin_dependency(owner) == owner
        # Admin pass
        assert admin_dependency(admin) == admin
        # Member fail
        with pytest.raises(HTTPException) as exc:
            admin_dependency(member)
        assert exc.value.status_code == 403

        # Test Owner requirement
        owner_dependency = requires_role(UserRole.OWNER.value)
        assert owner_dependency(owner) == owner
        with pytest.raises(HTTPException):
            owner_dependency(admin)

    def test_user_minimal(self):
        """CurrentUser should accept minimal fields."""
        uid = uuid4()
        user = CurrentUser(id=uid, email="test@example.com")
        assert user.id == uid
        assert user.role == UserRole.MEMBER
        assert user.tier == PricingTier.FREE_TRIAL
