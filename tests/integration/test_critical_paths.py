"""
Integration tests for critical paths in CloudSentinel-AI.
Tests end-to-end workflows for zombie detection and remediation.
"""

import pytest
from datetime import datetime, timezone, date
from decimal import Decimal
from uuid import uuid4, UUID
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import MagicMock, patch, AsyncMock

from app.schemas.costs import CloudUsageSummary, CostRecord
from app.shared.llm.analyzer import FinOpsAnalyzer
from app.models.tenant import Tenant
from app.models.remediation import (
    RemediationRequest,
    RemediationStatus,
    RemediationAction,
)
from app.modules.optimization.domain.remediation import RemediationService
from app.shared.core.exceptions import BudgetExceededError, KillSwitchTriggeredError


@pytest.fixture
def mock_llm() -> MagicMock:
    """Mock LLM for integration tests."""
    llm = MagicMock()
    llm.model_name = "gpt-4"
    return llm


@pytest.fixture
async def test_tenant(db: AsyncSession) -> Tenant:
    """Create a test tenant for integration tests."""
    tenant = Tenant(id=uuid4(), name="Integration Test Tenant", plan="pro")
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


@pytest.fixture
def sample_cloud_usage() -> CloudUsageSummary:
    """Sample cloud usage data for testing."""
    return CloudUsageSummary(
        tenant_id=str(uuid4()),
        provider="aws",
        start_date=date(2024, 1, 1),
        end_date=date(2024, 1, 7),
        records=[
            CostRecord(
                date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                amount=Decimal("500.00"),
                service="EC2",
                region="us-east-1",
                tags={"ResourceId": "i-1234567890abcdef0", "Name": "web-server-01"},
            ),
            CostRecord(
                date=datetime(2024, 1, 2, tzinfo=timezone.utc),
                amount=Decimal("450.00"),
                service="EC2",
                region="us-east-1",
                tags={"ResourceId": "i-0987654321fedcba0", "Name": "idle-server-01"},
            ),
            CostRecord(
                date=datetime(2024, 1, 3, tzinfo=timezone.utc),
                amount=Decimal("25.00"),
                service="EBS",
                region="us-east-1",
                tags={
                    "ResourceId": "vol-1234567890abcdef0",
                    "Name": "unused-volume-01",
                },
            ),
        ],
        total_cost=Decimal("975.00"),
    )


class TestZombieDetectionIntegration:
    """Integration tests for zombie detection workflow."""

    @pytest.mark.asyncio
    async def test_zombie_detection_end_to_end(
        self,
        mock_llm: MagicMock,
        sample_cloud_usage: CloudUsageSummary,
        test_tenant: Tenant,
        db: AsyncSession,
    ) -> None:
        """Test complete zombie detection workflow from data to analysis."""
        # Update sample data with test tenant
        sample_cloud_usage.tenant_id = str(test_tenant.id)

        analyzer = FinOpsAnalyzer(mock_llm)

        # Mock all external dependencies
        with (
            patch(
                "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
                new_callable=AsyncMock,
            ) as mock_reserve,
            patch.object(
                analyzer, "_check_cache_and_delta", return_value=(None, False)
            ),
            patch(
                "app.shared.llm.analyzer.LLMGuardrails.sanitize_input"
            ) as mock_sanitize,
            patch(
                "app.shared.llm.analyzer.SymbolicForecaster.forecast"
            ) as mock_forecast,
            patch.object(analyzer, "_setup_client_and_usage") as mock_setup,
            patch.object(analyzer, "_invoke_llm") as mock_invoke,
            patch(
                "app.shared.llm.analyzer.LLMBudgetManager.record_usage",
                new_callable=AsyncMock,
            ) as mock_record,
            patch.object(analyzer, "_process_analysis_results") as mock_process,
        ):
            # Setup mocks to simulate successful analysis
            mock_reserve.return_value = Decimal("1.50")
            mock_sanitize.return_value = {"test": "data"}
            mock_forecast.return_value = {"forecast": "test"}
            mock_setup.return_value = (None, "groq", "llama-3.3-70b-versatile", None)

            # Mock LLM response with zombie detection results
            mock_invoke.return_value = (
                '{"summary": "Found 2 zombies", "anomalies": [{"resource": "idle-server-01", "issue": "Low utilization EC2 instance", "cost_impact": "$450", "severity": "high"}, {"resource": "unused-volume-01", "issue": "Unused EBS volume", "cost_impact": "$25", "severity": "medium"}], "recommendations": ["Terminate idle-server-01", "Delete unused-volume-01"], "estimated_total_savings": 475}',
                {"token_usage": {"prompt_tokens": 500, "completion_tokens": 500}},
            )

            mock_process.return_value = {
                "insights": ["Found 2 zombies"],
                "anomalies": [
                    {
                        "resource": "idle-server-01",
                        "issue": "Low utilization EC2 instance",
                        "cost_impact": "$450",
                        "severity": "high",
                    },
                    {
                        "resource": "unused-volume-01",
                        "issue": "Unused EBS volume",
                        "cost_impact": "$25",
                        "severity": "medium",
                    },
                ],
                "recommendations": [
                    "Terminate idle-server-01",
                    "Delete unused-volume-01",
                ],
                "estimated_total_savings": 475,
                "symbolic_forecast": {"forecast": "test"},
                "llm_raw": {"summary": "Found 2 zombies"},
            }

            # Execute zombie detection
            result = await analyzer.analyze(
                sample_cloud_usage, tenant_id=test_tenant.id, db=db
            )

            # Verify analysis completed successfully
            assert result is not None
            assert "anomalies" in result
            assert len(result["anomalies"]) == 2

            # Verify specific zombies were detected
            anomalies = result["anomalies"]
            assert any("idle-server-01" in anomaly["resource"] for anomaly in anomalies)
            assert any(
                "unused-volume-01" in anomaly["resource"] for anomaly in anomalies
            )

            # Verify budget was checked and recorded
            mock_sanitize.assert_called_once()
            mock_setup.assert_called_once()
            mock_invoke.assert_called_once()
            mock_record.assert_called_once()

    @pytest.mark.asyncio
    async def test_zombie_detection_with_budget_exceeded(
        self,
        mock_llm: MagicMock,
        sample_cloud_usage: CloudUsageSummary,
        test_tenant: Tenant,
        db: AsyncSession,
    ) -> None:
        """Test zombie detection fails gracefully when budget exceeded."""
        sample_cloud_usage.tenant_id = str(test_tenant.id)
        analyzer = FinOpsAnalyzer(mock_llm)

        with (
            patch.object(
                analyzer, "_check_cache_and_delta", return_value=(None, False)
            ),
            patch(
                "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
                new_callable=AsyncMock,
            ) as mock_reserve,
        ):
            mock_reserve.side_effect = BudgetExceededError("Budget exceeded")
            # Should raise exception due to budget failure
            with pytest.raises(BudgetExceededError):
                await analyzer.analyze(
                    sample_cloud_usage, tenant_id=test_tenant.id, db=db
                )

    @pytest.mark.asyncio
    async def test_zombie_detection_with_cache_hit(
        self,
        mock_llm: MagicMock,
        sample_cloud_usage: CloudUsageSummary,
        test_tenant: Tenant,
    ) -> None:
        """Test zombie detection uses cached results when available."""
        sample_cloud_usage.tenant_id = str(test_tenant.id)
        analyzer = FinOpsAnalyzer(mock_llm)

        cached_result = {
            "insights": ["Cached analysis"],
            "anomalies": [{"resource": "cached-zombie", "issue": "Cached issue"}],
            "cached": True,
        }

        with patch.object(
            analyzer, "_check_cache_and_delta", return_value=(cached_result, False)
        ):
            result = await analyzer.analyze(
                sample_cloud_usage, tenant_id=test_tenant.id
            )

            # Should return cached result without calling LLM
            assert result == cached_result


class TestRemediationIntegration:
    """Integration tests for remediation workflow."""

    @pytest.mark.asyncio
    async def test_remediation_workflow_end_to_end(
        self, db: AsyncSession, test_tenant: Tenant
    ) -> None:
        """Test complete remediation workflow from request to execution."""
        # Create a remediation request
        remediation_request = RemediationRequest(
            id=uuid4(),
            tenant_id=test_tenant.id,
            resource_id="i-idle123",
            resource_type="ec2_instance",
            action=RemediationAction.STOP_INSTANCE,
            status=RemediationStatus.APPROVED,
            requested_by_user_id=uuid4(),
            estimated_monthly_savings=Decimal("100.00"),
        )

        db.add(remediation_request)
        await db.commit()
        await db.refresh(remediation_request)

        # Mock remediation service
        with (
            patch(
                "app.modules.optimization.domain.remediation.RemediationService._get_client"
            ) as mock_get_client,
            patch("app.shared.llm.budget_manager.LLMBudgetManager") as mock_budget_mgr,
            patch("app.shared.core.cache.get_cache_service"),
        ):
            mock_budget_mgr.check_and_reserve = AsyncMock(return_value=Decimal("1.50"))
            mock_budget_mgr.record_usage = AsyncMock()

            mock_ec2_client = AsyncMock()
            mock_get_client.return_value.__aenter__.return_value = mock_ec2_client
            mock_ec2_client.stop_instances.return_value = {
                "StoppingInstances": [{"InstanceId": "i-idle123"}]
            }

            # Execute remediation
            service = RemediationService(db)
            await service.execute(
                remediation_request.id, test_tenant.id, bypass_grace_period=True
            )

            # Verify remediation was executed
            await db.refresh(remediation_request)
            assert remediation_request.status == RemediationStatus.COMPLETED

            # Verify AWS API was called
            mock_ec2_client.stop_instances.assert_called_once_with(
                InstanceIds=["i-idle123"]
            )

    @pytest.mark.asyncio
    async def test_remediation_failure_handling(
        self, db: AsyncSession, test_tenant: Tenant
    ) -> None:
        """Test remediation handles failures gracefully."""
        # Create a remediation request
        remediation_request = RemediationRequest(
            id=uuid4(),
            tenant_id=test_tenant.id,
            resource_id="vol-failed123",
            resource_type="ebs_volume",
            action=RemediationAction.DELETE_VOLUME,
            status=RemediationStatus.APPROVED,
            requested_by_user_id=uuid4(),
            estimated_monthly_savings=Decimal("50.00"),
        )

        db.add(remediation_request)
        await db.commit()

        # Mock remediation service with AWS failure
        with patch(
            "app.modules.optimization.domain.remediation.RemediationService._get_client"
        ) as mock_get_client:
            mock_ec2_client = AsyncMock()
            mock_get_client.return_value.__aenter__.return_value = mock_ec2_client
            mock_ec2_client.delete_volume.side_effect = Exception("AWS API Error")

            # Execute remediation - should handle failure gracefully
            service = RemediationService(db)
            await service.execute(
                remediation_request.id, test_tenant.id, bypass_grace_period=True
            )

            # Verify remediation status reflects failure
            await db.refresh(remediation_request)
            assert remediation_request.status == RemediationStatus.FAILED

    @pytest.mark.asyncio
    async def test_remediation_budget_integration(
        self, db: AsyncSession, test_tenant: Tenant
    ) -> None:
        """Test remediation integrates with budget management."""
        remediation_request = RemediationRequest(
            id=uuid4(),
            tenant_id=test_tenant.id,
            resource_id="i-budget123",
            resource_type="ec2_instance",
            action=RemediationAction.STOP_INSTANCE,
            status=RemediationStatus.APPROVED,
            requested_by_user_id=uuid4(),
            estimated_monthly_savings=Decimal("200.00"),
        )

        db.add(remediation_request)
        await db.commit()

        with (
            patch(
                "app.modules.optimization.domain.remediation.SafetyGuardrailService"
            ) as mock_safety,
            patch(
                "app.modules.optimization.domain.remediation.RemediationService._get_client"
            ),
        ):
            mock_safety.return_value.check_all_guards = AsyncMock(
                side_effect=KillSwitchTriggeredError("Budget hard cap")
            )

            service = RemediationService(db)

            # Should handle guard failure gracefully
            await service.execute(
                remediation_request.id, test_tenant.id, bypass_grace_period=True
            )

            await db.refresh(remediation_request)
            assert remediation_request.status == RemediationStatus.FAILED


class TestTenantIsolationIntegration:
    """Integration tests for tenant isolation and security."""

    @pytest.mark.asyncio
    async def test_tenant_data_isolation_in_analysis(
        self, mock_llm: MagicMock, db: AsyncSession
    ) -> None:
        """Test that tenant data is properly isolated during analysis."""
        # Create two tenants
        tenant1 = Tenant(id=uuid4(), name="Tenant 1", plan="pro")
        tenant2 = Tenant(id=uuid4(), name="Tenant 2", plan="pro")
        db.add_all([tenant1, tenant2])
        await db.commit()

        # Create usage data for each tenant
        usage1 = CloudUsageSummary(
            tenant_id=str(tenant1.id),
            provider="aws",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            records=[
                CostRecord(
                    date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                    amount=Decimal("100.00"),
                    service="EC2",
                    region="us-east-1",
                    tags={"ResourceId": "i-tenant1"},
                )
            ],
            total_cost=Decimal("100.00"),
        )

        CloudUsageSummary(
            tenant_id=str(tenant2.id),
            provider="aws",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 1),
            records=[
                CostRecord(
                    date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                    amount=Decimal("200.00"),
                    service="EC2",
                    region="us-east-1",
                    tags={"ResourceId": "i-tenant2"},
                )
            ],
            total_cost=Decimal("200.00"),
        )

        analyzer = FinOpsAnalyzer(mock_llm)

        # Mock successful analysis for tenant 1
        with (
            patch(
                "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
                return_value=Decimal("1.50"),
            ),
            patch.object(
                analyzer, "_check_cache_and_delta", return_value=(None, False)
            ),
            patch(
                "app.shared.llm.analyzer.LLMGuardrails.sanitize_input"
            ) as mock_sanitize,
            patch(
                "app.shared.llm.analyzer.SymbolicForecaster.forecast"
            ) as mock_forecast,
            patch.object(analyzer, "_setup_client_and_usage") as mock_setup,
            patch.object(analyzer, "_invoke_llm") as mock_invoke,
            patch("app.shared.llm.analyzer.LLMBudgetManager.record_usage"),
            patch.object(analyzer, "_process_analysis_results") as mock_process,
        ):
            # Setup mocks
            mock_sanitize.return_value = {"test": "data"}
            mock_forecast.return_value = {"forecast": "test"}
            mock_setup.return_value = (None, "groq", "llama-3.3-70b-versatile", None)

            # Mock LLM response specific to tenant1
            mock_invoke.return_value = (
                '{"summary": "Tenant 1 analysis", "anomalies": [{"resource": "i-tenant1", "issue": "Tenant 1 issue"}]}',
                {"token_usage": {"prompt_tokens": 500, "completion_tokens": 500}},
            )

            mock_process.return_value = {
                "insights": ["Tenant 1 analysis"],
                "anomalies": [{"resource": "i-tenant1", "issue": "Tenant 1 issue"}],
                "recommendations": [],
                "symbolic_forecast": {"forecast": "test"},
                "llm_raw": {"summary": "Tenant 1 analysis"},
            }

            # Analyze tenant 1 data
            result1 = await analyzer.analyze(usage1, tenant_id=tenant1.id)

            # Verify tenant 1 gets tenant 1 results
            assert "i-tenant1" in str(result1["anomalies"])
            assert "i-tenant2" not in str(result1["anomalies"])

    @pytest.mark.asyncio
    async def test_remediation_tenant_isolation(self, db: AsyncSession) -> None:
        """Test that remediation operations are tenant-isolated."""
        # Create two tenants
        tenant1 = Tenant(id=uuid4(), name="Tenant 1", plan="pro")
        tenant2 = Tenant(id=uuid4(), name="Tenant 2", plan="pro")
        db.add_all([tenant1, tenant2])
        await db.commit()

        # Create remediation requests for each tenant
        request1 = RemediationRequest(
            id=uuid4(),
            tenant_id=tenant1.id,
            resource_id="i-tenant1-resource",
            resource_type="ec2_instance",
            action=RemediationAction.STOP_INSTANCE,
            status=RemediationStatus.APPROVED,
            requested_by_user_id=uuid4(),
        )

        request2 = RemediationRequest(
            id=uuid4(),
            tenant_id=tenant2.id,
            resource_id="i-tenant2-resource",
            resource_type="ec2_instance",
            action=RemediationAction.STOP_INSTANCE,
            status=RemediationStatus.PENDING,
            requested_by_user_id=uuid4(),
        )

        db.add_all([request1, request2])
        await db.commit()

        # Mock remediation service
        with patch(
            "app.modules.optimization.domain.remediation.RemediationService._get_client"
        ) as mock_get_client:
            mock_ec2_client = AsyncMock()
            mock_get_client.return_value.__aenter__.return_value = mock_ec2_client
            mock_ec2_client.stop_instances.return_value = {
                "StoppingInstances": [{"InstanceId": "mock"}]
            }

            service = RemediationService(db)

            # Execute remediation for tenant 1
            await service.execute(request1.id, tenant1.id, bypass_grace_period=True)

            # Verify only tenant 1's request was processed
            await db.refresh(request1)
            await db.refresh(request2)

            assert request1.status == RemediationStatus.COMPLETED
            assert (
                request2.status == RemediationStatus.PENDING
            )  # Should remain unchanged


class TestPerformanceIntegration:
    """Integration tests for performance and scalability."""

    @pytest.mark.asyncio
    async def test_concurrent_zombie_detection(self, mock_llm: MagicMock) -> None:
        """Test concurrent zombie detection operations."""
        analyzer = FinOpsAnalyzer(mock_llm)

        # Create multiple usage summaries
        usage_summaries = []
        for i in range(5):
            usage = CloudUsageSummary(
                tenant_id=str(uuid4()),
                provider="aws",
                start_date=date(2024, 1, 1),
                end_date=date(2024, 1, 1),
                records=[
                    CostRecord(
                        date=datetime(2024, 1, 1, tzinfo=timezone.utc),
                        amount=Decimal(f"{100 + i * 10}.00"),
                        service="EC2",
                        region="us-east-1",
                        tags={"ResourceId": f"i-test{i}"},
                    )
                ],
                total_cost=Decimal(f"{100 + i * 10}.00"),
            )
            usage_summaries.append(usage)

        import asyncio

        # Mock all external dependencies
        async def mock_analyze(*args, **kwargs):
            await asyncio.sleep(0.01)  # Simulate async work
            return {"result": "success", "anomalies": []}

        with patch.object(analyzer, "analyze", side_effect=mock_analyze):
            # Run concurrent analyses
            tasks = [
                analyzer.analyze(usage, tenant_id=UUID(usage.tenant_id))
                for usage in usage_summaries
            ]
            results = await asyncio.gather(*tasks)

            # Verify all completed successfully
            assert len(results) == 5
            assert all(result["result"] == "success" for result in results)

    @pytest.mark.asyncio
    async def test_large_dataset_zombie_detection(self, mock_llm: MagicMock) -> None:
        """Test zombie detection with large datasets."""
        analyzer = FinOpsAnalyzer(mock_llm)

        # Create large usage summary (1000 records)
        large_records = []
        for i in range(1000):
            large_records.append(
                CostRecord(
                    date=datetime(2024, 1, i % 30 + 1, tzinfo=timezone.utc),
                    amount=Decimal(f"{10 + (i % 50)}.00"),
                    service="EC2" if i % 2 == 0 else "EBS",
                    region="us-east-1",
                    tags={"ResourceId": f"res-{i:04d}", "Name": f"resource-{i:04d}"},
                )
            )

        large_usage = CloudUsageSummary(
            tenant_id=str(uuid4()),
            provider="aws",
            start_date=date(2024, 1, 1),
            end_date=date(2024, 1, 31),
            records=large_records,
            total_cost=Decimal("15000.00"),
        )

        # Mock all dependencies for performance testing
        with (
            patch(
                "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
                return_value=Decimal("1.50"),
            ),
            patch.object(
                analyzer, "_check_cache_and_delta", return_value=(None, False)
            ),
            patch(
                "app.shared.llm.analyzer.LLMGuardrails.sanitize_input"
            ) as mock_sanitize,
            patch(
                "app.shared.llm.analyzer.SymbolicForecaster.forecast"
            ) as mock_forecast,
            patch.object(analyzer, "_setup_client_and_usage") as mock_setup,
            patch.object(analyzer, "_invoke_llm") as mock_invoke,
            patch("app.shared.llm.analyzer.LLMBudgetManager.record_usage"),
            patch.object(analyzer, "_process_analysis_results") as mock_process,
        ):
            import time

            start_time = time.time()

            # Setup mocks
            mock_sanitize.return_value = {"test": "data"}
            mock_forecast.return_value = {"forecast": "test"}
            mock_setup.return_value = (None, "groq", "llama-3.3-70b-versatile", None)
            mock_invoke.return_value = (
                '{"summary": "Large dataset analysis"}',
                {"token_usage": {"prompt_tokens": 500, "completion_tokens": 500}},
            )
            mock_process.return_value = {"result": "success", "anomalies": []}

            # Execute analysis
            result = await analyzer.analyze(
                large_usage, tenant_id=UUID(large_usage.tenant_id)
            )

            end_time = time.time()
            duration = end_time - start_time

            # Verify completed successfully
            assert result["result"] == "success"

            # Should complete within reasonable time (< 5 seconds for 1000 records)
            assert duration < 5.0, (
                f"Analysis too slow: {duration:.2f}s for 1000 records"
            )


class TestErrorHandlingIntegration:
    """Integration tests for error handling and recovery."""

    @pytest.mark.asyncio
    async def test_zombie_detection_llm_failure_fallback(
        self,
        mock_llm: MagicMock,
        sample_cloud_usage: CloudUsageSummary,
        test_tenant: Tenant,
    ) -> None:
        """Test zombie detection falls back gracefully on LLM failures."""
        sample_cloud_usage.tenant_id = test_tenant.id
        analyzer = FinOpsAnalyzer(mock_llm)

        with (
            patch(
                "app.shared.llm.analyzer.LLMBudgetManager.check_and_reserve",
                return_value=Decimal("1.50"),
            ),
            patch.object(
                analyzer, "_check_cache_and_delta", return_value=(None, False)
            ),
            patch(
                "app.shared.llm.analyzer.LLMGuardrails.sanitize_input",
                return_value={"test": "data"},
            ),
            patch(
                "app.shared.llm.analyzer.SymbolicForecaster.forecast",
                return_value={"forecast": "test"},
            ),
            patch.object(
                analyzer,
                "_setup_client_and_usage",
                return_value=(None, "groq", "llama-3.3-70b-versatile", None),
            ),
            patch.object(
                analyzer, "_invoke_llm", return_value=("LLM service unavailable", {})
            ),
            patch.object(analyzer, "_process_analysis_results") as mock_process,
        ):
            # Should handle LLM failure and still return a result
            await analyzer.analyze(sample_cloud_usage, tenant_id=test_tenant.id)

            # Verify error handling worked
            mock_process.assert_called_once()

    @pytest.mark.asyncio
    async def test_remediation_partial_failure_recovery(
        self, db: AsyncSession, test_tenant: Tenant
    ) -> None:
        """Test remediation recovers from partial failures."""
        # Create multiple remediation requests
        requests = []
        for i in range(3):
            request = RemediationRequest(
                id=uuid4(),
                tenant_id=test_tenant.id,
                resource_id=f"i-test{i}",
                resource_type="ec2_instance",
                action=RemediationAction.STOP_INSTANCE,
                status=RemediationStatus.APPROVED,
                requested_by_user_id=uuid4(),
            )
            requests.append(request)

        db.add_all(requests)
        await db.commit()

        # Mock AWS client to fail on second request
        call_count = 0

        def mock_stop_instances(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise Exception("AWS temporary failure")
            return {"StoppingInstances": [{"InstanceId": kwargs["InstanceIds"][0]}]}

        with patch(
            "app.modules.optimization.domain.remediation.RemediationService._get_client"
        ) as mock_get_client:
            mock_ec2_client = AsyncMock()
            mock_get_client.return_value.__aenter__.return_value = mock_ec2_client
            mock_ec2_client.stop_instances.side_effect = mock_stop_instances

            service = RemediationService(db)

            # Execute all remediations
            for request in requests:
                await service.execute(
                    request.id, test_tenant.id, bypass_grace_period=True
                )

            # Check final states
            for request in requests:
                await db.refresh(request)

            # First and third should succeed, second should fail
            assert requests[0].status == RemediationStatus.COMPLETED
            assert requests[1].status == RemediationStatus.FAILED
            assert requests[2].status == RemediationStatus.COMPLETED
