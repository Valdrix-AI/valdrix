from __future__ import annotations

import pytest

from app.modules.governance.domain.scheduler.cohorts import TenantCohort


def test_tenant_cohort_missing_supports_name_and_value_case_insensitive() -> None:
    class _LowerOnlyStr(str):
        def upper(self) -> str:  # type: ignore[override]
            return "NOT_A_MEMBER_NAME"

        def lower(self) -> str:  # type: ignore[override]
            return "active"

    assert TenantCohort("HIGH_VALUE") is TenantCohort.HIGH_VALUE
    assert TenantCohort(_LowerOnlyStr("anything")) is TenantCohort.ACTIVE
    assert TenantCohort("DoRmAnT") is TenantCohort.DORMANT


def test_tenant_cohort_missing_invalid_value_raises() -> None:
    with pytest.raises(ValueError):
        TenantCohort(123)  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        TenantCohort("not-a-cohort")
