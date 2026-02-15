"""
Unit tests for GCP Usage Analyzer.

Tests zero-cost zombie detection logic using mock billing data.
"""

from app.shared.analysis.gcp_usage_analyzer import GCPUsageAnalyzer


class TestGCPUsageAnalyzerIdleVMs:
    """Tests for idle VM detection."""

    def test_detects_idle_vm_low_cpu(self):
        """VM with low CPU hours should be flagged as idle."""
        billing_records = [
            {
                "resource_id": "projects/my-project/zones/us-central1-a/instances/idle-vm",
                "service": "Compute Engine",
                "sku_description": "N1 Standard CPU Hours",
                "usage_amount": 2.0,
                "cost": 50.0,
            },
            {
                "resource_id": "projects/my-project/zones/us-central1-a/instances/idle-vm",
                "service": "Compute Engine",
                "sku_description": "Network Egress",
                "usage_amount": 0.1,
                "cost": 0.01,
            },
        ]

        analyzer = GCPUsageAnalyzer(billing_records)
        zombies = analyzer.find_idle_vms(days=7, cpu_threshold=5.0)

        assert len(zombies) == 1
        assert zombies[0]["resource_name"] == "idle-vm"
        assert zombies[0]["resource_type"] == "Compute Engine VM"
        assert zombies[0]["confidence_score"] >= 0.75

    def test_active_vm_not_flagged(self):
        """VM with high CPU usage should NOT be flagged."""
        billing_records = [
            {
                "resource_id": "projects/my-project/zones/us-central1-a/instances/active-vm",
                "service": "Compute Engine",
                "sku_description": "N1 Standard CPU Hours",
                "usage_amount": 168.0,  # Full week of usage
                "cost": 100.0,
            },
        ]

        analyzer = GCPUsageAnalyzer(billing_records)
        zombies = analyzer.find_idle_vms(days=7, cpu_threshold=5.0)

        assert len(zombies) == 0

    def test_gpu_vm_flagged_with_type(self):
        """GPU VM should be flagged with (GPU) in type."""
        billing_records = [
            {
                "resource_id": "projects/my-project/zones/us-central1-a/instances/gpu-vm",
                "service": "Compute Engine",
                "sku_description": "NVIDIA Tesla T4 GPU Hours",
                "usage_amount": 0.5,
                "cost": 200.0,
            },
        ]

        analyzer = GCPUsageAnalyzer(billing_records)
        zombies = analyzer.find_idle_vms(days=7, cpu_threshold=5.0)

        assert len(zombies) == 1
        assert "(GPU)" in zombies[0]["resource_type"]


class TestGCPUsageAnalyzerDisks:
    """Tests for unattached disk detection."""

    def test_detects_orphan_disk(self):
        """Disk with storage cost but no I/O should be flagged."""
        billing_records = [
            {
                "resource_id": "projects/my-project/zones/us-central1-a/disks/orphan-disk",
                "service": "Persistent Disk",
                "sku_description": "Storage PD Capacity",
                "usage_amount": 100.0,  # 100 GB
                "cost": 4.0,
            },
        ]

        analyzer = GCPUsageAnalyzer(billing_records)
        zombies = analyzer.find_unattached_disks()

        assert len(zombies) == 1
        assert zombies[0]["resource_name"] == "orphan-disk"
        assert zombies[0]["confidence_score"] >= 0.90

    def test_active_disk_not_flagged(self):
        """Disk with I/O operations should NOT be flagged."""
        billing_records = [
            {
                "resource_id": "projects/my-project/zones/us-central1-a/disks/active-disk",
                "service": "Persistent Disk",
                "sku_description": "Storage PD Capacity",
                "usage_amount": 100.0,
                "cost": 4.0,
            },
            {
                "resource_id": "projects/my-project/zones/us-central1-a/disks/active-disk",
                "service": "Persistent Disk",
                "sku_description": "Disk Read Operations",
                "usage_amount": 50000.0,
                "cost": 0.05,
            },
        ]

        analyzer = GCPUsageAnalyzer(billing_records)
        zombies = analyzer.find_unattached_disks()

        assert len(zombies) == 0


class TestGCPUsageAnalyzerCloudSQL:
    """Tests for idle Cloud SQL detection."""

    def test_detects_idle_cloud_sql(self):
        """Cloud SQL with no network traffic should be flagged."""
        billing_records = [
            {
                "resource_id": "projects/my-project/instances/idle-db",
                "service": "Cloud SQL",
                "sku_description": "Cloud SQL Instance",
                "usage_amount": 1.0,
                "cost": 50.0,
            },
            {
                "resource_id": "projects/my-project/instances/idle-db",
                "service": "Cloud SQL",
                "sku_description": "Network Traffic",
                "usage_amount": 0.001,  # Almost no traffic
                "cost": 0.0,
            },
        ]

        analyzer = GCPUsageAnalyzer(billing_records)
        zombies = analyzer.find_idle_cloud_sql(days=7)

        assert len(zombies) == 1
        assert zombies[0]["resource_name"] == "idle-db"
        assert zombies[0]["resource_type"] == "Cloud SQL"


class TestGCPUsageAnalyzerGKE:
    """Tests for empty GKE cluster detection."""

    def test_detects_empty_gke_cluster(self):
        """GKE cluster with control plane only should be flagged."""
        billing_records = [
            {
                "resource_id": "projects/my-project/locations/us-central1/clusters/empty-cluster",
                "service": "Kubernetes Engine",
                "sku_description": "Cluster Management Fee",
                "usage_amount": 1.0,
                "cost": 72.0,
            },
        ]

        analyzer = GCPUsageAnalyzer(billing_records)
        zombies = analyzer.find_empty_gke_clusters(days=7)

        assert len(zombies) == 1
        assert zombies[0]["resource_name"] == "empty-cluster"
        assert zombies[0]["resource_type"] == "GKE Cluster"


class TestGCPUsageAnalyzerOrphanIPs:
    """Tests for orphan IP detection."""

    def test_detects_orphan_ip(self):
        """Unused static IP with charges should be flagged."""
        billing_records = [
            {
                "resource_id": "projects/my-project/regions/us-central1/addresses/orphan-ip",
                "service": "Compute Engine",
                "sku_description": "Static External IP Charge",
                "usage_amount": 720.0,  # Hours
                "cost": 7.20,
            },
        ]

        analyzer = GCPUsageAnalyzer(billing_records)
        zombies = analyzer.find_orphan_ips()

        assert len(zombies) == 1
        assert zombies[0]["resource_name"] == "orphan-ip"
        assert zombies[0]["resource_type"] == "External IP Address"


class TestGCPUsageAnalyzerEmpty:
    """Tests for edge cases with empty data."""

    def test_empty_records_returns_empty(self):
        """Empty billing records should return no zombies."""
        analyzer = GCPUsageAnalyzer([])

        assert analyzer.find_idle_vms() == []
        assert analyzer.find_unattached_disks() == []
        assert analyzer.find_idle_cloud_sql() == []
        assert analyzer.find_empty_gke_clusters() == []
        assert analyzer.find_orphan_ips() == []
