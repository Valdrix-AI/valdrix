"""
Tests for Usage Metering API Endpoints
"""

import pytest
from uuid import uuid4
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock
from app.modules.reporting.api.v1.usage import get_usage_metrics


@pytest.mark.asyncio
async def test_get_usage_metrics_handler_success():
    """Test get_usage_metrics direct handler call."""
    tenant_id = uuid4()
    mock_user = MagicMock()
    mock_user.tenant_id = tenant_id
    mock_user.tier = "growth"

    mock_db = AsyncMock()

    # 1. LLMBudget lookup
    # 2. AWS metering jobs (cost_explorer_calls)
    # 3. Zombie scans
    # 4. Last successful scan
    # 5. Tenant lookup
    # 6. Notif settings
    # 7. Remediation count
    mock_db.scalar.side_effect = [
        MagicMock(monthly_limit_usd=10.0),  # budget
        5,  # cost_explorer_calls
        2,  # zombie_scans
        datetime.now(timezone.utc),  # last_scan
        MagicMock(plan="growth"),  # tenant
        MagicMock(slack_webhook="url"),  # notif
        10,  # remediation_count
    ]

    # LLMUsage execution result
    mock_res = MagicMock()
    mock_res.one.return_value = [5000, 10, 0.5]  # tokens, requests, cost
    mock_db.execute.return_value = mock_res

    # Call handler directly
    response = await get_usage_metrics(mock_user, mock_db)

    assert response.tenant_id == tenant_id
    assert response.llm.tokens_used == 5000
    assert response.aws.zombie_scans_today == 2
    assert response.features.total_remediations == 10
