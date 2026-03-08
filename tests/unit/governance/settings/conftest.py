from __future__ import annotations

import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from typing import Any

import pytest

from app.shared.core.auth import CurrentUser, UserRole, get_current_user
from app.shared.core.pricing import PricingTier

_UNSET = object()


@pytest.fixture
def make_current_user() -> Callable[..., CurrentUser]:
    def _make(
        *,
        role: UserRole = UserRole.ADMIN,
        tier: PricingTier | None = None,
        tenant_id: uuid.UUID | None | object = _UNSET,
        user_id: uuid.UUID | object = _UNSET,
        email: str | None = None,
    ) -> CurrentUser:
        resolved_tenant_id = (
            uuid.uuid4() if tenant_id is _UNSET else tenant_id
        )
        resolved_user_id = uuid.uuid4() if user_id is _UNSET else user_id
        resolved_email = email or (
            "admin@notify.io" if role is UserRole.ADMIN else "member@notify.io"
        )

        kwargs: dict[str, Any] = {
            "id": resolved_user_id,
            "tenant_id": resolved_tenant_id,
            "email": resolved_email,
            "role": role,
        }
        if tier is not None:
            kwargs["tier"] = tier
        return CurrentUser(**kwargs)

    return _make


@pytest.fixture
def override_current_user() -> Callable[[Any, CurrentUser], Iterator[CurrentUser]]:
    @contextmanager
    def _override(app: Any, user: CurrentUser) -> Iterator[CurrentUser]:
        app.dependency_overrides[get_current_user] = lambda: user
        try:
            yield user
        finally:
            app.dependency_overrides.pop(get_current_user, None)

    return _override


@pytest.fixture
def build_notification_payload() -> Callable[..., dict[str, Any]]:
    def _build(**overrides: Any) -> dict[str, Any]:
        payload = {
            "slack_enabled": True,
            "digest_schedule": "daily",
            "digest_hour": 9,
            "digest_minute": 0,
            "alert_on_budget_warning": True,
            "alert_on_budget_exceeded": True,
            "alert_on_zombie_detected": True,
        }
        payload.update(overrides)
        return payload

    return _build


@pytest.fixture
def build_jira_payload(
    build_notification_payload: Callable[..., dict[str, Any]],
) -> Callable[..., dict[str, Any]]:
    def _build(**overrides: Any) -> dict[str, Any]:
        payload = build_notification_payload(
            jira_enabled=True,
            jira_base_url="https://example.atlassian.net",
            jira_email="jira@example.com",
            jira_project_key="FINOPS",
            jira_issue_type="Task",
            jira_api_token="jira_token_value_123",
        )
        payload.update(overrides)
        return payload

    return _build


@pytest.fixture
def build_teams_payload(
    build_notification_payload: Callable[..., dict[str, Any]],
) -> Callable[..., dict[str, Any]]:
    def _build(**overrides: Any) -> dict[str, Any]:
        payload = build_notification_payload(
            teams_enabled=True,
            teams_webhook_url="https://example.webhook.office.com/webhookb2/xxxx",
        )
        payload.update(overrides)
        return payload

    return _build


@pytest.fixture
def build_workflow_payload(
    build_notification_payload: Callable[..., dict[str, Any]],
) -> Callable[..., dict[str, Any]]:
    def _build(**overrides: Any) -> dict[str, Any]:
        payload = build_notification_payload(
            jira_enabled=False,
            workflow_github_enabled=True,
            workflow_github_owner="Valdrics-AI",
            workflow_github_repo="valdrics",
            workflow_github_workflow_id="remediation.yml",
            workflow_github_ref="main",
            workflow_github_token="gh_token_value_123",
            workflow_gitlab_enabled=True,
            workflow_gitlab_base_url="https://gitlab.com",
            workflow_gitlab_project_id="12345",
            workflow_gitlab_ref="main",
            workflow_gitlab_trigger_token="gl_token_value_123",
            workflow_webhook_enabled=True,
            workflow_webhook_url="https://ci.example.com/hooks/valdrics",
            workflow_webhook_bearer_token="webhook_token_value_123",
        )
        payload.update(overrides)
        return payload

    return _build
