from typing import List, Dict, Any
from uuid import UUID

from app.modules.optimization.domain.strategies.base import BaseOptimizationStrategy
from app.models.optimization import StrategyRecommendation, CommitmentTerm, PaymentOption

class ComputeSavingsStrategy(BaseOptimizationStrategy):
    """
    Strategy for analyzing Compute usage and recommending Savings Plans / RIs.
    """
    
    async def analyze(self, tenant_id: UUID, usage_data: Dict[str, Any]) -> List[StrategyRecommendation]:
        """
        Analyzes compute usage for savings opportunities.
        
        Expected usage_data format:
        {
            "average_hourly_spend": float,
            "min_hourly_spend": float, # The steady-state baseline
            "region": str,
            "instance_types": List[str]
        }
        """
        recommendations = []
        
        # 1. Savings Plans Logic
        # We target the steady-state baseline (min_hourly_spend) for commitment
        baseline_spend = usage_data.get("min_hourly_spend", 0.0)
        
        if baseline_spend > 0.05: # Minimum threshold to bother suggesting (e.g. 5 cents/hr)
            # Calculate potential savings for 1-Year No Upfront Compute SP (approx ~25-30% off On-Demand)
            # These constants would ideally come from the Strategy Config or a Pricing Service
            savings_rate = 0.25 # 25% savings
            
            on_demand_monthly = baseline_spend * 730
            # commitment_monthly = commitment_amount * 730 * (1 - savings_rate) # Simplified logic: pay the effective rate
            
            # Let's use the simple model:
            # User spends $1.00/hr consistently.
            # We recommend a $0.75/hr commitment which covers that $1.00/hr usage.
            committed_hourly_spend = baseline_spend * (1 - savings_rate)
            expected_monthly_savings = (baseline_spend - committed_hourly_spend) * 730
            
            roi = self.calculate_roi(on_demand_monthly, committed_hourly_spend * 730)

            rec = self._create_recommendation(
                tenant_id=tenant_id,
                resource_type="Compute Savings Plan",
                region="Global", # Compute SPs are global
                term=CommitmentTerm.ONE_YEAR,
                payment_option=PaymentOption.NO_UPFRONT,
                monthly_savings=expected_monthly_savings,
                roi=roi,
                monthly_cost=committed_hourly_spend * 730
            )
            recommendations.append(rec)

        return recommendations

    def calculate_roi(self, on_demand_cost: float, commitment_cost: float) -> float:
        """
        ROI = (Savings / Investment) * 100 ? 
        Or just Savings Percentage?
        Typically ROI for cost savings is (Savings / Cost) or just the % reduction.
        Let's perform % reduction.
        """
        if on_demand_cost == 0:
            return 0.0
        
        savings = on_demand_cost - commitment_cost
        return (savings / on_demand_cost) * 100
