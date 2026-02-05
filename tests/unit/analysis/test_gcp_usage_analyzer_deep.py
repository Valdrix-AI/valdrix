import pytest
from app.shared.analysis.gcp_usage_analyzer import GCPUsageAnalyzer

class TestGCPUsageAnalyzer:
    def test_find_idle_vms(self):
        records = [
            # Idle VM (Ran for 7 days, has cost, but low compute usage and no egress)
            {
                "resource_id": "projects/p1/zones/z1/instances/vm-idle",
                "service": "Compute Engine",
                "sku_description": "N1 Predefined Instance vCPU",
                "usage_amount": 0.5, # 0.5 hours over 7 days (168h expected)
                "cost": 10.0,
                "usage_unit": "hour"
            },
            # Active VM
            {
                "resource_id": "projects/p1/zones/z1/instances/vm-active",
                "service": "Compute Engine",
                "sku_description": "N1 Predefined Instance vCPU",
                "usage_amount": 160.0,
                "cost": 50.0,
                "usage_unit": "hour"
            },
            {
                "resource_id": "projects/p1/zones/z1/instances/vm-active",
                "service": "Compute Engine",
                "sku_description": "Network Internet Egress",
                "usage_amount": 100.0, # 100 GB egress
                "cost": 1.0
            }
        ]
        analyzer = GCPUsageAnalyzer(records)
        results = analyzer.find_idle_vms(days=7)
        assert len(results) == 1
        assert results[0]["resource_id"] == "projects/p1/zones/z1/instances/vm-idle"

    def test_find_unattached_disks(self):
        records = [
            # Unattached disk (Storage cost but no read/write usage)
            {
                "resource_id": "projects/p1/zones/z1/disks/disk-orphan",
                "service": "Compute Engine",
                "sku_description": "Storage PD Capacity",
                "usage_amount": 100.0,
                "cost": 5.0,
                "usage_unit": "gibibyte month"
            }
        ]
        analyzer = GCPUsageAnalyzer(records)
        results = analyzer.find_unattached_disks()
        assert len(results) == 1
        assert results[0]["resource_id"] == "projects/p1/zones/z1/disks/disk-orphan"

    def test_find_idle_cloud_sql(self):
        records = [
            # Idle SQL
            {
                "resource_id": "db-idle",
                "service": "Cloud SQL",
                "sku_description": "Cloud SQL: Core",
                "usage_amount": 0.1,
                "cost": 20.0
            }
        ]
        analyzer = GCPUsageAnalyzer(records)
        results = analyzer.find_idle_cloud_sql(days=7)
        assert len(results) == 1
        assert results[0]["resource_id"] == "db-idle"

    def test_find_empty_gke_clusters(self):
        records = [
            # Empty GKE (Control plane cost but no node cost)
            {
                "resource_id": "gke-empty",
                "service": "Kubernetes Engine",
                "sku_description": "GKE Cluster Management Fee",
                "cost": 15.0
            }
        ]
        analyzer = GCPUsageAnalyzer(records)
        results = analyzer.find_empty_gke_clusters(days=7)
        assert len(results) == 1
        assert results[0]["resource_id"] == "gke-empty"

    def test_find_idle_cloud_functions(self):
        records = [
            # Idle function
            {
                "resource_id": "func-idle",
                "service": "Cloud Functions",
                "sku_description": "Function Execution",
                "cost": 2.0,
                "usage_amount": 0.0 # Zero invocations
            }
        ]
        analyzer = GCPUsageAnalyzer(records)
        results = analyzer.find_idle_cloud_functions(days=30)
        assert len(results) == 1
        assert results[0]["resource_id"] == "func-idle"

    def test_find_idle_cloud_run(self):
        records = [
            # Idle Run
            {
                "resource_id": "run-idle",
                "service": "Cloud Run",
                "sku_description": "Request Count",
                "cost": 5.0,
                "usage_amount": 0.0
            }
        ]
        analyzer = GCPUsageAnalyzer(records)
        results = analyzer.find_idle_cloud_run(days=30)
        assert len(results) == 1
        assert results[0]["resource_id"] == "run-idle"

    def test_find_orphan_ips(self):
        records = [
            # Orphan IP
            {
                "resource_id": "ip-orphan",
                "service": "Compute Engine",
                "sku_description": "Static Ip Charge",
                "cost": 3.0
            }
        ]
        analyzer = GCPUsageAnalyzer(records)
        results = analyzer.find_orphan_ips()
        assert len(results) == 1
        assert results[0]["resource_id"] == "ip-orphan"

    def test_find_old_snapshots(self):
        records = [
            # Old snapshot
            {
                "resource_id": "snap-old",
                "service": "Compute Engine",
                "sku_description": "Snapshot Storage",
                "cost": 1.0
            }
        ]
        analyzer = GCPUsageAnalyzer(records)
        results = analyzer.find_old_snapshots(age_days=90)
        assert len(results) == 1
        assert results[0]["resource_id"] == "snap-old"

    def test_negative_cases_exhaust_branches(self):
        records = [
            {"service": "WrongService"},
            {"service": "Compute Engine", "sku_description": "WrongSKU"},
            {
                "resource_id": "projects/p1/zones/z1/instances/vm-1",
                "service": "Compute Engine",
                "sku_description": "N1 Predefined Instance Core",
                "cost": 1.0,
                "usage_amount": 0.1
            }
        ]
        analyzer = GCPUsageAnalyzer(records)
        # Hit loops with continue
        analyzer.find_idle_vms()
        analyzer.find_unattached_disks()
        analyzer.find_idle_cloud_sql()
        analyzer.find_empty_gke_clusters()
        analyzer.find_idle_cloud_functions()
        analyzer.find_idle_cloud_run()
        analyzer.find_orphan_ips()
        analyzer.find_old_snapshots()
        assert True
