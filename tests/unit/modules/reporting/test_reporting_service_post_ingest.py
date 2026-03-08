from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.reporting.domain.service import ReportingService


@pytest.mark.asyncio
async def test_ingest_syncs_cloud_account_registry(
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
        attach_stream(mock_adapter, {"cost_usd": "50.0"})

        mock_persistence_instance = make_persistence_stub(records_saved=1)
        mock_persistence.return_value = mock_persistence_instance

        await service.ingest_costs_for_tenant(tenant_id)

    assert mock_db.execute.called


@pytest.mark.asyncio
async def test_ingest_triggers_attribution(
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
        attach_stream(mock_adapter, {"cost_usd": "100.0"})

        mock_persistence_instance = make_persistence_stub(records_saved=1)
        mock_persistence.return_value = mock_persistence_instance

        mock_attribution_instance = AsyncMock()
        mock_attribution.return_value = mock_attribution_instance

        await service.ingest_costs_for_tenant(tenant_id)

    mock_attribution.assert_called_once_with(mock_db)
    mock_attribution_instance.apply_rules_to_tenant.assert_called_once()


@pytest.mark.asyncio
async def test_ingest_handles_attribution_failure(
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
        attach_stream(mock_adapter, {"cost_usd": "50.0"})

        mock_persistence_instance = make_persistence_stub(records_saved=1)
        mock_persistence.return_value = mock_persistence_instance

        mock_attribution_instance = AsyncMock()
        mock_attribution_instance.apply_rules_to_tenant.side_effect = RuntimeError(
            "Attribution error"
        )
        mock_attribution.return_value = mock_attribution_instance

        result = await service.ingest_costs_for_tenant(tenant_id)

    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_ingest_aggregates_costs(
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
        attach_stream(
            mock_adapter,
            {"cost_usd": "10.0"},
            {"cost_usd": "20.0"},
            {"cost_usd": "15.0"},
        )

        mock_persistence_instance = make_persistence_stub(
            records_saved=3,
            consume_records=True,
        )
        mock_persistence.return_value = mock_persistence_instance

        result = await service.ingest_costs_for_tenant(tenant_id)

    assert result["details"][0]["records_ingested"] == 3
    assert result["details"][0]["total_cost"] == 45.0


@pytest.mark.asyncio
async def test_ingest_handles_null_costs(
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
        attach_stream(
            mock_adapter,
            {"cost_usd": "10.0"},
            {"cost_usd": None},
            {"cost_usd": "20.0"},
        )

        mock_persistence_instance = make_persistence_stub(records_saved=3)
        mock_persistence.return_value = mock_persistence_instance

        result = await service.ingest_costs_for_tenant(tenant_id)

    assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_ingest_updates_connection_last_ingested_at(
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
        attach_stream(mock_adapter, {"cost_usd": "100.0"})

        mock_persistence_instance = make_persistence_stub(records_saved=1)
        mock_persistence.return_value = mock_persistence_instance

        await service.ingest_costs_for_tenant(tenant_id)

    mock_db.add.assert_called()


@pytest.mark.asyncio
async def test_ingest_respects_days_parameter(
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
        attach_stream(mock_adapter, {"cost_usd": "1.0"})

        mock_persistence_instance = make_persistence_stub(records_saved=1)
        mock_persistence.return_value = mock_persistence_instance

        await service.ingest_costs_for_tenant(tenant_id, days=30)

    assert mock_adapter.stream_cost_and_usage.call_count == 1
    call_kwargs = mock_adapter.stream_cost_and_usage.call_args[1]
    time_diff = call_kwargs["end_date"] - call_kwargs["start_date"]
    assert time_diff.days == 30


@pytest.mark.asyncio
async def test_ingest_response_has_required_fields(
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
        attach_stream(mock_adapter, {"cost_usd": "50.0"})

        mock_persistence_instance = make_persistence_stub(records_saved=1)
        mock_persistence.return_value = mock_persistence_instance

        result = await service.ingest_costs_for_tenant(tenant_id)

    required_response_fields = ["status", "connections_processed", "details"]
    for field in required_response_fields:
        assert field in result

    assert isinstance(result["details"], list)
    for detail in result["details"]:
        assert "connection_id" in detail
        assert "provider" in detail
