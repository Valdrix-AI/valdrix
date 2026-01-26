"""
Tests for LLM Usage Tracker Logic
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from decimal import Decimal
from datetime import datetime, timezone
from app.shared.llm.usage_tracker import UsageTracker, BudgetStatus
from app.shared.core.exceptions import BudgetExceededError


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    db.add = MagicMock()
    db.refresh = AsyncMock()
    return db


def test_calculate_cost_openai(mock_db):
    """Test cost calculation for OpenAI (paid)."""
    tracker = UsageTracker(mock_db)
    cost = tracker.calculate_cost("openai", "gpt-4o-mini", 1000, 1000)
    # Price is 0.15 input, 0.6 output per 1M tokens
    expected = (Decimal("1000") * Decimal("0.15") / Decimal("1000000")) + \
               (Decimal("1000") * Decimal("0.6") / Decimal("1000000"))
    assert cost == expected


def test_calculate_cost_unknown(mock_db):
    """Test cost calculation for unknown provider/model."""
    tracker = UsageTracker(mock_db)
    cost = tracker.calculate_cost("unknown", "model", 1000, 1000)
    assert cost == Decimal("0")


@pytest.mark.asyncio
async def test_record_usage(mock_db):
    """Test recording LLM usage to DB."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    
    with patch("app.shared.llm.usage_tracker.get_cache_service") as mock_cache_cls:
        mock_cache_cls.return_value.enabled = False
        with patch("app.shared.core.ops_metrics.LLM_SPEND_USD") as mock_metrics:
            # Mock check_budget call at the end
            with patch.object(tracker, "_check_budget_and_alert", new_callable=AsyncMock):
                usage = await tracker.record(
                    tenant_id=tenant_id,
                    provider="openai",
                    model="gpt-4o-mini",
                    input_tokens=1000,
                    output_tokens=500
                )
                
                assert usage.tenant_id == tenant_id
                assert usage.input_tokens == 1000
                mock_db.add.assert_called_once()
                mock_db.commit.assert_called_once()
                mock_metrics.labels.assert_called()


@pytest.mark.asyncio
async def test_authorize_request_allowed(mock_db):
    """Test pre-authorization when budget is OK."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    
    # Mock budget check result
    mock_budget = MagicMock()
    mock_budget.hard_limit = True
    mock_budget.monthly_limit_usd = 100.0
    
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = mock_budget
    mock_db.execute.return_value = mock_execute_result
    
    # Mock current monthly usage
    with patch.object(tracker, "get_monthly_usage", new_callable=AsyncMock) as mock_usage:
        mock_usage.return_value = Decimal("50.0")
        
        allowed = await tracker.authorize_request(
            tenant_id=tenant_id,
            provider="openai",
            model="gpt-4o-mini",
            input_text="short query"
        )
        assert allowed is True


@pytest.mark.asyncio
async def test_authorize_request_rejected(mock_db):
    """Test pre-authorization rejection when budget is exceeded."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    
    mock_budget = MagicMock()
    mock_budget.hard_limit = True
    mock_budget.monthly_limit_usd = 10.0
    
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = mock_budget
    mock_db.execute.return_value = mock_execute_result
    
    with patch.object(tracker, "get_monthly_usage", new_callable=AsyncMock) as mock_usage:
        mock_usage.return_value = Decimal("10.0") # Already at limit
        
        with pytest.raises(BudgetExceededError):
            await tracker.authorize_request(
                tenant_id=tenant_id,
                provider="openai",
                model="gpt-4o-mini",
                input_text="A" * 1000 # Enough to make projected cost > limit
            )


@pytest.mark.asyncio
async def test_check_budget_hard_limit(mock_db):
    """Test check_budget when HARD_LIMIT is reached."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    
    # Mock Cache
    with patch("app.shared.llm.usage_tracker.get_cache_service") as mock_cache_cls:
        mock_cache_cls.return_value.enabled = False
        
        # Mock Budget DB Query
        mock_budget = MagicMock()
        mock_budget.hard_limit = True
        mock_budget.monthly_limit_usd = 50.0
        mock_budget.alert_threshold_percent = 80.0
        
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_budget
        mock_db.execute.return_value = mock_execute_result
        
        # Mock monthly usage >= limit
        with patch.object(tracker, "get_monthly_usage", new_callable=AsyncMock) as mock_usage:
            mock_usage.return_value = Decimal("51.0")
            
            with pytest.raises(BudgetExceededError):
                await tracker.check_budget(tenant_id)


@pytest.mark.asyncio
async def test_check_budget_soft_limit(mock_db):
    """Test check_budget when SOFT_LIMIT threshold is reached."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    
    with patch("app.shared.llm.usage_tracker.get_cache_service") as mock_cache_cls:
        mock_cache_cls.return_value.enabled = False
        
        mock_budget = MagicMock()
        mock_budget.hard_limit = True
        mock_budget.monthly_limit_usd = 100.0
        mock_budget.alert_threshold_percent = 80.0
        
        mock_execute_result = MagicMock()
        mock_execute_result.scalar_one_or_none.return_value = mock_budget
        mock_db.execute.return_value = mock_execute_result
        
        with patch.object(tracker, "get_monthly_usage", new_callable=AsyncMock) as mock_usage:
            mock_usage.return_value = Decimal("85.0") # 85% > 80%
            
            status = await tracker.check_budget(tenant_id)
            assert status == BudgetStatus.SOFT_LIMIT

@pytest.mark.asyncio
async def test_check_budget_and_alert_sends_slack(mock_db):
    """Test budget alert sends Slack notification."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    
    # Mock Budget
    mock_budget = MagicMock()
    mock_budget.monthly_limit_usd = 100.0
    mock_budget.alert_threshold_percent = 80.0
    mock_budget.alert_sent_at = None
    
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = mock_budget
    mock_db.execute.return_value = mock_execute_result
    
    # Mock usage > threshold
    with patch.object(tracker, "get_monthly_usage", new_callable=AsyncMock) as mock_usage:
        mock_usage.return_value = Decimal("85.0")
        
        with patch("app.shared.core.config.get_settings") as mock_settings:
            mock_settings.return_value.SLACK_BOT_TOKEN = "xoxb-test"
            mock_settings.return_value.SLACK_CHANNEL_ID = "C123"
            
            with patch("app.modules.notifications.domain.SlackService") as mock_slack_cls:
                mock_slack = AsyncMock()
                mock_slack_cls.return_value = mock_slack
                
                await tracker._check_budget_and_alert(tenant_id)
                
                # Verify Slack alert was sent
                mock_slack.send_alert.assert_called_once()
                # Verify alert_sent_at was updated
                assert mock_budget.alert_sent_at is not None
                mock_db.commit.assert_called_once()

@pytest.mark.asyncio
async def test_check_budget_cache_hit_hard_limit(mock_db):
    """Test check_budget using cached hard limit."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    
    with patch("app.shared.llm.usage_tracker.get_cache_service") as mock_cache_cls:
        mock_cache = MagicMock()
        mock_cache.enabled = True
        mock_cache.client.get = AsyncMock(return_value="1")
        mock_cache_cls.return_value = mock_cache
        
        status = await tracker.check_budget(tenant_id)
        assert status == BudgetStatus.HARD_LIMIT


@pytest.mark.asyncio
async def test_check_budget_and_alert_skip_if_already_sent(mock_db):
    """Test check_budget_and_alert skips if alert already sent this month."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    
    mock_budget = MagicMock()
    mock_budget.monthly_limit_usd = 100.0
    mock_budget.alert_threshold_percent = 80.0
    # Already sent this month
    now = datetime.now(timezone.utc)
    mock_budget.alert_sent_at = now
    
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = mock_budget
    mock_db.execute.return_value = mock_execute_result
    
    with patch.object(tracker, "get_monthly_usage", new_callable=AsyncMock) as mock_usage:
        mock_usage.return_value = Decimal("90.0")
        
        with patch("app.modules.notifications.domain.SlackService") as mock_slack_cls:
            mock_slack = AsyncMock()
            mock_slack_cls.return_value = mock_slack
            
            await tracker._check_budget_and_alert(tenant_id)
            
            # Should NOT send alert again
            mock_slack.send_alert.assert_not_called()


@pytest.mark.asyncio
async def test_check_budget_and_alert_slack_error_graceful(mock_db):
    """Test check_budget_and_alert handles Slack failures gracefully."""
    tracker = UsageTracker(mock_db)
    tenant_id = uuid4()
    
    mock_budget = MagicMock()
    mock_budget.monthly_limit_usd = 100.0
    mock_budget.alert_threshold_percent = 80.0
    mock_budget.alert_sent_at = None
    
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = mock_budget
    mock_db.execute.return_value = mock_execute_result
    
    with patch.object(tracker, "get_monthly_usage", new_callable=AsyncMock) as mock_usage:
        mock_usage.return_value = Decimal("90.0")
        
        with patch("app.shared.core.config.get_settings") as mock_settings:
            mock_settings.return_value.SLACK_BOT_TOKEN = "xoxb-test"
            mock_settings.return_value.SLACK_CHANNEL_ID = "C123"
            
            with patch("app.modules.notifications.domain.SlackService") as mock_slack_cls:
                mock_slack = AsyncMock()
                mock_slack.send_alert.side_effect = Exception("Slack down")
                mock_slack_cls.return_value = mock_slack
                
                # Should not raise exception
                await tracker._check_budget_and_alert(tenant_id)
                
                assert mock_budget.alert_sent_at is not None

def test_count_tokens_fallback():
    """Test token counting fallback when tiktoken is unavailable."""
    from app.shared.llm.usage_tracker import count_tokens
    with patch("tiktoken.get_encoding") as mock_get:
        mock_get.side_effect = ImportError("No tiktoken")
        # should use fallback (len // 4)
        assert count_tokens("1234") == 1


@pytest.mark.asyncio
async def test_authorize_request_no_budget(mock_db):
    """Test authorize_request allows if no budget exists."""
    tracker = UsageTracker(mock_db)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    # mock_db.execute is already AsyncMock, just set return_value
    mock_db.execute.return_value = mock_result
    
    result = await tracker.authorize_request(uuid4(), "groq", "model", "text")
    assert result is True


@pytest.mark.asyncio
async def test_check_budget_cache_soft_limit(mock_db):
    """Test check_budget using cached soft limit."""
    tracker = UsageTracker(mock_db)
    with patch("app.shared.llm.usage_tracker.get_cache_service") as mock_cache_cls:
        mock_cache = MagicMock()
        mock_cache.enabled = True
        # Create a proper client mock with async get method
        mock_client = MagicMock()
        mock_client.get = AsyncMock(side_effect=[None, "1"])  # First None (not blocked), then "1" (soft limit)
        mock_cache.client = mock_client
        mock_cache_cls.return_value = mock_cache
        
        status = await tracker.check_budget(uuid4())
        assert status == BudgetStatus.SOFT_LIMIT


@pytest.mark.asyncio
async def test_get_monthly_usage_scalar(mock_db):
    """Test get_monthly_usage with scalar result."""
    tracker = UsageTracker(mock_db)
    mock_result = MagicMock()
    # scalar() returns a Decimal directly
    mock_result.scalar.return_value = Decimal("12.34")
    mock_db.execute.return_value = mock_result
    
    result = await tracker.get_monthly_usage(uuid4())
    assert result == Decimal("12.34")
