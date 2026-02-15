"""
Tests for AWS Network Plugins

Tests for OrphanLoadBalancersPlugin and UnderusedNatGatewaysPlugin.
"""

import pytest

from app.modules.optimization.adapters.aws.plugins.network import (
    OrphanLoadBalancersPlugin,
    UnderusedNatGatewaysPlugin,
)


class TestOrphanLoadBalancersPlugin:
    """Test OrphanLoadBalancersPlugin functionality."""

    @pytest.fixture
    def plugin(self):
        """Create plugin instance."""
        return OrphanLoadBalancersPlugin()

    def test_category_key(self, plugin):
        """Test category key."""
        assert plugin.category_key == "orphan_load_balancers"

    def test_plugin_inherits_from_zombie_plugin(self, plugin):
        """Test that plugin inherits from ZombiePlugin."""
        from app.modules.optimization.domain.plugin import ZombiePlugin

        assert isinstance(plugin, ZombiePlugin)

    def test_plugin_has_scan_method(self, plugin):
        """Test that plugin has scan method."""
        assert hasattr(plugin, "scan")
        assert callable(plugin.scan)

    def test_plugin_has_get_client_method(self, plugin):
        """Test that plugin has _get_client method for AWS connections."""
        assert hasattr(plugin, "_get_client")


class TestUnderusedNatGatewaysPlugin:
    """Test UnderusedNatGatewaysPlugin functionality."""

    @pytest.fixture
    def plugin(self):
        """Create plugin instance."""
        return UnderusedNatGatewaysPlugin()

    def test_category_key(self, plugin):
        """Test category key."""
        assert plugin.category_key == "underused_nat_gateways"

    def test_plugin_inherits_from_zombie_plugin(self, plugin):
        """Test that plugin inherits from ZombiePlugin."""
        from app.modules.optimization.domain.plugin import ZombiePlugin

        assert isinstance(plugin, ZombiePlugin)

    def test_plugin_has_scan_method(self, plugin):
        """Test that plugin has scan method."""
        assert hasattr(plugin, "scan")
        assert callable(plugin.scan)
