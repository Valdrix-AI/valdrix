#!/usr/bin/env python3
"""Fail fast when checked-in runtime/architecture docs drift from repo reality."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DocumentationContract:
    path: str
    required_phrases: tuple[str, ...]
    forbidden_phrases: tuple[str, ...] = ()


DEFAULT_ROOT = Path(__file__).resolve().parents[1]
DOCUMENTATION_CONTRACTS: tuple[DocumentationContract, ...] = (
    DocumentationContract(
        path="docs/architecture/overview.md",
        required_phrases=("boundary target", "Helm chart", "Cloudflare Pages + Koyeb"),
        forbidden_phrases=("Zero external dependencies", "`k8s/`"),
    ),
    DocumentationContract(
        path="docs/DEPLOYMENT.md",
        required_phrases=(
            "Supported deployment profiles",
            "Helm + Terraform (AWS/EKS)",
            "Cloudflare Pages + Koyeb",
            "koyeb-worker.yaml",
        ),
        forbidden_phrases=("Vercel",),
    ),
    DocumentationContract(
        path="docs/CAPACITY_PLAN.md",
        required_phrases=(
            "Helm + Terraform (AWS/EKS)",
            "Cloudflare Pages + Koyeb",
            "AWS RDS profile",
            "koyeb-worker.yaml",
        ),
    ),
    DocumentationContract(
        path="docs/ROLLBACK_PLAN.md",
        required_phrases=("ENABLE_SCHEDULER=false", "backup/restore"),
        forbidden_phrases=("Koyeb/Vercel", "alembic downgrade [VERSION_ID]"),
    ),
    DocumentationContract(
        path="docs/architecture/database_schema_overview.md",
        required_phrases=(
            "One-step forward/rollback smoke",
            "backup/restore is the primary rollback path",
        ),
    ),
    DocumentationContract(
        path="docs/architecture/failover.md",
        required_phrases=("Cloudflare", "RDS", "disaster-recovery-drill.yml"),
        forbidden_phrases=("Route 53",),
    ),
    DocumentationContract(
        path="docs/runbooks/disaster_recovery.md",
        required_phrases=(
            "AWS RDS",
            "Cloudflare",
            "disaster-recovery-drill.yml",
            "koyeb-worker.yaml",
        ),
        forbidden_phrases=("Supabase",),
    ),
    DocumentationContract(
        path="docs/runbooks/incident_response.md",
        required_phrases=(
            "Settings -> Notifications",
            "strict SaaS mode",
        ),
        forbidden_phrases=("specified in `SLACK_CHANNEL_ID`",),
    ),
    DocumentationContract(
        path="docs/runbooks/production_env_checklist.md",
        required_phrases=(
            "SENTRY_DSN=https://",
            "OTEL_EXPORTER_OTLP_ENDPOINT=https://",
            "EXPOSE_API_DOCUMENTATION_PUBLICLY=false",
        ),
        forbidden_phrases=("Optional but recommended: `SENTRY_DSN",),
    ),
    DocumentationContract(
        path="docs/integrations/workflow_automation.md",
        required_phrases=(
            "env channel routing (`SLACK_CHANNEL_ID`) is blocked",
            "self-host or break-glass-only paths",
        ),
    ),
)


def verify_contracts(*, root: Path) -> list[str]:
    errors: list[str] = []
    for contract in DOCUMENTATION_CONTRACTS:
        target = root / contract.path
        if not target.exists():
            errors.append(f"missing file: {contract.path}")
            continue

        text = target.read_text(encoding="utf-8")
        for phrase in contract.required_phrases:
            if phrase not in text:
                errors.append(f"{contract.path}: missing required phrase {phrase!r}")
        for phrase in contract.forbidden_phrases:
            if phrase in text:
                errors.append(f"{contract.path}: forbidden phrase present {phrase!r}")
    return errors


def main() -> int:
    errors = verify_contracts(root=DEFAULT_ROOT)
    if errors:
        print("Documentation runtime contract violations detected:")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Documentation runtime contract verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
