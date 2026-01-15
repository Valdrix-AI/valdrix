import structlog
from datetime import date
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
                    # Use MultiTenant adapter
                    adapter = MultiTenantAWSAdapter(conn)
                    costs = await adapter.get_daily_costs(start_date, end_date)

                    if not costs:
                        continue

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

                except Exception as e:
                    logger.error("tenant_connection_failed", tenant_id=str(tenant.id), connection_id=str(conn.id), error=str(e))

        except Exception as e:
            logger.error("tenant_processing_failed", tenant_id=str(tenant.id), error=str(e))
