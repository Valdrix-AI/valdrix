import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock
from app.shared.adapters.azure import AzureAdapter
from app.models.azure_connection import AzureConnection


class TestAzureAdapterDateParsing:
    def test_parse_row_yyyymmdd_int(self):
        """Test parsing integer YYYYMMDD."""
        adapter = AzureAdapter(MagicMock(spec=AzureConnection))
        # row: [PreTaxCost, ServiceName, ResourceLocation, ChargeType, UsageDate]
        row = [10.0, "Virtual Machines", "US East", "Usage", 20231025]

        result = adapter._parse_row(row, "ActualCost")
        assert result["timestamp"] == datetime(2023, 10, 25, tzinfo=timezone.utc)

    def test_parse_row_yyyymmdd_string(self):
        """Test parsing string 'YYYYMMDD'."""
        adapter = AzureAdapter(MagicMock(spec=AzureConnection))
        row = [10.0, "Virtual Machines", "US East", "Usage", "20231025"]

        result = adapter._parse_row(row, "ActualCost")
        assert result["timestamp"] == datetime(2023, 10, 25, tzinfo=timezone.utc)

    def test_parse_row_iso_string(self):
        """Test parsing ISO string constraint (if we support it)."""
        # Current implementation likely fails this. We will check if it fails.
        # If it fails, we fix the code.
        adapter = AzureAdapter(MagicMock(spec=AzureConnection))
        row = [10.0, "Virtual Machines", "US East", "Usage", "2023-10-25"]

        try:
            result = adapter._parse_row(row, "ActualCost")
            assert result["timestamp"] == datetime(2023, 10, 25, tzinfo=timezone.utc)
        except ValueError:
            pytest.fail("Failed to parse ISO format date")
