import pytest
from app.shared.core.exceptions import (
    ValdrixException,
    AdapterError,
    AuthError,
    ConfigurationError,
    ResourceNotFoundError,
    BillingError,
    AIAnalysisError,
    BudgetExceededError,
    KillSwitchTriggeredError
)

class TestExceptionsDeep:
    """Deep tests for exceptions module to reach 100% coverage."""

    def test_adapter_error_sanitization_uuid(self):
        """Test that AdapterError sanitizes UUIDs."""
        raw_msg = "Error in request 12345678-1234-5678-1234-567812345678"
        exc = AdapterError(raw_msg)
        assert "[REDACTED_ID]" in exc.message
        assert "12345678-1234-5678-1234-567812345678" not in exc.message
        assert exc.status_code == 502

    def test_adapter_error_sanitization_secrets(self):
        """Test that AdapterError sanitizes sensitive tokens."""
        raw_msg = "Failed with token=secret123 and access_key=key456"
        exc = AdapterError(raw_msg)
        assert "token=[REDACTED]" in exc.message
        assert "access_key=[REDACTED]" in exc.message
        assert "secret123" not in exc.message
        assert "key456" not in exc.message

    def test_adapter_error_permission_mapping(self):
        """Test mapping of AccessDenied to user-friendly message."""
        raw_msg = "AWS Error: AccessDenied to s3:ListBucket"
        exc = AdapterError(raw_msg)
        assert "Permission denied" in exc.message
        assert "IAM role" in exc.message

    def test_adapter_error_throttling_mapping(self):
        """Test mapping of Throttling to user-friendly message."""
        raw_msg = "Rate limit exceeded: Throttling"
        exc = AdapterError(raw_msg)
        assert "rate limit exceeded" in exc.message
        assert "retrying" in exc.message

    def test_auth_error_defaults(self):
        """Test AuthError defaults."""
        exc = AuthError("Login failed")
        assert exc.message == "Login failed"
        assert exc.code == "auth_error"
        assert exc.status_code == 401

    def test_configuration_error_defaults(self):
        """Test ConfigurationError defaults."""
        exc = ConfigurationError("Missing key")
        assert exc.message == "Missing key"
        assert exc.code == "config_error"
        assert exc.status_code == 500

    def test_resource_not_found_defaults(self):
        """Test ResourceNotFoundError defaults."""
        exc = ResourceNotFoundError("User not found")
        assert exc.message == "User not found"
        assert exc.code == "not_found"
        assert exc.status_code == 404

    def test_billing_error_defaults(self):
        """Test BillingError defaults."""
        exc = BillingError("Payment failed")
        assert exc.message == "Payment failed"
        assert exc.code == "billing_error"
        assert exc.status_code == 400

    def test_ai_analysis_error_defaults(self):
        """Test AIAnalysisError defaults."""
        exc = AIAnalysisError("LLM failed")
        assert exc.message == "LLM failed"
        assert exc.code == "ai_error"
        assert exc.status_code == 500

    def test_budget_exceeded_error_defaults(self):
        """Test BudgetExceededError defaults."""
        exc = BudgetExceededError("Budget limit hit")
        assert exc.message == "Budget limit hit"
        assert exc.code == "budget_exceeded"
        assert exc.status_code == 402

    def test_kill_switch_triggered_defaults(self):
        """Test KillSwitchTriggeredError defaults."""
        exc = KillSwitchTriggeredError("Kill switch active")
        assert exc.message == "Kill switch active"
        assert exc.code == "kill_switch_triggered"
        assert exc.status_code == 403
