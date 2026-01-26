"""
Tests for Carbon Calculator service.

Tests cover:
- Carbon calculation for different AWS regions
- Equivalency calculations (trees, miles, etc.)
- Edge cases (zero cost, unknown regions)
"""
from app.modules.reporting.domain.calculator import (
    CarbonCalculator,
    REGION_CARBON_INTENSITY,
)


class TestCarbonCalculation:
    """Tests for calculate_from_costs method."""
    
    def test_calculate_from_costs_basic(self):
        """Test basic carbon calculation with sample cost data."""
        calculator = CarbonCalculator()
        
        cost_data = [
            {
                "TimePeriod": {"Start": "2026-01-01"},
                "Total": {
                    "UnblendedCost": {"Amount": "100.00"}
                }
            }
        ]
        
        result = calculator.calculate_from_costs(cost_data, region="us-east-1")
        
        assert "total_co2_kg" in result
        assert "total_cost_usd" in result
        assert "equivalencies" in result
        assert result["total_cost_usd"] == 100.00
        assert result["total_co2_kg"] > 0
    
    def test_low_carbon_region(self):
        """Test that low carbon regions produce less CO2."""
        calculator = CarbonCalculator()
        
        cost_data = [
            {"Total": {"UnblendedCost": {"Amount": "100.00"}}}
        ]
        
        # Oregon (us-west-2) has very low carbon intensity
        result_oregon = calculator.calculate_from_costs(cost_data, region="us-west-2")
        
        # Virginia (us-east-1) has higher carbon intensity
        result_virginia = calculator.calculate_from_costs(cost_data, region="us-east-1")
        
        # Oregon should produce much less CO2
        assert result_oregon["total_co2_kg"] < result_virginia["total_co2_kg"]
    
    def test_high_carbon_region(self):
        """Test that high carbon regions produce more CO2."""
        calculator = CarbonCalculator()
        
        cost_data = [
            {"Total": {"UnblendedCost": {"Amount": "100.00"}}}
        ]
        
        # Mumbai (ap-south-1) has high carbon intensity
        result_mumbai = calculator.calculate_from_costs(cost_data, region="ap-south-1")
        
        # Stockholm (eu-north-1) has low carbon intensity
        result_stockholm = calculator.calculate_from_costs(cost_data, region="eu-north-1")
        
        # Mumbai should produce much more CO2
        assert result_mumbai["total_co2_kg"] > result_stockholm["total_co2_kg"]
    
    def test_zero_cost_returns_zero_carbon(self):
        """Test that zero cost produces zero carbon."""
        calculator = CarbonCalculator()
        
        cost_data = [
            {"Total": {"UnblendedCost": {"Amount": "0.00"}}}
        ]
        
        result = calculator.calculate_from_costs(cost_data)
        
        assert result["total_co2_kg"] == 0
        assert result["total_cost_usd"] == 0
    
    def test_empty_cost_data(self):
        """Test handling of empty cost data."""
        calculator = CarbonCalculator()
        
        result = calculator.calculate_from_costs([])
        
        assert result["total_co2_kg"] == 0
        assert result["total_cost_usd"] == 0
    
    def test_unknown_region_uses_default(self):
        """Test that unknown regions use default carbon intensity."""
        calculator = CarbonCalculator()
        
        cost_data = [
            {"Total": {"UnblendedCost": {"Amount": "100.00"}}}
        ]
        
        # Unknown region should not crash
        result = calculator.calculate_from_costs(cost_data, region="mars-west-1")
        
        assert result["total_co2_kg"] > 0
        assert result["carbon_intensity_gco2_kwh"] == REGION_CARBON_INTENSITY["default"]


class TestEquivalencies:
    """Tests for equivalency calculations."""
    
    def test_equivalencies_included(self):
        """Test that equivalencies are calculated."""
        calculator = CarbonCalculator()
        
        cost_data = [
            {"Total": {"UnblendedCost": {"Amount": "100.00"}}}
        ]
        
        result = calculator.calculate_from_costs(cost_data)
        
        equivalencies = result["equivalencies"]
        assert "miles_driven" in equivalencies
        assert "trees_needed_for_year" in equivalencies
        assert "smartphone_charges" in equivalencies
        assert "percent_of_home_month" in equivalencies
    
    def test_equivalencies_scale_with_carbon(self):
        """Test that equivalencies scale proportionally with carbon."""
        calculator = CarbonCalculator()
        
        cost_data_small = [
            {"Total": {"UnblendedCost": {"Amount": "10.00"}}}
        ]
        cost_data_large = [
            {"Total": {"UnblendedCost": {"Amount": "100.00"}}}
        ]
        
        result_small = calculator.calculate_from_costs(cost_data_small)
        result_large = calculator.calculate_from_costs(cost_data_large)
        
        # Large cost should have ~10x more miles, trees, etc. (allow variance)
        ratio = result_large["equivalencies"]["miles_driven"] / result_small["equivalencies"]["miles_driven"]
        assert 8 < ratio < 12  # Allow rounding variance


class TestRegionConfiguration:
    """Tests for region configuration."""
    
    def test_all_major_regions_configured(self):
        """Test that major AWS regions have carbon intensity configured."""
        major_regions = [
            "us-east-1", "us-west-2", "eu-west-1", 
            "eu-central-1", "ap-southeast-1", "ap-northeast-1"
        ]
        
        for region in major_regions:
            assert region in REGION_CARBON_INTENSITY
            assert REGION_CARBON_INTENSITY[region] > 0
    
    def test_default_region_configured(self):
        """Test that default fallback is configured."""
        assert "default" in REGION_CARBON_INTENSITY
        assert REGION_CARBON_INTENSITY["default"] > 0
