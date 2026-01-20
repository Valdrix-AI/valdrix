from typing import Dict, Any, Optional
import json
import re
import copy
import structlog
from uuid import UUID

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.services.llm.usage_tracker import UsageTracker
from app.services.notifications import SlackService
from app.services.cache import get_cache_service
from app.services.llm.guardrails import LLMGuardrails, FinOpsAnalysisResult
from app.services.analysis.forecaster import SymbolicForecaster
from app.services.llm.factory import LLMFactory
from opentelemetry import trace
tracer = trace.get_tracer(__name__)
logger = structlog.get_logger()

from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)
from app.core.exceptions import AIAnalysisError

# System prompts are now managed in prompts.yaml

class FinOpsAnalyzer:
    """
    The 'Brain' of Valdrix.

    This class wraps a LangChain ChatModel and orchestrates the analysis of cost data.
    It uses a specialized System Prompt to enforce strict JSON output for programmatic use.
    """
    def __init__(self, llm: BaseChatModel, db: Optional[AsyncSession] = None):
        self.llm = llm
        self.db = db
        
        # Load prompt from registry (Phase 21: Audit Hardening)
        import yaml
        import os
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts.yaml")
        system_prompt = None
        
        try:
            if os.path.exists(prompt_path):
                with open(prompt_path, "r") as f:
                    registry = yaml.safe_load(f)
                    if isinstance(registry, dict) and "finops_analysis" in registry:
                        system_prompt = registry["finops_analysis"].get("system")
        except Exception as e:
            logger.error("failed_to_load_prompts_yaml", error=str(e), path=prompt_path)
            
        if not system_prompt:
            # Item 20: Robust Fallback Prompt
            logger.warning("using_fallback_system_prompt")
            system_prompt = (
                "You are a FinOps expert. Analyze the provided cloud cost data. "
                "Identify anomalies, waste, and optimization opportunities. "
                "You MUST return the analysis in valid JSON format only, "
                "with the keys: 'summary', 'anomalies' (list), 'recommendations' (list), "
                "and 'estimated_total_savings'."
            )
            
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "Analyze this cloud cost data:\n{cost_data}")
        ])

    def _strip_markdown(self, text: str) -> str:
        """
        Removes markdown code block wrappers from LLM responses.
        LLMs often ignore 'no markdown' instructions.
        """
        # Pattern matches ```json ... ``` or just ``` ... ```
        pattern = r'^```(?:json)?\s*\n?(.*?)\n?```$'
        match = re.match(pattern, text.strip(), re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

    async def analyze(
        self,
        usage_summary: "CloudUsageSummary",
        tenant_id: Optional[UUID] = None,
        db: Optional[AsyncSession] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """
        Takes normalized cloud usage data and returns AI-generated insights.
        
        This method handles:
        1. Cache and Delta Analysis checks.
        2. LLM client setup and budget verification.
        3. LangChain orchestration (Prompt -> LLM -> Output).
        4. Usage tracking and result processing.
        
        Args:
            usage_summary: The aggregated cost data to analyze.
            tenant_id: Tenant UUID for usage tracking and budget checks.
            db: Database session for persistence.
            provider: Optional provider override.
            model: Optional model override.
            force_refresh: bypass cache if True.
            
        Returns:
            A dictionary containing AI insights, recommendations, and anomalies.
            
        Raises:
            AIAnalysisError: If the LLM invocation or result processing fails.
            BudgetExceededError: If the tenant's LLM budget is exceeded.
        """
        from app.schemas.costs import CloudUsageSummary
        from app.core.exceptions import AIAnalysisError

        with tracer.start_as_current_span("analyze_costs") as span:
            span.set_attribute("tenant_id", str(tenant_id) if tenant_id else "anonymous")
            
            # 1. Cache & Delta Logic
            cached_analysis, is_delta = await self._check_cache_and_delta(
                tenant_id, force_refresh, usage_summary
            )
            if cached_analysis and not is_delta:
                return cached_analysis

            logger.info("starting_analysis", 
                        tenant_id=str(tenant_id), 
                        data_points=len(usage_summary.records),
                        mode="delta" if is_delta else "full",
                        cache_miss=not cached_analysis)

            # 2. Prepare Data & Pre-Authorize
            sanitized_data = await LLMGuardrails.sanitize_input(usage_summary.model_dump())
            # Add symbolic forecast to input for analysis
            from app.services.analysis.forecaster import SymbolicForecaster
            # 1.5 Get Symbolic Forecast (Grounding logic)
            # Use passed db, fallback to self.db
            effective_db = db or self.db
            sanitized_data["symbolic_forecast"] = await SymbolicForecaster.forecast(
                usage_summary.records,
                db=effective_db,
                tenant_id=tenant_id
            )
            formatted_data = json.dumps(sanitized_data, default=str)

            usage_tracker, effective_provider, effective_model, byok_key = \
                await self._setup_client_and_usage(tenant_id, db, provider, model, input_text=formatted_data)

            # 3. Invoke LLM
            response_content, response_metadata = await self._invoke_llm(
                formatted_data, effective_provider, effective_model, byok_key
            )

            # 4. Track Usage
            await self._track_usage(
                usage_tracker, tenant_id, effective_provider, effective_model, 
                response_metadata, byok_key
            )

            # 5. Post-Process & Alert
            return await self._process_analysis_results(
                response_content, tenant_id, usage_summary
            )

    async def _check_cache_and_delta(
        self, tenant_id: Optional[UUID], force_refresh: bool, usage_summary: Any
    ) -> tuple[Optional[Dict], bool]:
        """Checks cache and determines if delta analysis should be performed."""
        if not tenant_id:
            return None, False

        cache = get_cache_service()
        cached_analysis = await cache.get_analysis(tenant_id) if not force_refresh else None
        
        if cached_analysis and not get_settings().ENABLE_DELTA_ANALYSIS:
            logger.info("analysis_cache_hit_full", tenant_id=str(tenant_id))
            return cached_analysis, False

        is_delta = False
        if cached_analysis and get_settings().ENABLE_DELTA_ANALYSIS:
            is_delta = True
            logger.info("analysis_delta_mode_enabled", tenant_id=str(tenant_id))
            from datetime import date, timedelta
            settings = get_settings()
            delta_cutoff = date.today() - timedelta(days=settings.DELTA_ANALYSIS_DAYS)
            
            # BE-LLM-3: Data Safety - Pass a filtered copy to avoid polluting original object
            # This ensures subsequent processing in the same request uses the full data if needed.
            records_to_analyze = [copy.deepcopy(r) for r in cached_analysis.get("records", []) if r.date >= delta_cutoff] \
                if isinstance(cached_analysis, dict) else [copy.deepcopy(r) for r in usage_summary.records if r.date >= delta_cutoff]
            
            if not records_to_analyze:
                logger.info("analysis_delta_no_new_data", tenant_id=str(tenant_id))
                return cached_analysis, True

            # Create a shallow copy of summary but with filtered records
            usage_summary_copy = copy.copy(usage_summary)
            usage_summary_copy.records = records_to_analyze
            return cached_analysis, True # We don't return the copy here, handle in analyze()

        return cached_analysis, is_delta

    async def _setup_client_and_usage(
        self, 
        tenant_id: Optional[UUID], 
        db: Optional[AsyncSession], 
        provider: Optional[str], 
        model: Optional[str],
        input_text: Optional[str] = None
    ) -> tuple[Optional[UsageTracker], str, str, Optional[str]]:
        """Handles budget checks and determines the effective LLM provider/model."""
        usage_tracker = None
        byok_key = None
        budget = None
        
        if tenant_id and db:
            usage_tracker = UsageTracker(db)
            from app.services.llm.usage_tracker import BudgetStatus
            budget_status = await usage_tracker.check_budget(tenant_id)
            
            if budget_status == BudgetStatus.HARD_LIMIT:
                from app.core.exceptions import BudgetExceededError
                raise BudgetExceededError("Monthly LLM budget exceeded (Hard Limit).")

            from app.models.llm import LLMBudget
            result = await db.execute(select(LLMBudget).where(LLMBudget.tenant_id == tenant_id))
            budget = result.scalar_one_or_none()
            if budget:
                keys = {
                    "openai": budget.openai_api_key,
                    "claude": budget.claude_api_key,
                    "anthropic": budget.claude_api_key,
                    "google": budget.google_api_key,
                    "groq": budget.groq_api_key,
                    "azure": budget.azure_api_key
                }
                byok_key = keys.get(provider or budget.preferred_provider)

        # BE-LLM-2: Provider & Model Validation (SEC-LLM)
        VALID_MODELS = {
            "openai": ["gpt-4", "gpt-4-turbo", "gpt-4o", "gpt-4o-mini", "gpt-3.5-turbo"],
            "anthropic": ["claude-3-opus", "claude-3-sonnet", "claude-3-5-sonnet", "claude-3-5-haiku"],
            "google": ["gemini-pro", "gemini-1.5-pro", "gemini-1.5-flash"],
            "groq": ["llama-3.3-70b-versatile", "llama3-70b-8192", "mixtral-8x7b-32768", "llama-3.1-8b-instant"],
            "azure": ["gpt-4", "gpt-35-turbo"]
        }

        effective_provider = provider or (budget.preferred_provider if budget else get_settings().LLM_PROVIDER)
        effective_model = model or (budget.preferred_model if budget else "llama-3.3-70b-versatile")

        # BE-LLM-11: Hard Pre-Authorization (SEC-LLM)
        if tenant_id and usage_tracker and input_text:
            # We use max_output_tokens=2000 as a safe upper bound for analysis
            await usage_tracker.authorize_request(
                tenant_id=tenant_id,
                provider=effective_provider,
                model=effective_model,
                input_text=input_text,
                max_output_tokens=2000
            )

        # Handle Graceful Degradation (Soft Limit)
        if tenant_id and db and budget_status == BudgetStatus.SOFT_LIMIT:
            logger.warning("llm_budget_soft_limit_degradation", tenant_id=str(tenant_id))
            # Switch to cheapest model for the effective provider
            if effective_provider == "groq":
                effective_model = "llama-3.1-8b-instant"
            elif effective_provider == "openai":
                effective_model = "gpt-4o-mini"
            elif effective_provider == "google":
                effective_model = "gemini-1.5-flash"
            elif effective_provider == "anthropic":
                effective_model = "claude-3-5-haiku"

        if effective_provider not in VALID_MODELS:
            logger.warning("invalid_llm_provider_rejected", provider=effective_provider)
            effective_provider = get_settings().LLM_PROVIDER
            effective_model = "llama-3.3-70b-versatile"

        # Validate against known models for the provider
        allowed_models = VALID_MODELS.get(effective_provider, [])
        if effective_model not in allowed_models:
            # If it's a known provider but unknown model, allow it if it's safe and it's BYOK
            # Otherwise, fallback to the first model in our safe list
            if not (byok_key and re.match(r"^[a-zA-Z0-9\.\-\:\/]+$", str(effective_model))):
                logger.warning("unsupported_model_fallback", provider=effective_provider, model=effective_model)
                effective_model = allowed_models[0] if allowed_models else "llama-3.3-70b-versatile"
        
        return usage_tracker, effective_provider, effective_model, byok_key

    async def _invoke_llm(
        self, formatted_data: str, provider: str, model: str, byok_key: Optional[str]
    ) -> tuple[str, Dict]:
        """Orchestrates the LangChain invocation."""
        # Data is already formatted in analyze()
        pass

        current_llm = self.llm
        if provider != get_settings().LLM_PROVIDER or byok_key:
            current_llm = LLMFactory.create(provider, model=model, api_key=byok_key)

        chain = self.prompt | current_llm

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=4, max=10),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        async def _invoke_with_retry():
            logger.info("invoking_llm", provider=provider, model=model)
            response = await chain.ainvoke({"cost_data": formatted_data})
            return response.content, getattr(response, "response_metadata", {})

        # BE-LLM-7: Fallback model selection on primary failure
        FALLBACK_PROVIDERS = [
            ("groq", "llama-3.3-70b-versatile"),
            ("openai", "gpt-4o-mini"),
            ("anthropic", "claude-3-5-haiku"),
        ]

        with tracer.start_as_current_span("llm_invocation") as span:
            span.set_attribute("llm.provider", provider)
            span.set_attribute("llm.model", model)
            try:
                return await _invoke_with_retry()
            except Exception as primary_error:
                logger.warning("llm_primary_failed_trying_fallbacks", provider=provider, error=str(primary_error))
                
                # Try fallback providers
                for fallback_provider, fallback_model in FALLBACK_PROVIDERS:
                    if fallback_provider == provider:
                        continue  # Skip the one that just failed
                    try:
                        fallback_llm = LLMFactory.create(fallback_provider)
                        fallback_chain = self.prompt | fallback_llm
                        logger.info("trying_fallback_llm", provider=fallback_provider, model=fallback_model)
                        response = await fallback_chain.ainvoke({"cost_data": formatted_data})
                        span.set_attribute("llm.fallback_used", True)
                        span.set_attribute("llm.fallback_provider", fallback_provider)
                        return response.content, getattr(response, "response_metadata", {})
                    except Exception as fallback_error:
                        logger.warning("llm_fallback_failed", provider=fallback_provider, error=str(fallback_error))
                        continue
                
                # All fallbacks failed
                logger.error("llm_all_providers_failed", primary_provider=provider)
                from app.core.exceptions import AIAnalysisError
                raise AIAnalysisError(f"All LLM providers failed. Primary: {provider}, Error: {str(primary_error)}")

    async def _track_usage(
        self, usage_tracker: Optional[UsageTracker], tenant_id: Optional[UUID],
        provider: str, model: str, metadata: Dict, byok_key: Optional[str]
    ):
        """Records LLM usage metrics."""
        if not (tenant_id and usage_tracker):
            return

        try:
            token_usage = metadata.get("token_usage", {})
            await usage_tracker.record(
                tenant_id=tenant_id,
                provider=provider,
                model=model,
                input_tokens=token_usage.get("prompt_tokens", 0),
                output_tokens=token_usage.get("completion_tokens", 0),
                is_byok=byok_key is not None,
                request_type="cost_analysis",
            )
        except Exception as e:
            logger.warning("llm_usage_tracking_failed", error=str(e))

    async def _process_analysis_results(
        self, content: str, tenant_id: Optional[UUID], usage_summary: Any
    ) -> Dict[str, Any]:
        """Validates output, handles alerts, and caches results."""
        cache = get_cache_service()
        
        try:
            # 1. Validate LLM Output
            validated = LLMGuardrails.validate_output(content, FinOpsAnalysisResult)
            llm_result = validated.model_dump()
            
            # 2. Check and Alert for Anomaly
            await self._check_and_alert_anomalies(llm_result)
        except Exception as e:
            logger.warning("llm_validation_failed", error=str(e))
            # Fallback: try raw parsing if validation fails but it's still JSON
            try:
                llm_result = json.loads(self._strip_markdown(content))
            except json.JSONDecodeError as jde:
                logger.error("llm_fallback_json_parse_failed", error=str(jde), content_snippet=content[:100])
                llm_result = {"error": "AI analysis format invalid", "raw_content": content}
            except Exception as ex:
                logger.error("llm_fallback_failed_unexpectedly", error=str(ex))
                llm_result = {"error": "AI analysis processing failed", "raw_content": content}

        # Grounding: What does the deterministic math say?
        effective_db = self.db # In process_analysis_results we only have self.db
        symbolic_forecast = await SymbolicForecaster.forecast(
            usage_summary.records,
            db=effective_db,
            tenant_id=usage_summary.tenant_id
        )
        total_forecasted = float(symbolic_forecast.get("total_forecasted_cost", 0))
        
        final_result = {
            "insights": llm_result.get("insights", []),
            "recommendations": llm_result.get("recommendations", []),
            "anomalies": llm_result.get("anomalies", []),
            "forecast": llm_result.get("forecast", {}),
            "symbolic_forecast": symbolic_forecast,
            "llm_raw": llm_result # Keep for debugging
        }
        
        # 4. Cache the combined result (24h TTL)
        if tenant_id:
            await cache.set_analysis(tenant_id, final_result)
            logger.info("analysis_cached", tenant_id=str(tenant_id))
        
        return final_result

    async def _check_and_alert_anomalies(self, result: Dict):
        """Sends Slack alerts if high-severity anomalies are found."""
        anomalies = result.get("anomalies", [])
        if not anomalies:
            return

        settings = get_settings()
        if settings.SLACK_BOT_TOKEN and settings.SLACK_CHANNEL_ID:
            slack = SlackService(settings.SLACK_BOT_TOKEN, settings.SLACK_CHANNEL_ID)
            top = anomalies[0]
            await slack.send_alert(
                title=f"Cost Anomaly Detected: {top['resource']}",
                message=f"*Issue:* {top['issue']}\n*Impact:* {top['cost_impact']}\n*Severity:* {top['severity']}",
                severity="critical" if top['severity'] == "high" else "warning"
            )
