import asyncio

import pytest
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import Response

from app.shared.core.timeout import TimeoutMiddleware


@pytest.mark.asyncio
async def test_timeout_middleware_returns_504_on_timeout():
    app = FastAPI()
    middleware = TimeoutMiddleware(app, timeout_seconds=0.001)

    async def call_next(_request: Request) -> Response:
        await asyncio.sleep(0.01)
        return Response("ok")

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/slow",
        "headers": [],
        "query_string": b"",
        "client": ("127.0.0.1", 12345),
        "scheme": "http",
        "server": ("testserver", 80),
    }
    request = Request(scope)
    response = await middleware.dispatch(request, call_next)

    assert response.status_code == 504
