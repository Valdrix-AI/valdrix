"""
Targeted tests for app/shared/core/notifications.py missing coverage
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.shared.core.notifications import NotificationDispatcher


class TestNotificationDispatcherCoverage:
    """Test notification dispatcher to achieve full coverage."""

    @pytest.mark.asyncio
    async def test_send_alert_with_slack(self):
        """Test send_alert with Slack service available."""
        mock_slack = AsyncMock()

        with patch(
            "app.shared.core.notifications.get_slack_service", return_value=mock_slack
        ):
            with patch("app.shared.core.notifications.logger") as mock_logger:
                await NotificationDispatcher.send_alert(
                    title="Test Alert", message="Test message", severity="warning"
                )

                mock_slack.send_alert.assert_called_once_with(
                    "Test Alert", "Test message", "warning"
                )
                mock_logger.info.assert_called_once_with(
                    "notification_dispatched", title="Test Alert", severity="warning"
                )

    @pytest.mark.asyncio
    async def test_send_alert_without_slack(self):
        """Test send_alert without Slack service."""
        with patch(
            "app.shared.core.notifications.get_slack_service", return_value=None
        ):
            with patch("app.shared.core.notifications.logger") as mock_logger:
                await NotificationDispatcher.send_alert(
                    title="Test Alert", message="Test message", severity="error"
                )

                # Should not raise exception, just log
                mock_logger.info.assert_called_once_with(
                    "notification_dispatched", title="Test Alert", severity="error"
                )

    @pytest.mark.asyncio
    async def test_send_alert_default_severity(self):
        """Test send_alert with default severity."""
        mock_slack = AsyncMock()

        with patch(
            "app.shared.core.notifications.get_slack_service", return_value=mock_slack
        ):
            with patch("app.shared.core.notifications.logger"):
                await NotificationDispatcher.send_alert(
                    title="Test Alert", message="Test message"
                )

                mock_slack.send_alert.assert_called_once_with(
                    "Test Alert",
                    "Test message",
                    "warning",  # Default severity
                )

    @pytest.mark.asyncio
    async def test_send_alert_tenant_prefers_tenant_settings(self):
        """Tenant-scoped Slack should be preferred when DB context is provided."""
        mock_slack = AsyncMock()
        fake_db = MagicMock()
        with (
            patch(
                "app.shared.core.notifications.get_tenant_slack_service",
                new=AsyncMock(return_value=mock_slack),
            ) as mock_get_tenant,
            patch(
                "app.shared.core.notifications.get_slack_service", return_value=None
            ) as mock_get_env,
        ):
            await NotificationDispatcher.send_alert(
                title="Tenant Alert",
                message="Scoped message",
                severity="warning",
                tenant_id="tenant-100",
                db=fake_db,
            )

        mock_get_tenant.assert_awaited_once_with(fake_db, "tenant-100")
        mock_get_env.assert_not_called()
        mock_slack.send_alert.assert_awaited_once_with(
            "Tenant Alert", "Scoped message", "warning"
        )

    @pytest.mark.asyncio
    async def test_send_alert_tenant_missing_db_does_not_fallback(self):
        """When tenant_id is supplied without DB context, env fallback must not be used."""
        env_slack = AsyncMock()
        with (
            patch(
                "app.shared.core.notifications.get_tenant_slack_service",
                new=AsyncMock(return_value=None),
            ) as mock_get_tenant,
            patch(
                "app.shared.core.notifications.get_slack_service",
                return_value=env_slack,
            ) as mock_get_env,
            patch("app.shared.core.notifications.logger") as mock_logger,
        ):
            await NotificationDispatcher.send_alert(
                title="Tenant Alert",
                message="Scoped message",
                severity="warning",
                tenant_id="tenant-101",
            )

        mock_get_tenant.assert_not_called()
        mock_get_env.assert_not_called()
        env_slack.send_alert.assert_not_awaited()
        mock_logger.warning.assert_called()

    @pytest.mark.asyncio
    async def test_notify_zombies_with_slack(self):
        """Test notify_zombies with Slack service available."""
        mock_slack = AsyncMock()
        zombies_data = {"ec2": [{"id": "i-123", "cost": 50.0}]}

        with patch(
            "app.shared.core.notifications.get_slack_service", return_value=mock_slack
        ):
            await NotificationDispatcher.notify_zombies(
                zombies_data, estimated_savings=150.0
            )

            mock_slack.notify_zombies.assert_called_once_with(zombies_data, 150.0)

    @pytest.mark.asyncio
    async def test_notify_zombies_without_slack(self):
        """Test notify_zombies without Slack service."""
        zombies_data = {"ebs": [{"id": "vol-456", "cost": 25.0}]}

        with patch(
            "app.shared.core.notifications.get_slack_service", return_value=None
        ):
            # Should not raise exception
            await NotificationDispatcher.notify_zombies(
                zombies_data, estimated_savings=75.0
            )

    @pytest.mark.asyncio
    async def test_notify_zombies_tenant_prefers_tenant_settings(self):
        """notify_zombies should use tenant-scoped Slack when tenant context is provided."""
        mock_slack = AsyncMock()
        fake_db = MagicMock()
        zombies_data = {"ec2": [{"id": "i-abc"}]}
        with (
            patch(
                "app.shared.core.notifications.get_tenant_slack_service",
                new=AsyncMock(return_value=mock_slack),
            ) as mock_get_tenant,
            patch(
                "app.shared.core.notifications.get_slack_service", return_value=None
            ) as mock_get_env,
        ):
            await NotificationDispatcher.notify_zombies(
                zombies_data,
                estimated_savings=42.0,
                tenant_id="tenant-200",
                db=fake_db,
            )

        mock_get_tenant.assert_awaited_once_with(fake_db, "tenant-200")
        mock_get_env.assert_not_called()
        mock_slack.notify_zombies.assert_awaited_once_with(zombies_data, 42.0)

    @pytest.mark.asyncio
    async def test_notify_budget_alert_with_slack(self):
        """Test notify_budget_alert with Slack service available."""
        mock_slack = AsyncMock()

        with patch(
            "app.shared.core.notifications.get_slack_service", return_value=mock_slack
        ):
            await NotificationDispatcher.notify_budget_alert(
                current_spend=850.0, budget_limit=1000.0, percent_used=85.0
            )

            mock_slack.notify_budget_alert.assert_called_once_with(850.0, 1000.0, 85.0)

    @pytest.mark.asyncio
    async def test_notify_budget_alert_without_slack(self):
        """Test notify_budget_alert without Slack service."""
        with patch(
            "app.shared.core.notifications.get_slack_service", return_value=None
        ):
            # Should not raise exception
            await NotificationDispatcher.notify_budget_alert(
                current_spend=1200.0, budget_limit=1000.0, percent_used=120.0
            )

    @pytest.mark.asyncio
    async def test_notify_budget_alert_tenant_prefers_tenant_settings(self):
        """notify_budget_alert should use tenant-scoped Slack when tenant context is provided."""
        mock_slack = AsyncMock()
        fake_db = MagicMock()
        with (
            patch(
                "app.shared.core.notifications.get_tenant_slack_service",
                new=AsyncMock(return_value=mock_slack),
            ) as mock_get_tenant,
            patch(
                "app.shared.core.notifications.get_slack_service", return_value=None
            ) as mock_get_env,
        ):
            await NotificationDispatcher.notify_budget_alert(
                current_spend=850.0,
                budget_limit=1000.0,
                percent_used=85.0,
                tenant_id="tenant-300",
                db=fake_db,
            )

        mock_get_tenant.assert_awaited_once_with(fake_db, "tenant-300")
        mock_get_env.assert_not_called()
        mock_slack.notify_budget_alert.assert_awaited_once_with(850.0, 1000.0, 85.0)

    @pytest.mark.asyncio
    async def test_notify_remediation_completed(self):
        """Test notify_remediation_completed."""
        mock_slack = AsyncMock()
        fake_db = MagicMock()

        with (
            patch(
                "app.shared.core.notifications.get_tenant_slack_service",
                new=AsyncMock(return_value=mock_slack),
            ) as mock_get_tenant,
            patch(
                "app.shared.core.notifications.get_slack_service", return_value=None
            ) as mock_get_env,
        ):
            with patch("app.shared.core.notifications.logger") as mock_logger:
                await NotificationDispatcher.notify_remediation_completed(
                    tenant_id="tenant-123",
                    resource_id="i-456789",
                    action="terminate",
                    savings=75.50,
                    db=fake_db,
                )

                # Verify send_alert was called with correct parameters
                mock_slack.send_alert.assert_called_once()
                call_args = mock_slack.send_alert.call_args[0]

                assert call_args[0] == "Remediation Successful: Terminate i-456789"
                assert "Tenant: tenant-123" in call_args[1]
                assert "Resource: i-456789" in call_args[1]
                assert "Action: terminate" in call_args[1]
                assert "Monthly Savings: $75.50" in call_args[1]
                assert call_args[2] == "info"
                mock_get_tenant.assert_awaited_once_with(fake_db, "tenant-123")
                mock_get_env.assert_not_called()

                mock_logger.info.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_policy_event_slack_only(self):
        """Policy notification should dispatch to Slack when enabled."""
        mock_slack = AsyncMock()
        with (
            patch(
                "app.shared.core.notifications.get_slack_service",
                return_value=mock_slack,
            ),
            patch("app.shared.core.notifications.get_jira_service", return_value=None),
        ):
            await NotificationDispatcher.notify_policy_event(
                tenant_id="tenant-1",
                decision="block",
                summary="Blocked by policy",
                resource_id="prod-bucket",
                action="delete_s3_bucket",
                notify_slack=True,
                notify_jira=False,
            )

        mock_slack.send_alert.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_policy_event_jira_only(self):
        """Policy notification should dispatch to Jira when enabled."""
        mock_jira = AsyncMock()
        with (
            patch("app.shared.core.notifications.get_slack_service", return_value=None),
            patch(
                "app.shared.core.notifications.get_tenant_jira_service",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.shared.core.notifications.get_jira_service", return_value=mock_jira
            ),
        ):
            await NotificationDispatcher.notify_policy_event(
                tenant_id="tenant-1",
                decision="escalate",
                summary="GPU change requires approval",
                resource_id="gpu-node",
                action="terminate_instance",
                notify_slack=False,
                notify_jira=True,
            )

        mock_jira.create_policy_issue.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_policy_event_jira_prefers_tenant_settings(self):
        """Tenant-scoped Jira settings should be preferred when DB context is available."""
        mock_jira = AsyncMock()
        fake_db = MagicMock()
        with (
            patch("app.shared.core.notifications.get_slack_service", return_value=None),
            patch(
                "app.shared.core.notifications.get_tenant_jira_service",
                new=AsyncMock(return_value=mock_jira),
            ) as mock_get_tenant,
            patch(
                "app.shared.core.notifications.get_jira_service", return_value=None
            ) as mock_get_env,
        ):
            await NotificationDispatcher.notify_policy_event(
                tenant_id="tenant-42",
                decision="block",
                summary="Policy block summary",
                resource_id="prod-db",
                action="delete_rds_instance",
                notify_slack=False,
                notify_jira=True,
                db=fake_db,
            )

        mock_get_tenant.assert_awaited_once_with(fake_db, "tenant-42")
        mock_get_env.assert_not_called()
        mock_jira.create_policy_issue.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_notify_policy_event_slack_prefers_tenant_settings(self):
        """Tenant-scoped Slack settings should be preferred when DB context is available."""
        mock_slack = AsyncMock()
        fake_db = MagicMock()
        with (
            patch(
                "app.shared.core.notifications.get_tenant_slack_service",
                new=AsyncMock(return_value=mock_slack),
            ) as mock_get_tenant,
            patch(
                "app.shared.core.notifications.get_slack_service", return_value=None
            ) as mock_get_env,
        ):
            await NotificationDispatcher.notify_policy_event(
                tenant_id="tenant-55",
                decision="escalate",
                summary="Need owner approval",
                resource_id="gpu-node-1",
                action="terminate_instance",
                notify_slack=True,
                notify_jira=False,
                db=fake_db,
            )

        mock_get_tenant.assert_awaited_once_with(fake_db, "tenant-55")
        mock_get_env.assert_not_called()
        mock_slack.send_alert.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_notify_policy_event_slack_no_fallback_when_tenant_context_present(
        self,
    ):
        """If tenant-scoped Slack is unavailable, do not fallback to env service when DB is provided."""
        env_slack = AsyncMock()
        fake_db = MagicMock()
        with (
            patch(
                "app.shared.core.notifications.get_tenant_slack_service",
                new=AsyncMock(return_value=None),
            ) as mock_get_tenant,
            patch(
                "app.shared.core.notifications.get_slack_service",
                return_value=env_slack,
            ) as mock_get_env,
            patch("app.shared.core.notifications.logger") as mock_logger,
        ):
            await NotificationDispatcher.notify_policy_event(
                tenant_id="tenant-56",
                decision="block",
                summary="Blocked by policy",
                resource_id="prod-rds",
                action="delete_rds_instance",
                notify_slack=True,
                notify_jira=False,
                db=fake_db,
            )

        mock_get_tenant.assert_awaited_once_with(fake_db, "tenant-56")
        mock_get_env.assert_not_called()
        env_slack.send_alert.assert_not_awaited()
        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_policy_event_jira_no_fallback_when_tenant_context_present(
        self,
    ):
        """If tenant-scoped Jira is unavailable, do not fallback to env service when DB is provided."""
        env_jira = AsyncMock()
        fake_db = MagicMock()
        with (
            patch(
                "app.shared.core.notifications.get_tenant_jira_service",
                new=AsyncMock(return_value=None),
            ) as mock_get_tenant,
            patch(
                "app.shared.core.notifications.get_jira_service", return_value=env_jira
            ) as mock_get_env,
            patch("app.shared.core.notifications.logger") as mock_logger,
        ):
            await NotificationDispatcher.notify_policy_event(
                tenant_id="tenant-57",
                decision="escalate",
                summary="Requires owner approval",
                resource_id="gpu-node-2",
                action="terminate_instance",
                notify_slack=False,
                notify_jira=True,
                db=fake_db,
            )

        mock_get_tenant.assert_awaited_once_with(fake_db, "tenant-57")
        mock_get_env.assert_not_called()
        env_jira.create_policy_issue.assert_not_awaited()
        mock_logger.warning.assert_called_once()

    @pytest.mark.asyncio
    async def test_notify_policy_event_workflow_dispatches_with_evidence_links(self):
        """Policy workflow dispatch should include deterministic evidence links."""
        workflow = MagicMock()
        workflow.provider = "github_actions"
        workflow.dispatch = AsyncMock(return_value=True)
        fake_db = MagicMock()
        with (
            patch("app.shared.core.notifications.get_slack_service", return_value=None),
            patch("app.shared.core.notifications.get_jira_service", return_value=None),
            patch(
                "app.shared.core.notifications.get_tenant_workflow_dispatchers",
                new=AsyncMock(return_value=[workflow]),
            ),
        ):
            await NotificationDispatcher.notify_policy_event(
                tenant_id="tenant-1",
                decision="block",
                summary="blocked by guardrail",
                resource_id="prod-db",
                action="delete_rds_instance",
                notify_slack=False,
                notify_jira=False,
                notify_workflow=True,
                request_id="req-1",
                db=fake_db,
            )

        workflow.dispatch.assert_awaited_once()
        payload = workflow.dispatch.await_args.args[1]
        assert payload["request_id"] == "req-1"
        assert "evidence_links" in payload
        assert "remediation_plan_api" in payload["evidence_links"]

    @pytest.mark.asyncio
    async def test_notify_remediation_completed_workflow_dispatches(self):
        """Completion workflow dispatch should include remediation status payload."""
        workflow = MagicMock()
        workflow.provider = "gitlab_ci"
        workflow.dispatch = AsyncMock(return_value=True)
        fake_db = MagicMock()
        with (
            patch("app.shared.core.notifications.get_slack_service", return_value=None),
            patch(
                "app.shared.core.notifications.get_tenant_workflow_dispatchers",
                new=AsyncMock(return_value=[workflow]),
            ),
        ):
            await NotificationDispatcher.notify_remediation_completed(
                tenant_id="tenant-1",
                resource_id="i-abc",
                action="terminate_instance",
                savings=12.34,
                request_id="req-2",
                provider="aws",
                notify_workflow=True,
                db=fake_db,
            )

        workflow.dispatch.assert_awaited_once()
        payload = workflow.dispatch.await_args.args[1]
        assert payload["status"] == "completed"
        assert payload["provider"] == "aws"

    @pytest.mark.asyncio
    async def test_notify_policy_event_workflow_prefers_tenant_dispatchers(self):
        """Workflow dispatch should use tenant-scoped dispatchers when DB context is provided."""
        workflow = MagicMock()
        workflow.provider = "github_actions"
        workflow.dispatch = AsyncMock(return_value=True)
        fake_db = MagicMock()
        with (
            patch(
                "app.shared.core.notifications.get_tenant_workflow_dispatchers",
                new=AsyncMock(return_value=[workflow]),
            ) as tenant_dispatchers,
            patch(
                "app.shared.core.notifications.get_workflow_dispatchers",
                return_value=[],
            ) as env_dispatchers,
        ):
            await NotificationDispatcher.notify_policy_event(
                tenant_id="tenant-db",
                decision="escalate",
                summary="db-backed workflow dispatch",
                resource_id="gpu-node",
                action="terminate_instance",
                notify_slack=False,
                notify_jira=False,
                notify_workflow=True,
                request_id="req-db-1",
                db=fake_db,
            )

        tenant_dispatchers.assert_awaited_once_with(fake_db, "tenant-db")
        env_dispatchers.assert_not_called()
        workflow.dispatch.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_notify_policy_event_workflow_no_env_fallback_with_db_context(self):
        """When DB context is present, missing tenant workflow settings must not fallback to env dispatchers."""
        fake_db = MagicMock()
        env_workflow = MagicMock()
        env_workflow.provider = "github_actions"
        env_workflow.dispatch = AsyncMock(return_value=True)
        with (
            patch(
                "app.shared.core.notifications.get_tenant_workflow_dispatchers",
                new=AsyncMock(return_value=[]),
            ) as tenant_dispatchers,
            patch(
                "app.shared.core.notifications.get_workflow_dispatchers",
                return_value=[env_workflow],
            ) as env_dispatchers,
        ):
            await NotificationDispatcher.notify_policy_event(
                tenant_id="tenant-no-config",
                decision="block",
                summary="No tenant workflow config",
                resource_id="prod-db",
                action="delete_rds_instance",
                notify_slack=False,
                notify_jira=False,
                notify_workflow=True,
                request_id="req-nofallback",
                db=fake_db,
            )

        tenant_dispatchers.assert_awaited_once_with(fake_db, "tenant-no-config")
        env_dispatchers.assert_not_called()
        env_workflow.dispatch.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_notify_policy_event_workflow_no_env_fallback_when_db_context_missing(
        self,
    ):
        """When tenant context exists without DB context, workflow dispatch must not fallback to env dispatchers."""
        env_workflow = MagicMock()
        env_workflow.provider = "github_actions"
        env_workflow.dispatch = AsyncMock(return_value=True)
        with (
            patch(
                "app.shared.core.notifications.get_tenant_workflow_dispatchers",
                new=AsyncMock(return_value=[env_workflow]),
            ) as tenant_dispatchers,
            patch(
                "app.shared.core.notifications.get_workflow_dispatchers",
                return_value=[env_workflow],
            ) as env_dispatchers,
        ):
            await NotificationDispatcher.notify_policy_event(
                tenant_id="tenant-missing-db",
                decision="block",
                summary="No DB context",
                resource_id="prod-db",
                action="delete_rds_instance",
                notify_slack=False,
                notify_jira=False,
                notify_workflow=True,
                request_id="req-nodb",
                db=None,
            )

        tenant_dispatchers.assert_not_awaited()
        env_dispatchers.assert_not_called()
        env_workflow.dispatch.assert_not_awaited()
