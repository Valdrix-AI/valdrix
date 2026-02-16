# mypy: disable-error-code=import-untyped
import asyncio
import yaml
import os
import uuid
from typing import Any, Optional, TYPE_CHECKING
import json
import re
import copy
import structlog
from uuid import UUID
from datetime import date, datetime, timedelta

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

from app.shared.core.config import get_settings
from app.shared.llm.usage_tracker import UsageTracker
from app.modules.notifications.domain import (
    get_slack_service,
    get_tenant_slack_service,
)
from app.shared.core.cache import get_cache_service
from app.shared.llm.guardrails import LLMGuardrails, FinOpsAnalysisResult
from app.shared.analysis.forecaster import SymbolicForecaster
from app.shared.llm.factory import LLMFactory
from app.shared.core.exceptions import AIAnalysisError, BudgetExceededError
from app.shared.llm.budget_manager import LLMBudgetManager
from app.shared.core.constants import LLMProvider
from opentelemetry import trace

if TYPE_CHECKING:
    from app.schemas.costs import CloudUsageSummary

tracer = trace.get_tracer(__name__)
logger = structlog.get_logger()

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
        # Prompts are now loaded lazily or cached at module level to avoid blocking I/O
        self.prompt: Optional[ChatPromptTemplate] = None

    async def _get_prompt(self) -> ChatPromptTemplate:
        """Loads and caches the prompt template asynchronously."""
        if self.prompt is not None:
            return self.prompt

        system_prompt = await self._load_system_prompt_async()
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", system_prompt),
                ("user", "Analyze this cloud cost data:\n{cost_data}"),
            ]
        )
        return self.prompt

    async def _load_system_prompt_async(self) -> str:
        """Loads the system prompt from yaml in a thread pool or returns fallback."""
        prompt_path = os.path.join(os.path.dirname(__file__), "prompts.yaml")

        try:
            if os.path.exists(prompt_path):
                # PRODUCTION: Offload blocking I/O to a thread pool
                loop = asyncio.get_running_loop()

                def _read_file() -> Any:
                    with open(prompt_path, "r") as f:
                        return yaml.safe_load(f)

                registry = await loop.run_in_executor(None, _read_file)
                if isinstance(registry, dict) and "finops_analysis" in registry:
                    prompt = registry["finops_analysis"].get("system")
                    if isinstance(prompt, str) and prompt.strip():
                        return prompt
        except Exception as e:
            logger.error("failed_to_load_prompts_yaml", error=str(e), path=prompt_path)

        # Item 20: Robust Fallback Prompt
        logger.warning("using_fallback_system_prompt")
        return (
            "You are a FinOps expert. Analyze the provided cloud cost data. "
            "Identify anomalies, waste, and optimization opportunities. "
            "You MUST return the analysis in valid JSON format only, "
            "with the keys: 'summary', 'anomalies' (list), 'recommendations' (list), "
            "and 'estimated_total_savings'."
        )

    def _strip_markdown(self, text: str) -> str:
        """
        Removes markdown code block wrappers from LLM responses.
        LLMs often ignore 'no markdown' instructions.
        """
        # Pattern matches ```json ... ``` or just ``` ... ```
        pattern = r"^```(?:\w+)?\s*\n?(.*?)\n?```$"
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
    ) -> dict[str, Any]:
        """
        PRODUCTION: Analyzes cloud costs with mandatory budget pre-authorization.

        Flow:
        1. Check cache (return if hit)
        2. Pre-authorize LLM budget (HARD BLOCK if exceeded)
        3. Call LLM with authorized reservation
        4. Record actual usage on success
        5. Release reservation on failure (optional, handled by lack of record_usage)
        """
        operation_id = str(uuid.uuid4())
        effective_db = db or self.db

        with tracer.start_as_current_span("analyze_costs") as span:
            span.set_attribute(
                "tenant_id", str(tenant_id) if tenant_id else "anonymous"
            )
            span.set_attribute("operation_id", operation_id)

            # 1. Cache & Delta Logic
            cached_analysis, is_delta = await self._check_cache_and_delta(
                tenant_id, force_refresh, usage_summary
            )
            if cached_analysis and not is_delta:
                logger.info(
                    "analysis_cache_hit",
                    tenant_id=str(tenant_id),
                    operation_id=operation_id,
                )
                return cached_analysis

            records_for_analysis = getattr(
                usage_summary, "_analysis_records_override", usage_summary.records
            )
            if records_for_analysis is usage_summary.records:
                usage_summary_to_analyze = usage_summary
            else:
                usage_summary_to_analyze = copy.copy(usage_summary)
                usage_summary_to_analyze.records = records_for_analysis
                if hasattr(usage_summary, "_analysis_records_override"):
                    delattr(usage_summary, "_analysis_records_override")

            logger.info(
                "starting_analysis",
                tenant_id=str(tenant_id),
                data_points=len(usage_summary_to_analyze.records),
                mode="delta" if is_delta else "full",
                operation_id=operation_id,
            )

            # 2. PRODUCTION: PRE-AUTHORIZE LLM BUDGET (HARD BLOCK)
            reserved_amount = None

            # Safely get model name from LLM object, handling mocks in tests
            llm_model = getattr(
                self.llm,
                "model_name",
                getattr(self.llm, "model", "llama-3.3-70b-versatile"),
            )
            effective_model = model or llm_model

            try:
                if tenant_id and effective_db:
                    # Estimate tokens: 1 record ≈ 20 tokens, min 500
                    prompt_tokens = max(500, len(usage_summary_to_analyze.records) * 20)
                    completion_tokens = 500

                    reserved_amount = await LLMBudgetManager.check_and_reserve(
                        tenant_id=tenant_id,
                        db=effective_db,
                        model=effective_model,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        operation_id=operation_id,
                    )

                    logger.info(
                        "llm_budget_authorized",
                        tenant_id=str(tenant_id),
                        reserved_amount=float(reserved_amount),
                        operation_id=operation_id,
                    )
            except BudgetExceededError:
                raise
            except Exception as e:
                logger.error(
                    "budget_check_failed_unexpected",
                    error=str(e),
                    operation_id=operation_id,
                )
                # Fail open or closed? PRODUCTION: Fail closed if it's a known tenant
                if tenant_id:
                    raise AIAnalysisError(
                        f"Budget verification failed: {str(e)}"
                    ) from e

            # 3. Prepare Data
            try:
                sanitized_data = await LLMGuardrails.sanitize_input(
                    usage_summary_to_analyze.model_dump()
                )
                sanitized_data["symbolic_forecast"] = await SymbolicForecaster.forecast(
                    usage_summary_to_analyze.records,
                    db=effective_db,
                    tenant_id=tenant_id,
                )
                formatted_data = json.dumps(sanitized_data, default=str)
            except Exception as e:
                logger.error(
                    "data_preparation_failed", error=str(e), operation_id=operation_id
                )
                raise AIAnalysisError(f"Failed to prepare data: {str(e)}")

            # 4. Invoke LLM
            try:
                # Note: _setup_client_and_usage might still be needed for BYOK keys
                (
                    usage_tracker,
                    effective_provider,
                    final_model,
                    byok_key,
                ) = await self._setup_client_and_usage(
                    tenant_id,
                    effective_db,
                    provider,
                    effective_model,
                    input_text=formatted_data,
                )

                response_content, response_metadata = await self._invoke_llm(
                    formatted_data, effective_provider, final_model, byok_key
                )
            except Exception as e:
                logger.error(
                    "llm_invocation_failed", error=str(e), operation_id=operation_id
                )
                raise

            # 5. PRODUCTION: Record Usage
            if reserved_amount and effective_db:
                try:
                    # In production, we'd parse actual tokens from response_metadata
                    token_usage = response_metadata.get("token_usage", {})
                    if tenant_id is None:
                        raise AIAnalysisError(
                            "Tenant ID required to record metered LLM usage"
                        )
                    await LLMBudgetManager.record_usage(
                        tenant_id=tenant_id,
                        db=effective_db,
                        model=final_model,
                        provider=effective_provider,
                        prompt_tokens=token_usage.get("prompt_tokens", 500),
                        completion_tokens=token_usage.get("completion_tokens", 500),
                        is_byok=bool(byok_key),
                        operation_id=operation_id,
                    )
                except Exception as e:
                    logger.warning(
                        "usage_recording_failed",
                        error=str(e),
                        operation_id=operation_id,
                    )

            # 6. Post-Process
            return await self._process_analysis_results(
                response_content, tenant_id, usage_summary_to_analyze, db=effective_db
            )

    async def _check_cache_and_delta(
        self, tenant_id: Optional[UUID], force_refresh: bool, usage_summary: Any
    ) -> tuple[dict[str, Any] | None, bool]:
        """Checks cache and determines if delta analysis should be performed."""
        if not tenant_id:
            return None, False

        cache = get_cache_service()
        cached_analysis = (
            await cache.get_analysis(tenant_id) if not force_refresh else None
        )

        if cached_analysis and not get_settings().ENABLE_DELTA_ANALYSIS:
            logger.info("analysis_cache_hit_full", tenant_id=str(tenant_id))
            return cached_analysis, False

        is_delta = False
        if cached_analysis and get_settings().ENABLE_DELTA_ANALYSIS:
            is_delta = True
            logger.info("analysis_delta_mode_enabled", tenant_id=str(tenant_id))
            settings = get_settings()
            delta_cutoff = date.today() - timedelta(days=settings.DELTA_ANALYSIS_DAYS)

            # BE-LLM-3: Data Safety - Pass a filtered copy to avoid polluting original object
            # This ensures subsequent processing in the same request uses the full data if needed.
            from app.schemas.costs import CostRecord

            raw_records = (
                cached_analysis.get("records", [])
                if isinstance(cached_analysis, dict)
                else usage_summary.records
            )
            records_to_analyze = []
            for r in raw_records:
                r_dt = r.get("date") if isinstance(r, dict) else r.date

                if isinstance(r_dt, datetime):
                    r_date = r_dt.date()
                elif isinstance(r_dt, date):
                    r_date = r_dt
                elif isinstance(r_dt, str):
                    try:
                        r_date = date.fromisoformat(r_dt[:10])
                    except ValueError:
                        continue
                else:
                    continue

                if r_date >= delta_cutoff:
                    # Ensure we have CostRecord objects for the summary copy
                    if isinstance(r, dict):
                        records_to_analyze.append(CostRecord(**r))
                    else:
                        records_to_analyze.append(copy.deepcopy(r))

            if not records_to_analyze:
                logger.info("analysis_delta_no_new_data", tenant_id=str(tenant_id))
                return cached_analysis, False

            # Store filtered records for analysis without mutating the original records list
            usage_summary._analysis_records_override = records_to_analyze

        return cached_analysis, is_delta

    async def _setup_client_and_usage(
        self,
        tenant_id: Optional[UUID],
        db: Optional[AsyncSession],
        provider: Optional[str],
        model: Optional[str],
        input_text: Optional[str] = None,
    ) -> tuple[Optional[UsageTracker], str, str, Optional[str]]:
        """Handles budget checks and determines the effective LLM provider/model."""
        usage_tracker = None
        byok_key = None
        budget = None
        budget_status = None

        def _normalize_provider(value: Any) -> str:
            if isinstance(value, LLMProvider):
                return value.value
            if isinstance(value, str):
                return value.lower()
            return ""

        if tenant_id and db:
            usage_tracker = UsageTracker(db)
            from app.shared.llm.usage_tracker import BudgetStatus

            budget_status = await usage_tracker.check_budget(tenant_id)

            if budget_status == BudgetStatus.HARD_LIMIT:
                from app.shared.core.exceptions import BudgetExceededError

                raise BudgetExceededError("Monthly LLM budget exceeded (Hard Limit).")

            from app.models.llm import LLMBudget

            result = await db.execute(
                select(LLMBudget).where(LLMBudget.tenant_id == tenant_id)
            )
            budget = result.scalar_one_or_none()
            if budget:
                keys: dict[str, str | None] = {
                    LLMProvider.OPENAI: budget.openai_api_key,
                    LLMProvider.ANTHROPIC: budget.claude_api_key,  # unified
                    LLMProvider.GOOGLE: budget.google_api_key,
                    LLMProvider.GROQ: budget.groq_api_key,
                    LLMProvider.AZURE: getattr(budget, "azure_api_key", None),
                }
                requested_provider = _normalize_provider(
                    provider
                ) or _normalize_provider(budget.preferred_provider)
                byok_key = keys.get(requested_provider)

        # Provider & Model Validation
        valid_models: dict[str, list[str]] = {
            LLMProvider.OPENAI.value: [
                "gpt-4",
                "gpt-4-turbo",
                "gpt-4o",
                "gpt-4o-mini",
                "gpt-3.5-turbo",
            ],
            LLMProvider.ANTHROPIC.value: [
                "claude-3-opus",
                "claude-3-sonnet",
                "claude-3-5-sonnet",
                "claude-3-5-haiku",
            ],
            LLMProvider.GOOGLE.value: [
                "gemini-pro",
                "gemini-1.5-pro",
                "gemini-1.5-flash",
            ],
            LLMProvider.GROQ.value: [
                "llama-3.3-70b-versatile",
                "llama3-70b-8192",
                "mixtral-8x7b-32768",
                "llama-3.1-8b-instant",
            ],
            LLMProvider.AZURE.value: ["gpt-4", "gpt-35-turbo"],
        }

        preferred_provider = provider or (
            budget.preferred_provider if budget else get_settings().LLM_PROVIDER
        )
        effective_provider = (
            _normalize_provider(preferred_provider) or LLMProvider.GROQ.value
        )
        effective_model = str(
            model or (budget.preferred_model if budget else "llama-3.3-70b-versatile")
        )

        # Handle Graceful Degradation (Soft Limit)
        if tenant_id and db and budget_status == BudgetStatus.SOFT_LIMIT:
            logger.warning(
                "llm_budget_soft_limit_degradation", tenant_id=str(tenant_id)
            )
            # Switch to cheapest model for the effective provider
            if effective_provider == LLMProvider.GROQ.value:
                effective_model = "llama-3.1-8b-instant"
            elif effective_provider == LLMProvider.OPENAI.value:
                effective_model = "gpt-4o-mini"
            elif effective_provider == LLMProvider.GOOGLE.value:
                effective_model = "gemini-1.5-flash"
            elif effective_provider == LLMProvider.ANTHROPIC.value:
                effective_model = "claude-3-5-haiku"

        if effective_provider not in valid_models:
            logger.warning("invalid_llm_provider_rejected", provider=effective_provider)
            effective_provider = get_settings().LLM_PROVIDER
            effective_model = "llama-3.3-70b-versatile"

        # Validate against known models for the provider
        allowed_models = valid_models.get(effective_provider, [])
        if effective_model not in allowed_models:
            # If it's a known provider but unknown model, allow it if it's safe and it's BYOK
            # Otherwise, fallback to the first model in our safe list
            if not (
                byok_key and re.match(r"^[a-zA-Z0-9\.\-\:\/]+$", str(effective_model))
            ):
                logger.warning(
                    "unsupported_model_fallback",
                    provider=effective_provider,
                    model=effective_model,
                )
                effective_model = (
                    allowed_models[0] if allowed_models else "llama-3.3-70b-versatile"
                )

        return usage_tracker, effective_provider, effective_model, byok_key

    async def _invoke_llm(
        self, formatted_data: str, provider: str, model: str, byok_key: Optional[str]
    ) -> tuple[str, dict[str, Any]]:
        """Orchestrates the LangChain invocation."""
        current_llm = self.llm
        if provider != get_settings().LLM_PROVIDER or byok_key:
            current_llm = LLMFactory.create(provider, model=model, api_key=byok_key)

        prompt_template = await self._get_prompt()
        chain = prompt_template | current_llm

        @retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=4, max=10),
            retry=retry_if_exception_type(Exception),
            reraise=True,
        )
        async def _invoke_with_retry() -> tuple[str, dict[str, Any]]:
            logger.info("invoking_llm", provider=provider, model=model)
            response = await chain.ainvoke({"cost_data": formatted_data})
            content = response.content
            safe_content = (
                content
                if isinstance(content, str)
                else json.dumps(content, default=str)
            )
            metadata = getattr(response, "response_metadata", {})
            return safe_content, metadata if isinstance(metadata, dict) else {}

        # BE-LLM-7: Fallback model selection on primary failure
        # Aligned with DR_RUNBOOK.md: Groq -> Gemini -> OpenAI
        FALLBACK_PROVIDERS = [
            (LLMProvider.GROQ, "llama-3.3-70b-versatile"),
            (LLMProvider.GOOGLE, "gemini-1.5-flash"),
            (LLMProvider.OPENAI, "gpt-4o-mini"),
        ]

        with tracer.start_as_current_span("llm_invocation") as span:
            span.set_attribute("llm.provider", provider)
            span.set_attribute("llm.model", model)
            try:
                return await _invoke_with_retry()
            except Exception as primary_error:
                logger.warning(
                    "llm_primary_failed_trying_fallbacks",
                    provider=provider,
                    error=str(primary_error),
                )

                # Try fallback providers
                for fallback_provider, fallback_model in FALLBACK_PROVIDERS:
                    if fallback_provider == provider:
                        continue  # Skip the one that just failed
                    try:
                        fallback_llm = LLMFactory.create(
                            fallback_provider, model=fallback_model
                        )
                        fallback_chain = prompt_template | fallback_llm
                        logger.info(
                            "trying_fallback_llm",
                            provider=fallback_provider,
                            model=fallback_model,
                        )
                        response = await fallback_chain.ainvoke(
                            {"cost_data": formatted_data}
                        )
                        content = response.content
                        safe_content = (
                            content
                            if isinstance(content, str)
                            else json.dumps(content, default=str)
                        )
                        metadata = getattr(response, "response_metadata", {})
                        span.set_attribute("llm.fallback_used", True)
                        span.set_attribute("llm.fallback_provider", fallback_provider)
                        return safe_content, metadata if isinstance(
                            metadata, dict
                        ) else {}
                    except Exception as fallback_error:
                        logger.warning(
                            "llm_fallback_failed",
                            provider=fallback_provider,
                            error=str(fallback_error),
                        )
                        continue

                # All fallbacks failed
                logger.error("llm_all_providers_failed", primary_provider=provider)
                from app.shared.core.exceptions import AIAnalysisError

                raise AIAnalysisError(
                    f"All LLM providers failed. Primary: {provider}, Error: {str(primary_error)}"
                )

    async def _process_analysis_results(
        self,
        content: str,
        tenant_id: Optional[UUID],
        usage_summary: Any,
        db: Optional[AsyncSession] = None,
    ) -> dict[str, Any]:
        """Validates output, handles alerts, and caches results."""
        cache = get_cache_service()

        try:
            # 1. Validate LLM Output
            validated = LLMGuardrails.validate_output(content, FinOpsAnalysisResult)
            llm_result = validated.model_dump()

            # 2. Check and Alert for Anomaly
            await self._check_and_alert_anomalies(
                llm_result, tenant_id=tenant_id, db=db
            )
        except Exception as e:
            logger.warning("llm_validation_failed", error=str(e))
            # Fallback: try raw parsing if validation fails but it's still JSON
            try:
                llm_result = json.loads(self._strip_markdown(content))
            except json.JSONDecodeError as jde:
                logger.error(
                    "llm_fallback_json_parse_failed",
                    error=str(jde),
                    content_snippet=content[:100],
                )
                llm_result = {
                    "error": "AI analysis format invalid",
                    "raw_content": content,
                }
            except Exception as ex:
                logger.error("llm_fallback_failed_unexpectedly", error=str(ex))
                llm_result = {
                    "error": "AI analysis processing failed",
                    "raw_content": content,
                }

        if not isinstance(llm_result, dict):
            llm_result = {
                "error": "AI analysis produced non-object payload",
                "raw_content": llm_result,
            }

        # Grounding: What does the deterministic math say?
        effective_db = db or self.db
        symbolic_forecast = await SymbolicForecaster.forecast(
            usage_summary.records, db=effective_db, tenant_id=usage_summary.tenant_id
        )

        final_result = {
            "insights": llm_result.get("insights", []),
            "recommendations": llm_result.get("recommendations", []),
            "anomalies": llm_result.get("anomalies", []),
            "forecast": llm_result.get("forecast", {}),
            "symbolic_forecast": symbolic_forecast,
            "llm_raw": llm_result,  # Keep for debugging
        }

        # 4. Cache the combined result (24h TTL)
        if tenant_id:
            await cache.set_analysis(tenant_id, final_result)
            logger.info("analysis_cached", tenant_id=str(tenant_id))

        return final_result

    async def _check_and_alert_anomalies(
        self,
        result: dict[str, Any],
        tenant_id: Optional[UUID] = None,
        db: Optional[AsyncSession] = None,
    ) -> None:
        """Sends Slack alerts if high-severity anomalies are found."""
        anomalies = result.get("anomalies", [])
        if not anomalies:
            return

        try:
            slack = None
            if tenant_id:
                if db is None:
                    logger.warning(
                        "anomaly_alert_skipped_missing_tenant_db_context",
                        tenant_id=str(tenant_id),
                    )
                    return
                slack = await get_tenant_slack_service(db, tenant_id)
            else:
                slack = get_slack_service()

            if not slack:
                return

            top = anomalies[0]
            await slack.send_alert(
                title=f"Cost Anomaly Detected: {top['resource']}",
                message=f"*Issue:* {top['issue']}\n*Impact:* {top['cost_impact']}\n*Severity:* {top['severity']}",
                severity="critical" if top["severity"] == "high" else "warning",
            )
        except Exception as exc:
            logger.warning(
                "anomaly_alert_dispatch_failed",
                tenant_id=str(tenant_id) if tenant_id else None,
                error=str(exc),
            )
