"""
Tests for gcp_usage_analyzer.py - GCP BigQuery billing export analysis for resource utilization.
"""

from app.shared.analysis.gcp_usage_analyzer import GCPUsageAnalyzer


class TestGCPUsageAnalyzer:
    """Test suite for GCPUsageAnalyzer class."""

    def test_init_with_records(self):
        """Test initialization with GCP billing records."""
        records = [
            {
                "resource_id": "projects/my-project/zones/us-central1-a/instances/vm-1",
                "service": "Compute Engine",
                "sku_description": "N1 Predefined Instance Core running in Americas",
                "usage_amount": "168.0",
                "usage_unit": "seconds",
                "cost": "0.05",
                "currency": "USD",
            }
        ]

        analyzer = GCPUsageAnalyzer(records)
        assert analyzer.records == records
        assert hasattr(analyzer, "_resource_costs")
        assert isinstance(analyzer._resource_costs, dict)

    def test_group_by_resource(self):
        """Test grouping records by resource ID."""
        records = [
            {
                "resource_id": "projects/my-project/zones/us-central1-a/instances/vm-1",
                "cost": "10.50",
            },
            {
                "resource_id": "projects/my-project/zones/us-central1-a/instances/vm-1",
                "cost": "15.75",
            },
            {"resource_id": "projects/my-project/buckets/my-bucket", "cost": "5.00"},
        ]

        analyzer = GCPUsageAnalyzer(records)
        grouped = analyzer._resource_costs

        assert "projects/my-project/zones/us-central1-a/instances/vm-1" in grouped
        assert "projects/my-project/buckets/my-bucket" in grouped
        assert (
            len(grouped["projects/my-project/zones/us-central1-a/instances/vm-1"]) == 2
        )
        assert len(grouped["projects/my-project/buckets/my-bucket"]) == 1

    def test_find_idle_vms_no_vms(self):
        """Test finding idle VMs when no VM resources in data."""
        records = [
            {
                "resource_id": "projects/my-project/buckets/my-bucket",
                "service": "Cloud Storage",
                "cost": "5.00",
            }
        ]

        analyzer = GCPUsageAnalyzer(records)
        result = analyzer.find_idle_vms(days=7)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_find_idle_vms_with_low_usage(self):
        """Test finding idle VMs with low CPU usage."""
        records = [
            {
                "resource_id": "projects/my-project/zones/us-central1-a/instances/vm-1",
                "service": "Compute Engine",
                "sku_description": "N1 Predefined Instance Core running in Americas",
                "usage_amount": "2.4",  # 2.4 hours total for 7 days = 0.34 hours/day (low usage)
                "usage_unit": "seconds",
                "cost": "15.00",
            }
        ]

        analyzer = GCPUsageAnalyzer(records)
        result = analyzer.find_idle_vms(days=7, cpu_threshold=5.0)

        assert isinstance(result, list)
        assert len(result) == 1

        vm = result[0]
        assert (
            vm["resource_id"]
            == "projects/my-project/zones/us-central1-a/instances/vm-1"
        )
        assert vm["resource_type"] == "Compute Engine VM"
        assert vm["recommendation"] == "Stop or delete idle VM"

    def test_find_idle_vms_with_high_usage(self):
        """Test that VMs with high CPU usage are not flagged as idle."""
        records = [
            {
                "resource_id": "projects/my-project/zones/us-central1-a/instances/vm-1",
                "service": "Compute Engine",
                "sku_description": "N1 Predefined Instance Core running in Americas",
                "usage_amount": "60480.0",  # 1008 hours = 144 hours/day (high usage)
                "usage_unit": "seconds",
                "cost": "50.00",
            }
        ]

        analyzer = GCPUsageAnalyzer(records)
        result = analyzer.find_idle_vms(days=7, cpu_threshold=5.0)

        assert isinstance(result, list)
        assert len(result) == 0  # Should not flag high usage VMs

    def test_find_idle_vms_multiple_vms(self):
        """Test finding idle VMs with multiple VMs in data."""
        records = [
            # Idle VM
            {
                "resource_id": "projects/my-project/zones/us-central1-a/instances/vm-1",
                "service": "Compute Engine",
                "sku_description": "N1 Predefined Instance Core running in Americas",
                "usage_amount": "2.4",  # Low usage - should be flagged as idle
                "usage_unit": "seconds",
                "cost": "15.00",
            },
            # Active VM
            {
                "resource_id": "projects/my-project/zones/us-central1-a/instances/vm-2",
                "service": "Compute Engine",
                "sku_description": "N1 Predefined Instance Core running in Americas",
                "usage_amount": "60480.0",  # High usage
                "usage_unit": "seconds",
                "cost": "50.00",
            },
        ]

        analyzer = GCPUsageAnalyzer(records)
        result = analyzer.find_idle_vms(days=7, cpu_threshold=5.0)

        assert isinstance(result, list)
        assert len(result) == 1  # Only the idle VM

        vm = result[0]
        assert (
            vm["resource_id"]
            == "projects/my-project/zones/us-central1-a/instances/vm-1"
        )

    def test_find_idle_cloud_sql_no_databases(self):
        """Test finding idle Cloud SQL databases when no SQL resources in data."""
        records = [
            {
                "resource_id": "projects/my-project/buckets/my-bucket",
                "service": "Cloud Storage",
                "cost": "5.00",
            }
        ]

        analyzer = GCPUsageAnalyzer(records)
        result = analyzer.find_idle_cloud_sql(days=7)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_find_idle_cloud_sql_with_low_usage(self):
        """Test finding idle Cloud SQL databases with low usage."""
        records = [
            {
                "resource_id": "projects/my-project/instances/my-sql-instance",
                "service": "Cloud SQL",
                "sku_description": "Cloud SQL for MySQL: db-f1-micro",
                "usage_amount": "3024.0",  # Low usage
                "usage_unit": "seconds",
                "cost": "10.00",
            }
        ]

        analyzer = GCPUsageAnalyzer(records)
        result = analyzer.find_idle_cloud_sql(days=7)

        assert isinstance(result, list)
        assert len(result) == 1

        db = result[0]
        assert db["resource_id"] == "projects/my-project/instances/my-sql-instance"
        assert db["resource_type"] == "Cloud SQL"
        assert db["recommendation"] == "Stop instance or delete if not needed"

    def test_find_empty_gke_clusters_no_clusters(self):
        """Test finding empty GKE clusters when no GKE resources in data."""
        records = [
            {
                "resource_id": "projects/my-project/buckets/my-bucket",
                "service": "Cloud Storage",
                "cost": "5.00",
            }
        ]

        analyzer = GCPUsageAnalyzer(records)
        result = analyzer.find_empty_gke_clusters(days=7)

        assert isinstance(result, list)
        assert len(result) == 0

    def test_find_empty_gke_clusters_with_no_nodes(self):
        """Test finding empty GKE clusters with no node costs."""
        records = [
            {
                "resource_id": "projects/my-project/clusters/my-cluster",
                "service": "Kubernetes Engine",
                "sku_description": "Kubernetes Engine Cluster Management Fee",
                "usage_amount": "1008.0",  # Control plane usage
                "usage_unit": "seconds",
                "cost": "25.00",
            }
            # No node cost records
        ]

        analyzer = GCPUsageAnalyzer(records)
        result = analyzer.find_empty_gke_clusters(days=7)

        assert isinstance(result, list)
        assert len(result) == 1

        cluster = result[0]
        assert cluster["resource_id"] == "projects/my-project/clusters/my-cluster"
        assert cluster["resource_type"] == "GKE Cluster"
        assert cluster["recommendation"] == "Delete empty cluster"
