from unittest.mock import patch

from app.shared.core.config import Settings, get_settings

FAKE_KDF_SALT = "S0RGX1NBTFRfRk9SX1RFU1RJTkdfMzJfQllURVNfT0s="


def test_settings_redis_url_fallback_from_host_port():
    with patch.dict("os.environ", {}, clear=True):
        settings = Settings(
            DATABASE_URL="sqlite+aiosqlite:///:memory:",
            SUPABASE_JWT_SECRET="x" * 32,
            ENCRYPTION_KEY="k" * 32,
            CSRF_SECRET_KEY="c" * 32,
            KDF_SALT=FAKE_KDF_SALT,
            REDIS_URL=None,
            REDIS_HOST="localhost",
            REDIS_PORT="6380",
            TESTING=False,
            _env_file=None,
        )

        assert settings.REDIS_URL == "redis://localhost:6380"


def test_get_settings_does_not_mutate_csrf_key():
    class DummySettings:
        CSRF_SECRET_KEY = ""
        ENVIRONMENT = "development"

        @property
        def is_production(self) -> bool:
            return False

    get_settings.cache_clear()
    with patch("app.shared.core.config.Settings", return_value=DummySettings()):
        settings = get_settings()
        assert settings.CSRF_SECRET_KEY == ""


def test_get_settings_caches_singleton():
    class DummySettings:
        CSRF_SECRET_KEY = "x"
        ENVIRONMENT = "development"

        @property
        def is_production(self) -> bool:
            return False

    get_settings.cache_clear()
    with patch("app.shared.core.config.Settings", return_value=DummySettings()):
        first = get_settings()
        second = get_settings()
        assert first is second
