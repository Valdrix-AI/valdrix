from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import date, timedelta
import time
import structlog
from prometheus_client import Counter, Histogram
from app.services.adapters.aws import AWSAdapter
from app.services.llm.factory import LLMFactory
from app.services.llm.analyzer import FinOpsAnalyzer
from app.core.config import get_settings

logger = structlog.get_logger()

# Prometheus Metrics
SCHEDULER_JOB_RUNS = Counter(
    "cloudsentinel_scheduler_job_runs_total",
    "Total number of scheduled job runs",
    ["job_name", "status"]  # status: success, failure
)

SCHEDULER_JOB_DURATION = Histogram(
    "cloudsentinel_scheduler_job_duration_seconds",
    "Duration of scheduled jobs in seconds",
    ["job_name"],
    buckets=[1, 5, 10, 30, 60, 120, 300, 600]  # Up to 10 minutes
)


class SchedulerService:
    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.settings = get_settings()
        self._last_run_success: bool | None = None
        self._last_run_time: str | None = None

    async def daily_analysis_job(self):
        """
        The actual job that runs every morning.
        Fetches yesterday's costs -> Analyzes -> Logs Results.
        """
        job_name = "daily_finops_scan"
        start_time = time.time()
        
        logger.info("scheduler_job_starting", job=job_name)

        # 1. Calculate Date Range
        today = date.today()
        yesterday = today - timedelta(days=1)

        # 2. Initialize Components
        adapter = AWSAdapter()
        llm = LLMFactory.create(self.settings.LLM_PROVIDER)
        analyzer = FinOpsAnalyzer(llm)

        # 3. Execute Workflow
        try:
            costs = await adapter.get_daily_costs(yesterday, today)
            if not costs:
                logger.warning("scheduler_job_no_data", job=job_name)
                SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="success").inc()
                self._last_run_success = True
                self._last_run_time = today.isoformat()
                return

            analysis = await analyzer.analyze(costs)

            # TODO: Send to Slack/Email

            # Log success with key metrics, not truncated text
            logger.info(
                "scheduler_job_complete",
                job=job_name,
                cost_records=len(costs),
                analysis_length=len(analysis)
            )
            
            SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="success").inc()
            self._last_run_success = True
            self._last_run_time = today.isoformat()

        except Exception as e:
            logger.error("scheduler_job_failed", job=job_name, error=str(e))
            SCHEDULER_JOB_RUNS.labels(job_name=job_name, status="failure").inc()
            self._last_run_success = False
            self._last_run_time = today.isoformat()
            raise  # Re-raise so APScheduler knows it failed

        finally:
            duration = time.time() - start_time
            SCHEDULER_JOB_DURATION.labels(job_name=job_name).observe(duration)
            logger.info("scheduler_job_duration", job=job_name, seconds=round(duration, 2))

    async def send_daily_slack_digest(self):
        """Send daily cost digest to Slack."""
        job_name = "slack_daily_digest"
        logger.info("scheduler_job_starting", job=job_name)
    
        try:
            # Skip if Slack not configured
            if not self.settings.SLACK_BOT_TOKEN or not self.settings.SLACK_CHANNEL_ID:
                logger.info("slack_not_configured_skipping")
                return
            
            # 1. Fetch yesterday's data
            today = date.today()
            yesterday = today - timedelta(days=1)
            adapter = AWSAdapter()
            
            # Get costs
            costs = await adapter.get_daily_costs(yesterday, today)
            total_cost = sum(c.get("amount", 0) for c in costs) if costs else 0
            
            # 2. Send digest
            from app.services.notifications import SlackService
            slack = SlackService(self.settings.SLACK_BOT_TOKEN, self.settings.SLACK_CHANNEL_ID)
            
            await slack.send_digest({
                "total_cost": total_cost,
                "carbon_kg": 0,  # TODO: fetch from carbon service
                "zombie_count": 0,  # TODO: fetch from zombie service
                "period": f"{yesterday.isoformat()} - {today.isoformat()}"
            })
            
            logger.info("scheduler_job_complete", job=job_name)
            
        except Exception as e:
            logger.error("scheduler_job_failed", job=job_name, error=str(e))

    def start(self):
        """
        Start the scheduler.
        """
        # Get schedule from settings (with defaults)
        hour = self.settings.SCHEDULER_HOUR
        minute = self.settings.SCHEDULER_MINUTE
        
        trigger = CronTrigger(hour=hour, minute=minute, timezone="UTC")

        self.scheduler.add_job(
            self.daily_analysis_job,
            trigger=trigger,
            id="daily_finops_scan",
            replace_existing=True,
            max_instances=1,  # Prevent overlapping runs
            misfire_grace_time=3600,  # 1 hour grace period for missed jobs
        )
        # Add Slack digest job - runs at 9:00 AM UTC
        self.scheduler.add_job(
            self.send_daily_slack_digest,
            trigger=CronTrigger(hour=9, minute=0, timezone="UTC"),
            id="slack_daily_digest",
            replace_existing=True,
        )
        
        self.scheduler.start()
        logger.info("scheduler_started", schedule=f"{hour:02d}:{minute:02d} UTC")

    def stop(self):
        """
        Stop the scheduler gracefully, waiting for running jobs.
        """
        self.scheduler.shutdown(wait=True)
        logger.info("scheduler_stopped")

    def get_status(self) -> dict:
        """
        Return scheduler status for health checks.
        """
        return {
            "running": self.scheduler.running,
            "last_run_success": self._last_run_success,
            "last_run_time": self._last_run_time,
            "jobs": [job.id for job in self.scheduler.get_jobs()]
        }