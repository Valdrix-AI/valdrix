"""
Tests for Job Handlers - Zombie Scan and Notifications
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from types import SimpleNamespace
from uuid import UUID, uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.background_job import BackgroundJob
from app.modules.governance.domain.jobs.handlers.zombie import ZombieScanHandler
from app.modules.governance.domain.jobs.handlers.notifications import (
    NotificationHandler,
    WebhookRetryHandler,
)
from app.modules.governance.domain.jobs.handlers.remediation import RemediationHandler
from app.modules.governance.domain.jobs.handlers.finops import FinOpsAnalysisHandler


@pytest.fixture
def mock_db():
    db = MagicMock(spec=AsyncSession)
    db.execute = AsyncMock()
    return db


@pytest.fixture
def sample_job():
    job = MagicMock(spec=BackgroundJob)
    job.tenant_id = uuid4()
    job.payload = {}
    return job


@pytest.mark.asyncio
async def test_zombie_scan_handler_no_connections(mock_db, sample_job):
    """Test ZombieScanHandler when no cloud connections exist."""
    handler = ZombieScanHandler()

    # Setup mock result object
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db.execute.return_value = mock_result

    result = await handler.execute(sample_job, mock_db)
    assert result["status"] == "skipped"
    assert "no_connections_found" in result["reason"]


@pytest.mark.asyncio
async def test_zombie_scan_handler_success(mock_db, sample_job):
    """Test ZombieScanHandler successful execution with AWS/Azure connections."""
    handler = ZombieScanHandler()

    # Mock AWS connection
    mock_aws = MagicMock()
    mock_aws.id = uuid4()
    mock_aws.region = "us-east-1"

    # Mock DB query results for connections
    mock_aws_result = MagicMock()
    mock_aws_result.scalars.return_value.all.return_value = [mock_aws]

    mock_empty_result = MagicMock()
    mock_empty_result.scalars.return_value.all.return_value = []

    # DB calls: AWS, Azure, GCP
    mock_db.execute.side_effect = [
        mock_aws_result,
        mock_empty_result,
        mock_empty_result,
    ]

    # Mock detector and factory
    with patch(
        "app.modules.optimization.domain.factory.ZombieDetectorFactory.get_detector"
    ) as mock_factory:
        mock_detector = AsyncMock()
        mock_detector.provider_name = "aws"
        mock_detector.scan_all.return_value = {
            "unattached_volumes": [
                {"id": "v-1", "monthly_waste": 25.0, "provider": "aws"},
                {"id": "v-2", "monthly_waste": 25.0, "provider": "aws"},
            ]
        }
        mock_factory.return_value = mock_detector

        result = await handler.execute(sample_job, mock_db)

        assert result["status"] == "completed"
        assert result["zombies_found"] == 2
        assert result["total_waste"] == 50.0
        assert len(result["details"]) == 1
        assert result["details"][0]["provider"] == "aws"


@pytest.mark.asyncio
async def test_notification_handler_success(mock_db, sample_job):
    """Test NotificationHandler successful execution."""
    handler = NotificationHandler()
    sample_job.payload = {"message": "Hello", "title": "Test Title"}

    with patch(
        "app.modules.notifications.domain.get_tenant_slack_service",
        new_callable=AsyncMock,
    ) as mock_get_slack:
        mock_slack = AsyncMock()
        mock_slack.send_alert.return_value = True
        mock_get_slack.return_value = mock_slack

        result = await handler.execute(sample_job, mock_db)
        assert result["status"] == "completed"
        assert result["success"] is True
        mock_slack.send_alert.assert_called_once_with(
            title="Test Title", message="Hello", severity="info"
        )


@pytest.mark.asyncio
async def test_notification_handler_no_message(mock_db, sample_job):
    """Test NotificationHandler failure when message is missing."""
    handler = NotificationHandler()
    sample_job.payload = {"title": "No Message Here"}

    with pytest.raises(ValueError, match="message required"):
        await handler.execute(sample_job, mock_db)


@pytest.mark.asyncio
async def test_webhook_retry_handler_paystack(mock_db, sample_job):
    """Test WebhookRetryHandler delegation to Paystack processor."""
    handler = WebhookRetryHandler()
    sample_job.payload = {"provider": "paystack"}

    with patch(
        "app.modules.billing.domain.billing.webhook_retry.process_paystack_webhook"
    ) as mock_process:
        mock_process.return_value = {"status": "completed"}

        result = await handler.execute(sample_job, mock_db)
        assert result["status"] == "completed"
        mock_process.assert_called_once_with(sample_job, mock_db)


@pytest.mark.asyncio
async def test_webhook_retry_handler_generic_http(mock_db, sample_job):
    """Test WebhookRetryHandler generic HTTP POST retry."""
    handler = WebhookRetryHandler()
    sample_job.payload = {
        "provider": "generic",
        "url": "https://example.com/webhook",
        "data": {"foo": "bar"},
    }

    with (
        patch("httpx.AsyncClient.post") as mock_post,
        patch(
            "app.modules.governance.domain.jobs.handlers.notifications.get_settings",
            return_value=SimpleNamespace(
                WEBHOOK_ALLOWED_DOMAINS=["example.com"],
                WEBHOOK_REQUIRE_HTTPS=True,
                WEBHOOK_BLOCK_PRIVATE_IPS=True,
            ),
        ),
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.raise_for_status = MagicMock()
        mock_post.return_value = mock_resp

        result = await handler.execute(sample_job, mock_db)
        assert result["status"] == "completed"
        assert result["status_code"] == 200
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://example.com/webhook"
        assert kwargs["json"] == {"foo": "bar"}
        assert kwargs["headers"]["Content-Type"] == "application/json"


@pytest.mark.asyncio
async def test_webhook_retry_handler_rejects_non_allowlisted_domain(
    mock_db, sample_job
):
    handler = WebhookRetryHandler()
    sample_job.payload = {
        "provider": "generic",
        "url": "https://evil.example.net/webhook",
        "data": {"foo": "bar"},
    }

    with patch(
        "app.modules.governance.domain.jobs.handlers.notifications.get_settings",
        return_value=SimpleNamespace(
            WEBHOOK_ALLOWED_DOMAINS=["example.com"],
            WEBHOOK_REQUIRE_HTTPS=True,
            WEBHOOK_BLOCK_PRIVATE_IPS=True,
        ),
    ):
        with pytest.raises(ValueError, match="allowlist"):
            await handler.execute(sample_job, mock_db)


@pytest.mark.asyncio
async def test_remediation_handler_targeted(mock_db, sample_job):
    """Test RemediationHandler targeted execution by request_id."""
    handler = RemediationHandler()
    request_id = str(uuid4())
    sample_job.payload = {"request_id": request_id}

    remediation_request = MagicMock()
    remediation_request.id = UUID(request_id)
    remediation_request.tenant_id = sample_job.tenant_id
    remediation_request.provider = "aws"
    remediation_request.region = "us-east-1"
    remediation_request.status.value = "approved"
    remediation_request.connection_id = None
    remediation_request.scheduled_execution_at = None

    remediation_res = MagicMock()
    remediation_res.scalar_one_or_none.return_value = remediation_request

    connection = MagicMock()
    connection.id = uuid4()
    connection.region = "us-east-1"

    conn_res = MagicMock()
    conn_res.scalars.return_value.first.return_value = connection
    mock_db.execute.side_effect = [remediation_res, conn_res]

    with (
        patch(
            "app.shared.adapters.aws_multitenant.MultiTenantAWSAdapter"
        ) as mock_adapter_cls,
        patch(
            "app.modules.optimization.domain.remediation.RemediationService"
        ) as mock_service_cls,
    ):
        mock_adapter = AsyncMock()
        mock_adapter.get_credentials.return_value = {"key": "val"}
        mock_adapter_cls.return_value = mock_adapter

        mock_service = AsyncMock()
        mock_result = MagicMock()
        mock_result.id = UUID(request_id)
        mock_result.status.value = "completed"
        mock_service.execute.return_value = mock_result
        mock_service_cls.return_value = mock_service

        result = await handler.execute(sample_job, mock_db)

        assert result["status"] == "completed"
        assert result["mode"] == "targeted"
        assert result["request_id"] == request_id
        mock_service.execute.assert_called_once_with(
            UUID(request_id), sample_job.tenant_id
        )


@pytest.mark.asyncio
async def test_remediation_handler_autonomous_sweep(mock_db, sample_job):
    """Test RemediationHandler autonomous sweep."""
    handler = RemediationHandler()
    sample_job.payload = {}

    # Mock AWS connection exists
    mock_conn = MagicMock()
    mock_conn.id = uuid4()
    mock_conn.region = "us-east-1"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_conn
    mock_db.execute.return_value = mock_result

    with patch(
        "app.shared.adapters.aws_multitenant.MultiTenantAWSAdapter"
    ) as mock_adapter_cls:
        mock_adapter = AsyncMock()
        mock_adapter.get_credentials.return_value = {"key": "val"}
        mock_adapter_cls.return_value = mock_adapter

        with patch(
            "app.shared.remediation.autonomous.AutonomousRemediationEngine"
        ) as mock_engine_cls:
            mock_engine = AsyncMock()
            mock_engine.run_autonomous_sweep.return_value = {
                "mode": "dry_run",
                "scanned": 10,
                "auto_executed": 0,
            }
            mock_engine_cls.return_value = mock_engine

            result = await handler.execute(sample_job, mock_db)

            assert result["status"] == "completed"
            assert result["mode"] == "dry_run"
            assert result["scanned"] == 10
            mock_engine.run_autonomous_sweep.assert_called_once()


@pytest.mark.asyncio
async def test_finops_analysis_handler_success(mock_db, sample_job):
    """Test FinOpsAnalysisHandler successful execution."""
    handler = FinOpsAnalysisHandler()

    mock_conn = MagicMock(provider="aws")
    aws_result = MagicMock()
    aws_result.scalars.return_value.all.return_value = [mock_conn]
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    mock_db.execute = AsyncMock(
        side_effect=[
            aws_result,  # AWS
            empty_result,  # Azure
            empty_result,  # GCP
            empty_result,  # SaaS
            empty_result,  # License
            empty_result,  # Platform
            empty_result,  # Hybrid
        ]
    )

    with patch(
        "app.modules.governance.domain.jobs.handlers.finops.AdapterFactory"
    ) as mock_factory:
        mock_adapter = MagicMock()
        usage_summary = MagicMock()
        usage_summary.records = [MagicMock()]
        mock_adapter.get_daily_costs = AsyncMock(return_value=usage_summary)
        mock_factory.get_adapter.return_value = mock_adapter

        with patch(
            "app.modules.governance.domain.jobs.handlers.finops.FinOpsAnalyzer"
        ) as mock_analyzer_cls:
            mock_analyzer = AsyncMock()
            mock_analyzer.analyze.return_value = {
                "insights": ["ok"],
                "recommendations": [],
            }
            mock_analyzer_cls.return_value = mock_analyzer

            with patch(
                "app.modules.governance.domain.jobs.handlers.finops.LLMFactory.create"
            ) as mock_create:
                mock_create.return_value = MagicMock()

                result = await handler.execute(sample_job, mock_db)

                assert result["status"] == "completed"
                assert result["analysis_runs"] == 1
                assert result["analysis_length"] > 0
                mock_analyzer.analyze.assert_called_once()
