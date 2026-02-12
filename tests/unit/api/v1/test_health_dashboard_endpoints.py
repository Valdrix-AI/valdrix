"""
Tests for Investor Health Dashboard API Endpoints
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
from app.modules.health_dashboard import get_investor_health_dashboard


@pytest.mark.asyncio
async def test_get_investor_health_dashboard_handler_success():
    """Test get_investor_health_dashboard direct handler call."""
    mock_admin = MagicMock()
    mock_admin.role = "admin"
    
    mock_db = AsyncMock()
    
    # Mock sequence of scalar/execute calls
    # 5 tenant metrics scalars
    # 4 job health scalars (pending, running, failed, dlq)
    # 3 LLM metrics scalars (requests, cost, utilization)
    # 2 AWS connection scalars (total, verified)
    mock_db.scalar.side_effect = [
        10, 5, 8, 2, 8, # tenants (5)
        1, 2, 0, 0,    # jobs (4)
        1000, 2.5, 0.4, # llm (3)
        5, 4            # aws (2)
    ]
    
    # Job processing stats Result (1 execute call)
    mock_job_stats = MagicMock()
    mock_job_stats.one.return_value = [150.0, 100.0, 200.0, 300.0] # avg, p50, p95, p99
    
    # AWS Connection Result - Wait, the code uses scalar for AWS connections now, not execute
    
    mock_db.execute.side_effect = [mock_job_stats]
    
    response = await get_investor_health_dashboard(mock_admin, mock_db)
    
    assert response.system.status == "healthy"
    assert response.tenants.total_tenants == 10
    assert response.job_queue.pending_jobs == 1
    assert response.llm_usage.total_requests_24h == 1000
    assert response.aws_connections.failed_connections == 1
