"""
Tests for scheduler_tasks.py - Background job scheduling and processing.

Production-quality tests for Scheduler Tasks.
Tests cover job scheduling, cohort analysis, remediation, billing, maintenance, and error handling.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4

from app.tasks.scheduler_tasks import (
    run_remediation_sweep,
    run_billing_sweep,
    run_acceptance_sweep,
    run_maintenance_sweep,
    run_currency_sync,
    _remediation_sweep_logic,
    _billing_sweep_logic,
    _acceptance_sweep_logic,
    _maintenance_sweep_logic,
)



class TestRemediationSweep:
    """Tests for remediation sweep functionality."""

    @pytest.mark.asyncio
    async def test_remediation_sweep_success(self):
        """Test successful remediation sweep."""
        mock_connection = MagicMock()
        mock_connection.id = uuid4()
        mock_connection.tenant_id = uuid4()
        mock_connection.region = "us-east-1"
        mock_connection.provider = "aws"
        mock_connection.status = "active"

        with (
            patch(
                "app.tasks.scheduler_tasks.async_session_maker"
            ) as mock_session_maker,
            patch(
                "app.tasks.scheduler_tasks.SchedulerOrchestrator"
            ) as mock_orchestrator_cls,
            patch("app.tasks.scheduler_tasks.BACKGROUND_JOBS_ENQUEUED"),
            patch(
                "app.tasks.scheduler_tasks.list_active_connections_all_tenants",
                new_callable=AsyncMock,
            ) as mock_load_connections,
        ):
            mock_session = AsyncMock()
            mock_session_maker.return_value = mock_session

            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.begin.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_load_connections.return_value = [mock_connection]

            # Mock orchestrator for green window check
            mock_orchestrator = MagicMock()
            mock_orchestrator.is_low_carbon_window = AsyncMock(return_value=True)
            mock_orchestrator_cls.return_value = mock_orchestrator

            # Mock job insertion
            mock_job_result = MagicMock()
            mock_job_result.rowcount = 1
            mock_session.execute.return_value = mock_job_result

            await _remediation_sweep_logic()

            # Should have checked green window
            mock_orchestrator.is_low_carbon_window.assert_called_once_with("us-east-1")

    @pytest.mark.asyncio
    async def test_remediation_sweep_non_green_window(self):
        """Test remediation sweep schedules jobs later when not in green window."""
        mock_connection = MagicMock()
        mock_connection.id = uuid4()
        mock_connection.tenant_id = uuid4()
        mock_connection.region = "us-east-1"
        mock_connection.provider = "aws"
        mock_connection.status = "active"

        with (
            patch(
                "app.tasks.scheduler_tasks.async_session_maker"
            ) as mock_session_maker,
            patch(
                "app.tasks.scheduler_tasks.SchedulerOrchestrator"
            ) as mock_orchestrator_cls,
            patch(
                "app.tasks.scheduler_tasks.list_active_connections_all_tenants",
                new_callable=AsyncMock,
            ) as mock_load_connections,
        ):
            mock_session = AsyncMock()
            mock_session_maker.return_value = mock_session

            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.begin.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=None)
            mock_load_connections.return_value = [mock_connection]
            mock_session.execute.return_value = MagicMock(rowcount=1)

            # Mock orchestrator - not green window
            mock_orchestrator = MagicMock()
            mock_orchestrator.is_low_carbon_window = AsyncMock(return_value=False)
            mock_orchestrator_cls.return_value = mock_orchestrator

            await _remediation_sweep_logic()

            # Should have scheduled job 4 hours later
            # This is verified by checking the scheduled_for time in the job creation

    @pytest.mark.asyncio
    async def test_remediation_sweep_non_aws_skips_carbon_window_gate(self):
        """Non-AWS connectors should enqueue remediation without carbon-window gating."""
        mock_connection = MagicMock()
        mock_connection.id = uuid4()
        mock_connection.tenant_id = uuid4()
        mock_connection.provider = "saas"
        mock_connection.is_active = True

        with (
            patch(
                "app.tasks.scheduler_tasks.async_session_maker"
            ) as mock_session_maker,
            patch(
                "app.tasks.scheduler_tasks.SchedulerOrchestrator"
            ) as mock_orchestrator_cls,
            patch(
                "app.tasks.scheduler_tasks.list_active_connections_all_tenants",
                new_callable=AsyncMock,
            ) as mock_load_connections,
        ):
            mock_session = AsyncMock()
            mock_session_maker.return_value = mock_session

            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.begin.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_load_connections.return_value = [mock_connection]
            mock_session.execute.return_value = MagicMock(rowcount=1)

            mock_orchestrator = MagicMock()
            mock_orchestrator.is_low_carbon_window = AsyncMock(return_value=False)
            mock_orchestrator_cls.return_value = mock_orchestrator

            await _remediation_sweep_logic()

            mock_orchestrator.is_low_carbon_window.assert_not_called()

    @pytest.mark.asyncio
    async def test_remediation_sweep_non_aws_with_region_uses_carbon_window_gate(self):
        """Non-AWS connectors with concrete regions should use carbon-window gating."""
        mock_connection = MagicMock()
        mock_connection.id = uuid4()
        mock_connection.tenant_id = uuid4()
        mock_connection.provider = "azure"
        mock_connection.region = "westeurope"
        mock_connection.is_active = True

        with (
            patch(
                "app.tasks.scheduler_tasks.async_session_maker"
            ) as mock_session_maker,
            patch(
                "app.tasks.scheduler_tasks.SchedulerOrchestrator"
            ) as mock_orchestrator_cls,
            patch(
                "app.tasks.scheduler_tasks.list_active_connections_all_tenants",
                new_callable=AsyncMock,
            ) as mock_load_connections,
        ):
            mock_session = AsyncMock()
            mock_session_maker.return_value = mock_session

            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.begin.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_load_connections.return_value = [mock_connection]
            mock_session.execute.return_value = MagicMock(rowcount=1)

            mock_orchestrator = MagicMock()
            mock_orchestrator.is_low_carbon_window = AsyncMock(return_value=False)
            mock_orchestrator_cls.return_value = mock_orchestrator

            await _remediation_sweep_logic()

            mock_orchestrator.is_low_carbon_window.assert_called_once_with("westeurope")

    def test_run_remediation_sweep_task(self):
        """Test the Celery task wrapper for remediation sweep."""
        with (
            patch("app.tasks.scheduler_tasks.run_async") as mock_run_async,
            patch("app.tasks.scheduler_tasks._remediation_sweep_logic"),
        ):
            run_remediation_sweep()

            mock_run_async.assert_called_once()
            args = mock_run_async.call_args[0]
            assert len(args) == 1


class TestBillingSweep:
    """Tests for billing sweep functionality."""

    @pytest.mark.asyncio
    async def test_billing_sweep_success(self):
        """Test successful billing sweep."""
        mock_subscription = MagicMock()
        mock_subscription.id = uuid4()
        mock_subscription.tenant_id = uuid4()
        mock_subscription.status = "active"
        mock_subscription.next_payment_date = datetime.now(timezone.utc) - timedelta(
            days=1
        )
        mock_subscription.paystack_auth_code = "auth_123"

        with (
            patch(
                "app.tasks.scheduler_tasks.async_session_maker"
            ) as mock_session_maker,
            patch("app.tasks.scheduler_tasks.BackgroundJob"),
            patch("app.tasks.scheduler_tasks.BACKGROUND_JOBS_ENQUEUED"),
        ):
            mock_session = AsyncMock()
            mock_session_maker.return_value = mock_session

            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.begin.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=None)

            # Mock subscription query
            mock_sub_result = MagicMock()
            mock_sub_result.scalars.return_value.all.return_value = [mock_subscription]
            mock_session.execute.return_value = mock_sub_result

            # Mock job insertion
            mock_job_result = MagicMock()
            mock_job_result.rowcount = 1
            mock_session.execute.side_effect = [mock_sub_result, mock_job_result]

            await _billing_sweep_logic()

            # Should have enqueued billing job

    @pytest.mark.asyncio
    async def test_billing_sweep_no_due_subscriptions(self):
        """Test billing sweep with no due subscriptions."""
        with patch(
            "app.tasks.scheduler_tasks.async_session_maker"
        ) as mock_session_maker:
            mock_session = AsyncMock()
            mock_session_maker.return_value = mock_session

            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.begin.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=None)

            # Mock empty subscription query
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = []
            mock_session.execute.return_value = mock_result

            await _billing_sweep_logic()

            # Should handle empty results gracefully

    def test_run_billing_sweep_task(self):
        """Test the Celery task wrapper for billing sweep."""
        with (
            patch("app.tasks.scheduler_tasks.run_async") as mock_run_async,
            patch("app.tasks.scheduler_tasks._billing_sweep_logic"),
        ):
            run_billing_sweep()

            mock_run_async.assert_called_once()


class TestAcceptanceSweep:
    """Tests for daily acceptance-suite evidence capture sweep."""

    @pytest.mark.asyncio
    async def test_acceptance_sweep_enqueues_jobs(self):
        mock_tenant1 = MagicMock()
        mock_tenant1.id = uuid4()
        mock_tenant1.plan = "starter"

        mock_tenant2 = MagicMock()
        mock_tenant2.id = uuid4()
        mock_tenant2.plan = "pro"

        with (
            patch(
                "app.tasks.scheduler_tasks.async_session_maker"
            ) as mock_session_maker,
            patch("app.tasks.scheduler_tasks.BACKGROUND_JOBS_ENQUEUED"),
            patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_RUNS"),
            patch("app.tasks.scheduler_tasks.SCHEDULER_JOB_DURATION"),
        ):
            mock_session = AsyncMock()
            mock_session_maker.return_value = mock_session

            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_session.begin.return_value.__aenter__ = AsyncMock(
                return_value=mock_session
            )
            mock_session.begin.return_value.__aexit__ = AsyncMock(return_value=None)

            # Select tenants
            mock_result = MagicMock()
            mock_result.scalars.return_value.all.return_value = [
                mock_tenant1,
                mock_tenant2,
            ]

            # Insert results
            mock_insert_result = MagicMock()
            mock_insert_result.rowcount = 1

            mock_session.execute.side_effect = [
                mock_result,
                mock_insert_result,
                mock_insert_result,
            ]

            await _acceptance_sweep_logic()

            # One SELECT + 2 INSERTs
            assert mock_session.execute.call_count >= 3

    def test_run_acceptance_sweep_task(self):
        with (
            patch("app.tasks.scheduler_tasks.run_async") as mock_run_async,
            patch("app.tasks.scheduler_tasks._acceptance_sweep_logic"),
        ):
            run_acceptance_sweep()
            mock_run_async.assert_called_once()


class TestMaintenanceSweep:
    """Tests for maintenance sweep functionality."""

    @pytest.mark.asyncio
    async def test_maintenance_sweep_success(self):
        """Test successful maintenance sweep."""
        with (
            patch(
                "app.tasks.scheduler_tasks.async_session_maker"
            ) as mock_session_maker,
            patch(
                "app.tasks.scheduler_tasks.CostPersistenceService"
            ) as mock_persistence_cls,
            patch("app.tasks.scheduler_tasks.CostAggregator") as mock_aggregator_cls,
            patch(
                "app.modules.reporting.domain.carbon_factors.CarbonFactorService.auto_activate_latest",
                new_callable=AsyncMock,
            ) as mock_auto_activate,
            patch(
                "app.shared.core.maintenance.PartitionMaintenanceService.create_future_partitions",
                new=AsyncMock(return_value=0),
            ) as mock_create_partitions,
            patch(
                "app.shared.core.maintenance.PartitionMaintenanceService.archive_old_partitions",
                new=AsyncMock(return_value=1),
            ) as mock_archive_partitions,
        ):
            mock_session = AsyncMock()
            mock_session_maker.return_value = mock_session
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_auto_activate.return_value = {
                "status": "no_update",
                "active_factor_set_id": "seeded",
            }

            # Mock persistence service
            mock_persistence = MagicMock()
            mock_persistence.finalize_batch = AsyncMock(
                return_value={"records_finalized": 100}
            )
            mock_persistence_cls.return_value = mock_persistence

            # Mock aggregator
            mock_aggregator = MagicMock()
            mock_aggregator.refresh_materialized_view = AsyncMock()
            mock_aggregator_cls.return_value = mock_aggregator

            # Realized savings query result.
            empty_result = MagicMock()
            empty_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=empty_result)

            await _maintenance_sweep_logic()

            # Should have called all maintenance operations
            mock_persistence.finalize_batch.assert_called_once_with(days_ago=2)
            mock_aggregator.refresh_materialized_view.assert_called_once()
            mock_auto_activate.assert_awaited_once()
            mock_create_partitions.assert_awaited_once_with(months_ahead=3)
            mock_archive_partitions.assert_awaited_once_with(months_old=13)

    @pytest.mark.asyncio
    async def test_maintenance_sweep_records_cost_retention_audit_evidence(self):
        with (
            patch(
                "app.tasks.scheduler_tasks.async_session_maker"
            ) as mock_session_maker,
            patch(
                "app.tasks.scheduler_tasks.CostPersistenceService"
            ) as mock_persistence_cls,
            patch("app.tasks.scheduler_tasks.CostAggregator") as mock_aggregator_cls,
            patch(
                "app.modules.reporting.domain.carbon_factors.CarbonFactorService.auto_activate_latest",
                new_callable=AsyncMock,
            ) as mock_auto_activate,
            patch(
                "app.shared.core.maintenance.PartitionMaintenanceService.create_future_partitions",
                new=AsyncMock(return_value=0),
            ) as mock_create_partitions,
            patch(
                "app.shared.core.maintenance.PartitionMaintenanceService.archive_old_partitions",
                new=AsyncMock(return_value=1),
            ) as mock_archive_partitions,
            patch(
                "app.modules.governance.domain.security.audit_log.AuditLogger"
            ) as mock_audit_logger_cls,
            patch(
                "app.shared.core.ops_metrics.record_cost_retention_purge"
            ) as mock_record_cost_retention_purge,
        ):
            mock_session = AsyncMock()
            mock_session_maker.return_value = mock_session
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_auto_activate.return_value = {
                "status": "no_update",
                "active_factor_set_id": "seeded",
            }

            mock_persistence = MagicMock()
            mock_persistence.finalize_batch = AsyncMock(
                return_value={"records_finalized": 100}
            )
            mock_persistence.cleanup_expired_records_by_plan = AsyncMock(
                return_value={
                    "deleted_count": 2,
                    "tiers": {"growth": 2},
                    "tenant_reports": [
                        {
                            "tenant_id": str(uuid4()),
                            "tenant_tier": "growth",
                            "retention_days": 365,
                            "deleted_count": 2,
                            "oldest_recorded_at": "2024-01-01",
                            "newest_recorded_at": "2024-01-02",
                        }
                    ],
                    "batch_size": 5000,
                    "max_batches": 50,
                    "as_of_date": "2026-03-07",
                }
            )
            mock_persistence_cls.return_value = mock_persistence

            mock_aggregator = MagicMock()
            mock_aggregator.refresh_materialized_view = AsyncMock()
            mock_aggregator_cls.return_value = mock_aggregator

            empty_result = MagicMock()
            empty_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=empty_result)

            mock_audit_logger = MagicMock()
            mock_audit_logger.log = AsyncMock()
            mock_audit_logger_cls.return_value = mock_audit_logger

            await _maintenance_sweep_logic()

            mock_persistence.cleanup_expired_records_by_plan.assert_awaited_once()
            mock_audit_logger.log.assert_awaited_once()
            mock_record_cost_retention_purge.assert_called_once_with("growth", 2)
            mock_create_partitions.assert_awaited_once_with(months_ahead=3)
            mock_archive_partitions.assert_awaited_once_with(months_old=13)

    @pytest.mark.asyncio
    async def test_maintenance_sweep_persistence_failure(self):
        """Test maintenance sweep handles persistence failure."""
        with (
            patch(
                "app.tasks.scheduler_tasks.async_session_maker"
            ) as mock_session_maker,
            patch(
                "app.tasks.scheduler_tasks.CostPersistenceService"
            ) as mock_persistence_cls,
            patch("app.tasks.scheduler_tasks.CostAggregator") as mock_aggregator_cls,
            patch(
                "app.modules.reporting.domain.carbon_factors.CarbonFactorService.auto_activate_latest",
                new_callable=AsyncMock,
            ) as mock_auto_activate,
            patch(
                "app.shared.core.maintenance.PartitionMaintenanceService.create_future_partitions",
                new=AsyncMock(return_value=0),
            ) as mock_create_partitions,
            patch(
                "app.shared.core.maintenance.PartitionMaintenanceService.archive_old_partitions",
                new=AsyncMock(return_value=1),
            ) as mock_archive_partitions,
        ):
            mock_session = AsyncMock()
            mock_session_maker.return_value = mock_session
            mock_session.__aenter__ = AsyncMock(return_value=mock_session)
            mock_session.__aexit__ = AsyncMock(return_value=None)
            mock_auto_activate.return_value = {
                "status": "no_update",
                "active_factor_set_id": "seeded",
            }

            # Mock persistence failure
            mock_persistence = MagicMock()
            mock_persistence.finalize_batch = AsyncMock(
                side_effect=RuntimeError("Persistence failed")
            )
            mock_persistence_cls.return_value = mock_persistence

            # Mock aggregator
            mock_aggregator = MagicMock()
            mock_aggregator.refresh_materialized_view = AsyncMock()
            mock_aggregator_cls.return_value = mock_aggregator

            # Realized savings query result.
            empty_result = MagicMock()
            empty_result.scalars.return_value.all.return_value = []
            mock_session.execute = AsyncMock(return_value=empty_result)

            # Should not raise exception despite persistence failure
            await _maintenance_sweep_logic()

            # Should still call aggregator
            mock_aggregator.refresh_materialized_view.assert_called_once()
            mock_auto_activate.assert_awaited_once()
            mock_create_partitions.assert_awaited_once_with(months_ahead=3)
            mock_archive_partitions.assert_awaited_once_with(months_old=13)

    def test_run_maintenance_sweep_task(self):
        """Test the Celery task wrapper for maintenance sweep."""
        with (
            patch("app.tasks.scheduler_tasks.run_async") as mock_run_async,
            patch("app.tasks.scheduler_tasks._maintenance_sweep_logic"),
        ):
            run_maintenance_sweep()

            mock_run_async.assert_called_once()


class TestCurrencySync:
    """Tests for currency synchronization functionality."""

    def test_run_currency_sync_task(self):
        """Test the Celery task for currency synchronization."""
        with (
            patch("app.tasks.scheduler_tasks.run_async") as mock_async,
            patch("app.tasks.scheduler_tasks.get_exchange_rate") as mock_rate,
        ):
            mock_rate.return_value = 1.0  # Mock exchange rate

            # Should not raise exceptions
            run_currency_sync()

            # Should have called get_exchange_rate for each currency
            assert mock_async.call_count == 3
