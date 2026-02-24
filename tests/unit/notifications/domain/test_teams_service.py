from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.notifications.domain.teams import (
    TeamsService,
    _host_allowed,
    _is_private_or_link_local,
    _truncate,
    _validate_webhook_url,
    get_tenant_teams_service,
)


def _settings(
    *,
    allowlist: list[str] | None = None,
    require_https: bool = True,
    block_private_ips: bool = True,
    timeout: float = 10.0,
) -> SimpleNamespace:
    return SimpleNamespace(
        TEAMS_WEBHOOK_ALLOWED_DOMAINS=allowlist or ["office.com", "outlook.office.com"],
        TEAMS_WEBHOOK_REQUIRE_HTTPS=require_https,
        TEAMS_WEBHOOK_BLOCK_PRIVATE_IPS=block_private_ips,
        TEAMS_TIMEOUT_SECONDS=timeout,
    )


def test_helpers_validate_hosts_and_truncation() -> None:
    assert _is_private_or_link_local("127.0.0.1") is True
    assert _is_private_or_link_local("10.1.2.3") is True
    assert _is_private_or_link_local("8.8.8.8") is False

    allowlist = {"office.com"}
    assert _host_allowed("office.com", allowlist) is True
    assert _host_allowed("sub.office.com", allowlist) is True
    assert _host_allowed("example.com", allowlist) is False

    assert _truncate("short", 10) == "short"
    assert _truncate("x" * 30, 10).endswith("(truncated)")


def test_validate_webhook_url_rejects_unsafe_cases_and_accepts_allowlist() -> None:
    allowlist = {"office.com", "outlook.office.com"}

    with pytest.raises(ValueError):
        _validate_webhook_url(
            "http://outlook.office.com/webhook/test",
            allowlist,
            require_https=True,
            block_private_ips=True,
        )
    with pytest.raises(ValueError):
        _validate_webhook_url(
            "https://user:pass@outlook.office.com/webhook/test",
            allowlist,
            require_https=True,
            block_private_ips=True,
        )
    with pytest.raises(ValueError):
        _validate_webhook_url(
            "https://localhost/webhook/test",
            allowlist,
            require_https=True,
            block_private_ips=True,
        )
    with pytest.raises(ValueError):
        _validate_webhook_url(
            "https://169.254.1.1/webhook/test",
            allowlist,
            require_https=True,
            block_private_ips=True,
        )
    with pytest.raises(ValueError):
        _validate_webhook_url(
            "https://example.com/webhook/test",
            allowlist,
            require_https=True,
            block_private_ips=True,
        )

    _validate_webhook_url(
        "https://outlook.office.com/webhook/test",
        allowlist,
        require_https=True,
        block_private_ips=True,
    )


@pytest.mark.asyncio
async def test_health_check_success_and_failure() -> None:
    service = TeamsService(
        webhook_url="https://outlook.office.com/webhook/test", timeout_seconds=3.0
    )

    with patch(
        "app.modules.notifications.domain.teams.get_settings",
        return_value=_settings(),
    ):
        ok, status, error = await service.health_check()
    assert ok is True
    assert status == 200
    assert error is None

    with patch(
        "app.modules.notifications.domain.teams.get_settings",
        return_value=_settings(allowlist=["example.com"]),
    ):
        ok, status, error = await service.health_check()
    assert ok is False
    assert status == 400
    assert isinstance(error, str)


@pytest.mark.asyncio
async def test_send_alert_handles_invalid_webhook_non_2xx_and_exception() -> None:
    service = TeamsService(
        webhook_url="https://outlook.office.com/webhook/test", timeout_seconds=3.0
    )

    with patch(
        "app.modules.notifications.domain.teams.get_settings",
        return_value=_settings(allowlist=["example.com"]),
    ):
        assert (
            await service.send_alert(title="a", message="b", severity="warning") is False
        )

    bad_resp = SimpleNamespace(status_code=429, text="rate limited")
    client = SimpleNamespace(post=AsyncMock(return_value=bad_resp))
    with (
        patch(
            "app.modules.notifications.domain.teams.get_settings",
            return_value=_settings(),
        ),
        patch(
            "app.shared.core.http.get_http_client",
            return_value=client,
        ),
    ):
        assert (
            await service.send_alert(title="a", message="b", severity="warning") is False
        )

    client_exc = SimpleNamespace(post=AsyncMock(side_effect=RuntimeError("network")))
    with (
        patch(
            "app.modules.notifications.domain.teams.get_settings",
            return_value=_settings(),
        ),
        patch(
            "app.shared.core.http.get_http_client",
            return_value=client_exc,
        ),
    ):
        assert (
            await service.send_alert(title="a", message="b", severity="warning") is False
        )


@pytest.mark.asyncio
async def test_send_alert_builds_expected_payload_and_filters_actions() -> None:
    service = TeamsService(
        webhook_url="https://outlook.office.com/webhook/test", timeout_seconds=3.0
    )
    ok_resp = SimpleNamespace(status_code=200, text="ok")
    client = SimpleNamespace(post=AsyncMock(return_value=ok_resp))

    with (
        patch(
            "app.modules.notifications.domain.teams.get_settings",
            return_value=_settings(),
        ),
        patch(
            "app.shared.core.http.get_http_client",
            return_value=client,
        ),
    ):
        sent = await service.send_alert(
            title="T" * 400,
            message="M" * 9000,
            severity="unexpected",
            actions={"Open": "https://example.com", "": "https://ignored.com"},
        )

    assert sent is True
    client.post.assert_awaited_once()
    payload = client.post.await_args.kwargs["json"]
    assert payload["type"] == "message"
    card = payload["attachments"][0]["content"]
    title_block = card["body"][0]
    message_block = card["body"][1]
    assert len(title_block["text"]) <= 257
    assert len(message_block["text"]) <= 7001
    assert title_block["color"] == "warning"
    assert len(card["actions"]) == 1
    assert card["actions"][0]["title"] == "Open"


@pytest.mark.asyncio
async def test_notify_helpers_delegate_to_send_alert() -> None:
    service = TeamsService(
        webhook_url="https://outlook.office.com/webhook/test", timeout_seconds=3.0
    )
    with patch.object(TeamsService, "send_alert", new=AsyncMock(return_value=True)) as send:
        assert (
            await service.notify_zombies({"ec2_instances": []}, estimated_savings=1.0)
            is True
        )
        send.assert_not_awaited()

        result = await service.notify_zombies(
            {"ec2_instances": ["i-1", "i-2"], "volumes": ["vol-1"]},
            estimated_savings=42.5,
        )
        assert result is True
        kwargs = send.await_args.kwargs
        assert kwargs["title"] == "Zombie Resources Detected"
        assert "Found 3 zombie resources" in kwargs["message"]

        send.reset_mock()
        assert (
            await service.notify_budget_alert(
                current_spend=120.0, budget_limit=100.0, percent_used=120.0
            )
            is True
        )
        assert send.await_args.kwargs["severity"] == "critical"


@pytest.mark.asyncio
async def test_get_tenant_teams_service_guards_and_success() -> None:
    db = MagicMock()
    db.execute = AsyncMock()

    with patch(
        "app.modules.notifications.domain.teams.get_settings",
        return_value=_settings(timeout=9.5),
    ):
        assert await get_tenant_teams_service(db, "not-a-uuid") is None

    result_none = MagicMock()
    result_none.scalar_one_or_none.return_value = None
    db.execute.return_value = result_none
    with patch(
        "app.modules.notifications.domain.teams.get_settings",
        return_value=_settings(timeout=9.5),
    ):
        assert await get_tenant_teams_service(db, uuid4()) is None

    disabled = SimpleNamespace(teams_enabled=False, teams_webhook_url="https://x")
    result_disabled = MagicMock()
    result_disabled.scalar_one_or_none.return_value = disabled
    db.execute.return_value = result_disabled
    with patch(
        "app.modules.notifications.domain.teams.get_settings",
        return_value=_settings(timeout=9.5),
    ):
        assert await get_tenant_teams_service(db, uuid4()) is None

    no_webhook = SimpleNamespace(teams_enabled=True, teams_webhook_url=None)
    result_no_webhook = MagicMock()
    result_no_webhook.scalar_one_or_none.return_value = no_webhook
    db.execute.return_value = result_no_webhook
    with patch(
        "app.modules.notifications.domain.teams.get_settings",
        return_value=_settings(timeout=9.5),
    ):
        assert await get_tenant_teams_service(db, uuid4()) is None

    enabled = SimpleNamespace(
        teams_enabled=True, teams_webhook_url="https://outlook.office.com/webhook/test"
    )
    result_enabled = MagicMock()
    result_enabled.scalar_one_or_none.return_value = enabled
    db.execute.return_value = result_enabled
    with patch(
        "app.modules.notifications.domain.teams.get_settings",
        return_value=_settings(timeout=9.5),
    ):
        service = await get_tenant_teams_service(db, uuid4())
    assert isinstance(service, TeamsService)
    assert service is not None
    assert service.timeout_seconds == 9.5
