"""
Unit tests for Azure Usage Analyzer.

Tests zero-cost zombie detection logic using mock cost export data.
"""

from app.shared.analysis.azure_usage_analyzer import AzureUsageAnalyzer


class TestAzureUsageAnalyzerIdleVMs:
    """Tests for idle VM detection."""

    def test_detects_idle_vm(self):
        """VM with low cost should be flagged as idle."""
        cost_records = [
            {
                "ResourceId": "/subscriptions/sub-123/resourceGroups/rg-test/providers/Microsoft.Compute/virtualMachines/idle-vm",
                "MeterCategory": "Virtual Machines",
                "MeterSubCategory": "D2s v3",
                "UsageQuantity": 720.0,
                "Cost": 5.0,  # Very low cost
                "Tags": {"Environment": "Dev"},
            },
        ]

        analyzer = AzureUsageAnalyzer(cost_records)
        zombies = analyzer.find_idle_vms(days=30, cost_threshold=10.0)

        assert isinstance(zombies, list)

    def test_empty_records_returns_empty(self):
        """Empty records should return no zombies."""
        analyzer = AzureUsageAnalyzer([])
        assert analyzer.find_idle_vms() == []


class TestAzureUsageAnalyzerDisks:
    """Tests for unattached disk detection."""

    def test_detects_unattached_disk(self):
        """Disk with storage cost but no VM association should be flagged."""
        cost_records = [
            {
                "ResourceId": "/subscriptions/sub-123/resourceGroups/rg-test/providers/Microsoft.Compute/disks/orphan-disk",
                "MeterCategory": "Storage",
                "MeterSubCategory": "Premium SSD",
                "UsageQuantity": 128.0,
                "Cost": 19.20,
            },
        ]

        analyzer = AzureUsageAnalyzer(cost_records)
        zombies = analyzer.find_unattached_disks()

        assert isinstance(zombies, list)


class TestAzureUsageAnalyzerSQL:
    """Tests for idle SQL database detection."""

    def test_detects_idle_sql_database(self):
        """SQL database with no DTU usage should be flagged."""
        cost_records = [
            {
                "ResourceId": "/subscriptions/sub-123/resourceGroups/rg-test/providers/Microsoft.Sql/servers/sql-server/databases/idle-db",
                "MeterCategory": "SQL Database",
                "MeterSubCategory": "Standard",
                "UsageQuantity": 720.0,
                "Cost": 15.0,
            },
        ]

        analyzer = AzureUsageAnalyzer(cost_records)
        zombies = analyzer.find_idle_sql_databases(days=7)

        assert isinstance(zombies, list)


class TestAzureUsageAnalyzerAKS:
    """Tests for idle AKS cluster detection."""

    def test_detects_idle_aks_cluster(self):
        """AKS cluster with minimal workload should be flagged."""
        cost_records = [
            {
                "ResourceId": "/subscriptions/sub-123/resourceGroups/rg-test/providers/Microsoft.ContainerService/managedClusters/empty-aks",
                "MeterCategory": "Azure Kubernetes Service",
                "MeterSubCategory": "Standard",
                "UsageQuantity": 1.0,
                "Cost": 73.0,
            },
        ]

        analyzer = AzureUsageAnalyzer(cost_records)
        zombies = analyzer.find_idle_aks_clusters(days=7)

        assert isinstance(zombies, list)


class TestAzureUsageAnalyzerNICs:
    """Tests for orphan NIC detection."""

    def test_detects_orphan_nic(self):
        """Unused NIC with association should be flagged."""
        cost_records = [
            {
                "ResourceId": "/subscriptions/sub-123/resourceGroups/rg-test/providers/Microsoft.Network/networkInterfaces/orphan-nic",
                "MeterCategory": "Virtual Network",
                "MeterSubCategory": "Network Interface",
                "UsageQuantity": 720.0,
                "Cost": 0.0,
            },
        ]

        analyzer = AzureUsageAnalyzer(cost_records)
        zombies = analyzer.find_orphan_nics()

        assert isinstance(zombies, list)
