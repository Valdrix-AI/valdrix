from __future__ import annotations

import pytest

import scripts.bootstrap_performance_tenant as bootstrap_performance_tenant


@pytest.mark.asyncio
async def test_onboard_tenant_accepts_success(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 200
        text = "ok"

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, headers, json):
            assert headers["Authorization"] == "Bearer token-123"
            assert json["tenant_name"] == "Perf Tenant"
            return Response()

    monkeypatch.setattr(bootstrap_performance_tenant.httpx, "AsyncClient", Client)

    await bootstrap_performance_tenant._onboard_tenant(
        base_url="http://127.0.0.1:8000",
        token="token-123",
        tenant_name="Perf Tenant",
        email="owner@example.com",
    )


@pytest.mark.asyncio
async def test_onboard_tenant_accepts_already_onboarded(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 400
        text = "Already onboarded"

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, headers, json):
            return Response()

    monkeypatch.setattr(bootstrap_performance_tenant.httpx, "AsyncClient", Client)

    await bootstrap_performance_tenant._onboard_tenant(
        base_url="http://127.0.0.1:8000",
        token="token-123",
        tenant_name="Perf Tenant",
        email="owner@example.com",
    )


@pytest.mark.asyncio
async def test_onboard_tenant_raises_on_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 503
        text = "upstream failure"

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def post(self, url, headers, json):
            return Response()

    monkeypatch.setattr(bootstrap_performance_tenant.httpx, "AsyncClient", Client)

    with pytest.raises(SystemExit, match="Tenant bootstrap failed \\(503\\)"):
        await bootstrap_performance_tenant._onboard_tenant(
            base_url="http://127.0.0.1:8000",
            token="token-123",
            tenant_name="Perf Tenant",
            email="owner@example.com",
        )

