import pytest
import uuid
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from app.modules.reporting.api.v1.carbon import (
    get_carbon_footprint,
    get_carbon_budget,
    analyze_graviton_opportunities,
    get_carbon_intensity_forecast,
)
from app.modules.reporting.api.v1 import carbon as carbon_api


@pytest.mark.asyncio
async def test_get_carbon_footprint_date_range_error():
    user = MagicMock()
    db = AsyncMock()
    start = date.today()
    end = start + timedelta(days=400)

    with pytest.raises(HTTPException) as exc:
        await get_carbon_footprint(start, end, user, db, provider="aws")
    assert exc.value.status_code == 400
    assert "Date range cannot exceed 1 year" in exc.value.detail


@pytest.mark.asyncio
@patch(
    "app.modules.reporting.api.v1.carbon._fetch_provider_cost_data",
    new_callable=AsyncMock,
)
@patch(
    "app.modules.reporting.api.v1.carbon._get_provider_connection",
    new_callable=AsyncMock,
)
async def test_get_carbon_footprint_success(mock_get_connection, mock_fetch_cost_data):
    user = MagicMock()
    user.tenant_id = "tenant-123"
    db = AsyncMock()
    mock_get_connection.return_value = MagicMock()
    mock_fetch_cost_data.return_value = [{"service": "Amazon EC2", "cost_usd": 100.0}]

    with patch(
        "app.modules.reporting.api.v1.carbon.CarbonCalculator"
    ) as mock_calc_class:
        mock_calc = mock_calc_class.return_value
        mock_calc.calculate_from_costs.return_value = {"total_co2_kg": 10.5}

        response = await get_carbon_footprint(
            date.today(), date.today(), user, db, provider="aws"
        )
        assert response["total_co2_kg"] == 10.5


@pytest.mark.asyncio
@patch(
    "app.modules.reporting.api.v1.carbon._get_provider_connection",
    new_callable=AsyncMock,
)
async def test_get_carbon_budget_no_connection(mock_get_connection):
    user = MagicMock()
    user.tenant_id = "tenant-123"
    db = AsyncMock()
    mock_get_connection.return_value = None

    response = await get_carbon_budget(user, db, provider="aws")
    assert response["alert_status"] == "unknown"


@pytest.mark.asyncio
@patch(
    "app.modules.reporting.api.v1.carbon._fetch_provider_cost_data",
    new_callable=AsyncMock,
)
@patch(
    "app.modules.reporting.api.v1.carbon._get_provider_connection",
    new_callable=AsyncMock,
)
@patch("app.modules.reporting.api.v1.carbon.CarbonBudgetService")
async def test_get_carbon_budget_success(
    mock_budget_service_class, mock_get_connection, mock_fetch_cost_data
):
    user = MagicMock()
    user.tenant_id = "tenant-123"
    db = AsyncMock()

    mock_get_connection.return_value = MagicMock()
    mock_fetch_cost_data.return_value = [{"service": "Amazon EC2", "cost_usd": 10.0}]

    # Carbon settings lookup query
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute.return_value = mock_result

    mock_budget_service = mock_budget_service_class.return_value
    mock_budget_service.get_budget_status = AsyncMock(
        return_value={"alert_status": "ok"}
    )

    response = await get_carbon_budget(user, db, provider="aws")
    assert response["alert_status"] == "ok"


@pytest.mark.asyncio
async def test_get_carbon_footprint_invalid_provider():
    user = MagicMock()
    user.tenant_id = "tenant-123"
    db = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await get_carbon_footprint(
            date.today(), date.today(), user, db, provider="oracle"
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
@patch(
    "app.modules.reporting.api.v1.carbon._get_provider_connection",
    new_callable=AsyncMock,
)
async def test_get_carbon_footprint_accepts_cloud_plus_provider(
    mock_get_connection,
):
    user = MagicMock()
    user.tenant_id = "tenant-123"
    db = AsyncMock()
    mock_get_connection.return_value = None

    with pytest.raises(HTTPException) as exc:
        await get_carbon_footprint(
            date.today(),
            date.today(),
            user,
            db,
            provider="saas",
        )

    assert exc.value.status_code == 400
    assert "No active SAAS connection found" in exc.value.detail


@pytest.mark.asyncio
@patch("app.modules.reporting.api.v1.carbon.MultiTenantAWSAdapter")
@patch("app.modules.reporting.api.v1.carbon.GravitonAnalyzer")
async def test_analyze_graviton_opportunities_success(
    mock_analyzer_class, mock_adapter_class
):
    user = MagicMock()
    user.tenant_id = "tenant-123"
    db = AsyncMock()

    mock_result = MagicMock()
    connection = MagicMock()
    connection.aws_account_id = "123456789012"
    connection.role_arn = "arn:aws:iam::123456789012:role/ValdrixRole"
    connection.external_id = "external-id"
    connection.region = "us-east-1"
    connection.tenant_id = "tenant-123"
    connection.cur_bucket_name = "cur-bucket"
    connection.cur_report_name = "cur-report"
    connection.cur_prefix = "cur-prefix"
    mock_result.scalar_one_or_none.return_value = connection
    db.execute.return_value = mock_result

    _ = mock_adapter_class.return_value

    mock_analyzer = mock_analyzer_class.return_value
    mock_analyzer.analyze = AsyncMock(return_value={"candidates": []})

    response = await analyze_graviton_opportunities(user, db)
    assert "candidates" in response


@pytest.mark.asyncio
@patch("app.modules.reporting.api.v1.carbon.CarbonAwareScheduler")
async def test_get_carbon_intensity_forecast(mock_scheduler_class):
    request = MagicMock()
    user = MagicMock()
    mock_scheduler = mock_scheduler_class.return_value
    mock_scheduler.get_intensity_forecast = AsyncMock(return_value=[])
    mock_scheduler.get_region_intensity = AsyncMock(return_value=0.5)

    response = await get_carbon_intensity_forecast(request, user, "us-east-1", 24)
    assert response["current_intensity"] == 0.5


@pytest.mark.asyncio
@patch("app.modules.reporting.api.v1.carbon.CarbonAwareScheduler")
async def test_get_carbon_intensity_forecast_default_region_hint_is_global(
    mock_scheduler_class,
):
    request = MagicMock()
    user = MagicMock()
    mock_scheduler = mock_scheduler_class.return_value
    mock_scheduler.get_intensity_forecast = AsyncMock(return_value=[])
    mock_scheduler.get_region_intensity = AsyncMock(return_value=0.4)

    response = await get_carbon_intensity_forecast(request, user)

    assert response["region"] == "global"
    mock_scheduler.get_intensity_forecast.assert_awaited_once_with("global", 24)
    mock_scheduler.get_region_intensity.assert_awaited_once_with("global")


@pytest.mark.asyncio
@patch(
    "app.modules.reporting.api.v1.carbon._fetch_provider_cost_data",
    new_callable=AsyncMock,
)
@patch(
    "app.modules.reporting.api.v1.carbon._get_provider_connection",
    new_callable=AsyncMock,
)
async def test_get_carbon_footprint_cache_hit_skips_provider_calls(
    mock_get_connection,
    mock_fetch_cost_data,
):
    user = MagicMock()
    user.tenant_id = "tenant-123"
    db = AsyncMock()

    class CacheHit:
        enabled = True

        async def get(self, _key: str):
            return {"total_co2_kg": 7.7}

        async def set(self, _key: str, _value, ttl=None):
            return True

    with patch(
        "app.modules.reporting.api.v1.carbon.get_cache_service",
        return_value=CacheHit(),
    ):
        response = await get_carbon_footprint(
            date.today(), date.today(), user, db, provider="aws"
        )

    assert response["total_co2_kg"] == 7.7
    mock_get_connection.assert_not_awaited()
    mock_fetch_cost_data.assert_not_awaited()


@pytest.mark.asyncio
@patch(
    "app.modules.reporting.api.v1.carbon._fetch_provider_cost_data",
    new_callable=AsyncMock,
)
@patch(
    "app.modules.reporting.api.v1.carbon._get_provider_connection",
    new_callable=AsyncMock,
)
@patch("app.modules.reporting.api.v1.carbon.CarbonCalculator")
@patch("app.modules.reporting.api.v1.carbon.CarbonBudgetService")
async def test_get_carbon_budget_uses_tenant_default_region_for_global_aws(
    mock_budget_service_class,
    mock_calculator_class,
    mock_get_connection,
    mock_fetch_cost_data,
):
    user = MagicMock()
    user.tenant_id = "tenant-123"
    db = AsyncMock()

    connection = MagicMock()
    connection.provider = "aws"
    connection.region = "us-west-2"
    mock_get_connection.return_value = connection
    mock_fetch_cost_data.return_value = [{"service": "Amazon EC2", "cost_usd": 10.0}]

    settings_row = MagicMock()
    settings_row.default_region = "eu-west-1"
    settings_result = MagicMock()
    settings_result.scalar_one_or_none.return_value = settings_row
    db.execute.return_value = settings_result

    mock_budget_service = mock_budget_service_class.return_value
    mock_budget_service.get_budget_status = AsyncMock(return_value={"alert_status": "ok"})
    mock_budget_service.send_carbon_alert = AsyncMock()

    mock_calculator = mock_calculator_class.return_value
    mock_calculator.calculate_from_costs.return_value = {"total_co2_kg": 1.0}

    response = await get_carbon_budget(user, db, region="global", provider="aws")

    assert response["alert_status"] == "ok"
    mock_calculator.calculate_from_costs.assert_called_once()
    _, kwargs = mock_calculator.calculate_from_costs.call_args
    assert kwargs["region"] == "eu-west-1"


def test_carbon_helper_branches() -> None:
    assert carbon_api._resolve_region_hint("aws", "") == "us-east-1"
    assert carbon_api._resolve_region_hint("saas", "") == "global"
    assert carbon_api._resolve_region_hint("saas", "us-east-1") == "global"
    assert carbon_api._resolve_region_hint("aws", "us-east-1") == "us-east-1"

    conn = MagicMock()
    conn.region = "eu-west-1"
    assert carbon_api._resolve_calc_region(conn, "aws", "ap-south-1") == "ap-south-1"
    assert carbon_api._resolve_calc_region(conn, "saas", "us-east-1") == "eu-west-1"

    assert carbon_api._coerce_query_int("bad", default=24, minimum=1, maximum=72) == 24
    assert carbon_api._coerce_query_int(0, default=24, minimum=1, maximum=72) == 1
    assert carbon_api._coerce_query_int(100, default=24, minimum=1, maximum=72) == 72

    user = MagicMock()
    user.tenant_id = None
    with pytest.raises(HTTPException):
        carbon_api._require_tenant_id(user)


@pytest.mark.asyncio
async def test_carbon_cache_helpers_branches() -> None:
    cache = MagicMock()
    cache.enabled = True
    cache.get = AsyncMock(return_value="not-dict")
    cache.set = AsyncMock()

    with patch("app.modules.reporting.api.v1.carbon.get_cache_service", return_value=cache):
        assert await carbon_api._read_cached_payload("k") is None
        await carbon_api._store_cached_payload("k", {"ok": True}, ttl=timedelta(minutes=5))
    cache.set.assert_awaited_once()


@pytest.mark.asyncio
async def test_fetch_provider_cost_data_non_aws_branch() -> None:
    adapter = MagicMock()
    adapter.get_cost_and_usage = AsyncMock(return_value=[{"service": "S3"}])
    connection = MagicMock()

    with patch("app.modules.reporting.api.v1.carbon.AdapterFactory.get_adapter", return_value=adapter):
        payload = await carbon_api._fetch_provider_cost_data(
            connection=connection,
            provider="saas",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
        )
    assert payload[0]["provider"] == "saas"


@pytest.mark.asyncio
async def test_get_carbon_footprint_provider_required() -> None:
    user = MagicMock()
    user.tenant_id = "tenant-123"
    with pytest.raises(HTTPException) as exc:
        await get_carbon_footprint(date.today(), date.today(), user, AsyncMock(), provider=None)
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_get_carbon_budget_provider_required_and_cache_hit() -> None:
    user = MagicMock()
    user.tenant_id = "tenant-123"
    with pytest.raises(HTTPException) as exc:
        await get_carbon_budget(user, AsyncMock(), provider=None)
    assert exc.value.status_code == 400


def test_factor_set_and_update_log_mapping_helpers() -> None:
    factor_row = MagicMock()
    factor_row.id = uuid.uuid4()
    factor_row.status = "active"
    factor_row.is_active = True
    factor_row.factor_source = "watttime"
    factor_row.factor_version = "2026.01"
    factor_row.factor_timestamp = datetime(2026, 2, 1, 10, 0, tzinfo=timezone.utc)
    factor_row.methodology_version = "v2"
    factor_row.factors_checksum_sha256 = "abc123"
    factor_row.created_at = datetime(2026, 2, 1, 11, 0, tzinfo=timezone.utc)
    factor_row.activated_at = datetime(2026, 2, 1, 12, 0, tzinfo=timezone.utc)
    factor_item = carbon_api._factor_set_to_item(factor_row)
    assert factor_item.id == str(factor_row.id)
    assert factor_item.activated_at == factor_row.activated_at.isoformat()

    log_row = MagicMock()
    log_row.id = uuid.uuid4()
    log_row.recorded_at = datetime(2026, 2, 1, 13, 0, tzinfo=timezone.utc)
    log_row.action = "manual_activated"
    log_row.message = "ok"
    log_row.old_factor_set_id = None
    log_row.new_factor_set_id = uuid.uuid4()
    log_row.old_checksum_sha256 = None
    log_row.new_checksum_sha256 = "def456"
    log_row.details = "bad-shape"
    log_item = carbon_api._update_log_to_item(log_row)
    assert log_item.id == str(log_row.id)
    assert log_item.new_factor_set_id == str(log_row.new_factor_set_id)
    assert log_item.details == {}


@pytest.mark.asyncio
async def test_get_provider_connection_and_aws_gross_usage_branch() -> None:
    db = AsyncMock()
    tenant_id = uuid.uuid4()

    with patch(
        "app.modules.reporting.api.v1.carbon.list_tenant_connections",
        new=AsyncMock(return_value=[]),
    ):
        assert await carbon_api._get_provider_connection(db, tenant_id, "aws") is None

    connection = MagicMock()
    with patch(
        "app.modules.reporting.api.v1.carbon.list_tenant_connections",
        new=AsyncMock(return_value=[connection]),
    ):
        assert (
            await carbon_api._get_provider_connection(db, tenant_id, "aws")
            is connection
        )

    adapter = MagicMock()
    adapter.get_gross_usage = AsyncMock(return_value=[{"service": "EC2", "cost_usd": 1.0}])
    with patch(
        "app.modules.reporting.api.v1.carbon.AdapterFactory.get_adapter",
        return_value=adapter,
    ):
        payload = await carbon_api._fetch_provider_cost_data(
            connection=connection,
            provider="aws",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 2),
        )
    assert payload[0]["provider"] == "aws"
    adapter.get_gross_usage.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_green_schedule_cache_hit_branch() -> None:
    user = MagicMock()
    user.tenant_id = "tenant-123"

    class CacheHit:
        enabled = True

        async def get(self, _key: str):
            return {"region": "global", "optimal_start_time": None, "recommendation": "Execute now"}

        async def set(self, _key: str, _value, ttl=None):
            return True

    with patch(
        "app.modules.reporting.api.v1.carbon.get_cache_service",
        return_value=CacheHit(),
    ):
        payload = await carbon_api.get_green_schedule(user=user)
    assert payload["region"] == "global"

    cache = MagicMock()
    cache.enabled = True
    cache.get = AsyncMock(return_value={"alert_status": "cached"})
    cache.set = AsyncMock()
    with patch("app.modules.reporting.api.v1.carbon.get_cache_service", return_value=cache):
        response = await get_carbon_budget(user, AsyncMock(), provider="aws")
    assert response["alert_status"] == "cached"


@pytest.mark.asyncio
@patch(
    "app.modules.reporting.api.v1.carbon._fetch_provider_cost_data",
    new_callable=AsyncMock,
)
@patch(
    "app.modules.reporting.api.v1.carbon._get_provider_connection",
    new_callable=AsyncMock,
)
@patch("app.modules.reporting.api.v1.carbon.CarbonCalculator")
@patch("app.modules.reporting.api.v1.carbon.CarbonBudgetService")
async def test_get_carbon_budget_sends_alert_when_warning(
    mock_budget_service_class,
    mock_calculator_class,
    mock_get_connection,
    mock_fetch_cost_data,
):
    user = MagicMock()
    user.tenant_id = "tenant-123"
    db = AsyncMock()
    mock_get_connection.return_value = MagicMock()
    mock_fetch_cost_data.return_value = [{"service": "Amazon EC2", "cost_usd": 10.0}]
    settings_result = MagicMock()
    settings_result.scalar_one_or_none.return_value = None
    db.execute.return_value = settings_result
    mock_calculator_class.return_value.calculate_from_costs.return_value = {"total_co2_kg": 1.0}

    mock_budget_service = mock_budget_service_class.return_value
    mock_budget_service.get_budget_status = AsyncMock(return_value={"alert_status": "warning"})
    mock_budget_service.send_carbon_alert = AsyncMock()

    response = await get_carbon_budget(user, db, provider="aws")
    assert response["alert_status"] == "warning"
    mock_budget_service.send_carbon_alert.assert_awaited_once()


@pytest.mark.asyncio
async def test_analyze_graviton_cache_and_no_connection_branches() -> None:
    user = MagicMock()
    user.tenant_id = "tenant-123"

    cache = MagicMock()
    cache.enabled = True
    cache.get = AsyncMock(return_value={"cached": True})
    cache.set = AsyncMock()
    with patch("app.modules.reporting.api.v1.carbon.get_cache_service", return_value=cache):
        cached = await analyze_graviton_opportunities(user, AsyncMock())
    assert cached["cached"] is True

    cache.get = AsyncMock(return_value=None)
    db = AsyncMock()
    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result
    with patch("app.modules.reporting.api.v1.carbon.get_cache_service", return_value=cache):
        payload = await analyze_graviton_opportunities(user, db)
    assert payload["migration_candidates"] == 0


@pytest.mark.asyncio
@patch("app.modules.reporting.api.v1.carbon.CarbonAwareScheduler")
async def test_intensity_and_schedule_cached_and_runtime_paths(mock_scheduler_class):
    cache = MagicMock()
    cache.enabled = True
    cache.get = AsyncMock(side_effect=[{"cached": "intensity"}, None, None])
    cache.set = AsyncMock()

    with patch("app.modules.reporting.api.v1.carbon.get_cache_service", return_value=cache):
        cached = await get_carbon_intensity_forecast(MagicMock(), MagicMock(), "global", 24)
        assert cached["cached"] == "intensity"

        scheduler = mock_scheduler_class.return_value
        scheduler.get_optimal_execution_time = AsyncMock(
            return_value=datetime(2026, 2, 25, 13, 0, tzinfo=timezone.utc)
        )
        schedule = await carbon_api.get_green_schedule(
            user=MagicMock(),
            region="global",
            duration_hours=1,
        )
        assert "Defer to 13:00 UTC" in schedule["recommendation"]

        scheduler.get_optimal_execution_time = AsyncMock(return_value=None)
        schedule_now = await carbon_api.get_green_schedule(
            user=MagicMock(),
            region="global",
            duration_hours=1,
        )
        assert schedule_now["recommendation"] == "Execute now"


@pytest.mark.asyncio
async def test_carbon_factor_endpoints_branches() -> None:
    db = AsyncMock()
    user = MagicMock()

    class _ScalarResult:
        def __init__(self, rows):
            self._rows = rows

        def scalars(self):
            return self

        def all(self):
            return self._rows

    factor_item = carbon_api.CarbonFactorSetItem(
        id=str(uuid.uuid4()),
        status="active",
        is_active=True,
        factor_source="unit_test",
        factor_version="v1",
        factor_timestamp=datetime(2026, 2, 1, tzinfo=timezone.utc).isoformat(),
        methodology_version="focus-1.3",
        factors_checksum_sha256="abc",
        created_at=datetime(2026, 2, 1, tzinfo=timezone.utc).isoformat(),
        activated_at=None,
    )
    log_item = carbon_api.CarbonFactorUpdateLogItem(
        id=str(uuid.uuid4()),
        recorded_at=datetime(2026, 2, 1, tzinfo=timezone.utc).isoformat(),
        action="staged",
        message=None,
        old_factor_set_id=None,
        new_factor_set_id=None,
        old_checksum_sha256=None,
        new_checksum_sha256=None,
        details={},
    )

    with (
        patch("app.modules.reporting.api.v1.carbon._factor_set_to_item", return_value=factor_item),
        patch("app.modules.reporting.api.v1.carbon._update_log_to_item", return_value=log_item),
    ):
        service = MagicMock()
        service.ensure_active = AsyncMock(return_value=MagicMock())
        service.stage = AsyncMock(return_value=MagicMock())
        service.activate = AsyncMock(return_value=MagicMock())
        service.auto_activate_latest = AsyncMock(return_value={"status": "ok"})
        with patch("app.modules.reporting.api.v1.carbon.CarbonFactorService", return_value=service):
            db.execute.return_value = _ScalarResult([MagicMock(), MagicMock()])
            active = await carbon_api.get_active_carbon_factor_set(user=user, db=db)
            listed = await carbon_api.list_carbon_factor_sets(user=user, db=db, limit=2)
            logs = await carbon_api.list_carbon_factor_update_logs(user=user, db=db, limit=2)
            staged = await carbon_api.stage_carbon_factor_set(
                request=carbon_api.CarbonFactorStageRequest(payload={"foo": "bar"}, message="stage"),
                user=user,
                db=db,
            )
            assert active.id == factor_item.id
            assert listed.total == 2
            assert logs.total == 2
            assert staged.id == factor_item.id

            db.scalar.return_value = None
            with pytest.raises(HTTPException):
                await carbon_api.activate_carbon_factor_set(
                    factor_set_id=uuid.uuid4(),
                    user=user,
                    db=db,
                )

            db.scalar.return_value = MagicMock()
            activated = await carbon_api.activate_carbon_factor_set(
                factor_set_id=uuid.uuid4(),
                user=user,
                db=db,
            )
            auto_result = await carbon_api.auto_activate_latest_carbon_factors(user=user, db=db)
            assert activated.id == factor_item.id
            assert auto_result["status"] == "ok"
