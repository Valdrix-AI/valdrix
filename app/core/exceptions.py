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
    """Raised when an external cloud adapter fails."""
    def __init__(self, message: str, code: str = "adapter_error", details: Optional[Dict[str, Any]] = None):
        super().__init__(message, code=code, status_code=502, details=details)

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
