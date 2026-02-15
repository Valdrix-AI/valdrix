"""
Carbon Intensity Metrics (gCO2e per USD).
Used for illustrative GreenOps projections.
"""

from typing import Dict, Union
from decimal import Decimal, InvalidOperation

# Illustrative intensities:
# Coal-heavy (e.g. us-east-1) vs. Green-heavy (e.g. eu-central-1)
REGION_CARBON_INTENSITY: Dict[str, float] = {
    "us-east-1": 412.0,
    "us-west-2": 150.0,
    "eu-central-1": 55.0,
    "af-south-1": 620.0,
    "global": 300.0,
}

DEFAULT_CARBON_INTENSITY = 300.0


def get_region_intensity(region: Union[str, None]) -> float:
    """
    Get carbon intensity for a region with fallback to default.

    Args:
        region: AWS region name or None

    Returns:
        Carbon intensity in gCO2e per USD
    """
    if not region:
        return DEFAULT_CARBON_INTENSITY

    region = region.lower().strip()
    intensity = REGION_CARBON_INTENSITY.get(region, DEFAULT_CARBON_INTENSITY)

    # Validate that intensity is a valid numeric value
    try:
        intensity_float = float(intensity)
        if 0 < intensity_float < 2000:  # Reasonable bounds
            return intensity_float
        else:
            return DEFAULT_CARBON_INTENSITY
    except (ValueError, TypeError):
        return DEFAULT_CARBON_INTENSITY


def calculate_carbon_footprint(
    cost: Union[Decimal, float, int], region: Union[str, None]
) -> Decimal:
    """
    Calculate carbon footprint for a given cost and region.

    Args:
        cost: Cost amount (USD)
        region: AWS region name

    Returns:
        Carbon footprint in kg CO2e

    Raises:
        ValueError: If cost is negative
        TypeError: If cost is not numeric
    """
    if cost is None:
        raise TypeError("Cost cannot be None")

    try:
        cost_decimal = Decimal(str(cost))
    except (ValueError, TypeError):
        raise TypeError(f"Cost must be numeric, got {type(cost)}")

    if cost_decimal < 0:
        raise ValueError("Cost cannot be negative")

    intensity = get_region_intensity(region)
    # Convert gCO2e per USD to kgCO2e per USD (divide by 1000)
    return cost_decimal * Decimal(str(intensity)) / Decimal("1000")


def validate_region_data() -> bool:
    """
    Validate that region carbon intensity data is reasonable for production use.

    Returns:
        True if data is valid, False otherwise
    """
    if not REGION_CARBON_INTENSITY:
        return False

    # Check that all values are reasonable
    for region, intensity in REGION_CARBON_INTENSITY.items():
        if not isinstance(intensity, (int, float)):
            return False
        if not (0 < intensity < 2000):  # Reasonable bounds
            return False

    # Should have at least one clean and one dirty region
    values = list(REGION_CARBON_INTENSITY.values())
    has_clean = any(v < 200 for v in values)
    has_dirty = any(v > 400 for v in values)

    return has_clean and has_dirty


def get_carbon_reduction_opportunity(
    cost: Union[Decimal, float, int],
) -> Dict[str, Union[str, float]]:
    """
    Calculate potential carbon reduction by moving to cleaner regions.

    Args:
        cost: Monthly cloud cost (USD)

    Returns:
        Dict with reduction opportunities
    """
    if not REGION_CARBON_INTENSITY:
        return {"error": "No region data available"}

    try:
        cost_decimal = Decimal(str(cost))
    except (ValueError, TypeError, InvalidOperation):
        return {"error": "Invalid cost value"}

    if cost_decimal < 0:
        return {"error": "Cost cannot be negative"}

    # Find dirtiest and cleanest regions
    sorted_regions = sorted(REGION_CARBON_INTENSITY.items(), key=lambda x: x[1])
    cleanest = sorted_regions[0]
    dirtiest = sorted_regions[-1]

    # Calculate potential savings
    try:
        dirty_footprint = calculate_carbon_footprint(cost_decimal, dirtiest[0])
        clean_footprint = calculate_carbon_footprint(cost_decimal, cleanest[0])
        reduction = dirty_footprint - clean_footprint
    except (ValueError, TypeError) as exc:
        return {"error": str(exc)}

    return {
        "dirtiest_region": dirtiest[0],
        "cleanest_region": cleanest[0],
        "monthly_reduction_kg": float(reduction),
        "reduction_percentage": float((reduction / dirty_footprint) * 100)
        if dirty_footprint > 0
        else 0,
        "cost": float(cost_decimal),
    }


def estimate_carbon_for_service(
    service: str,
    monthly_cost: Union[Decimal, float, int],
    region: Union[str, None] = None,
) -> Dict[str, Union[str, float]]:
    """
    Estimate carbon footprint for a specific cloud service.

    Args:
        service: Cloud service name (e.g., 'compute', 'storage')
        monthly_cost: Monthly cost for the service
        region: AWS region (optional)

    Returns:
        Dict with carbon estimates
    """
    try:
        footprint = calculate_carbon_footprint(monthly_cost, region)
        return {
            "service": service,
            "region": region or "global",
            "monthly_cost_usd": float(monthly_cost),
            "monthly_carbon_kg": float(footprint),
            "annual_carbon_kg": float(footprint * 12),
            "intensity_g_per_usd": get_region_intensity(region),
        }
    except (ValueError, TypeError) as e:
        return {"error": str(e)}
