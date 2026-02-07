import pytest
import json
from unittest.mock import MagicMock, AsyncMock, patch
from uuid import uuid4
from app.shared.llm.zombie_analyzer import ZombieAnalyzer
from app.models.llm import LLMBudget

@pytest.fixture
def mock_llm():
    from langchain_core.language_models.chat_models import BaseChatModel
    llm = MagicMock(spec=BaseChatModel)
    llm.ainvoke = AsyncMock()
    return llm

@pytest.fixture
def analyzer(mock_llm):
    return ZombieAnalyzer(mock_llm)

class TestZombieAnalyzerExhaustive:
    """Exhaustive tests for ZombieAnalyzer to reach 100% coverage."""

    @pytest.mark.asyncio
    async def test_analyze_no_zombies_detected(self, analyzer):
        """Test analyze when no zombies are detected (line 126)."""
        result = await analyzer.analyze({})
        assert result["summary"] == "No zombie resources detected."
        assert result["resources"] == []

    def test_flatten_zombies_non_list_items(self, analyzer):
        """Test flattening results with non-list items (line 107)."""
        raw_data = {
            "invalid_cat": "not a list",
            "valid_cat": [{"id": "r1"}]
        }
        flattened = analyzer._flatten_zombies(raw_data)
        assert len(flattened) == 1
        assert flattened[0]["id"] == "r1"

    def test_flatten_zombies_non_dict_items(self, analyzer):
        """Test flattening results with non-dict items in list (line 109)."""
        raw_data = {
            "cat": ["not a dict", {"id": "r1"}]
        }
        flattened = analyzer._flatten_zombies(raw_data)
        assert len(flattened) == 1
        assert flattened[0]["id"] == "r1"

    @pytest.mark.asyncio
    async def test_analyze_validation_failure(self, analyzer, mock_llm):
        """Test analyze when LLM response validation fails (lines 164-166)."""
        mock_response = MagicMock()
        mock_response.content = "invalid json"
        
        # Mock chain.ainvoke via pipe operator
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_response)
        
        with patch("app.shared.llm.zombie_analyzer.ChatPromptTemplate") as mock_prompt_cls, \
             patch("app.shared.llm.guardrails.LLMGuardrails.validate_output", side_effect=ValueError("Parse error")), \
             patch("app.shared.llm.factory.LLMFactory.create") as mock_create:
            mock_prompt_cls.from_messages.return_value.__or__.return_value = mock_chain
            mock_create.return_value = mock_llm
            
            # Fresh analyzer to pick up mocked prompt
            auth_analyzer = ZombieAnalyzer(mock_llm)
            auth_analyzer._get_effective_llm_config = AsyncMock(return_value=("openai", "gpt-4", None))
            
            result = await auth_analyzer.analyze({"cat": [{"id": "r1"}]})
            
            assert "parsing failed" in result["summary"]
            assert result["parse_error"] == "Parse error"

    @pytest.mark.asyncio
    async def test_get_effective_config_byok_openai(self, analyzer):
        """Test resolving config with OpenAI BYOK key."""
        mock_db = AsyncMock()
        mock_budget = MagicMock(spec=LLMBudget)
        mock_budget.preferred_provider = "openai"
        mock_budget.preferred_model = "gpt-4o"
        mock_budget.openai_api_key = "sk-openai"
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_budget
        mock_db.execute.return_value = mock_result
        
        prov, model, key = await analyzer._get_effective_llm_config(mock_db, uuid4(), None, None)
        
        assert prov == "openai"
        assert model == "gpt-4o"
        assert key == "sk-openai"

    @pytest.mark.asyncio
    async def test_get_effective_config_byok_claude(self, analyzer):
        """Test resolving config with Claude BYOK key."""
        mock_db = AsyncMock()
        mock_budget = MagicMock(spec=LLMBudget)
        mock_budget.preferred_provider = "claude"
        mock_budget.claude_api_key = "sk-ant"
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_budget
        mock_db.execute.return_value = mock_result
        
        prov, model, key = await analyzer._get_effective_llm_config(mock_db, uuid4(), "claude", None)
        assert key == "sk-ant"

    @pytest.mark.asyncio
    async def test_get_effective_config_byok_google(self, analyzer):
        """Test resolving config with Google BYOK key."""
        mock_db = AsyncMock()
        mock_budget = MagicMock(spec=LLMBudget)
        mock_budget.preferred_provider = "google"
        mock_budget.google_api_key = "goo-key"
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_budget
        mock_db.execute.return_value = mock_result
        
        prov, model, key = await analyzer._get_effective_llm_config(mock_db, uuid4(), "google", None)
        assert key == "goo-key"

    @pytest.mark.asyncio
    async def test_get_effective_config_byok_groq(self, analyzer):
        """Test resolving config with Groq BYOK key."""
        mock_db = AsyncMock()
        mock_budget = MagicMock(spec=LLMBudget)
        mock_budget.preferred_provider = "groq"
        mock_budget.groq_api_key = "groq-key"
        
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_budget
        mock_db.execute.return_value = mock_result
        
        prov, model, key = await analyzer._get_effective_llm_config(mock_db, uuid4(), "groq", None)
        assert key == "groq-key"

    @pytest.mark.asyncio
    async def test_record_usage_exception(self, analyzer):
        """Test usage recording failure handling (lines 239-242)."""
        mock_db = AsyncMock()
        mock_response = MagicMock()
        mock_response.response_metadata = {"token_usage": {"prompt_tokens": 10}}
        
        with patch("app.shared.llm.zombie_analyzer.UsageTracker") as mock_tracker_cls:
            mock_tracker_cls.return_value.record = AsyncMock(side_effect=Exception("Tracker fail"))
            
            # This should NOT raise an exception
            await analyzer._record_usage(mock_db, uuid4(), "provider", "model", mock_response, False)

    @pytest.mark.asyncio
    async def test_analyze_trigger_factory(self, analyzer, mock_llm):
        """Test analyze triggering LLMFactory (lines 143-144)."""
        mock_response = MagicMock()
        mock_response.content = json.dumps({"summary": "ok", "resources": []})
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_response)
        
        with patch("app.shared.llm.zombie_analyzer.get_settings") as mock_settings_fn, \
             patch("app.shared.llm.factory.LLMFactory") as mock_factory, \
             patch("app.shared.llm.zombie_analyzer.ChatPromptTemplate") as mock_prompt_cls:
            
            mock_settings_fn.return_value.LLM_PROVIDER = "groq" # Default is different
            mock_factory.create.return_value = mock_llm # Factory returns our mock
            mock_prompt_cls.from_messages.return_value.__or__.return_value = mock_chain
            
            auth_analyzer = ZombieAnalyzer(mock_llm)
            auth_analyzer._get_effective_llm_config = AsyncMock(return_value=("openai", "gpt-4", "sk-test"))
            
            with patch("app.shared.llm.guardrails.LLMGuardrails.validate_output") as mock_validate:
                mock_validate.return_value.model_dump.return_value = {"summary": "ok"}
                
                await auth_analyzer.analyze({"c": [{"d": 1}]}, tenant_id=uuid4(), db=AsyncMock())
                
                assert mock_factory.create.called
                mock_factory.create.assert_called_with("openai", api_key="sk-test")

    def test_strip_markdown_variants(self, analyzer):
        """Test strip_markdown with different inputs (lines 91-95)."""
        assert analyzer._strip_markdown("```json\n{\"test\": 1}\n```") == "{\"test\": 1}"
        assert analyzer._strip_markdown("plain text") == "plain text"

    @pytest.mark.asyncio
    async def test_get_effective_config_no_budget(self, analyzer):
        """Test resolving config when budget is missing (line 190)."""
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_result
        
        prov, model, key = await analyzer._get_effective_llm_config(mock_db, uuid4(), None, None)
        assert prov in ["openai", "groq", "google", "anthropic"] # Accept any default
        assert key is None

    @pytest.mark.asyncio
    async def test_analyze_full_with_usage(self, analyzer, mock_llm):
        """Test full analyze flow with usage tracking (lines 155-156)."""
        mock_response = MagicMock()
        mock_response.content = json.dumps({"summary": "ok", "resources": []})
        mock_response.response_metadata = {"token_usage": {"prompt_tokens": 5, "completion_tokens": 5}}
        
        mock_chain = MagicMock()
        mock_chain.ainvoke = AsyncMock(return_value=mock_response)
        
        with patch("app.shared.llm.zombie_analyzer.ChatPromptTemplate") as mock_prompt_cls, \
             patch("app.shared.llm.guardrails.LLMGuardrails.validate_output") as mock_validate, \
             patch("app.shared.llm.zombie_analyzer.UsageTracker") as mock_tracker_cls:
            
            mock_prompt_cls.from_messages.return_value.__or__.return_value = mock_chain
            mock_validate.return_value.model_dump.return_value = {"summary": "Valid"}
            
            db = AsyncMock()
            tenant_id = uuid4()
            
            auth_analyzer = ZombieAnalyzer(mock_llm)
            auth_analyzer._get_effective_llm_config = AsyncMock(return_value=("openai", "gpt-4", None))
            
            await auth_analyzer.analyze({"c": [{"d": 1}]}, tenant_id=tenant_id, db=db)
            
            assert mock_tracker_cls.called
