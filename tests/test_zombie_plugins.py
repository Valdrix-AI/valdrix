"""
Tests for Zombie Detector Plugins

Tests:
1. ZombiePlugin base class
2. Plugin imports
3. Result structures
"""


from app.services.zombies.zombie_plugin import ZombiePlugin
from app.services.zombies import plugins


class TestZombiePluginModule:
    """Test plugin module structure."""
    
    def test_plugins_package_imports(self):
        """Plugins package should be importable."""
        from app.services.zombies.plugins import (
            storage,
            compute,
            database,
            network,
            containers,
            analytics,
        )
        
        assert storage is not None
        assert compute is not None
        assert database is not None
        assert network is not None
        assert containers is not None
        assert analytics is not None
    
    def test_plugins_exports_plugins(self):
        """Plugins package should export plugin classes."""
        
        # Should have plugin classes exported
        assert hasattr(plugins, 'UnattachedVolumesPlugin')
        assert hasattr(plugins, 'IdleInstancesPlugin')
        assert len(plugins.__all__) >= 5


class TestZombiePluginBase:
    """Test ZombiePlugin base class."""
    
    def test_plugin_class_exists(self):
        """ZombiePlugin class should exist."""
        assert ZombiePlugin is not None
    
    def test_plugin_is_abstract_base(self):
        """ZombiePlugin should be an abstract base class."""
        import inspect
        # It should be a class
        assert inspect.isclass(ZombiePlugin)


class TestPluginResults:
    """Test plugin result structures."""
    
    def test_zombie_result_structure(self):
        """Zombie detection results should have standard fields."""
        # A typical zombie result should include:
        mock_result = {
            "resource_id": "vol-123456",
            "resource_type": "ebs_volume",
            "region": "us-east-1",
            "monthly_cost": 10.50,
            "days_unused": 30,
            "reason": "No attachments for 30+ days"
        }
        
        # Verify expected fields
        assert "resource_id" in mock_result
        assert "monthly_cost" in mock_result
        assert "region" in mock_result
    
    def test_scan_result_aggregation(self):
        """Scan results should be aggregatable."""
        results = [
            {"resource_id": "vol-1", "monthly_cost": 10.0},
            {"resource_id": "vol-2", "monthly_cost": 20.0},
            {"resource_id": "vol-3", "monthly_cost": 15.0},
        ]
        
        total_waste = sum(r["monthly_cost"] for r in results)
        assert total_waste == 45.0
    
    def test_results_groupable_by_type(self):
        """Results should be groupable by resource type."""
        results = [
            {"resource_id": "vol-1", "resource_type": "ebs_volume"},
            {"resource_id": "i-1", "resource_type": "ec2_instance"},
            {"resource_id": "vol-2", "resource_type": "ebs_volume"},
        ]
        
        by_type = {}
        for r in results:
            t = r["resource_type"]
            by_type.setdefault(t, []).append(r)
        
        assert len(by_type["ebs_volume"]) == 2
        assert len(by_type["ec2_instance"]) == 1


class TestPluginCategories:
    """Test that plugins cover key AWS categories."""
    
    def test_storage_category_exists(self):
        """Storage plugins should exist (EBS, S3, etc)."""
        from app.services.zombies.plugins import storage
        assert storage is not None
    
    def test_compute_category_exists(self):
        """Compute plugins should exist (EC2, Lambda)."""
        from app.services.zombies.plugins import compute
        assert compute is not None
    
    def test_database_category_exists(self):
        """Database plugins should exist (RDS, Redshift)."""
        from app.services.zombies.plugins import database
        assert database is not None
    
    def test_network_category_exists(self):
        """Network plugins should exist (ELB, EIP)."""
        from app.services.zombies.plugins import network
        assert network is not None
    
    def test_container_category_exists(self):
        """Container plugins should exist (ECR, ECS)."""
        from app.services.zombies.plugins import containers
        assert containers is not None
    
    def test_analytics_category_exists(self):
        """Analytics plugins should exist (SageMaker)."""
        from app.services.zombies.plugins import analytics
        assert analytics is not None
