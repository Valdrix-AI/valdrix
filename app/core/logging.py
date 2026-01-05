import sys
import structlog
import logging
from app.core.config import get_settings

def setup_logging():
  settings = get_settings()

  # 1. Choose the renderer based on environment
  # If DEBUG=True (Local), use ConsoleRenderer (Colors!)
  # If DEBUG=False (Prod), use JSONRenderer (Machine readable)
  if settings.DEBUG:
    renderer = structlog.dev.ConsoleRenderer()
    min_level = logging.DEBUG
  else:
    renderer = structlog.processors.JSONRenderer()
    min_level = logging.INFO

  # 2. Configure the "Processors" (The Middleware Pipeline for Logs)
  processors = [
    structlog.contextvars.merge_contextvars, # Support async context
    structlog.processors.add_log_level,      # Add "level": "info"
    structlog.processors.TimeStamper(fmt="iso"), # Add "timestamp": "2026..."
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,    # Render exceptions nicely
    renderer
  ]

  # 3. Configure the logger or apply the configuration
  structlog.configure(
    processors=processors,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
  )
  
  # 4. Intercept the standard logging (e.g. uvicorn's internal log).
  # This ensure even library logs get formatted as JSON.
  logging.basicConfig(
    format="%(message)s",
    stream=sys.stdout,
    level=min_level,
  )


