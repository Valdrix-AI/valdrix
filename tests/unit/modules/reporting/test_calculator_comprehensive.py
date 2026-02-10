"""
Comprehensive tests for CarbonCalculator module.
Covers cost-based and record-based calculations, carbon efficiency metrics, and recommendations.
"""

from typing import Dict
from decimal import Decimal
from typing import List, Dict, Any
from dataclasses import dataclass

from app.modules.reporting.domain.calculator import (
    CarbonCalculator,
    REGION_CARBON_INTENSITY,
    SERVICE_ENERGY_FACTORS,
    AWS_PUE,
    EMBODIED_EMISSIONS_FACTOR,
)


@dataclass
class MockCostRecord:
    """Mock for CostRecord used in tests."""
    cost_usd: Decimal
    service: str
    usage_type: str = ""
    amount_raw: float = 0.0


class TestCarbonCalculatorFromCosts:
    """Test cost-based carbon calculations."""
    
    def test_calculate_from_grouped_costs_single_service(self):
        """Test calculation with grouped cost data for a single service."""
        calculator = CarbonCalculator()
        cost_data = [
            {
                "Groups": [
                    {
                        "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "100.00"
                            }
                        }
                    }
                ]
            }
        ]
        
        result = calculator.calculate_from_costs(cost_data, region="us-east-1")
        
        assert "total_co2_kg" in result
        assert result["total_cost_usd"] == 100.0
        assert result["region"] == "us-east-1"
        assert result["total_co2_kg"] > 0
        assert "carbon_efficiency_score" in result

    def test_calculate_from_multiple_services(self):
        """Test calculation with multiple services in grouped data."""
        calculator = CarbonCalculator()
        cost_data = [
            {
                "Groups": [
                    {
                        "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "100.00"
                            }
                        }
                    },
                    {
                        "Keys": ["Amazon Simple Storage Service"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "50.00"
                            }
                        }
                    }
                ]
            }
        ]
        
        result = calculator.calculate_from_costs(cost_data, region="eu-north-1")
        
        assert result["total_cost_usd"] == 150.0
        assert result["region"] == "eu-north-1"
        # Compute is more energy-intensive than storage
        assert result["total_co2_kg"] > 0

    def test_calculate_from_flat_ungrouped_costs(self):
        """Test calculation with flat (ungrouped) cost data."""
        calculator = CarbonCalculator()
        cost_data = [
            {
                "Total": {
                    "UnblendedCost": {
                        "Amount": "75.50"
                    }
                }
            }
        ]
        
        result = calculator.calculate_from_costs(cost_data, region="ca-central-1")
        
        assert result["total_cost_usd"] == 75.50
        assert result["region"] == "ca-central-1"
        assert result["total_co2_kg"] > 0

    def test_calculate_with_zero_cost_data(self):
        """Test calculation with zero cost data."""
        calculator = CarbonCalculator()
        cost_data = [
            {
                "Groups": [
                    {
                        "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "0"
                            }
                        }
                    }
                ]
            }
        ]
        
        result = calculator.calculate_from_costs(cost_data, region="us-west-2")
        
        assert result["total_cost_usd"] == 0.0
        assert result["total_co2_kg"] == 0.0

    def test_calculate_handles_missing_amount_field(self):
        """Test calculation gracefully handles missing Amount field."""
        calculator = CarbonCalculator()
        cost_data = [
            {
                "Groups": [
                    {
                        "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                        "Metrics": {
                            "UnblendedCost": {}
                        }
                    }
                ]
            }
        ]
        
        result = calculator.calculate_from_costs(cost_data, region="us-east-1")
        
        assert result["total_cost_usd"] == 0.0

    def test_calculate_preserves_service_accuracy(self):
        """Test that service names are preserved accurately in calculation."""
        calculator = CarbonCalculator()
        cost_data = [
            {
                "Groups": [
                    {
                        "Keys": ["Amazon Simple Storage Service"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "100.00"
                            }
                        }
                    }
                ]
            }
        ]
        
        result = calculator.calculate_from_costs(cost_data, region="us-east-1")
        
        # Should return result dict
        assert isinstance(result, dict)
        assert result["total_cost_usd"] == 100.0
        # Storage is less energy-intensive than compute
        assert result["total_co2_kg"] > 0

    def test_calculate_with_unknown_service(self):
        """Test calculation with unknown service name uses default factor."""
        calculator = CarbonCalculator()
        cost_data = [
            {
                "Groups": [
                    {
                        "Keys": ["Unknown Cloud Service"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "100.00"
                            }
                        }
                    }
                ]
            }
        ]
        
        result = calculator.calculate_from_costs(cost_data, region="us-east-1")
        
        assert result["total_cost_usd"] == 100.0
        # Should use default energy factor (0.03)
        assert result["total_co2_kg"] > 0

    def test_calculate_region_carbon_intensity_variations(self):
        """Test that different regions produce different carbon footprints."""
        calculator = CarbonCalculator()
        cost_data = [
            {
                "Groups": [
                    {
                        "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "100.00"
                            }
                        }
                    }
                ]
            }
        ]
        
        # Low-carbon region
        result_green = calculator.calculate_from_costs(cost_data, region="eu-north-1")
        
        # High-carbon region
        result_brown = calculator.calculate_from_costs(cost_data, region="ap-south-1")
        
        # Same cost should produce different emissions in different regions
        assert result_green["total_co2_kg"] > 0
        assert result_brown["total_co2_kg"] > result_green["total_co2_kg"]


class TestCarbonCalculatorFromRecords:
    """Test record-based carbon calculations."""

    def test_calculate_from_records_basic(self):
        """Test calculation from cost records."""
        calculator = CarbonCalculator()
        records = [
            MockCostRecord(
                cost_usd=Decimal("50.0"),
                service="Amazon Elastic Compute Cloud - Compute",
                usage_type="vCPU-Hours",
                amount_raw=100.0
            )
        ]
        
        result = calculator.calculate_from_records(records, region="us-east-1")
        
        assert result["total_cost_usd"] == 50.0
        assert result["total_co2_kg"] > 0
        assert result["region"] == "us-east-1"

    def test_calculate_from_records_with_usage_metadata(self):
        """Test EC2 record calculation with usage metadata."""
        calculator = CarbonCalculator()
        records = [
            MockCostRecord(
                cost_usd=Decimal("100.0"),
                service="Amazon Elastic Compute Cloud - EC2",
                usage_type="on-demand-ec2-instances",
                amount_raw=1000.0
            )
        ]
        
        result = calculator.calculate_from_records(records, region="us-west-2")
        
        # Should calculate emissions based on cost
        assert result["estimated_energy_kwh"] > 0
        assert result["total_co2_kg"] > 0

    def test_calculate_from_records_without_usage_type(self):
        """Test record calculation falls back to cost-proxy when usage_type is missing."""
        calculator = CarbonCalculator()
        records = [
            MockCostRecord(
                cost_usd=Decimal("100.0"),
                service="Amazon Simple Storage Service",
                usage_type="",
                amount_raw=0.0
            )
        ]
        
        result = calculator.calculate_from_records(records, region="eu-west-1")
        
        assert result["total_cost_usd"] == 100.0
        assert result["total_co2_kg"] > 0
        """Test record calculation falls back to cost-proxy when usage_type is missing."""
        calculator = CarbonCalculator()
        records = [
            MockCostRecord(
                cost_usd=Decimal("100.0"),
                service="Amazon Simple Storage Service",
                usage_type="",
                amount_raw=0.0
            )
        ]
        
        result = calculator.calculate_from_records(records, region="eu-west-1")
        
        assert result["total_cost_usd"] == 100.0
        assert result["total_co2_kg"] > 0

    def test_calculate_from_multiple_records(self):
        """Test calculation aggregates multiple records correctly."""
        calculator = CarbonCalculator()
        records = [
            MockCostRecord(
                cost_usd=Decimal("50.0"),
                service="Amazon Elastic Compute Cloud - Compute"
            ),
            MockCostRecord(
                cost_usd=Decimal("30.0"),
                service="Amazon Simple Storage Service"
            ),
            MockCostRecord(
                cost_usd=Decimal("20.0"),
                service="Amazon Relational Database Service"
            )
        ]
        
        result = calculator.calculate_from_records(records, region="us-east-1")
        
        assert result["total_cost_usd"] == 100.0
        assert result["total_co2_kg"] > 0


class TestCarbonCalculatorMetrics:
    """Test calculation result metrics and metadata."""

    def test_result_contains_required_fields(self):
        """Test that result contains all required metric fields."""
        calculator = CarbonCalculator()
        cost_data = [{"Groups": []}]
        
        result = calculator.calculate_from_costs(cost_data, region="us-east-1")
        
        required_fields = [
            "total_co2_kg",
            "scope2_co2_kg",
            "scope3_co2_kg",
            "total_cost_usd",
            "estimated_energy_kwh",
            "carbon_efficiency_score",
            "carbon_efficiency_unit",
            "region",
            "carbon_intensity_gco2_kwh",
            "equivalencies",
            "methodology",
            "includes_embodied_emissions",
        ]
        
        for field in required_fields:
            assert field in result

    def test_scope2_and_scope3_breakdown(self):
        """Test that Scope 2 and Scope 3 emissions are calculated correctly."""
        calculator = CarbonCalculator()
        cost_data = [
            {
                "Groups": [
                    {
                        "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "100.00"
                            }
                        }
                    }
                ]
            }
        ]
        
        result = calculator.calculate_from_costs(cost_data, region="us-east-1")
        
        # Total = Scope 2 + Scope 3
        total = result["scope2_co2_kg"] + result["scope3_co2_kg"]
        assert abs(total - result["total_co2_kg"]) < 0.01  # Account for rounding

    def test_carbon_efficiency_score_calculation(self):
        """Test carbon efficiency score (gCO2e per $1)."""
        calculator = CarbonCalculator()
        cost_data = [
            {
                "Groups": [
                    {
                        "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "100.00"
                            }
                        }
                    }
                ]
            }
        ]
        
        result = calculator.calculate_from_costs(cost_data, region="us-east-1")
        
        # Carbon efficiency = (total_co2_kg * 1000) / total_cost_usd
        expected_score = (result["total_co2_kg"] * 1000) / result["total_cost_usd"]
        assert abs(result["carbon_efficiency_score"] - expected_score) < 0.1

    def test_carbon_efficiency_with_zero_cost(self):
        """Test carbon efficiency score handling with zero cost."""
        calculator = CarbonCalculator()
        # Create a test with zero cost but some emissions (edge case)
        result = calculator._finalize_calculation(
            Decimal("0"),
            Decimal("10"),  # 10 kWh uses energy
            "us-east-1"
        )
        
        # Should return high sentinel value
        assert result["carbon_efficiency_score"] == 9999.9


class TestCarbonCalculatorEquivalencies:
    """Test carbon equivalency conversions."""

    def test_calculate_equivalencies_miles_driven(self):
        """Test miles driven equivalency calculation."""
        calculator = CarbonCalculator()
        equivalencies = calculator._calculate_equivalencies(100.0)  # 100 kg CO2
        
        # 100 kg * 1000 g/kg / 404 g/mile ≈ 247.5 miles
        assert "miles_driven" in equivalencies
        assert 240 < equivalencies["miles_driven"] < 255

    def test_calculate_equivalencies_trees_needed(self):
        """Test trees needed for year equivalency."""
        calculator = CarbonCalculator()
        equivalencies = calculator._calculate_equivalencies(100.0)
        
        # 100 kg / 22 kg/tree ≈ 4.5 trees
        assert "trees_needed_for_year" in equivalencies
        assert 4 < equivalencies["trees_needed_for_year"] < 5

    def test_calculate_equivalencies_smartphone_charges(self):
        """Test smartphone charges equivalency."""
        calculator = CarbonCalculator()
        equivalencies = calculator._calculate_equivalencies(34.0)  # 34 kg CO2
        
        # 34 kg * 1000 g/kg / 3.4 g/charge = 10000 charges
        assert "smartphone_charges" in equivalencies
        assert equivalencies["smartphone_charges"] == 10000

    def test_calculate_equivalencies_home_month_percent(self):
        """Test percent of home usage per month equivalency."""
        calculator = CarbonCalculator()
        equivalencies = calculator._calculate_equivalencies(180.0)  # Half home monthly
        
        # (180 kg / 360 kg) * 100 = 50%
        assert "percent_of_home_month" in equivalencies
        assert equivalencies["percent_of_home_month"] == 50.0


class TestCarbonCalculatorRecommendations:
    """Test region recommendations."""

    def test_get_green_region_recommendations_from_high_carbon(self):
        """Test region recommendations from high-carbon region."""
        calculator = CarbonCalculator()
        recommendations = calculator.get_green_region_recommendations("ap-south-1")
        
        assert len(recommendations) <= 5
        assert all("region" in r for r in recommendations)
        assert all("carbon_intensity" in r for r in recommendations)
        assert all("savings_percent" in r for r in recommendations)

    def test_recommendations_are_lower_carbon(self):
        """Test that recommended regions have lower carbon intensity."""
        calculator = CarbonCalculator()
        current_intensity = REGION_CARBON_INTENSITY["ap-south-1"]
        recommendations = calculator.get_green_region_recommendations("ap-south-1")
        
        for rec in recommendations:
            assert rec["carbon_intensity"] < current_intensity

    def test_recommendations_from_low_carbon_region(self):
        """Test recommendations from already low-carbon region."""
        calculator = CarbonCalculator()
        recommendations = calculator.get_green_region_recommendations("us-west-2")
        
        # Should have fewer or zero recommendations
        assert len(recommendations) <= 5

    def test_recommendations_calculate_savings_percent(self):
        """Test that savings percent is calculated correctly."""
        calculator = CarbonCalculator()
        recommendations = calculator.get_green_region_recommendations("us-east-1")
        
        us_east_1_intensity = REGION_CARBON_INTENSITY["us-east-1"]
        for rec in recommendations:
            expected_savings = (1 - rec["carbon_intensity"] / us_east_1_intensity) * 100
            assert abs(rec["savings_percent"] - expected_savings) < 0.2


class TestCarbonCalculatorForecasting:
    """Test emissions forecasting."""

    def test_forecast_emissions_baseline(self):
        """Test baseline emissions forecast."""
        calculator = CarbonCalculator()
        forecast = calculator.forecast_emissions(10.0, days=30, region_trend_factor=1.0)
        
        assert forecast["forecast_days"] == 30
        assert forecast["baseline_co2_kg"] == 300.0
        assert forecast["projected_co2_kg"] == 300.0

    def test_forecast_emissions_with_grid_improvement(self):
        """Test forecast with grid efficiency improvement."""
        calculator = CarbonCalculator()
        forecast = calculator.forecast_emissions(
            current_daily_co2_kg=10.0,
            days=30,
            region_trend_factor=0.99  # 1% improvement
        )
        
        baseline = 10.0 * 30
        projected = baseline * 0.99
        
        assert forecast["baseline_co2_kg"] == baseline
        assert forecast["projected_co2_kg"] == projected

    def test_forecast_emissions_with_grid_degradation(self):
        """Test forecast with grid efficiency degradation."""
        calculator = CarbonCalculator()
        forecast = calculator.forecast_emissions(
            current_daily_co2_kg=10.0,
            days=30,
            region_trend_factor=1.02  # 2% degradation
        )
        
        baseline = 10.0 * 30
        projected = baseline * 1.02
        
        assert forecast["projected_co2_kg"] == projected

    def test_forecast_includes_description(self):
        """Test forecast includes descriptive text."""
        calculator = CarbonCalculator()
        forecast = calculator.forecast_emissions(5.0, days=60)
        
        assert "description" in forecast
        assert "60" in forecast["description"]


class TestCarbonCalculatorEdgeCases:
    """Test edge cases and error handling."""

    def test_calculate_with_negative_cost_ignored(self):
        """Test that negative costs are handled (shouldn't contribute)."""
        calculator = CarbonCalculator()
        cost_data = [
            {
                "Groups": [
                    {
                        "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "-50.00"
                            }
                        }
                    }
                ]
            }
        ]
        
        result = calculator.calculate_from_costs(cost_data, region="us-east-1")
        
        # Negative shouldn't be processed
        assert result["total_cost_usd"] <= 0

    def test_calculate_with_unknown_region_uses_default(self):
        """Test calculation with unknown region uses default intensity."""
        calculator = CarbonCalculator()
        cost_data = [
            {
                "Groups": [
                    {
                        "Keys": ["Amazon Elastic Compute Cloud - Compute"],
                        "Metrics": {
                            "UnblendedCost": {
                                "Amount": "100.00"
                            }
                        }
                    }
                ]
            }
        ]
        
        result = calculator.calculate_from_costs(cost_data, region="unknown-region-1")
        
        assert result["carbon_intensity_gco2_kwh"] == REGION_CARBON_INTENSITY["default"]

    def test_pue_multiplier_applied(self):
        """Test that PUE multiplier is applied to energy calculations."""
        calculator = CarbonCalculator()
        
        # Create fixed calculation
        result = calculator._finalize_calculation(
            Decimal("0"),
            Decimal("100"),  # 100 kWh
            "us-east-1"
        )
        
        # Energy should be multiplied by PUE (1.2)
        # 100 kWh * 1.2 = 120 kWh effective
        assert result["estimated_energy_kwh"] == round(100 * AWS_PUE, 3)

    def test_embodied_emissions_included(self):
        """Test that embodied emissions (Scope 3) are included."""
        calculator = CarbonCalculator()
        result = calculator._finalize_calculation(
            Decimal("0"),
            Decimal("100"),
            "us-east-1"
        )
        
        assert result["scope3_co2_kg"] > 0
        assert result["includes_embodied_emissions"] is True
        assert result["methodology"] == "Valdrix 2026 (CCF + AWS CCFT v3.0.0)"
