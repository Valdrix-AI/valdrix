from types import SimpleNamespace

import pytest

import scripts.load_test_api as load_test_api


def _args(**overrides):
    base = {
        "profile": "health",
        "provider": "",
        "start_date": "",
        "end_date": "",
        "include_deep_health": False,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_build_profile_endpoints_health_uses_liveness():
    endpoints = load_test_api._build_profile_endpoints(_args(profile="health"))
    assert endpoints == [load_test_api.LIVENESS_ENDPOINT]


def test_build_profile_endpoints_health_deep_uses_deep_health():
    endpoints = load_test_api._build_profile_endpoints(_args(profile="health_deep"))
    assert endpoints == [load_test_api.DEEP_HEALTH_ENDPOINT]


def test_build_profile_endpoints_dashboard_defaults_to_liveness():
    endpoints = load_test_api._build_profile_endpoints(_args(profile="dashboard"))
    assert endpoints[0] == load_test_api.LIVENESS_ENDPOINT
    assert load_test_api.DEEP_HEALTH_ENDPOINT not in endpoints


def test_build_profile_endpoints_enforcement_includes_control_plane_read_paths():
    endpoints = load_test_api._build_profile_endpoints(_args(profile="enforcement"))
    assert endpoints[0] == load_test_api.LIVENESS_ENDPOINT
    assert "/api/v1/enforcement/policies" in endpoints
    assert "/api/v1/enforcement/budgets" in endpoints
    assert "/api/v1/enforcement/credits" in endpoints
    assert "/api/v1/enforcement/approvals/queue?limit=50" in endpoints
    assert "/api/v1/enforcement/ledger?limit=50" in endpoints
    assert "/api/v1/enforcement/exports/parity?limit=50" in endpoints


def test_build_profile_endpoints_include_deep_health_flag():
    endpoints = load_test_api._build_profile_endpoints(
        _args(profile="dashboard", include_deep_health=True)
    )
    assert endpoints[0] == load_test_api.DEEP_HEALTH_ENDPOINT
    assert load_test_api.LIVENESS_ENDPOINT in endpoints


@pytest.mark.asyncio
async def test_run_preflight_checks_success(monkeypatch):
    captured_headers: dict[str, str] = {}

    class DummyResponse:
        status_code = 200
        text = "ok"

    class SuccessfulClient:
        def __init__(self, *args, **kwargs):
            nonlocal captured_headers
            captured_headers = dict(kwargs.get("headers") or {})

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url):
            return DummyResponse()

    monkeypatch.setattr(load_test_api.httpx, "AsyncClient", SuccessfulClient)

    result = await load_test_api._run_preflight_checks(
        target_url="http://127.0.0.1:8000",
        endpoints=["/health/live"],
        headers={"Authorization": "Bearer abc"},
        timeout_seconds=2.0,
        attempts=2,
    )

    assert result["passed"] is True
    assert result["failures"] == []
    assert captured_headers.get("Authorization") == "Bearer abc"


@pytest.mark.asyncio
async def test_run_preflight_checks_failure_with_retry(monkeypatch):
    call_count = 0

    class DummyResponse:
        status_code = 500
        text = "boom"

    class FailingClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, url):
            nonlocal call_count
            call_count += 1
            return DummyResponse()

    monkeypatch.setattr(load_test_api.httpx, "AsyncClient", lambda *a, **k: FailingClient())

    result = await load_test_api._run_preflight_checks(
        target_url="http://127.0.0.1:8000",
        endpoints=["/health/live"],
        headers={},
        timeout_seconds=2.0,
        attempts=2,
    )

    assert result["passed"] is False
    assert len(result["failures"]) == 1
    assert "HTTP 500" in result["failures"][0]["error"]
    assert call_count == 2
