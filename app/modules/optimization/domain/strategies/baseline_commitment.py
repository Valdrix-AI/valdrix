from __future__ import annotations

from statistics import fmean
from typing import Any, Dict, List, Sequence
from uuid import UUID

from app.models.optimization import (
    CommitmentTerm,
    PaymentOption,
    StrategyRecommendation,
)
from app.modules.optimization.domain.strategies.base import BaseOptimizationStrategy


class BaselineCommitmentStrategy(BaseOptimizationStrategy):
    """
    Provider-aware commitment strategy driven by baseline spend.

    This strategy intentionally does NOT attempt SKU-level modeling (that requires provider
    price catalogs + instance family metadata). Instead, it produces finance-grade *budget*
    commitment guidance using:
    - stable baseline spend (p25) from the normalized ledger
    - explicit discount-rate assumptions stored in strategy config
    - deterministic confidence scoring based on ingestion coverage + volatility + backtest MAPE

    Config format:
    - min_hourly_threshold: float
    - hours_per_month: float (default 730)
    - commitment_label: str (resource_type label shown in UI)
    - region_scope: "global" | "top_region"
    - offers: optional list[dict] with:
        - term: "1_year" | "3_year"
        - payment_option: "no_upfront" | "partial_upfront" | "all_upfront"
        - savings_rate, savings_rate_low, savings_rate_high
        - upfront_cost (optional)
    - backtest_tolerance: float (default 0.30)
    """

    async def analyze(
        self, tenant_id: UUID, usage_data: Dict[str, Any]
    ) -> List[StrategyRecommendation]:
        recommendations: List[StrategyRecommendation] = []

        baseline_spend = float(usage_data.get("baseline_hourly_spend") or 0.0)
        min_hourly_threshold = float(self.config.get("min_hourly_threshold", 0.05))
        if baseline_spend <= min_hourly_threshold:
            return recommendations

        hours_per_month = float(self.config.get("hours_per_month", 730.0))
        on_demand_monthly = baseline_spend * hours_per_month

        label = str(self.config.get("commitment_label") or "Compute Commitment")
        region_scope = str(self.config.get("region_scope") or "global").strip().lower()
        if region_scope == "top_region":
            region = str(usage_data.get("top_region") or "Unknown")
        else:
            region = "Global"

        usage_confidence = float(usage_data.get("confidence_score", 0.7))
        coverage_ratio = float(usage_data.get("coverage_ratio", 0.0))
        confidence = self._bounded_confidence(
            usage_confidence=usage_confidence, coverage_ratio=coverage_ratio
        )

        # Backtest signal (optional): reduce confidence when baseline projection is unstable.
        hourly_series = usage_data.get("hourly_cost_series")
        backtest = None
        if isinstance(hourly_series, list) and hourly_series:
            tolerance = float(self.config.get("backtest_tolerance", 0.30))
            backtest = self.backtest_hourly_series(hourly_series, tolerance=tolerance)
            if not backtest.get("within_tolerance", True):
                confidence = round(max(0.0, confidence * 0.7), 3)

        offers = self._offers_from_config()
        if not offers:
            offers = [
                {
                    "term": CommitmentTerm.ONE_YEAR,
                    "payment_option": PaymentOption.NO_UPFRONT,
                    "savings_rate": float(self.config.get("savings_rate", 0.20)),
                    "savings_rate_low": float(
                        self.config.get("savings_rate_low", 0.15)
                    ),
                    "savings_rate_high": float(
                        self.config.get("savings_rate_high", 0.25)
                    ),
                    "upfront_cost": float(self.config.get("upfront_cost", 0.0)),
                }
            ]

        for offer in offers:
            savings_mid = float(offer["savings_rate"])
            savings_low = float(offer["savings_rate_low"])
            savings_high = float(offer["savings_rate_high"])
            upfront_cost = float(offer.get("upfront_cost", 0.0))

            monthly_savings_low = on_demand_monthly * savings_low
            monthly_savings = on_demand_monthly * savings_mid
            monthly_savings_high = on_demand_monthly * savings_high
            monthly_commitment_cost = on_demand_monthly - monthly_savings

            break_even_months = None
            if upfront_cost > 0 and monthly_savings > 0:
                break_even_months = upfront_cost / monthly_savings

            roi = self.calculate_roi(
                on_demand_monthly, monthly_commitment_cost + upfront_cost
            )

            rec = self._create_recommendation(
                tenant_id=tenant_id,
                resource_type=label,
                region=region,
                term=offer["term"],
                payment_option=offer["payment_option"],
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

        # Attach backtest evidence to the first rec's confidence when available (without schema changes).
        # The detailed backtest report is exposed via the /backtest endpoint.
        _ = backtest

        return recommendations

    def _offers_from_config(self) -> list[dict[str, Any]]:
        raw = self.config.get("offers")
        if not isinstance(raw, list):
            return []

        offers: list[dict[str, Any]] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            term_raw = str(item.get("term") or "").strip().lower()
            if term_raw in {"1_year", "one_year", "1y"}:
                term = CommitmentTerm.ONE_YEAR
            elif term_raw in {"3_year", "three_year", "3y"}:
                term = CommitmentTerm.THREE_YEAR
            else:
                continue

            payment_raw = str(item.get("payment_option") or "").strip().lower()
            if payment_raw in {"no_upfront", "none"}:
                payment = PaymentOption.NO_UPFRONT
            elif payment_raw in {"partial_upfront", "partial"}:
                payment = PaymentOption.PARTIAL_UPFRONT
            elif payment_raw in {"all_upfront", "all"}:
                payment = PaymentOption.ALL_UPFRONT
            else:
                continue

            try:
                savings_mid = float(item.get("savings_rate"))
                savings_low = float(item.get("savings_rate_low", savings_mid))
                savings_high = float(item.get("savings_rate_high", savings_mid))
            except Exception:
                continue

            offers.append(
                {
                    "term": term,
                    "payment_option": payment,
                    "savings_rate": savings_mid,
                    "savings_rate_low": savings_low,
                    "savings_rate_high": savings_high,
                    "upfront_cost": float(item.get("upfront_cost", 0.0) or 0.0),
                }
            )
        return offers

    def backtest_hourly_series(
        self,
        hourly_costs: Sequence[float],
        tolerance: float = 0.30,
    ) -> Dict[str, Any]:
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

    def _bounded_confidence(
        self, usage_confidence: float, coverage_ratio: float
    ) -> float:
        coverage_component = max(0.0, min(coverage_ratio, 1.0))
        usage_component = max(0.0, min(usage_confidence, 1.0))
        blended = (usage_component * 0.8) + (coverage_component * 0.2)
        return round(max(0.0, min(blended, 1.0)), 3)

    def _percentile(self, values: Sequence[float], percentile: float) -> float:
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
        if on_demand_cost <= 0:
            return 0.0
        savings = on_demand_cost - commitment_cost
        return (savings / on_demand_cost) * 100.0
