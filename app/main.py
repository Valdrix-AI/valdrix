from datetime import date
from typing import List, Dict, Any, Annotated
from fastapi import FastAPI, Depends, Query, Header, HTTPException
from app.core.config import get_settings
from app.core.logging import setup_logging
import structlog
from app.services.adapters.base import CostAdapter
from app.services.adapters.aws import AWSAdapter
from app.services.llm.factory import LLMFactory
from app.services.llm.analyzer import FinOpsAnalyzer
from app.services.scheduler import SchedulerService
from prometheus_fastapi_instrumentator import Instrumentator
from contextlib import asynccontextmanager
import secrets
from app.core.auth import get_current_user, CurrentUser
from app.api.v1.onboard import router as onboard_router



# Configure logging
setup_logging()

# Get logger
logger = structlog.get_logger()

# Dependency Factory
def get_cost_adapter() -> CostAdapter:
  return AWSAdapter()

# This runs BEFORE the app starts (setup) and AFTER it stops (teardown).
@asynccontextmanager
async def lifespan(app: FastAPI):
  # Setup: Connect to DB, load AI model, etc
  settings = get_settings()
  logger.info(f"Loading {settings.APP_NAME} config...")

  # Initialize scheduler
  scheduler = SchedulerService()
  scheduler.start()
  app.state.scheduler = scheduler # Store scheduler in app state for health checks

  yield

  # Teardown: Disconnect from DB, etc
  logger.info(f"Shutting down {settings.APP_NAME}...")
  # Stop scheduler
  scheduler.stop()

# 2. Create the app instance
settings = get_settings()

app = FastAPI(
  title=settings.APP_NAME,
  version=settings.VERSION,
  lifespan=lifespan)

# Initialize Prometheus Metrics
Instrumentator().instrument(app).expose(app)

# Include onboard router
app.include_router(onboard_router)

# 3. Health Check (The Heartbeat of the app)
# Every K8s pod needs a health check endpoint to prove it's alive
@app.get("/health")
async def health_check():
  scheduler_status = app.state.scheduler.get_status()
  return {
    "status": "active",
    "app": settings.APP_NAME,
    "version": settings.VERSION,
    "scheduler": scheduler_status,
  }

@app.get("/costs", response_model=List[Dict[str, Any]])
async def get_costs(
  start_date: date,
  end_date: date,
  adapter: Annotated[CostAdapter, Depends(get_cost_adapter)],
  user: Annotated[CurrentUser, Depends(get_current_user)]
):
  """
  Retrieves daily cloud costs for a specified date range.

  This endpoint uses the `CostAdapter` dependency (Strategy Pattern) to fetch data from the 
  configured cloud provider (currently AWS).

  Args:
      start_date (date): The start date for the cost period (inclusive).
      end_date (date): The end date for the cost period (exclusive).
      adapter (CostAdapter): The injected cloud provider adapter.
      user (CurrentUser): The authenticated user.

  Returns:
      List[Dict[str, Any]]: A list of daily cost records.
  """
  logger.info("fetching_costs", start=start_date, end=end_date, user_id=str(user.id))
  return await adapter.get_daily_costs(start_date, end_date)

# Dependency Factory for LLM
def get_llm_provider() -> str:
  settings = get_settings()
  return settings.LLM_PROVIDER

def get_analyzer(provider: str = Depends(get_llm_provider)) -> FinOpsAnalyzer:
  llm = LLMFactory.create(provider)
  return FinOpsAnalyzer(llm)

@app.get("/analyze")
async def analyze_costs(
    start_date: date,
    end_date: date,
    adapter: Annotated[CostAdapter, Depends(get_cost_adapter)],
    analyzer: Annotated[FinOpsAnalyzer, Depends(get_analyzer)],
    user: Annotated[CurrentUser, Depends(get_current_user)]
):
    """
    Analyzes cloud costs using GenAI to identify anomalies and savings.

    This is the core "Sentinel" feature. It:
    1. Fetches raw cost data using the `CostAdapter`.
    2. Feeds the data into the `FinOpsAnalyzer` (LLM).
    3. Returns structured insights (anomalies, zombie resources, etc.).

    Args:
        start_date (date): Start of analysis period.
        end_date (date): End of analysis period.
        adapter (CostAdapter): Injected source of cost inputs.
        analyzer (FinOpsAnalyzer): Injected AI analysis engine.

    Returns:
        dict: A JSON object containing AI-generated insights.
    """
    logger.info("starting_sentinel_analysis", start=start_date, end=end_date)
    
    # Step 1: Get cost data
    cost_data = await adapter.get_daily_costs(start_date, end_date)
    
    # Step 2: Analyze with AI
    insights = await analyzer.analyze(cost_data)
    
    return {"analysis": insights}

@app.post("/admin/trigger-analysis")
async def trigger_analysis(x_admin_key: str = Header(..., alias="X-Admin-Key")):
    """
    Manually trigger a scheduled analysis job.
    Requires X-Admin-Key header matching ADMIN_API_KEY environment variable.
    """
    settings = get_settings()
    
    if not settings.ADMIN_API_KEY:
        logger.error("admin_key_not_configured")
        raise HTTPException(
            status_code=503, 
            detail="Admin endpoint not configured. Set ADMIN_API_KEY."
        )
    
    if not secrets.compare_digest(x_admin_key, settings.ADMIN_API_KEY):
        logger.warning("admin_auth_failed", provided_key_prefix=x_admin_key[:4] + "***")
        raise HTTPException(status_code=403, detail="Forbidden")
    
    logger.info("manual_trigger_requested")
    await app.state.scheduler.daily_analysis_job()
    return {"status": "triggered", "message": "Daily analysis job executed."}