"""
Tests for CarbonBudgetService - Budget Alerts
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4
from datetime import date, datetime, timezone
from app.modules.reporting.domain.budget_alerts import CarbonBudgetService


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


@pytest.fixture
def carbon_service(mock_db):
    return CarbonBudgetService(mock_db)


@pytest.mark.asyncio
async def test_get_budget_status_ok(carbon_service, mock_db):
    """Test get_budget_status returns OK when under threshold."""
    tenant_id = uuid4()

    # Mock carbon settings with correct attribute names
    mock_settings = MagicMock()
    mock_settings.carbon_budget_kg = 100.0
    mock_settings.alert_threshold_percent = 80

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_settings
    mock_db.execute.return_value = mock_result

    status = await carbon_service.get_budget_status(
        tenant_id=tenant_id,
        month_start=date.today(),
        current_co2_kg=50.0,  # 50%
    )

    assert status["alert_status"] == "ok"
    assert status["usage_percent"] == 50.0


@pytest.mark.asyncio
async def test_get_budget_status_warning(carbon_service, mock_db):
    """Test get_budget_status returns WARNING at threshold."""
    tenant_id = uuid4()

    mock_settings = MagicMock()
    mock_settings.carbon_budget_kg = 100.0
    mock_settings.alert_threshold_percent = 80

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_settings
    mock_db.execute.return_value = mock_result

    status = await carbon_service.get_budget_status(
        tenant_id=tenant_id,
        month_start=date.today(),
        current_co2_kg=85.0,  # 85% > 80%
    )

    assert status["alert_status"] == "warning"


@pytest.mark.asyncio
async def test_get_budget_status_exceeded(carbon_service, mock_db):
    """Test get_budget_status returns EXCEEDED over 100%."""
    tenant_id = uuid4()

    mock_settings = MagicMock()
    mock_settings.carbon_budget_kg = 100.0
    mock_settings.alert_threshold_percent = 80

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_settings
    mock_db.execute.return_value = mock_result

    status = await carbon_service.get_budget_status(
        tenant_id=tenant_id,
        month_start=date.today(),
        current_co2_kg=110.0,  # 110%
    )

    assert status["alert_status"] == "exceeded"


@pytest.mark.asyncio
async def test_get_budget_status_no_budget(carbon_service, mock_db):
    """Test get_budget_status with no settings returns defaults."""
    tenant_id = uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    status = await carbon_service.get_budget_status(
        tenant_id=tenant_id, month_start=date.today(), current_co2_kg=50.0
    )

    # Should use default budget of 100kg
    assert status["budget_kg"] == 100.0


def test_get_recommendations_low_usage(carbon_service):
    """Test recommendations for low usage."""
    recs = carbon_service._get_recommendations(30.0, "ok")
    assert len(recs) > 0
    assert any("within budget" in r.lower() for r in recs)


def test_get_recommendations_exceeded(carbon_service):
    """Test recommendations when exceeded."""
    recs = carbon_service._get_recommendations(110.0, "exceeded")
    assert len(recs) > 0
    assert any("exceeded" in r.lower() for r in recs)


@pytest.mark.asyncio
async def test_should_send_alert_no_recent(carbon_service, mock_db):
    """Test should_send_alert returns True if no recent alert."""
    tenant_id = uuid4()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute.return_value = mock_result

    should_send = await carbon_service.should_send_alert(tenant_id, "warning")

    assert should_send is True


@pytest.mark.asyncio
async def test_should_send_alert_recent_sent(carbon_service, mock_db):
    """Test should_send_alert returns False if sent today."""
    tenant_id = uuid4()

    mock_settings = MagicMock()
    mock_settings.last_alert_sent = datetime.now(timezone.utc)  # Correct attribute
    mock_settings.last_alert_status = "warning"

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_settings
    mock_db.execute.return_value = mock_result

    should_send = await carbon_service.should_send_alert(tenant_id, "warning")

    assert should_send is False


@pytest.mark.asyncio
async def test_mark_alert_sent(carbon_service, mock_db):
    """Test mark_alert_sent calls db update."""
    tenant_id = uuid4()

    await carbon_service.mark_alert_sent(tenant_id, "warning")

    mock_db.execute.assert_called_once()
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_send_carbon_alert_rate_limited(carbon_service, mock_db):
    """Test send_carbon_alert is rate limited."""
    tenant_id = uuid4()

    with patch.object(
        carbon_service, "should_send_alert", new_callable=AsyncMock
    ) as mock_check:
        mock_check.return_value = False

        budget_status = {"alert_status": "warning", "usage_percent": 85.0}
        sent = await carbon_service.send_carbon_alert(tenant_id, budget_status)

        assert sent is False


@pytest.mark.asyncio
async def test_send_carbon_alert_slack(carbon_service, mock_db):
    """Test send_carbon_alert via Slack."""
    tenant_id = uuid4()

    with patch.object(
        carbon_service, "should_send_alert", new_callable=AsyncMock
    ) as mock_check:
        mock_check.return_value = True

        with patch.object(carbon_service, "mark_alert_sent", new_callable=AsyncMock):
            with patch("app.shared.core.config.get_settings") as mock_settings:
                mock_cfg = MagicMock()
                mock_cfg.SLACK_BOT_TOKEN = "xoxb-test"
                mock_cfg.SLACK_CHANNEL_ID = "C123"
                mock_cfg.SMTP_HOST = None
                mock_settings.return_value = mock_cfg

                # Mock DB for notification settings
                mock_notif = MagicMock()
                mock_notif.slack_enabled = True
                mock_notif.slack_channel_override = None
                mock_notif.alert_on_carbon_budget_warning = True
                mock_notif.alert_on_carbon_budget_exceeded = True

                notif_result = MagicMock()
                notif_result.scalar_one_or_none.return_value = mock_notif
                carbon_result = MagicMock()
                carbon_result.scalar_one_or_none.return_value = None
                mock_db.execute.side_effect = [notif_result, carbon_result]

                with patch(
                    "app.modules.notifications.domain.get_tenant_slack_service",
                    new_callable=AsyncMock,
                ) as mock_get_tenant_slack:
                    mock_slack = AsyncMock()
                    mock_get_tenant_slack.return_value = mock_slack

                    budget_status = {
                        "alert_status": "warning",
                        "usage_percent": 85.0,
                        "current_usage_kg": 85.0,
                        "budget_kg": 100.0,
                        "recommendations": ["Use Graviton"],
                    }

                    await carbon_service.send_carbon_alert(tenant_id, budget_status)

                    mock_slack.send_alert.assert_called_once()
