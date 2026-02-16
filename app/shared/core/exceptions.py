from typing import Optional, Dict, Any
import re


class ValdrixException(Exception):
    """Base exception for all Valdrix errors."""

    def __init__(
        self,
        message: str,
        code: str = "internal_error",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

    def record_to_otel(self) -> None:
        """Record this exception to the current OpenTelemetry span."""
        from opentelemetry import trace

        span = trace.get_current_span()
        if span.is_recording():
            span.record_exception(self)
            span.set_attribute("exception.code", self.code)
            span.set_status(trace.Status(trace.StatusCode.ERROR, self.message))

    def __str__(self) -> str:
        return f"[{self.code}] {self.message} (Status: {self.status_code})"


class AdapterError(ValdrixException):
    """
    Raised when an external cloud adapter fails.
    BE-ADAPT-3: Automatically sanitizes error messages to avoid leaking internal cloud details.
    """

    def __init__(
        self,
        message: str,
        code: str = "adapter_error",
        details: Optional[Dict[str, Any]] = None,
    ):
        sanitized_message = self._sanitize(message)
        super().__init__(sanitized_message, code=code, status_code=502, details=details)

    def _sanitize(self, msg: str) -> str:
        """Remove sensitive tokens, request IDs, and internal paths from error messages."""
        # Remove UUIDs (likely Request IDs)
        msg = re.sub(
            r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
            "[REDACTED_ID]",
            msg,
            flags=re.IGNORECASE,
        )
        # Remove common sensitive AWS/Azure/GCP keywords if they appear in raw error strings
        msg = re.sub(
            r"(?i)(access_key|secret_key|token|password|signature)=[^&\s]+",
            r"\1=[REDACTED]",
            msg,
        )
        # Simplify common cloud errors to user-friendly versions
        if "AccessDenied" in msg or "Unauthorized" in msg:
            return "Permission denied: Ensure the Valdrix IAM role has the required read permissions."
        if "Throttling" in msg or "RequestLimitExceeded" in msg:
            return (
                "Cloud provider rate limit exceeded. Valdrix is retrying with backoff."
            )
        return msg


class AuthError(ValdrixException):
    """Raised when authentication or authorization fails."""

    def __init__(
        self,
        message: str,
        code: str = "auth_error",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, code=code, status_code=401, details=details)


class ConfigurationError(ValdrixException):
    """Raised when application configuration is invalid or missing."""

    def __init__(
        self,
        message: str,
        code: str = "config_error",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, code=code, status_code=500, details=details)


class DecryptionError(ValdrixException):
    """Raised when encrypted data cannot be decrypted."""

    def __init__(
        self,
        message: str = "Failed to decrypt value",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(
            message, code="decryption_failed", status_code=500, details=details
        )


class ResourceNotFoundError(ValdrixException):
    """Raised when a requested resource is not found."""

    def __init__(
        self,
        message: str,
        code: str = "not_found",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, code=code, status_code=404, details=details)


class BillingError(ValdrixException):
    """Raised when payment or subscription processing fails."""

    def __init__(
        self,
        message: str,
        code: str = "billing_error",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, code=code, status_code=400, details=details)


class AIAnalysisError(ValdrixException):
    """Raised when LLM/AI analysis fails."""

    def __init__(
        self,
        message: str,
        code: str = "ai_error",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, code=code, status_code=500, details=details)


class BudgetExceededError(ValdrixException):
    """Raised when an LLM request is blocked due to budget constraints."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message, code="budget_exceeded", status_code=402, details=details
        )


class KillSwitchTriggeredError(ValdrixException):
    """Raised when a remediation action is blocked by the safety kill switch."""

    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message, code="kill_switch_triggered", status_code=403, details=details
        )


class ExternalAPIError(ValdrixException):
    """Raised when an external API (LLM, Cloud Provider, etc.) fails."""

    def __init__(
        self,
        message: str,
        code: str = "external_api_error",
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, code=code, status_code=502, details=details)
