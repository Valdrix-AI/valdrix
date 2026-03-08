from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_codeowners_exists_and_assigns_default_owner() -> None:
    codeowners = (REPO_ROOT / "CODEOWNERS").read_text(encoding="utf-8")

    assert "* @daretechie" in codeowners


def test_soc2_controls_reference_current_artifacts() -> None:
    text = (REPO_ROOT / "docs/SOC2_CONTROLS.md").read_text(encoding="utf-8")

    assert "CODEOWNERS" in text
    assert "`app/shared/core/logging.py`" in text
    assert "`docs/runbooks/disaster_recovery.md`" in text
    assert "`docs/FULL_CODEBASE_AUDIT.md`" in text
    assert "`app/core/logging.py`" not in text
    assert "`docs/DR_RUNBOOK.md`" not in text
    assert "`technical_due_diligence.md`" not in text


def test_retention_policy_matches_supported_erasure_controls() -> None:
    text = (REPO_ROOT / "docs/policies/data_retention.md").read_text(
        encoding="utf-8"
    )

    assert "/api/v1/audit/data-erasure-request" in text
    assert "background job retention" in text.lower()
    assert "plan-aware retention purge" in text
    assert "resource_type=cost_records_retention" in text


def test_rollback_and_recovery_docs_match_supported_platforms() -> None:
    rollback = (REPO_ROOT / "docs/ROLLBACK_PLAN.md").read_text(encoding="utf-8")
    recovery = (REPO_ROOT / "docs/runbooks/disaster_recovery.md").read_text(
        encoding="utf-8"
    )
    failover = (REPO_ROOT / "docs/architecture/failover.md").read_text(
        encoding="utf-8"
    )
    deployment = (REPO_ROOT / "docs/DEPLOYMENT.md").read_text(encoding="utf-8")
    capacity = (REPO_ROOT / "docs/CAPACITY_PLAN.md").read_text(encoding="utf-8")
    db_overview = (
        REPO_ROOT / "docs/architecture/database_schema_overview.md"
    ).read_text(encoding="utf-8")

    assert "ENABLE_SCHEDULER=false" in rollback
    assert "backup/restore" in rollback.lower()
    assert "Koyeb/Vercel" not in rollback
    assert "AWS RDS" in recovery
    assert "Cloudflare" in recovery
    assert "disaster-recovery-drill.yml" in recovery
    assert "Supabase" not in recovery
    assert "Cloudflare" in failover
    assert "RDS" in failover
    assert "disaster-recovery-drill.yml" in failover
    assert "Route 53" not in failover
    assert "Supported deployment profiles" in deployment
    assert "Helm + Terraform (AWS/EKS)" in deployment
    assert "Cloudflare Pages + Koyeb" in deployment
    assert "koyeb-worker.yaml" in deployment
    assert "Helm + Terraform (AWS/EKS)" in capacity
    assert "Cloudflare Pages + Koyeb" in capacity
    assert "koyeb-worker.yaml" in capacity
    assert "One-step forward/rollback smoke" in db_overview
    assert "backup/restore is the primary rollback path" in db_overview

    dr_workflow = (
        REPO_ROOT / ".github/workflows/disaster-recovery-drill.yml"
    ).read_text(encoding="utf-8")
    assert "workflow_dispatch:" in dr_workflow
    assert "schedule:" in dr_workflow
    assert "scripts/run_disaster_recovery_drill.py" in dr_workflow
    assert 'ENVIRONMENT: "staging"' in dr_workflow
    assert "postgres:16.8-alpine" in dr_workflow
    assert "uv run alembic upgrade head" in dr_workflow
    assert "uv run celery -A app.shared.core.celery_app:celery_app worker -l info" in dr_workflow


def test_architecture_overview_does_not_overclaim_domain_purity_or_raw_k8s() -> None:
    text = (REPO_ROOT / "docs/architecture/overview.md").read_text(
        encoding="utf-8"
    )

    assert "Zero external dependencies" not in text
    assert "`k8s/`" not in text
    assert "Helm chart" in text
    assert "boundary target" in text


def test_incident_and_production_runbooks_match_strict_saas_observability_contract() -> None:
    incident = (REPO_ROOT / "docs/runbooks/incident_response.md").read_text(
        encoding="utf-8"
    )
    production = (
        REPO_ROOT / "docs/runbooks/production_env_checklist.md"
    ).read_text(encoding="utf-8")
    workflow = (REPO_ROOT / "docs/integrations/workflow_automation.md").read_text(
        encoding="utf-8"
    )
    soc2 = (REPO_ROOT / "docs/SOC2_CONTROLS.md").read_text(encoding="utf-8")

    assert "Settings -> Notifications" in incident
    assert "strict SaaS mode" in incident
    assert "specified in `SLACK_CHANNEL_ID`" not in incident
    assert "SENTRY_DSN=https://" in production
    assert "OTEL_EXPORTER_OTLP_ENDPOINT=https://" in production
    assert "EXPOSE_API_DOCUMENTATION_PUBLICLY=false" in production
    assert "Optional but recommended: `SENTRY_DSN" not in production
    assert "env channel routing (`SLACK_CHANNEL_ID`) is blocked" in workflow
    assert "self-host or break-glass-only paths" in workflow
    assert "`app/modules/governance/api/v1/settings/account.py`" in soc2
    assert "| CC6.4 |" in soc2 and "Implemented" in soc2


def test_partition_archival_helpers_match_runtime_maintenance_path() -> None:
    sql_text = (REPO_ROOT / "scripts/archive_partitions.sql").read_text(
        encoding="utf-8"
    )
    script_text = (REPO_ROOT / "scripts/run_archival_setup.py").read_text(
        encoding="utf-8"
    )

    assert "PartitionMaintenanceService" in script_text
    assert "archive_old_partitions" in script_text
    assert "cost_records_archive" in sql_text
    assert "ux_cost_records_archive_id_recorded_at" in sql_text
    assert "RAISE NOTICE" not in sql_text
