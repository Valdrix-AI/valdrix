import pytest
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient
from app.models.background_job import BackgroundJob, JobStatus, JobType
from app.models.cloud import CloudAccount, CostRecord
from app.models.tenant import Tenant
from app.modules.reporting.api.v1 import costs as costs_api
from app.shared.core.auth import CurrentUser, get_current_user, UserRole
from app.shared.core.pricing import PricingTier


@pytest.mark.asyncio
async def test_get_costs_and_breakdown(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="costs@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch("app.modules.reporting.api.v1.costs.CostAggregator.get_dashboard_summary", new=AsyncMock()) as mock_summary, \
             patch("app.modules.reporting.api.v1.costs.CostAggregator.get_basic_breakdown", new=AsyncMock()) as mock_breakdown:
            mock_summary.return_value = {"total_cost": 123.45}
            mock_breakdown.return_value = {"services": []}

            response = await async_client.get(
                "/api/v1/costs",
                params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
            )
            assert response.status_code == 200
            assert response.json()["total_cost"] == 123.45

            response = await async_client.get(
                "/api/v1/costs/breakdown",
                params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
            )
            assert response.status_code == 200
            assert response.json()["services"] == []
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_cost_attribution_summary(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="allocation@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.GROWTH,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch(
            "app.modules.reporting.domain.attribution_engine.AttributionEngine.get_allocation_summary",
            new=AsyncMock(),
        ) as mock_summary:
            mock_summary.return_value = {
                "buckets": [{"name": "Platform", "total_amount": 123.45, "record_count": 2}],
                "total": 123.45,
            }

            response = await async_client.get(
                "/api/v1/costs/attribution/summary",
                params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["total"] == 123.45
            assert data["buckets"][0]["name"] == "Platform"
            assert mock_summary.await_count == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_cost_forecast_paths(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="forecast@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        # Insufficient records -> 400
        with patch("app.modules.reporting.api.v1.costs.CostAggregator.get_summary", new=AsyncMock()) as mock_summary:
            mock_summary.return_value = SimpleNamespace(records=[])
            response = await async_client.get("/api/v1/costs/forecast", params={"days": 30})
            assert response.status_code == 400
            assert "Insufficient cost history" in response.json()["error"]

        # Sufficient records -> forecast returned
        with patch("app.modules.reporting.api.v1.costs.CostAggregator.get_summary", new=AsyncMock()) as mock_summary, \
             patch("app.shared.analysis.forecaster.SymbolicForecaster.forecast", new=AsyncMock()) as mock_forecast:
            mock_summary.return_value = SimpleNamespace(records=[{"cost": 10.0}])
            mock_forecast.return_value = {"forecast": [1, 2, 3]}
            response = await async_client.get("/api/v1/costs/forecast", params={"days": 14})
            assert response.status_code == 200
            assert response.json()["forecast"] == [1, 2, 3]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_analyze_costs_paths(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="analyze@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        # No records -> fallback response
        with patch("app.modules.reporting.api.v1.costs.CostAggregator.get_summary", new=AsyncMock()) as mock_summary:
            mock_summary.return_value = SimpleNamespace(records=[])
            response = await async_client.post("/api/v1/costs/analyze")
            assert response.status_code == 200
            data = response.json()
            assert data["summary"] == "No cost data available for analysis."

        # Records -> analyzer path
        with patch("app.modules.reporting.api.v1.costs.CostAggregator.get_summary", new=AsyncMock()) as mock_summary, \
             patch("app.modules.reporting.api.v1.costs.LLMFactory.create", return_value=MagicMock()) as mock_create, \
             patch("app.modules.reporting.api.v1.costs.FinOpsAnalyzer") as mock_analyzer_class:
            mock_summary.return_value = SimpleNamespace(records=[{"cost": 10.0}])
            mock_analyzer = mock_analyzer_class.return_value
            mock_analyzer.analyze = AsyncMock(return_value={"summary": "ok"})

            response = await async_client.post("/api/v1/costs/analyze")
            assert response.status_code == 200
            assert response.json()["summary"] == "ok"
            assert mock_create.called
            assert mock_analyzer.analyze.await_count == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_analyze_costs_requires_tier(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="starter@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.post("/api/v1/costs/analyze")
        assert response.status_code == 403
        assert "requires" in response.json()["error"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_trigger_ingest(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="ingest@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        mock_job = SimpleNamespace(id=uuid.uuid4())
        with patch("app.modules.governance.domain.jobs.processor.enqueue_job", new=AsyncMock(return_value=mock_job)):
            response = await async_client.post("/api/v1/costs/ingest")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "queued"
            assert data["job_id"] == str(mock_job.id)
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_trigger_ingest_with_backfill_window(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="ingest-range@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.GROWTH,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        mock_job = SimpleNamespace(id=uuid.uuid4())
        with patch("app.modules.governance.domain.jobs.processor.enqueue_job", new=AsyncMock(return_value=mock_job)) as mock_enqueue:
            response = await async_client.post(
                "/api/v1/costs/ingest",
                params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "queued"
            assert data["start_date"] == "2026-01-01"
            assert data["end_date"] == "2026-01-31"
            call_kwargs = mock_enqueue.await_args.kwargs
            assert call_kwargs["payload"]["start_date"] == "2026-01-01"
            assert call_kwargs["payload"]["end_date"] == "2026-01-31"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_trigger_ingest_backfill_requires_growth_tier(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="ingest-backfill-denied@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.post(
            "/api/v1/costs/ingest",
            params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
        )
        assert response.status_code == 403
        assert "backfill" in response.json()["error"].lower()
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_trigger_ingest_backfill_requires_both_dates(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="ingest-invalid@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.post(
            "/api/v1/costs/ingest",
            params={"start_date": "2026-01-01"},
        )
        assert response.status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_costs_returns_data_quality_metadata(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="quality@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch("app.modules.reporting.api.v1.costs.CostAggregator.get_dashboard_summary", new=AsyncMock()) as mock_summary:
            mock_summary.return_value = {
                "total_cost": 123.45,
                "data_quality": {
                    "freshness": {"status": "mixed"},
                    "canonical_mapping": {"mapped_percentage": 99.1, "meets_target": True},
                },
            }

            response = await async_client.get(
                "/api/v1/costs",
                params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["data_quality"]["freshness"]["status"] == "mixed"
            assert data["data_quality"]["canonical_mapping"]["mapped_percentage"] == 99.1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_costs_requires_tenant_context(async_client: AsyncClient, app):
    mock_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=None,
        email="no-tenant@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.get(
            "/api/v1/costs",
            params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
        )
        assert response.status_code == 403
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_costs_large_dataset_returns_accepted(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        email="large@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        mock_job = SimpleNamespace(id=uuid.uuid4())
        with patch(
            "app.modules.reporting.api.v1.costs.CostAggregator.count_records",
            new=AsyncMock(return_value=costs_api.LARGE_DATASET_THRESHOLD + 1),
        ), patch(
            "app.modules.governance.domain.jobs.processor.enqueue_job",
            new=AsyncMock(return_value=mock_job),
        ) as mock_enqueue:
            response = await async_client.get(
                "/api/v1/costs",
                params={"start_date": "2024-01-01", "end_date": "2024-01-31", "provider": "aws"},
            )

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "accepted"
        assert body["job_id"] == str(mock_job.id)
        assert mock_enqueue.await_args.kwargs["payload"]["provider"] == "aws"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_trigger_ingest_rejects_invalid_date_order(async_client: AsyncClient, app):
    mock_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="ingest-order@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.STARTER,
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.post(
            "/api/v1/costs/ingest",
            params={"start_date": "2026-02-02", "end_date": "2026-02-01"},
        )
        assert response.status_code == 400
        assert "start_date must be <=" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_unit_economics_rejects_invalid_date_order(async_client: AsyncClient, app):
    mock_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="unit-order@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.PRO,
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.get(
            "/api/v1/costs/unit-economics",
            params={"start_date": "2026-02-02", "end_date": "2026-02-01"},
        )
        assert response.status_code == 400
        assert "start_date must be <=" in response.json()["error"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_unit_economics_alert_failure_is_non_fatal(async_client: AsyncClient, app, db, member_user):
    app.dependency_overrides[get_current_user] = lambda: member_user
    try:
        account = CloudAccount(
            tenant_id=member_user.tenant_id,
            provider="aws",
            name="Alert Failure AWS",
            is_active=True,
        )
        db.add(account)
        await db.flush()
        for day in range(1, 8):
            db.add(
                CostRecord(
                    tenant_id=member_user.tenant_id,
                    account_id=account.id,
                    service="AmazonEC2",
                    region="us-east-1",
                    usage_type="BoxUsage",
                    cost_usd=Decimal("100.00"),
                    currency="USD",
                    canonical_charge_category="compute",
                    canonical_mapping_version="focus-1.3-v1",
                    recorded_at=date(2026, 2, day),
                    timestamp=datetime(2026, 2, day, 10, 0, tzinfo=timezone.utc),
                )
            )
            db.add(
                CostRecord(
                    tenant_id=member_user.tenant_id,
                    account_id=account.id,
                    service="AmazonEC2",
                    region="us-east-1",
                    usage_type="BoxUsage",
                    cost_usd=Decimal("50.00"),
                    currency="USD",
                    canonical_charge_category="compute",
                    canonical_mapping_version="focus-1.3-v1",
                    recorded_at=date(2026, 1, 24 + day),
                    timestamp=datetime(2026, 1, 24 + day, 10, 0, tzinfo=timezone.utc),
                )
            )
        await db.commit()

        with patch(
            "app.modules.reporting.api.v1.costs.NotificationDispatcher.send_alert",
            new=AsyncMock(side_effect=RuntimeError("alert failure")),
        ):
            response = await async_client.get(
                "/api/v1/costs/unit-economics",
                params={"start_date": "2026-02-01", "end_date": "2026-02-07"},
            )

        assert response.status_code == 200
        assert response.json()["alert_dispatched"] is False
        assert response.json()["anomaly_count"] >= 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_window_total_cost_provider_filter_and_missing_rows(db):
    tenant_id = uuid.uuid4()
    account = CloudAccount(
        tenant_id=tenant_id,
        provider="aws",
        name="Provider Filter",
        is_active=True,
    )
    db.add(account)
    await db.flush()

    db.add(
        CostRecord(
            tenant_id=tenant_id,
            account_id=account.id,
            service="AmazonEC2",
            region="us-east-1",
            usage_type="BoxUsage",
            cost_usd=Decimal("12.50"),
            currency="USD",
            canonical_charge_category="compute",
            canonical_mapping_version="focus-1.3-v1",
            recorded_at=date(2026, 2, 1),
            timestamp=datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc),
        )
    )
    await db.commit()

    aws_total = await costs_api._window_total_cost(
        db=db,
        tenant_id=tenant_id,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 1),
        provider="aws",
    )
    gcp_total = await costs_api._window_total_cost(
        db=db,
        tenant_id=tenant_id,
        start_date=date(2026, 2, 1),
        end_date=date(2026, 2, 1),
        provider="gcp",
    )
    assert aws_total == Decimal("12.50")
    assert gcp_total == Decimal("0")


def test_build_unit_metrics_handles_zero_denominator_and_zero_baseline():
    metrics = costs_api._build_unit_metrics(
        total_cost=Decimal("25.0"),
        baseline_total_cost=Decimal("0"),
        threshold_percent=10.0,
        request_volume=0.0,
        workload_volume=5.0,
        customer_volume=2.5,
    )
    assert len(metrics) == 2
    assert all(metric.delta_percent == 0.0 for metric in metrics)
    assert all(metric.is_anomalous is False for metric in metrics)


@pytest.mark.asyncio
async def test_get_ingestion_sla_metrics(async_client: AsyncClient, app, db):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="sla@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        now = datetime.now(timezone.utc)
        db.add(Tenant(id=tenant_id, name="SLA Tenant", plan="pro"))
        db.add_all(
            [
                BackgroundJob(
                    tenant_id=tenant_id,
                    job_type=JobType.COST_INGESTION.value,
                    status=JobStatus.COMPLETED.value,
                    payload={},
                    result={"ingested": 120},
                    scheduled_for=now,
                    created_at=now,
                    started_at=now,
                    completed_at=now + timedelta(seconds=300),
                ),
                BackgroundJob(
                    tenant_id=tenant_id,
                    job_type=JobType.COST_INGESTION.value,
                    status=JobStatus.COMPLETED.value,
                    payload={},
                    result={"ingested": 40},
                    scheduled_for=now,
                    created_at=now,
                    started_at=now,
                    completed_at=now + timedelta(seconds=120),
                ),
                BackgroundJob(
                    tenant_id=tenant_id,
                    job_type=JobType.COST_INGESTION.value,
                    status=JobStatus.FAILED.value,
                    payload={},
                    result={},
                    scheduled_for=now,
                    created_at=now,
                    started_at=now,
                    completed_at=now + timedelta(seconds=60),
                ),
            ]
        )
        await db.commit()

        response = await async_client.get(
            "/api/v1/costs/ingestion/sla",
            params={"window_hours": 24, "target_success_rate_percent": 60},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["window_hours"] == 24
        assert data["total_jobs"] == 3
        assert data["successful_jobs"] == 2
        assert data["failed_jobs"] == 1
        assert data["success_rate_percent"] == pytest.approx(66.67, rel=0.01)
        assert data["meets_sla"] is True
        assert data["records_ingested"] == 160
        assert data["avg_duration_seconds"] == pytest.approx(160.0, rel=0.01)
        assert data["p95_duration_seconds"] == pytest.approx(300.0, rel=0.01)
        assert data["latest_completed_at"] is not None
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_ingestion_sla_no_jobs(async_client: AsyncClient, app, db):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="sla-empty@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        db.add(Tenant(id=tenant_id, name="SLA Empty", plan="pro"))
        await db.commit()

        response = await async_client.get("/api/v1/costs/ingestion/sla")
        assert response.status_code == 200
        data = response.json()
        assert data["total_jobs"] == 0
        assert data["successful_jobs"] == 0
        assert data["failed_jobs"] == 0
        assert data["success_rate_percent"] == 0.0
        assert data["meets_sla"] is False
        assert data["records_ingested"] == 0
    finally:
        app.dependency_overrides.pop(get_current_user, None)
