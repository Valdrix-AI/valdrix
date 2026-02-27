from datetime import date, datetime
from typing import Annotated, Any, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.governance.api.v1.audit_common import _sanitize_csv_cell
from app.modules.governance.domain.security.compliance_pack_bundle import (
    export_compliance_pack_bundle,
)
from app.shared.core.auth import CurrentUser
from app.shared.core.dependencies import requires_feature
from app.shared.core.pricing import FeatureFlag
from app.shared.db.session import get_db

router = APIRouter(tags=["Audit"])


@router.get("/compliance-pack")
async def export_compliance_pack(
    user: Annotated[
        CurrentUser,
        Depends(
            requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="owner")
        ),
    ],
    db: AsyncSession = Depends(get_db),
    start_date: Optional[datetime] = Query(
        None, description="Start of date range (UTC)"
    ),
    end_date: Optional[datetime] = Query(None, description="End of date range (UTC)"),
    evidence_limit: int = Query(
        200, ge=1, le=2000, description="Max integration evidence records"
    ),
    include_focus_export: bool = Query(
        default=False,
        description="Include a bounded FOCUS v1.3 core cost export CSV inside the compliance pack.",
    ),
    focus_provider: Optional[str] = Query(
        default=None,
        description="Optional provider filter for the bundled FOCUS export (aws|azure|gcp|saas|license|platform|hybrid).",
    ),
    focus_include_preliminary: bool = Query(
        default=False,
        description="Include PRELIMINARY cost records in the bundled FOCUS export (otherwise FINAL only).",
    ),
    focus_max_rows: int = Query(
        default=50000,
        ge=1,
        le=200000,
        description="Maximum number of cost rows to include in the bundled FOCUS export (prevents huge ZIPs).",
    ),
    focus_start_date: Optional[date] = Query(
        default=None,
        description="FOCUS export start date (YYYY-MM-DD). Defaults to last 30 days.",
    ),
    focus_end_date: Optional[date] = Query(
        default=None,
        description="FOCUS export end date (YYYY-MM-DD). Defaults to today.",
    ),
    include_savings_proof: bool = Query(
        default=False,
        description="Include a Savings Proof report (JSON + CSV) inside the compliance pack.",
    ),
    savings_provider: Optional[str] = Query(
        default=None,
        description="Optional provider filter for the bundled Savings Proof report (aws|azure|gcp|saas|license|platform|hybrid).",
    ),
    savings_start_date: Optional[date] = Query(
        default=None,
        description="Savings Proof start date (YYYY-MM-DD). Defaults to last 30 days.",
    ),
    savings_end_date: Optional[date] = Query(
        default=None,
        description="Savings Proof end date (YYYY-MM-DD). Defaults to today.",
    ),
    include_realized_savings: bool = Query(
        default=False,
        description="Include realized savings evidence (JSON + CSV) inside the compliance pack.",
    ),
    realized_provider: Optional[str] = Query(
        default=None,
        description="Optional provider filter for realized savings evidence (aws|azure|gcp|saas|license|platform|hybrid).",
    ),
    realized_start_date: Optional[date] = Query(
        default=None,
        description="Realized savings window start date (YYYY-MM-DD). Defaults to savings_start_date if provided, otherwise last 30 days.",
    ),
    realized_end_date: Optional[date] = Query(
        default=None,
        description="Realized savings window end date (YYYY-MM-DD). Defaults to savings_end_date if provided, otherwise today.",
    ),
    realized_limit: int = Query(
        default=5000,
        ge=1,
        le=200000,
        description="Maximum number of realized savings evidence rows included (prevents huge ZIPs).",
    ),
    include_close_package: bool = Query(
        default=False,
        description="Include a reconciliation close package (JSON + CSV) inside the compliance pack.",
    ),
    close_provider: Optional[str] = Query(
        default=None,
        description="Optional provider filter for the bundled close package (aws|azure|gcp|saas|license|platform|hybrid).",
    ),
    close_start_date: Optional[date] = Query(
        default=None,
        description="Close package start date (YYYY-MM-DD). Defaults to last 30 days.",
    ),
    close_end_date: Optional[date] = Query(
        default=None,
        description="Close package end date (YYYY-MM-DD). Defaults to today.",
    ),
    close_enforce_finalized: bool = Query(
        default=True,
        description="If true, fail close package generation when PRELIMINARY data exists in the period.",
    ),
    close_max_restatements: int = Query(
        default=5000,
        ge=0,
        le=200000,
        description="Maximum number of restatement entries included in the close package details (0 includes none).",
    ),
) -> Any:
    return await export_compliance_pack_bundle(
        user=user,
        db=db,
        start_date=start_date,
        end_date=end_date,
        evidence_limit=evidence_limit,
        include_focus_export=include_focus_export,
        focus_provider=focus_provider,
        focus_include_preliminary=focus_include_preliminary,
        focus_max_rows=focus_max_rows,
        focus_start_date=focus_start_date,
        focus_end_date=focus_end_date,
        include_savings_proof=include_savings_proof,
        savings_provider=savings_provider,
        savings_start_date=savings_start_date,
        savings_end_date=savings_end_date,
        include_realized_savings=include_realized_savings,
        realized_provider=realized_provider,
        realized_start_date=realized_start_date,
        realized_end_date=realized_end_date,
        realized_limit=realized_limit,
        include_close_package=include_close_package,
        close_provider=close_provider,
        close_start_date=close_start_date,
        close_end_date=close_end_date,
        close_enforce_finalized=close_enforce_finalized,
        close_max_restatements=close_max_restatements,
        sanitize_csv_cell=_sanitize_csv_cell,
    )
