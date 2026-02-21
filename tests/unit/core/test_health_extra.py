import pytest
from unittest.mock import AsyncMock, patch

from app.shared.core.health import HealthService


@pytest.mark.asyncio
async def test_check_all_formats_expected_keys():
    service = HealthService()
    health = {
        "status": "healthy",
        "timestamp": "t",
        "checks": {
            "database": {"status": "up"},
            "cache": {"status": "healthy"},
            "external_services": {"services": {"aws_sts": {"status": "healthy"}}},
            "system_resources": {"status": "healthy"},
        },
    }
    with patch.object(
        service, "comprehensive_health_check", AsyncMock(return_value=health)
    ):
        result = await service.check_all()

    assert result["database"]["status"] == "up"
    assert result["redis"]["status"] == "healthy"
    assert result["aws"]["status"] == "healthy"
    assert result["system"]["status"] == "healthy"


@pytest.mark.asyncio
async def test_handle_check_errors_wraps_exception():
    service = HealthService()

    async def fail():
        raise RuntimeError("boom")

    result = await service._handle_check_errors(fail())
    assert result["status"] == "error"
    assert "boom" in result["error"]


@pytest.mark.asyncio
async def test_check_aws_status_codes():
    service = HealthService()

    class FakeResponse:
        def __init__(self, code):
            self.status_code = code

    class FakeClient:
        def __init__(self, code):
            self._code = code

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return None

        async def get(self, _url):
            return FakeResponse(self._code)

    with patch(
        "app.shared.core.http.get_http_client", return_value=FakeClient(200)
    ):
        ok, _ = await service.check_aws()
        assert ok is True

    with patch(
        "app.shared.core.http.get_http_client", return_value=FakeClient(404)
    ):
        ok, _ = await service.check_aws()
        assert ok is True

    with patch(
        "app.shared.core.http.get_http_client", return_value=FakeClient(503)
    ):
        ok, details = await service.check_aws()
        assert ok is False
        assert "STS returned 503" in details["error"]
