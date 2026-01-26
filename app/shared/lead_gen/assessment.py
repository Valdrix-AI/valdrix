from typing import Dict, Any

class FreeAssessmentService:
    """
    Provides a simplified cloud architecture and cost assessment for lead generation.
    """
    async def run_assessment(self, data: Dict[str, Any]) -> Dict[str, Any]:
        email = data.get("email")
        if not email:
            raise ValueError("Email is required for assessment.")
            
        monthly_spend = data.get("monthly_spend", 0.0)
        
        # Simplified rule-based logic for lead-gen visibility
        estimated_savings = monthly_spend * 0.18 # Default 18% heuristic
        
        return {
            "status": "success",
            "message": "Cost assessment complete.",
            "summary": {
                "estimated_savings_usd": round(estimated_savings, 2),
                "potential_optimization_percent": 18.2,
                "confidence": "High (Rule-based)"
            },
            "next_steps": "Sign up for Valdrix Pro to get resource-level insights and automated remediation."
        }
