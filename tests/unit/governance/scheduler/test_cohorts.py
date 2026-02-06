"""
Tests for Tenant Cohort Classification

Tests the scheduler's tenant cohort logic for tiered scheduling decisions.
"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock

from app.modules.governance.domain.scheduler.cohorts import (
    TenantCohort,
    get_tenant_cohort,
)


class TestTenantCohort:
    """Test TenantCohort enum values."""
    
    def test_cohort_values(self):
        """Verify cohort enum has expected values."""
        assert TenantCohort.HIGH_VALUE == "high_value"
        assert TenantCohort.ACTIVE == "active"
        assert TenantCohort.DORMANT == "dormant"


class TestGetTenantCohort:
    """Test get_tenant_cohort classification logic."""
    
    def _make_tenant(self, plan: str) -> MagicMock:
        """Create a mock tenant with the given plan."""
        tenant = MagicMock()
        tenant.plan = plan
        return tenant
    
    def test_enterprise_is_high_value(self):
        """Enterprise tier should be HIGH_VALUE cohort."""
        tenant = self._make_tenant("enterprise")
        assert get_tenant_cohort(tenant) == TenantCohort.HIGH_VALUE
    
    def test_pro_is_high_value(self):
        """Pro tier should be HIGH_VALUE cohort."""
        tenant = self._make_tenant("pro")
        assert get_tenant_cohort(tenant) == TenantCohort.HIGH_VALUE
    
    def test_growth_is_active(self):
        """Growth tier should be ACTIVE cohort."""
        tenant = self._make_tenant("growth")
        assert get_tenant_cohort(tenant) == TenantCohort.ACTIVE
    
    def test_starter_without_activity_is_dormant(self):
        """Starter tier with no activity info should be DORMANT."""
        tenant = self._make_tenant("starter")
        assert get_tenant_cohort(tenant) == TenantCohort.DORMANT
    
    def test_trial_without_activity_is_dormant(self):
        """Trial tier with no activity info should be DORMANT."""
        tenant = self._make_tenant("trial")
        assert get_tenant_cohort(tenant) == TenantCohort.DORMANT
    
    def test_dormancy_detection_7_days(self):
        """Tenant inactive for 7 days should be DORMANT."""
        tenant = self._make_tenant("growth")
        last_active = datetime.now(timezone.utc) - timedelta(days=7)
        assert get_tenant_cohort(tenant, last_active) == TenantCohort.DORMANT
    
    def test_dormancy_detection_8_days(self):
        """Tenant inactive for 8 days should be DORMANT."""
        tenant = self._make_tenant("growth")
        last_active = datetime.now(timezone.utc) - timedelta(days=8)
        assert get_tenant_cohort(tenant, last_active) == TenantCohort.DORMANT
    
    def test_active_within_7_days(self):
        """Tenant active within 7 days should not be DORMANT."""
        tenant = self._make_tenant("growth")
        last_active = datetime.now(timezone.utc) - timedelta(days=6)
        assert get_tenant_cohort(tenant, last_active) == TenantCohort.ACTIVE
    
    def test_high_value_not_affected_by_dormancy(self):
        """Enterprise/Pro should be HIGH_VALUE even if inactive."""
        tenant = self._make_tenant("enterprise")
        last_active = datetime.now(timezone.utc) - timedelta(days=30)
        # High-value check happens first, before dormancy
        assert get_tenant_cohort(tenant, last_active) == TenantCohort.HIGH_VALUE
    
    def test_free_tier_is_dormant(self):
        """Free tier should be DORMANT."""
        tenant = self._make_tenant("free")
        assert get_tenant_cohort(tenant) == TenantCohort.DORMANT
    
    def test_unknown_tier_is_dormant(self):
        """Unknown tier should default to DORMANT."""
        tenant = self._make_tenant("unknown_plan")
        assert get_tenant_cohort(tenant) == TenantCohort.DORMANT
