from app.modules.reporting.domain.calculator import CarbonCalculator, EMBODIED_EMISSIONS_FACTOR, AWS_PUE

def test_scope3_calculation():
    """Verify Scope 3 (Embodied) emissions are correctly added."""
    calculator = CarbonCalculator()
    
    # Mock data: 100 USD spent on EC2 -> implies energy usage
    # From calculator.py: EC2 factor is 0.05 kWh/$
    cost = 100.0
    expected_energy_direct = 100.0 * 0.05 # 5 kWh
    expected_energy_pue = expected_energy_direct * AWS_PUE # 5 * 1.2 = 6 kWh
    
    # Scope 3 = 6 kWh * 0.025 = 0.15 kgCO2e
    expected_scope3 = expected_energy_pue * EMBODIED_EMISSIONS_FACTOR
    
    # Mock input record
    data = [{
        "Groups": [{
            "Keys": ["Amazon Elastic Compute Cloud - Compute"],
            "Metrics": {"UnblendedCost": {"Amount": str(cost)}}
        }]
    }]
    
    result = calculator.calculate_from_costs(data, region="us-east-1")
    
    # Allow small float precision differences
    assert abs(result["scope3_co2_kg"] - expected_scope3) < 0.01
    assert result["includes_embodied_emissions"] is True

def test_carbon_forecasting():
    """Verify forecast logic."""
    calculator = CarbonCalculator()
    daily_co2 = 10.0
    days = 30
    
    forecast = calculator.forecast_emissions(daily_co2, days=days, region_trend_factor=1.0)
    
    assert forecast["baseline_co2_kg"] == 300.0
    assert forecast["projected_co2_kg"] == 300.0 # Factor 1.0
    
    # Test with improvement
    forecast_improved = calculator.forecast_emissions(daily_co2, days=days, region_trend_factor=0.9)
    assert forecast_improved["projected_co2_kg"] == 270.0
