from __future__ import annotations

from datetime import date
from typing import Any, Dict, Optional
from uuid import UUID

from pydantic import BaseModel, Field


class UnitEconomicsSettingsResponse(BaseModel):
    id: UUID
    default_request_volume: float
    default_workload_volume: float
    default_customer_volume: float
    anomaly_threshold_percent: float


class UnitEconomicsSettingsUpdate(BaseModel):
    default_request_volume: Optional[float] = Field(default=None, gt=0)
    default_workload_volume: Optional[float] = Field(default=None, gt=0)
    default_customer_volume: Optional[float] = Field(default=None, gt=0)
    anomaly_threshold_percent: Optional[float] = Field(default=None, gt=0, le=1000)


class UnitEconomicsMetric(BaseModel):
    metric_key: str
    label: str
    denominator: float
    total_cost: float
    cost_per_unit: float
    baseline_cost_per_unit: float
    delta_percent: float
    is_anomalous: bool


class UnitEconomicsResponse(BaseModel):
    start_date: str
    end_date: str
    total_cost: float
    baseline_total_cost: float
    threshold_percent: float
    anomaly_count: int
    alert_dispatched: bool
    metrics: list[UnitEconomicsMetric]


class IngestionSLAResponse(BaseModel):
    window_hours: int
    target_success_rate_percent: float
    total_jobs: int
    successful_jobs: int
    failed_jobs: int
    success_rate_percent: float
    meets_sla: bool
    latest_completed_at: Optional[str]
    avg_duration_seconds: Optional[float]
    p95_duration_seconds: Optional[float]
    records_ingested: int


class ProviderRecencyResponse(BaseModel):
    provider: str
    active_connections: int
    recently_ingested: int
    stale_connections: int
    never_ingested: int
    latest_ingested_at: Optional[str]
    recency_target_hours: int
    meets_recency_target: bool


class AcceptanceKpiMetric(BaseModel):
    key: str
    label: str
    available: bool
    target: str
    actual: str
    meets_target: bool
    details: Dict[str, Any] = Field(default_factory=dict)


class AcceptanceKpisResponse(BaseModel):
    start_date: str
    end_date: str
    tier: str
    all_targets_met: bool
    available_metrics: int
    metrics: list[AcceptanceKpiMetric]


class AcceptanceKpiEvidenceItem(BaseModel):
    event_id: str
    run_id: str | None
    captured_at: str
    actor_id: str | None
    actor_email: str | None
    success: bool
    acceptance_kpis: AcceptanceKpisResponse


class AcceptanceKpiEvidenceListResponse(BaseModel):
    total: int
    items: list[AcceptanceKpiEvidenceItem]


class AcceptanceKpiEvidenceCaptureResponse(BaseModel):
    status: str
    event_id: str
    run_id: str
    captured_at: str
    acceptance_kpis: AcceptanceKpisResponse


class CostAnomalyItem(BaseModel):
    day: str
    provider: str
    account_id: str
    account_name: Optional[str]
    service: str
    actual_cost_usd: float
    expected_cost_usd: float
    delta_cost_usd: float
    percent_change: Optional[float]
    kind: str
    probable_cause: str
    confidence: float
    severity: str


class CostAnomalyResponse(BaseModel):
    target_date: str
    lookback_days: int
    provider: Optional[str]
    min_abs_usd: float
    min_percent: float
    min_severity: str
    count: int
    alerted_count: int
    anomalies: list[CostAnomalyItem]


class ProviderInvoiceUpsertRequest(BaseModel):
    provider: str
    start_date: date
    end_date: date
    currency: str = "USD"
    total_amount: float
    invoice_number: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None


class ProviderInvoiceStatusUpdateRequest(BaseModel):
    status: str
    notes: Optional[str] = None
