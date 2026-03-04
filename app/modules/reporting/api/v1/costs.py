from fastapi import APIRouter, Depends, Query, HTTPException, Response, Request
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, timedelta
from typing import Optional, Dict, Any
from uuid import UUID

from app.shared.core.config import get_settings
from app.shared.db.session import get_db
from app.shared.core.auth import get_current_user, requires_role, CurrentUser
from app.shared.core.dependencies import requires_feature
from app.shared.core.notifications import NotificationDispatcher
from app.modules.reporting.domain.aggregator import LARGE_DATASET_THRESHOLD
from app.modules.reporting.domain.aggregator import CostAggregator
from app.modules.reporting.domain.anomaly_detection import (
    CostAnomaly,
    CostAnomalyDetectionService,
    dispatch_cost_anomaly_alerts,
)
from app.models.unit_economics_settings import UnitEconomicsSettings
from app.shared.llm.analyzer import FinOpsAnalyzer
from app.shared.llm.factory import LLMFactory

__all__ = ["LARGE_DATASET_THRESHOLD"]
from app.shared.core.pricing import (
    FeatureFlag,
    PricingTier,
    is_feature_enabled,
    normalize_tier,
)
from app.shared.core.rate_limit import analysis_limit
from app.modules.reporting.api.v1.costs_models import (
    AcceptanceKpiEvidenceCaptureResponse,
    AcceptanceKpiEvidenceListResponse,
    AcceptanceKpiMetric,
    AcceptanceKpisResponse,
    CostAnomalyItem,
    CostAnomalyResponse,
    IngestionSLAResponse,
    ProviderInvoiceStatusUpdateRequest,
    ProviderInvoiceUpsertRequest,
    ProviderRecencyResponse,
    UnitEconomicsMetric,
    UnitEconomicsResponse,
    UnitEconomicsSettingsResponse,
    UnitEconomicsSettingsUpdate,
)
from app.modules.reporting.api.v1.costs_acceptance_payload import (
    compute_acceptance_kpis_payload as _compute_acceptance_kpis_payload_impl,
)
from app.modules.reporting.api.v1.costs_acceptance_routes import (
    capture_acceptance_kpis_impl,
    get_acceptance_kpis_impl,
    list_acceptance_kpi_evidence_impl,
)
from app.modules.reporting.api.v1.costs_reconciliation_routes import (
    delete_provider_invoice_impl,
    export_focus_v13_costs_csv_impl,
    get_reconciliation_close_package_impl,
    get_restatement_history_impl,
    get_restatement_runs_impl,
    list_provider_invoices_impl,
    update_provider_invoice_status_impl,
    upsert_provider_invoice_impl,
)
from app.modules.reporting.api.v1.costs_unit_economics_routes import (
    get_unit_economics_impl,
    get_unit_economics_settings_impl,
    update_unit_economics_settings_impl,
)
from app.modules.reporting.api.v1.costs_helpers import (
    anomaly_to_response_item,
    build_unit_metrics,
    render_acceptance_kpi_csv,
    sanitize_csv_cell,
    validate_anomaly_severity,
)
from app.modules.reporting.api.v1.costs_core_routes import (
    analyze_costs_impl,
    get_canonical_quality_impl,
    get_cost_anomalies_impl,
    get_cost_attribution_coverage_impl,
    get_cost_attribution_summary_impl,
    get_cost_breakdown_impl,
    get_cost_forecast_impl,
    get_costs_impl,
    get_ingestion_sla_impl,
    trigger_ingest_impl,
)
from app.modules.reporting.api.v1.costs_metrics import (
    build_provider_recency_summary as _build_provider_recency_summary_impl,
    compute_ingestion_sla_metrics as _compute_ingestion_sla_metrics_impl,
    compute_license_governance_kpi as _compute_license_governance_kpi_impl,
    compute_provider_recency_summaries as _compute_provider_recency_summaries_impl,
    get_or_create_unit_settings as _get_or_create_unit_settings_impl,
    is_connection_active_state as _is_connection_active_impl,
    settings_to_response as _settings_to_response_impl,
    window_total_cost as _window_total_cost_impl,
)

router = APIRouter(tags=["Costs"])
_PATCHABLE_TEST_SEAMS = (
    NotificationDispatcher,
    CostAggregator,
    CostAnomaly,
    CostAnomalyDetectionService,
    dispatch_cost_anomaly_alerts,
    UnitEconomicsSettings,
    FinOpsAnalyzer,
    LLMFactory,
    AcceptanceKpiMetric,
    CostAnomalyItem,
    ProviderRecencyResponse,
    UnitEconomicsMetric,
)
SUPPORTED_PROVIDER_FILTERS = {
    "aws",
    "azure",
    "gcp",
    "saas",
    "license",
    "platform",
    "hybrid",
}
SUPPORTED_ANOMALY_SEVERITIES = {"low", "medium", "high", "critical"}


def _require_tenant_id(user: CurrentUser) -> UUID:
    if user.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant context is required")
    return user.tenant_id


def _resolve_user_tier(user: CurrentUser) -> PricingTier:
    return normalize_tier(getattr(user, "tier", PricingTier.FREE))


def _normalize_provider_filter(provider: str | None) -> str | None:
    if provider is None:
        return None
    normalized = provider.strip().lower()
    if not normalized:
        return None
    if normalized not in SUPPORTED_PROVIDER_FILTERS:
        supported = ", ".join(sorted(SUPPORTED_PROVIDER_FILTERS))
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported provider '{provider}'. Use one of: {supported}",
        )
    return normalized


_sanitize_csv_cell = sanitize_csv_cell
_get_or_create_unit_settings = _get_or_create_unit_settings_impl
_settings_to_response = _settings_to_response_impl
_window_total_cost = _window_total_cost_impl


def _validate_anomaly_severity(value: str) -> str:
    return validate_anomaly_severity(value, SUPPORTED_ANOMALY_SEVERITIES)


_anomaly_to_response_item = anomaly_to_response_item
_build_unit_metrics = build_unit_metrics
_render_acceptance_kpi_csv = render_acceptance_kpi_csv


def _is_connection_active(connection: Any) -> bool:
    return _is_connection_active_impl(connection)


def _build_provider_recency_summary(
    provider: str,
    connections: list[Any],
    *,
    now: Any,
    recency_target_hours: int,
) -> ProviderRecencyResponse:
    return _build_provider_recency_summary_impl(
        provider,
        connections,
        now=now,
        recency_target_hours=recency_target_hours,
    )


async def _compute_provider_recency_summaries(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    recency_target_hours: int,
) -> list[ProviderRecencyResponse]:
    return await _compute_provider_recency_summaries_impl(
        db,
        tenant_id,
        recency_target_hours=recency_target_hours,
    )


async def _compute_ingestion_sla_metrics(
    db: AsyncSession,
    tenant_id: UUID,
    *,
    window_hours: int,
    target_success_rate_percent: float,
) -> IngestionSLAResponse:
    return await _compute_ingestion_sla_metrics_impl(
        db,
        tenant_id,
        window_hours=window_hours,
        target_success_rate_percent=target_success_rate_percent,
    )


async def _compute_license_governance_kpi(
    *,
    db: AsyncSession,
    tenant_id: UUID,
    start_date: date,
    end_date: date,
) -> AcceptanceKpiMetric:
    return await _compute_license_governance_kpi_impl(
        db=db,
        tenant_id=tenant_id,
        start_date=start_date,
        end_date=end_date,
    )


@router.get("")
async def get_costs(
    response: Response,
    start_date: date = Query(...),
    end_date: date = Query(...),
    provider: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Any:
    return await get_costs_impl(
        response=response,
        start_date=start_date,
        end_date=end_date,
        provider=provider,
        db=db,
        current_user=current_user,
        require_tenant_id=_require_tenant_id,
        cost_aggregator_cls=CostAggregator,
    )


@router.get("/breakdown")
async def get_cost_breakdown(
    start_date: date = Query(...),
    end_date: date = Query(...),
    provider: Optional[str] = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Any:
    return await get_cost_breakdown_impl(
        start_date=start_date,
        end_date=end_date,
        provider=provider,
        limit=limit,
        offset=offset,
        db=db,
        current_user=current_user,
        require_tenant_id=_require_tenant_id,
        cost_aggregator_cls=CostAggregator,
    )


@router.get("/attribution/summary")
async def get_cost_attribution_summary(
    start_date: date = Query(...),
    end_date: date = Query(...),
    bucket: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(requires_feature(FeatureFlag.CHARGEBACK)),
) -> Dict[str, Any]:
    return await get_cost_attribution_summary_impl(
        start_date=start_date,
        end_date=end_date,
        bucket=bucket,
        limit=limit,
        offset=offset,
        db=db,
        current_user=current_user,
        require_tenant_id=_require_tenant_id,
    )


@router.get("/attribution/coverage")
async def get_cost_attribution_coverage(
    start_date: date = Query(...),
    end_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(requires_feature(FeatureFlag.CHARGEBACK)),
) -> Dict[str, Any]:
    return await get_cost_attribution_coverage_impl(
        start_date=start_date,
        end_date=end_date,
        db=db,
        current_user=current_user,
        require_tenant_id=_require_tenant_id,
    )


@router.get("/canonical/quality")
async def get_canonical_quality(
    start_date: date = Query(...),
    end_date: date = Query(...),
    provider: Optional[str] = Query(default=None),
    notify_on_breach: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Any:
    return await get_canonical_quality_impl(
        start_date=start_date,
        end_date=end_date,
        provider=provider,
        notify_on_breach=notify_on_breach,
        db=db,
        current_user=current_user,
        require_tenant_id=_require_tenant_id,
        normalize_provider_filter=_normalize_provider_filter,
        cost_aggregator_cls=CostAggregator,
        notification_dispatcher_cls=NotificationDispatcher,
    )


@router.get("/forecast")
async def get_cost_forecast(
    days: int = Query(30, ge=7, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> Any:
    return await get_cost_forecast_impl(
        days=days,
        db=db,
        current_user=current_user,
        require_tenant_id=_require_tenant_id,
        cost_aggregator_cls=CostAggregator,
        symbolic_forecaster_cls=__import__(
            "app.shared.analysis.forecaster",
            fromlist=["SymbolicForecaster"],
        ).SymbolicForecaster,
    )


@router.get("/anomalies", response_model=CostAnomalyResponse)
async def get_cost_anomalies(
    target_date: date = Query(default_factory=date.today),
    lookback_days: int = Query(default=28, ge=7, le=120),
    provider: Optional[str] = Query(default=None),
    min_abs_usd: float = Query(default=25.0, ge=0.0),
    min_percent: float = Query(default=30.0, gt=0.0),
    min_severity: str = Query(default="medium"),
    alert: bool = Query(default=False),
    suppression_hours: int = Query(default=24, ge=1, le=24 * 30),
    user: CurrentUser = Depends(requires_feature(FeatureFlag.ANOMALY_DETECTION)),
    db: AsyncSession = Depends(get_db),
) -> CostAnomalyResponse:
    payload = await get_cost_anomalies_impl(
        target_date=target_date,
        lookback_days=lookback_days,
        provider=provider,
        min_abs_usd=min_abs_usd,
        min_percent=min_percent,
        min_severity=min_severity,
        alert=alert,
        suppression_hours=suppression_hours,
        user=user,
        db=db,
        require_tenant_id=_require_tenant_id,
        normalize_provider_filter=_normalize_provider_filter,
        validate_anomaly_severity=_validate_anomaly_severity,
        anomaly_to_response_item=_anomaly_to_response_item,
        anomaly_detection_service_cls=CostAnomalyDetectionService,
        dispatch_cost_anomaly_alerts_fn=dispatch_cost_anomaly_alerts,
    )
    return CostAnomalyResponse(**payload)


@router.post("/analyze")
@analysis_limit
async def analyze_costs(
    request: Request,
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=date.today),
    provider: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(requires_feature(FeatureFlag.LLM_ANALYSIS)),
) -> Any:
    return await analyze_costs_impl(
        request=request,
        start_date=start_date,
        end_date=end_date,
        provider=provider,
        db=db,
        current_user=current_user,
        require_tenant_id=_require_tenant_id,
        cost_aggregator_cls=CostAggregator,
        llm_factory_cls=LLMFactory,
        finops_analyzer_cls=FinOpsAnalyzer,
    )


@router.post("/ingest")
async def trigger_ingest(
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: CurrentUser = Depends(requires_role("admin")),
) -> Dict[str, str]:
    return await trigger_ingest_impl(
        start_date=start_date,
        end_date=end_date,
        db=db,
        current_user=current_user,
        resolve_user_tier=_resolve_user_tier,
        require_tenant_id=_require_tenant_id,
    )


@router.get("/ingestion/sla", response_model=IngestionSLAResponse)
async def get_ingestion_sla(
    window_hours: int = Query(default=24, ge=1, le=24 * 30),
    target_success_rate_percent: float = Query(default=95.0, ge=0, le=100),
    user: CurrentUser = Depends(requires_feature(FeatureFlag.INGESTION_SLA)),
    db: AsyncSession = Depends(get_db),
) -> IngestionSLAResponse:
    payload = await get_ingestion_sla_impl(
        window_hours=window_hours,
        target_success_rate_percent=target_success_rate_percent,
        user=user,
        db=db,
        require_tenant_id=_require_tenant_id,
        compute_ingestion_sla_metrics=_compute_ingestion_sla_metrics,
    )
    if isinstance(payload, IngestionSLAResponse):
        return payload
    return IngestionSLAResponse.model_validate(payload)


async def _compute_acceptance_kpis_payload(
    *,
    start_date: date,
    end_date: date,
    ingestion_window_hours: int,
    ingestion_target_success_rate_percent: float,
    recency_target_hours: int,
    chargeback_target_percent: float,
    max_unit_anomalies: int,
    ledger_normalization_target_percent: float = 95.0,
    canonical_mapping_target_percent: float = 90.0,
    current_user: CurrentUser,
    db: AsyncSession,
) -> AcceptanceKpisResponse:
    return await _compute_acceptance_kpis_payload_impl(
        start_date=start_date,
        end_date=end_date,
        ingestion_window_hours=ingestion_window_hours,
        ingestion_target_success_rate_percent=ingestion_target_success_rate_percent,
        recency_target_hours=recency_target_hours,
        chargeback_target_percent=chargeback_target_percent,
        max_unit_anomalies=max_unit_anomalies,
        ledger_normalization_target_percent=ledger_normalization_target_percent,
        canonical_mapping_target_percent=canonical_mapping_target_percent,
        current_user=current_user,
        db=db,
        compute_ingestion_sla_metrics_fn=_compute_ingestion_sla_metrics,
        compute_provider_recency_summaries_fn=_compute_provider_recency_summaries,
        compute_license_governance_kpi_fn=_compute_license_governance_kpi,
        get_or_create_unit_settings_fn=_get_or_create_unit_settings,
        window_total_cost_fn=_window_total_cost,
        get_settings_fn=get_settings,
        is_feature_enabled_fn=is_feature_enabled,
    )


@router.get("/acceptance/kpis", response_model=AcceptanceKpisResponse)
async def get_acceptance_kpis(
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=date.today),
    ingestion_window_hours: int = Query(default=24 * 7, ge=1, le=24 * 30),
    ingestion_target_success_rate_percent: float = Query(default=95.0, ge=0, le=100),
    recency_target_hours: int = Query(default=48, ge=1, le=24 * 14),
    chargeback_target_percent: float = Query(default=90.0, ge=0, le=100),
    max_unit_anomalies: int = Query(default=0, ge=0, le=100),
    response_format: str = Query(default="json", pattern="^(json|csv)$"),
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Any:
    """
    Consolidated acceptance KPIs for production sign-off evidence.
    """
    return await get_acceptance_kpis_impl(
        start_date=start_date,
        end_date=end_date,
        ingestion_window_hours=ingestion_window_hours,
        ingestion_target_success_rate_percent=ingestion_target_success_rate_percent,
        recency_target_hours=recency_target_hours,
        chargeback_target_percent=chargeback_target_percent,
        max_unit_anomalies=max_unit_anomalies,
        response_format=response_format,
        current_user=current_user,
        db=db,
        compute_acceptance_kpis_payload=_compute_acceptance_kpis_payload,
        render_acceptance_kpi_csv=_render_acceptance_kpi_csv,
    )


@router.post(
    "/acceptance/kpis/capture", response_model=AcceptanceKpiEvidenceCaptureResponse
)
async def capture_acceptance_kpis(
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=30)),
    end_date: date = Query(default_factory=date.today),
    ingestion_window_hours: int = Query(default=24 * 7, ge=1, le=24 * 30),
    ingestion_target_success_rate_percent: float = Query(default=95.0, ge=0, le=100),
    recency_target_hours: int = Query(default=48, ge=1, le=24 * 14),
    chargeback_target_percent: float = Query(default=90.0, ge=0, le=100),
    max_unit_anomalies: int = Query(default=0, ge=0, le=100),
    current_user: CurrentUser = Depends(requires_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AcceptanceKpiEvidenceCaptureResponse:
    """
    Capture and persist acceptance KPI evidence as an immutable audit log record.

    This is intended for operators/admins who need audit-grade evidence for
    rollout/procurement sign-off.
    """
    return await capture_acceptance_kpis_impl(
        start_date=start_date,
        end_date=end_date,
        ingestion_window_hours=ingestion_window_hours,
        ingestion_target_success_rate_percent=ingestion_target_success_rate_percent,
        recency_target_hours=recency_target_hours,
        chargeback_target_percent=chargeback_target_percent,
        max_unit_anomalies=max_unit_anomalies,
        current_user=current_user,
        db=db,
        compute_acceptance_kpis_payload=_compute_acceptance_kpis_payload,
        require_tenant_id=_require_tenant_id,
    )


@router.get(
    "/acceptance/kpis/evidence", response_model=AcceptanceKpiEvidenceListResponse
)
async def list_acceptance_kpi_evidence(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: CurrentUser = Depends(requires_role("admin")),
    db: AsyncSession = Depends(get_db),
) -> AcceptanceKpiEvidenceListResponse:
    """
    List persisted acceptance KPI evidence snapshots for this tenant.
    """
    return await list_acceptance_kpi_evidence_impl(
        limit=limit,
        current_user=current_user,
        db=db,
        require_tenant_id=_require_tenant_id,
    )


@router.get("/unit-economics/settings", response_model=UnitEconomicsSettingsResponse)
async def get_unit_economics_settings(
    user: CurrentUser = Depends(requires_feature(FeatureFlag.UNIT_ECONOMICS)),
    db: AsyncSession = Depends(get_db),
) -> UnitEconomicsSettingsResponse:
    return await get_unit_economics_settings_impl(
        user=user,
        db=db,
        require_tenant_id=_require_tenant_id,
        get_or_create_unit_settings=_get_or_create_unit_settings,
        settings_to_response=_settings_to_response,
    )


@router.put("/unit-economics/settings", response_model=UnitEconomicsSettingsResponse)
async def update_unit_economics_settings(
    payload: UnitEconomicsSettingsUpdate,
    user: CurrentUser = Depends(requires_feature(FeatureFlag.UNIT_ECONOMICS, "admin")),
    db: AsyncSession = Depends(get_db),
) -> UnitEconomicsSettingsResponse:
    return await update_unit_economics_settings_impl(
        payload=payload,
        user=user,
        db=db,
        require_tenant_id=_require_tenant_id,
        get_or_create_unit_settings=_get_or_create_unit_settings,
        settings_to_response=_settings_to_response,
    )


@router.get("/unit-economics", response_model=UnitEconomicsResponse)
async def get_unit_economics(
    start_date: date = Query(...),
    end_date: date = Query(...),
    provider: Optional[str] = Query(default=None),
    request_volume: Optional[float] = Query(default=None, gt=0),
    workload_volume: Optional[float] = Query(default=None, gt=0),
    customer_volume: Optional[float] = Query(default=None, gt=0),
    alert_on_anomaly: bool = Query(default=True),
    user: CurrentUser = Depends(requires_feature(FeatureFlag.UNIT_ECONOMICS)),
    db: AsyncSession = Depends(get_db),
) -> UnitEconomicsResponse:
    return await get_unit_economics_impl(
        start_date=start_date,
        end_date=end_date,
        provider=provider,
        request_volume=request_volume,
        workload_volume=workload_volume,
        customer_volume=customer_volume,
        alert_on_anomaly=alert_on_anomaly,
        user=user,
        db=db,
        require_tenant_id=_require_tenant_id,
        get_or_create_unit_settings=_get_or_create_unit_settings,
        window_total_cost=_window_total_cost,
        build_unit_metrics=_build_unit_metrics,
    )


@router.get("/reconciliation/close-package", response_model=None)
async def get_reconciliation_close_package(
    start_date: date = Query(...),
    end_date: date = Query(...),
    provider: Optional[str] = Query(default=None),
    response_format: str = Query(default="json", pattern="^(json|csv)$"),
    enforce_finalized: bool = Query(default=True),
    user: CurrentUser = Depends(requires_feature(FeatureFlag.CLOSE_WORKFLOW)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    return await get_reconciliation_close_package_impl(
        start_date=start_date,
        end_date=end_date,
        provider=provider,
        response_format=response_format,
        enforce_finalized=enforce_finalized,
        user=user,
        db=db,
        require_tenant_id=_require_tenant_id,
        normalize_provider_filter=_normalize_provider_filter,
    )


@router.get("/reconciliation/restatements", response_model=None)
async def get_restatement_history(
    start_date: date = Query(...),
    end_date: date = Query(...),
    provider: Optional[str] = Query(default=None),
    response_format: str = Query(default="json", pattern="^(json|csv)$"),
    user: CurrentUser = Depends(requires_feature(FeatureFlag.RECONCILIATION)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    return await get_restatement_history_impl(
        start_date=start_date,
        end_date=end_date,
        provider=provider,
        response_format=response_format,
        user=user,
        db=db,
        require_tenant_id=_require_tenant_id,
        normalize_provider_filter=_normalize_provider_filter,
        get_settings=get_settings,
    )


@router.get("/reconciliation/restatement-runs", response_model=None)
async def get_restatement_runs(
    start_date: date = Query(...),
    end_date: date = Query(...),
    provider: Optional[str] = Query(default=None),
    response_format: str = Query(default="json", pattern="^(json|csv)$"),
    user: CurrentUser = Depends(requires_feature(FeatureFlag.RECONCILIATION)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    return await get_restatement_runs_impl(
        start_date=start_date,
        end_date=end_date,
        provider=provider,
        response_format=response_format,
        user=user,
        db=db,
        require_tenant_id=_require_tenant_id,
        normalize_provider_filter=_normalize_provider_filter,
    )


@router.get("/reconciliation/invoices", response_model=None)
async def list_provider_invoices(
    provider: Optional[str] = Query(default=None),
    start_date: Optional[date] = Query(default=None),
    end_date: Optional[date] = Query(default=None),
    user: CurrentUser = Depends(requires_feature(FeatureFlag.CLOSE_WORKFLOW)),
    db: AsyncSession = Depends(get_db),
) -> Any:
    return await list_provider_invoices_impl(
        provider=provider,
        start_date=start_date,
        end_date=end_date,
        user=user,
        db=db,
        require_tenant_id=_require_tenant_id,
        normalize_provider_filter=_normalize_provider_filter,
    )


@router.post("/reconciliation/invoices", response_model=None)
async def upsert_provider_invoice(
    request: Request,
    payload: ProviderInvoiceUpsertRequest,
    user: CurrentUser = Depends(
        requires_feature(FeatureFlag.CLOSE_WORKFLOW, required_role="admin")
    ),
    db: AsyncSession = Depends(get_db),
) -> Any:
    return await upsert_provider_invoice_impl(
        request=request,
        payload=payload,
        user=user,
        db=db,
        require_tenant_id=_require_tenant_id,
    )


@router.patch("/reconciliation/invoices/{invoice_id}", response_model=None)
async def update_provider_invoice_status(
    request: Request,
    invoice_id: UUID,
    payload: ProviderInvoiceStatusUpdateRequest,
    user: CurrentUser = Depends(
        requires_feature(FeatureFlag.CLOSE_WORKFLOW, required_role="admin")
    ),
    db: AsyncSession = Depends(get_db),
) -> Any:
    return await update_provider_invoice_status_impl(
        request=request,
        invoice_id=invoice_id,
        payload=payload,
        user=user,
        db=db,
        require_tenant_id=_require_tenant_id,
    )


@router.delete("/reconciliation/invoices/{invoice_id}", response_model=None)
async def delete_provider_invoice(
    request: Request,
    invoice_id: UUID,
    user: CurrentUser = Depends(
        requires_feature(FeatureFlag.CLOSE_WORKFLOW, required_role="admin")
    ),
    db: AsyncSession = Depends(get_db),
) -> Any:
    return await delete_provider_invoice_impl(
        request=request,
        invoice_id=invoice_id,
        user=user,
        db=db,
        require_tenant_id=_require_tenant_id,
    )


@router.get("/export/focus", response_model=None)
async def export_focus_v13_costs_csv(
    start_date: date = Query(..., description="Start date (inclusive, YYYY-MM-DD)"),
    end_date: date = Query(..., description="End date (inclusive, YYYY-MM-DD)"),
    provider: Optional[str] = Query(
        default=None, description="Optional provider filter"
    ),
    include_preliminary: bool = Query(
        default=False,
        description="Include PRELIMINARY records (otherwise exports FINAL only).",
    ),
    user: CurrentUser = Depends(
        requires_feature(FeatureFlag.COMPLIANCE_EXPORTS, required_role="admin")
    ),
    db: AsyncSession = Depends(get_db),
) -> Any:
    return await export_focus_v13_costs_csv_impl(
        start_date=start_date,
        end_date=end_date,
        provider=provider,
        include_preliminary=include_preliminary,
        user=user,
        db=db,
        require_tenant_id=_require_tenant_id,
        normalize_provider_filter=_normalize_provider_filter,
        sanitize_csv_cell=_sanitize_csv_cell,
        get_settings=get_settings,
    )
