from abc import ABC, abstractmethod
from typing import List, Any
from uuid import UUID
from datetime import datetime, timezone
from typing import Optional

from app.models.optimization import (
    StrategyRecommendation,
    OptimizationStrategy,
    CommitmentTerm,
    PaymentOption,
)


class BaseOptimizationStrategy(ABC):
    """
    Abstract Base Class for FinOps Optimization Strategies.
    Implements the Strategy Pattern for different optimization types (RI, SP, Spot, etc.).
    """

    def __init__(self, strategy_config: OptimizationStrategy):
        self.strategy_config = strategy_config
        self.config = strategy_config.config

    @abstractmethod
    async def analyze(
        self, tenant_id: UUID, usage_data: Any
    ) -> List[StrategyRecommendation]:
        """
        Analyze usage data and generate recommendations.

        Args:
            tenant_id: The ID of the tenant to analyze.
            usage_data: The usage data to analyze (format depends on implementation).

        Returns:
            List of StrategyRecommendation objects (not yet persisted).
        """
        pass

    @abstractmethod
    def calculate_roi(self, on_demand_cost: float, commitment_cost: float) -> float:
        """
        Calculate Return on Investment (percentage).

        Args:
            on_demand_cost: Projected cost without optimization.
            commitment_cost: Projected cost with optimization (including upfront).

        Returns:
            ROI percentage (e.g., 25.5 for 25.5%).
        """
        pass

    def _create_recommendation(
        self,
        tenant_id: UUID,
        resource_type: str,
        region: str,
        term: CommitmentTerm,
        payment_option: PaymentOption,
        monthly_savings: float,
        roi: float,
        upfront_cost: float = 0.0,
        monthly_cost: float = 0.0,
        monthly_savings_low: Optional[float] = None,
        monthly_savings_high: Optional[float] = None,
        break_even_months: Optional[float] = None,
        confidence_score: Optional[float] = None,
    ) -> StrategyRecommendation:
        """Helper to instantiate a StrategyRecommendation model."""
        return StrategyRecommendation(
            tenant_id=tenant_id,
            strategy_id=self.strategy_config.id,
            resource_type=resource_type,
            region=region,
            term=term,
            payment_option=payment_option,
            estimated_monthly_savings=monthly_savings,
            estimated_monthly_savings_low=monthly_savings_low,
            estimated_monthly_savings_high=monthly_savings_high,
            roi_percentage=roi,
            break_even_months=break_even_months,
            confidence_score=confidence_score,
            upfront_cost=upfront_cost,
            monthly_recurring_cost=monthly_cost,
            status="open",
            created_at=datetime.now(timezone.utc),
        )
