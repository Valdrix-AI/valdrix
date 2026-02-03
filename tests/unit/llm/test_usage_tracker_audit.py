import pytest
from decimal import Decimal
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4

# conftest.py handles environment mocks

from app.shared.llm.usage_tracker import UsageTracker, count_tokens, BudgetStatus
from app.shared.core.exceptions import BudgetExceededError

@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    return db

@pytest.fixture
def tenant_id():
    return uuid4()

def test_count_tokens_fallback(monkeypatch):
    with patch("tiktoken.get_encoding", side_effect=Exception("failed")):
        assert count_tokens("abcd") == 1
        assert count_tokens("12345678") == 2

def test_count_tokens_tiktoken():
    mock_enc = MagicMock()
    mock_enc.encode.return_value = [1, 2, 3] 
    with patch("tiktoken.get_encoding", return_value=mock_enc):
        assert count_tokens("test", model="gpt-4") == 3

def test_calculate_cost():
    tracker = UsageTracker(MagicMock())
    mock_pricing = {
        "groq": {"llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79}}
    }
    with patch.dict("app.shared.llm.pricing_data.LLM_PRICING", mock_pricing, clear=True):
        cost = tracker.calculate_cost("groq", "llama-3.3-70b-versatile", 1_000_000, 1_000_000)
        assert cost == Decimal("1.38")

@pytest.mark.asyncio
async def test_record_success(mock_db, tenant_id):
    tracker = UsageTracker(mock_db)
    mock_cache = MagicMock()
    mock_cache.enabled = True
    mock_cache.client.set = AsyncMock()
    
    # Patch at CLASS level to ensure it works
    with patch("app.shared.llm.usage_tracker.UsageTracker.calculate_cost", return_value=Decimal("1.00")), \
         patch("app.shared.llm.usage_tracker.get_cache_service", return_value=mock_cache), \
         patch("app.shared.llm.usage_tracker.UsageTracker.get_monthly_usage", new_callable=AsyncMock) as mock_get_usage, \
         patch("app.shared.core.ops_metrics.LLM_SPEND_USD"), \
         patch("app.shared.core.pricing.get_tenant_tier", new_callable=AsyncMock) as mock_tier, \
         patch("app.shared.llm.usage_tracker.LLMUsage") as MockLLMUsage:
        
        mock_get_usage.return_value = Decimal("10.00")
        mock_tier.return_value = MagicMock(value="pro")
        
        mock_usage_instance = MagicMock()
        MockLLMUsage.return_value = mock_usage_instance
        
        usage = await tracker.record(tenant_id, "groq", "model", 100, 100)
        
        assert usage is mock_usage_instance
        assert mock_db.add.called

@pytest.mark.asyncio
async def test_authorize_request_allowed(mock_db, tenant_id):
    tracker = UsageTracker(mock_db)
    
    with patch("sqlalchemy.select"):
        budget = MagicMock()
        budget.monthly_limit_usd = Decimal("100.00")
        budget.hard_limit = True
        
        res = MagicMock()
        res.scalar_one_or_none.return_value = budget
        mock_db.execute.return_value = res
        
        with patch("app.shared.llm.usage_tracker.UsageTracker.get_monthly_usage", new_callable=AsyncMock) as mock_usage, \
             patch.dict("app.shared.llm.pricing_data.LLM_PRICING", {}, clear=True):
            
            mock_usage.return_value = Decimal("10.00")
            allowed = await tracker.authorize_request(tenant_id, "groq", "model", "text", max_output_tokens=100)
            assert allowed is True

@pytest.mark.asyncio
async def test_authorize_request_denied(mock_db, tenant_id):
    tracker = UsageTracker(mock_db)
    
    with patch("sqlalchemy.select"):
        budget = MagicMock()
        budget.monthly_limit_usd = Decimal("5.00")
        budget.hard_limit = True
        
        res = MagicMock()
        res.scalar_one_or_none.return_value = budget
        mock_db.execute.return_value = res
        
        with patch("app.shared.llm.usage_tracker.UsageTracker.get_monthly_usage", new_callable=AsyncMock) as mock_usage, \
             patch.dict("app.shared.llm.pricing_data.LLM_PRICING", {}, clear=True):
            
            mock_usage.return_value = Decimal("10.00")
            with pytest.raises(BudgetExceededError):
                await tracker.authorize_request(tenant_id, "groq", "model", "text")

@pytest.mark.asyncio
async def test_check_budget_hard_limit(mock_db, tenant_id):
    tracker = UsageTracker(mock_db)
    mock_cache = MagicMock()
    mock_cache.enabled = True
    mock_cache.client.get = AsyncMock(return_value="1") 
    
    with patch("app.shared.llm.usage_tracker.get_cache_service", return_value=mock_cache):
        status = await tracker.check_budget(tenant_id)
        assert status == BudgetStatus.HARD_LIMIT

@pytest.mark.asyncio
async def test_check_budget_fail_closed(mock_db, tenant_id):
    tracker = UsageTracker(mock_db)
    mock_db.execute.side_effect = Exception("DB Down")
    
    with patch("sqlalchemy.select"):
        with pytest.raises(BudgetExceededError) as exc:
            await tracker.check_budget(tenant_id)
        assert exc.value.details.get("fail_closed") is True

@pytest.mark.asyncio
async def test_alert_logic(mock_db, tenant_id):
    tracker = UsageTracker(mock_db)
    
    with patch("sqlalchemy.select"):
        budget = MagicMock()
        budget.tenant_id = tenant_id
        budget.monthly_limit_usd = Decimal("100.00")
        budget.alert_threshold_percent = 80
        budget.alert_sent_at = None
        
        res = MagicMock()
        res.scalar_one_or_none.return_value = budget
        mock_db.execute.return_value = res
        
        # Patch CLASS method here too
        with patch("app.shared.llm.usage_tracker.UsageTracker.get_monthly_usage", new_callable=AsyncMock) as mock_usage, \
             patch("app.shared.core.logging.audit_log") as mock_audit, \
             patch("app.modules.notifications.domain.SlackService"):
            
            mock_usage.return_value = Decimal("85.00")
            await tracker._check_budget_and_alert(tenant_id)
            assert mock_audit.called
