from typing import Optional, Dict, Any

class ValdrixException(Exception):
    """Base exception for all Valdrix errors."""
    def __init__(
        self,
        message: str,
        code: str = "internal_error",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}

class AdapterError(ValdrixException):
    """
    Raised when an external cloud adapter fails.
    BE-ADAPT-3: Automatically sanitizes error messages to avoid leaking internal cloud details.
    """
    def __init__(self, message: str, code: str = "adapter_error", details: Optional[Dict[str, Any]] = None):
        sanitized_message = self._sanitize(message)
        super().__init__(sanitized_message, code=code, status_code=502, details=details)

    def _sanitize(self, msg: str) -> str:
        """Remove sensitive tokens, request IDs, and internal paths from error messages."""
        import re
        # Remove UUIDs (likely Request IDs)
        msg = re.sub(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '[REDACTED_ID]', msg, flags=re.IGNORECASE)
        # Remove common sensitive AWS/Azure/GCP keywords if they appear in raw error strings
        msg = re.sub(r'(?i)(access_key|secret_key|token|password|signature)=[^&\s]+', r'\1=[REDACTED]', msg)
        # Simplify common cloud errors to user-friendly versions
        if "AccessDenied" in msg or "Unauthorized" in msg:
            return "Permission denied: Ensure the Valdrix IAM role has the required read permissions."
        if "Throttling" in msg or "RequestLimitExceeded" in msg:
            return "Cloud provider rate limit exceeded. Valdrix is retrying with backoff."
        return msg

class AuthError(ValdrixException):
    """Raised when authentication or authorization fails."""
    def __init__(self, message: str, code: str = "auth_error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=code, status_code=401, details=details)

class ConfigurationError(ValdrixException):
    """Raised when application configuration is invalid or missing."""
    def __init__(self, message: str, code: str = "config_error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=code, status_code=500, details=details)

class ResourceNotFoundError(ValdrixException):
    """Raised when a requested resource is not found."""
    def __init__(self, message: str, code: str = "not_found", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=code, status_code=404, details=details)

class BillingError(ValdrixException):
    """Raised when payment or subscription processing fails."""
    def __init__(self, message: str, code: str = "billing_error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=code, status_code=400, details=details)

class AIAnalysisError(ValdrixException):
    """Raised when LLM/AI analysis fails."""
    def __init__(self, message: str, code: str = "ai_error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=code, status_code=500, details=details)

class BudgetExceededError(ValdrixException):
    """Raised when an LLM request is blocked due to budget constraints."""
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code="budget_exceeded", status_code=402, details=details)
