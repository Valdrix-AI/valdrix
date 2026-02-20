import structlog
from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from typing import TYPE_CHECKING, Optional, Dict, Any
import asyncio

if TYPE_CHECKING:
    from app.shared.llm.guardrails import FinOpsAnalysisResult
    from app.models.remediation import RemediationAction
    from uuid import UUID
from app.models.tenant import Tenant
from app.shared.llm.factory import LLMFactory
from app.shared.llm.analyzer import FinOpsAnalyzer
from app.modules.reporting.domain.calculator import CarbonCalculator
from app.modules.optimization.domain.factory import ZombieDetectorFactory
from app.shared.adapters.factory import AdapterFactory
from app.schemas.costs import CloudUsageSummary, CostRecord
from app.shared.core.adapter_usage import fetch_daily_costs_if_supported
from app.shared.core.connection_state import is_connection_active, resolve_connection_region
from app.shared.core.connection_queries import CONNECTION_MODEL_PAIRS
from app.shared.core.config import get_settings
from app.shared.core.provider import (
    SUPPORTED_PROVIDERS,
    normalize_provider,
    resolve_provider_from_connection,
)

logger = structlog.get_logger()


class AnalysisProcessor:
    """Handles the heavy lifting of analyzing a single tenant's cloud usage."""

    def __init__(self) -> None:
        self.settings = get_settings()

    @staticmethod
    def _collect_connections(tenant: Tenant) -> list[Any]:
        connections: list[Any] = []
        for provider, _model in CONNECTION_MODEL_PAIRS:
            relation_name = f"{provider}_connections"
            provider_connections = list(getattr(tenant, relation_name, []) or [])
            connections.extend(provider_connections)
        return [conn for conn in connections if is_connection_active(conn)]

    @staticmethod
    def _as_datetime(value: Any) -> datetime:
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        if isinstance(value, date):
            return datetime.combine(value, time.min, tzinfo=timezone.utc)
        return datetime.now(timezone.utc)

    def _build_usage_summary_from_rows(
        self,
        rows: list[dict[str, Any]],
        tenant_id: str,
        provider: str,
        start_date: date,
        end_date: date,
    ) -> CloudUsageSummary | None:
        records: list[CostRecord] = []
        for row in rows:
            raw_amount = row.get("cost_usd", 0) or 0
            amount = Decimal(str(raw_amount))
            if amount <= 0:
                continue

            amount_raw = row.get("amount_raw")
            amount_raw_decimal = (
                Decimal(str(amount_raw)) if amount_raw is not None else None
            )
            tags = row.get("tags")
            records.append(
                CostRecord(
                    date=self._as_datetime(row.get("timestamp")),
                    amount=amount,
                    amount_raw=amount_raw_decimal,
                    currency=str(row.get("currency") or "USD"),
                    service=str(row.get("service") or "unknown"),
                    region=row.get("region"),
                    usage_type=row.get("usage_type"),
                    tags=tags if isinstance(tags, dict) else {},
                )
            )

        if not records:
            return None

        total_cost = sum((record.amount for record in records), Decimal("0"))
        return CloudUsageSummary(
            tenant_id=tenant_id,
            provider=provider,
            start_date=start_date,
            end_date=end_date,
            total_cost=total_cost,
            records=records,
        )

    async def process_tenant(
        self, db: AsyncSession, tenant: Tenant, start_date: date, end_date: date
    ) -> None:
        """Process a single tenant's analysis."""
        try:
            logger.info("processing_tenant", tenant_id=str(tenant.id), name=tenant.name)

            # 1. Use pre-loaded Notification Settings (Avoids N+1 query)
            notif_settings = tenant.notification_settings

            # 2. Use pre-loaded cloud connections across providers.
            connections = self._collect_connections(tenant)

            if not connections:
                logger.info("tenant_no_connections", tenant_id=str(tenant.id))
                return

            llm = LLMFactory.create(self.settings.LLM_PROVIDER)
            analyzer = FinOpsAnalyzer(llm)
            carbon_calc = CarbonCalculator()
            savings_processor = SavingsProcessor()
            start_dt = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
            end_dt = datetime.combine(end_date, time.max, tzinfo=timezone.utc)

            for conn in connections:
                try:
                    async def _run_analysis() -> None:
                        provider = resolve_provider_from_connection(conn)
                        if not provider:
                            logger.warning(
                                "tenant_connection_provider_unresolved",
                                tenant_id=str(tenant.id),
                                connection_id=str(getattr(conn, "id", "unknown")),
                            )
                            return
                        adapter = AdapterFactory.get_adapter(conn)

                        usage_summary = await fetch_daily_costs_if_supported(
                            adapter,
                            start_date,
                            end_date,
                            group_by_service=True,
                        )
                        if usage_summary is None:
                            rows = await adapter.get_cost_and_usage(
                                start_dt,
                                end_dt,
                                granularity="DAILY",
                            )
                            usage_summary = self._build_usage_summary_from_rows(
                                rows=rows,
                                tenant_id=str(tenant.id),
                                provider=provider,
                                start_date=start_date,
                                end_date=end_date,
                            )

                        if not usage_summary or not usage_summary.records:
                            return

                        # 1. LLM Analysis
                        analysis_result = await analyzer.analyze(
                            usage_summary,
                            tenant_id=tenant.id,
                            db=db,
                            provider=provider,
                        )
                        if isinstance(analysis_result, dict):
                            try:
                                from app.shared.llm.guardrails import FinOpsAnalysisResult

                                parsed_result = FinOpsAnalysisResult(**analysis_result)
                                await savings_processor.process_recommendations(
                                    db,
                                    tenant.id,
                                    parsed_result,
                                    provider=provider,
                                    connection_id=getattr(conn, "id", None),
                                )
                            except Exception as savings_exc:
                                logger.error(
                                    "savings_autopilot_failed",
                                    tenant_id=str(tenant.id),
                                    provider=provider,
                                    connection_id=str(getattr(conn, "id", "unknown")),
                                    error=str(savings_exc),
                                )

                        # 2. Carbon Calculation
                        calc_region = resolve_connection_region(conn)
                        normalized_rows = [
                            {
                                "cost_usd": float(record.amount),
                                "service": record.service,
                                "provider": provider,
                            }
                            for record in usage_summary.records
                        ]
                        carbon_result = carbon_calc.calculate_from_costs(
                            normalized_rows,
                            region=calc_region,
                            provider=provider,
                        )

                        # 3. Zombie Detection for supported providers.
                        zombie_result: Dict[str, Any] = {}
                        if provider in {
                            "aws",
                            "azure",
                            "gcp",
                            "saas",
                            "license",
                            "platform",
                            "hybrid",
                        }:
                            try:
                                detector = ZombieDetectorFactory.get_detector(
                                    conn,
                                    region=calc_region,
                                    db=db,
                                )
                                zombie_result = await detector.scan_all()
                            except Exception as zombie_exc:
                                logger.warning(
                                    "tenant_zombie_scan_skipped",
                                    tenant_id=str(tenant.id),
                                    provider=provider,
                                    connection_id=str(getattr(conn, "id", "unknown")),
                                    error=str(zombie_exc),
                                )
                        else:
                            logger.info(
                                "tenant_zombie_scan_not_supported",
                                tenant_id=str(tenant.id),
                                provider=provider,
                            )

                        # 4. Notify if enabled in tenant settings
                        if notif_settings and notif_settings.slack_enabled:
                            if notif_settings.digest_schedule in ["daily", "weekly"]:
                                from app.modules.notifications.domain import (
                                    get_tenant_slack_service,
                                )

                                slack = await get_tenant_slack_service(db, tenant.id)
                                if not slack:
                                    logger.info(
                                        "tenant_digest_skipped_slack_not_configured",
                                        tenant_id=str(tenant.id),
                                    )
                                else:
                                    zombie_count = sum(
                                        len(items)
                                        for items in zombie_result.values()
                                        if isinstance(items, list)
                                    )
                                    total_cost = float(usage_summary.total_cost)

                                    await slack.send_digest(
                                        {
                                            "tenant_name": tenant.name,
                                            "total_cost": total_cost,
                                            "carbon_kg": carbon_result.get(
                                                "total_co2_kg", 0
                                            ),
                                            "zombie_count": zombie_count,
                                            "period": f"{start_date.isoformat()} - {end_date.isoformat()}",
                                        }
                                    )

                    # BE-SCHED-2: Analysis Timeout Protection (SEC-05)
                    # We use a 10-minute timeout per connection to prevent job hangs
                    # while allowing enough time for large-scale CUR processing.
                    async with asyncio.timeout(600):
                        await _run_analysis()

                except (asyncio.TimeoutError, TimeoutError):
                    logger.error(
                        "tenant_analysis_timeout",
                        tenant_id=str(tenant.id),
                        connection_id=str(conn.id),
                    )
                except Exception as e:
                    logger.error(
                        "tenant_connection_failed",
                        tenant_id=str(tenant.id),
                        connection_id=str(conn.id),
                        error=str(e),
                    )

        except Exception as e:
            logger.error(
                "tenant_processing_failed", tenant_id=str(tenant.id), error=str(e)
            )


class SavingsProcessor:
    """Executes high-confidence, low-risk autonomous savings."""

    async def process_recommendations(
        self,
        db: AsyncSession,
        tenant_id: UUID,
        analysis_result: "FinOpsAnalysisResult",
        *,
        provider: str,
        connection_id: Optional["UUID"] = None,
    ) -> None:
        """Filters for 'autonomous_ready' items and executes them."""
        from uuid import UUID as PyUUID
        from app.modules.optimization.domain.remediation import RemediationService
        from app.shared.core.config import get_settings
        from app.models.remediation import RemediationAction

        remediation = RemediationService(db)
        settings = get_settings()
        provider_norm = normalize_provider(provider)
        if provider_norm not in SUPPORTED_PROVIDERS:
            logger.warning(
                "autonomous_savings_skipped_unsupported_provider",
                tenant_id=str(tenant_id),
                provider=str(provider or ""),
            )
            return

        # System User ID for autonomous actions
        system_user_id = PyUUID("00000000-0000-0000-0000-000000000000")

        # Allow only low-risk actions for autopilot execution
        safe_actions = {
            RemediationAction.STOP_INSTANCE,
            RemediationAction.RESIZE_INSTANCE,
            RemediationAction.STOP_RDS_INSTANCE,
            RemediationAction.DEALLOCATE_AZURE_VM,
            RemediationAction.STOP_GCP_INSTANCE,
        }

        for rec in analysis_result.recommendations:
            confidence_raw = (rec.confidence or "").strip().lower()
            confidence_score = None
            try:
                confidence_score = float(confidence_raw)
            except ValueError:
                pass

            is_high_confidence = confidence_raw == "high" or (
                confidence_score is not None and confidence_score >= 0.9
            )

            if rec.autonomous_ready and is_high_confidence:
                logger.info(
                    "executing_autonomous_savings",
                    tenant_id=str(tenant_id),
                    resource=rec.resource,
                    action=rec.action,
                )

                action_enum = self._map_action_to_enum(rec.action)
                if not action_enum:
                    logger.warning("unsupported_autonomous_action", action=rec.action)
                    continue

                try:
                    # Clean currency string
                    savings_val = 0.0
                    if rec.estimated_savings:
                        savings_str = (
                            rec.estimated_savings.replace("$", "")
                            .replace("/month", "")
                            .strip()
                        )
                        try:
                            savings_val = float(savings_str)
                        except ValueError:
                            pass

                    request = await remediation.create_request(
                        tenant_id=tenant_id,
                        user_id=system_user_id,
                        resource_id=rec.resource,
                        resource_type=rec.resource_type or "unknown",
                        action=action_enum,
                        estimated_savings=savings_val,
                        provider=provider_norm,
                        connection_id=connection_id,
                        explainability_notes=f"Savings Autopilot: {rec.action}. High confidence, low risk.",
                    )

                    if action_enum in safe_actions:
                        # Auto-approve & Execute for safe actions only
                        await remediation.approve(
                            request.id,
                            tenant_id,
                            system_user_id,
                            notes="AUTO_APPROVED: Savings Autopilot",
                        )
                        execution_result = await remediation.execute(
                            request.id,
                            tenant_id,
                            bypass_grace_period=settings.AUTOPILOT_BYPASS_GRACE_PERIOD,
                        )
                        result_status = (
                            execution_result.status.value
                            if hasattr(execution_result.status, "value")
                            else str(execution_result.status)
                        )
                        if result_status == "failed":
                            execution_error = (
                                getattr(execution_result, "execution_error", None)
                                or "Autonomous remediation execution failed."
                            )
                            raise ValueError(execution_error)
                        if result_status != "completed":
                            logger.info(
                                "autonomous_savings_deferred",
                                tenant_id=str(tenant_id),
                                request_id=str(request.id),
                                status=result_status,
                            )
                            continue
                    else:
                        # Never auto-execute destructive actions; leave for human review
                        logger.warning(
                            "autonomous_action_requires_review",
                            tenant_id=str(tenant_id),
                            request_id=str(request.id),
                            action=action_enum.value,
                        )

                    logger.info(
                        "autonomous_savings_completed",
                        tenant_id=str(tenant_id),
                        request_id=str(request.id),
                    )
                except Exception as e:
                    logger.error(
                        "autonomous_savings_execution_failed",
                        resource=rec.resource,
                        error=str(e),
                    )

    def _map_action_to_enum(self, action_str: str) -> "Optional[RemediationAction]":
        from app.models.remediation import RemediationAction

        s = action_str.lower()
        if "deallocate" in s and "azure" in s:
            return RemediationAction.DEALLOCATE_AZURE_VM
        if "stop gcp instance" in s or "stop compute engine" in s:
            return RemediationAction.STOP_GCP_INSTANCE
        if "delete volume" in s:
            return RemediationAction.DELETE_VOLUME
        if "stop instance" in s:
            return RemediationAction.STOP_INSTANCE
        if "terminate instance" in s:
            return RemediationAction.TERMINATE_INSTANCE
        if "resize" in s:
            return RemediationAction.RESIZE_INSTANCE
        if "delete snapshot" in s:
            return RemediationAction.DELETE_SNAPSHOT
        if "release elastic ip" in s:
            return RemediationAction.RELEASE_ELASTIC_IP
        if "stop rds" in s:
            return RemediationAction.STOP_RDS_INSTANCE
        if "delete rds" in s:
            return RemediationAction.DELETE_RDS_INSTANCE
        if "revoke github seat" in s:
            return RemediationAction.REVOKE_GITHUB_SEAT
        if "reclaim license" in s or "reclaim seat" in s:
            return RemediationAction.RECLAIM_LICENSE_SEAT
        if "manual review" in s:
            return RemediationAction.MANUAL_REVIEW
        return None
