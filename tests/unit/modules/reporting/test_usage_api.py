import pytest
"""
Tests for Usage Metering API.
"""
import os
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4


from app.modules.reporting.api.v1.usage import get_usage_metrics, UsageResponse, LLMUsageRecord

@pytest.mark.asyncio
async def test_get_usage_metrics_structure():
    """Test that get_usage_metrics returns the correct structure including usage list."""
    
    mock_db = AsyncMock()
    mock_user = MagicMock()
    mock_user.tenant_id = uuid4()
    
    # Import models locally to avoid circular imports if any, or just for clarity
    from app.modules.reporting.api.v1.usage import LLMUsageMetrics, AWSMeteringMetrics, FeatureUsageMetrics
    
    # Create valid Pydantic model instances for mocks
    llm_metrics = LLMUsageMetrics(
        tokens_used=100, 
        tokens_limit=1000, 
        requests_count=5, 
        estimated_cost_usd=0.01,
        period_start="2024-01-01T00:00:00",
        period_end="2024-02-01T00:00:00",
        utilization_percent=10.0
    )
    
    aws_metrics = AWSMeteringMetrics(
        cost_explorer_calls_today=1, 
        zombie_scans_today=0, 
        regions_scanned=1, 
        last_scan_at=None
    )
    
    feature_metrics = FeatureUsageMetrics(
        greenops_enabled=True, 
        activeops_enabled=True, 
        webhooks_configured=1, 
        total_remediations=5
    )


    # Mock _get_llm_usage
    with patch("app.modules.reporting.api.v1.usage._get_llm_usage", new_callable=AsyncMock) as mock_llm:
        mock_llm.return_value = llm_metrics
        
        # Mock _get_recent_llm_activity
        with patch("app.modules.reporting.api.v1.usage._get_recent_llm_activity", new_callable=AsyncMock) as mock_recent:
            mock_recent.return_value = [
                LLMUsageRecord(
                    id=uuid4(),
                    created_at="2024-01-01T12:00:00",
                    model="gpt-4",
                    input_tokens=10,
                    output_tokens=20,
                    total_tokens=30,
                    cost_usd=0.001,
                    request_type="chat"
                )
            ]
            
            # Mock _get_aws_metering
            with patch("app.modules.reporting.api.v1.usage._get_aws_metering", new_callable=AsyncMock) as mock_aws:
                mock_aws.return_value = aws_metrics
                
                # Mock _get_feature_usage
                with patch("app.modules.reporting.api.v1.usage._get_feature_usage", new_callable=AsyncMock) as mock_feat:
                    mock_feat.return_value = feature_metrics
                    
                    response = await get_usage_metrics(user=mock_user, db=mock_db)
                    
                    assert isinstance(response, UsageResponse)
                    assert len(response.usage) == 1
                    assert response.usage[0].model == "gpt-4"
                    assert response.usage[0].total_tokens == 30
