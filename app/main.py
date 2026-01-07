from datetime import date
from typing import List, Dict, Any, Annotated
from fastapi import FastAPI, Depends, Query
from app.core.config import get_settings
from app.core.logging import setup_logging
import structlog
from app.services.adapters.base import CostAdapter
from app.services.adapters.aws import AWSAdapter
from app.services.llm.factory import LLMFactory
from app.services.llm.analyzer import FinOpsAnalyzer
from contextlib import asynccontextmanager


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

  yield

  # Teardown: Disconnect from DB, etc
  logger.info(f"Shutting down {settings.APP_NAME}...")

# 2. Create the app instance
settings = get_settings()
app = FastAPI(
  title=settings.APP_NAME,
  version=settings.VERSION,
  lifespan=lifespan)

# 3. Health Check (The Heartbeat of the app)
# Every K8s pod needs a health check endpoint to prove it's alive
@app.get("/health")
async def health_check():
  return {
    "status": "active",
    "app": settings.APP_NAME,
    "version": settings.VERSION,    
  }

@app.get("/costs", response_model=List[Dict[str, Any]])
async def get_costs(
  start_date: date,
  end_date: date,
  adapter: Annotated[CostAdapter, Depends(get_cost_adapter)]
):
  logger.info("fecthing_costs", start=start_date, end=end_date)
  return await adapter.get_daily_costs(start_date, end_date)

# Dependency Factory for LLM
def get_llm_provider() -> str:
    # You can make this configurable via settings later
    return "groq"  # or "openai", "claude", "google"

def get_analyzer(provider: str = Depends(get_llm_provider)) -> FinOpsAnalyzer:
    llm = LLMFactory.create(provider)
    return FinOpsAnalyzer(llm)

@app.get("/analyze")
async def analyze_costs(
    start_date: date,
    end_date: date,
    adapter: Annotated[CostAdapter, Depends(get_cost_adapter)],
    analyzer: Annotated[FinOpsAnalyzer, Depends(get_analyzer)]
):
    """
    Fetches cloud costs and analyzes them using AI.
    This is the "Sentinel" core feature.
    """
    logger.info("starting_sentinel_analysis", start=start_date, end=end_date)
    
    # Step 1: Get cost data
    cost_data = await adapter.get_daily_costs(start_date, end_date)
    
    # Step 2: Analyze with AI
    insights = await analyzer.analyze(cost_data)
    
    return {"analysis": insights}