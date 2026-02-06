"""
Tests for AWS Infrastructure Plugins

Tests for StoppedInstancesWithEbsPlugin, UnusedLambdaPlugin, and OrphanVpcEndpointsPlugin.
"""

import pytest
from unittest.mock import MagicMock

from app.modules.optimization.adapters.aws.plugins.infrastructure import (
    StoppedInstancesWithEbsPlugin,
    UnusedLambdaPlugin,
    OrphanVpcEndpointsPlugin,
)


class TestStoppedInstancesWithEbsPlugin:
    """Test StoppedInstancesWithEbsPlugin functionality."""
    
    @pytest.fixture
    def plugin(self):
        """Create plugin instance."""
        return StoppedInstancesWithEbsPlugin()
    
    def test_category_key(self, plugin):
        """Test category key."""
        assert plugin.category_key == "stopped_instances_with_ebs"
    
    def test_plugin_inherits_from_zombie_plugin(self, plugin):
        """Test that plugin inherits from ZombiePlugin."""
        from app.modules.optimization.domain.plugin import ZombiePlugin
        assert isinstance(plugin, ZombiePlugin)
    
    def test_plugin_has_scan_method(self, plugin):
        """Test that plugin has scan method."""
        assert hasattr(plugin, "scan")
        assert callable(plugin.scan)


class TestUnusedLambdaPlugin:
    """Test UnusedLambdaPlugin functionality."""
    
    @pytest.fixture
    def plugin(self):
        """Create plugin instance."""
        return UnusedLambdaPlugin()
    
    def test_category_key(self, plugin):
        """Test category key."""
        assert plugin.category_key == "unused_lambda_functions"
    
    def test_plugin_inherits_from_zombie_plugin(self, plugin):
        """Test that plugin inherits from ZombiePlugin."""
        from app.modules.optimization.domain.plugin import ZombiePlugin
        assert isinstance(plugin, ZombiePlugin)
    
    def test_plugin_has_scan_method(self, plugin):
        """Test that plugin has scan method."""
        assert hasattr(plugin, "scan")
        assert callable(plugin.scan)


class TestOrphanVpcEndpointsPlugin:
    """Test OrphanVpcEndpointsPlugin functionality."""
    
    @pytest.fixture
    def plugin(self):
        """Create plugin instance."""
        return OrphanVpcEndpointsPlugin()
    
    def test_category_key(self, plugin):
        """Test category key."""
        assert plugin.category_key == "orphan_vpc_endpoints"
    
    def test_plugin_inherits_from_zombie_plugin(self, plugin):
        """Test that plugin inherits from ZombiePlugin."""
        from app.modules.optimization.domain.plugin import ZombiePlugin
        assert isinstance(plugin, ZombiePlugin)
    
    def test_plugin_has_scan_method(self, plugin):
        """Test that plugin has scan method."""
        assert hasattr(plugin, "scan")
        assert callable(plugin.scan)
