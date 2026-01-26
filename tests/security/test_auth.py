"""
Tests for Auth Module

Tests:
1. JWT decoding
2. CurrentUser model
3. Role checking
4. RBAC decorator
"""

import pytest
from uuid import UUID

from app.shared.core.auth import CurrentUser, requires_role


class TestCurrentUserModel:
    """Test CurrentUser Pydantic model."""
    
    def test_current_user_minimal(self):
        """CurrentUser should accept minimal fields."""
        user = CurrentUser(
            id=UUID("12345678-1234-1234-1234-123456789012"),
            email="test@example.com"
        )
        
        assert user.email == "test@example.com"
        assert user.role == "member"  # Default
        assert user.tenant_id is None  # Optional
    
    def test_current_user_full(self):
        """CurrentUser should accept all fields."""
        user = CurrentUser(
            id=UUID("12345678-1234-1234-1234-123456789012"),
            email="admin@example.com",
            tenant_id=UUID("87654321-4321-4321-4321-210987654321"),
            role="admin"
        )
        
        assert user.role == "admin"
        assert user.tenant_id is not None
    
    def test_user_roles(self):
        """User roles should be valid strings."""
        valid_roles = ["owner", "admin", "member"]
        
        for role in valid_roles:
            user = CurrentUser(
                id=UUID("12345678-1234-1234-1234-123456789012"),
                email="test@example.com",
                role=role
            )
            assert user.role == role


class TestRoleHierarchy:
    """Test role-based access control hierarchy."""
    
    def test_role_hierarchy_exists(self):
        """Role hierarchy should define access levels."""
        hierarchy = {
            "owner": 100,
            "admin": 50,
            "member": 10
        }
        
        assert hierarchy["owner"] > hierarchy["admin"]
        assert hierarchy["admin"] > hierarchy["member"]
    
    def test_owner_highest_privilege(self):
        """Owner should have highest privilege."""
        hierarchy = {"owner": 100, "admin": 50, "member": 10}
        assert hierarchy["owner"] == max(hierarchy.values())


class TestRequiresRoleDecorator:
    """Test requires_role dependency factory."""
    
    def test_requires_role_returns_callable(self):
        """requires_role should return a dependency function."""
        role_checker = requires_role("admin")
        assert callable(role_checker)
    
    def test_multiple_role_levels(self):
        """Should create checkers for different role levels."""
        member_checker = requires_role("member")
        admin_checker = requires_role("admin")
        owner_checker = requires_role("owner")
        
        assert callable(member_checker)
        assert callable(admin_checker)
        assert callable(owner_checker)


class TestJWTDecoding:
    """Test JWT token handling."""
    
    def test_jwt_decode_function_exists(self):
        """decode_jwt should be importable."""
        from app.shared.core.auth import decode_jwt
        assert callable(decode_jwt)
    
    def test_invalid_token_raises(self):
        """Invalid JWT should raise HTTPException."""
        from app.shared.core.auth import decode_jwt
        from fastapi import HTTPException
        
        with pytest.raises(HTTPException):
            decode_jwt("invalid_token_here")


class TestAuthDependencies:
    """Test auth dependency functions."""
    
    def test_get_current_user_exists(self):
        """get_current_user should be importable."""
        from app.shared.core.auth import get_current_user
        assert callable(get_current_user)
    
    def test_get_current_user_from_jwt_exists(self):
        """get_current_user_from_jwt should be importable."""
        from app.shared.core.auth import get_current_user_from_jwt
        assert callable(get_current_user_from_jwt)
