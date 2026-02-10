from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.models.background_job import audit_job_deletion


def test_audit_job_deletion_logs_event():
    target = SimpleNamespace(id="job-1", tenant_id="tenant-1", job_type="test_job")

    with patch("structlog.get_logger") as mock_get_logger:
        mock_logger = MagicMock()
        mock_get_logger.return_value = mock_logger

        audit_job_deletion(None, None, target)

        mock_get_logger.assert_called_once_with("audit.deletion")
        mock_logger.info.assert_called_once_with(
            "resource_permanently_deleted",
            resource_type="background_job",
            resource_id="job-1",
            tenant_id="tenant-1",
            job_type="test_job",
        )
