from statistics import fmean
from typing import Any, Dict, List, Sequence
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
            "baseline_hourly_spend": float, # The steady-state baseline
            "confidence_score": float,      # 0.0 to 1.0
            "coverage_ratio": float,        # 0.0 to 1.0
            "region": str,
            "instance_types": List[str],
        }
        """
        recommendations: List[StrategyRecommendation] = []

        # 1. Compute Savings Plan logic anchored on observed baseline spend.
        baseline_spend = float(
            usage_data.get("baseline_hourly_spend")
            or usage_data.get("min_hourly_spend")
            or 0.0
        )
        min_hourly_threshold = float(self.config.get("min_hourly_threshold", 0.05))
        if baseline_spend <= min_hourly_threshold:
            return recommendations

        savings_mid = float(self.config.get("savings_rate", 0.25))
        savings_low = float(self.config.get("savings_rate_low", max(savings_mid - 0.05, 0.0)))
        savings_high = float(self.config.get("savings_rate_high", min(savings_mid + 0.05, 0.95)))

        hours_per_month = float(self.config.get("hours_per_month", 730.0))
        on_demand_monthly = baseline_spend * hours_per_month

        monthly_savings_low = on_demand_monthly * savings_low
        monthly_savings = on_demand_monthly * savings_mid
        monthly_savings_high = on_demand_monthly * savings_high
        monthly_commitment_cost = on_demand_monthly - monthly_savings

        upfront_cost = float(self.config.get("upfront_cost", 0.0))
        break_even_months = 0.0
        if upfront_cost > 0 and monthly_savings > 0:
            break_even_months = upfront_cost / monthly_savings

        confidence = self._bounded_confidence(
            usage_confidence=float(usage_data.get("confidence_score", 0.7)),
            coverage_ratio=float(usage_data.get("coverage_ratio", 0.0)),
        )

        roi = self.calculate_roi(on_demand_monthly, monthly_commitment_cost + upfront_cost)

        rec = self._create_recommendation(
            tenant_id=tenant_id,
            resource_type="Compute Savings Plan",
            region="Global",  # Compute SPs are global.
            term=CommitmentTerm.ONE_YEAR,
            payment_option=PaymentOption.NO_UPFRONT,
            monthly_savings=monthly_savings,
            monthly_savings_low=monthly_savings_low,
            monthly_savings_high=monthly_savings_high,
            roi=roi,
            upfront_cost=upfront_cost,
            monthly_cost=monthly_commitment_cost,
            break_even_months=break_even_months,
            confidence_score=confidence,
        )
        recommendations.append(rec)

        return recommendations

    def backtest_hourly_series(
        self,
        hourly_costs: Sequence[float],
        tolerance: float = 0.30,
    ) -> Dict[str, Any]:
        """
        Backtest baseline-based projection against the most recent 24 hours.
        Returns MAPE and tolerance pass/fail signal.
        """
        if len(hourly_costs) < 48:
            return {
                "mape": 1.0,
                "tolerance": tolerance,
                "within_tolerance": False,
                "sample_size": 0,
                "reason": "insufficient_history",
            }

        train = [max(float(x), 0.0) for x in hourly_costs[:-24]]
        actual = [max(float(x), 0.0) for x in hourly_costs[-24:]]

        non_zero_train = [v for v in train if v > 0]
        if not non_zero_train:
            return {
                "mape": 0.0,
                "tolerance": tolerance,
                "within_tolerance": True,
                "sample_size": len(actual),
                "reason": "all_zero_history",
            }

        predicted_baseline = self._percentile(non_zero_train, 0.25)
        ape_values = []
        for observed in actual:
            denominator = max(observed, 1e-9)
            ape_values.append(abs(observed - predicted_baseline) / denominator)

        mape = float(fmean(ape_values)) if ape_values else 0.0
        return {
            "mape": mape,
            "tolerance": tolerance,
            "within_tolerance": mape <= tolerance,
            "sample_size": len(actual),
            "predicted_hourly_baseline": predicted_baseline,
        }

    def _bounded_confidence(self, usage_confidence: float, coverage_ratio: float) -> float:
        """Blend model confidence with ingestion coverage and clamp to [0, 1]."""
        coverage_component = max(0.0, min(coverage_ratio, 1.0))
        usage_component = max(0.0, min(usage_confidence, 1.0))
        blended = (usage_component * 0.8) + (coverage_component * 0.2)
        return round(max(0.0, min(blended, 1.0)), 3)

    def _percentile(self, values: Sequence[float], percentile: float) -> float:
        """Linear interpolation percentile for deterministic baseline estimation."""
        if not values:
            return 0.0
        ordered = sorted(float(v) for v in values)
        if len(ordered) == 1:
            return ordered[0]
        pct = max(0.0, min(percentile, 1.0))
        rank = pct * (len(ordered) - 1)
        lower_idx = int(rank)
        upper_idx = min(lower_idx + 1, len(ordered) - 1)
        frac = rank - lower_idx
        return ordered[lower_idx] + ((ordered[upper_idx] - ordered[lower_idx]) * frac)

    def calculate_roi(self, on_demand_cost: float, commitment_cost: float) -> float:
        """
        ROI represented as % cost reduction.
        """
        if on_demand_cost <= 0:
            return 0.0

        savings = on_demand_cost - commitment_cost
        return (savings / on_demand_cost) * 100
