"""
Tests for app/shared/core/exceptions.py - Custom exception classes
"""
from app.shared.core.exceptions import ValdrixException


class TestValdrixException:
    """Test ValdrixException custom exception class."""

    def test_valdrix_exception_creation(self):
        """Test creating a ValdrixException with all parameters."""
        exc = ValdrixException(
            message="Test error message",
            code="TEST_ERROR",
            status_code=400,
            details={"field": "value"}
        )
        
        assert exc.message == "Test error message"
        assert exc.code == "TEST_ERROR"
        assert exc.status_code == 400
        assert exc.details == {"field": "value"}

    def test_valdrix_exception_creation_minimal(self):
        """Test creating a ValdrixException with minimal parameters."""
        exc = ValdrixException(message="Simple error")
        
        assert exc.message == "Simple error"
        assert exc.code == "internal_error"  # Default
        assert exc.status_code == 500  # Default
        assert exc.details == {}  # Default empty dict

    def test_valdrix_exception_str_representation(self):
        """Test string representation of ValdrixException."""
        exc = ValdrixException(
            message="Test error",
            code="TEST_CODE",
            status_code=422
        )
        
        str_repr = str(exc)
        assert "Test error" in str_repr
        assert "TEST_CODE" in str_repr
        assert "422" in str_repr

    def test_valdrix_exception_inheritance(self):
        """Test that ValdrixException inherits from Exception."""
        exc = ValdrixException(message="Test")
        
        assert isinstance(exc, Exception)
        assert isinstance(exc, ValdrixException)

    def test_valdrix_exception_with_none_details(self):
        """Test ValdrixException with None details."""
        exc = ValdrixException(
            message="Test",
            code="TEST",
            details=None
        )
        
        assert exc.details == {}  # None details becomes empty dict

    def test_valdrix_exception_with_empty_details(self):
        """Test ValdrixException with empty details dict."""
        exc = ValdrixException(
            message="Test",
            code="TEST",
            details={}
        )
        
        assert exc.details == {}

    def test_valdrix_exception_status_code_validation(self):
        """Test that status_code accepts valid HTTP status codes."""
        # Test various valid status codes
        for status in [200, 400, 401, 403, 404, 422, 500, 502, 503]:
            exc = ValdrixException(
                message=f"Error with status {status}",
                status_code=status
            )
            assert exc.status_code == status

    def test_valdrix_exception_code_types(self):
        """Test ValdrixException with different code types."""
        test_cases = [
            ("VALIDATION_ERROR", 422),
            ("NOT_FOUND", 404),
            ("PERMISSION_DENIED", 403),
            ("RATE_LIMITED", 429),
            ("INTERNAL_ERROR", 500),
            (None, 500),  # Default code
            ("", "internal_error"),  # Empty code becomes default
        ]
        
        for code, expected_status in test_cases:
            exc = ValdrixException(
                message=f"Test with code: {code}",
                code=code or "internal_error",
                status_code=expected_status
            )
            assert exc.code == (code or "internal_error")
            assert exc.status_code == expected_status

from app.shared.core.exceptions import (
    AdapterError, AuthError, ConfigurationError, ResourceNotFoundError,
    BillingError, AIAnalysisError, BudgetExceededError, KillSwitchTriggeredError
)

class TestCustomExceptions:
    """Test specific ValdrixException subclasses."""

    def test_adapter_error_sanitization(self):
        """Test that AdapterError sanitizes sensitive info."""
        raw_msg = "AWS Error: RequestId: 12345678-1234-1234-1234-1234567890ab failed. access_key=AKIA123 with signature=XYZ"
        exc = AdapterError(raw_msg)
        
        assert "12345678-1234-1234-1234-1234567890ab" not in str(exc)
        assert "[REDACTED_ID]" in str(exc)
        assert "access_key=[REDACTED]" in str(exc)
        assert "signature=[REDACTED]" in str(exc)
        assert exc.status_code == 502

    def test_adapter_error_simplification(self):
        """Test that common cloud errors are simplified."""
        exc1 = AdapterError("Some AccessDenied error from AWS")
        assert "Permission denied" in str(exc1)
        
        exc2 = AdapterError("ThrottlingException: Rate exceeded")
        assert "rate limit exceeded" in str(exc2)

    def test_auth_error(self):
        exc = AuthError("Login failed")
        assert exc.status_code == 401
        assert exc.code == "auth_error"

    def test_config_error(self):
        exc = ConfigurationError("Missing key")
        assert exc.status_code == 500
        assert exc.code == "config_error"

    def test_not_found_error(self):
        exc = ResourceNotFoundError("User not found")
        assert exc.status_code == 404
        assert exc.code == "not_found"

    def test_billing_error(self):
        exc = BillingError("Card declined")
        assert exc.status_code == 400
        assert exc.code == "billing_error"

    def test_ai_error(self):
        exc = AIAnalysisError("LLM failed")
        assert exc.status_code == 500
        assert exc.code == "ai_error"

    def test_budget_error(self):
        exc = BudgetExceededError("Limit reached")
        assert exc.status_code == 402
        assert exc.code == "budget_exceeded"

    def test_kill_switch_error(self):
        exc = KillSwitchTriggeredError("Unsafe action")
        assert exc.status_code == 403
        assert exc.code == "kill_switch_triggered"
