"""
Carbon-Aware Scheduling

Implements GreenOps automation by:
1. Scheduling non-urgent workloads during renewable energy peaks
2. Preferring low-carbon regions for flexible operations
3. Tracking and reporting carbon impact of scheduling decisions

Data Sources:
- WattTime API (real-time grid carbon intensity)
- Electricity Maps API (alternative)
- AWS Sustainability Pillar data

References:
- Green Software Foundation: Carbon Aware SDK
- AWS Well-Architected: Sustainability Pillar
"""

from datetime import datetime, timezone
from typing import List, Dict, Optional
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger()


class CarbonIntensity(str, Enum):
    """Carbon intensity levels."""
    VERY_LOW = "very_low"  # < 100 gCO2/kWh
    LOW = "low"  # 100-200 gCO2/kWh
    MEDIUM = "medium"  # 200-400 gCO2/kWh
    HIGH = "high"  # 400-600 gCO2/kWh
    VERY_HIGH = "very_high"  # > 600 gCO2/kWh


@dataclass
class RegionCarbonProfile:
    """Carbon profile for an AWS region."""
    region: str
    avg_intensity_gco2_kwh: float
    renewable_percentage: float
    best_hours_utc: List[int]  # Hours when carbon is typically lowest


# Static data based on 2026 research
# Real implementation should use WattTime or Electricity Maps API
REGION_CARBON_PROFILES = {
    # Low carbon regions (hydro/nuclear/renewable heavy)
    "eu-north-1": RegionCarbonProfile("eu-north-1", 30, 95, [0, 1, 2, 3, 4, 5]),  # Sweden
    "eu-west-1": RegionCarbonProfile("eu-west-1", 200, 60, [1, 2, 3, 4]),  # Ireland
    "ca-central-1": RegionCarbonProfile("ca-central-1", 50, 80, [0, 1, 2, 3]),  # Quebec Hydro
    "us-west-2": RegionCarbonProfile("us-west-2", 100, 70, [2, 3, 4, 5]),  # Oregon Hydro

    # Medium carbon regions
    "us-east-1": RegionCarbonProfile("us-east-1", 350, 25, [2, 3, 4]),  # Virginia
    "ap-northeast-1": RegionCarbonProfile("ap-northeast-1", 450, 20, [1, 2, 3]),  # Tokyo

    # High carbon regions
    "ap-south-1": RegionCarbonProfile("ap-south-1", 700, 15, [10, 11, 12]),  # Mumbai (solar peak)
    "ap-southeast-1": RegionCarbonProfile("ap-southeast-1", 450, 20, [10, 11, 12]),  # Singapore
}

# BE-CARBON-1: Data freshness tracking
_CARBON_DATA_LAST_UPDATED = datetime(2026, 1, 15, tzinfo=timezone.utc)
_CARBON_DATA_MAX_AGE_DAYS = 30  # Data older than this should trigger a warning


def validate_carbon_data_freshness() -> bool:
    """
    BE-CARBON-1: Validate that carbon intensity data is fresh.
    Raises CarbonDataStaleError if data is outdated.
    Returns True if data is current.
    """
    now = datetime.now(timezone.utc)
    age = (now - _CARBON_DATA_LAST_UPDATED).days
    
    if age > _CARBON_DATA_MAX_AGE_DAYS:
        error_msg = f"Carbon intensity data is {age} days old (max: {_CARBON_DATA_MAX_AGE_DAYS}). Update REGION_CARBON_PROFILES."
        logger.error("carbon_data_stale", 
                     last_updated=_CARBON_DATA_LAST_UPDATED.isoformat(),
                     age_days=age,
                     max_age_days=_CARBON_DATA_MAX_AGE_DAYS)
        raise ValueError(error_msg)
    
    return True


class CarbonAwareScheduler:
    """
    Schedules workloads based on carbon intensity.

    Usage:
        scheduler = CarbonAwareScheduler()

        # Find best time for backup job
        optimal_time = scheduler.get_optimal_execution_time(
            regions=["us-east-1", "eu-west-1"],
            workload_type="backup"
        )

        # Find lowest carbon region for new workload
        best_region = scheduler.get_lowest_carbon_region(
            candidate_regions=["us-east-1", "us-west-2", "eu-north-1"]
        )
    """

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key  # For WattTime or Electricity Maps
        self._use_static_data = api_key is None

    def get_region_intensity(self, region: str) -> CarbonIntensity:
        """Get current carbon intensity for a region."""
        profile = REGION_CARBON_PROFILES.get(region)
        if not profile:
            return CarbonIntensity.MEDIUM  # Unknown = medium

        intensity = profile.avg_intensity_gco2_kwh
        if intensity < 100:
            return CarbonIntensity.VERY_LOW
        elif intensity < 200:
            return CarbonIntensity.LOW
        elif intensity < 400:
            return CarbonIntensity.MEDIUM
        elif intensity < 600:
            return CarbonIntensity.HIGH
        else:
            return CarbonIntensity.VERY_HIGH

    def get_lowest_carbon_region(
        self,
        candidate_regions: List[str]
    ) -> str:
        """
        Find the lowest carbon region from candidates.

        Use for:
        - Disaster recovery failover decisions
        - New workload placement
        """
        if not candidate_regions:
            raise ValueError("No candidate regions provided")

        ranked = sorted(
            candidate_regions,
            key=lambda r: REGION_CARBON_PROFILES.get(
                r,
                RegionCarbonProfile(r, 500, 20, [])
            ).avg_intensity_gco2_kwh
        )

        best = ranked[0]
        logger.info("lowest_carbon_region_selected",
                   region=best,
                   candidates=candidate_regions)

        return best

    def get_optimal_execution_time(
        self,
        region: str,
        max_delay_hours: int = 24
    ) -> Optional[datetime]:
        """
        Find optimal time to execute workload for lowest carbon.

        Returns:
            Best datetime to execute (within delay window)
        """
        profile = REGION_CARBON_PROFILES.get(region)
        if not profile or not profile.best_hours_utc:
            return None  # Execute now

        now = datetime.now(timezone.utc)
        current_hour = now.hour

        # Find next best hour within window
        for hour_offset in range(max_delay_hours):
            candidate_hour = (current_hour + hour_offset) % 24
            if candidate_hour in profile.best_hours_utc:
                optimal = now.replace(
                    hour=candidate_hour,
                    minute=0,
                    second=0,
                    microsecond=0
                )
                if hour_offset > 0:
                    optimal = optimal.replace(day=now.day + (hour_offset // 24))

                logger.info("carbon_optimal_time",
                           region=region,
                           optimal_hour=candidate_hour,
                           delay_hours=hour_offset)
                return optimal

        return None  # No optimal time in window

    def should_defer_workload(
        self,
        region: str,
        workload_type: str = "batch"
    ) -> bool:
        """
        Check if workload should be deferred to lower-carbon time.

        Workload types:
        - "critical": Never defer
        - "standard": Defer if high carbon
        - "batch": Always defer to optimal time if possible
        """
        if workload_type == "critical":
            return False

        intensity = self.get_region_intensity(region)

        if workload_type == "batch":
            return intensity not in [CarbonIntensity.VERY_LOW, CarbonIntensity.LOW]

        # Standard: defer only if very high
        return intensity == CarbonIntensity.VERY_HIGH

    def estimate_carbon_savings(
        self,
        region_from: str,
        region_to: str,
        compute_hours: float
    ) -> Dict[str, float]:
        """
        Estimate carbon savings from region migration.

        Returns:
            Dict with gCO2 saved and percentage reduction
        """
        from_profile = REGION_CARBON_PROFILES.get(
            region_from,
            RegionCarbonProfile(region_from, 400, 20, [])
        )
        to_profile = REGION_CARBON_PROFILES.get(
            region_to,
            RegionCarbonProfile(region_to, 400, 20, [])
        )

        # Assuming 0.5 kWh per compute hour (rough estimate)
        kwh = compute_hours * 0.5

        from_carbon = from_profile.avg_intensity_gco2_kwh * kwh
        to_carbon = to_profile.avg_intensity_gco2_kwh * kwh
        saved = from_carbon - to_carbon

        return {
            "from_gco2": round(from_carbon, 2),
            "to_gco2": round(to_carbon, 2),
            "saved_gco2": round(saved, 2),
            "reduction_percent": round((saved / from_carbon) * 100, 1) if from_carbon > 0 else 0
        }
