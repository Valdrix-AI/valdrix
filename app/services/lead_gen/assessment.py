
import structlog
from typing import Dict, Any, Optional
from uuid import uuid4
from datetime import date, timedelta
from decimal import Decimal

from app.schemas.costs import CloudUsageSummary, CostRecord
from app.services.llm.analyzer import FinOpsAnalyzer
from app.services.analysis.forecaster import SymbolicForecaster

logger = structlog.get_logger()

class FreeAssessmentService:
    """
    Lead Generation Assessment Engine.
    Provides a one-time 'taste' of Valdrix AI analysis for non-users.
    """
    
    def __init__(self, analyzer: Optional[FinOpsAnalyzer] = None):
        if analyzer:
            self.analyzer = analyzer
        else:
            from app.services.llm.factory import LLMFactory
            self.analyzer = FinOpsAnalyzer(llm=LLMFactory.create())

    async def run_assessment(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Runs a one-time assessment on provided raw data.
        Input validation and sanitization are critical here as this is public.
        """
        assessment_id = str(uuid4())
        logger.info("running_free_assessment", assessment_id=assessment_id)
        
        try:
            # 1. Normalize input into CloudUsageSummary
            summary = self._normalize_input(raw_data)
            
            # 2. Run analysis (using a cheaper/default model for free users)
            analysis = await self.analyzer.analyze(
                usage_summary=summary,
                tenant_id=None, # Public assessment doesn't have a tenant yet
                provider="groq", # Default to cheapest provider
                model="llama-3.1-8b-instant"
            )
            
            # 3. Add marketing hooks
            return {
                "assessment_id": assessment_id,
                "summary": {
                    "total_cost": float(summary.total_cost),
                    "potential_savings": float(analysis.get("potential_savings", 0)), # Simplified
                },
                "insights": analysis.get("insights", [])[:3], # Limit to 3 for free version
                "recommendations": analysis.get("recommendations", [])[:2],
                "next_steps": [
                    "Create a free account to see full breakdown",
                    "Connect your cloud account for automated optimization",
                    "Schedule a demo with our FinOps experts"
                ]
            }
            
        except Exception as e:
            logger.error("free_assessment_failed", assessment_id=assessment_id, error=str(e))
            raise ValueError(f"Assessment failed: {str(e)}")

    def _normalize_input(self, raw_data: Dict[str, Any]) -> CloudUsageSummary:
        """Converts raw user-provided list into internal schema."""
        records = []
        total_cost = Decimal("0")
        
        # Expecting 'data' as list of { "service": "...", "cost": 10.5 }
        input_list = raw_data.get("data", [])
        if not input_list:
            raise ValueError("No data provided for assessment")
            
        today = date.today()
        for i, item in enumerate(input_list):
            amount = Decimal(str(item.get("cost", 0)))
            total_cost += amount
            records.append(CostRecord(
                date=today - timedelta(days=len(input_list) - i),
                amount=amount,
                service=item.get("service", "Unknown"),
                currency="USD"
            ))
            
        return CloudUsageSummary(
            tenant_id="public-assessment",
            provider="manual",
            start_date=records[0].date if records else today,
            end_date=records[-1].date if records else today,
            total_cost=total_cost,
            records=records
        )
