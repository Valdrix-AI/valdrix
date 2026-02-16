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
from typing import List, Dict, Optional, Any
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
    renewable_percentage: float
    carbon_intensity_low: float  # Typical low in gCO2/kWh
    carbon_intensity_high: float  # Typical high in gCO2/kWh
    best_hours_utc: List[int]  # Hours when carbon is typically lowest
    peak_solar_hour_utc: Optional[int] = None
    peak_wind_hour_utc: Optional[int] = None


# Static data based on 2026 research
# Intensities are gCO2eq/kWh (Average Carbon Intensity - Industry Standard)
REGION_CARBON_PROFILES = {
    "eu-north-1": RegionCarbonProfile(
        "eu-north-1", 95, 30, 45, [0, 1, 2, 3, 4, 5, 22, 23], None, 2
    ),  # Sweden (Wind/Hydro)
    "eu-west-1": RegionCarbonProfile(
        "eu-west-1", 60, 150, 280, [1, 2, 3, 4, 11, 12, 13], 12, 3
    ),  # Ireland (Solar/Wind)
    "ca-central-1": RegionCarbonProfile(
        "ca-central-1", 80, 40, 60, [0, 1, 2, 3, 4, 5], None, None
    ),  # Quebec (Hydro stable)
    "us-west-2": RegionCarbonProfile(
        "us-west-2", 70, 80, 120, [2, 3, 4, 5, 12, 13], 13, 4
    ),  # Oregon (Hydro/Solar)
    "us-east-1": RegionCarbonProfile(
        "us-east-1", 25, 320, 420, [12, 13, 14, 15], 13, None
    ),  # Virginia (Gas/Solar mix)
    "ap-northeast-1": RegionCarbonProfile(
        "ap-northeast-1", 20, 400, 550, [2, 3, 4], 3, None
    ),  # Tokyo
    "ap-south-1": RegionCarbonProfile(
        "ap-south-1", 15, 600, 850, [6, 7, 8, 9], 7, None
    ),  # Mumbai (Strong solar)
    "af-south-1": RegionCarbonProfile(
        "af-south-1", 10, 700, 950, [6, 7, 8, 9], 7, None
    ),  # Cape Town (Coal heavy, some solar)
}

# BE-CARBON-1: Data freshness tracking
# Updated to 2026-02-08 as part of project maintenance
_CARBON_DATA_LAST_UPDATED = datetime(2026, 2, 8, tzinfo=timezone.utc)
_CARBON_DATA_MAX_AGE_DAYS = 30  # Data older than this should trigger a warning

# Representative coordinates for WattTime forecasting by AWS region
# Keep in sync with REGION_CARBON_PROFILES coverage.
WATTTIME_REGION_COORDS = {
    "us-east-1": (38.03, -78.48),  # Virginia, USA
    "us-west-2": (45.52, -122.67),  # Oregon, USA
    "ca-central-1": (45.50, -73.56),  # Quebec, Canada
    "eu-west-1": (53.34, -6.26),  # Dublin, Ireland
    "eu-north-1": (59.32, 18.06),  # Stockholm, Sweden
    "ap-northeast-1": (35.68, 139.69),  # Tokyo, Japan
    "ap-south-1": (19.07, 72.88),  # Mumbai, India
    "af-south-1": (-33.92, 18.42),  # Cape Town, South Africa
}


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
        logger.error(
            "carbon_data_stale",
            last_updated=_CARBON_DATA_LAST_UPDATED.isoformat(),
            age_days=age,
            max_age_days=_CARBON_DATA_MAX_AGE_DAYS,
        )
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

    def __init__(
        self,
        wattime_key: Optional[str] = None,
        electricitymaps_key: Optional[str] = None,
    ):
        self.wattime_key = wattime_key
        self.electricitymaps_key = electricitymaps_key
        self._use_static_data = not (wattime_key or electricitymaps_key)

    async def get_region_intensity(self, region: str) -> CarbonIntensity:
        """Get current carbon intensity for a region."""
        profile = REGION_CARBON_PROFILES.get(region)
        if not profile:
            return CarbonIntensity.MEDIUM  # Unknown = medium

        # BE-CARBON-1: Ensure data is fresh
        validate_carbon_data_freshness()

        # Logic for real-time calculation would go here if API key is present
        # For now, we simulate current intensity based on current UTC hour
        now_hour = datetime.now(timezone.utc).hour
        intensity = self._simulate_intensity(profile, now_hour)

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

    def _simulate_intensity(self, profile: RegionCarbonProfile, hour_utc: int) -> float:
        """Simulates carbon intensity for a specific hour using a sine wave for solar/wind."""
        import math

        # Baseline is halfway between low and high
        base = (profile.carbon_intensity_low + profile.carbon_intensity_high) / 2
        amplitude = (profile.carbon_intensity_high - profile.carbon_intensity_low) / 2

        # Solar effect (lowest at peak solar hour)
        solar_factor = 0.0
        if profile.peak_solar_hour_utc is not None:
            # Lowest intensity at peak solar
            solar_factor = math.cos(
                math.pi * (hour_utc - profile.peak_solar_hour_utc) / 12
            )

        # Wind effect (simulated as another wave if applicable)
        wind_factor = 0.0
        if profile.peak_wind_hour_utc is not None:
            wind_factor = math.cos(
                math.pi * (hour_utc - profile.peak_wind_hour_utc) / 6
            )

        # Combined simulated intensity
        # We subtract the factors because higher renewable = lower carbon intensity
        adjustment = (solar_factor * 0.7 + wind_factor * 0.3) * amplitude
        return max(
            profile.carbon_intensity_low,
            min(profile.carbon_intensity_high, base - adjustment),
        )

    async def get_intensity_forecast(
        self, region: str, hours: int = 24
    ) -> List[Dict[str, Any]]:
        """
        Generates a carbon intensity forecast.
        Simulation: Provides Average Carbon Intensity (gCO2eq/kWh).
        Production-ready: Will call WattTime (MOER) or Electricity Maps (Average) if API keys are available.
        Fallback: High-fidelity diurnal simulation.
        """
        # BE-CARBON-1: Ensure data is fresh
        validate_carbon_data_freshness()

        profile = REGION_CARBON_PROFILES.get(region)
        if not profile:
            return []

        if self.wattime_key:
            return await self._fetch_wattime_forecast(region, hours)

        if self.electricitymaps_key:
            return await self._fetch_emap_forecast(region, hours)

        forecast = []
        from datetime import timedelta

        now = datetime.now(timezone.utc)
        base_time = now.replace(minute=0, second=0, microsecond=0)

        for i in range(hours):
            target_time = base_time + timedelta(hours=i)
            target_hour = target_time.hour
            intensity = self._simulate_intensity(profile, target_hour)

            forecast.append(
                {
                    "hour_utc": target_hour,
                    "timestamp": target_time.isoformat(),
                    "intensity_gco2_kwh": round(intensity, 1),
                    "level": self._intensity_to_level(intensity),
                }
            )
        return forecast

    def _intensity_to_level(self, intensity: float) -> str:
        if intensity < 100:
            return "very_low"
        if intensity < 200:
            return "low"
        if intensity < 400:
            return "medium"
        if intensity < 600:
            return "high"
        return "very_high"

    def _get_avg_intensity(self, profile: RegionCarbonProfile) -> float:
        """Returns the average intensity for a profile."""
        return (profile.carbon_intensity_low + profile.carbon_intensity_high) / 2

    def get_lowest_carbon_region(self, candidate_regions: List[str]) -> str:
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
            key=lambda r: self._get_avg_intensity(
                REGION_CARBON_PROFILES.get(r, RegionCarbonProfile(r, 20, 400, 600, []))
            ),
        )

        best = ranked[0]
        logger.info(
            "lowest_carbon_region_selected", region=best, candidates=candidate_regions
        )

        return best

    async def get_optimal_execution_time(
        self, region: str, max_delay_hours: int = 24
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

        # Find next best hour within window
        from datetime import timedelta

        # Start looking from current hour
        for hour_offset in range(max_delay_hours):
            target_time = now + timedelta(hours=hour_offset)
            candidate_hour = target_time.hour

            if candidate_hour in profile.best_hours_utc:
                # Normalize to the beginning of that hour
                optimal = target_time.replace(minute=0, second=0, microsecond=0)

                # Ensure we don't return a time in the past
                if optimal < now:
                    continue

                logger.info(
                    "carbon_optimal_time",
                    region=region,
                    optimal_hour=candidate_hour,
                    delay_hours=hour_offset,
                )
                return optimal

        return None  # No optimal time in window

    async def should_defer_workload(
        self, region: str, workload_type: str = "batch"
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

        intensity = await self.get_region_intensity(region)

        if workload_type == "batch":
            return intensity not in [CarbonIntensity.VERY_LOW, CarbonIntensity.LOW]

        # Standard: defer only if very high
        return intensity == CarbonIntensity.VERY_HIGH

    def estimate_carbon_savings(
        self, region_from: str, region_to: str, compute_hours: float
    ) -> Dict[str, float]:
        """
        Estimate carbon savings from region migration.

        Returns:
            Dict with gCO2 saved and percentage reduction
        """
        from_profile = REGION_CARBON_PROFILES.get(
            region_from, RegionCarbonProfile(region_from, 20, 400, 600, [])
        )
        to_profile = REGION_CARBON_PROFILES.get(
            region_to, RegionCarbonProfile(region_to, 20, 400, 600, [])
        )

        # Assuming 0.5 kWh per compute hour (rough estimate)
        kwh = compute_hours * 0.5

        from_carbon = self._get_avg_intensity(from_profile) * kwh
        to_carbon = self._get_avg_intensity(to_profile) * kwh
        saved = from_carbon - to_carbon

        return {
            "from_gco2": round(from_carbon, 2),
            "to_gco2": round(to_carbon, 2),
            "saved_gco2": round(saved, 2),
            "reduction_percent": round((saved / from_carbon) * 100, 1)
            if from_carbon > 0
            else 0,
        }

    async def _fetch_wattime_forecast(
        self, region: str, hours: int
    ) -> List[Dict[str, Any]]:
        """Fetch real-time MOER data from WattTime."""

        try:
            from app.shared.core.http import get_http_client

            client = get_http_client()
            # WattTime uses a login endpoint for a token, then GET /v2/forecast
            coords = WATTTIME_REGION_COORDS.get(region)
            if not coords:
                logger.warning("wattime_region_unmapped", region=region)
                return []

            payload = {
                "latitude": coords[0],
                "longitude": coords[1],
                "horizon": hours,
            }

            response = await client.get(
                "https://api2.watttime.org/v2/forecast",
                params=payload,
                headers={"Authorization": f"Bearer {self.wattime_key}"},
            )
            response.raise_for_status()
            data = response.json()
            return [
                {
                    "timestamp": d["point_time"],
                    "intensity_gco2_kwh": d["value"],
                    "level": self._intensity_to_level(d["value"]),
                }
                for d in data.get("data", [])
            ]
        except Exception as e:
            logger.error("wattime_api_failed", error=str(e), region=region)
            return []

    async def _fetch_emap_forecast(
        self, region: str, hours: int
    ) -> List[Dict[str, Any]]:
        """Fetch average intensity from Electricity Maps."""

        try:
            from app.shared.core.http import get_http_client

            client = get_http_client()
            # Maps region to Electricity Maps zone (e.g., US-VA, DE, FR)
            zone = "US-VA"  # Default
            if region.startswith("eu-"):
                zone = region.split("-")[
                    1
                ].upper()  # Rough guess (e.g., eu-west-1 -> WEST)

            headers = (
                {"auth-token": self.electricitymaps_key}
                if self.electricitymaps_key
                else {}
            )
            response = await client.get(
                "https://api.electricitymap.org/v3/carbon-intensity/forecast",
                params={"zone": zone, "horizon": hours},
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()
            return [
                {
                    "timestamp": d["datetime"],
                    "intensity_gco2_kwh": d["carbonIntensity"],
                    "level": self._intensity_to_level(d["carbonIntensity"]),
                }
                for d in data.get("forecast", [])
            ]
        except Exception as e:
            logger.error("emap_api_failed", error=str(e), region=region)
            return []
