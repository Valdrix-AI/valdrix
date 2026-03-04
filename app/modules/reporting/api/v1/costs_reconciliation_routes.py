from __future__ import annotations

import csv
import io
from collections.abc import AsyncIterator, Callable
from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.governance.domain.security.audit_log import AuditEventType, AuditLogger
from app.modules.reporting.api.v1.costs_models import (
    ProviderInvoiceStatusUpdateRequest,
    ProviderInvoiceUpsertRequest,
)
from app.modules.reporting.domain.focus_export import (
    FOCUS_V13_CORE_COLUMNS,
    FocusV13ExportService,
)
from app.modules.reporting.domain.reconciliation import CostReconciliationService
from app.shared.core.auth import CurrentUser


async def get_reconciliation_close_package_impl(
    *,
    start_date: date,
    end_date: date,
    provider: str | None,
    response_format: str,
    enforce_finalized: bool,
    user: CurrentUser,
    db: AsyncSession,
    require_tenant_id: Callable[[CurrentUser], UUID],
    normalize_provider_filter: Callable[[str | None], str | None],
) -> Any:
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    tenant_id = require_tenant_id(user)
    normalized_provider = normalize_provider_filter(provider)
    service = CostReconciliationService(db)
    try:
        package = await service.generate_close_package(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            enforce_finalized=enforce_finalized,
            provider=normalized_provider,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    if response_format == "csv":
        filename = (
            f"close-package-{start_date.isoformat()}-{end_date.isoformat()}"
            f"-{normalized_provider or 'all'}.csv"
        )
        return Response(
            content=package["csv"],
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return package


async def get_restatement_history_impl(
    *,
    start_date: date,
    end_date: date,
    provider: str | None,
    response_format: str,
    user: CurrentUser,
    db: AsyncSession,
    require_tenant_id: Callable[[CurrentUser], UUID],
    normalize_provider_filter: Callable[[str | None], str | None],
    get_settings: Callable[[], Any],
) -> Any:
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    settings = get_settings()
    window_days = (end_date - start_date).days + 1
    if window_days > settings.FOCUS_EXPORT_MAX_DAYS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Date window exceeds export limit ({settings.FOCUS_EXPORT_MAX_DAYS} days). "
                "Use a smaller range."
            ),
        )

    tenant_id = require_tenant_id(user)
    normalized_provider = normalize_provider_filter(provider)
    service = CostReconciliationService(db)
    export_csv = response_format == "csv"
    payload = await service.get_restatement_history(
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        export_csv=export_csv,
        provider=normalized_provider,
    )

    if export_csv:
        filename = (
            f"restatements-{start_date.isoformat()}-{end_date.isoformat()}"
            f"-{normalized_provider or 'all'}.csv"
        )
        return Response(
            content=payload["csv"],
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return payload


async def get_restatement_runs_impl(
    *,
    start_date: date,
    end_date: date,
    provider: str | None,
    response_format: str,
    user: CurrentUser,
    db: AsyncSession,
    require_tenant_id: Callable[[CurrentUser], UUID],
    normalize_provider_filter: Callable[[str | None], str | None],
) -> Any:
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    tenant_id = require_tenant_id(user)
    normalized_provider = normalize_provider_filter(provider)
    service = CostReconciliationService(db)
    export_csv = response_format == "csv"
    payload = await service.get_restatement_runs(
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
        export_csv=export_csv,
        provider=normalized_provider,
    )

    if export_csv:
        filename = (
            f"restatement-runs-{start_date.isoformat()}-{end_date.isoformat()}"
            f"-{normalized_provider or 'all'}.csv"
        )
        return Response(
            content=payload["csv"],
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    return payload


async def list_provider_invoices_impl(
    *,
    provider: str | None,
    start_date: date | None,
    end_date: date | None,
    user: CurrentUser,
    db: AsyncSession,
    require_tenant_id: Callable[[CurrentUser], UUID],
    normalize_provider_filter: Callable[[str | None], str | None],
) -> Any:
    tenant_id = require_tenant_id(user)
    service = CostReconciliationService(db)
    invoices = await service.list_invoices(
        tenant_id=tenant_id,
        provider=normalize_provider_filter(provider) if provider else None,
        start_date=start_date,
        end_date=end_date,
    )
    return [
        {
            "id": str(inv.id),
            "provider": inv.provider,
            "period_start": inv.period_start.isoformat(),
            "period_end": inv.period_end.isoformat(),
            "invoice_number": inv.invoice_number,
            "currency": inv.currency,
            "total_amount": float(inv.total_amount or 0),
            "total_amount_usd": float(inv.total_amount_usd or 0),
            "status": inv.status,
            "notes": inv.notes,
            "updated_at": inv.updated_at.isoformat() if inv.updated_at else None,
        }
        for inv in invoices
    ]


async def upsert_provider_invoice_impl(
    *,
    request: Request,
    payload: ProviderInvoiceUpsertRequest,
    user: CurrentUser,
    db: AsyncSession,
    require_tenant_id: Callable[[CurrentUser], UUID],
) -> Any:
    if payload.start_date > payload.end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    tenant_id = require_tenant_id(user)
    service = CostReconciliationService(db)
    try:
        invoice = await service.upsert_invoice(
            tenant_id=tenant_id,
            provider=payload.provider,
            start_date=payload.start_date,
            end_date=payload.end_date,
            currency=payload.currency,
            total_amount=Decimal(str(payload.total_amount or 0)),
            invoice_number=payload.invoice_number,
            status=payload.status,
            notes=payload.notes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    audit = AuditLogger(db, tenant_id=tenant_id)
    await audit.log(
        event_type=AuditEventType.INVOICE_UPSERTED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="provider_invoice",
        resource_id=str(invoice.id),
        details={
            "provider": invoice.provider,
            "period_start": invoice.period_start.isoformat(),
            "period_end": invoice.period_end.isoformat(),
            "currency": invoice.currency,
            "total_amount_usd": float(invoice.total_amount_usd or 0),
            "status": invoice.status,
        },
        request_method=request.method,
        request_path=str(request.url.path),
    )
    await db.commit()

    return {
        "status": "success",
        "invoice": {
            "id": str(invoice.id),
            "provider": invoice.provider,
            "period_start": invoice.period_start.isoformat(),
            "period_end": invoice.period_end.isoformat(),
            "invoice_number": invoice.invoice_number,
            "currency": invoice.currency,
            "total_amount": float(invoice.total_amount or 0),
            "total_amount_usd": float(invoice.total_amount_usd or 0),
            "status": invoice.status,
            "notes": invoice.notes,
            "updated_at": invoice.updated_at.isoformat()
            if invoice.updated_at
            else None,
        },
    }


async def update_provider_invoice_status_impl(
    *,
    request: Request,
    invoice_id: UUID,
    payload: ProviderInvoiceStatusUpdateRequest,
    user: CurrentUser,
    db: AsyncSession,
    require_tenant_id: Callable[[CurrentUser], UUID],
) -> Any:
    tenant_id = require_tenant_id(user)
    service = CostReconciliationService(db)
    updated = await service.update_invoice_status(
        tenant_id=tenant_id,
        invoice_id=invoice_id,
        status=payload.status,
        notes=payload.notes,
    )
    if not updated:
        raise HTTPException(status_code=404, detail="Invoice not found")

    audit = AuditLogger(db, tenant_id=tenant_id)
    await audit.log(
        event_type=AuditEventType.INVOICE_STATUS_UPDATED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="provider_invoice",
        resource_id=str(invoice_id),
        details={"status": updated.status},
        request_method=request.method,
        request_path=str(request.url.path),
    )
    await db.commit()

    return {
        "status": "success",
        "invoice_id": str(invoice_id),
        "invoice_status": updated.status,
    }


async def delete_provider_invoice_impl(
    *,
    request: Request,
    invoice_id: UUID,
    user: CurrentUser,
    db: AsyncSession,
    require_tenant_id: Callable[[CurrentUser], UUID],
) -> Any:
    tenant_id = require_tenant_id(user)
    service = CostReconciliationService(db)
    deleted = await service.delete_invoice(tenant_id=tenant_id, invoice_id=invoice_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Invoice not found")

    audit = AuditLogger(db, tenant_id=tenant_id)
    await audit.log(
        event_type=AuditEventType.INVOICE_DELETED,
        actor_id=user.id,
        actor_email=user.email,
        resource_type="provider_invoice",
        resource_id=str(invoice_id),
        details={},
        request_method=request.method,
        request_path=str(request.url.path),
    )
    await db.commit()
    return {"status": "deleted", "invoice_id": str(invoice_id)}


async def export_focus_v13_costs_csv_impl(
    *,
    start_date: date,
    end_date: date,
    provider: str | None,
    include_preliminary: bool,
    user: CurrentUser,
    db: AsyncSession,
    require_tenant_id: Callable[[CurrentUser], UUID],
    normalize_provider_filter: Callable[[str | None], str | None],
    sanitize_csv_cell: Callable[[Any], str],
    get_settings: Callable[[], Any],
) -> Any:
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be <= end_date")

    settings = get_settings()
    window_days = (end_date - start_date).days + 1
    if window_days > settings.FOCUS_EXPORT_MAX_DAYS:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Date window exceeds export limit ({settings.FOCUS_EXPORT_MAX_DAYS} days). "
                "Use a smaller range."
            ),
        )

    tenant_id = require_tenant_id(user)
    normalized_provider = normalize_provider_filter(provider)
    service = FocusV13ExportService(db)

    async def _iter_csv() -> AsyncIterator[bytes]:
        out = io.StringIO(newline="")
        writer = csv.writer(out)
        writer.writerow(FOCUS_V13_CORE_COLUMNS)
        yield out.getvalue().encode("utf-8")
        out.seek(0)
        out.truncate(0)

        async for row in service.export_rows(
            tenant_id=tenant_id,
            start_date=start_date,
            end_date=end_date,
            provider=normalized_provider,
            include_preliminary=include_preliminary,
        ):
            writer.writerow(
                [sanitize_csv_cell(row.get(col, "")) for col in FOCUS_V13_CORE_COLUMNS]
            )
            yield out.getvalue().encode("utf-8")
            out.seek(0)
            out.truncate(0)

    filename = (
        f"focus-v1.3-core-{start_date.isoformat()}-{end_date.isoformat()}"
        f"-{normalized_provider or 'all'}.csv"
    )
    return StreamingResponse(
        _iter_csv(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
