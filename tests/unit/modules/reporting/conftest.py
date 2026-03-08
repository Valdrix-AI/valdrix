from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.models.hybrid_connection import HybridConnection
from app.models.license_connection import LicenseConnection
from app.models.platform_connection import PlatformConnection
from app.models.saas_connection import SaaSConnection


def _build_connection(model: type[Any], *, provider: str, name: str) -> MagicMock:
    connection = MagicMock(spec=model)
    connection.id = str(uuid.uuid4())
    connection.tenant_id = str(uuid.uuid4())
    connection.provider = provider
    connection.name = name
    connection.last_ingested_at = None
    return connection


@pytest.fixture
def mock_db() -> AsyncMock:
    db = AsyncMock(spec=AsyncSession)
    db.commit = AsyncMock()
    db.add = MagicMock()
    return db


@pytest.fixture
def mock_aws_connection() -> MagicMock:
    return _build_connection(
        AWSConnection,
        provider="aws",
        name="Test AWS Account",
    )


@pytest.fixture
def mock_azure_connection() -> MagicMock:
    return _build_connection(
        AzureConnection,
        provider="azure",
        name="Test Azure Subscription",
    )


@pytest.fixture
def mock_gcp_connection() -> MagicMock:
    return _build_connection(
        GCPConnection,
        provider="gcp",
        name="Test GCP Project",
    )


@pytest.fixture
def mock_saas_connection() -> MagicMock:
    return _build_connection(
        SaaSConnection,
        provider="saas",
        name="Test SaaS Feed",
    )


@pytest.fixture
def mock_license_connection() -> MagicMock:
    return _build_connection(
        LicenseConnection,
        provider="license",
        name="Test License Feed",
    )


@pytest.fixture
def mock_platform_connection() -> MagicMock:
    return _build_connection(
        PlatformConnection,
        provider="platform",
        name="Test Platform Feed",
    )


@pytest.fixture
def mock_hybrid_connection() -> MagicMock:
    return _build_connection(
        HybridConnection,
        provider="hybrid",
        name="Test Hybrid Feed",
    )


@pytest.fixture
def configure_connection_queries(
    mock_db: AsyncMock,
) -> Callable[..., MagicMock]:
    def _configure(
        *,
        aws: list[Any] | None = None,
        azure: list[Any] | None = None,
        gcp: list[Any] | None = None,
        saas: list[Any] | None = None,
        license: list[Any] | None = None,
        platform: list[Any] | None = None,
        hybrid: list[Any] | None = None,
    ) -> MagicMock:
        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [
            aws or [],
            azure or [],
            gcp or [],
            saas or [],
            license or [],
            platform or [],
            hybrid or [],
        ]
        mock_db.execute = AsyncMock(return_value=query_result)
        return query_result

    return _configure


@pytest.fixture
def attach_stream() -> Callable[[AsyncMock, dict[str, Any]], None]:
    def _attach(mock_adapter: AsyncMock, *records: dict[str, Any]) -> None:
        async def _stream() -> AsyncIterator[dict[str, Any]]:
            for record in records:
                yield record

        mock_adapter.stream_cost_and_usage = MagicMock(
            side_effect=lambda *args, **kwargs: _stream()
        )

    return _attach


@pytest.fixture
def make_persistence_stub() -> Callable[..., AsyncMock]:
    def _make(*, records_saved: int, consume_records: bool = False) -> AsyncMock:
        persistence = AsyncMock()
        if consume_records:

            async def _consume(records, *args, **kwargs):
                async for _ in records:
                    pass
                return {"records_saved": records_saved}

            persistence.save_records_stream.side_effect = _consume
        else:
            persistence.save_records_stream = AsyncMock(
                return_value={"records_saved": records_saved}
            )
        return persistence

    return _make
