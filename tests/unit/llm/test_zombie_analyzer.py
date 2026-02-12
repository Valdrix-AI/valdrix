import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from app.shared.llm.zombie_analyzer import ZombieAnalyzer

@pytest.fixture
def mock_llm():
    llm = MagicMock()
    # Mock ainvoke for async chain
    llm.ainvoke = AsyncMock()
    return llm

@pytest.fixture
def analyzer(mock_llm):
    return ZombieAnalyzer(mock_llm)

def test_strip_markdown(analyzer):
    """Test removing markdown wrappers."""
    assert analyzer._strip_markdown("```json\n{\"foo\": \"bar\"}\n```") == "{\"foo\": \"bar\"}"
    assert analyzer._strip_markdown("```\n{\"foo\": \"bar\"}\n```") == "{\"foo\": \"bar\"}"
    assert analyzer._strip_markdown("{\"foo\": \"bar\"}") == "{\"foo\": \"bar\"}"

def test_flatten_zombies(analyzer):
    """Test flattening nested detection results."""
    raw_data = {
        "region": "us-east-1",
        "total_monthly_waste": 100.0,
        "ec2_idle": [
            {"resource_id": "i-123", "cost": 50.0},
            {"resource_id": "i-456", "cost": 50.0}
        ],
        "ebs_unattached": [
            {"resource_id": "vol-789", "cost": 10.0}
        ]
    }
    
    flattened = analyzer._flatten_zombies(raw_data)
    
    assert len(flattened) == 3
    assert flattened[0]["category"] == "ec2_idle"
    assert flattened[2]["category"] == "ebs_unattached"
    assert "total_monthly_waste" not in [item.get("category") for item in flattened]

@pytest.mark.asyncio
async def test_analyze_flow(analyzer, mock_llm):
    """Test full analysis flow."""
    # Mock LLM response
    mock_response = MagicMock()
    mock_response.content = json.dumps({
        "summary": "Found zombies",
        "total_monthly_savings": "$100.00",
        "resources": []
    })
    # Chain = prompt | llm
    mock_chain = MagicMock()
    mock_chain.ainvoke = AsyncMock(return_value=mock_response)
    
    # Mock get_settings to ensure LLM_PROVIDER matches our "effective" provider
    # so logic logic skips LLMFactory.create() and uses our mock_llm
    with patch("app.shared.llm.zombie_analyzer.get_settings") as mock_settings_fn:
        mock_settings_fn.return_value.LLM_PROVIDER = "openai"
        
        # We need to mock the pipe operator on the prompt
        with patch("app.shared.llm.zombie_analyzer.ChatPromptTemplate") as mock_prompt_cls:
            mock_prompt_cls.from_messages.return_value.__or__.return_value = mock_chain
            
            # Instantiate fresh analyzer to pick up mocked prompt
            fresh_analyzer = ZombieAnalyzer(mock_llm)
            
            # Mock get_effective_llm_config to skip DB/Budget calls logic complexity
            fresh_analyzer._get_effective_llm_config = AsyncMock(return_value=("openai", "gpt-4", None))
            
            # Mock record_usage
            fresh_analyzer._record_usage = AsyncMock()
            
            # Mock guardrails
            with patch("app.shared.llm.guardrails.LLMGuardrails.validate_output") as mock_validate:
                mock_validate.return_value.model_dump.return_value = {
                    "summary": "Valid summary",
                    "resources": []
                }
                
                result = await fresh_analyzer.analyze(
                    detection_results={"ec2": [{"id": "i-1"}]},
                    tenant_id=uuid4(),
                    db=AsyncMock()
                )
                
                assert result["summary"] == "Valid summary"
                mock_chain.ainvoke.assert_awaited()
