"""
Carbon Footprint Calculator (2026 Edition)

Estimates CO₂ emissions from AWS cloud usage based on:
1. AWS region (electricity grid carbon intensity)
2. Service type (compute, storage, networking)
3. Cost as a proxy for resource consumption
4. Embodied emissions (server manufacturing impact)

Methodology Sources:
- AWS Customer Carbon Footprint Tool (CCFT) v3.0.0 (Oct 2025)
- Cloud Carbon Footprint (CCF) open source project
- GHG Protocol for Scope 1, 2, and 3 emissions
- EPA emissions factors
"""

from typing import List, Dict, Any
from decimal import Decimal
import structlog

logger = structlog.get_logger()


# Carbon intensity by AWS region (gCO₂eq per kWh)
# Source: Electricity Maps, EPA eGRID, and AWS sustainability reports (2025)
REGION_CARBON_INTENSITY = {
    # Low carbon (renewables/nuclear)
    "us-west-2": 21,      # Oregon - hydro
    "eu-north-1": 28,     # Stockholm - hydro/nuclear
    "ca-central-1": 35,   # Montreal - hydro
    "eu-west-1": 316,     # Ireland - wind/gas mix

    # Medium carbon
    "us-west-1": 218,     # N. California
    "eu-west-2": 225,     # London
    "eu-central-1": 338,  # Frankfurt

    # High carbon (coal/gas heavy)
    "us-east-1": 379,     # N. Virginia
    "us-east-2": 440,     # Ohio
    "ap-southeast-1": 408,# Singapore
    "ap-south-1": 708,    # Mumbai
    "ap-northeast-1": 506,# Tokyo

    # Default for unknown regions
    "default": 400,
}

# Energy consumption per dollar spent (kWh/$)
# These are rough estimates based on CCF methodology
# Different services have different energy profiles
SERVICE_ENERGY_FACTORS = {
    "Amazon Elastic Compute Cloud - Compute": 0.05,  # EC2 is energy-intensive
    "EC2 - Other": 0.04,                             # EC2 related services
    "Amazon Simple Storage Service": 0.01,           # S3 is efficient
    "Amazon Relational Database Service": 0.04,      # RDS moderate
    "Amazon CloudFront": 0.02,                       # CDN is efficient
    "AWS Lambda": 0.03,                              # Serverless moderate
    "Amazon DynamoDB": 0.02,                         # NoSQL efficient
    "Amazon Virtual Private Cloud": 0.02,            # VPC networking
    "default": 0.03,                                 # Default estimate
}

# Power Usage Effectiveness (PUE) - datacenter overhead
# AWS reports PUE of ~1.2 for modern datacenters
AWS_PUE = 1.2

# Embodied emissions factor (kgCO2e per kWh of compute)
# Source: CCF methodology - accounts for server manufacturing
# Typical value: ~0.025 kgCO2e per kWh (amortized over 4-year server lifecycle)
EMBODIED_EMISSIONS_FACTOR = 0.025


class CarbonCalculator:
    """
    Calculates carbon footprint from cloud cost data.

    2026 Methodology (aligned with CCF and AWS CCFT):
    1. Estimate energy (kWh) from cost using service-specific factors
    2. Apply PUE multiplier for datacenter overhead
    3. Multiply by region carbon intensity (gCO₂/kWh) → Scope 2
    4. Add embodied emissions (Scope 3)
    5. Convert to kg CO₂
    6. Calculate carbon efficiency score (gCO2e per $1)
    """

    def calculate_from_costs(
        self,
        cost_data: List[Dict[str, Any]],
        region: str = "us-east-1",
    ) -> Dict[str, Any]:
        """
        Cost-proxy calculation for manual uploads and quick views.
        """
        total_cost_usd = Decimal("0")
        total_energy_kwh = Decimal("0")

        # Sum up costs and estimate energy
        for record in cost_data:
            try:
                # Case 1: Grouped data (e.g. by Service)
                groups = record.get("Groups", [])
                if groups:
                    for group in groups:
                        service = group.get("Keys", ["default"])[0]
                        cost_amount = Decimal(
                            group.get("Metrics", {})
                            .get("UnblendedCost", {})
                            .get("Amount", "0")
                            )
                        if cost_amount > 0:
                            total_cost_usd += cost_amount
                            # Get factor for this specific service or use default
                            factor_key = service if service in SERVICE_ENERGY_FACTORS else "default"
                            energy_factor = Decimal(str(SERVICE_ENERGY_FACTORS[factor_key]))
                            total_energy_kwh += cost_amount * energy_factor

                # Case 2: Flat data (un-grouped)
                else:
                    cost_amount = Decimal(
                        record.get("Total", {})
                        .get("UnblendedCost", {})
                        .get("Amount", "0")
                        )
                    if cost_amount > 0:
                        total_cost_usd += cost_amount
                        energy_factor = Decimal(str(SERVICE_ENERGY_FACTORS["default"]))
                        total_energy_kwh += cost_amount * energy_factor

            except (KeyError, TypeError, ValueError) as e:
                logger.warning("carbon_calc_skip_record", error=str(e))
                continue

        return self._finalize_calculation(total_cost_usd, total_energy_kwh, region)

    def calculate_from_records(
        self,
        records: List[Any], # List[CostRecord]
        region: str = "us-east-1",
    ) -> Dict[str, Any]:
        """
        High-precision SKU-level calculation. 
        Uses amount_raw if it represents actual usage quantities.
        """
        total_cost_usd = Decimal("0")
        total_energy_kwh = Decimal("0")

        for record in records:
            total_cost_usd += record.cost_usd
            
            # If we have raw usage (vCPU-Hours, GB-Months), we can be much more accurate.
            # In a full implementation, we'd map usage_type to precise kWh consumption.
            # For now, we use amount_raw as a refined proxy or direct kWh if the CUR adapter 
            # pre-calculates it.
            
            if record.amount_raw and record.amount_raw > 0:
                # Refined conversion logic: 
                # EC2 Compute: amount_raw (Hours) * Watts per vCPU / 1000
                if "EC2" in record.service and "vCPU-Hours" in str(record.usage_type):
                    # Average 2026 server: 10W per vCPU active
                    total_energy_kwh += record.amount_raw * Decimal("0.010") 
                else:
                    # Fallback to refined cost-proxy if usage_type isn't mapped
                    factor_key = record.service if record.service in SERVICE_ENERGY_FACTORS else "default"
                    energy_factor = Decimal(str(SERVICE_ENERGY_FACTORS[factor_key]))
                    total_energy_kwh += record.cost_usd * energy_factor
            else:
                # Absolute fallback
                factor_key = record.service if record.service in SERVICE_ENERGY_FACTORS else "default"
                energy_factor = Decimal(str(SERVICE_ENERGY_FACTORS[factor_key]))
                total_energy_kwh += record.cost_usd * energy_factor

        return self._finalize_calculation(total_cost_usd, total_energy_kwh, region)

    def _finalize_calculation(
        self, 
        total_cost_usd: Decimal, 
        total_energy_kwh: Decimal, 
        region: str
    ) -> Dict[str, Any]:
        """Shared logic for emissions calculation and result formatting."""
        # Apply PUE (datacenter overhead)
        total_energy_with_pue = total_energy_kwh * Decimal(str(AWS_PUE))

        # Get carbon intensity for region
        carbon_intensity = REGION_CARBON_INTENSITY.get(
            region, REGION_CARBON_INTENSITY["default"]
        )

        # Calculate Scope 2 CO₂ (operational emissions) in grams
        scope2_co2_grams = total_energy_with_pue * Decimal(str(carbon_intensity))
        scope2_co2_kg = scope2_co2_grams / Decimal("1000")

        # Calculate Scope 3 CO₂ (embodied emissions from server manufacturing)
        scope3_co2_kg = total_energy_with_pue * Decimal(str(EMBODIED_EMISSIONS_FACTOR))

        # Total CO₂ = Scope 2 + Scope 3
        total_co2_kg = scope2_co2_kg + scope3_co2_kg

        # Calculate Carbon Efficiency Score (gCO2e per $1 of usage)
        carbon_efficiency_score = 0.0
        if total_cost_usd > 0:
            carbon_efficiency_score = float(total_co2_kg * 1000 / total_cost_usd)
        elif total_co2_kg > 0:
            # If cost is 0 but co2 is not (rare but possible in some edge cases)
            carbon_efficiency_score = 9999.9  # High inefficiency sentinel

        # Calculate equivalencies for user-friendly display
        equivalencies = self._calculate_equivalencies(float(total_co2_kg))

        result = {
            # Core metrics
            "total_co2_kg": round(float(total_co2_kg), 3),
            "scope2_co2_kg": round(float(scope2_co2_kg), 3),
            "scope3_co2_kg": round(float(scope3_co2_kg), 3),
            "total_cost_usd": round(float(total_cost_usd), 2),
            "estimated_energy_kwh": round(float(total_energy_with_pue), 3),

            # FinOps Carbon KPI (lower is better)
            "carbon_efficiency_score": round(carbon_efficiency_score, 2),
            "carbon_efficiency_unit": "gCO2e per $1 spent",

            # Region info
            "region": region,
            "carbon_intensity_gco2_kwh": carbon_intensity,

            # Human-readable equivalencies
            "equivalencies": equivalencies,

            # Methodology metadata
            "methodology": "Valdrix 2026 (CCF + AWS CCFT v3.0.0)",
            "includes_embodied_emissions": True,

            # Projections
            "forecast_30d": self.forecast_emissions(float(total_co2_kg) / 30 if total_co2_kg > 0 else 0),

            # GreenOps recommendations
            "green_region_recommendations": self.get_green_region_recommendations(region)
        }

        logger.info(
            "carbon_calculated",
            co2_kg=result["total_co2_kg"],
            cost_usd=result["total_cost_usd"],
            efficiency_score=result["carbon_efficiency_score"],
            region=region,
        )

        return result

    def _calculate_equivalencies(self, co2_kg: float) -> Dict[str, Any]:
        """
        Convert CO₂ to relatable equivalencies.

        Sources: EPA Greenhouse Gas Equivalencies Calculator
        """
        return {
            # Average car emits 404g CO₂ per mile
            "miles_driven": round(co2_kg * 1000 / 404, 1),

            # One tree absorbs ~22kg CO₂ per year
            "trees_needed_for_year": round(co2_kg / 22, 1),

            # Average smartphone charge uses ~0.0085 kWh = ~3.4g CO₂
            "smartphone_charges": round(co2_kg * 1000 / 3.4, 0),

            # Average home uses ~900kWh/month = ~360kg CO₂/month
            "percent_of_home_month": round((co2_kg / 360) * 100, 2),
        }

    def get_green_region_recommendations(self, current_region: str) -> List[Dict[str, Any]]:
        """
        Recommend lower-carbon regions for workload placement.

        Valdrix Innovation: Help users reduce emissions
        by migrating to greener AWS regions.
        """
        current_intensity = REGION_CARBON_INTENSITY.get(
            current_region, REGION_CARBON_INTENSITY["default"]
        )

        recommendations = []
        for region, intensity in sorted(REGION_CARBON_INTENSITY.items(), key=lambda x: x[1]):
            if region == "default":
                continue
            if intensity < current_intensity and current_intensity > 0:
                savings_percent = round((1 - intensity / current_intensity) * 100, 1)
                recommendations.append({
                    "region": region,
                    "carbon_intensity": intensity,
                    "savings_percent": savings_percent,
                })

        return recommendations[:5]  # Top 5 greenest alternatives

    def forecast_emissions(
        self,
        current_daily_co2_kg: float,
        days: int = 30,
        region_trend_factor: float = 0.99  # Assuming 1% monthly grid improvement (optimistic) or flat
    ) -> Dict[str, Any]:
        """
        Predict future emissions based on current workload and grid trends.

        Args:
            current_daily_co2_kg: Current daily emission rate.
            days: Number of days to forecast.
            region_trend_factor: Monthly grid efficiency improvement (default 0.99 = 1% better).

        Returns:
            Dict with forecasted totals and trend description.
        """
        # Simple projection
        baseline_projection = current_daily_co2_kg * days

        # Adjusted projection (accounting for grid improvements or degradation)
        projected_co2_kg = baseline_projection * region_trend_factor

        return {
            "forecast_days": days,
            "baseline_co2_kg": round(baseline_projection, 2),
            "projected_co2_kg": round(projected_co2_kg, 2),
            "trend_factor": region_trend_factor,
            "description": f"Forecast for next {days} days based on current usage.",
        }
