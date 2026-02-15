"""
Tests for AWS Containers Plugin (ECR)

Tests the StaleEcrImagesPlugin for detecting untagged ECR images.
"""

import pytest

from app.modules.optimization.adapters.aws.plugins.containers import (
    StaleEcrImagesPlugin,
)


class TestStaleEcrImagesPlugin:
    """Test StaleEcrImagesPlugin functionality."""

    @pytest.fixture
    def plugin(self):
        """Create a StaleEcrImagesPlugin instance."""
        return StaleEcrImagesPlugin()

    def test_category_key(self, plugin):
        """Test that category_key returns correct value."""
        assert plugin.category_key == "stale_ecr_images"

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
