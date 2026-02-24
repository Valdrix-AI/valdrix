import pytest
"""
Tests for ZombieAnalyzer Logic - BYOK and Usage Tracking
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession
from app.shared.llm.zombie_analyzer import ZombieAnalyzer


@pytest.fixture
def mock_llm():
    llm = MagicMock()
    # Mock ainvoke to return an AIMessage-like object
    llm.ainvoke = AsyncMock()
    return llm


@pytest.fixture
def mock_db():
    db = MagicMock(spec=AsyncSession)
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    # add and refresh are sync in SQLAlchemy, though refresh can be used with await in some wrappers
    # but here we mock them as synchronous to avoid the RuntimeWarning
    db.add = MagicMock()
    db.refresh = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_analyze_empty_results(mock_llm):
    """Test analyze method with empty results."""
    analyzer = ZombieAnalyzer(mock_llm)
    result = await analyzer.analyze({})
    assert result["summary"] == "No zombie resources detected."
    assert result["resources"] == []


@pytest.mark.asyncio
async def test_analyze_with_byok_config(mock_llm, mock_db):
    """Test analyze method with BYOK configuration."""
    analyzer = ZombieAnalyzer(mock_llm)
    tenant_id = uuid4()
    # Mock detection results
    detection_results = {
        "ebs_volumes": [{"resource_id": "vol-123"}],
        "total_monthly_waste": 10.0,
    }
    # Mock LLMBudget query for BYOK
    mock_budget = MagicMock()
    mock_budget.preferred_provider = "openai"
    mock_budget.preferred_model = "gpt-4o"
    mock_budget.openai_api_key = "sk-valid-key-long-enough-12345"
    mock_execute_result = MagicMock()
    mock_execute_result.scalar_one_or_none.return_value = mock_budget
    mock_db.execute.return_value = mock_execute_result
    # Mock LLM chain execution
    mock_response = MagicMock()
    mock_response.content = json.dumps(
        {
            "summary": "BYOK test",
            "total_monthly_savings": "$10.00",
            "resources": [],
            "general_recommendations": [],
        }
    )
    mock_response.response_metadata = {
        "token_usage": {"prompt_tokens": 10, "completion_tokens": 5}
    }
    # We need to mock the chain invocation
    with patch("langchain_core.prompts.ChatPromptTemplate.__or__") as mock_or:
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = mock_response
        mock_or.return_value = mock_chain
        # Patch LLMFactory.create since it's called for BYOK
        with (
            patch("app.shared.llm.factory.LLMFactory.create") as mock_factory_create,
            patch(
                "app.shared.llm.zombie_analyzer.LLMBudgetManager.check_and_reserve",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.shared.llm.zombie_analyzer.LLMBudgetManager.record_usage",
                new=AsyncMock(return_value=None),
            ),
        ):
            mock_factory_create.return_value = mock_llm
            result = await analyzer.analyze(
                detection_results, tenant_id=tenant_id, db=mock_db, provider="openai"
            )
            assert result["summary"] == "BYOK test"
            # Verify BYOK key was passed to factory
            mock_factory_create.assert_called_with(
                "openai",
                model="gpt-4o",
                api_key="sk-valid-key-long-enough-12345",
                max_output_tokens=512,
            )


@pytest.mark.asyncio
async def test_analyze_usage_tracking(mock_llm, mock_db):
    """Test that usage tracking is called during analysis."""
    analyzer = ZombieAnalyzer(mock_llm)
    tenant_id = uuid4()
    detection_results = {"ebs": [{"resource_id": "vol-1"}], "total_monthly_waste": 10.0}
    mock_response = MagicMock()
    # VALID JSON matching schema
    mock_response.content = json.dumps(
        {
            "summary": "Usage test",
            "total_monthly_savings": "$10.00",
            "resources": [
                {
                    "resource_id": "vol-1",
                    "resource_type": "ebs_volume",
                    "provider": "aws",
                    "explanation": "Unused",
                    "confidence": "high",
                    "confidence_score": 0.9,
                    "confidence_reason": "Idle",
                    "recommended_action": "Delete",
                    "monthly_cost": "$10.00",
                    "risk_if_deleted": "low",
                    "risk_explanation": "None",
                }
            ],
            "general_recommendations": [],
        }
    )
    mock_response.response_metadata = {
        "token_usage": {"prompt_tokens": 100, "completion_tokens": 50}
    }
    with patch("langchain_core.prompts.ChatPromptTemplate.__or__") as mock_or:
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = mock_response
        mock_or.return_value = mock_chain
        with (
            patch(
                "app.shared.llm.zombie_analyzer.LLMBudgetManager.check_and_reserve",
                new=AsyncMock(return_value=None),
            ),
            patch(
                "app.shared.llm.zombie_analyzer.LLMBudgetManager.record_usage",
                new=AsyncMock(return_value=None),
            ) as mock_record_usage,
        ):
            # Setup mock_db execution result correctly
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = None
            mock_db.execute.return_value = mock_result
            await analyzer.analyze(detection_results, tenant_id=tenant_id, db=mock_db)
            # Verify usage tracking was called with correct tokens
            mock_record_usage.assert_called_once()
            args = mock_record_usage.call_args.kwargs
            assert args["prompt_tokens"] == 100
            assert args["completion_tokens"] == 50


@pytest.mark.asyncio
async def test_analyze_json_parse_error_fallback(mock_llm):
    """Test fallback behavior when LLM returns invalid JSON."""
    analyzer = ZombieAnalyzer(mock_llm)
    detection_results = {"total_monthly_waste": 50.0, "ebs": [{"id": "v-1"}]}
    mock_response = MagicMock()
    mock_response.content = "This is not JSON"
    with patch("langchain_core.prompts.ChatPromptTemplate.__or__") as mock_or:
        mock_chain = AsyncMock()
        mock_chain.ainvoke.return_value = mock_response
        mock_or.return_value = mock_chain
        result = await analyzer.analyze(detection_results)
        assert "Analysis completed but response parsing failed" in result["summary"]
        assert result["raw_response"] == "This is not JSON"
        assert result["total_monthly_savings"] == "$50.00"
