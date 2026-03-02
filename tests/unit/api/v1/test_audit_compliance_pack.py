import io
import json
import zipfile
import csv
from datetime import datetime, timezone, date
from decimal import Decimal
from uuid import uuid4

import pytest


@pytest.mark.asyncio
async def test_export_compliance_pack_returns_zip(async_client, app, db, test_tenant):
    from app.shared.core.auth import CurrentUser, get_current_user, UserRole
    from app.shared.core.pricing import PricingTier
    from app.models.notification_settings import NotificationSettings
    from app.models.remediation_settings import RemediationSettings
    from app.models.tenant_identity_settings import TenantIdentitySettings
    from app.modules.governance.domain.security.audit_log import (
        AuditEventType,
        AuditLog,
    )

    owner_user = CurrentUser(
        id=uuid4(),
        email="owner@valdrics.io",
        tenant_id=test_tenant.id,
        role=UserRole.OWNER,
        tier=PricingTier.PRO,
    )

    # Seed a log + settings with secrets; export should redact secrets and include only "has_*" flags.
    db.add(
        AuditLog(
            tenant_id=test_tenant.id,
            event_type=AuditEventType.SETTINGS_UPDATED.value,
            event_timestamp=datetime.now(timezone.utc),
            actor_id=owner_user.id,
            actor_email=owner_user.email,
            request_method="PUT",
            request_path="/api/v1/settings/notifications",
            success=True,
        )
    )
    db.add(
        NotificationSettings(
            tenant_id=test_tenant.id,
            slack_enabled=True,
            jira_enabled=True,
            jira_base_url="https://example.atlassian.net",
            jira_email="owner@valdrics.io",
            jira_project_key="FINOPS",
            jira_issue_type="Task",
            jira_api_token="super-secret-token",
        )
    )
    db.add(
        RemediationSettings(
            tenant_id=test_tenant.id,
            auto_pilot_enabled=False,
            simulation_mode=True,
        )
    )
    db.add(
        TenantIdentitySettings(
            tenant_id=test_tenant.id,
            sso_enabled=True,
            allowed_email_domains=["valdrics.io"],
            scim_enabled=False,
        )
    )
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: owner_user
    try:
        resp = await async_client.get("/api/v1/audit/compliance-pack")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    assert resp.headers.get("content-type", "").startswith("application/zip")
    assert "attachment" in (resp.headers.get("content-disposition") or "").lower()

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = set(zf.namelist())
    assert "manifest.json" in names
    assert "audit_logs.csv" in names
    assert "notification_settings.json" in names
    assert "remediation_settings.json" in names
    assert "identity_settings.json" in names
    assert "integration_acceptance_evidence.json" in names
    assert "acceptance_kpis_evidence.json" in names
    assert "performance_load_test_evidence.json" in names
    assert "ingestion_soak_evidence.json" in names
    assert "partitioning_evidence.json" in names
    assert "quarterly_commercial_proof_evidence.json" in names
    assert "identity_smoke_evidence.json" in names
    assert "sso_federation_validation_evidence.json" in names
    assert "tenant_isolation_evidence.json" in names
    assert "carbon_assurance_evidence.json" in names
    assert "carbon_factor_sets.json" in names
    assert "carbon_factor_update_logs.json" in names
    assert "job_slo_evidence.json" in names
    assert "docs/integrations/scim.md" in names
    assert "docs/integrations/idp_reference_configs.md" in names
    assert "docs/integrations/sso.md" in names
    assert "docs/integrations/microsoft_teams.md" in names
    assert "docs/compliance/compliance_pack.md" in names
    assert "docs/ops/acceptance_evidence_capture.md" in names
    assert "docs/runbooks/month_end_close.md" in names
    assert "docs/runbooks/tenant_data_lifecycle.md" in names
    assert "docs/runbooks/partition_maintenance.md" in names
    assert "docs/licensing.md" in names
    assert "LICENSE" in names
    assert "TRADEMARK_POLICY.md" in names
    assert "COMMERCIAL_LICENSE.md" in names

    manifest = json.loads(zf.read("manifest.json").decode("utf-8"))
    assert manifest["tenant_id"] == str(test_tenant.id)
    assert manifest["actor_email"] == owner_user.email
    assert "factor_sets_count" in manifest["carbon_factors"]
    assert "update_logs_count" in manifest["carbon_factors"]

    factor_sets = json.loads(zf.read("carbon_factor_sets.json").decode("utf-8"))
    factor_updates = json.loads(
        zf.read("carbon_factor_update_logs.json").decode("utf-8")
    )
    assert isinstance(factor_sets, list)
    assert isinstance(factor_updates, list)
    if factor_sets:
        assert "factors_checksum_sha256" in factor_sets[0]

    notif_snapshot = json.loads(zf.read("notification_settings.json").decode("utf-8"))
    assert notif_snapshot["exists"] is True
    assert notif_snapshot["jira_enabled"] is True
    assert notif_snapshot["has_jira_api_token"] is True
    assert notif_snapshot["teams_enabled"] is False
    assert notif_snapshot["has_teams_webhook_url"] is False
    assert "jira_api_token" not in notif_snapshot

    identity_snapshot = json.loads(zf.read("identity_settings.json").decode("utf-8"))
    assert identity_snapshot["exists"] is True
    assert identity_snapshot["sso_enabled"] is True
    assert identity_snapshot["allowed_email_domains"] == ["valdrics.io"]
    assert identity_snapshot["has_scim_token"] is False
    assert identity_snapshot["scim_group_mappings"] == []
    assert "scim_bearer_token" not in identity_snapshot

    acceptance_kpi_evidence = json.loads(
        zf.read("acceptance_kpis_evidence.json").decode("utf-8")
    )
    assert isinstance(acceptance_kpi_evidence, list)


@pytest.mark.asyncio
async def test_export_compliance_pack_can_include_focus_export(
    async_client, app, db, test_tenant
):
    from app.shared.core.auth import CurrentUser, get_current_user, UserRole
    from app.shared.core.pricing import PricingTier
    from app.models.aws_connection import AWSConnection
    from app.models.cloud import CloudAccount, CostRecord
    from app.modules.reporting.domain.focus_export import FOCUS_V13_CORE_COLUMNS

    owner_user = CurrentUser(
        id=uuid4(),
        email="owner-focus@valdrics.io",
        tenant_id=test_tenant.id,
        role=UserRole.OWNER,
        tier=PricingTier.PRO,
    )

    account_id = uuid4()
    db.add(
        AWSConnection(
            id=account_id,
            tenant_id=test_tenant.id,
            aws_account_id="123456789012",
            role_arn="arn:aws:iam::123456789012:role/ValdricsReadOnly",
            external_id="vx-test-external-id",
            region="us-east-1",
            status="active",
        )
    )
    db.add(
        CloudAccount(
            id=account_id,
            tenant_id=test_tenant.id,
            provider="aws",
            name="Prod AWS",
            is_active=True,
        )
    )
    record_day = date.today()
    db.add(
        CostRecord(
            id=uuid4(),
            tenant_id=test_tenant.id,
            account_id=account_id,
            service="AmazonEC2",
            region="us-east-1",
            usage_type="BoxUsage:t3.micro",
            canonical_charge_category="compute",
            canonical_charge_subcategory="runtime",
            canonical_mapping_version="focus-1.3-v1",
            cost_usd=Decimal("10.50"),
            amount_raw=Decimal("10.50"),
            currency="USD",
            carbon_kg=None,
            is_preliminary=False,
            cost_status="FINAL",
            reconciliation_run_id=None,
            ingestion_metadata={"tags": {"env": "prod"}},
            attribution_id=None,
            allocated_to=None,
            recorded_at=record_day,
            timestamp=datetime(
                record_day.year, record_day.month, record_day.day, tzinfo=timezone.utc
            ),
        )
    )
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: owner_user
    try:
        resp = await async_client.get(
            "/api/v1/audit/compliance-pack?include_focus_export=true&focus_max_rows=100"
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200
    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    focus_csv = zf.read("exports/focus-v1.3-core.csv").decode("utf-8")
    rows = list(csv.reader(io.StringIO(focus_csv)))
    assert rows[0] == FOCUS_V13_CORE_COLUMNS
    assert len(rows) >= 2
    header = rows[0]
    billing_idx = header.index("BillingAccountId")
    assert any(r[billing_idx] == "123456789012" for r in rows[1:])


@pytest.mark.asyncio
async def test_export_compliance_pack_can_include_savings_proof_and_close_package(
    async_client, app, db, test_tenant
):
    from app.shared.core.auth import CurrentUser, get_current_user, UserRole
    from app.shared.core.pricing import PricingTier
    from app.models.cloud import CloudAccount, CostRecord
    from app.models.optimization import (
        CommitmentTerm,
        OptimizationStrategy,
        PaymentOption,
        StrategyRecommendation,
        StrategyType,
    )
    from app.models.remediation import (
        RemediationAction,
        RemediationRequest,
        RemediationStatus,
    )
    from app.models.tenant import User

    owner_user = CurrentUser(
        id=uuid4(),
        email="owner-pack@valdrics.io",
        tenant_id=test_tenant.id,
        role=UserRole.OWNER,
        tier=PricingTier.PRO,
    )

    requester_id = uuid4()
    db.add(
        User(
            id=requester_id,
            tenant_id=test_tenant.id,
            email="requester-pack@valdrics.io",
            role=UserRole.OWNER,
        )
    )

    strategy_id = uuid4()
    db.add(
        OptimizationStrategy(
            id=strategy_id,
            name="Compute Savings Plan",
            description="test strategy",
            type=StrategyType.SAVINGS_PLAN.value,
            provider="aws",
            config={},
            is_active=True,
        )
    )
    db.add(
        StrategyRecommendation(
            id=uuid4(),
            tenant_id=test_tenant.id,
            strategy_id=strategy_id,
            resource_type="Compute Savings Plan",
            region="Global",
            term=CommitmentTerm.ONE_YEAR.value,
            payment_option=PaymentOption.NO_UPFRONT.value,
            upfront_cost=Decimal("0.00"),
            monthly_recurring_cost=Decimal("0.00"),
            estimated_monthly_savings=Decimal("50.00"),
            estimated_monthly_savings_low=Decimal("40.00"),
            estimated_monthly_savings_high=Decimal("60.00"),
            roi_percentage=Decimal("10.00"),
            break_even_months=Decimal("0.00"),
            confidence_score=Decimal("0.95"),
            status="open",
            applied_at=None,
        )
    )
    db.add(
        RemediationRequest(
            id=uuid4(),
            tenant_id=test_tenant.id,
            resource_id="i-savings-pack",
            resource_type="ec2_instance",
            provider="aws",
            region="us-east-1",
            action=RemediationAction.STOP_INSTANCE,
            status=RemediationStatus.PENDING,
            requested_by_user_id=requester_id,
            estimated_monthly_savings=Decimal("25.00"),
        )
    )

    account_id = uuid4()
    db.add(
        CloudAccount(
            id=account_id,
            tenant_id=test_tenant.id,
            provider="aws",
            name="Pack AWS",
            is_active=True,
        )
    )

    record_day = date.today()
    db.add(
        CostRecord(
            id=uuid4(),
            tenant_id=test_tenant.id,
            account_id=account_id,
            service="AmazonEC2",
            region="us-east-1",
            usage_type="BoxUsage:t3.micro",
            canonical_charge_category="compute",
            canonical_charge_subcategory="runtime",
            canonical_mapping_version="focus-1.3-v1",
            cost_usd=Decimal("10.00"),
            amount_raw=Decimal("10.00"),
            currency="USD",
            carbon_kg=None,
            is_preliminary=False,
            cost_status="FINAL",
            reconciliation_run_id=None,
            ingestion_metadata={"source_adapter": "cur"},
            attribution_id=None,
            allocated_to=None,
            recorded_at=record_day,
            timestamp=datetime(
                record_day.year, record_day.month, record_day.day, tzinfo=timezone.utc
            ),
        )
    )
    await db.commit()

    app.dependency_overrides[get_current_user] = lambda: owner_user
    try:
        resp = await async_client.get(
            "/api/v1/audit/compliance-pack"
            f"?include_savings_proof=true&savings_start_date={record_day.isoformat()}&savings_end_date={record_day.isoformat()}"
            f"&include_realized_savings=true&realized_start_date={record_day.isoformat()}&realized_end_date={record_day.isoformat()}"
            f"&include_close_package=true&close_start_date={record_day.isoformat()}&close_end_date={record_day.isoformat()}"
            "&close_max_restatements=0"
        )
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert resp.status_code == 200

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = set(zf.namelist())
    assert "exports/savings-proof.json" in names
    assert "exports/savings-proof.csv" in names
    assert "exports/savings-proof-drilldown-strategy-type.json" in names
    assert "exports/savings-proof-drilldown-strategy-type.csv" in names
    assert "exports/savings-proof-drilldown-remediation-action.json" in names
    assert "exports/savings-proof-drilldown-remediation-action.csv" in names
    assert "exports/realized-savings.json" in names
    assert "exports/realized-savings.csv" in names
    assert "exports/close-package.json" in names
    assert "exports/close-package.csv" in names

    savings_payload = json.loads(zf.read("exports/savings-proof.json").decode("utf-8"))
    assert savings_payload["open_recommendations"] >= 1
    assert savings_payload["pending_remediations"] >= 1

    drill_payload = json.loads(
        zf.read("exports/savings-proof-drilldown-strategy-type.json").decode("utf-8")
    )
    assert drill_payload["dimension"] == "strategy_type"
    assert isinstance(drill_payload["buckets"], list)

    close_payload = json.loads(zf.read("exports/close-package.json").decode("utf-8"))
    assert close_payload["close_status"] in {"ready", "blocked_preliminary_data"}

    realized_payload = json.loads(
        zf.read("exports/realized-savings.json").decode("utf-8")
    )
    assert isinstance(realized_payload, list)
