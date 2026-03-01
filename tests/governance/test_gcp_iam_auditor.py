from __future__ import annotations

import pytest

from app.modules.governance.domain.security.gcp_iam_auditor import GCPIAMAuditor


@pytest.mark.asyncio
async def test_gcp_iam_auditor_flags_public_and_privileged_bindings() -> None:
    auditor = GCPIAMAuditor(
        [
            {
                "role": "roles/owner",
                "members": ["allUsers", "user:admin@corp.example"],
            }
        ],
        project_id="acme-prod",
    )

    report = await auditor.audit()

    assert report.provider == "gcp"
    assert report.status == "risk"
    assert report.score < 85
    assert any(f.control == "public_access" and f.severity == "critical" for f in report.findings)
    assert any(f.control == "least_privilege" and f.severity == "high" for f in report.findings)
    assert any(
        f.control == "conditional_access" and f.severity == "medium" for f in report.findings
    )


@pytest.mark.asyncio
async def test_gcp_iam_auditor_no_findings_for_scoped_conditioned_role() -> None:
    auditor = GCPIAMAuditor(
        [
            {
                "role": "roles/storage.objectViewer",
                "members": ["serviceAccount:reader@acme-prod.iam.gserviceaccount.com"],
                "condition": {"title": "bucket scope", "expression": "resource.name.startsWith('projects/_/buckets/acme')"},
            }
        ],
        project_id="acme-prod",
    )

    report = await auditor.audit()

    assert report.status == "compliant"
    assert report.score == 100
    assert report.findings == ()
