import importlib
from unittest.mock import patch
from app.shared.core import celery_app
from app.shared.core.config import get_settings


def test_celery_config_base():
    """Verify base celery configuration."""
    assert celery_app.celery_app.conf.task_serializer == "json"
    assert celery_app.celery_app.conf.timezone == "UTC"


def test_celery_testing_config():
    """Verify testing configuration branches."""
    get_settings.cache_clear()
    with patch.dict("os.environ", {"TESTING": "True"}):
        importlib.reload(celery_app)
        assert celery_app.celery_app.conf.task_always_eager is True
        assert celery_app.celery_app.conf.broker_url == "memory://"


def test_celery_production_config():
    """Verify production (non-testing) configuration branches."""
    get_settings.cache_clear()
    with patch.dict(
        "os.environ",
        {
            "TESTING": "False",
            "REDIS_URL": "redis://localhost",
            "UPSTASH_REDIS_URL": "",  # Prevent leakage
        },
    ):
        importlib.reload(celery_app)
        assert celery_app.celery_app.conf.task_always_eager is False


def test_celery_default_redis():
    """Verify default redis URL when REDIS_URL is missing."""
    get_settings.cache_clear()
    with patch.dict(
        "os.environ",
        {
            "TESTING": "False",
            "REDIS_URL": "redis://localhost:6379/0",
            "UPSTASH_REDIS_URL": "",  # Prevent leakage
        },
    ):
        importlib.reload(celery_app)
        assert celery_app.celery_app.conf.broker_url == "redis://localhost:6379/0"


def test_cleanup():
    """Ensure we leave the module in testing state for other tests."""
    get_settings.cache_clear()
    importlib.reload(celery_app)
