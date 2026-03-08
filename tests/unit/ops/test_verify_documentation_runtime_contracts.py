from __future__ import annotations

from pathlib import Path

from scripts.verify_documentation_runtime_contracts import (
    DocumentationContract,
    verify_contracts,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_verify_contracts_accepts_matching_docs(tmp_path: Path) -> None:
    _write(
        tmp_path / "docs/architecture/overview.md",
        "boundary target\nHelm chart\nCloudflare Pages + Koyeb\n",
    )
    _write(
        tmp_path / "docs/DEPLOYMENT.md",
        "Supported deployment profiles\nHelm + Terraform (AWS/EKS)\nCloudflare Pages + Koyeb\nkoyeb-worker.yaml\n",
    )
    _write(
        tmp_path / "docs/CAPACITY_PLAN.md",
        "Helm + Terraform (AWS/EKS)\nCloudflare Pages + Koyeb\nAWS RDS profile\nkoyeb-worker.yaml\n",
    )
    _write(
        tmp_path / "docs/ROLLBACK_PLAN.md",
        "ENABLE_SCHEDULER=false\nbackup/restore\n",
    )
    _write(
        tmp_path / "docs/architecture/database_schema_overview.md",
        "One-step forward/rollback smoke\nbackup/restore is the primary rollback path\n",
    )
    _write(
        tmp_path / "docs/architecture/failover.md",
        "Cloudflare\nRDS\ndisaster-recovery-drill.yml\n",
    )
    _write(
        tmp_path / "docs/runbooks/disaster_recovery.md",
        "AWS RDS\nCloudflare\ndisaster-recovery-drill.yml\nkoyeb-worker.yaml\n",
    )
    _write(
        tmp_path / "docs/runbooks/incident_response.md",
        "Settings -> Notifications\nstrict SaaS mode\n",
    )
    _write(
        tmp_path / "docs/runbooks/production_env_checklist.md",
        "SENTRY_DSN=https://...\nOTEL_EXPORTER_OTLP_ENDPOINT=https://collector:4317\nEXPOSE_API_DOCUMENTATION_PUBLICLY=false\n",
    )
    _write(
        tmp_path / "docs/integrations/workflow_automation.md",
        "env channel routing (`SLACK_CHANNEL_ID`) is blocked\nself-host or break-glass-only paths\n",
    )

    errors = verify_contracts(root=tmp_path)
    assert errors == []


def test_verify_contracts_reports_missing_and_forbidden_phrases(tmp_path: Path) -> None:
    for contract in (
        DocumentationContract(
            path="docs/architecture/overview.md",
            required_phrases=("boundary target",),
            forbidden_phrases=("Zero external dependencies",),
        ),
        DocumentationContract(
            path="docs/DEPLOYMENT.md",
            required_phrases=("Supported deployment profiles",),
        ),
        DocumentationContract(
            path="docs/CAPACITY_PLAN.md",
            required_phrases=("AWS RDS profile",),
        ),
        DocumentationContract(
            path="docs/ROLLBACK_PLAN.md",
            required_phrases=("ENABLE_SCHEDULER=false",),
        ),
        DocumentationContract(
            path="docs/architecture/database_schema_overview.md",
            required_phrases=("backup/restore is the primary rollback path",),
        ),
        DocumentationContract(
            path="docs/architecture/failover.md",
            required_phrases=("Cloudflare",),
        ),
        DocumentationContract(
            path="docs/runbooks/disaster_recovery.md",
            required_phrases=("AWS RDS",),
        ),
        DocumentationContract(
            path="docs/runbooks/incident_response.md",
            required_phrases=("Settings -> Notifications",),
            forbidden_phrases=("specified in `SLACK_CHANNEL_ID`",),
        ),
        DocumentationContract(
            path="docs/runbooks/production_env_checklist.md",
            required_phrases=("OTEL_EXPORTER_OTLP_ENDPOINT=https://",),
        ),
        DocumentationContract(
            path="docs/integrations/workflow_automation.md",
            required_phrases=("self-host or break-glass-only paths",),
        ),
    ):
        _write(tmp_path / contract.path, "placeholder\n")

    _write(
        tmp_path / "docs/architecture/overview.md",
        "Zero external dependencies\n",
    )

    errors = verify_contracts(root=tmp_path)
    assert "docs/architecture/overview.md: missing required phrase 'boundary target'" in errors
    assert (
        "docs/architecture/overview.md: forbidden phrase present 'Zero external dependencies'"
        in errors
    )
