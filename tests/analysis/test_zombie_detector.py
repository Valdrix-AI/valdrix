"""
Tests for ZombieDetector and Zombie Plugin Architecture

Tests cover:
- ZombieDetector instantiation and plugin loading
- Plugin structure and interface compliance
- scan_all() aggregation logic
- Individual plugin scan() mocking
- Cost estimation calculation
"""

import pytest
from unittest.mock import AsyncMock

from app.modules.optimization.domain.detector import ZombieDetector
from app.modules.optimization.domain.zombie_plugin import ZombiePlugin, ESTIMATED_COSTS
from app.modules.optimization.domain.aws_provider.plugins import (
    UnattachedVolumesPlugin, OldSnapshotsPlugin, IdleS3BucketsPlugin,
    UnusedElasticIpsPlugin, IdleInstancesPlugin,
    OrphanLoadBalancersPlugin, UnderusedNatGatewaysPlugin,
    IdleRdsPlugin, ColdRedshiftPlugin,
    IdleSageMakerPlugin, LegacyEcrImagesPlugin
)


class AsyncContextManagerMock:
    """Helper to mock async with context managers."""
    def __init__(self, return_value):
        self.return_value = return_value
    async def __aenter__(self):
        return self.return_value
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass


class TestZombieDetectorInstantiation:
    """Tests for ZombieDetector initialization."""
    
    def test_default_region(self):
        """Should default to us-east-1."""
        detector = ZombieDetector()
        assert detector.region == "us-east-1"
    
    def test_custom_region(self):
        """Should accept custom region."""
        detector = ZombieDetector(region="eu-west-1")
        assert detector.region == "eu-west-1"
    
    def test_credentials_storage(self):
        """Should store credentials for STS-based access."""
        creds = {"AccessKeyId": "test", "SecretAccessKey": "test", "SessionToken": "test"}
        detector = ZombieDetector(credentials=creds)
        assert detector.credentials == creds
    
    def test_plugins_loaded(self):
        """Should load all 11 zombie plugins."""
        detector = ZombieDetector()
        assert len(detector.plugins) == 11
    
    def test_all_plugin_types_present(self):
        """Should include all expected plugin types."""
        detector = ZombieDetector()
        plugin_classes = [type(p) for p in detector.plugins]
        
        expected = [
            UnattachedVolumesPlugin, OldSnapshotsPlugin, IdleS3BucketsPlugin,
            UnusedElasticIpsPlugin, IdleInstancesPlugin,
            OrphanLoadBalancersPlugin, UnderusedNatGatewaysPlugin,
            IdleRdsPlugin, ColdRedshiftPlugin,
            IdleSageMakerPlugin, LegacyEcrImagesPlugin
        ]
        
        for expected_class in expected:
            assert expected_class in plugin_classes, f"{expected_class.__name__} not found"


class TestPluginInterface:
    """Tests for ZombiePlugin ABC compliance."""
    
    def test_all_plugins_have_category_key(self):
        """All plugins must define category_key property."""
        detector = ZombieDetector()
        for plugin in detector.plugins:
            assert hasattr(plugin, 'category_key')
            assert isinstance(plugin.category_key, str)
            assert len(plugin.category_key) > 0
    
    def test_category_keys_are_unique(self):
        """Each plugin must have a unique category key."""
        detector = ZombieDetector()
        keys = [p.category_key for p in detector.plugins]
        assert len(keys) == len(set(keys)), "Duplicate category keys found"
    
    def test_all_plugins_have_scan_method(self):
        """All plugins must implement scan() method."""
        detector = ZombieDetector()
        for plugin in detector.plugins:
            assert hasattr(plugin, 'scan')
            assert callable(plugin.scan)


class TestEstimatedCosts:
    """Tests for cost estimation constants."""
    
    def test_all_cost_keys_present(self):
        """Should have all expected cost keys."""
        required_keys = [
            "ebs_volume_gb", "elastic_ip", "snapshot_gb",
            "ec2_t3_micro", "ec2_t3_small", "ec2_t3_medium",
            "ec2_m5_large", "ec2_default", "elb", "s3_gb",
            "ecr_gb", "sagemaker_endpoint", "redshift_cluster", "nat_gateway"
        ]
        for key in required_keys:
            assert key in ESTIMATED_COSTS, f"Missing cost key: {key}"
    
    def test_all_costs_are_positive(self):
        """All cost values should be positive numbers."""
        for key, value in ESTIMATED_COSTS.items():
            assert value >= 0, f"Cost for {key} should be non-negative"


@pytest.mark.asyncio
class TestScanAll:
    """Tests for ZombieDetector.scan_all()"""
    
    async def test_returns_dict_with_metadata(self):
        """scan_all() should return dict with region and timestamp."""
        detector = ZombieDetector()
        
        # Mock all plugins to return empty lists
        for plugin in detector.plugins:
            plugin.scan = AsyncMock(return_value=[])
        
        result = await detector.scan_all()
        
        assert "region" in result
        assert result["region"] == "us-east-1"
        assert "scanned_at" in result
        assert "total_monthly_waste" in result
    
    async def test_aggregates_plugin_results(self):
        """scan_all() should aggregate results from all plugins."""
        detector = ZombieDetector()
        
        # Mock one plugin to return a zombie
        for plugin in detector.plugins:
            if plugin.category_key == "unattached_volumes":
                plugin.scan = AsyncMock(return_value=[
                    {"resource_id": "vol-123", "monthly_cost": 10.0}
                ])
            else:
                plugin.scan = AsyncMock(return_value=[])
        
        result = await detector.scan_all()
        
        assert "unattached_volumes" in result
        assert len(result["unattached_volumes"]) == 1
        assert result["unattached_volumes"][0]["resource_id"] == "vol-123"
    
    async def test_calculates_total_waste(self):
        """scan_all() should sum up monthly costs from all zombies."""
        detector = ZombieDetector()
        
        # Mock multiple plugins with zombies
        for plugin in detector.plugins:
            if plugin.category_key == "unattached_volumes":
                plugin.scan = AsyncMock(return_value=[
                    {"resource_id": "vol-1", "monthly_cost": 10.0},
                    {"resource_id": "vol-2", "monthly_cost": 20.0}
                ])
            elif plugin.category_key == "old_snapshots":
                plugin.scan = AsyncMock(return_value=[
                    {"resource_id": "snap-1", "monthly_cost": 5.0}
                ])
            else:
                plugin.scan = AsyncMock(return_value=[])
        
        result = await detector.scan_all()
        
        # 10 + 20 + 5 = 35
        assert result["total_monthly_waste"] == 35.0
    
    async def test_handles_plugin_failure_gracefully(self):
        """If a plugin fails, others should still run."""
        detector = ZombieDetector()
        
        for i, plugin in enumerate(detector.plugins):
            if i == 0:
                # First plugin throws exception
                plugin.scan = AsyncMock(side_effect=Exception("AWS Error"))
            else:
                plugin.scan = AsyncMock(return_value=[])
        
        # Should not raise, should return results from other plugins
        result = await detector.scan_all()
        
        assert "region" in result
        assert result[detector.plugins[0].category_key] == []  # Failed plugin returns empty


@pytest.mark.asyncio
class TestUnattachedVolumesPlugin:
    """Tests for UnattachedVolumesPlugin."""
    
    async def test_category_key(self):
        """Should return correct category key."""
        plugin = UnattachedVolumesPlugin()
        assert plugin.category_key == "unattached_volumes"
    
    async def test_inherits_from_zombie_plugin(self):
        """Should inherit from ZombiePlugin ABC."""
        plugin = UnattachedVolumesPlugin()
        assert isinstance(plugin, ZombiePlugin)
    
    async def test_has_scan_method(self):
        """Should have scan method."""
        plugin = UnattachedVolumesPlugin()
        assert hasattr(plugin, 'scan')
        assert callable(plugin.scan)


@pytest.mark.asyncio  
class TestOldSnapshotsPlugin:
    """Tests for OldSnapshotsPlugin."""
    
    async def test_category_key(self):
        """Should return correct category key."""
        plugin = OldSnapshotsPlugin()
        assert plugin.category_key == "old_snapshots"


@pytest.mark.asyncio
class TestIdleS3BucketsPlugin:
    """Tests for IdleS3BucketsPlugin."""
    
    async def test_category_key(self):
        """Should return correct category key."""
        plugin = IdleS3BucketsPlugin()
        assert plugin.category_key == "idle_s3_buckets"
