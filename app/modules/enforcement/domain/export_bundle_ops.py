from __future__ import annotations

from collections.abc import Callable
import csv
from datetime import datetime
from decimal import Decimal
import hashlib
import hmac
import io
import json
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.enforcement import EnforcementApprovalRequest, EnforcementDecision


def render_decisions_csv(
    decisions: list[EnforcementDecision],
    *,
    computed_context_snapshot_fn: Callable[[dict[str, Any] | None], dict[str, Any]],
    sanitize_csv_cell_fn: Callable[[Any], str],
    normalize_policy_document_schema_version_fn: Callable[[str | None], str],
    normalize_policy_document_sha256_fn: Callable[[str | None], str],
    to_decimal_fn: Callable[[Any], Decimal],
    iso_or_empty_fn: Callable[[datetime | None], str],
    json_default_fn: Callable[[Any], Any],
) -> str:
    headers = [
        "decision_id",
        "source",
        "environment",
        "project_id",
        "action",
        "resource_reference",
        "decision",
        "reason_codes",
        "policy_version",
        "policy_document_schema_version",
        "policy_document_sha256",
        "computed_context_version",
        "computed_context_generated_at",
        "computed_context_month_start",
        "computed_context_month_end",
        "computed_context_month_elapsed_days",
        "computed_context_month_total_days",
        "computed_context_observed_cost_days",
        "computed_context_latest_cost_date",
        "computed_context_data_source_mode",
        "request_fingerprint",
        "idempotency_key",
        "estimated_monthly_delta_usd",
        "estimated_hourly_delta_usd",
        "allocation_available_usd",
        "credits_available_usd",
        "reserved_allocation_usd",
        "reserved_credit_usd",
        "reservation_active",
        "approval_required",
        "approval_token_issued",
        "token_expires_at",
        "created_by_user_id",
        "created_at",
        "request_payload",
        "response_payload",
    ]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(headers)
    for decision in decisions:
        context_snapshot = computed_context_snapshot_fn(decision.response_payload)
        writer.writerow(
            [
                sanitize_csv_cell_fn(decision.id),
                sanitize_csv_cell_fn(decision.source.value),
                sanitize_csv_cell_fn(decision.environment),
                sanitize_csv_cell_fn(decision.project_id),
                sanitize_csv_cell_fn(decision.action),
                sanitize_csv_cell_fn(decision.resource_reference),
                sanitize_csv_cell_fn(decision.decision.value),
                sanitize_csv_cell_fn(
                    json.dumps(
                        list(decision.reason_codes or []),
                        separators=(",", ":"),
                    )
                ),
                sanitize_csv_cell_fn(int(decision.policy_version)),
                sanitize_csv_cell_fn(
                    normalize_policy_document_schema_version_fn(
                        decision.policy_document_schema_version
                    )
                ),
                sanitize_csv_cell_fn(
                    normalize_policy_document_sha256_fn(decision.policy_document_sha256)
                ),
                sanitize_csv_cell_fn(context_snapshot["context_version"]),
                sanitize_csv_cell_fn(context_snapshot["generated_at"]),
                sanitize_csv_cell_fn(context_snapshot["month_start"]),
                sanitize_csv_cell_fn(context_snapshot["month_end"]),
                sanitize_csv_cell_fn(context_snapshot["month_elapsed_days"]),
                sanitize_csv_cell_fn(context_snapshot["month_total_days"]),
                sanitize_csv_cell_fn(context_snapshot["observed_cost_days"]),
                sanitize_csv_cell_fn(context_snapshot["latest_cost_date"]),
                sanitize_csv_cell_fn(context_snapshot["data_source_mode"]),
                sanitize_csv_cell_fn(decision.request_fingerprint),
                sanitize_csv_cell_fn(decision.idempotency_key),
                sanitize_csv_cell_fn(to_decimal_fn(decision.estimated_monthly_delta_usd)),
                sanitize_csv_cell_fn(to_decimal_fn(decision.estimated_hourly_delta_usd)),
                sanitize_csv_cell_fn(
                    to_decimal_fn(decision.allocation_available_usd)
                    if decision.allocation_available_usd is not None
                    else ""
                ),
                sanitize_csv_cell_fn(
                    to_decimal_fn(decision.credits_available_usd)
                    if decision.credits_available_usd is not None
                    else ""
                ),
                sanitize_csv_cell_fn(to_decimal_fn(decision.reserved_allocation_usd)),
                sanitize_csv_cell_fn(to_decimal_fn(decision.reserved_credit_usd)),
                sanitize_csv_cell_fn(bool(decision.reservation_active)),
                sanitize_csv_cell_fn(bool(decision.approval_required)),
                sanitize_csv_cell_fn(bool(decision.approval_token_issued)),
                sanitize_csv_cell_fn(iso_or_empty_fn(decision.token_expires_at)),
                sanitize_csv_cell_fn(decision.created_by_user_id or ""),
                sanitize_csv_cell_fn(iso_or_empty_fn(decision.created_at)),
                sanitize_csv_cell_fn(
                    json.dumps(
                        decision.request_payload or {},
                        sort_keys=True,
                        separators=(",", ":"),
                        default=json_default_fn,
                    )
                ),
                sanitize_csv_cell_fn(
                    json.dumps(
                        decision.response_payload or {},
                        sort_keys=True,
                        separators=(",", ":"),
                        default=json_default_fn,
                    )
                ),
            ]
        )
    return out.getvalue()


def render_approvals_csv(
    approvals: list[EnforcementApprovalRequest],
    *,
    sanitize_csv_cell_fn: Callable[[Any], str],
    iso_or_empty_fn: Callable[[datetime | None], str],
) -> str:
    headers = [
        "approval_id",
        "decision_id",
        "status",
        "requested_by_user_id",
        "reviewed_by_user_id",
        "review_notes",
        "routing_rule_id",
        "routing_required_permission",
        "routing_allowed_reviewer_roles",
        "routing_require_requester_reviewer_separation",
        "approval_token_expires_at",
        "approval_token_consumed_at",
        "expires_at",
        "approved_at",
        "denied_at",
        "created_at",
        "updated_at",
    ]
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(headers)
    for approval in approvals:
        routing_trace = (
            approval.routing_trace if isinstance(approval.routing_trace, dict) else {}
        )
        routing_roles = routing_trace.get("allowed_reviewer_roles")
        if not isinstance(routing_roles, list):
            routing_roles = []
        writer.writerow(
            [
                sanitize_csv_cell_fn(approval.id),
                sanitize_csv_cell_fn(approval.decision_id),
                sanitize_csv_cell_fn(approval.status.value),
                sanitize_csv_cell_fn(approval.requested_by_user_id or ""),
                sanitize_csv_cell_fn(approval.reviewed_by_user_id or ""),
                sanitize_csv_cell_fn(approval.review_notes or ""),
                sanitize_csv_cell_fn(approval.routing_rule_id or ""),
                sanitize_csv_cell_fn(routing_trace.get("required_permission") or ""),
                sanitize_csv_cell_fn(",".join(str(role) for role in routing_roles)),
                sanitize_csv_cell_fn(
                    bool(routing_trace.get("require_requester_reviewer_separation"))
                ),
                sanitize_csv_cell_fn(iso_or_empty_fn(approval.approval_token_expires_at)),
                sanitize_csv_cell_fn(
                    iso_or_empty_fn(approval.approval_token_consumed_at)
                ),
                sanitize_csv_cell_fn(iso_or_empty_fn(approval.expires_at)),
                sanitize_csv_cell_fn(iso_or_empty_fn(approval.approved_at)),
                sanitize_csv_cell_fn(iso_or_empty_fn(approval.denied_at)),
                sanitize_csv_cell_fn(iso_or_empty_fn(approval.created_at)),
                sanitize_csv_cell_fn(iso_or_empty_fn(approval.updated_at)),
            ]
        )
    return out.getvalue()


def resolve_manifest_signing_secret(
    *,
    configured_secret: str,
    fallback_secret: str,
) -> str:
    configured = str(configured_secret or "").strip()
    if len(configured) >= 32:
        return configured

    fallback = str(fallback_secret or "").strip()
    if len(fallback) >= 32:
        return fallback

    raise HTTPException(
        status_code=503,
        detail="Export manifest signing key is not configured",
    )


def resolve_manifest_signing_key_id(
    *,
    explicit_key_id: str,
    jwt_signing_key_id: str,
) -> str:
    explicit = str(explicit_key_id or "").strip()
    if explicit:
        return explicit[:64]
    jwt_kid = str(jwt_signing_key_id or "").strip()
    if jwt_kid:
        return jwt_kid[:64]
    return "enforcement-export-hmac-v1"


def build_signed_export_manifest_payload(
    *,
    tenant_id: UUID,
    bundle: Any,
    resolve_signing_secret_fn: Callable[[], str],
    resolve_signing_key_id_fn: Callable[[], str],
    canonical_json_fn: Callable[[dict[str, Any]], str],
) -> dict[str, Any]:
    content_payload: dict[str, Any] = {
        "schema_version": "valdrics.enforcement.export_manifest.v1",
        "tenant_id": str(tenant_id),
        "window_start": bundle.window_start,
        "window_end": bundle.window_end,
        "decision_count_db": int(bundle.decision_count_db),
        "decision_count_exported": int(bundle.decision_count_exported),
        "approval_count_db": int(bundle.approval_count_db),
        "approval_count_exported": int(bundle.approval_count_exported),
        "decisions_sha256": str(bundle.decisions_sha256),
        "approvals_sha256": str(bundle.approvals_sha256),
        "policy_lineage_sha256": str(bundle.policy_lineage_sha256),
        "policy_lineage": list(bundle.policy_lineage),
        "computed_context_lineage_sha256": str(bundle.computed_context_lineage_sha256),
        "computed_context_lineage": list(bundle.computed_context_lineage),
        "parity_ok": bool(bundle.parity_ok),
    }
    canonical_content_json = canonical_json_fn(content_payload)
    content_sha256 = hashlib.sha256(canonical_content_json.encode("utf-8")).hexdigest()
    signing_secret = resolve_signing_secret_fn()
    signature = hmac.new(
        signing_secret.encode("utf-8"),
        canonical_content_json.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    signature_key_id = resolve_signing_key_id_fn()

    return {
        "schema_version": "valdrics.enforcement.export_manifest.v1",
        "generated_at": bundle.generated_at,
        "tenant_id": tenant_id,
        "window_start": bundle.window_start,
        "window_end": bundle.window_end,
        "decision_count_db": bundle.decision_count_db,
        "decision_count_exported": bundle.decision_count_exported,
        "approval_count_db": bundle.approval_count_db,
        "approval_count_exported": bundle.approval_count_exported,
        "decisions_sha256": bundle.decisions_sha256,
        "approvals_sha256": bundle.approvals_sha256,
        "policy_lineage_sha256": bundle.policy_lineage_sha256,
        "policy_lineage": list(bundle.policy_lineage),
        "computed_context_lineage_sha256": bundle.computed_context_lineage_sha256,
        "computed_context_lineage": list(bundle.computed_context_lineage),
        "parity_ok": bundle.parity_ok,
        "content_sha256": content_sha256,
        "signature_algorithm": "hmac-sha256",
        "signature_key_id": signature_key_id,
        "signature": signature,
        "canonical_content_json": canonical_content_json,
    }


async def build_export_bundle_payload(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    window_start: datetime,
    window_end: datetime,
    max_rows: int,
    as_utc_fn: Callable[[datetime], datetime],
    normalize_policy_document_schema_version_fn: Callable[[str | None], str],
    normalize_policy_document_sha256_fn: Callable[[str | None], str],
    computed_context_snapshot_fn: Callable[[dict[str, Any] | None], dict[str, Any]],
    json_default_fn: Callable[[Any], Any],
    render_decisions_csv_fn: Callable[[list[EnforcementDecision]], str],
    render_approvals_csv_fn: Callable[[list[EnforcementApprovalRequest]], str],
    export_events_counter: Any,
    utcnow_fn: Callable[[], datetime],
) -> dict[str, Any]:
    bounded_max_rows = int(max_rows)
    if bounded_max_rows < 1:
        raise HTTPException(status_code=422, detail="max_rows must be >= 1")
    if bounded_max_rows > 50000:
        raise HTTPException(status_code=422, detail="max_rows must be <= 50000")

    normalized_start = as_utc_fn(window_start)
    normalized_end = as_utc_fn(window_end)
    if normalized_start >= normalized_end:
        raise HTTPException(
            status_code=422,
            detail="window_start must be before window_end",
        )

    decision_count_db = int(
        (
            await db.execute(
                select(func.count(EnforcementDecision.id))
                .where(EnforcementDecision.tenant_id == tenant_id)
                .where(EnforcementDecision.created_at >= normalized_start)
                .where(EnforcementDecision.created_at <= normalized_end)
            )
        ).scalar_one()
        or 0
    )
    if decision_count_db > bounded_max_rows:
        export_events_counter.labels(
            artifact="bundle",
            outcome="rejected_limit",
        ).inc()
        raise HTTPException(
            status_code=422,
            detail=(
                f"Export window exceeds max_rows ({bounded_max_rows}). "
                "Narrow the date range or increase max_rows."
            ),
        )

    decision_rows = await db.execute(
        select(EnforcementDecision)
        .where(EnforcementDecision.tenant_id == tenant_id)
        .where(EnforcementDecision.created_at >= normalized_start)
        .where(EnforcementDecision.created_at <= normalized_end)
        .order_by(EnforcementDecision.created_at.asc(), EnforcementDecision.id.asc())
    )
    decisions = list(decision_rows.scalars().all())
    decision_count_exported = len(decisions)

    approval_count_db = int(
        (
            await db.execute(
                select(func.count(EnforcementApprovalRequest.id))
                .select_from(EnforcementApprovalRequest)
                .join(
                    EnforcementDecision,
                    EnforcementDecision.id == EnforcementApprovalRequest.decision_id,
                )
                .where(EnforcementApprovalRequest.tenant_id == tenant_id)
                .where(EnforcementDecision.tenant_id == tenant_id)
                .where(EnforcementDecision.created_at >= normalized_start)
                .where(EnforcementDecision.created_at <= normalized_end)
            )
        ).scalar_one()
        or 0
    )

    approvals: list[EnforcementApprovalRequest] = []
    if decisions:
        decision_ids = [decision.id for decision in decisions]
        approval_rows = await db.execute(
            select(EnforcementApprovalRequest)
            .where(EnforcementApprovalRequest.tenant_id == tenant_id)
            .where(EnforcementApprovalRequest.decision_id.in_(decision_ids))
            .order_by(
                EnforcementApprovalRequest.created_at.asc(),
                EnforcementApprovalRequest.id.asc(),
            )
        )
        approvals = list(approval_rows.scalars().all())

    policy_lineage_counts: dict[tuple[str, str], int] = {}
    for decision in decisions:
        schema_version = normalize_policy_document_schema_version_fn(
            getattr(decision, "policy_document_schema_version", None)
        )
        policy_hash = normalize_policy_document_sha256_fn(
            getattr(decision, "policy_document_sha256", None)
        )
        key = (schema_version, policy_hash)
        policy_lineage_counts[key] = int(policy_lineage_counts.get(key, 0)) + 1

    policy_lineage: list[dict[str, Any]] = []
    for schema_version, policy_hash in sorted(policy_lineage_counts.keys()):
        policy_lineage.append(
            {
                "policy_document_schema_version": schema_version,
                "policy_document_sha256": policy_hash,
                "decision_count": int(policy_lineage_counts[(schema_version, policy_hash)]),
            }
        )
    policy_lineage_json = json.dumps(
        policy_lineage,
        sort_keys=True,
        separators=(",", ":"),
        default=json_default_fn,
    )
    policy_lineage_sha256 = hashlib.sha256(policy_lineage_json.encode("utf-8")).hexdigest()

    computed_context_lineage_counts: dict[
        tuple[str, str, str, str, int, int, int, str, str],
        int,
    ] = {}
    for decision in decisions:
        snapshot = computed_context_snapshot_fn(decision.response_payload)
        context_key = (
            str(snapshot["context_version"]),
            str(snapshot["generated_at"]),
            str(snapshot["month_start"]),
            str(snapshot["month_end"]),
            int(snapshot["month_elapsed_days"]),
            int(snapshot["month_total_days"]),
            int(snapshot["observed_cost_days"]),
            str(snapshot["latest_cost_date"]),
            str(snapshot["data_source_mode"]),
        )
        computed_context_lineage_counts[context_key] = (
            int(computed_context_lineage_counts.get(context_key, 0)) + 1
        )

    computed_context_lineage: list[dict[str, Any]] = []
    for context_key in sorted(computed_context_lineage_counts.keys()):
        (
            context_version,
            generated_at,
            month_start,
            month_end,
            month_elapsed_days,
            month_total_days,
            observed_cost_days,
            latest_cost_date,
            data_source_mode,
        ) = context_key
        computed_context_lineage.append(
            {
                "context_version": context_version,
                "generated_at": generated_at,
                "month_start": month_start,
                "month_end": month_end,
                "month_elapsed_days": month_elapsed_days,
                "month_total_days": month_total_days,
                "observed_cost_days": observed_cost_days,
                "latest_cost_date": latest_cost_date,
                "data_source_mode": data_source_mode,
                "decision_count": int(computed_context_lineage_counts[context_key]),
            }
        )
    computed_context_lineage_json = json.dumps(
        computed_context_lineage,
        sort_keys=True,
        separators=(",", ":"),
        default=json_default_fn,
    )
    computed_context_lineage_sha256 = hashlib.sha256(
        computed_context_lineage_json.encode("utf-8")
    ).hexdigest()

    approval_count_exported = len(approvals)
    decisions_csv = render_decisions_csv_fn(decisions)
    approvals_csv = render_approvals_csv_fn(approvals)
    decisions_sha256 = hashlib.sha256(decisions_csv.encode("utf-8")).hexdigest()
    approvals_sha256 = hashlib.sha256(approvals_csv.encode("utf-8")).hexdigest()
    parity_ok = (
        decision_count_db == decision_count_exported
        and approval_count_db == approval_count_exported
    )
    export_events_counter.labels(
        artifact="bundle",
        outcome=("success" if parity_ok else "mismatch"),
    ).inc()

    return {
        "generated_at": utcnow_fn(),
        "window_start": normalized_start,
        "window_end": normalized_end,
        "decision_count_db": decision_count_db,
        "decision_count_exported": decision_count_exported,
        "approval_count_db": approval_count_db,
        "approval_count_exported": approval_count_exported,
        "decisions_sha256": decisions_sha256,
        "approvals_sha256": approvals_sha256,
        "policy_lineage_sha256": policy_lineage_sha256,
        "policy_lineage": policy_lineage,
        "computed_context_lineage_sha256": computed_context_lineage_sha256,
        "computed_context_lineage": computed_context_lineage,
        "decisions_csv": decisions_csv,
        "approvals_csv": approvals_csv,
        "parity_ok": parity_ok,
    }
