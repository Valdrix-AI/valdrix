import structlog
from datetime import date
from uuid import UUID
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.tenant import Tenant
from app.services.llm.factory import LLMFactory
from app.services.llm.analyzer import FinOpsAnalyzer
from app.services.carbon.calculator import CarbonCalculator
from app.services.zombies.detector import ZombieDetector
from app.services.adapters.aws_multitenant import MultiTenantAWSAdapter
from app.core.config import get_settings

logger = structlog.get_logger()

class AnalysisProcessor:
    """Handles the heavy lifting of analyzing a single tenant's cloud usage."""

    def __init__(self):
        self.settings = get_settings()

    async def process_tenant(self, db: AsyncSession, tenant: Tenant, start_date: date, end_date: date):
        """Process a single tenant's analysis."""
        try:
            logger.info("processing_tenant", tenant_id=str(tenant.id), name=tenant.name)

            # 1. Use pre-loaded Notification Settings (Avoids N+1 query)
            notif_settings = tenant.notification_settings

            # 2. Use pre-loaded AWS connections (Avoids N+1 query)
            connections = tenant.aws_connections

            if not connections:
                logger.info("tenant_no_connections", tenant_id=str(tenant.id))
                return

            llm = LLMFactory.create(self.settings.LLM_PROVIDER)
            analyzer = FinOpsAnalyzer(llm)
            carbon_calc = CarbonCalculator()

            for conn in connections:
                try:
                    # BE-SCHED-2: Analysis Timeout Protection (SEC-05)
                    # Use a generous 5-minute timeout per connection to prevent job hangs
                    import asyncio
                    async def _run_analysis():
                        # Use MultiTenant adapter
                        adapter = MultiTenantAWSAdapter(conn)
                        costs = await adapter.get_daily_costs(start_date, end_date)

                        if not costs:
                            return

                        # 1. LLM Analysis
                        await analyzer.analyze(costs, tenant_id=tenant.id, db=db)

                        # 2. Carbon Calculation
                        carbon_result = carbon_calc.calculate_from_costs(costs, region=conn.region)

                        # 3. Zombie Detection
                        creds = await adapter.get_credentials()
                        detector = ZombieDetector(region=conn.region, credentials=creds)
                        zombie_result = await detector.scan_all()

                        # 4. Notify if enabled in settings
                        if notif_settings and notif_settings.slack_enabled:
                            if notif_settings.digest_schedule in ["daily", "weekly"]:
                                settings = get_settings()
                                if settings.SLACK_BOT_TOKEN and settings.SLACK_CHANNEL_ID:
                                    channel = notif_settings.slack_channel_override or settings.SLACK_CHANNEL_ID

                                    from app.services.notifications import SlackService
                                    slack = SlackService(settings.SLACK_BOT_TOKEN, channel)

                                    zombie_count = sum(len(items) for items in zombie_result.values() if isinstance(items, list))
                                    total_cost = sum(
                                        float(day.get("Total", {}).get("UnblendedCost", {}).get("Amount", 0))
                                        for day in costs
                                    )

                                    await slack.send_digest({
                                        "tenant_name": tenant.name,
                                        "total_cost": total_cost,
                                        "carbon_kg": carbon_result.get("total_co2_kg", 0),
                                        "zombie_count": zombie_count,
                                        "period": f"{start_date.isoformat()} - {end_date.isoformat()}"
                                    })

                    await asyncio.wait_for(_run_analysis(), timeout=300)

                except asyncio.TimeoutError:
                    logger.error("tenant_analysis_timeout", tenant_id=str(tenant.id), connection_id=str(conn.id))
                except Exception as e:
                    logger.error("tenant_connection_failed", tenant_id=str(tenant.id), connection_id=str(conn.id), error=str(e))

            # 3. New: Savings Autopilot (Phase 42)
            # Fetch latest analysis result and execute autonomous savings
            try:
                from app.models.analysis import AnalysisResult
                res_obj = await db.execute(
                    select(AnalysisResult)
                    .where(AnalysisResult.tenant_id == tenant.id)
                    .order_by(AnalysisResult.created_at.desc())
                    .limit(1)
                )
                latest_analysis = res_obj.scalar_one_or_none()
                if latest_analysis and latest_analysis.raw_result:
                    from app.services.llm.guardrails import FinOpsAnalysisResult
                    parsed_result = FinOpsAnalysisResult(**latest_analysis.raw_result)
                    
                    savings_processor = SavingsProcessor()
                    await savings_processor.process_recommendations(db, tenant.id, parsed_result)
            except Exception as e:
                logger.error("savings_autopilot_failed", tenant_id=str(tenant.id), error=str(e))

        except Exception as e:
            logger.error("tenant_processing_failed", tenant_id=str(tenant.id), error=str(e))

class SavingsProcessor:
    """Executes high-confidence, low-risk autonomous savings."""

    async def process_recommendations(self, db: AsyncSession, tenant_id: UUID, analysis_result: "FinOpsAnalysisResult"):
        """Filters for 'autonomous_ready' items and executes them."""
        from uuid import UUID as PyUUID
        from app.services.zombies.remediation_service import RemediationService
        from app.models.remediation import RemediationAction
        
        remediation = RemediationService(db)
        # System User ID for autonomous actions
        system_user_id = PyUUID("00000000-0000-0000-0000-000000000000")
        
        for rec in analysis_result.recommendations:
            if rec.autonomous_ready and rec.confidence.lower() == "high":
                logger.info("executing_autonomous_savings", 
                            tenant_id=str(tenant_id), 
                            resource=rec.resource, 
                            action=rec.action)
                
                action_enum = self._map_action_to_enum(rec.action)
                if not action_enum:
                    logger.warning("unsupported_autonomous_action", action=rec.action)
                    continue
                
                try:
                    # Clean currency string
                    savings_val = 0.0
                    if rec.estimated_savings:
                        savings_str = rec.estimated_savings.replace('$', '').replace('/month', '').strip()
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
                        explainability_notes=f"Savings Autopilot: {rec.action}. High confidence, low risk."
                    )
                    
                    # Auto-approve & Execute immediately
                    await remediation.approve(request.id, tenant_id, system_user_id, notes="AUTO_APPROVED: Savings Autopilot")
                    await remediation.execute(request.id, tenant_id, bypass_grace_period=True)
                    
                    logger.info("autonomous_savings_completed", 
                                tenant_id=str(tenant_id), 
                                request_id=str(request.id))
                except Exception as e:
                    logger.error("autonomous_savings_execution_failed", resource=rec.resource, error=str(e))

    def _map_action_to_enum(self, action_str: str) -> "Optional[RemediationAction]":
        from app.models.remediation import RemediationAction
        s = action_str.lower()
        if "delete volume" in s: return RemediationAction.DELETE_VOLUME
        if "stop instance" in s: return RemediationAction.STOP_INSTANCE
        if "terminate instance" in s: return RemediationAction.TERMINATE_INSTANCE
        if "resize" in s: return RemediationAction.RESIZE_INSTANCE
        if "delete snapshot" in s: return RemediationAction.DELETE_SNAPSHOT
        if "release elastic ip" in s: return RemediationAction.RELEASE_ELASTIC_IP
        if "stop rds" in s: return RemediationAction.STOP_RDS_INSTANCE
        if "delete rds" in s: return RemediationAction.DELETE_RDS_INSTANCE
        return None
