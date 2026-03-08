from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient

from app.shared.core.pricing import PricingTier


@pytest.mark.asyncio
async def test_capture_notification_acceptance_evidence_success(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    admin = make_current_user(tier=PricingTier.PRO)
    slack = AsyncMock()
    slack.send_alert.return_value = True
    jira = AsyncMock()
    jira.create_issue.return_value = True
    teams = AsyncMock()
    teams.send_alert.return_value = True
    dispatcher = AsyncMock()
    dispatcher.provider = "github_actions"
    dispatcher.dispatch.return_value = True

    with (
        override_current_user(app, admin),
        patch(
            "app.modules.notifications.domain.get_tenant_slack_service",
            new=AsyncMock(return_value=slack),
        ),
        patch(
            "app.modules.notifications.domain.get_tenant_jira_service",
            new=AsyncMock(return_value=jira),
        ),
        patch(
            "app.modules.notifications.domain.get_tenant_teams_service",
            new=AsyncMock(return_value=teams),
        ),
        patch(
            "app.modules.notifications.domain.get_tenant_workflow_dispatchers",
            new=AsyncMock(return_value=[dispatcher]),
        ),
    ):
        capture = await async_client.post(
            "/api/v1/settings/notifications/acceptance-evidence/capture",
            json={},
        )
        payload = capture.json()
        run_id = payload["run_id"]
        listing = await async_client.get(
            "/api/v1/settings/notifications/acceptance-evidence",
            params={"run_id": run_id},
        )

    assert capture.status_code == 200
    assert payload["overall_status"] == "success"
    assert payload["passed"] == 4
    assert payload["failed"] == 0
    assert listing.status_code == 200
    list_payload = listing.json()
    assert list_payload["total"] == 5
    channels = {item["channel"] for item in list_payload["items"]}
    assert {"slack", "jira", "teams", "workflow", "suite"} <= channels


@pytest.mark.asyncio
async def test_capture_notification_acceptance_evidence_partial_failure_fail_fast(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    with (
        override_current_user(app, make_current_user(tier=PricingTier.PRO)),
        patch(
            "app.modules.notifications.domain.get_tenant_slack_service",
            new=AsyncMock(return_value=None),
        ),
    ):
        capture = await async_client.post(
            "/api/v1/settings/notifications/acceptance-evidence/capture",
            json={
                "include_slack": True,
                "include_jira": True,
                "include_teams": True,
                "include_workflow": True,
                "fail_fast": True,
            },
        )

    assert capture.status_code == 200
    payload = capture.json()
    assert payload["overall_status"] == "failed"
    assert payload["passed"] == 0
    assert payload["failed"] == 1
    assert len(payload["results"]) == 1
    assert payload["results"][0]["channel"] == "slack"


@pytest.mark.asyncio
async def test_list_notification_acceptance_evidence_requires_tenant(
    async_client: AsyncClient,
    app,
    make_current_user,
    override_current_user,
) -> None:
    with override_current_user(
        app,
        make_current_user(tier=PricingTier.PRO, tenant_id=None),
    ):
        response = await async_client.get(
            "/api/v1/settings/notifications/acceptance-evidence"
        )

    assert response.status_code == 403
    assert "Tenant context required" in response.json()["error"]
