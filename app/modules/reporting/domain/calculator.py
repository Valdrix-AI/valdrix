"""
Carbon Footprint Calculator (2026 Edition)

Estimates CO2 emissions from cloud and Cloud+ spend based on:
1. Region/grid carbon intensity
2. Service type (compute, storage, networking, SaaS/license)
3. Cost as a proxy for resource consumption
4. Embodied emissions (server manufacturing impact)

Methodology Sources:
- Cloud Carbon Footprint (CCF) methodology patterns
- Provider sustainability references (AWS/Azure/GCP)
- GHG Protocol for Scope 1, 2, and 3 emissions
- EPA emissions factors
"""

from decimal import Decimal
import hashlib
import json
from typing import Any, Dict, List

import structlog

logger = structlog.get_logger()


# Carbon intensity by cloud region (gCO2eq per kWh)
# Source: Electricity Maps, EPA eGRID, and provider sustainability reports.
REGION_CARBON_INTENSITY = {
    # Low carbon (renewables/nuclear)
    "us-west-2": 21,  # Oregon - hydro
    "eu-north-1": 28,  # Stockholm - hydro/nuclear
    "ca-central-1": 35,  # Montreal - hydro
    "eu-west-1": 316,  # Ireland - wind/gas mix
    # Medium carbon
    "us-west-1": 218,  # N. California
    "eu-west-2": 225,  # London
    "eu-central-1": 338,  # Frankfurt
    # High carbon (coal/gas heavy)
    "us-east-1": 379,  # N. Virginia
    "us-east-2": 440,  # Ohio
    "ap-southeast-1": 408,  # Singapore
    "ap-south-1": 708,  # Mumbai
    "ap-northeast-1": 506,  # Tokyo
    # Default for unknown regions
    "default": 400,
}

# Energy consumption per dollar spent (kWh/$), provider-aware.
AWS_SERVICE_ENERGY_FACTORS = {
    "Amazon Elastic Compute Cloud - Compute": 0.05,
    "EC2 - Other": 0.04,
    "Amazon Simple Storage Service": 0.01,
    "Amazon Relational Database Service": 0.04,
    "Amazon CloudFront": 0.02,
    "AWS Lambda": 0.03,
    "Amazon DynamoDB": 0.02,
    "Amazon Virtual Private Cloud": 0.02,
    "default": 0.03,
}

AZURE_SERVICE_ENERGY_FACTORS = {
    "Virtual Machines": 0.05,
    "Azure Kubernetes Service": 0.04,
    "Storage": 0.012,
    "SQL Database": 0.04,
    "Functions": 0.03,
    "default": 0.03,
}

GCP_SERVICE_ENERGY_FACTORS = {
    "Compute Engine": 0.05,
    "Google Kubernetes Engine": 0.04,
    "Cloud Storage": 0.01,
    "Cloud SQL": 0.04,
    "Cloud Functions": 0.03,
    "default": 0.03,
}

SAAS_SERVICE_ENERGY_FACTORS = {
    "default": 0.015,
}

LICENSE_SERVICE_ENERGY_FACTORS = {
    "default": 0.01,
}

GENERIC_SERVICE_ENERGY_FACTORS = {
    "default": 0.03,
}

SERVICE_ENERGY_FACTORS_BY_PROVIDER = {
    "aws": AWS_SERVICE_ENERGY_FACTORS,
    "azure": AZURE_SERVICE_ENERGY_FACTORS,
    "gcp": GCP_SERVICE_ENERGY_FACTORS,
    "saas": SAAS_SERVICE_ENERGY_FACTORS,
    "license": LICENSE_SERVICE_ENERGY_FACTORS,
    "generic": GENERIC_SERVICE_ENERGY_FACTORS,
}

# Power Usage Effectiveness (PUE) - cloud datacenter overhead.
CLOUD_PUE = 1.2

# Embodied emissions factor (kgCO2e per kWh of compute)
EMBODIED_EMISSIONS_FACTOR = 0.025
CARBON_FACTOR_SOURCE = "Electricity Maps + EPA eGRID + provider sustainability reports"
CARBON_FACTOR_VERSION = "2025-12-01"
CARBON_FACTOR_TIMESTAMP = "2025-12-01"
CARBON_METHODOLOGY_VERSION = "valdrix-carbon-v2.0"


def build_carbon_factor_payload() -> Dict[str, Any]:
    """
    Build the canonical carbon factor payload used for:
    - DB-backed factor set staging/activation
    - audit evidence (carbon assurance snapshots)
    - methodology metadata checksums

    Important: this payload must NOT include request-specific context like provider/tenant.
    """
    return {
        "region_carbon_intensity": REGION_CARBON_INTENSITY,
        "service_energy_factors_by_provider": SERVICE_ENERGY_FACTORS_BY_PROVIDER,
        "cloud_pue": float(CLOUD_PUE),
        "embodied_emissions_factor": float(EMBODIED_EMISSIONS_FACTOR),
        "factor_source": CARBON_FACTOR_SOURCE,
        "factor_version": CARBON_FACTOR_VERSION,
        "factor_timestamp": CARBON_FACTOR_TIMESTAMP,
        "methodology_version": CARBON_METHODOLOGY_VERSION,
    }


def compute_carbon_factor_checksum(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def carbon_assurance_snapshot(
    factor_payload: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """
    Return an auditable snapshot of the carbon methodology and factor versions.

    This is used for procurement/compliance evidence capture (reproducibility).
    """
    payload = (
        factor_payload
        if isinstance(factor_payload, dict) and factor_payload
        else build_carbon_factor_payload()
    )
    checksum = compute_carbon_factor_checksum(payload)

    return {
        "methodology_version": str(
            payload.get("methodology_version") or CARBON_METHODOLOGY_VERSION
        ),
        "factor_source": str(payload.get("factor_source") or CARBON_FACTOR_SOURCE),
        "factor_version": str(payload.get("factor_version") or CARBON_FACTOR_VERSION),
        "factor_timestamp": str(
            payload.get("factor_timestamp") or CARBON_FACTOR_TIMESTAMP
        ),
        "constants": {
            "cloud_pue": float(payload.get("cloud_pue") or CLOUD_PUE),
            "embodied_emissions_factor_kg_per_kwh": float(
                payload.get("embodied_emissions_factor") or EMBODIED_EMISSIONS_FACTOR
            ),
        },
        "region_intensity": {
            "count": len(payload.get("region_carbon_intensity") or {}),
            "default_gco2_kwh": int(
                (payload.get("region_carbon_intensity") or {}).get("default", 400)
            ),
        },
        "providers": sorted(
            (payload.get("service_energy_factors_by_provider") or {}).keys()
        ),
        "factors_checksum_sha256": checksum,
    }


class CarbonCalculator:
    """
    Calculates carbon footprint from cloud and Cloud+ cost data.

    2026 Methodology:
    1. Estimate energy (kWh) from cost using provider/service factors
    2. Apply PUE multiplier for datacenter overhead
    3. Multiply by region carbon intensity (gCO2/kWh) -> Scope 2
    4. Add embodied emissions (Scope 3)
    5. Convert to kg CO2
    6. Calculate carbon efficiency score (gCO2e per $1)
    """

    def __init__(self, factor_payload: Dict[str, Any] | None = None) -> None:
        payload = (
            factor_payload
            if isinstance(factor_payload, dict) and factor_payload
            else build_carbon_factor_payload()
        )
        self._factor_payload = payload
        self._region_intensity = (
            payload.get("region_carbon_intensity") or REGION_CARBON_INTENSITY
        )
        self._energy_factors = (
            payload.get("service_energy_factors_by_provider")
            or SERVICE_ENERGY_FACTORS_BY_PROVIDER
        )
        self._cloud_pue = Decimal(str(payload.get("cloud_pue") or CLOUD_PUE))
        self._embodied_emissions_factor = Decimal(
            str(payload.get("embodied_emissions_factor") or EMBODIED_EMISSIONS_FACTOR)
        )
        self._factor_source = str(payload.get("factor_source") or CARBON_FACTOR_SOURCE)
        self._factor_version = str(
            payload.get("factor_version") or CARBON_FACTOR_VERSION
        )
        self._factor_timestamp = str(
            payload.get("factor_timestamp") or CARBON_FACTOR_TIMESTAMP
        )
        self._methodology_version = str(
            payload.get("methodology_version") or CARBON_METHODOLOGY_VERSION
        )
        self._factors_checksum = compute_carbon_factor_checksum(payload)

    def _normalize_provider(self, provider: str | None) -> str:
        provider_key = (provider or "aws").strip().lower()
        return provider_key if provider_key in self._energy_factors else "generic"

    def _resolve_energy_factor(self, provider: str, service: str | None) -> Decimal:
        provider_key = self._normalize_provider(provider)
        service_key = str(service or "default")
        factor_map = self._energy_factors[provider_key]

        if service_key in factor_map:
            return Decimal(str(factor_map[service_key]))

        # Cross-provider fallback for known AWS labels common in normalized inputs.
        if service_key in AWS_SERVICE_ENERGY_FACTORS:
            return Decimal(str(AWS_SERVICE_ENERGY_FACTORS[service_key]))

        return Decimal(
            str(factor_map.get("default", GENERIC_SERVICE_ENERGY_FACTORS["default"]))
        )

    def calculate_from_costs(
        self,
        cost_data: List[Dict[str, Any]],
        region: str = "us-east-1",
        provider: str = "aws",
    ) -> Dict[str, Any]:
        """Cost-proxy calculation for grouped/flat usage inputs."""
        total_cost_usd = Decimal("0")
        total_energy_kwh = Decimal("0")

        for record in cost_data:
            try:
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
                            energy_factor = self._resolve_energy_factor(
                                provider, service
                            )
                            total_energy_kwh += cost_amount * energy_factor
                elif "cost_usd" in record:
                    # Normalized adapter payload (AWS/Azure/GCP/SaaS/license).
                    cost_amount = Decimal(str(record.get("cost_usd", "0")))
                    if cost_amount > 0:
                        total_cost_usd += cost_amount
                        service = str(record.get("service") or "default")
                        row_provider = str(record.get("provider") or provider)
                        energy_factor = self._resolve_energy_factor(
                            row_provider, service
                        )
                        total_energy_kwh += cost_amount * energy_factor
                else:
                    cost_amount = Decimal(
                        record.get("Total", {})
                        .get("UnblendedCost", {})
                        .get("Amount", "0")
                    )
                    if cost_amount > 0:
                        total_cost_usd += cost_amount
                        energy_factor = self._resolve_energy_factor(provider, None)
                        total_energy_kwh += cost_amount * energy_factor
            except (KeyError, TypeError, ValueError) as exc:
                logger.warning("carbon_calc_skip_record", error=str(exc))
                continue

        return self._finalize_calculation(
            total_cost_usd, total_energy_kwh, region, provider
        )

    def calculate_from_records(
        self,
        records: List[Any],
        region: str = "us-east-1",
        provider: str = "aws",
    ) -> Dict[str, Any]:
        """
        High-precision calculation from record objects.
        Uses amount_raw when available as higher-fidelity signal.
        """
        total_cost_usd = Decimal("0")
        total_energy_kwh = Decimal("0")

        for record in records:
            record_provider = str(getattr(record, "provider", provider) or provider)
            total_cost_usd += record.cost_usd

            if record.amount_raw and record.amount_raw > 0:
                # Example refinement for explicit EC2 vCPU-hours usage.
                if "EC2" in record.service and "vCPU-Hours" in str(record.usage_type):
                    total_energy_kwh += record.amount_raw * Decimal("0.010")
                else:
                    energy_factor = self._resolve_energy_factor(
                        record_provider, record.service
                    )
                    total_energy_kwh += record.cost_usd * energy_factor
            else:
                energy_factor = self._resolve_energy_factor(
                    record_provider, record.service
                )
                total_energy_kwh += record.cost_usd * energy_factor

        return self._finalize_calculation(
            total_cost_usd, total_energy_kwh, region, provider
        )

    def _finalize_calculation(
        self,
        total_cost_usd: Decimal,
        total_energy_kwh: Decimal,
        region: str,
        provider: str = "aws",
    ) -> Dict[str, Any]:
        """Shared logic for emissions calculation and result formatting."""
        total_energy_with_pue = total_energy_kwh * self._cloud_pue

        carbon_intensity = int(
            self._region_intensity.get(
                region, self._region_intensity.get("default", 400)
            )
        )

        scope2_co2_grams = total_energy_with_pue * Decimal(str(carbon_intensity))
        scope2_co2_kg = scope2_co2_grams / Decimal("1000")

        scope3_co2_kg = total_energy_with_pue * self._embodied_emissions_factor
        total_co2_kg = scope2_co2_kg + scope3_co2_kg

        carbon_efficiency_score = 0.0
        if total_cost_usd > 0:
            carbon_efficiency_score = float(total_co2_kg * 1000 / total_cost_usd)
        elif total_co2_kg > 0:
            carbon_efficiency_score = 9999.9

        equivalencies = self._calculate_equivalencies(float(total_co2_kg))
        methodology_metadata = self._build_methodology_metadata(
            provider=provider,
            region=region,
            carbon_intensity=carbon_intensity,
            total_cost_usd=total_cost_usd,
            total_energy_kwh=total_energy_kwh,
        )

        normalized_provider = self._normalize_provider(provider)
        result = {
            "total_co2_kg": round(float(total_co2_kg), 3),
            "scope2_co2_kg": round(float(scope2_co2_kg), 3),
            "scope3_co2_kg": round(float(scope3_co2_kg), 3),
            "total_cost_usd": round(float(total_cost_usd), 2),
            "estimated_energy_kwh": round(float(total_energy_with_pue), 3),
            "carbon_efficiency_score": round(carbon_efficiency_score, 2),
            "carbon_efficiency_unit": "gCO2e per $1 spent",
            "provider": normalized_provider,
            "region": region,
            "carbon_intensity_gco2_kwh": carbon_intensity,
            "equivalencies": equivalencies,
            "methodology": "Valdrix 2026 (CCF + multi-cloud provider factors v2.0)",
            "methodology_metadata": methodology_metadata,
            "includes_embodied_emissions": True,
            "forecast_30d": self.forecast_emissions(
                float(total_co2_kg) / 30 if total_co2_kg > 0 else 0
            ),
            "green_region_recommendations": self.get_green_region_recommendations(
                region
            ),
        }

        logger.info(
            "carbon_calculated",
            co2_kg=result["total_co2_kg"],
            cost_usd=result["total_cost_usd"],
            efficiency_score=result["carbon_efficiency_score"],
            provider=result["provider"],
            region=region,
        )

        return result

    def _build_methodology_metadata(
        self,
        provider: str,
        region: str,
        carbon_intensity: int,
        total_cost_usd: Decimal,
        total_energy_kwh: Decimal,
    ) -> Dict[str, Any]:
        normalized_provider = self._normalize_provider(provider)
        factors_checksum = self._factors_checksum

        input_checksum = hashlib.sha256(
            json.dumps(
                {
                    "provider": normalized_provider,
                    "region": region,
                    "carbon_intensity": carbon_intensity,
                    "total_cost_usd": str(total_cost_usd),
                    "total_energy_kwh": str(total_energy_kwh),
                },
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

        return {
            "methodology_version": self._methodology_version,
            "factor_source": self._factor_source,
            "factor_version": self._factor_version,
            "factor_timestamp": self._factor_timestamp,
            "provider": normalized_provider,
            "region_factor": {
                "region": region,
                "carbon_intensity_gco2_kwh": carbon_intensity,
            },
            "constants": {
                "cloud_pue": float(self._cloud_pue),
                "embodied_emissions_factor_kg_per_kwh": float(
                    self._embodied_emissions_factor
                ),
            },
            "factors_checksum_sha256": factors_checksum,
            "calculation_input_checksum_sha256": input_checksum,
        }

    def _calculate_equivalencies(self, co2_kg: float) -> Dict[str, Any]:
        """Convert CO2 to relatable equivalencies."""
        return {
            "miles_driven": round(co2_kg * 1000 / 404, 1),
            "trees_needed_for_year": round(co2_kg / 22, 1),
            "smartphone_charges": round(co2_kg * 1000 / 3.4, 0),
            "percent_of_home_month": round((co2_kg / 360) * 100, 2),
        }

    def get_green_region_recommendations(
        self, current_region: str
    ) -> List[Dict[str, Any]]:
        """Recommend lower-carbon regions for workload placement."""
        current_intensity = int(
            self._region_intensity.get(
                current_region, self._region_intensity.get("default", 400)
            )
        )

        recommendations = []
        for region, intensity in sorted(
            self._region_intensity.items(), key=lambda x: x[1]
        ):
            if region == "default":
                continue
            if intensity < current_intensity and current_intensity > 0:
                savings_percent = round((1 - intensity / current_intensity) * 100, 1)
                recommendations.append(
                    {
                        "region": region,
                        "carbon_intensity": intensity,
                        "savings_percent": savings_percent,
                    }
                )

        return recommendations[:5]

    def forecast_emissions(
        self,
        current_daily_co2_kg: float,
        days: int = 30,
        region_trend_factor: float = 0.99,
    ) -> Dict[str, Any]:
        """Predict future emissions based on current workload and grid trends."""
        baseline_projection = current_daily_co2_kg * days
        projected_co2_kg = baseline_projection * region_trend_factor

        return {
            "forecast_days": days,
            "baseline_co2_kg": round(baseline_projection, 2),
            "projected_co2_kg": round(projected_co2_kg, 2),
            "trend_factor": region_trend_factor,
            "description": f"Forecast for next {days} days based on current usage.",
        }
