from __future__ import annotations

import pytest

import scripts.run_disaster_recovery_drill as run_disaster_recovery_drill


@pytest.mark.asyncio
async def test_request_json_returns_parsed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"status": "ok"}

    class Client:
        async def request(self, method, url, headers=None, json=None):
            return Response()

    status, payload = await run_disaster_recovery_drill._request_json(
        Client(), "GET", "http://127.0.0.1:8000/health/live"
    )

    assert status == 200
    assert payload == {"status": "ok"}


@pytest.mark.asyncio
async def test_request_json_falls_back_to_text(monkeypatch: pytest.MonkeyPatch) -> None:
    class Response:
        status_code = 503
        text = "service unavailable"

        @staticmethod
        def json():
            raise ValueError("not json")

    class Client:
        async def request(self, method, url, headers=None, json=None):
            return Response()

    status, payload = await run_disaster_recovery_drill._request_json(
        Client(), "GET", "http://127.0.0.1:8000/health"
    )

    assert status == 503
    assert payload == "service unavailable"

