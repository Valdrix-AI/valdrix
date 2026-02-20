import pytest
"""
Comprehensive tests for ReportingService module.
Covers cost ingestion, connection handling, data aggregation, and error scenarios.
"""


from unittest.mock import AsyncMock, MagicMock, patch
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.reporting.domain.service import ReportingService
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.models.saas_connection import SaaSConnection
from app.models.license_connection import LicenseConnection
from app.models.platform_connection import PlatformConnection
from app.models.hybrid_connection import HybridConnection


# Fixtures for mock connections
@pytest.fixture
def mock_db():
    """Create a mock AsyncSession."""
    return AsyncMock(spec=AsyncSession)


@pytest.fixture
def mock_aws_connection():
    """Create a mock AWS connection."""
    conn = MagicMock(spec=AWSConnection)
    conn.id = str(uuid.uuid4())
    conn.tenant_id = str(uuid.uuid4())
    conn.provider = "aws"
    conn.name = "Test AWS Account"
    conn.last_ingested_at = None
    return conn


@pytest.fixture
def mock_azure_connection():
    """Create a mock Azure connection."""
    conn = MagicMock(spec=AzureConnection)
    conn.id = str(uuid.uuid4())
    conn.tenant_id = str(uuid.uuid4())
    conn.provider = "azure"
    conn.name = "Test Azure Subscription"
    conn.last_ingested_at = None
    return conn


@pytest.fixture
def mock_gcp_connection():
    """Create a mock GCP connection."""
    conn = MagicMock(spec=GCPConnection)
    conn.id = str(uuid.uuid4())
    conn.tenant_id = str(uuid.uuid4())
    conn.provider = "gcp"
    conn.name = "Test GCP Project"
    conn.last_ingested_at = None
    return conn


@pytest.fixture
def mock_saas_connection():
    """Create a mock SaaS connection."""
    conn = MagicMock(spec=SaaSConnection)
    conn.id = str(uuid.uuid4())
    conn.tenant_id = str(uuid.uuid4())
    conn.provider = "saas"
    conn.name = "Test SaaS Feed"
    conn.last_ingested_at = None
    return conn


@pytest.fixture
def mock_license_connection():
    """Create a mock license connection."""
    conn = MagicMock(spec=LicenseConnection)
    conn.id = str(uuid.uuid4())
    conn.tenant_id = str(uuid.uuid4())
    conn.provider = "license"
    conn.name = "Test License Feed"
    conn.last_ingested_at = None
    return conn


@pytest.fixture
def mock_platform_connection():
    """Create a mock platform connection."""
    conn = MagicMock(spec=PlatformConnection)
    conn.id = str(uuid.uuid4())
    conn.tenant_id = str(uuid.uuid4())
    conn.provider = "platform"
    conn.name = "Test Platform Feed"
    conn.last_ingested_at = None
    return conn


@pytest.fixture
def mock_hybrid_connection():
    """Create a mock hybrid connection."""
    conn = MagicMock(spec=HybridConnection)
    conn.id = str(uuid.uuid4())
    conn.tenant_id = str(uuid.uuid4())
    conn.provider = "hybrid"
    conn.name = "Test Hybrid Feed"
    conn.last_ingested_at = None
    return conn


class TestGetAllConnections:
    """Test the _get_all_connections internal method."""

    @pytest.mark.asyncio
    async def test_get_all_connections_single_aws(self, mock_db, mock_aws_connection):
        """Test fetching a single AWS connection."""
        tenant_id = mock_aws_connection.tenant_id

        # Mock the database execute call
        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [
            [mock_aws_connection],
            [],
            [],
            [],
            [],
            [],
            [],
        ]

        mock_db.execute = AsyncMock(return_value=query_result)

        service = ReportingService(mock_db)
        connections = await service._get_all_connections(tenant_id)

        assert len(connections) == 1
        assert connections[0].provider == "aws"

    @pytest.mark.asyncio
    async def test_get_all_connections_empty(self, mock_db):
        """Test fetching connections when none exist."""
        tenant_id = str(uuid.uuid4())

        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = []

        mock_db.execute = AsyncMock(return_value=query_result)

        service = ReportingService(mock_db)
        connections = await service._get_all_connections(tenant_id)

        assert connections == []

    @pytest.mark.asyncio
    async def test_get_all_connections_multiple_providers(
        self,
        mock_db,
        mock_aws_connection,
        mock_azure_connection,
        mock_gcp_connection,
        mock_saas_connection,
        mock_license_connection,
        mock_platform_connection,
        mock_hybrid_connection,
    ):
        """Test fetching connections from cloud and Cloud+ providers."""
        tenant_id = str(uuid.uuid4())

        # All connections have same tenant_id
        all_connections = [
            mock_aws_connection,
            mock_azure_connection,
            mock_gcp_connection,
            mock_saas_connection,
            mock_license_connection,
            mock_platform_connection,
            mock_hybrid_connection,
        ]
        for conn in all_connections:
            conn.tenant_id = tenant_id

        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [[conn] for conn in all_connections]
        mock_db.execute = AsyncMock(return_value=query_result)
        mock_db.commit = AsyncMock()

        service = ReportingService(mock_db)
        connections = await service._get_all_connections(tenant_id)

        providers = {conn.provider for conn in connections}
        assert providers == {
            "aws",
            "azure",
            "gcp",
            "saas",
            "license",
            "platform",
            "hybrid",
        }


class TestCostIngestionNoConnections:
    """Test cost ingestion when no connections exist."""

    @pytest.mark.asyncio
    async def test_ingest_costs_no_active_connections(self, mock_db):
        """Test ingestion returns early when no connections exist."""
        tenant_id = str(uuid.uuid4())

        # Mock _get_all_connections to return empty
        query_result = MagicMock()
        query_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=query_result)

        service = ReportingService(mock_db)
        result = await service.ingest_costs_for_tenant(tenant_id)

        assert result["status"] == "skipped"
        assert result["reason"] == "no_active_connections"


class TestCostIngestionWithConnections:
    """Test cost ingestion with active connections."""

    @pytest.mark.asyncio
    async def test_ingest_costs_single_connection(self, mock_db, mock_aws_connection):
        """Test cost ingestion with single AWS connection."""
        tenant_id = mock_aws_connection.tenant_id

        # Mock database operations
        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [
            [mock_aws_connection],
            [],
            [],
            [],
            [],
            [],
            [],
        ]
        mock_db.execute = AsyncMock(return_value=query_result)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        service = ReportingService(mock_db)

        # Mock the adapter and related services
        with (
            patch(
                "app.modules.reporting.domain.service.AdapterFactory"
            ) as mock_factory,
            patch(
                "app.modules.reporting.domain.service.CostPersistenceService"
            ) as mock_persistence,
            patch(
                "app.modules.reporting.domain.service.AttributionEngine"
            ) as mock_attribution,
        ):
            mock_adapter = AsyncMock()
            mock_factory.get_adapter.return_value = mock_adapter

            # Mock stream
            async def mock_stream():
                yield {"cost_usd": "10.0"}
                yield {"cost_usd": "20.0"}

            # mock_stream returns an async_generator
            # stream_cost_and_usage should be a MagicMock with side_effect to return new generator each time
            mock_adapter.stream_cost_and_usage = MagicMock(
                side_effect=lambda *args, **kwargs: mock_stream()
            )

            # Mock persistence service
            mock_persistence_instance = AsyncMock()
            mock_persistence_instance.save_records_stream = AsyncMock(
                return_value={"records_saved": 2}
            )
            mock_persistence.return_value = mock_persistence_instance

            # Mock attribution engine
            mock_attribution_instance = AsyncMock()
            mock_attribution.return_value = mock_attribution_instance
            mock_attribution_instance.apply_rules_to_tenant = AsyncMock()

            result = await service.ingest_costs_for_tenant(tenant_id)

            assert result["status"] == "completed"
            assert result["connections_processed"] == 1
            assert len(result["details"]) == 1

    @pytest.mark.asyncio
    async def test_ingest_costs_multiple_connections(
        self, mock_db, mock_aws_connection, mock_azure_connection
    ):
        """Test cost ingestion with multiple connections."""
        tenant_id = str(uuid.uuid4())

        # Set same tenant for both
        mock_aws_connection.tenant_id = tenant_id
        mock_azure_connection.tenant_id = tenant_id

        # Mock database
        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [
            [mock_aws_connection],
            [mock_azure_connection],
            [],
            [],
            [],
            [],
            [],
        ]
        mock_db.execute = AsyncMock(return_value=query_result)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        service = ReportingService(mock_db)

        with (
            patch(
                "app.modules.reporting.domain.service.AdapterFactory"
            ) as mock_factory,
            patch(
                "app.modules.reporting.domain.service.CostPersistenceService"
            ) as mock_persistence,
            patch("app.modules.reporting.domain.service.AttributionEngine"),
        ):
            mock_adapter = AsyncMock()
            mock_factory.get_adapter.return_value = mock_adapter

            async def mock_stream():
                yield {"cost_usd": "100.0"}

            mock_adapter.stream_cost_and_usage = MagicMock(
                side_effect=lambda *args, **kwargs: mock_stream()
            )

            mock_persistence_instance = AsyncMock()
            mock_persistence_instance.save_records_stream = AsyncMock(
                return_value={"records_saved": 1}
            )
            mock_persistence.return_value = mock_persistence_instance

            result = await service.ingest_costs_for_tenant(tenant_id)

            assert result["status"] == "completed"
            assert result["connections_processed"] == 2

    @pytest.mark.asyncio
    async def test_ingest_costs_cloud_plus_connections(
        self,
        mock_db,
        mock_saas_connection,
        mock_license_connection,
        mock_platform_connection,
        mock_hybrid_connection,
    ):
        """Cloud+ connectors should participate in unified ingestion."""
        tenant_id = str(uuid.uuid4())
        mock_saas_connection.tenant_id = tenant_id
        mock_license_connection.tenant_id = tenant_id
        mock_platform_connection.tenant_id = tenant_id
        mock_hybrid_connection.tenant_id = tenant_id

        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [
            [],
            [],
            [],
            [mock_saas_connection],
            [mock_license_connection],
            [mock_platform_connection],
            [mock_hybrid_connection],
        ]
        mock_db.execute = AsyncMock(return_value=query_result)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        service = ReportingService(mock_db)

        with (
            patch(
                "app.modules.reporting.domain.service.AdapterFactory"
            ) as mock_factory,
            patch(
                "app.modules.reporting.domain.service.CostPersistenceService"
            ) as mock_persistence,
            patch("app.modules.reporting.domain.service.AttributionEngine"),
        ):
            mock_adapter = AsyncMock()
            mock_factory.get_adapter.return_value = mock_adapter

            async def mock_stream():
                yield {"cost_usd": "15.0"}

            mock_adapter.stream_cost_and_usage = MagicMock(
                side_effect=lambda *args, **kwargs: mock_stream()
            )

            mock_persistence_instance = AsyncMock()
            mock_persistence_instance.save_records_stream = AsyncMock(
                return_value={"records_saved": 1}
            )
            mock_persistence.return_value = mock_persistence_instance

            result = await service.ingest_costs_for_tenant(tenant_id)

            assert result["status"] == "completed"
            assert result["connections_processed"] == 4
            providers = {entry.get("provider") for entry in result["details"]}
            assert providers == {"saas", "license", "platform", "hybrid"}

    @pytest.mark.asyncio
    async def test_ingest_costs_connection_failure(self, mock_db, mock_aws_connection):
        """Test cost ingestion handles connection errors gracefully."""
        tenant_id = mock_aws_connection.tenant_id

        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [
            [mock_aws_connection],
            [],
            [],
            [],
            [],
            [],
            [],
        ]
        mock_db.execute = AsyncMock(return_value=query_result)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        service = ReportingService(mock_db)

        with patch(
            "app.modules.reporting.domain.service.AdapterFactory"
        ) as mock_factory:
            # Simulate adapter failure
            mock_factory.get_adapter.side_effect = Exception("Connection failed")

            result = await service.ingest_costs_for_tenant(tenant_id)

            assert result["status"] == "completed"
            assert any(d.get("status") == "failed" for d in result["details"])

    @pytest.mark.asyncio
    async def test_ingest_costs_missing_cur_data_yields_zero_records(
        self, mock_db, mock_aws_connection
    ):
        """Missing CUR data (empty stream) should not break ingestion."""
        tenant_id = mock_aws_connection.tenant_id

        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [
            [mock_aws_connection],
            [],
            [],
            [],
            [],
            [],
            [],
        ]
        mock_db.execute = AsyncMock(return_value=query_result)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        service = ReportingService(mock_db)

        with (
            patch(
                "app.modules.reporting.domain.service.AdapterFactory"
            ) as mock_factory,
            patch(
                "app.modules.reporting.domain.service.CostPersistenceService"
            ) as mock_persistence,
            patch("app.modules.reporting.domain.service.AttributionEngine"),
        ):
            mock_adapter = AsyncMock()
            mock_factory.get_adapter.return_value = mock_adapter

            async def empty_stream():
                if False:  # pragma: no cover
                    yield {}

            mock_adapter.stream_cost_and_usage = MagicMock(
                side_effect=lambda *args, **kwargs: empty_stream()
            )

            mock_persistence_instance = AsyncMock()
            mock_persistence_instance.save_records_stream = AsyncMock(
                return_value={"records_saved": 0}
            )
            mock_persistence.return_value = mock_persistence_instance

            result = await service.ingest_costs_for_tenant(tenant_id)

            assert result["status"] == "completed"
            assert result["details"][0]["records_ingested"] == 0
            assert result["details"][0]["total_cost"] == 0.0

    @pytest.mark.asyncio
    async def test_ingest_costs_invalid_tenant_config_marks_connection_failed(
        self, mock_db, mock_aws_connection
    ):
        """Invalid tenant connection config should fail safely per connection."""
        tenant_id = mock_aws_connection.tenant_id

        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [
            [mock_aws_connection],
            [],
            [],
            [],
            [],
            [],
            [],
        ]
        mock_db.execute = AsyncMock(return_value=query_result)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        service = ReportingService(mock_db)

        with patch(
            "app.modules.reporting.domain.service.AdapterFactory"
        ) as mock_factory:
            mock_factory.get_adapter.side_effect = ValueError(
                "Invalid tenant config: missing CUR bucket"
            )

            result = await service.ingest_costs_for_tenant(tenant_id)

            assert result["status"] == "completed"
            assert result["details"][0]["status"] == "failed"
            assert "Invalid tenant config" in result["details"][0]["error"]


class TestCloudAccountRegistry:
    """Test CloudAccount registry synchronization."""

    @pytest.mark.asyncio
    async def test_ingest_syncs_cloud_account_registry(
        self, mock_db, mock_aws_connection
    ):
        """Test that ingestion syncs CloudAccount registry."""
        tenant_id = mock_aws_connection.tenant_id

        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [
            [mock_aws_connection],
            [],
            [],
            [],
            [],
            [],
            [],
        ]
        mock_db.execute = AsyncMock(return_value=query_result)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        service = ReportingService(mock_db)

        with (
            patch(
                "app.modules.reporting.domain.service.AdapterFactory"
            ) as mock_factory,
            patch(
                "app.modules.reporting.domain.service.CostPersistenceService"
            ) as mock_persistence,
            patch("app.modules.reporting.domain.service.AttributionEngine"),
        ):
            mock_adapter = AsyncMock()
            mock_factory.get_adapter.return_value = mock_adapter

            async def mock_stream():
                yield {"cost_usd": "50.0"}

            mock_adapter.stream_cost_and_usage = MagicMock(
                side_effect=lambda *args, **kwargs: mock_stream()
            )

            mock_persistence_instance = AsyncMock()
            mock_persistence_instance.save_records_stream = AsyncMock(
                return_value={"records_saved": 1}
            )
            mock_persistence.return_value = mock_persistence_instance

            await service.ingest_costs_for_tenant(tenant_id)

            # Check that execute was called (for registry sync with upsert)
            assert mock_db.execute.called
            # Commit is handled by caller (e.g. JobProcessor) - BE-TRANS-1


class TestAttributionTriggering:
    """Test attribution engine triggering."""

    @pytest.mark.asyncio
    async def test_ingest_triggers_attribution(self, mock_db, mock_aws_connection):
        """Test that ingestion triggers attribution rules."""
        tenant_id = mock_aws_connection.tenant_id

        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [
            [mock_aws_connection],
            [],
            [],
            [],
            [],
            [],
            [],
        ]
        mock_db.execute = AsyncMock(return_value=query_result)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        service = ReportingService(mock_db)

        with (
            patch(
                "app.modules.reporting.domain.service.AdapterFactory"
            ) as mock_factory,
            patch(
                "app.modules.reporting.domain.service.CostPersistenceService"
            ) as mock_persistence,
            patch(
                "app.modules.reporting.domain.service.AttributionEngine"
            ) as mock_attribution,
        ):
            mock_adapter = AsyncMock()
            mock_factory.get_adapter.return_value = mock_adapter

            async def mock_stream():
                yield {"cost_usd": "100.0"}

            mock_adapter.stream_cost_and_usage = MagicMock(
                side_effect=lambda *args, **kwargs: mock_stream()
            )

            mock_persistence_instance = AsyncMock()
            mock_persistence_instance.save_records_stream = AsyncMock(
                return_value={"records_saved": 1}
            )
            mock_persistence.return_value = mock_persistence_instance

            mock_attribution_instance = AsyncMock()
            mock_attribution.return_value = mock_attribution_instance

            await service.ingest_costs_for_tenant(tenant_id)

            # Attribution engine should be instantiated and used
            mock_attribution.assert_called_once_with(mock_db)
            mock_attribution_instance.apply_rules_to_tenant.assert_called_once()

    @pytest.mark.asyncio
    async def test_ingest_handles_attribution_failure(
        self, mock_db, mock_aws_connection
    ):
        """Test that ingestion continues if attribution fails."""
        tenant_id = mock_aws_connection.tenant_id

        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [
            [mock_aws_connection],
            [],
            [],
            [],
            [],
            [],
            [],
        ]
        mock_db.execute = AsyncMock(return_value=query_result)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        service = ReportingService(mock_db)

        with (
            patch(
                "app.modules.reporting.domain.service.AdapterFactory"
            ) as mock_factory,
            patch(
                "app.modules.reporting.domain.service.CostPersistenceService"
            ) as mock_persistence,
            patch(
                "app.modules.reporting.domain.service.AttributionEngine"
            ) as mock_attribution,
        ):
            mock_adapter = AsyncMock()
            mock_factory.get_adapter.return_value = mock_adapter

            async def mock_stream():
                yield {"cost_usd": "50.0"}

            mock_adapter.stream_cost_and_usage = MagicMock(
                side_effect=lambda *args, **kwargs: mock_stream()
            )

            mock_persistence_instance = AsyncMock()
            mock_persistence_instance.save_records_stream = AsyncMock(
                return_value={"records_saved": 1}
            )
            mock_persistence.return_value = mock_persistence_instance

            # Attribution fails
            mock_attribution_instance = AsyncMock()
            mock_attribution_instance.apply_rules_to_tenant.side_effect = Exception(
                "Attribution error"
            )
            mock_attribution.return_value = mock_attribution_instance

            result = await service.ingest_costs_for_tenant(tenant_id)

            # Should still return completed status
            assert result["status"] == "completed"


class TestCostAggregation:
    """Test cost stream aggregation and tracking."""

    @pytest.mark.asyncio
    async def test_ingest_aggregates_costs(self, mock_db, mock_aws_connection):
        """Test that cost stream is aggregated correctly."""
        tenant_id = mock_aws_connection.tenant_id

        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [
            [mock_aws_connection],
            [],
            [],
            [],
            [],
            [],
            [],
        ]
        mock_db.execute = AsyncMock(return_value=query_result)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        service = ReportingService(mock_db)

        with (
            patch(
                "app.modules.reporting.domain.service.AdapterFactory"
            ) as mock_factory,
            patch(
                "app.modules.reporting.domain.service.CostPersistenceService"
            ) as mock_persistence,
            patch("app.modules.reporting.domain.service.AttributionEngine"),
        ):
            mock_adapter = AsyncMock()
            mock_factory.get_adapter.return_value = mock_adapter

            # Stream multiple records with costs
            async def mock_stream():
                yield {"cost_usd": "10.0"}
                yield {"cost_usd": "20.0"}
                yield {"cost_usd": "15.0"}

            mock_adapter.stream_cost_and_usage = MagicMock(
                side_effect=lambda *args, **kwargs: mock_stream()
            )

            mock_persistence_instance = AsyncMock()

            async def consume_stream(records, *args, **kwargs):
                async for _ in records:
                    pass
                return {"records_saved": 3}

            mock_persistence_instance.save_records_stream.side_effect = consume_stream
            mock_persistence.return_value = mock_persistence_instance

            result = await service.ingest_costs_for_tenant(tenant_id)

            # Check result contains aggregated info
            assert result["details"][0]["records_ingested"] == 3
            # Total cost = 10 + 20 + 15 = 45
            assert result["details"][0]["total_cost"] == 45.0

    @pytest.mark.asyncio
    async def test_ingest_handles_null_costs(self, mock_db, mock_aws_connection):
        """Test that null/missing costs are handled gracefully."""
        tenant_id = mock_aws_connection.tenant_id

        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [
            [mock_aws_connection],
            [],
            [],
            [],
            [],
            [],
            [],
        ]
        mock_db.execute = AsyncMock(return_value=query_result)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        service = ReportingService(mock_db)

        with (
            patch(
                "app.modules.reporting.domain.service.AdapterFactory"
            ) as mock_factory,
            patch(
                "app.modules.reporting.domain.service.CostPersistenceService"
            ) as mock_persistence,
            patch("app.modules.reporting.domain.service.AttributionEngine"),
        ):
            mock_adapter = AsyncMock()
            mock_factory.get_adapter.return_value = mock_adapter

            async def mock_stream():
                yield {"cost_usd": "10.0"}
                yield {"cost_usd": None}  # Null cost
                yield {"cost_usd": "20.0"}

            mock_adapter.stream_cost_and_usage = MagicMock(
                side_effect=lambda *args, **kwargs: mock_stream()
            )

            mock_persistence_instance = AsyncMock()
            mock_persistence_instance.save_records_stream = AsyncMock(
                return_value={"records_saved": 3}
            )
            mock_persistence.return_value = mock_persistence_instance

            result = await service.ingest_costs_for_tenant(tenant_id)

            # Should handle gracefully - cost should be None converted to 0
            assert result["status"] == "completed"


class TestConnectionMetadataUpdate:
    """Test connection metadata updates during ingestion."""

    @pytest.mark.asyncio
    async def test_ingest_updates_connection_last_ingested_at(
        self, mock_db, mock_aws_connection
    ):
        """Test that connection's last_ingested_at timestamp is updated."""
        tenant_id = mock_aws_connection.tenant_id

        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [
            [mock_aws_connection],
            [],
            [],
            [],
            [],
            [],
            [],
        ]
        mock_db.execute = AsyncMock(return_value=query_result)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        service = ReportingService(mock_db)

        with (
            patch(
                "app.modules.reporting.domain.service.AdapterFactory"
            ) as mock_factory,
            patch(
                "app.modules.reporting.domain.service.CostPersistenceService"
            ) as mock_persistence,
            patch("app.modules.reporting.domain.service.AttributionEngine"),
        ):
            mock_adapter = AsyncMock()
            mock_factory.get_adapter.return_value = mock_adapter

            async def mock_stream():
                yield {"cost_usd": "100.0"}

            mock_adapter.stream_cost_and_usage = MagicMock(
                side_effect=lambda *args, **kwargs: mock_stream()
            )

            mock_persistence_instance = AsyncMock()
            mock_persistence_instance.save_records_stream = AsyncMock(
                return_value={"records_saved": 1}
            )
            mock_persistence.return_value = mock_persistence_instance

            await service.ingest_costs_for_tenant(tenant_id)

            # Connection should be added to session (indicating update)
            mock_db.add.assert_called()


class TestDaysParameter:
    """Test days parameter for cost window."""

    @pytest.mark.asyncio
    async def test_ingest_respects_days_parameter(self, mock_db, mock_aws_connection):
        """Test that days parameter affects date range."""
        tenant_id = mock_aws_connection.tenant_id

        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [
            [mock_aws_connection],
            [],
            [],
            [],
            [],
            [],
            [],
        ]
        mock_db.execute = AsyncMock(return_value=query_result)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        service = ReportingService(mock_db)

        with (
            patch(
                "app.modules.reporting.domain.service.AdapterFactory"
            ) as mock_factory,
            patch(
                "app.modules.reporting.domain.service.CostPersistenceService"
            ) as mock_persistence,
            patch("app.modules.reporting.domain.service.AttributionEngine"),
        ):
            mock_adapter = AsyncMock()
            mock_factory.get_adapter.return_value = mock_adapter

            async def mock_stream():
                yield {"cost_usd": "1.0"}

            mock_adapter.stream_cost_and_usage = MagicMock(
                side_effect=lambda *args, **kwargs: mock_stream()
            )

            mock_persistence_instance = AsyncMock()
            mock_persistence_instance.save_records_stream = AsyncMock(
                return_value={"records_saved": 1}
            )
            mock_persistence.return_value = mock_persistence_instance

            # Ingest with custom days
            await service.ingest_costs_for_tenant(tenant_id, days=30)

            # Adapter should be called with appropriate date range
            assert mock_adapter.stream_cost_and_usage.call_count == 1
            call_kwargs = mock_adapter.stream_cost_and_usage.call_args[1]

            # end_date - start_date should be ~30 days
            time_diff = call_kwargs["end_date"] - call_kwargs["start_date"]
            assert time_diff.days == 30


class TestResponseStructure:
    """Test response structure from ingestion methods."""

    @pytest.mark.asyncio
    async def test_ingest_response_has_required_fields(
        self, mock_db, mock_aws_connection
    ):
        """Test that response contains all required fields."""
        tenant_id = mock_aws_connection.tenant_id

        query_result = MagicMock()
        query_result.scalars.return_value.all.side_effect = [
            [mock_aws_connection],
            [],
            [],
            [],
            [],
            [],
            [],
        ]
        mock_db.execute = AsyncMock(return_value=query_result)
        mock_db.commit = AsyncMock()
        mock_db.add = MagicMock()

        service = ReportingService(mock_db)

        with (
            patch(
                "app.modules.reporting.domain.service.AdapterFactory"
            ) as mock_factory,
            patch(
                "app.modules.reporting.domain.service.CostPersistenceService"
            ) as mock_persistence,
            patch("app.modules.reporting.domain.service.AttributionEngine"),
        ):
            mock_adapter = AsyncMock()
            mock_factory.get_adapter.return_value = mock_adapter

            async def mock_stream():
                yield {"cost_usd": "50.0"}

            mock_adapter.stream_cost_and_usage = MagicMock(
                side_effect=lambda *args, **kwargs: mock_stream()
            )

            mock_persistence_instance = AsyncMock()
            mock_persistence_instance.save_records_stream = AsyncMock(
                return_value={"records_saved": 1}
            )
            mock_persistence.return_value = mock_persistence_instance

            result = await service.ingest_costs_for_tenant(tenant_id)

            required_response_fields = ["status", "connections_processed", "details"]
            for field in required_response_fields:
                assert field in result

            # Details should contain result for each connection
            assert isinstance(result["details"], list)
            for detail in result["details"]:
                assert "connection_id" in detail
                assert "provider" in detail
