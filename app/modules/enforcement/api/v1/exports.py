from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import io
import json
import zipfile

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.enforcement.api.v1.common import tenant_or_403, require_feature_or_403
from app.modules.enforcement.api.v1.schemas import EnforcementExportParityResponse
from app.modules.enforcement.domain.service import EnforcementService
from app.shared.core.auth import CurrentUser, requires_role_with_db_context
from app.shared.core.config import get_settings
from app.shared.core.ops_metrics import ENFORCEMENT_EXPORT_EVENTS_TOTAL
from app.shared.core.pricing import FeatureFlag
from app.shared.db.session import get_db


router = APIRouter(tags=["Enforcement"])


def _export_max_days() -> int:
    raw = getattr(get_settings(), "ENFORCEMENT_EXPORT_MAX_DAYS", 366)
    try:
        max_days = int(raw)
    except (TypeError, ValueError):
        max_days = 366
    return max(1, min(max_days, 3650))


def _export_max_rows() -> int:
    raw = getattr(get_settings(), "ENFORCEMENT_EXPORT_MAX_ROWS", 10000)
    try:
        max_rows = int(raw)
    except (TypeError, ValueError):
        max_rows = 10000
    return max(1, min(max_rows, 50000))


def _resolve_window(
    *,
    start_date: date | None,
    end_date: date | None,
) -> tuple[datetime, datetime]:
    now = datetime.now(timezone.utc)
    normalized_end = end_date or now.date()
    normalized_start = start_date or (normalized_end - timedelta(days=29))
    if normalized_start > normalized_end:
        raise HTTPException(
            status_code=422,
            detail="start_date must be on or before end_date",
        )

    window_days = (normalized_end - normalized_start).days + 1
    if window_days > _export_max_days():
        raise HTTPException(
            status_code=422,
            detail=(
                f"Date window exceeds export limit ({_export_max_days()} days). "
                "Narrow the date range."
            ),
        )

    window_start = datetime.combine(normalized_start, time.min, tzinfo=timezone.utc)
    window_end = datetime.combine(normalized_end, time.max, tzinfo=timezone.utc)
    return window_start, window_end


def _resolve_max_rows(requested: int | None) -> int:
    configured_limit = _export_max_rows()
    if requested is None:
        return configured_limit

    normalized = int(requested)
    if normalized < 1:
        raise HTTPException(status_code=422, detail="max_rows must be >= 1")
    if normalized > configured_limit:
        raise HTTPException(
            status_code=422,
            detail=f"max_rows must be <= {configured_limit}",
        )
    return normalized


@router.get("/exports/parity", response_model=EnforcementExportParityResponse)
async def get_export_parity(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    max_rows: int | None = Query(default=None),
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> EnforcementExportParityResponse:
    await require_feature_or_403(
        user=current_user,
        db=db,
        feature=FeatureFlag.API_ACCESS,
    )
    tenant_id = tenant_or_403(current_user)
    window_start, window_end = _resolve_window(start_date=start_date, end_date=end_date)
    service = EnforcementService(db)
    bundle = await service.build_export_bundle(
        tenant_id=tenant_id,
        window_start=window_start,
        window_end=window_end,
        max_rows=_resolve_max_rows(max_rows),
    )
    signed_manifest = service.build_signed_export_manifest(
        tenant_id=tenant_id,
        bundle=bundle,
    )
    ENFORCEMENT_EXPORT_EVENTS_TOTAL.labels(
        artifact="parity",
        outcome=("success" if bundle.parity_ok else "mismatch"),
    ).inc()
    return EnforcementExportParityResponse(
        generated_at=bundle.generated_at,
        window_start=bundle.window_start,
        window_end=bundle.window_end,
        decision_count_db=bundle.decision_count_db,
        decision_count_exported=bundle.decision_count_exported,
        approval_count_db=bundle.approval_count_db,
        approval_count_exported=bundle.approval_count_exported,
        decisions_sha256=bundle.decisions_sha256,
        approvals_sha256=bundle.approvals_sha256,
        policy_lineage_sha256=bundle.policy_lineage_sha256,
        policy_lineage_entries=len(bundle.policy_lineage),
        computed_context_lineage_sha256=bundle.computed_context_lineage_sha256,
        computed_context_lineage_entries=len(bundle.computed_context_lineage),
        parity_ok=bundle.parity_ok,
        manifest_content_sha256=signed_manifest.content_sha256,
        manifest_signature=signed_manifest.signature,
        manifest_signature_algorithm=signed_manifest.signature_algorithm,
        manifest_signature_key_id=signed_manifest.signature_key_id,
    )


@router.get("/exports/archive", response_model=None)
async def download_export_archive(
    start_date: date | None = Query(default=None),
    end_date: date | None = Query(default=None),
    max_rows: int | None = Query(default=None),
    current_user: CurrentUser = Depends(requires_role_with_db_context("admin")),
    db: AsyncSession = Depends(get_db),
) -> Response:
    await require_feature_or_403(
        user=current_user,
        db=db,
        feature=FeatureFlag.API_ACCESS,
    )
    tenant_id = tenant_or_403(current_user)
    window_start, window_end = _resolve_window(start_date=start_date, end_date=end_date)
    service = EnforcementService(db)
    bundle = await service.build_export_bundle(
        tenant_id=tenant_id,
        window_start=window_start,
        window_end=window_end,
        max_rows=_resolve_max_rows(max_rows),
    )
    signed_manifest = service.build_signed_export_manifest(
        tenant_id=tenant_id,
        bundle=bundle,
    )
    ENFORCEMENT_EXPORT_EVENTS_TOTAL.labels(
        artifact="archive",
        outcome=("success" if bundle.parity_ok else "mismatch"),
    ).inc()
    manifest = signed_manifest.to_payload()

    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(
        archive_buffer,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
    ) as bundle_zip:
        bundle_zip.writestr("manifest.json", json.dumps(manifest, indent=2))
        bundle_zip.writestr("manifest.canonical.json", signed_manifest.canonical_content_json)
        bundle_zip.writestr("manifest.sha256", f"{signed_manifest.content_sha256}\n")
        bundle_zip.writestr("manifest.sig", f"{signed_manifest.signature}\n")
        bundle_zip.writestr("decisions.csv", bundle.decisions_csv)
        bundle_zip.writestr("approvals.csv", bundle.approvals_csv)

    archive_buffer.seek(0)
    filename = (
        f"enforcement-export-{tenant_id}-{bundle.generated_at.strftime('%Y%m%dT%H%M%SZ')}.zip"
    )
    return Response(
        content=archive_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
