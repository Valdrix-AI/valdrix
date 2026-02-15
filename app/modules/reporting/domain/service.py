"""
Reporting Domain Service
Orchestrates cost ingestion, aggregation, and attribution.
"""

import inspect
import uuid
import structlog
from collections.abc import AsyncIterator
from typing import Dict, Any, List, Awaitable, cast
from datetime import datetime, timezone, timedelta
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.shared.adapters.factory import AdapterFactory
from app.modules.reporting.domain.persistence import CostPersistenceService
from app.modules.reporting.domain.attribution_engine import AttributionEngine
from app.models.aws_connection import AWSConnection
from app.models.azure_connection import AzureConnection
from app.models.gcp_connection import GCPConnection
from app.models.saas_connection import SaaSConnection
from app.models.license_connection import LicenseConnection
from app.models.platform_connection import PlatformConnection
from app.models.hybrid_connection import HybridConnection
from app.models.cloud import CloudAccount
from app.shared.core.service import BaseService
from app.shared.core.async_utils import maybe_call

logger = structlog.get_logger()


class ReportingService(BaseService):
    async def _get_all_connections(self, tenant_id: Any) -> List[Any]:
        """Fetch all cloud and Cloud+ connections for a tenant."""
        connections: List[
            AWSConnection
            | AzureConnection
            | GCPConnection
            | SaaSConnection
            | LicenseConnection
            | PlatformConnection
            | HybridConnection
        ] = []
        for model in [
            AWSConnection,
            AzureConnection,
            GCPConnection,
            SaaSConnection,
            LicenseConnection,
            PlatformConnection,
            HybridConnection,
        ]:
            stmt = self._scoped_query(model, tenant_id)
            result = await self.db.execute(stmt)
            connections.extend(result.scalars().all())
        return connections

    async def ingest_costs_for_tenant(
        self, tenant_id: Any, days: int = 7
    ) -> Dict[str, Any]:
        """
        Orchestrates multi-cloud cost ingestion and attribution.
        """
        connections = await self._get_all_connections(tenant_id)
        if not connections:
            return {"status": "skipped", "reason": "no_active_connections"}

        persistence = CostPersistenceService(self.db)
        results = []

        # 1. Sync CloudAccount registry
        for conn in connections:
            stmt = (
                pg_insert(CloudAccount)
                .values(
                    id=conn.id,
                    tenant_id=conn.tenant_id,
                    provider=conn.provider,
                    name=getattr(conn, "name", f"{conn.provider.upper()} Connection"),
                    is_active=True,
                )
                .on_conflict_do_update(
                    index_elements=["id"],
                    set_={
                        "provider": conn.provider,
                        "name": getattr(
                            conn, "name", f"{conn.provider.upper()} Connection"
                        ),
                    },
                )
            )
            await self.db.execute(stmt)
        # Redundant commit removed (BE-TRANS-1)

        # 2. Ingest per connection
        for conn in connections:
            try:
                run_id = uuid.uuid4()
                adapter = AdapterFactory.get_adapter(conn)
                end_date = datetime.now(timezone.utc)
                start_date = end_date - timedelta(days=days)

                cost_stream_or_awaitable = adapter.stream_cost_and_usage(
                    start_date=start_date, end_date=end_date, granularity="HOURLY"
                )
                if inspect.isawaitable(cost_stream_or_awaitable):
                    cost_stream = cast(
                        AsyncIterator[Dict[str, Any]],
                        await cast(Awaitable[Any], cost_stream_or_awaitable),
                    )
                else:
                    cost_stream = cast(
                        AsyncIterator[Dict[str, Any]], cost_stream_or_awaitable
                    )

                records_ingested = 0
                total_cost_acc = 0.0

                async def tracking_wrapper(
                    stream: AsyncIterator[Dict[str, Any]],
                ) -> AsyncIterator[Dict[str, Any]]:
                    nonlocal records_ingested, total_cost_acc
                    async for r in stream:
                        records_ingested += 1
                        total_cost_acc += float(r.get("cost_usd", 0) or 0)
                        yield r

                save_result = await persistence.save_records_stream(
                    records=tracking_wrapper(cost_stream),
                    tenant_id=tenant_id,  # Already a UUID or passed correctly
                    account_id=conn.id,  # Pass UUID object directly (BE-UUID-1)
                    reconciliation_run_id=run_id,
                    is_preliminary=True,
                )

                conn.last_ingested_at = datetime.now(timezone.utc)
                await maybe_call(self.db.add, conn)

                results.append(
                    {
                        "connection_id": str(conn.id),
                        "provider": conn.provider,
                        "records_ingested": save_result.get("records_saved", 0),
                        "total_cost": total_cost_acc,
                    }
                )

            except Exception as e:
                logger.error(
                    "cost_ingestion_failed", connection_id=str(conn.id), error=str(e)
                )
                results.append(
                    {"connection_id": str(conn.id), "status": "failed", "error": str(e)}
                )

        # Redundant commit removed (BE-TRANS-1)

        # 3. Trigger Attribution
        try:
            attr_engine = AttributionEngine(self.db)
            # Use current month for context
            now = datetime.now(timezone.utc).date()
            start_of_month = now.replace(day=1)
            await attr_engine.apply_rules_to_tenant(
                tenant_id, start_date=start_of_month, end_date=now
            )
            logger.info("attribution_applied_post_ingestion", tenant_id=str(tenant_id))
        except Exception as e:
            logger.error(
                "attribution_trigger_failed", tenant_id=str(tenant_id), error=str(e)
            )

        return {
            "status": "completed",
            "connections_processed": len(connections),
            "details": results,
        }
