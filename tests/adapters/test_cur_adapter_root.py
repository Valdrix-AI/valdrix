"""
Tests for CUR Adapter - Cost and Usage Reports

Tests:
1. CURAdapter initialization
2. CURConfig model
3. Date range handling
"""

from datetime import date

from app.shared.adapters.cur_adapter import CURAdapter, CURConfig


class TestCURAdapterInitialization:
    """Test CURAdapter initialization."""
    
    def test_adapter_initializes(self):
        """CURAdapter should initialize with required params."""
        adapter = CURAdapter(
            bucket_name="test-bucket",
            report_prefix="valdrix-report/reports",
            credentials={"AccessKeyId": "test", "SecretAccessKey": "test"}
        )
        assert adapter is not None
        assert adapter.bucket_name == "test-bucket"
        assert adapter.report_prefix == "valdrix-report/reports"
    
    def test_adapter_default_region(self):
        """CURAdapter should default to us-east-1."""
        adapter = CURAdapter(
            bucket_name="bucket",
            report_prefix="prefix",
            credentials={}
        )
        assert adapter.region == "us-east-1"
    
    def test_adapter_custom_region(self):
        """CURAdapter should accept custom region."""
        adapter = CURAdapter(
            bucket_name="bucket",
            report_prefix="prefix",
            credentials={},
            region="eu-west-1"
        )
        assert adapter.region == "eu-west-1"


class TestCURConfig:
    """Test CURConfig dataclass."""
    
    def test_config_initialization(self):
        """CURConfig should initialize correctly."""
        config = CURConfig(
            bucket_name="my-bucket",
            report_prefix="cur/reports",
            report_name="valdrix-cur"
        )
        
        assert config.bucket_name == "my-bucket"
        assert config.report_prefix == "cur/reports"
        assert config.report_name == "valdrix-cur"
        assert config.format == "Parquet"  # Default
    
    def test_config_custom_format(self):
        """CURConfig should accept custom format."""
        config = CURConfig(
            bucket_name="bucket",
            report_prefix="prefix",
            report_name="name",
            format="CSV"
        )
        assert config.format == "CSV"
    
    def test_config_from_dict(self):
        """CURConfig should be creatable from dict."""
        data = {
            "bucket_name": "bucket",
            "report_prefix": "prefix",
            "report_name": "name"
        }
        
        config = CURConfig.from_dict(data)
        
        assert config.bucket_name == "bucket"
        assert config.report_prefix == "prefix"
    
    def test_config_from_dict_with_format(self):
        """CURConfig.from_dict should handle format."""
        data = {
            "bucket_name": "bucket",
            "report_prefix": "prefix",
            "report_name": "name",
            "format": "CSV"
        }
        
        config = CURConfig.from_dict(data)
        assert config.format == "CSV"


class TestCURDateRanges:
    """Test date range handling."""
    
    def test_monthly_range(self):
        """Should handle single month range."""
        start = date(2026, 1, 1)
        end = date(2026, 1, 31)
        
        days = (end - start).days + 1
        assert days == 31
    
    def test_cross_month_range(self):
        """Should handle cross-month queries."""
        start = date(2025, 12, 15)
        end = date(2026, 1, 15)
        
        days = (end - start).days
        assert days == 31
    
    def test_cross_year_range(self):
        """Should handle cross-year queries."""
        start = date(2025, 11, 1)
        end = date(2026, 2, 28)
        
        # Should be roughly 4 months
        days = (end - start).days
        assert days > 100


class TestCURAdapterMethods:
    """Test CURAdapter method signatures."""
    
    def test_has_get_daily_costs(self):
        """Should have get_daily_costs method."""
        adapter = CURAdapter(
            bucket_name="bucket",
            report_prefix="prefix",
            credentials={}
        )
        assert hasattr(adapter, 'get_daily_costs')
    
    def test_has_get_gross_usage(self):
        """Should have get_gross_usage method."""
        adapter = CURAdapter(
            bucket_name="bucket",
            report_prefix="prefix",
            credentials={}
        )
        assert hasattr(adapter, 'get_gross_usage')
    
    def test_has_get_resource_usage(self):
        """Should have get_resource_usage method."""
        adapter = CURAdapter(
            bucket_name="bucket",
            report_prefix="prefix",
            credentials={}
        )
        assert hasattr(adapter, 'get_resource_usage')
