from __future__ import annotations

import pytest

from app.modules.governance.domain.security.azure_rbac_auditor import AzureRBACAuditor


@pytest.mark.asyncio
async def test_azure_rbac_auditor_flags_broad_privileged_assignment() -> None:
    auditor = AzureRBACAuditor(
        [
            {
                "principal_name": "alice@corp.example",
                "principal_type": "User",
                "role_definition_name": "Owner",
                "scope": "/subscriptions/12345678-aaaa-bbbb-cccc-1234567890ab",
                "mfa_enabled": False,
                "is_pim_eligible": False,
            }
        ],
        subscription_id="12345678-aaaa-bbbb-cccc-1234567890ab",
    )

    report = await auditor.audit()

    assert report.provider == "azure"
    assert report.status == "risk"
    assert report.score < 85
    assert any(f.control == "least_privilege" and f.severity == "critical" for f in report.findings)
    assert any(f.control == "mfa_enforcement" and f.severity == "high" for f in report.findings)
    assert any(f.control == "jit_access" and f.severity == "medium" for f in report.findings)


@pytest.mark.asyncio
async def test_azure_rbac_auditor_compliant_for_non_privileged_assignments() -> None:
    auditor = AzureRBACAuditor(
        [
            {
                "principal_name": "readonly-app",
                "principal_type": "ServicePrincipal",
                "role_definition_name": "Reader",
                "scope": "/subscriptions/123/resourceGroups/rg-app",
                "mfa_enabled": True,
                "is_pim_eligible": True,
            }
        ],
        subscription_id="123",
    )

    report = await auditor.audit()

    assert report.status == "compliant"
    assert report.score == 100
    assert report.findings == ()
