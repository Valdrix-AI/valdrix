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

from app.core.config import get_settings
from app.services.llm.usage_tracker import UsageTracker
from app.services.llm.guardrails import LLMGuardrails, ZombieAnalysisResult

logger = structlog.get_logger()

ZOMBIE_ANALYSIS_PROMPT = """You are a Cloud FinOps expert analyzing zombie (unused/underutilized) AWS resources.

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
      "provider": "aws|azure|gcp",
      "explanation": "Why this is a zombie - be specific and clear",
      "confidence": "high|medium|low",
      "confidence_score": 0.0-1.0,
      "confidence_reason": "Why you rated this confidence level",
      "recommended_action": "What to do with this resource",
      "monthly_cost": "$X.XX",
      "risk_if_deleted": "low|medium|high",
      "risk_explanation": "Brief explanation of deletion risk"
    }}
  ],
  "general_recommendations": [
    "List of overall recommendations for preventing future zombie resources"
  ]
}}

IMPORTANT RULES:
- Base conclusions ONLY on provided data
- Preserve the Cloud Provider ("aws", "azure", or "gcp") for each resource
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
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", ZOMBIE_ANALYSIS_PROMPT),
            ("user", "Analyze these detected zombie resources:\n{zombie_data}")
        ])

    def _strip_markdown(self, text: str) -> str:
        """Remove markdown code block wrappers from LLM responses."""
        pattern = r'^```(?:json)?\s*\n?(.*?)\n?```$'
        match = re.match(pattern, text.strip(), re.DOTALL)
        if match:
            return match.group(1).strip()
        return text.strip()

    def _flatten_zombies(self, detection_results: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Flatten nested zombie categories into a single list for LLM analysis."""
        flattened = []

        # Skip metadata keys
        skip_keys = {"region", "scanned_at", "total_monthly_waste"}

        for category, items in detection_results.items():
            if category in skip_keys:
                continue
            if isinstance(items, list):
                for item in items:
                    if isinstance(item, dict):
                        item["category"] = category
                        flattened.append(item)

        return flattened

    async def analyze(
        self,
        detection_results: Dict[str, Any],
        tenant_id: Optional[UUID] = None,
        db: Optional[AsyncSession] = None,
        provider: Optional[str] = None,
        model: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze detected zombie resources with LLM.

        Args:
            detection_results: Raw output from ZombieDetector.scan_all()
            tenant_id: For usage tracking and BYOK
            db: Database session for budget/usage queries
            provider: Override LLM provider
            model: Override LLM model

        Returns:
            Dict with AI-generated analysis and explanations
        """
        # Flatten zombies for analysis
        zombies = self._flatten_zombies(detection_results)

        if not zombies:
            return {
                "summary": "No zombie resources detected.",
                "total_monthly_savings": "$0.00",
                "resources": [],
                "general_recommendations": []
            }

        logger.info("zombie_analysis_starting", zombie_count=len(zombies))

        # Determine provider and model
        effective_provider = provider
        effective_model = model

        if tenant_id and db and (not effective_provider or not effective_model):
            from app.models.llm import LLMBudget
            result = await db.execute(select(LLMBudget).where(LLMBudget.tenant_id == tenant_id))
            budget = result.scalar_one_or_none()
            if budget:
                effective_provider = effective_provider or budget.preferred_provider
                effective_model = effective_model or budget.preferred_model

        # Fallbacks
        effective_provider = effective_provider or get_settings().LLM_PROVIDER
        effective_model = effective_model or "llama-3.3-70b-versatile"

        # Check for BYOK (Bring Your Own Key)
        byok_key = None
        if tenant_id and db:
            from app.models.llm import LLMBudget
            result = await db.execute(select(LLMBudget).where(LLMBudget.tenant_id == tenant_id))
            budget = result.scalar_one_or_none()
            if budget:
                if effective_provider == "openai":
                    byok_key = budget.openai_api_key
                elif effective_provider in ["claude", "anthropic"]:
                    byok_key = budget.claude_api_key
                elif effective_provider == "google":
                    byok_key = budget.google_api_key
                elif effective_provider == "groq":
                    byok_key = budget.groq_api_key

        # Build LLM with potential BYOK
        current_llm = self.llm
        if effective_provider != get_settings().LLM_PROVIDER or byok_key:
            from app.services.llm.factory import LLMFactory
            current_llm = LLMFactory.create(effective_provider, api_key=byok_key)

        # Sanitize zombie data to prevent prompt injection via resource tags/names
        sanitized_zombies = LLMGuardrails.sanitize_input(zombies)
        
        # Format zombie data for prompt
        formatted_data = json.dumps(sanitized_zombies, default=str, indent=2)

        # Invoke LLM
        chain = self.prompt | current_llm
        response = await chain.ainvoke({"zombie_data": formatted_data})

        # Track LLM usage
        if tenant_id and db:
            try:
                usage_metadata = response.response_metadata.get("token_usage", {})
                input_tokens = usage_metadata.get("prompt_tokens", 0)
                output_tokens = usage_metadata.get("completion_tokens", 0)

                tracker = UsageTracker(db)
                await tracker.record(
                    tenant_id=tenant_id,
                    provider=effective_provider,
                    model=effective_model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    is_byok=byok_key is not None,
                    request_type="zombie_analysis",
                )
                logger.info("zombie_analysis_usage_tracked",
                           input_tokens=input_tokens,
                           output_tokens=output_tokens)
            except Exception as e:
                logger.warning("zombie_usage_tracking_failed", 
                               tenant_id=str(tenant_id),
                               error=str(e),
                               exc_info=True)

        # Parse and validate response
        try:
            validated_result = LLMGuardrails.validate_output(response.content, ZombieAnalysisResult)
            analysis = validated_result.model_dump()
            logger.info("zombie_analysis_complete", resource_count=len(analysis.get("resources", [])))
            return analysis
        except json.JSONDecodeError as e:
            logger.error("zombie_analysis_json_parse_failed", error=str(e))
            return {
                "summary": "Analysis completed but response parsing failed.",
                "total_monthly_savings": f"${detection_results.get('total_monthly_waste', 0):.2f}",
                "resources": [],
                "general_recommendations": ["Review detected resources manually."],
                "raw_response": response.content,
                "parse_error": str(e)
            }
