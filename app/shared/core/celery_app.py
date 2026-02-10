from celery import Celery
from app.shared.core.config import get_settings

settings = get_settings()

# Use Redis URL from settings, default to localhost if not set (development)
broker_url = settings.REDIS_URL or "redis://localhost:6379/0"
backend_url = settings.REDIS_URL or "redis://localhost:6379/0"

# Initialize Celery app
celery_app = Celery(
    "valdrix_worker",
    broker=broker_url,
    backend=backend_url,
    include=["app.tasks.scheduler_tasks"]
)

# Configuration
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Worker settings
    worker_prefetch_multiplier=1,  # Prevent worker from hogging tasks (fair dispatch)
    task_acks_late=True,           # Retry if worker crashes mid-task
    task_reject_on_worker_lost=True,
    # Connection settings - CRITICAL: prevents indefinite blocking during startup
    broker_connection_timeout=5,    # 5 second timeout for broker connection
    broker_connection_retry=True,   # Enable retries
    broker_connection_max_retries=3,  # Max 3 retries
    broker_connection_retry_on_startup=True,  # Retry briefly on startup instead of failing immediately
)


# BE-TEST-2: Support eager execution for unit tests without Redis
if settings.TESTING:
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        broker_url="memory://",
        result_backend="rpc://",
        broker_connection_retry_on_startup=False,  # Never block in tests
    )

if __name__ == "__main__":
    celery_app.start()
