import pytest
from uuid import uuid4
from decimal import Decimal
from unittest.mock import MagicMock, patch, AsyncMock
from app.shared.core.safety_service import SafetyGuardrailService
from app.shared.core.exceptions import KillSwitchTriggeredError


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    return db


@pytest.fixture
def service(mock_db):
    return SafetyGuardrailService(mock_db)


@pytest.mark.asyncio
async def test_global_kill_switch_triggered(service, mock_db):
    tenant_id = uuid4()
    # Mock settings threshold
    service._settings.REMEDIATION_KILL_SWITCH_THRESHOLD = 500.0
    service._settings.REMEDIATION_KILL_SWITCH_SCOPE = "tenant"

    # Mock DB result: already $450 saved today, impact is $60
    mock_result = MagicMock()
    mock_result.scalar.return_value = Decimal("450.0")
    mock_db.execute.return_value = mock_result

    with pytest.raises(KillSwitchTriggeredError, match="Safety kill-switch triggered"):
        await service._check_global_kill_switch(tenant_id, Decimal("60.0"))


@pytest.mark.asyncio
async def test_global_kill_switch_allowed(service, mock_db):
    tenant_id = uuid4()
    service._settings.REMEDIATION_KILL_SWITCH_THRESHOLD = 500.0
    service._settings.REMEDIATION_KILL_SWITCH_SCOPE = "tenant"

    mock_result = MagicMock()
    mock_result.scalar.return_value = Decimal("400.0")
    mock_db.execute.return_value = mock_result

    # Impact $50, total $450 < $500
    await service._check_global_kill_switch(tenant_id, Decimal("50.0"))


@pytest.mark.asyncio
async def test_global_kill_switch_invalid_scope_falls_back_to_tenant(service, mock_db):
    tenant_id = uuid4()
    service._settings.REMEDIATION_KILL_SWITCH_THRESHOLD = 500.0
    service._settings.REMEDIATION_KILL_SWITCH_SCOPE = "invalid_scope"

    mock_result = MagicMock()
    mock_result.scalar.return_value = Decimal("400.0")
    mock_db.execute.return_value = mock_result

    await service._check_global_kill_switch(tenant_id, Decimal("50.0"))
    stmt = mock_db.execute.await_args.args[0]
    where_text = str(stmt)
    assert "remediation_requests.tenant_id" in where_text


@pytest.mark.asyncio
async def test_monthly_hard_cap_triggered(service, mock_db):
    tenant_id = uuid4()

    # 1. Mock RemediationSettings
    mock_settings_obj = MagicMock()
    mock_settings_obj.hard_cap_enabled = True
    mock_settings_obj.monthly_hard_cap_usd = 1000.0

    # 2. Mock CostAggregator
    mock_summary = MagicMock()
    mock_summary.total_cost = Decimal("1100.0")

    # Mock DB results: first settings, then CostAggregator?
    # Actually CostAggregator.get_summary is matched separately.

    mock_db_res = MagicMock()
    mock_db_res.scalar_one_or_none.return_value = mock_settings_obj
    mock_db.execute.return_value = mock_db_res

    with patch(
        "app.modules.reporting.domain.aggregator.CostAggregator.get_summary",
        return_value=mock_summary,
    ):
        with patch(
            "app.shared.core.notifications.NotificationDispatcher.notify_budget_alert",
            new_callable=AsyncMock,
        ) as mock_notify:
            with pytest.raises(
                KillSwitchTriggeredError, match="Monthly budget hard-cap reached"
            ):
                await service._check_monthly_hard_cap(tenant_id)

            mock_notify.assert_awaited()


@pytest.mark.asyncio
async def test_circuit_breaker_triggered(service, mock_db):
    tenant_id = uuid4()

    # Mock 5 failures
    mock_result = MagicMock()
    mock_result.scalar.return_value = 5
    mock_db.execute.return_value = mock_result

    with pytest.raises(
        KillSwitchTriggeredError, match="Remediation circuit breaker open"
    ):
        await service._check_circuit_breaker(tenant_id)


@pytest.mark.asyncio
async def test_check_all_guards_success(service):
    tenant_id = uuid4()

    # Mock all internal checks to pass
    service._check_global_kill_switch = AsyncMock()
    service._check_monthly_hard_cap = AsyncMock()
    service._check_circuit_breaker = AsyncMock()

    await service.check_all_guards(tenant_id, Decimal("10.0"))

    service._check_global_kill_switch.assert_awaited_with(tenant_id, Decimal("10.0"))
    service._check_monthly_hard_cap.assert_awaited_with(tenant_id)
    service._check_circuit_breaker.assert_awaited_with(tenant_id)
