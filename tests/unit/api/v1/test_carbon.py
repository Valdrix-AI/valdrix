import pytest
from datetime import date, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi import HTTPException
from app.modules.reporting.api.v1.carbon import (
    get_carbon_footprint,
    get_carbon_budget,
    analyze_graviton_opportunities,
    get_carbon_intensity_forecast,
)


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
