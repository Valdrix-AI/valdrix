import pytest
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import AsyncClient
from app.models.background_job import BackgroundJob, JobStatus, JobType
from app.models.cloud import CloudAccount, CostRecord
from app.models.license_connection import LicenseConnection
from app.models.remediation import (
    RemediationAction,
    RemediationRequest,
    RemediationStatus,
)
from app.models.tenant import Tenant, User
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
        with (
            patch(
                "app.modules.reporting.api.v1.costs.CostAggregator.get_dashboard_summary",
                new=AsyncMock(),
            ) as mock_summary,
            patch(
                "app.modules.reporting.api.v1.costs.CostAggregator.get_basic_breakdown",
                new=AsyncMock(),
            ) as mock_breakdown,
        ):
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
                "buckets": [
                    {"name": "Platform", "total_amount": 123.45, "record_count": 2}
                ],
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
async def test_get_cost_attribution_coverage(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="coverage@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.GROWTH,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with patch(
            "app.modules.reporting.domain.attribution_engine.AttributionEngine.get_allocation_coverage",
            new=AsyncMock(),
        ) as mock_coverage:
            mock_coverage.return_value = {
                "target_percentage": 90.0,
                "coverage_percentage": 93.5,
                "meets_target": True,
                "status": "ok",
            }

            response = await async_client.get(
                "/api/v1/costs/attribution/coverage",
                params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["coverage_percentage"] == 93.5
            assert data["meets_target"] is True
            assert mock_coverage.await_count == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_canonical_quality_with_alert(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="canonical@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with (
            patch(
                "app.modules.reporting.api.v1.costs.CostAggregator.get_canonical_data_quality",
                new=AsyncMock(),
            ) as mock_quality,
            patch(
                "app.modules.reporting.api.v1.costs.NotificationDispatcher.send_alert",
                new=AsyncMock(),
            ) as mock_alert,
        ):
            mock_quality.return_value = {
                "target_percentage": 99.0,
                "total_records": 100,
                "mapped_percentage": 95.0,
                "unmapped_records": 5,
                "meets_target": False,
                "status": "warning",
            }
            response = await async_client.get(
                "/api/v1/costs/canonical/quality",
                params={
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "provider": "saas",
                    "notify_on_breach": "true",
                },
            )
            assert response.status_code == 200
            payload = response.json()
            assert payload["status"] == "warning"
            assert payload["alert_triggered"] is True
            assert mock_alert.await_count == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_canonical_quality_rejects_invalid_provider(
    async_client: AsyncClient, app
):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="canonical-invalid@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.get(
            "/api/v1/costs/canonical/quality",
            params={
                "start_date": "2026-01-01",
                "end_date": "2026-01-31",
                "provider": "oracle",
            },
        )
        assert response.status_code == 400
        assert "unsupported provider" in response.json()["error"].lower()
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
        with patch(
            "app.modules.reporting.api.v1.costs.CostAggregator.get_summary",
            new=AsyncMock(),
        ) as mock_summary:
            mock_summary.return_value = SimpleNamespace(records=[])
            response = await async_client.get(
                "/api/v1/costs/forecast", params={"days": 30}
            )
            assert response.status_code == 400
            assert "Insufficient cost history" in response.json()["error"]

        # Sufficient records -> forecast returned
        with (
            patch(
                "app.modules.reporting.api.v1.costs.CostAggregator.get_summary",
                new=AsyncMock(),
            ) as mock_summary,
            patch(
                "app.shared.analysis.forecaster.SymbolicForecaster.forecast",
                new=AsyncMock(),
            ) as mock_forecast,
        ):
            mock_summary.return_value = SimpleNamespace(records=[{"cost": 10.0}])
            mock_forecast.return_value = {"forecast": [1, 2, 3]}
            response = await async_client.get(
                "/api/v1/costs/forecast", params={"days": 14}
            )
            assert response.status_code == 200
            assert response.json()["forecast"] == [1, 2, 3]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_cost_anomalies_paths(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="anomalies@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.GROWTH,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        mock_item = MagicMock()
        mock_item.day = date(2026, 2, 12)
        mock_item.provider = "aws"
        mock_item.account_id = uuid.uuid4()
        mock_item.account_name = "Prod"
        mock_item.service = "AmazonEC2"
        mock_item.actual_cost_usd = Decimal("250.00")
        mock_item.expected_cost_usd = Decimal("100.00")
        mock_item.delta_cost_usd = Decimal("150.00")
        mock_item.percent_change = 150.0
        mock_item.kind = "spike"
        mock_item.probable_cause = "spend_spike"
        mock_item.confidence = 0.9
        mock_item.severity = "high"

        with (
            patch(
                "app.modules.reporting.api.v1.costs.CostAnomalyDetectionService.detect",
                new=AsyncMock(return_value=[mock_item]),
            ),
            patch(
                "app.modules.reporting.api.v1.costs.dispatch_cost_anomaly_alerts",
                new=AsyncMock(return_value=1),
            ) as mock_alert,
        ):
            response = await async_client.get(
                "/api/v1/costs/anomalies",
                params={
                    "target_date": "2026-02-12",
                    "provider": "aws",
                    "alert": "true",
                    "suppression_hours": 12,
                    "min_severity": "medium",
                },
            )
        assert response.status_code == 200
        body = response.json()
        assert body["count"] == 1
        assert body["alerted_count"] == 1
        assert body["anomalies"][0]["kind"] == "spike"
        assert body["anomalies"][0]["severity"] == "high"
        assert mock_alert.await_count == 1
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_cost_anomalies_requires_growth(async_client: AsyncClient, app):
    mock_user = CurrentUser(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        email="anomalies-denied@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = await async_client.get(
            "/api/v1/costs/anomalies",
            params={"target_date": "2026-02-12"},
        )
        assert response.status_code == 403
        assert "requires" in response.json()["error"].lower()
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
        with patch(
            "app.modules.reporting.api.v1.costs.CostAggregator.get_summary",
            new=AsyncMock(),
        ) as mock_summary:
            mock_summary.return_value = SimpleNamespace(records=[])
            response = await async_client.post("/api/v1/costs/analyze")
            assert response.status_code == 200
            data = response.json()
            assert data["summary"] == "No cost data available for analysis."

        # Records -> analyzer path
        with (
            patch(
                "app.modules.reporting.api.v1.costs.CostAggregator.get_summary",
                new=AsyncMock(),
            ) as mock_summary,
            patch(
                "app.modules.reporting.api.v1.costs.LLMFactory.create",
                return_value=MagicMock(),
            ) as mock_create,
            patch(
                "app.modules.reporting.api.v1.costs.FinOpsAnalyzer"
            ) as mock_analyzer_class,
        ):
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
async def test_analyze_costs_available_on_starter(async_client: AsyncClient, app):
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
        assert response.status_code == 200
        payload = response.json()
        assert payload["summary"] == "No cost data available for analysis."
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
        with patch(
            "app.modules.governance.domain.jobs.processor.enqueue_job",
            new=AsyncMock(return_value=mock_job),
        ):
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
        with patch(
            "app.modules.governance.domain.jobs.processor.enqueue_job",
            new=AsyncMock(return_value=mock_job),
        ) as mock_enqueue:
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
async def test_trigger_ingest_backfill_requires_growth_tier(
    async_client: AsyncClient, app
):
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
async def test_trigger_ingest_backfill_requires_both_dates(
    async_client: AsyncClient, app
):
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
        with patch(
            "app.modules.reporting.api.v1.costs.CostAggregator.get_dashboard_summary",
            new=AsyncMock(),
        ) as mock_summary:
            mock_summary.return_value = {
                "total_cost": 123.45,
                "data_quality": {
                    "freshness": {"status": "mixed"},
                    "canonical_mapping": {
                        "mapped_percentage": 99.1,
                        "meets_target": True,
                    },
                },
            }

            response = await async_client.get(
                "/api/v1/costs",
                params={"start_date": "2024-01-01", "end_date": "2024-01-31"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["data_quality"]["freshness"]["status"] == "mixed"
            assert (
                data["data_quality"]["canonical_mapping"]["mapped_percentage"] == 99.1
            )
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
        with (
            patch(
                "app.modules.reporting.api.v1.costs.CostAggregator.count_records",
                new=AsyncMock(return_value=costs_api.LARGE_DATASET_THRESHOLD + 1),
            ),
            patch(
                "app.modules.governance.domain.jobs.processor.enqueue_job",
                new=AsyncMock(return_value=mock_job),
            ) as mock_enqueue,
        ):
            response = await async_client.get(
                "/api/v1/costs",
                params={
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-31",
                    "provider": "aws",
                },
            )

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "accepted"
        assert body["job_id"] == str(mock_job.id)
        assert mock_enqueue.await_args.kwargs["payload"]["provider"] == "aws"
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_trigger_ingest_rejects_invalid_date_order(
    async_client: AsyncClient, app
):
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
async def test_get_unit_economics_rejects_invalid_date_order(
    async_client: AsyncClient, app
):
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
async def test_get_unit_economics_alert_failure_is_non_fatal(
    async_client: AsyncClient, app, db, member_user
):
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


@pytest.mark.asyncio
async def test_get_acceptance_kpis(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="q2-kpi@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.PRO,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with (
            patch(
                "app.modules.reporting.api.v1.costs._compute_ingestion_sla_metrics",
                new=AsyncMock(
                    return_value=costs_api.IngestionSLAResponse(
                        window_hours=168,
                        target_success_rate_percent=95.0,
                        total_jobs=12,
                        successful_jobs=12,
                        failed_jobs=0,
                        success_rate_percent=100.0,
                        meets_sla=True,
                        latest_completed_at="2026-02-13T10:00:00+00:00",
                        avg_duration_seconds=120.0,
                        p95_duration_seconds=180.0,
                        records_ingested=1250,
                    )
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._compute_provider_recency_summaries",
                new=AsyncMock(
                    return_value=[
                        costs_api.ProviderRecencyResponse(
                            provider="aws",
                            active_connections=2,
                            recently_ingested=2,
                            stale_connections=0,
                            never_ingested=0,
                            latest_ingested_at="2026-02-13T09:00:00+00:00",
                            recency_target_hours=48,
                            meets_recency_target=True,
                        )
                    ]
                ),
            ),
            patch(
                "app.modules.reporting.domain.attribution_engine.AttributionEngine.get_allocation_coverage",
                new=AsyncMock(
                    return_value={
                        "target_percentage": 90.0,
                        "coverage_percentage": 94.0,
                        "meets_target": True,
                        "status": "ok",
                        "allocated_cost": 940.0,
                        "unallocated_cost": 60.0,
                        "total_cost": 1000.0,
                    }
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._get_or_create_unit_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        default_request_volume=1000,
                        default_workload_volume=100,
                        default_customer_volume=20,
                        anomaly_threshold_percent=20.0,
                    )
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._window_total_cost",
                new=AsyncMock(side_effect=[Decimal("1000"), Decimal("900")]),
            ),
        ):
            response = await async_client.get(
                "/api/v1/costs/acceptance/kpis",
                params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["all_targets_met"] is True
        assert payload["available_metrics"] >= 3
        by_key = {item["key"]: item for item in payload["metrics"]}
        assert by_key["ingestion_reliability"]["meets_target"] is True
        assert by_key["chargeback_coverage"]["actual"] == "94.00%"
        assert by_key["unit_economics_stability"]["meets_target"] is True
        assert "license_governance_reliability" in by_key
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_acceptance_kpis_includes_license_governance_metrics(
    async_client: AsyncClient, app, db
):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="acceptance-kpi-license@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        db.add(Tenant(id=tenant_id, name="Acceptance KPI License", plan=PricingTier.PRO.value))
        db.add(
            User(id=user_id, tenant_id=tenant_id, email=mock_user.email, role=UserRole.ADMIN)
        )
        db.add(
            LicenseConnection(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                name="M365 Seats",
                vendor="microsoft_365",
                auth_method="api_key",
                api_key=None,
                connector_config={},
                license_feed=[],
                is_active=True,
            )
        )
        db.add_all(
            [
                RemediationRequest(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    resource_id="user-1",
                    resource_type="license_seat",
                    provider="license",
                    region="global",
                    action=RemediationAction.RECLAIM_LICENSE_SEAT,
                    status=RemediationStatus.COMPLETED,
                    requested_by_user_id=user_id,
                    created_at=datetime(2026, 1, 10, 10, 0, tzinfo=timezone.utc),
                    executed_at=datetime(2026, 1, 10, 12, 0, tzinfo=timezone.utc),
                ),
                RemediationRequest(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    resource_id="user-2",
                    resource_type="license_seat",
                    provider="license",
                    region="global",
                    action=RemediationAction.RECLAIM_LICENSE_SEAT,
                    status=RemediationStatus.FAILED,
                    requested_by_user_id=user_id,
                    created_at=datetime(2026, 1, 11, 10, 0, tzinfo=timezone.utc),
                ),
                RemediationRequest(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    resource_id="user-3",
                    resource_type="license_seat",
                    provider="license",
                    region="global",
                    action=RemediationAction.RECLAIM_LICENSE_SEAT,
                    status=RemediationStatus.SCHEDULED,
                    requested_by_user_id=user_id,
                    created_at=datetime(2026, 1, 12, 10, 0, tzinfo=timezone.utc),
                ),
            ]
        )
        await db.commit()

        with (
            patch(
                "app.modules.reporting.api.v1.costs._compute_ingestion_sla_metrics",
                new=AsyncMock(
                    return_value=costs_api.IngestionSLAResponse(
                        window_hours=168,
                        target_success_rate_percent=95.0,
                        total_jobs=12,
                        successful_jobs=12,
                        failed_jobs=0,
                        success_rate_percent=100.0,
                        meets_sla=True,
                        latest_completed_at="2026-02-13T10:00:00+00:00",
                        avg_duration_seconds=120.0,
                        p95_duration_seconds=180.0,
                        records_ingested=1250,
                    )
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._compute_provider_recency_summaries",
                new=AsyncMock(
                    return_value=[
                        costs_api.ProviderRecencyResponse(
                            provider="aws",
                            active_connections=1,
                            recently_ingested=1,
                            stale_connections=0,
                            never_ingested=0,
                            latest_ingested_at="2026-02-13T09:00:00+00:00",
                            recency_target_hours=48,
                            meets_recency_target=True,
                        )
                    ]
                ),
            ),
            patch(
                "app.modules.reporting.domain.attribution_engine.AttributionEngine.get_allocation_coverage",
                new=AsyncMock(
                    return_value={
                        "target_percentage": 90.0,
                        "coverage_percentage": 94.0,
                        "meets_target": True,
                        "status": "ok",
                        "allocated_cost": 94.0,
                        "unallocated_cost": 6.0,
                        "total_cost": 100.0,
                    }
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._get_or_create_unit_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        default_request_volume=1000,
                        default_workload_volume=100,
                        default_customer_volume=20,
                        anomaly_threshold_percent=20.0,
                    )
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._window_total_cost",
                new=AsyncMock(side_effect=[Decimal("100"), Decimal("90")]),
            ),
        ):
            response = await async_client.get(
                "/api/v1/costs/acceptance/kpis",
                params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
            )

        assert response.status_code == 200
        payload = response.json()
        by_key = {item["key"]: item for item in payload["metrics"]}
        license_metric = by_key["license_governance_reliability"]
        assert license_metric["available"] is True
        assert license_metric["details"]["active_license_connections"] == 1
        assert license_metric["details"]["total_requests"] == 3
        assert license_metric["details"]["completed_requests"] == 1
        assert license_metric["details"]["failed_requests"] == 1
        assert license_metric["details"]["in_flight_requests"] == 1
        assert license_metric["meets_target"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_acceptance_kpis_includes_ledger_quality_metrics_when_data_exists(
    async_client: AsyncClient, app, db
):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="acceptance-kpi-ledger@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        db.add(Tenant(id=tenant_id, name="Acceptance KPI Ledger", plan=PricingTier.PRO.value))
        db.add(
            User(id=user_id, tenant_id=tenant_id, email=mock_user.email, role=UserRole.ADMIN)
        )

        account_id = uuid.uuid4()
        db.add(
            CloudAccount(
                id=account_id,
                tenant_id=tenant_id,
                provider="aws",
                name="Prod AWS",
                is_active=True,
            )
        )

        # 4 rows in-window:
        # - 2 normalized + mapped
        # - 1 unknown service + unmapped
        # - 1 usage_amount present but missing usage_unit (normalization failure)
        record_days = [date(2026, 1, d) for d in (10, 11, 12, 13)]
        db.add_all(
            [
                CostRecord(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    account_id=account_id,
                    service="AmazonEC2",
                    region="us-east-1",
                    usage_type="BoxUsage:t3.micro",
                    resource_id="i-123",
                    usage_amount=Decimal("1"),
                    usage_unit="Hrs",
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
                    ingestion_metadata={},
                    tags=None,
                    attribution_id=None,
                    allocated_to=None,
                    recorded_at=record_days[0],
                    timestamp=datetime(
                        record_days[0].year,
                        record_days[0].month,
                        record_days[0].day,
                        tzinfo=timezone.utc,
                    ),
                ),
                CostRecord(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    account_id=account_id,
                    service="AmazonS3",
                    region="us-east-1",
                    usage_type="TimedStorage-ByteHrs",
                    resource_id="bucket-abc",
                    usage_amount=None,
                    usage_unit=None,
                    canonical_charge_category="storage",
                    canonical_charge_subcategory="capacity",
                    canonical_mapping_version="focus-1.3-v1",
                    cost_usd=Decimal("5.00"),
                    amount_raw=Decimal("5.00"),
                    currency="USD",
                    carbon_kg=None,
                    is_preliminary=False,
                    cost_status="FINAL",
                    reconciliation_run_id=None,
                    ingestion_metadata={},
                    tags=None,
                    attribution_id=None,
                    allocated_to=None,
                    recorded_at=record_days[1],
                    timestamp=datetime(
                        record_days[1].year,
                        record_days[1].month,
                        record_days[1].day,
                        tzinfo=timezone.utc,
                    ),
                ),
                CostRecord(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    account_id=account_id,
                    service="Unknown",
                    region="us-east-1",
                    usage_type="Usage",
                    resource_id="unknown",
                    usage_amount=None,
                    usage_unit=None,
                    canonical_charge_category="unmapped",
                    canonical_charge_subcategory=None,
                    canonical_mapping_version="focus-1.3-v1",
                    cost_usd=Decimal("1.00"),
                    amount_raw=Decimal("1.00"),
                    currency="USD",
                    carbon_kg=None,
                    is_preliminary=False,
                    cost_status="FINAL",
                    reconciliation_run_id=None,
                    ingestion_metadata={},
                    tags=None,
                    attribution_id=None,
                    allocated_to=None,
                    recorded_at=record_days[2],
                    timestamp=datetime(
                        record_days[2].year,
                        record_days[2].month,
                        record_days[2].day,
                        tzinfo=timezone.utc,
                    ),
                ),
                CostRecord(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    account_id=account_id,
                    service="AmazonRDS",
                    region="us-east-1",
                    usage_type="InstanceUsage:db.t3.micro",
                    resource_id="db-xyz",
                    usage_amount=Decimal("3"),
                    usage_unit=None,  # normalization failure
                    canonical_charge_category="database",
                    canonical_charge_subcategory="managed",
                    canonical_mapping_version="focus-1.3-v1",
                    cost_usd=Decimal("7.00"),
                    amount_raw=Decimal("7.00"),
                    currency="USD",
                    carbon_kg=None,
                    is_preliminary=False,
                    cost_status="FINAL",
                    reconciliation_run_id=None,
                    ingestion_metadata={},
                    tags=None,
                    attribution_id=None,
                    allocated_to=None,
                    recorded_at=record_days[3],
                    timestamp=datetime(
                        record_days[3].year,
                        record_days[3].month,
                        record_days[3].day,
                        tzinfo=timezone.utc,
                    ),
                ),
            ]
        )
        await db.commit()

        with (
            patch(
                "app.modules.reporting.api.v1.costs._compute_ingestion_sla_metrics",
                new=AsyncMock(
                    return_value=costs_api.IngestionSLAResponse(
                        window_hours=168,
                        target_success_rate_percent=95.0,
                        total_jobs=1,
                        successful_jobs=1,
                        failed_jobs=0,
                        success_rate_percent=100.0,
                        meets_sla=True,
                        latest_completed_at="2026-02-13T10:00:00+00:00",
                        avg_duration_seconds=60.0,
                        p95_duration_seconds=60.0,
                        records_ingested=4,
                    )
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._compute_provider_recency_summaries",
                new=AsyncMock(
                    return_value=[
                        costs_api.ProviderRecencyResponse(
                            provider="aws",
                            active_connections=1,
                            recently_ingested=1,
                            stale_connections=0,
                            never_ingested=0,
                            latest_ingested_at="2026-02-13T09:00:00+00:00",
                            recency_target_hours=48,
                            meets_recency_target=True,
                        )
                    ]
                ),
            ),
            patch(
                "app.modules.reporting.domain.attribution_engine.AttributionEngine.get_allocation_coverage",
                new=AsyncMock(
                    return_value={
                        "target_percentage": 90.0,
                        "coverage_percentage": 94.0,
                        "meets_target": True,
                        "status": "ok",
                        "allocated_cost": 94.0,
                        "unallocated_cost": 6.0,
                        "total_cost": 100.0,
                    }
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._get_or_create_unit_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        default_request_volume=1000,
                        default_workload_volume=100,
                        default_customer_volume=20,
                        anomaly_threshold_percent=20.0,
                    )
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._window_total_cost",
                new=AsyncMock(side_effect=[Decimal("100"), Decimal("90")]),
            ),
        ):
            response = await async_client.get(
                "/api/v1/costs/acceptance/kpis",
                params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
            )

        assert response.status_code == 200
        payload = response.json()
        by_key = {item["key"]: item for item in payload["metrics"]}

        assert by_key["ledger_normalization_coverage"]["available"] is True
        assert by_key["canonical_mapping_coverage"]["available"] is True
        assert by_key["ledger_normalization_coverage"]["actual"] == "50.00%"
        assert by_key["canonical_mapping_coverage"]["actual"] == "75.00%"
        assert by_key["ledger_normalization_coverage"]["meets_target"] is False
        assert by_key["canonical_mapping_coverage"]["meets_target"] is False
        assert payload["all_targets_met"] is False
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_acceptance_kpis_marks_unavailable_features(
    async_client: AsyncClient, app
):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="q2-kpi-starter@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.STARTER,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with (
            patch(
                "app.modules.reporting.api.v1.costs._compute_ingestion_sla_metrics",
                new=AsyncMock(
                    return_value=costs_api.IngestionSLAResponse(
                        window_hours=168,
                        target_success_rate_percent=95.0,
                        total_jobs=2,
                        successful_jobs=1,
                        failed_jobs=1,
                        success_rate_percent=50.0,
                        meets_sla=False,
                        latest_completed_at="2026-02-13T10:00:00+00:00",
                        avg_duration_seconds=200.0,
                        p95_duration_seconds=300.0,
                        records_ingested=12,
                    )
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._compute_provider_recency_summaries",
                new=AsyncMock(
                    return_value=[
                        costs_api.ProviderRecencyResponse(
                            provider="aws",
                            active_connections=1,
                            recently_ingested=0,
                            stale_connections=1,
                            never_ingested=0,
                            latest_ingested_at="2026-02-10T09:00:00+00:00",
                            recency_target_hours=48,
                            meets_recency_target=False,
                        )
                    ]
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._get_or_create_unit_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        default_request_volume=1000,
                        default_workload_volume=100,
                        default_customer_volume=20,
                        anomaly_threshold_percent=20.0,
                    )
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._window_total_cost",
                new=AsyncMock(side_effect=[Decimal("500"), Decimal("300")]),
            ),
        ):
            response = await async_client.get(
                "/api/v1/costs/acceptance/kpis",
                params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
            )

        assert response.status_code == 200
        payload = response.json()
        by_key = {item["key"]: item for item in payload["metrics"]}
        assert by_key["chargeback_coverage"]["available"] is False
        assert "Growth tier" in by_key["chargeback_coverage"]["target"]
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_get_acceptance_kpis_csv_export(async_client: AsyncClient, app):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="q2-kpi-csv@valdrix.io",
        role=UserRole.MEMBER,
        tier=PricingTier.PRO,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        with (
            patch(
                "app.modules.reporting.api.v1.costs._compute_ingestion_sla_metrics",
                new=AsyncMock(
                    return_value=costs_api.IngestionSLAResponse(
                        window_hours=168,
                        target_success_rate_percent=95.0,
                        total_jobs=10,
                        successful_jobs=9,
                        failed_jobs=1,
                        success_rate_percent=90.0,
                        meets_sla=False,
                        latest_completed_at="2026-02-13T10:00:00+00:00",
                        avg_duration_seconds=120.0,
                        p95_duration_seconds=200.0,
                        records_ingested=400,
                    )
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._compute_provider_recency_summaries",
                new=AsyncMock(
                    return_value=[
                        costs_api.ProviderRecencyResponse(
                            provider="aws",
                            active_connections=1,
                            recently_ingested=1,
                            stale_connections=0,
                            never_ingested=0,
                            latest_ingested_at="2026-02-13T09:00:00+00:00",
                            recency_target_hours=48,
                            meets_recency_target=True,
                        )
                    ]
                ),
            ),
            patch(
                "app.modules.reporting.domain.attribution_engine.AttributionEngine.get_allocation_coverage",
                new=AsyncMock(
                    return_value={
                        "target_percentage": 90.0,
                        "coverage_percentage": 91.0,
                        "meets_target": True,
                        "status": "ok",
                        "allocated_cost": 910.0,
                        "unallocated_cost": 90.0,
                        "total_cost": 1000.0,
                    }
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._get_or_create_unit_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        default_request_volume=1000,
                        default_workload_volume=100,
                        default_customer_volume=20,
                        anomaly_threshold_percent=20.0,
                    )
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._window_total_cost",
                new=AsyncMock(side_effect=[Decimal("1000"), Decimal("800")]),
            ),
        ):
            response = await async_client.get(
                "/api/v1/costs/acceptance/kpis",
                params={
                    "start_date": "2026-01-01",
                    "end_date": "2026-01-31",
                    "response_format": "csv",
                },
            )

        assert response.status_code == 200
        assert "text/csv" in response.headers["content-type"]
        assert "attachment; filename=" in response.headers.get(
            "content-disposition", ""
        )
        assert "metric,key,label,available,target,actual,meets_target" in response.text
    finally:
        app.dependency_overrides.pop(get_current_user, None)


@pytest.mark.asyncio
async def test_capture_acceptance_kpis_persists_audit_evidence(
    async_client: AsyncClient, app, db
):
    tenant_id = uuid.uuid4()
    user_id = uuid.uuid4()
    mock_user = CurrentUser(
        id=user_id,
        tenant_id=tenant_id,
        email="kpi-capture-admin@valdrix.io",
        role=UserRole.ADMIN,
        tier=PricingTier.PRO,
    )

    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        db.add(Tenant(id=tenant_id, name="KPI Evidence Tenant", plan=PricingTier.PRO.value))
        db.add(
            User(id=user_id, tenant_id=tenant_id, email=mock_user.email, role=UserRole.ADMIN)
        )
        await db.commit()

        with (
            patch(
                "app.modules.reporting.api.v1.costs._compute_ingestion_sla_metrics",
                new=AsyncMock(
                    return_value=costs_api.IngestionSLAResponse(
                        window_hours=168,
                        target_success_rate_percent=95.0,
                        total_jobs=12,
                        successful_jobs=12,
                        failed_jobs=0,
                        success_rate_percent=100.0,
                        meets_sla=True,
                        latest_completed_at="2026-02-13T10:00:00+00:00",
                        avg_duration_seconds=120.0,
                        p95_duration_seconds=180.0,
                        records_ingested=1250,
                    )
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._compute_provider_recency_summaries",
                new=AsyncMock(
                    return_value=[
                        costs_api.ProviderRecencyResponse(
                            provider="aws",
                            active_connections=2,
                            recently_ingested=2,
                            stale_connections=0,
                            never_ingested=0,
                            latest_ingested_at="2026-02-13T09:00:00+00:00",
                            recency_target_hours=48,
                            meets_recency_target=True,
                        )
                    ]
                ),
            ),
            patch(
                "app.modules.reporting.domain.attribution_engine.AttributionEngine.get_allocation_coverage",
                new=AsyncMock(
                    return_value={
                        "target_percentage": 90.0,
                        "coverage_percentage": 94.0,
                        "meets_target": True,
                        "status": "ok",
                        "allocated_cost": 940.0,
                        "unallocated_cost": 60.0,
                        "total_cost": 1000.0,
                    }
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._get_or_create_unit_settings",
                new=AsyncMock(
                    return_value=SimpleNamespace(
                        default_request_volume=1000,
                        default_workload_volume=100,
                        default_customer_volume=20,
                        anomaly_threshold_percent=20.0,
                    )
                ),
            ),
            patch(
                "app.modules.reporting.api.v1.costs._window_total_cost",
                new=AsyncMock(side_effect=[Decimal("1000"), Decimal("900")]),
            ),
        ):
            response = await async_client.post(
                "/api/v1/costs/acceptance/kpis/capture",
                params={"start_date": "2026-01-01", "end_date": "2026-01-31"},
            )

        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "captured"
        assert payload["event_id"]
        assert payload["run_id"]
        assert payload["acceptance_kpis"]["start_date"] == "2026-01-01"

        list_response = await async_client.get("/api/v1/costs/acceptance/kpis/evidence")
        assert list_response.status_code == 200
        evidence = list_response.json()
        assert evidence["total"] >= 1
        assert evidence["items"][0]["event_id"] == payload["event_id"]
        assert evidence["items"][0]["acceptance_kpis"]["end_date"] == "2026-01-31"
    finally:
        app.dependency_overrides.pop(get_current_user, None)
