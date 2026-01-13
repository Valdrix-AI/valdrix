"""
Tests for Audit Log API and Service

Tests:
1. AuditLog model
2. AuditLogger service
3. Sensitive data masking
4. Event types
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

from app.services.security.audit_log import (
    AuditEventType,
    AuditLog,
    AuditLogger,
)


class TestAuditEventType:
    """Test AuditEventType enum."""
    
    def test_auth_events(self):
        """Auth event types should exist."""
        assert AuditEventType.AUTH_LOGIN.value == "auth.login"
        assert AuditEventType.AUTH_LOGOUT.value == "auth.logout"
        assert AuditEventType.AUTH_FAILED.value == "auth.failed"
    
    def test_resource_events(self):
        """Resource CRUD event types should exist."""
        assert AuditEventType.RESOURCE_CREATE.value == "resource.create"
        assert AuditEventType.RESOURCE_READ.value == "resource.read"
        assert AuditEventType.RESOURCE_UPDATE.value == "resource.update"
        assert AuditEventType.RESOURCE_DELETE.value == "resource.delete"
    
    def test_remediation_events(self):
        """Remediation event types should exist."""
        assert AuditEventType.REMEDIATION_REQUESTED.value == "remediation.requested"
        assert AuditEventType.REMEDIATION_APPROVED.value == "remediation.approved"
        assert AuditEventType.REMEDIATION_EXECUTED.value == "remediation.executed"
        assert AuditEventType.REMEDIATION_FAILED.value == "remediation.failed"
    
    def test_billing_events(self):
        """Billing event types should exist."""
        assert AuditEventType.BILLING_SUBSCRIPTION_CREATED.value == "billing.subscription_created"
        assert AuditEventType.BILLING_PAYMENT_RECEIVED.value == "billing.payment_received"


class TestAuditLogModel:
    """Test AuditLog SQLAlchemy model."""
    
    def test_audit_log_has_required_fields(self):
        """AuditLog should have all required fields."""
        assert hasattr(AuditLog, 'id')
        assert hasattr(AuditLog, 'tenant_id')
        assert hasattr(AuditLog, 'event_type')
        assert hasattr(AuditLog, 'event_timestamp')
        assert hasattr(AuditLog, 'actor_id')
        assert hasattr(AuditLog, 'actor_email')
        assert hasattr(AuditLog, 'actor_ip')
        assert hasattr(AuditLog, 'correlation_id')
        assert hasattr(AuditLog, 'resource_type')
        assert hasattr(AuditLog, 'resource_id')
        assert hasattr(AuditLog, 'details')
        assert hasattr(AuditLog, 'success')
        assert hasattr(AuditLog, 'error_message')
    
    def test_audit_log_table_name(self):
        """AuditLog should use correct table name."""
        assert AuditLog.__tablename__ == "audit_logs"


class TestAuditLogger:
    """Test AuditLogger service class."""
    
    def test_logger_initialization(self):
        """AuditLogger should initialize with db and tenant_id."""
        mock_db = MagicMock()
        logger = AuditLogger(mock_db, "tenant-123")
        
        assert logger.db == mock_db
        assert logger.tenant_id == "tenant-123"
        assert logger.correlation_id is not None  # Auto-generated
    
    def test_logger_with_correlation_id(self):
        """AuditLogger should accept custom correlation ID."""
        mock_db = MagicMock()
        logger = AuditLogger(mock_db, "tenant-123", correlation_id="corr-456")
        
        assert logger.correlation_id == "corr-456"
    
    @pytest.mark.asyncio
    async def test_log_creates_entry(self):
        """AuditLogger.log() should create AuditLog entry."""
        mock_db = AsyncMock()
        mock_db.add = MagicMock()
        mock_db.flush = AsyncMock()
        
        logger = AuditLogger(mock_db, "tenant-123")
        
        entry = await logger.log(
            event_type=AuditEventType.AUTH_LOGIN,
            actor_email="user@test.com",
            success=True
        )
        
        assert mock_db.add.called
        assert mock_db.flush.called
        assert entry.event_type == "auth.login"
        assert entry.success is True


class TestSensitiveDataMasking:
    """Test sensitive field masking in AuditLogger."""
    
    def test_mask_password_field(self):
        """Password fields should be masked."""
        mock_db = MagicMock()
        logger = AuditLogger(mock_db, "tenant-123")
        
        data = {"username": "admin", "password": "secret123"}
        masked = logger._mask_sensitive(data)
        
        assert masked["username"] == "admin"
        assert masked["password"] == "***REDACTED***"
    
    def test_mask_token_field(self):
        """Token fields should be masked."""
        mock_db = MagicMock()
        logger = AuditLogger(mock_db, "tenant-123")
        
        data = {"access_token": "eyJhbGc...", "user": "admin"}
        masked = logger._mask_sensitive(data)
        
        assert masked["access_token"] == "***REDACTED***"
        assert masked["user"] == "admin"
    
    def test_mask_api_key_field(self):
        """API key fields should be masked."""
        mock_db = MagicMock()
        logger = AuditLogger(mock_db, "tenant-123")
        
        data = {"api_key": "sk-12345", "name": "test"}
        masked = logger._mask_sensitive(data)
        
        assert masked["api_key"] == "***REDACTED***"
    
    def test_mask_external_id(self):
        """External ID should be masked."""
        mock_db = MagicMock()
        logger = AuditLogger(mock_db, "tenant-123")
        
        data = {"external_id": "vx-abc123", "role_arn": "arn:aws:..."}
        masked = logger._mask_sensitive(data)
        
        assert masked["external_id"] == "***REDACTED***"
    
    def test_mask_nested_sensitive_fields(self):
        """Nested sensitive fields should be masked."""
        mock_db = MagicMock()
        logger = AuditLogger(mock_db, "tenant-123")
        
        data = {
            "user": "admin",
            "credentials": {
                "secret": "mysecret",
                "token": "mytoken"
            }
        }
        masked = logger._mask_sensitive(data)
        
        assert masked["user"] == "admin"
        assert masked["credentials"]["secret"] == "***REDACTED***"
        assert masked["credentials"]["token"] == "***REDACTED***"
    
    def test_mask_handles_non_dict(self):
        """Non-dict input should be returned as-is."""
        mock_db = MagicMock()
        logger = AuditLogger(mock_db, "tenant-123")
        
        assert logger._mask_sensitive("string") == "string"
        assert logger._mask_sensitive(123) == 123
        assert logger._mask_sensitive(None) is None


class TestAuditLoggerSensitiveFields:
    """Test SENSITIVE_FIELDS constant."""
    
    def test_sensitive_fields_include_secrets(self):
        """SENSITIVE_FIELDS should include common secret field names."""
        expected = {"password", "token", "secret", "api_key", "access_key", "external_id"}
        
        for field in expected:
            assert field in AuditLogger.SENSITIVE_FIELDS, f"Missing: {field}"
