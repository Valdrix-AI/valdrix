from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.reporting.domain.service import ReportingService


@pytest.mark.asyncio
async def test_ingest_costs_single_connection(
    mock_db,
    mock_aws_connection: MagicMock,
    configure_connection_queries,
    attach_stream,
    make_persistence_stub,
) -> None:
    tenant_id = mock_aws_connection.tenant_id
    configure_connection_queries(aws=[mock_aws_connection])
    service = ReportingService(mock_db)

    with (
        patch("app.modules.reporting.domain.service.AdapterFactory") as mock_factory,
        patch(
            "app.modules.reporting.domain.service.CostPersistenceService"
        ) as mock_persistence,
        patch("app.modules.reporting.domain.service.AttributionEngine") as mock_attribution,
    ):
        mock_adapter = AsyncMock()
        mock_factory.get_adapter.return_value = mock_adapter
        attach_stream(mock_adapter, {"cost_usd": "10.0"}, {"cost_usd": "20.0"})

        mock_persistence_instance = make_persistence_stub(records_saved=2)
        mock_persistence.return_value = mock_persistence_instance

        mock_attribution_instance = AsyncMock()
        mock_attribution.return_value = mock_attribution_instance

        result = await service.ingest_costs_for_tenant(tenant_id)

    assert result["status"] == "completed"
    assert result["connections_processed"] == 1
    assert len(result["details"]) == 1


@pytest.mark.asyncio
async def test_ingest_costs_multiple_connections(
    mock_db,
    mock_aws_connection: MagicMock,
    mock_azure_connection: MagicMock,
    configure_connection_queries,
    attach_stream,
    make_persistence_stub,
) -> None:
    tenant_id = str(uuid.uuid4())
    mock_aws_connection.tenant_id = tenant_id
    mock_azure_connection.tenant_id = tenant_id
    configure_connection_queries(
        aws=[mock_aws_connection],
        azure=[mock_azure_connection],
    )
    service = ReportingService(mock_db)

    with (
        patch("app.modules.reporting.domain.service.AdapterFactory") as mock_factory,
        patch(
            "app.modules.reporting.domain.service.CostPersistenceService"
        ) as mock_persistence,
        patch("app.modules.reporting.domain.service.AttributionEngine"),
    ):
        mock_adapter = AsyncMock()
        mock_factory.get_adapter.return_value = mock_adapter
        attach_stream(mock_adapter, {"cost_usd": "100.0"})

        mock_persistence_instance = make_persistence_stub(records_saved=1)
        mock_persistence.return_value = mock_persistence_instance

        result = await service.ingest_costs_for_tenant(tenant_id)

    assert result["status"] == "completed"
    assert result["connections_processed"] == 2


@pytest.mark.asyncio
async def test_ingest_costs_cloud_plus_connections(
    mock_db,
    mock_saas_connection: MagicMock,
    mock_license_connection: MagicMock,
    mock_platform_connection: MagicMock,
    mock_hybrid_connection: MagicMock,
    configure_connection_queries,
    attach_stream,
    make_persistence_stub,
) -> None:
    tenant_id = str(uuid.uuid4())
    for connection in (
        mock_saas_connection,
        mock_license_connection,
        mock_platform_connection,
        mock_hybrid_connection,
    ):
        connection.tenant_id = tenant_id

    configure_connection_queries(
        saas=[mock_saas_connection],
        license=[mock_license_connection],
        platform=[mock_platform_connection],
        hybrid=[mock_hybrid_connection],
    )
    service = ReportingService(mock_db)

    with (
        patch("app.modules.reporting.domain.service.AdapterFactory") as mock_factory,
        patch(
            "app.modules.reporting.domain.service.CostPersistenceService"
        ) as mock_persistence,
        patch("app.modules.reporting.domain.service.AttributionEngine"),
    ):
        mock_adapter = AsyncMock()
        mock_factory.get_adapter.return_value = mock_adapter
        attach_stream(mock_adapter, {"cost_usd": "15.0"})

        mock_persistence_instance = make_persistence_stub(records_saved=1)
        mock_persistence.return_value = mock_persistence_instance

        result = await service.ingest_costs_for_tenant(tenant_id)

    assert result["status"] == "completed"
    assert result["connections_processed"] == 4
    providers = {entry.get("provider") for entry in result["details"]}
    assert providers == {"saas", "license", "platform", "hybrid"}


@pytest.mark.asyncio
async def test_ingest_costs_connection_failure(
    mock_db,
    mock_aws_connection: MagicMock,
    configure_connection_queries,
) -> None:
    tenant_id = mock_aws_connection.tenant_id
    configure_connection_queries(aws=[mock_aws_connection])
    service = ReportingService(mock_db)

    with patch("app.modules.reporting.domain.service.AdapterFactory") as mock_factory:
        mock_factory.get_adapter.side_effect = RuntimeError("Connection failed")

        result = await service.ingest_costs_for_tenant(tenant_id)

    assert result["status"] == "completed"
    assert any(detail.get("status") == "failed" for detail in result["details"])


@pytest.mark.asyncio
async def test_ingest_costs_missing_cur_data_yields_zero_records(
    mock_db,
    mock_aws_connection: MagicMock,
    configure_connection_queries,
    attach_stream,
    make_persistence_stub,
) -> None:
    tenant_id = mock_aws_connection.tenant_id
    configure_connection_queries(aws=[mock_aws_connection])
    service = ReportingService(mock_db)

    with (
        patch("app.modules.reporting.domain.service.AdapterFactory") as mock_factory,
        patch(
            "app.modules.reporting.domain.service.CostPersistenceService"
        ) as mock_persistence,
        patch("app.modules.reporting.domain.service.AttributionEngine"),
    ):
        mock_adapter = AsyncMock()
        mock_factory.get_adapter.return_value = mock_adapter
        attach_stream(mock_adapter)

        mock_persistence_instance = make_persistence_stub(records_saved=0)
        mock_persistence.return_value = mock_persistence_instance

        result = await service.ingest_costs_for_tenant(tenant_id)

    assert result["status"] == "completed"
    assert result["details"][0]["records_ingested"] == 0
    assert result["details"][0]["total_cost"] == 0.0


@pytest.mark.asyncio
async def test_ingest_costs_invalid_tenant_config_marks_connection_failed(
    mock_db,
    mock_aws_connection: MagicMock,
    configure_connection_queries,
) -> None:
    tenant_id = mock_aws_connection.tenant_id
    configure_connection_queries(aws=[mock_aws_connection])
    service = ReportingService(mock_db)

    with patch("app.modules.reporting.domain.service.AdapterFactory") as mock_factory:
        mock_factory.get_adapter.side_effect = ValueError(
            "Invalid tenant config: missing CUR bucket"
        )

        result = await service.ingest_costs_for_tenant(tenant_id)

    assert result["status"] == "completed"
    assert result["details"][0]["status"] == "failed"
    assert "Invalid tenant config" in result["details"][0]["error"]
