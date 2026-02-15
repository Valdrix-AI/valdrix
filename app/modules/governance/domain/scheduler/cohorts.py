from enum import Enum
from datetime import datetime, timezone
from typing import cast
from app.models.tenant import Tenant


class TenantCohort(str, Enum):
    HIGH_VALUE = "high_value"  # Enterprise, Pro
    ACTIVE = "active"  # Growth
    DORMANT = "dormant"  # Starter, or any tier inactive 7+ days

    @classmethod
    def _missing_(cls, value: object) -> "TenantCohort | None":
        """
        Allow construction from enum member name (e.g. "HIGH_VALUE") or
        case-insensitive variants so tests that call TenantCohort("HIGH_VALUE")
        succeed.
        """
        if isinstance(value, str):
            # Try name lookup (case-insensitive)
            name = value.upper()
            if name in cls.__members__:
                return cls.__members__[name]

            # Try value-based (case-insensitive)
            low = value.lower()
            for member in cls:
                if member.value == low:
                    return member

        return cast("TenantCohort | None", super()._missing_(value))


def get_tenant_cohort(
    tenant: Tenant, last_active: datetime | None = None
) -> TenantCohort:
    """
    Classify tenant into a cohort for tiered scheduling.

    Args:
        tenant: The tenant model
        last_active: Optional last activity timestamp (for dormancy detection)

    Returns:
        TenantCohort for scheduling decisions
    """
    # High-value tiers get priority scheduling
    if tenant.plan in ["enterprise", "pro"]:
        return TenantCohort.HIGH_VALUE

    # Check for dormancy (inactive > 7 days)
    if last_active:
        days_inactive = (datetime.now(timezone.utc) - last_active).days
        if days_inactive >= 7:
            return TenantCohort.DORMANT

    # Growth tier = Active cohort
    if tenant.plan == "growth":
        return TenantCohort.ACTIVE

    # Starter and Trial with no activity info = DORMANT (weekly scans)
    return TenantCohort.DORMANT
