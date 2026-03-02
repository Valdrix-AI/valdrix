from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.modules.notifications.domain.jira import (
    JiraService,
    get_jira_service,
    get_tenant_jira_service,
)


def _async_client_cm(client: AsyncMock) -> AsyncMock:
    cm = AsyncMock()
    cm.__aenter__.return_value = client
    cm.__aexit__.return_value = None
    return cm


def test_sanitize_label_handles_empty_and_truncation() -> None:
    assert JiraService._sanitize_label(" Prod Team / Alerts ") == "prod-team-alerts"
    assert JiraService._sanitize_label("$$$") == "valdrics"
    assert len(JiraService._sanitize_label("a" * 100)) == 64


@pytest.mark.asyncio
async def test_create_issue_success_and_payload_shape() -> None:
    service = JiraService(
        base_url="https://example.atlassian.net/",
        email="jira@example.com",
        api_token="token",
        project_key="FINOPS",
    )
    response = MagicMock(status_code=201, text="ok")
    client = AsyncMock()
    client.post = AsyncMock(return_value=response)

    with patch("app.shared.core.http.get_http_client", return_value=client):
        ok = await service.create_issue(
            summary="x" * 260,
            description="desc",
            labels=["Team Ops", "Prod/Blue"],
        )

    assert ok is True
    payload = client.post.await_args.kwargs["json"]
    assert payload["fields"]["summary"] == "x" * 240
    assert payload["fields"]["labels"] == ["team-ops", "prod-blue"]


@pytest.mark.asyncio
async def test_create_issue_failure_status_and_exception() -> None:
    service = JiraService(
        base_url="https://example.atlassian.net",
        email="jira@example.com",
        api_token="token",
        project_key="FINOPS",
    )

    bad_response = MagicMock(status_code=400, text="bad request")
    client = AsyncMock()
    client.post = AsyncMock(return_value=bad_response)
    with patch("app.shared.core.http.get_http_client", return_value=client):
        assert await service.create_issue("s", "d") is False

    client = AsyncMock()
    client.post = AsyncMock(side_effect=RuntimeError("jira down"))
    with patch("app.shared.core.http.get_http_client", return_value=client):
        assert await service.create_issue("s", "d") is False


@pytest.mark.asyncio
async def test_create_policy_issue_delegates_to_create_issue() -> None:
    service = JiraService(
        base_url="https://example.atlassian.net",
        email="jira@example.com",
        api_token="token",
        project_key="FINOPS",
    )
    with patch.object(
        service, "create_issue", new=AsyncMock(return_value=True)
    ) as create_issue:
        ok = await service.create_policy_issue(
            tenant_id=str(uuid4()),
            decision="block",
            policy_summary="blocked by guardrail",
            resource_id="prod-db",
            action="delete rds",
            severity="high",
        )

    assert ok is True
    kwargs = create_issue.await_args.kwargs
    assert "BLOCK" in kwargs["summary"]
    assert "policy event" in kwargs["description"].lower()
    assert "high" in kwargs["labels"]


@pytest.mark.asyncio
async def test_create_cost_anomaly_issue_delegates_to_create_issue() -> None:
    service = JiraService(
        base_url="https://example.atlassian.net",
        email="jira@example.com",
        api_token="token",
        project_key="FINOPS",
    )
    settings = SimpleNamespace(
        WORKFLOW_EVIDENCE_BASE_URL=None,
        API_URL="http://127.0.0.1:8000",
        FRONTEND_URL="http://127.0.0.1:3000",
    )
    with patch("app.shared.core.config.get_settings", return_value=settings):
        with patch.object(
            service, "create_issue", new=AsyncMock(return_value=True)
        ) as create_issue:
            ok = await service.create_cost_anomaly_issue(
                tenant_id=str(uuid4()),
                day="2026-02-14",
                provider="aws",
                account_id=str(uuid4()),
                account_name="Prod AWS",
                service="AmazonEC2",
                kind="spike",
                severity="high",
                actual_cost_usd=350.0,
                expected_cost_usd=100.0,
                delta_cost_usd=250.0,
                percent_change=250.0,
                confidence=0.92,
                probable_cause="spend_spike",
            )

    assert ok is True
    kwargs = create_issue.await_args.kwargs
    assert "COST ANOMALY" in kwargs["summary"].upper()
    assert "evidence" in kwargs["description"].lower()
    assert "cost-anomaly" in kwargs["labels"]


def test_get_jira_service_complete_and_incomplete() -> None:
    incomplete = SimpleNamespace(
        SAAS_STRICT_INTEGRATIONS=False,
        JIRA_BASE_URL=None,
        JIRA_EMAIL="jira@example.com",
        JIRA_API_TOKEN="token",
        JIRA_PROJECT_KEY="FINOPS",
        JIRA_ISSUE_TYPE="Task",
        JIRA_TIMEOUT_SECONDS=5.0,
    )
    with patch("app.shared.core.config.get_settings", return_value=incomplete):
        assert get_jira_service() is None

    complete = SimpleNamespace(
        SAAS_STRICT_INTEGRATIONS=False,
        JIRA_BASE_URL="https://example.atlassian.net",
        JIRA_EMAIL="jira@example.com",
        JIRA_API_TOKEN="token",
        JIRA_PROJECT_KEY="FINOPS",
        JIRA_ISSUE_TYPE="Incident",
        JIRA_TIMEOUT_SECONDS=7.0,
    )
    with patch("app.shared.core.config.get_settings", return_value=complete):
        service = get_jira_service()
    assert isinstance(service, JiraService)
    assert service is not None and service.issue_type == "Incident"


def test_get_jira_service_returns_none_in_strict_mode() -> None:
    strict = SimpleNamespace(
        SAAS_STRICT_INTEGRATIONS=True,
        JIRA_BASE_URL="https://example.atlassian.net",
        JIRA_EMAIL="jira@example.com",
        JIRA_API_TOKEN="token",
        JIRA_PROJECT_KEY="FINOPS",
        JIRA_ISSUE_TYPE="Task",
        JIRA_TIMEOUT_SECONDS=5.0,
    )
    with patch("app.shared.core.config.get_settings", return_value=strict):
        assert get_jira_service() is None


@pytest.mark.asyncio
async def test_get_tenant_jira_service_guard_paths() -> None:
    db = MagicMock()
    db.execute = AsyncMock()

    assert await get_tenant_jira_service(db, "not-a-uuid") is None

    result = MagicMock()
    result.scalar_one_or_none.return_value = None
    db.execute.return_value = result
    assert await get_tenant_jira_service(db, uuid4()) is None

    notif_disabled = SimpleNamespace(jira_enabled=False)
    result.scalar_one_or_none.return_value = notif_disabled
    assert await get_tenant_jira_service(db, uuid4()) is None

    notif_incomplete = SimpleNamespace(
        jira_enabled=True,
        jira_base_url="https://example.atlassian.net",
        jira_email=None,
        jira_project_key="FINOPS",
        jira_issue_type="Task",
        jira_api_token="token",
    )
    result.scalar_one_or_none.return_value = notif_incomplete
    assert await get_tenant_jira_service(db, uuid4()) is None


@pytest.mark.asyncio
async def test_get_tenant_jira_service_success() -> None:
    db = MagicMock()
    notif = SimpleNamespace(
        jira_enabled=True,
        jira_base_url="https://example.atlassian.net",
        jira_email="jira@example.com",
        jira_project_key="FINOPS",
        jira_issue_type="Task",
        jira_api_token="token-123",
    )
    result = MagicMock()
    result.scalar_one_or_none.return_value = notif
    db.execute = AsyncMock(return_value=result)

    settings = SimpleNamespace(JIRA_TIMEOUT_SECONDS=12.5)
    with patch("app.shared.core.config.get_settings", return_value=settings):
        service = await get_tenant_jira_service(db, uuid4())

    assert isinstance(service, JiraService)
    assert service is not None and service.timeout_seconds == 12.5
