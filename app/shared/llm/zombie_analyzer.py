"""
Zombie Resource Analyzer - AI-powered explanations for detected zombie resources.

Uses LLM to provide:
- Human-readable explanations for why resources are considered "zombies"
- Risk assessment and confidence scores
- Recommended remediation actions
- Estimated savings breakdown
"""

from typing import Dict, Any, List, Optional
from uuid import UUID
import json
import re
import structlog

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.shared.core.config import get_settings
from app.shared.core.pricing import get_tenant_tier, get_tier_limit
from app.shared.llm.budget_manager import LLMBudgetManager
from app.shared.llm.guardrails import LLMGuardrails, ZombieAnalysisResult

logger = structlog.get_logger()

ZOMBIE_ANALYSIS_PROMPT = """You are a Cloud+ FinOps expert analyzing zombie (unused/underutilized) resources across IaaS and Cloud+ providers.

INPUT: A list of detected zombie resources with their metadata.

YOUR TASK:
1. Explain WHY each resource is considered a zombie in plain English
2. Assess the confidence level of each detection
3. Recommend specific actions for each resource
4. Calculate the total potential savings

OUTPUT FORMAT (STRICT JSON ONLY):
{{
  "summary": "Brief 1-2 sentence overview of findings",
  "total_monthly_savings": "$X.XX",
  "resources": [
    {{
      "resource_id": "the resource identifier",
      "resource_type": "type of resource",
      "provider": "aws|azure|gcp|saas|license|platform|hybrid",
      "explanation": "Why this is a zombie - be specific and clear",
      "confidence": "high|medium|low",
      "confidence_score": 0.0-1.0,
      "confidence_reason": "Why you rated this confidence level",
      "recommended_action": "What to do with this resource",
      "monthly_cost": "$X.XX",
      "risk_if_deleted": "low|medium|high",
      "risk_explanation": "Brief explanation of deletion risk",
      "owner": "principal/user email if provided",
      "is_gpu": true|false
    }}
  ],
  "general_recommendations": [
    "List of overall recommendations for preventing future zombie resources"
  ]
}}

IMPORTANT RULES:
- Base conclusions ONLY on provided data
- Preserve the Cloud Provider for each resource (aws|azure|gcp|saas|license|platform|hybrid)
- Provide a numeric confidence_score (0.0 to 1.0) where 1.0 is highest
- Be conservative with confidence ratings
- Always explain the risk of deleting each resource
- If unsure, recommend review before deletion
- Output ONLY valid JSON, no markdown
"""


class ZombieAnalyzer:
    """
    AI-powered analyzer for zombie resources.

    Takes rule-based detection results and enriches them with LLM explanations.
    """

    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self.prompt = ChatPromptTemplate.from_messages(
            [
                ("system", ZOMBIE_ANALYSIS_PROMPT),
                (
                    "user",
                    "Analyze these detected zombie resources:\n\n[BEGIN DATA]\n{zombie_data}\n[END DATA]",
                ),
            ]
        )

    def _strip_markdown(self, text: str) -> str:
        """Remove markdown code block wrappers from LLM responses."""
        pattern = r"^```(?:json)?\s*\n?(.*?)\n?```$"
        match = re.match(pattern, text.strip(), re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

    def _flatten_zombies(
        self, detection_results: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Flatten nested zombie categories into a single list for LLM analysis."""
        flattened = []

        # Skip metadata keys
        skip_keys = {
            "region",
            "scanned_at",
            "total_monthly_waste",
            "errors",
            "details",
            "scanned_connections",
            "waste_rightsizing",
            "architectural_inefficiency",
            "ai_analysis",
            "partial_scan",
            "scan_timeout",
            "partial_results",
        }

        for category, items in detection_results.items():
            if category in skip_keys:
                continue
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        item["category"] = category
                        flattened.append(item)

        return flattened

    @staticmethod
    def _resolve_output_token_ceiling(raw_limit: Any) -> int | None:
        if raw_limit is None:
            return None
        try:
            parsed = int(raw_limit)
        except (TypeError, ValueError):
            return None
        if parsed <= 0:
            return None
        return max(128, min(parsed, 32768))

    async def analyze(
        self,
        detection_results: Dict[str, Any],
        tenant_id: Optional[UUID] = None,
        db: Optional[AsyncSession] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Analyze detected zombie resources with LLM."""
        zombies = self._flatten_zombies(detection_results)
        if not zombies:
            return {
                "summary": "No zombie resources detected.",
                "total_monthly_savings": "$0.00",
                "resources": [],
                "general_recommendations": [],
            }

        logger.info("zombie_analysis_starting", zombie_count=len(zombies))

        # 1. Resolve LLM Configuration
        max_output_tokens: Optional[int] = None
        if tenant_id and db:
            tier = await get_tenant_tier(tenant_id, db)
            max_output_tokens = self._resolve_output_token_ceiling(
                get_tier_limit(tier, "llm_output_max_tokens")
            )

        (
            effective_provider,
            effective_model,
            byok_key,
        ) = await self._get_effective_llm_config(db, tenant_id, provider, model)

        # 2. Build/Get LLM Instance
        current_llm = self.llm
        if effective_provider != get_settings().LLM_PROVIDER or byok_key:
            from app.shared.llm.factory import LLMFactory

            current_llm = LLMFactory.create(
                effective_provider,
                model=effective_model,
                api_key=byok_key,
                max_output_tokens=max_output_tokens,
            )

        # 3. Sanitize and Format
        sanitized_zombies = await LLMGuardrails.sanitize_input(zombies)
        formatted_data = json.dumps(sanitized_zombies, default=str, indent=2)

        # 3b. Pre-authorize usage against tier/budget guardrails.
        if tenant_id and db:
            prompt_tokens = max(500, len(formatted_data) // 4)
            await LLMBudgetManager.check_and_reserve(
                tenant_id=tenant_id,
                db=db,
                provider=effective_provider,
                model=effective_model,
                prompt_tokens=prompt_tokens,
                completion_tokens=max_output_tokens or 1200,
            )

        # 4. Invoke LLM
        chain = self.prompt | current_llm
        response = await chain.ainvoke({"zombie_data": formatted_data})

        # 5. Track Usage
        if tenant_id and db:
            await self._record_usage(
                db,
                tenant_id,
                effective_provider,
                effective_model,
                response,
                byok_key is not None,
            )

        # 6. Parse and Validate
        response_content = response.content
        response_text = (
            response_content
            if isinstance(response_content, str)
            else json.dumps(response_content, default=str)
        )
        try:
            validated_result = LLMGuardrails.validate_output(
                response_text, ZombieAnalysisResult
            )
            analysis = validated_result.model_dump()
            logger.info(
                "zombie_analysis_complete",
                resource_count=len(analysis.get("resources", [])),
            )
            return analysis
        except ValueError as e:
            logger.error("zombie_analysis_validation_failed", error=str(e))
            return {
                "summary": "Analysis completed but response parsing failed.",
                "total_monthly_savings": f"${detection_results.get('total_monthly_waste', 0):.2f}",
                "resources": [],
                "general_recommendations": ["Review detected resources manually."],
                "raw_response": response_text,
                "parse_error": str(e),
            }

    async def _get_effective_llm_config(
        self,
        db: Optional[AsyncSession],
        tenant_id: Optional[UUID],
        provider: Optional[str],
        model: Optional[str],
    ) -> tuple[str, str, Optional[str]]:
        """Resolves the best provider, model, and optional BYOK key."""
        effective_provider = provider
        effective_model = model
        byok_key = None

        if tenant_id and db:
            from app.models.llm import LLMBudget

            result = await db.execute(
                select(LLMBudget).where(LLMBudget.tenant_id == tenant_id).limit(1)
            )
            budget = result.scalar_one_or_none()
            if budget:
                effective_provider = effective_provider or budget.preferred_provider
                effective_model = effective_model or budget.preferred_model

                # Extract BYOK key if applicable
                prov = effective_provider or get_settings().LLM_PROVIDER
                if prov == "openai":
                    byok_key = budget.openai_api_key
                elif prov in ["claude", "anthropic"]:
                    byok_key = budget.claude_api_key
                elif prov == "google":
                    byok_key = budget.google_api_key
                elif prov == "groq":
                    byok_key = budget.groq_api_key

        effective_provider = effective_provider or get_settings().LLM_PROVIDER
        effective_model = effective_model or "llama-3.3-70b-versatile"

        return effective_provider, effective_model, byok_key

    async def _record_usage(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        provider: str,
        model: str,
        response: Any,
        is_byok: bool,
    ) -> None:
        """Records LLM usage metrics."""
        try:
            usage_metadata = response.response_metadata.get("token_usage", {})
            input_tokens = usage_metadata.get("prompt_tokens", 0)
            output_tokens = usage_metadata.get("completion_tokens", 0)

            await LLMBudgetManager.record_usage(
                tenant_id=tenant_id,
                db=db,
                provider=provider,
                model=model,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                is_byok=is_byok,
                request_type="zombie_analysis",
            )
            logger.info(
                "zombie_analysis_usage_tracked",
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        except Exception as e:
            logger.warning(
                "zombie_usage_tracking_failed", tenant_id=str(tenant_id), error=str(e)
            )
