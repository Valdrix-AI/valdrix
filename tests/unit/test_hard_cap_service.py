import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from decimal import Decimal
from uuid import uuid4
from app.shared.remediation.hard_cap_service import BudgetHardCapService
from app.models.remediation_settings import RemediationSettings

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.fixture
def hard_cap_service(mock_db):
    return BudgetHardCapService(mock_db)

@pytest.mark.asyncio
async def test_hard_cap_no_settings(hard_cap_service, mock_db):
    # Setup mock to return None for scalar_one_or_none
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result
    
    result = await hard_cap_service.check_and_enforce(uuid4())
    assert result is None

@pytest.mark.asyncio
async def test_hard_cap_not_enabled(hard_cap_service, mock_db):
    settings = RemediationSettings(hard_cap_enabled=False, monthly_hard_cap_usd=1000)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = settings
    mock_db.execute.return_value = mock_result
    
    result = await hard_cap_service.check_and_enforce(uuid4())
    assert result is None

@pytest.mark.asyncio
async def test_hard_cap_not_breached(hard_cap_service, mock_db):
    tenant_id = uuid4()
    settings = RemediationSettings(tenant_id=tenant_id, hard_cap_enabled=True, monthly_hard_cap_usd=500.0)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = settings
    mock_db.execute.return_value = mock_result
    
    with patch("app.modules.reporting.domain.aggregator.CostAggregator.get_summary") as mock_summary:
        mock_summary.return_value = MagicMock(total_cost=Decimal("400.00"))
        
        result = await hard_cap_service.check_and_enforce(tenant_id)
        assert result is False

@pytest.mark.asyncio
async def test_hard_cap_breached(hard_cap_service, mock_db):
    tenant_id = uuid4()
    settings = RemediationSettings(tenant_id=tenant_id, hard_cap_enabled=True, monthly_hard_cap_usd=500.0)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = settings
    mock_db.execute.return_value = mock_result
    
    with patch("app.modules.reporting.domain.aggregator.CostAggregator.get_summary") as mock_summary, \
         patch("app.shared.remediation.hard_cap_service.get_slack_service") as mock_slack_factory:
        
        mock_summary.return_value = MagicMock(total_cost=Decimal("600.00"))
        mock_slack = AsyncMock()
        mock_slack_factory.return_value = mock_slack
        
        result = await hard_cap_service.check_and_enforce(tenant_id)
        assert result is True
        mock_slack.notify_budget_alert.assert_called_once()
