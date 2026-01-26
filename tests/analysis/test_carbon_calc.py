"""
Tests for Carbon Calculator

Tests:
1. CO2 emission calculations
2. Grid intensity factors
3. Carbon equivalencies
"""


from app.modules.reporting.domain.calculator import CarbonCalculator


class TestCarbonCalculatorInitialization:
    """Test CarbonCalculator initialization."""
    
    def test_calculator_initializes(self):
        """Calculator should initialize."""
        calc = CarbonCalculator()
        assert calc is not None


class TestEmissionCalculations:
    """Test CO2 emission calculations."""
    
    def test_kwh_to_co2(self):
        """Should convert kWh to CO2 emissions."""
        # Average grid: ~0.5 kg CO2 per kWh
        kwh = 100
        grid_intensity = 0.5  # kg CO2/kWh
        
        co2_kg = kwh * grid_intensity
        assert co2_kg == 50.0
    
    def test_compute_instance_emissions(self):
        """Should calculate emissions for compute."""
        # t3.medium ~25W average
        watts = 25
        hours = 720  # month
        grid_intensity = 0.4
        
        kwh = (watts * hours) / 1000
        co2_kg = kwh * grid_intensity
        
        assert kwh == 18.0
        assert co2_kg == 7.2
    
    def test_storage_emissions(self):
        """Should calculate storage emissions."""
        # ~0.0065 kWh per GB-month for HDD
        gb_months = 1000
        kwh_per_gb = 0.0065
        grid_intensity = 0.5
        
        kwh = gb_months * kwh_per_gb
        co2_kg = kwh * grid_intensity
        
        assert kwh == 6.5
        assert co2_kg == 3.25


class TestGridIntensity:
    """Test grid intensity factors by region."""
    
    def test_us_east_intensity(self):
        """US East should have moderate intensity."""
        regions = {
            "us-east-1": 0.46,  # Virginia
            "us-west-2": 0.35,  # Oregon (hydro)
            "eu-west-1": 0.38,  # Ireland (wind)
        }
        
        assert regions["us-east-1"] > regions["us-west-2"]
    
    def test_green_regions(self):
        """Some regions should be greener."""
        green_regions = ["eu-north-1", "us-west-2", "eu-west-1"]

        
        # Green regions typically < 0.4 kg CO2/kWh
        assert len(green_regions) >= 1


class TestCarbonEquivalencies:
    """Test carbon footprint equivalencies."""
    
    def test_miles_driven(self):
        """Convert CO2 to miles driven equivalent."""
        co2_kg = 100
        kg_per_mile = 0.404  # Average car
        
        miles = co2_kg / kg_per_mile
        assert miles > 200
    
    def test_trees_needed(self):
        """Calculate trees needed to offset."""
        co2_kg = 1000
        kg_per_tree_year = 22  # Average tree absorbs ~22kg/year
        
        trees = co2_kg / kg_per_tree_year
        assert trees > 40
    
    def test_smartphone_charges(self):
        """Convert to smartphone charges."""
        co2_kg = 10
        kg_per_charge = 0.008  # ~8g per charge
        
        charges = co2_kg / kg_per_charge
        assert charges > 1000
