"""
Production-quality tests for carbon_data.py - Carbon intensity metrics with comprehensive coverage.
Includes edge cases, error handling, realistic scenarios, and production-like testing patterns.
"""

import pytest
from decimal import Decimal, InvalidOperation
from unittest.mock import patch
from app.shared.analysis.carbon_data import (
    REGION_CARBON_INTENSITY,
    DEFAULT_CARBON_INTENSITY,
    get_region_intensity,
    calculate_carbon_footprint,
    validate_region_data,
    get_carbon_reduction_opportunity,
    estimate_carbon_for_service,
)


def test_region_carbon_intensity_comprehensive_data():
    """Test that region carbon intensity data is properly structured and realistic."""
    # Verify data structure
    assert isinstance(REGION_CARBON_INTENSITY, dict)
    assert len(REGION_CARBON_INTENSITY) >= 4  # At minimum major regions

    # Verify all values are realistic carbon intensities (gCO2e per USD)
    for region, intensity in REGION_CARBON_INTENSITY.items():
        assert isinstance(intensity, (int, float))
        assert 0 < intensity < 2000, (
            f"Region {region} has unrealistic carbon intensity: {intensity}"
        )

        # Specific region validations
        if region == "us-east-1":
            assert intensity > 300, "US East should have high carbon intensity"
        elif region == "eu-central-1":
            assert intensity < 200, "EU should have lower carbon intensity"
        elif region == "af-south-1":
            assert intensity > 400, "Africa should have high carbon intensity"


def test_region_carbon_intensity_keys_production_format():
    """Test that region keys follow cloud provider region naming conventions."""
    for region in REGION_CARBON_INTENSITY.keys():
        if region == "global":
            continue  # Special case for global average

        # Region keys should be normalized lowercase identifiers.
        assert isinstance(region, str)
        assert len(region) >= 5, f"Region {region} name too short"
        assert region == region.lower(), f"Region {region} must be lowercase"
        assert all(c.isalnum() or c == "-" for c in region), (
            f"Region {region} contains invalid characters"
        )


def test_default_carbon_intensity_production_ready():
    """Test default carbon intensity with production considerations."""
    assert isinstance(DEFAULT_CARBON_INTENSITY, (int, float))
    assert DEFAULT_CARBON_INTENSITY > 0

    # Should be reasonable global average
    assert 200 <= DEFAULT_CARBON_INTENSITY <= 600, (
        f"Default intensity {DEFAULT_CARBON_INTENSITY} is unrealistic"
    )

    # Should match global entry if it exists
    if "global" in REGION_CARBON_INTENSITY:
        assert abs(DEFAULT_CARBON_INTENSITY - REGION_CARBON_INTENSITY["global"]) < 1, (
            "Default should match global average"
        )


def test_carbon_intensity_range_production_scenarios():
    """Test carbon intensity ranges for production deployment scenarios."""
    values = list(REGION_CARBON_INTENSITY.values())

    # Should have meaningful variation for optimization opportunities
    min_value = min(values)
    max_value = max(values)

    # Carbon optimization should be possible (at least 2x difference)
    assert max_value / min_value >= 2.0, (
        f"Carbon intensity variation ({max_value / min_value:.1f}x) insufficient for optimization"
    )

    # Should include both clean and dirty regions
    clean_regions = [v for v in values if v < 200]  # Low carbon
    dirty_regions = [v for v in values if v > 500]  # High carbon

    assert len(clean_regions) > 0, "No low-carbon regions available"
    assert len(dirty_regions) > 0, "No high-carbon regions available"


def test_get_region_intensity_basic():
    """Test basic region intensity lookup."""
    # Test existing region
    intensity = get_region_intensity("us-east-1")
    assert intensity == REGION_CARBON_INTENSITY["us-east-1"]

    # Test default fallback
    intensity = get_region_intensity("non-existent-region")
    assert intensity == DEFAULT_CARBON_INTENSITY


def test_get_region_intensity_edge_cases():
    """Test region intensity lookup with edge cases."""
    # Test case insensitive lookup
    intensity1 = get_region_intensity("US-EAST-1")
    intensity2 = get_region_intensity("us-east-1")
    assert intensity1 == intensity2

    # Test empty/None inputs
    assert get_region_intensity("") == DEFAULT_CARBON_INTENSITY
    assert get_region_intensity(None) == DEFAULT_CARBON_INTENSITY

    # Test global region
    global_intensity = get_region_intensity("global")
    assert global_intensity == DEFAULT_CARBON_INTENSITY


def test_calculate_carbon_footprint_basic():
    """Test basic carbon footprint calculation."""
    cost = Decimal("100.00")
    region = "us-east-1"

    footprint = calculate_carbon_footprint(cost, region)
    expected = (
        cost * Decimal(str(REGION_CARBON_INTENSITY["us-east-1"])) / Decimal("1000")
    )  # Convert g to kg

    assert footprint == expected
    assert isinstance(footprint, Decimal)


def test_calculate_carbon_footprint_edge_cases():
    """Test carbon footprint calculation with edge cases."""
    # Zero cost
    assert calculate_carbon_footprint(Decimal("0"), "us-east-1") == Decimal("0")

    # Negative cost (should handle gracefully)
    with pytest.raises(ValueError):
        calculate_carbon_footprint(Decimal("-10"), "us-east-1")

    # Very large cost
    large_cost = Decimal("1000000")
    footprint = calculate_carbon_footprint(large_cost, "us-east-1")
    assert footprint > 0
    # intensity is 412.0 g/USD. For 1,000,000 USD, that's 412,000,000 g = 412,000 kg.
    assert footprint == large_cost * Decimal(
        str(REGION_CARBON_INTENSITY["us-east-1"])
    ) / Decimal("1000")

    # Unknown region
    footprint = calculate_carbon_footprint(Decimal("100"), "unknown-region")
    expected = Decimal("100") * Decimal(str(DEFAULT_CARBON_INTENSITY)) / Decimal("1000")
    assert footprint == expected


def test_calculate_carbon_footprint_precision():
    """Test carbon footprint calculation precision and rounding."""
    # Test with precise decimal values
    cost = Decimal("123.456789")
    region = "eu-central-1"

    footprint = calculate_carbon_footprint(cost, region)
    intensity = Decimal(str(REGION_CARBON_INTENSITY["eu-central-1"]))

    # Should maintain precision
    assert footprint == (cost * intensity) / Decimal("1000")

    # Test rounding behavior for display
    display_value = round(float(footprint), 2)
    assert display_value > 0


def test_validate_region_data_comprehensive():
    """Test comprehensive region data validation."""
    # Valid data should pass
    assert validate_region_data()

    # Test with missing global average
    with patch.dict(REGION_CARBON_INTENSITY, {}, clear=True):
        assert not validate_region_data()

    # Test with invalid intensity values
    with patch.dict(REGION_CARBON_INTENSITY, {"test": -10}, clear=True):
        assert not validate_region_data()

    # Test with unrealistic values
    with patch.dict(REGION_CARBON_INTENSITY, {"test": 10000}, clear=True):
        assert not validate_region_data()


def test_carbon_data_thread_safety():
    """Test thread safety of carbon data access."""
    import threading
    import time

    results = []

    def access_data():
        time.sleep(0.001)  # Small delay to encourage race conditions
        intensity = get_region_intensity("us-east-1")
        results.append(intensity)

    threads = []
    for i in range(10):
        thread = threading.Thread(target=access_data)
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    # All threads should get same result
    assert all(r == REGION_CARBON_INTENSITY["us-east-1"] for r in results)
    assert len(results) == 10


def test_carbon_data_environmental_impact():
    """Test environmental impact calculations for production scenarios."""
    # Test carbon reduction opportunity
    dirty_region = max(REGION_CARBON_INTENSITY.items(), key=lambda x: x[1])
    clean_region = min(REGION_CARBON_INTENSITY.items(), key=lambda x: x[1])

    cost = Decimal("10000")  # Monthly cloud spend
    dirty_footprint = calculate_carbon_footprint(cost, dirty_region[0])
    clean_footprint = calculate_carbon_footprint(cost, clean_region[0])

    # Should show meaningful reduction opportunity
    reduction_percent = (dirty_footprint - clean_footprint) / dirty_footprint * 100
    assert reduction_percent > 20, (
        f"Carbon reduction opportunity too small: {reduction_percent:.1f}%"
    )


def test_carbon_data_error_handling():
    """Test error handling in carbon data operations."""
    # Test invalid cost types
    with pytest.raises((TypeError, InvalidOperation)):
        calculate_carbon_footprint("not_a_decimal", "us-east-1")

    # Test None cost
    with pytest.raises((TypeError, InvalidOperation)):
        calculate_carbon_footprint(None, "us-east-1")

    # Test malformed region data (if functions were to handle it)
    with patch.dict(REGION_CARBON_INTENSITY, {"test": "not_a_number"}):
        # This should not crash the system
        intensity = get_region_intensity("test")
        assert intensity == DEFAULT_CARBON_INTENSITY  # Should fallback gracefully


def test_get_carbon_reduction_opportunity_basic():
    result = get_carbon_reduction_opportunity(Decimal("1000"))
    assert "dirtiest_region" in result
    assert "cleanest_region" in result
    assert result["monthly_reduction_kg"] >= 0
    assert result["cost"] == 1000.0


def test_get_carbon_reduction_opportunity_invalid_cost():
    assert get_carbon_reduction_opportunity("bad") == {"error": "Invalid cost value"}


def test_get_carbon_reduction_opportunity_negative_cost():
    assert get_carbon_reduction_opportunity(Decimal("-1")) == {
        "error": "Cost cannot be negative"
    }


def test_estimate_carbon_for_service_success():
    result = estimate_carbon_for_service("compute", Decimal("250"), "us-east-1")
    assert result["service"] == "compute"
    assert result["region"] == "us-east-1"
    assert result["monthly_cost_usd"] == 250.0
    assert result["monthly_carbon_kg"] > 0
    assert result["annual_carbon_kg"] == pytest.approx(result["monthly_carbon_kg"] * 12)


def test_estimate_carbon_for_service_invalid_cost():
    result = estimate_carbon_for_service("compute", None, "us-east-1")
    assert "error" in result


def test_carbon_data_performance():
    """Test performance characteristics of carbon data operations."""
    import time

    # Test lookup performance
    start_time = time.time()
    for _ in range(1000):
        get_region_intensity("us-east-1")
    end_time = time.time()

    # Should be very fast (< 0.1 seconds for 1000 operations)
    assert end_time - start_time < 0.1, f"Lookup too slow: {end_time - start_time:.3f}s"

    # Test calculation performance
    start_time = time.time()
    for _ in range(1000):
        calculate_carbon_footprint(Decimal("100"), "us-east-1")
    end_time = time.time()

    # Should be fast enough for production use
    assert end_time - start_time < 0.2, (
        f"Calculation too slow: {end_time - start_time:.3f}s"
    )
