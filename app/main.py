from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.config import get_settings
from app.core.logging import setup_logging
import structlog

# Configure logging
setup_logging()

# Get logger
logger = structlog.get_logger()

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