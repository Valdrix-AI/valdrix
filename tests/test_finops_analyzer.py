"""
Tests for FinOpsAnalyzer (LLM-based cost analysis)

Tests cover:
- Analyzer instantiation
- Prompt template validation
- JSON output parsing
- Error handling for malformed LLM responses
- Usage tracking integration
"""

import pytest
from unittest.mock import MagicMock, AsyncMock
import json

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage

from app.services.llm.analyzer import FinOpsAnalyzer, FINOPS_SYSTEM_PROMPT


class TestFinOpsAnalyzerInstantiation:
    """Tests for FinOpsAnalyzer initialization."""
    
    def test_requires_llm(self):
        """Should require a LangChain chat model."""
        mock_llm = MagicMock(spec=BaseChatModel)
        analyzer = FinOpsAnalyzer(llm=mock_llm)
        assert analyzer.llm is mock_llm
    
    def test_creates_prompt_template(self):
        """Should create a ChatPromptTemplate with cost_data variable."""
        mock_llm = MagicMock(spec=BaseChatModel)
        analyzer = FinOpsAnalyzer(llm=mock_llm)
        assert analyzer.prompt is not None
        # Should have 'cost_data' as input variable
        assert 'cost_data' in analyzer.prompt.input_variables


class TestSystemPrompt:
    """Tests for the system prompt."""
    
    def test_instructs_json_output(self):
        """System prompt should instruct strict JSON output."""
        assert "JSON" in FINOPS_SYSTEM_PROMPT
        assert "STRICT JSON ONLY" in FINOPS_SYSTEM_PROMPT
    
    def test_defines_output_schema(self):
        """System prompt should define the expected output schema."""
        assert "anomalies" in FINOPS_SYSTEM_PROMPT
        assert "zombie_resources" in FINOPS_SYSTEM_PROMPT
        assert "recommendations" in FINOPS_SYSTEM_PROMPT
        assert "total_estimated_savings" in FINOPS_SYSTEM_PROMPT
    
    def test_includes_severity_levels(self):
        """System prompt should define severity levels."""
        assert "high|medium|low" in FINOPS_SYSTEM_PROMPT


class TestStripMarkdown:
    """Tests for _strip_markdown helper."""
    
    def test_removes_json_code_block(self):
        """Should strip ```json wrapper."""
        mock_llm = MagicMock(spec=BaseChatModel)
        analyzer = FinOpsAnalyzer(llm=mock_llm)
        
        input_text = '```json\n{"key": "value"}\n```'
        result = analyzer._strip_markdown(input_text)
        
        assert result == '{"key": "value"}'
    
    def test_handles_plain_json(self):
        """Should handle plain JSON without markdown."""
        mock_llm = MagicMock(spec=BaseChatModel)
        analyzer = FinOpsAnalyzer(llm=mock_llm)
        
        input_text = '{"key": "value"}'
        result = analyzer._strip_markdown(input_text)
        
        assert result == '{"key": "value"}'
    
    def test_removes_generic_code_block(self):
        """Should strip ``` wrapper without language."""
        mock_llm = MagicMock(spec=BaseChatModel)
        analyzer = FinOpsAnalyzer(llm=mock_llm)
        
        input_text = '```\n{"key": "value"}\n```'
        result = analyzer._strip_markdown(input_text)
        
        assert result == '{"key": "value"}'


@pytest.mark.asyncio
class TestAnalyze:
    """Tests for analyze() method."""
    
    async def test_invokes_llm_with_cost_data(self):
        """Should invoke LLM with formatted cost data."""
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content='{"anomalies":[],"zombie_resources":[],"optimizations":[],"total_estimated_savings":"$0/month"}'))
        
        analyzer = FinOpsAnalyzer(llm=mock_llm)
        
        cost_data = [{"service": "EC2", "cost": 100.0}]
        _ = await analyzer.analyze(cost_data)
        
        # LLM should have been invoked
        mock_llm.ainvoke.assert_called_once()
    
    async def test_returns_parsed_result(self):
        """Should return result from LLM response."""
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_response = {
            "anomalies": [],
            "zombie_resources": [],
            "recommendations": [],
            "summary": {"total_estimated_savings": "$0/month"}
        }
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content=json.dumps(mock_response)))
        
        analyzer = FinOpsAnalyzer(llm=mock_llm)
        
        result = await analyzer.analyze([{"service": "EC2", "cost": 100.0}])
        
        # Result should be valid JSON string or parsed dict
        assert result is not None
    
    async def test_handles_markdown_wrapped_json(self):
        """Should handle LLM responses wrapped in markdown code blocks."""
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_response = '```json\n{"anomalies":[],"zombie_resources":[],"optimizations":[],"total_estimated_savings":"$0/month"}\n```'
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content=mock_response))
        
        analyzer = FinOpsAnalyzer(llm=mock_llm)
        
        result = await analyzer.analyze([{"service": "EC2", "cost": 100.0}])
        
        assert "anomalies" in result
        assert "total_estimated_savings" in result
    
    async def test_handles_invalid_json_gracefully(self):
        """Should handle invalid JSON from LLM gracefully."""
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content="This is not valid JSON at all"))
        
        analyzer = FinOpsAnalyzer(llm=mock_llm)
        
        # Should not raise, should return the raw response
        result = await analyzer.analyze([{"service": "EC2", "cost": 100.0}])
        assert result is not None  # Returns raw content on parse failure
    
    async def test_handles_empty_cost_data(self):
        """Should handle empty cost data gracefully."""
        mock_llm = MagicMock(spec=BaseChatModel)
        mock_llm.ainvoke = AsyncMock(return_value=AIMessage(content='{"anomalies":[],"zombie_resources":[],"optimizations":[],"total_estimated_savings":"$0/month"}'))
        
        analyzer = FinOpsAnalyzer(llm=mock_llm)
        
        result = await analyzer.analyze([])
        
        assert "anomalies" in result
