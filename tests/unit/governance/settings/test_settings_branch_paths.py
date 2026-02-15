from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.modules.governance.api.v1.settings import activeops, carbon, llm, notifications
from app.shared.core.auth import CurrentUser
from app.shared.core.pricing import PricingTier


def _scalar_result(value: object) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


@pytest.fixture
def user() -> CurrentUser:
    return CurrentUser(
        id=uuid4(),
        email="admin@example.com",
        tenant_id=uuid4(),
        tier=PricingTier.ENTERPRISE,
    )


@pytest.fixture
def db() -> MagicMock:
    mock_db = MagicMock()
    mock_db.execute = AsyncMock()
    mock_db.commit = AsyncMock()

    async def _refresh(obj: object, *args: object, **kwargs: object) -> None:
        # Emulate DB-side/default-populated fields for object-only unit tests.
        if hasattr(obj, "email_enabled") and getattr(obj, "email_enabled") is None:
            setattr(obj, "email_enabled", False)
        if hasattr(obj, "hard_limit") and getattr(obj, "hard_limit") is None:
            setattr(obj, "hard_limit", False)

    mock_db.refresh = AsyncMock(side_effect=_refresh)
    mock_db.add = MagicMock()
    return mock_db


@pytest.mark.asyncio
async def test_activeops_get_creates_default_when_missing(
    user: CurrentUser, db: MagicMock
) -> None:
    db.execute.return_value = _scalar_result(None)
    response = await activeops.get_activeops_settings(user, db)
    assert response.auto_pilot_enabled is False
    assert response.min_confidence_threshold == 0.95
    db.add.assert_called_once()


@pytest.mark.asyncio
async def test_activeops_update_branches(user: CurrentUser, db: MagicMock) -> None:
    existing = SimpleNamespace(auto_pilot_enabled=False, min_confidence_threshold=0.95)
    db.execute.return_value = _scalar_result(existing)

    update = activeops.ActiveOpsSettingsUpdate(
        auto_pilot_enabled=True, min_confidence_threshold=0.8
    )
    with patch.object(activeops, "audit_log"):
        response = await activeops.update_activeops_settings(update, user, db)

    assert response.auto_pilot_enabled is True
    assert response.min_confidence_threshold == 0.8

    db.execute.return_value = _scalar_result(None)
    with patch.object(activeops, "audit_log"):
        created = await activeops.update_activeops_settings(update, user, db)
    assert created.auto_pilot_enabled is True
    assert db.add.called


def test_carbon_update_validates_email_dependencies() -> None:
    with pytest.raises(ValidationError):
        carbon.CarbonSettingsUpdate(email_enabled=True, email_recipients=None)

    normalized = carbon.CarbonSettingsUpdate(
        email_enabled=True,
        email_recipients=" alice@example.com, bob@example.com ",
    )
    assert normalized.email_recipients == "alice@example.com, bob@example.com"


@pytest.mark.asyncio
async def test_carbon_get_and_update_branches(user: CurrentUser, db: MagicMock) -> None:
    db.execute.return_value = _scalar_result(None)
    response = await carbon.get_carbon_settings(user, db)
    assert response.default_region == "us-east-1"
    db.add.assert_called_once()

    existing = SimpleNamespace(
        carbon_budget_kg=100.0,
        alert_threshold_percent=80,
        default_region="us-east-1",
        email_enabled=False,
        email_recipients=None,
    )
    db.execute.return_value = _scalar_result(existing)
    update = carbon.CarbonSettingsUpdate(
        carbon_budget_kg=250.0,
        alert_threshold_percent=70,
        default_region="eu-west-1",
        email_enabled=False,
    )
    with patch.object(carbon, "audit_log"):
        updated = await carbon.update_carbon_settings(update, user, db)
    assert updated.carbon_budget_kg == 250.0

    db.execute.return_value = _scalar_result(None)
    with patch.object(carbon, "audit_log"):
        created = await carbon.update_carbon_settings(update, user, db)
    assert created.default_region == "eu-west-1"


@pytest.mark.asyncio
async def test_notification_get_and_update_branches(
    user: CurrentUser, db: MagicMock
) -> None:
    db.execute.return_value = _scalar_result(None)
    created = await notifications.get_notification_settings(user, db)
    assert created.digest_schedule == "daily"
    db.add.assert_called_once()

    existing = SimpleNamespace(
        slack_enabled=True,
        slack_channel_override=None,
        digest_schedule="daily",
        digest_hour=9,
        digest_minute=0,
        alert_on_budget_warning=True,
        alert_on_budget_exceeded=True,
        alert_on_zombie_detected=True,
    )
    db.execute.return_value = _scalar_result(existing)
    update = notifications.NotificationSettingsUpdate(
        slack_enabled=False,
        slack_channel_override="#ops",
        digest_schedule="weekly",
        digest_hour=8,
        digest_minute=30,
        alert_on_budget_warning=False,
        alert_on_budget_exceeded=True,
        alert_on_zombie_detected=False,
    )
    with patch.object(notifications, "audit_log"):
        updated = await notifications.update_notification_settings(update, user, db)
    assert updated.slack_enabled is False
    assert updated.digest_schedule == "weekly"

    db.execute.return_value = _scalar_result(None)
    with patch.object(notifications, "audit_log"):
        created_again = await notifications.update_notification_settings(
            update, user, db
        )
    assert created_again.slack_channel_override == "#ops"


@pytest.mark.asyncio
async def test_test_slack_notification_error_and_success_paths(
    user: CurrentUser,
    db: MagicMock,
) -> None:
    with patch.object(notifications, "_record_acceptance_evidence", new=AsyncMock()):
        with patch(
            "app.modules.notifications.domain.get_tenant_slack_service",
            new=AsyncMock(return_value=None),
        ):
            with pytest.raises(HTTPException) as exc:
                await notifications.test_slack_notification(user, db)
    assert exc.value.status_code == 400

    slack = AsyncMock()
    slack.send_alert = AsyncMock(return_value=False)
    with patch.object(notifications, "_record_acceptance_evidence", new=AsyncMock()):
        with patch(
            "app.modules.notifications.domain.get_tenant_slack_service",
            new=AsyncMock(return_value=slack),
        ):
            with pytest.raises(HTTPException) as exc:
                await notifications.test_slack_notification(user, db)
    assert exc.value.status_code == 500

    slack = AsyncMock()
    slack.send_alert = AsyncMock(return_value=True)
    with patch.object(notifications, "_record_acceptance_evidence", new=AsyncMock()):
        with patch(
            "app.modules.notifications.domain.get_tenant_slack_service",
            new=AsyncMock(return_value=slack),
        ):
            ok = await notifications.test_slack_notification(user, db)
    assert ok["status"] == "success"

    slack = AsyncMock()
    slack.send_alert = AsyncMock(side_effect=RuntimeError("slack init failed"))
    with patch.object(notifications, "_record_acceptance_evidence", new=AsyncMock()):
        with patch(
            "app.modules.notifications.domain.get_tenant_slack_service",
            new=AsyncMock(return_value=slack),
        ):
            with pytest.raises(HTTPException) as exc:
                await notifications.test_slack_notification(user, db)
    assert exc.value.status_code == 500


@pytest.mark.asyncio
async def test_llm_get_update_and_models_paths(
    user: CurrentUser, db: MagicMock
) -> None:
    db.execute.return_value = _scalar_result(None)
    created = await llm.get_llm_settings(user, db)
    assert created.preferred_provider == "groq"

    existing = SimpleNamespace(
        monthly_limit_usd=10.0,
        alert_threshold_percent=80,
        hard_limit=False,
        preferred_provider="groq",
        preferred_model="llama",
        openai_api_key=None,
        claude_api_key=None,
        google_api_key=None,
        groq_api_key=None,
    )
    db.execute.return_value = _scalar_result(existing)

    update_zero = llm.LLMSettingsUpdate(
        monthly_limit_usd=20.0,
        alert_threshold_percent=0,
        hard_limit=True,
        preferred_provider="openai",
        preferred_model="gpt-4.1-mini",
    )
    with patch.object(llm, "audit_log"):
        updated_zero = await llm.update_llm_settings(update_zero, user, db)
    assert updated_zero.alert_threshold_percent == 0

    update_max = llm.LLMSettingsUpdate(
        monthly_limit_usd=20.0,
        alert_threshold_percent=100,
        hard_limit=False,
        preferred_provider="groq",
        preferred_model="llama-3.3-70b-versatile",
        groq_api_key="gsk_123",
    )
    with patch.object(llm, "audit_log"):
        updated_max = await llm.update_llm_settings(update_max, user, db)
    assert updated_max.has_groq_key is True

    db.execute.return_value = _scalar_result(None)
    with patch.object(llm, "audit_log"):
        created_again = await llm.update_llm_settings(update_max, user, db)
    assert created_again.preferred_provider == "groq"

    with patch(
        "app.shared.llm.pricing_data.LLM_PRICING",
        {"groq": {"m1": {}, "m2": {}}, "openai": {"o1": {}}},
    ):
        models = await llm.get_llm_models()
    assert models["groq"] == ["m1", "m2"]
    assert models["openai"] == ["o1"]
