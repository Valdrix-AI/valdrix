from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from app.modules.reporting.domain.service import ReportingService


@pytest.mark.asyncio
async def test_get_all_connections_single_aws(
    mock_db,
    mock_aws_connection: MagicMock,
    configure_connection_queries,
) -> None:
    tenant_id = mock_aws_connection.tenant_id
    configure_connection_queries(aws=[mock_aws_connection])

    service = ReportingService(mock_db)
    connections = await service._get_all_connections(tenant_id)

    assert len(connections) == 1
    assert connections[0].provider == "aws"


@pytest.mark.asyncio
async def test_get_all_connections_empty(
    mock_db,
    configure_connection_queries,
) -> None:
    tenant_id = str(uuid.uuid4())
    configure_connection_queries()

    service = ReportingService(mock_db)
    connections = await service._get_all_connections(tenant_id)

    assert connections == []


@pytest.mark.asyncio
async def test_get_all_connections_multiple_providers(
    mock_db,
    mock_aws_connection: MagicMock,
    mock_azure_connection: MagicMock,
    mock_gcp_connection: MagicMock,
    mock_saas_connection: MagicMock,
    mock_license_connection: MagicMock,
    mock_platform_connection: MagicMock,
    mock_hybrid_connection: MagicMock,
    configure_connection_queries,
) -> None:
    tenant_id = str(uuid.uuid4())
    all_connections = [
        mock_aws_connection,
        mock_azure_connection,
        mock_gcp_connection,
        mock_saas_connection,
        mock_license_connection,
        mock_platform_connection,
        mock_hybrid_connection,
    ]
    for connection in all_connections:
        connection.tenant_id = tenant_id

    configure_connection_queries(
        aws=[mock_aws_connection],
        azure=[mock_azure_connection],
        gcp=[mock_gcp_connection],
        saas=[mock_saas_connection],
        license=[mock_license_connection],
        platform=[mock_platform_connection],
        hybrid=[mock_hybrid_connection],
    )

    service = ReportingService(mock_db)
    connections = await service._get_all_connections(tenant_id)

    providers = {connection.provider for connection in connections}
    assert providers == {
        "aws",
        "azure",
        "gcp",
        "saas",
        "license",
        "platform",
        "hybrid",
    }


@pytest.mark.asyncio
async def test_ingest_costs_no_active_connections(
    mock_db,
    configure_connection_queries,
) -> None:
    tenant_id = str(uuid.uuid4())
    configure_connection_queries()

    service = ReportingService(mock_db)
    result = await service.ingest_costs_for_tenant(tenant_id)

    assert result["status"] == "skipped"
    assert result["reason"] == "no_active_connections"
