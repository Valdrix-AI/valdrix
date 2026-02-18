import json
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock

from app.main import app as valdrix_app
from app.main import (
    valdrix_exception_handler,
    http_exception_handler,
    csrf_protect_exception_handler,
    validation_exception_handler,
    value_error_handler,
    generic_exception_handler,
    custom_rate_limit_handler,
    _load_emissions_tracker,
)
from app.main import settings
from app.shared.core.exceptions import ValdrixException
from app.shared.db.session import get_db
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi_csrf_protect.exceptions import CsrfProtectError
from slowapi.errors import RateLimitExceeded
from starlette.requests import Request
from types import ModuleType
from typing import AsyncGenerator


@pytest_asyncio.fixture
async def lite_client() -> AsyncGenerator[AsyncClient, None]:
    """Async client without real DB setup (avoids aiosqlite thread usage)."""
    settings.TESTING = True

    async def override_get_db():
        yield MagicMock()

    valdrix_app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=valdrix_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
    valdrix_app.dependency_overrides.pop(get_db, None)


@pytest.mark.asyncio
async def test_root_endpoint(lite_client: AsyncClient):
    """Test root endpoint returns status ok."""
    response = await lite_client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


@pytest.mark.asyncio
async def test_health_live(lite_client: AsyncClient):
    """Test Liveness probe."""
    response = await lite_client.get("/health/live")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_health_detailed(lite_client: AsyncClient):
    """Test full health check endpoint."""
    with patch("app.shared.core.health.HealthService.check_all") as mock_check:
        mock_check.return_value = {
            "status": "healthy",
            "database": {"status": "up"},
            "redis": {"status": "up"},
            "aws": {"status": "up"},
        }
        response = await lite_client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_not_found(lite_client: AsyncClient):
    """Test 404 handler."""
    response = await lite_client.get("/api/v1/nonexistent")
    assert response.status_code == 404


def _make_request(path: str = "/boom", method: str = "GET") -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": [],
        "query_string": b"",
        "server": ("test", 80),
        "client": ("testclient", 1234),
        "scheme": "http",
    }
    return Request(scope)


def _make_request_with_headers(
    path: str, method: str, headers: list[tuple[bytes, bytes]]
) -> Request:
    scope = {
        "type": "http",
        "method": method,
        "path": path,
        "headers": headers,
        "query_string": b"",
        "server": ("test", 80),
        "client": ("testclient", 1234),
        "scheme": "http",
    }
    return Request(scope)


@pytest.mark.asyncio
async def test_valdrix_exception_handler_records_metrics():
    request = _make_request(path="/fail", method="POST")
    exc = ValdrixException("boom", code="oops", status_code=418, details={"x": 1})

    with patch("app.main.API_ERRORS_TOTAL") as mock_metric:
        response = await valdrix_exception_handler(request, exc)
        mock_metric.labels.assert_called_once_with(
            path="/fail", method="POST", status_code=418
        )
        mock_metric.labels.return_value.inc.assert_called_once()

        assert response.status_code == 418
        from typing import cast
        body = json.loads(cast(bytes, response.body))
        assert body["code"] == "oops"


@pytest.mark.asyncio
async def test_http_exception_handler_records_metrics():
    request = _make_request(path="/missing", method="GET")
    exc = HTTPException(status_code=404, detail="Not Found")

    with patch("app.main.API_ERRORS_TOTAL") as mock_metric:
        response = await http_exception_handler(request, exc)
        mock_metric.labels.assert_called_once_with(
            path="/missing", method="GET", status_code=404
        )
        mock_metric.labels.return_value.inc.assert_called_once()

        assert response.status_code == 404
        from typing import cast
        body = json.loads(cast(bytes, response.body))
        assert body["code"] == "HTTP_ERROR"


@pytest.mark.asyncio
async def test_csrf_exception_handler_records_metrics():
    request = _make_request(path="/csrf", method="PUT")
    exc = CsrfProtectError(403, "csrf blocked")

    with (
        patch("app.main.CSRF_ERRORS") as mock_csrf,
        patch("app.main.API_ERRORS_TOTAL") as mock_api,
    ):
        response = await csrf_protect_exception_handler(request, exc)
        mock_csrf.labels.assert_called_once_with(path="/csrf", method="PUT")
        mock_csrf.labels.return_value.inc.assert_called_once()
        mock_api.labels.assert_called_once_with(
            path="/csrf", method="PUT", status_code=403
        )
        mock_api.labels.return_value.inc.assert_called_once()

        assert response.status_code == 403
        from typing import cast
        body = json.loads(cast(bytes, response.body))
        assert body["code"] == "csrf_error"


@pytest.mark.asyncio
async def test_csrf_middleware_skips_bearer_token_requests():
    """
    Bearer-token authenticated API calls should not require CSRF cookies/headers.
    CSRF is only meaningful for cookie/session-auth flows.
    """
    from starlette.responses import Response
    from app.main import csrf_protect_middleware

    request = _make_request_with_headers(
        path="/api/v1/settings/notifications",
        method="PUT",
        headers=[(b"authorization", b"Bearer test-token")],
    )

    async def call_next(_request: Request) -> Response:
        return Response("ok", status_code=200)

    original_testing = settings.TESTING
    settings.TESTING = False
    try:
        # If CSRF runs here, it will attempt to validate and fail (no cookies).
        # We want the bearer header to short-circuit CSRF entirely.
        with patch(
            "app.main.CsrfProtect", side_effect=AssertionError("CSRF should be skipped")
        ):
            response = await csrf_protect_middleware(request, call_next)
        assert response.status_code == 200
    finally:
        settings.TESTING = original_testing


@pytest.mark.asyncio
async def test_csrf_middleware_skips_when_no_cookie_header_present():
    """
    CSRF is only meaningful for cookie-based auth flows.
    If no Cookie header is present, CSRF validation should not run.
    """
    from starlette.responses import Response
    from app.main import csrf_protect_middleware

    request = _make_request_with_headers(
        path="/api/v1/settings/notifications",
        method="PUT",
        headers=[],
    )

    async def call_next(_request: Request) -> Response:
        return Response("ok", status_code=200)

    original_testing = settings.TESTING
    settings.TESTING = False
    try:
        with patch(
            "app.main.CsrfProtect", side_effect=AssertionError("CSRF should be skipped")
        ):
            response = await csrf_protect_middleware(request, call_next)
        assert response.status_code == 200
    finally:
        settings.TESTING = original_testing


@pytest.mark.asyncio
async def test_csrf_middleware_enforces_when_cookie_present_and_no_bearer():
    """
    If cookies are present (cookie-auth flow) and there's no bearer auth,
    CSRF validation should run and block requests missing tokens.
    """
    from app.main import csrf_protect_middleware

    request = _make_request_with_headers(
        path="/api/v1/settings/notifications",
        method="PUT",
        headers=[(b"cookie", b"session=fake; fastapi-csrf-token=fake")],
    )

    async def call_next(_request: Request):  # pragma: no cover
        raise AssertionError("call_next should not be reached if CSRF blocks")

    class _FakeCsrf:
        async def validate_csrf(self, _request: Request) -> None:
            raise CsrfProtectError(400, "Missing csrf header")

    import app.main as main_mod

    original_testing = main_mod.settings.TESTING
    main_mod.settings.TESTING = False
    try:
        with patch("app.main.CsrfProtect", return_value=_FakeCsrf()):
            response = await csrf_protect_middleware(request, call_next)
        assert response.status_code == 400
        from typing import cast
        body = json.loads(cast(bytes, response.body))
        assert body["code"] == "csrf_error"
    finally:
        main_mod.settings.TESTING = original_testing


@pytest.mark.asyncio
async def test_validation_exception_handler_records_metrics():
    request = _make_request(path="/validate", method="POST")
    exc = RequestValidationError(
        [{"loc": ("body", "x"), "msg": "bad", "type": "value_error"}]
    )

    with patch("app.main.API_ERRORS_TOTAL") as mock_metric:
        response = await validation_exception_handler(request, exc)
        mock_metric.labels.assert_called_once_with(
            path="/validate", method="POST", status_code=422
        )
        mock_metric.labels.return_value.inc.assert_called_once()
        assert response.status_code == 422


@pytest.mark.asyncio
async def test_value_error_handler_records_metrics():
    request = _make_request(path="/value", method="PUT")
    exc = ValueError("boom")

    with patch("app.shared.core.error_governance.API_ERRORS_TOTAL") as mock_metric:
        response = await value_error_handler(request, exc)
        mock_metric.labels.assert_called_once_with(
            path="/value", method="PUT", status_code=400
        )
        mock_metric.labels.return_value.inc.assert_called_once()
        assert response.status_code == 400


@pytest.mark.asyncio
async def test_generic_exception_handler_records_metrics():
    request = _make_request(path="/generic", method="GET")
    exc = RuntimeError("explode")

    with patch("app.shared.core.error_governance.API_ERRORS_TOTAL") as mock_metric:
        response = await generic_exception_handler(request, exc)
        mock_metric.labels.assert_called_once_with(
            path="/generic", method="GET", status_code=500
        )
        mock_metric.labels.return_value.inc.assert_called_once()
        assert response.status_code == 500


@pytest.mark.asyncio
async def test_rate_limit_handler_records_metrics():
    request = _make_request(path="/rate", method="GET")
    limit = MagicMock()
    limit.error_message = None
    limit.limit = "1/minute"
    exc = RateLimitExceeded(limit)

    def fake_handler(_request, _exc):
        from starlette.responses import JSONResponse

        return JSONResponse(status_code=429, content={"detail": "rate limit"})

    with (
        patch("app.main.original_handler", new=fake_handler),
        patch("app.main.RATE_LIMIT_EXCEEDED") as mock_rate,
        patch("app.main.API_ERRORS_TOTAL") as mock_api,
    ):
        response = await custom_rate_limit_handler(request, exc)
        mock_rate.labels.assert_called_once_with(
            path="/rate", method="GET", tier="unknown"
        )
        mock_rate.labels.return_value.inc.assert_called_once()
        mock_api.labels.assert_called_once_with(
            path="/rate", method="GET", status_code=429
        )
        mock_api.labels.return_value.inc.assert_called_once()
        assert response.status_code == 429


@pytest.mark.asyncio
async def test_validation_exception_handler_sanitizes_non_serializable_values():
    request = _make_request(path="/validate", method="POST")
    exc = RequestValidationError(
        [
            {
                "loc": ("body", "x"),
                "msg": "bad",
                "type": "value_error",
                "ctx": {"error": ValueError("nope")},
                "input": object(),
            }
        ]
    )

    response = await validation_exception_handler(request, exc)
    assert response.status_code == 422
    from typing import cast
    body = json.loads(cast(bytes, response.body))
    details = body["details"][0]
    assert isinstance(details["ctx"]["error"], str)
    assert "nope" in details["ctx"]["error"]
    assert isinstance(details["input"], str)


def test_load_emissions_tracker_skips_in_test_mode():
    old = settings.TESTING
    settings.TESTING = True
    try:
        assert _load_emissions_tracker() is None
    finally:
        settings.TESTING = old


def test_load_emissions_tracker_imports_codecarbon_when_available():
    module = ModuleType("codecarbon")

    class DummyTracker:  # pragma: no cover - simple sentinel
        pass

    setattr(module, "EmissionsTracker", DummyTracker)
    with (
        patch("app.main._is_test_mode", return_value=False),
        patch.dict("sys.modules", {"codecarbon": module}),
    ):
        tracker = _load_emissions_tracker()
    assert tracker is DummyTracker
