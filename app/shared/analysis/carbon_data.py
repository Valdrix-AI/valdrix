"""
Carbon Intensity Metrics (gCO2e per USD).
Used for illustrative GreenOps projections.
"""

from typing import Dict

# Illustrative intensities: 
# Coal-heavy (e.g. us-east-1) vs. Green-heavy (e.g. eu-central-1)
REGION_CARBON_INTENSITY: Dict[str, float] = {
    "us-east-1": 412.0,
    "us-west-2": 150.0,
    "eu-central-1": 55.0,
    "af-south-1": 620.0,
    "global": 300.0
}

DEFAULT_CARBON_INTENSITY = 300.0
