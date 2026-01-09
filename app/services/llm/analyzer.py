from typing import List, Dict, Any, Optional
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate
import structlog
import re
from uuid import UUID
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.llm.usage_tracker import UsageTracker
import json
from app.core.config import get_settings
from app.services.notifications import SlackService
logger = structlog.get_logger()

# The "System Prompt" - defines the AI's personality and task
FINOPS_SYSTEM_PROMPT = """You are a FinOps cost analysis expert specializing in cloud infrastructure optimization.

TASK:
Analyze the provided cloud cost data and identify cost optimization opportunities.

INPUT DATA FORMAT:
- Resource usage metrics (CPU, memory, network)
- Cost trends over the past 30 days
- Resource metadata (type, region, tags)

ANALYSIS CRITERIA:
1. Anomalies: Cost changes greater than 30% week-over-week or unexpected spending patterns
2. Zombie Resources: Resources with less than 5% utilization for 7 or more consecutive days
3. Optimizations: Right-sizing opportunities with greater than 20% potential savings, reserved instance candidates, and idle resources

OUTPUT FORMAT (STRICT JSON ONLY):
{{
  "anomalies": [
    {{
      "resource": "resource-id or name",
      "issue": "description of anomaly",
      "cost_impact": "$XX/month",
      "severity": "high|medium|low"
    }}
  ],
  "zombie_resources": [
    {{
      "resource": "resource-id",
      "type": "EC2|RDS|ELB|Other",
      "current_cost": "$XX/month",
      "utilization": "X%",
      "recommendation": "terminate|resize|investigate"
    }}
  ],
  "recommendations": [
    {{
      "action": "specific action to take",
      "resource": "affected resource(s)",
      "estimated_savings": "$XX/month",
      "priority": "high|medium|low",
      "effort": "low|medium|high",
      "confidence": "high|medium|low"
    }}
  ],
  "summary": {{
    "total_estimated_savings": "$XXX/month",
    "top_priority_action": "most impactful recommendation",
    "risk_level": "low|medium|high"
  }}
}}

RULES:
- Return valid JSON only (no markdown, no explanations)
- Use exact enum values as specified
- Base all conclusions strictly on the provided data
- If no issues are found, return empty arrays and set total_estimated_savings to "$0/month"
- Prioritize recommendations by ROI (estimated savings versus implementation effort)
"""

class FinOpsAnalyzer:
    """
    The 'Brain' of CloudSentinel.
    
    This class wraps a LangChain ChatModel and orchestrates the analysis of cost data.
    It uses a specialized System Prompt to enforce strict JSON output for programmatic use.
    """
    def __init__(self, llm: BaseChatModel):
        self.llm = llm
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", FINOPS_SYSTEM_PROMPT),
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
    cost_data: List[Dict[str, Any]],
    tenant_id: Optional[UUID] = None,
    db: Optional[AsyncSession] = None,
    provider: str = "groq",
    model: str = "llama-3.3-70b-versatile",) -> str:
        """
        Takes raw cost data and returns AI-generated insights.

        The process:
        1. Formats the raw list of dictionaries into a string.
        2. Injects it into the prompt template.
        3. Invokes the LLM to process the data against the System Prompt.
        4. Strips any markdown formatting from the response to ensure valid JSON.

        Args:
            cost_data: List of daily cost records from the adapter.
        
        Returns:
            str: A raw JSON string containing the analysis.
        """
        logger.info("starting_analysis", data_points=len(cost_data))
        
        # Format cost data as string for the prompt
        formatted_data = str(cost_data)
        
        # Build the chain: Prompt -> LLM
        chain = self.prompt | self.llm
        
        # Invoke the chain
        response = await chain.ainvoke({"cost_data": formatted_data})

        # Track LLM usage if tenant context provided
        if tenant_id and db:
            try:
                # Extract token usage from response metadata
                usage_metadata = response.response_metadata.get("token_usage", {})
                input_tokens = usage_metadata.get("prompt_tokens", 0)
                output_tokens = usage_metadata.get("completion_tokens", 0)
                
                # Record usage
                tracker = UsageTracker(db)
                await tracker.record(
                    tenant_id=tenant_id,
                    provider=provider,
                    model=model,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    request_type="cost_analysis",
                )
            except Exception as e:
                # Don't fail the analysis if tracking fails
                logger.warning("llm_usage_tracking_failed", error=str(e))
        
        logger.info("analysis_complete")
        
        # After analysis, check for anomalies and alert
        try:
            result = json.loads(self._strip_markdown(response.content))
            if result.get("anomalies") and len(result["anomalies"]) > 0:
                settings = get_settings()
                if settings.SLACK_BOT_TOKEN and settings.SLACK_CHANNEL_ID:
                    slack = SlackService(settings.SLACK_BOT_TOKEN, settings.SLACK_CHANNEL_ID)
                    
                    top_anomaly = result["anomalies"][0]
                    await slack.send_alert(
                        title=f"Cost Anomaly Detected: {top_anomaly['resource']}",
                        message=f"*Issue:* {top_anomaly['issue']}\n*Impact:* {top_anomaly['cost_impact']}\n*Severity:* {top_anomaly['severity']}",
                        severity="critical" if top_anomaly['severity'] == "high" else "warning"
                    )
        except json.JSONDecodeError:
            pass  # If response isn't valid JSON, skip alerting
            
        return self._strip_markdown(response.content)