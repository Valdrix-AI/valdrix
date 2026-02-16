import pytest
from uuid import uuid4
from unittest.mock import MagicMock, AsyncMock, patch
from app.modules.governance.domain.scheduler.processors import SavingsProcessor
from app.shared.llm.guardrails import FinOpsAnalysisResult, FinOpsRecommendation
from app.models.remediation import RemediationAction


@pytest.mark.asyncio
async def test_savings_processor_executes_autonomous_ready(db) -> None:
    """Verify that SavingsProcessor identifies and executes autonomous_ready recommendations."""
    tenant_id = uuid4()

    # 1. Create a mock analysis result with one autonomous_ready recommendation
    rec = FinOpsRecommendation(
        action="Stop instance i-999",
        resource="i-999",
        type="ec2",
        estimated_savings="$45/month",
        priority="high",
        effort="low",
        confidence="high",
        autonomous_ready=True,
    )
    result = FinOpsAnalysisResult(
        insights=["Found idle volume"], recommendations=[rec], anomalies=[], forecast={}
    )

    # 2. Mock RemediationService
    with patch(
        "app.modules.optimization.domain.remediation.RemediationService", autospec=True
    ) as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.create_request = AsyncMock()
        mock_service.approve = AsyncMock()
        mock_service.execute = AsyncMock()

        # Mock create_request to return a dummy request object
        mock_request = MagicMock()
        mock_request.id = uuid4()
        mock_service.create_request.return_value = mock_request

        processor = SavingsProcessor()
        await processor.process_recommendations(db, tenant_id, result)

        # 3. Assertions
        mock_service.create_request.assert_called_once()
        args, kwargs = mock_service.create_request.call_args
        assert kwargs["resource_id"] == "i-999"
        assert kwargs["action"] == RemediationAction.STOP_INSTANCE
        assert kwargs["estimated_savings"] == 45.0

        mock_service.approve.assert_called_once()
        mock_service.execute.assert_called_once_with(
            mock_request.id, tenant_id, bypass_grace_period=False
        )


@pytest.mark.asyncio
async def test_savings_processor_skips_non_autonomous(db):
    """Verify that SavingsProcessor ignores recommendations that are not autonomous_ready."""
    tenant_id = uuid4()

    rec = FinOpsRecommendation(
        action="Resize instance i-123",
        resource="i-123",
        type="ec2",
        estimated_savings="$100/month",
        priority="high",
        effort="medium",
        confidence="medium",
        autonomous_ready=False,  # NOT autonomous
    )
    result = FinOpsAnalysisResult(recommendations=[rec])

    with patch(
        "app.modules.optimization.domain.remediation.RemediationService", autospec=True
    ) as mock_service_cls:
        mock_service = mock_service_cls.return_value
        processor = SavingsProcessor()
        await processor.process_recommendations(db, tenant_id, result)

        mock_service.create_request.assert_not_called()


@pytest.mark.asyncio
async def test_savings_processor_does_not_auto_execute_destructive_actions(db):
    tenant_id = uuid4()
    rec = FinOpsRecommendation(
        action="Delete Volume vol-999",
        resource="vol-999",
        type="ebs",
        estimated_savings="$45/month",
        priority="high",
        effort="low",
        confidence="high",
        autonomous_ready=True,
    )
    result = FinOpsAnalysisResult(recommendations=[rec])

    with patch(
        "app.modules.optimization.domain.remediation.RemediationService", autospec=True
    ) as mock_service_cls:
        mock_service = mock_service_cls.return_value
        mock_service.create_request = AsyncMock()
        mock_service.approve = AsyncMock()
        mock_service.execute = AsyncMock()
        mock_request = MagicMock()
        mock_request.id = uuid4()
        mock_service.create_request.return_value = mock_request

        processor = SavingsProcessor()
        await processor.process_recommendations(db, tenant_id, result)

        mock_service.create_request.assert_called_once()
        mock_service.approve.assert_not_called()
        mock_service.execute.assert_not_called()
