import os
import unittest
from unittest.mock import patch
from app.shared.core.config import Settings

class TestRedisConfig(unittest.TestCase):
    def test_redis_url_construction(self):
        """Test that REDIS_URL is constructed from HOST and PORT if missing."""
        env = {
            "REDIS_HOST": "redis-test",
            "REDIS_PORT": "6380",
            "REDIS_URL": "",
            "SUPABASE_JWT_SECRET": "test_secret_32_chars_long_xxxxxxxx"
        }
        with patch.dict(os.environ, env, clear=True):
            # Pass DEBUG=True to bypass production security checks
            settings = Settings(_env_file=None, DEBUG=True)
            self.assertEqual(settings.REDIS_URL, "redis://redis-test:6380")

    def test_redis_url_precedence(self):
        """Test that explicit REDIS_URL takes precedence."""
        env = {
            "REDIS_HOST": "redis-test",
            "REDIS_PORT": "6380",
            "REDIS_URL": "redis://explicit-host:9999",
            "SUPABASE_JWT_SECRET": "test_secret_32_chars_long_xxxxxxxx"
        }
        with patch.dict(os.environ, env, clear=True):
            settings = Settings(_env_file=None, DEBUG=True)
            self.assertEqual(settings.REDIS_URL, "redis://explicit-host:9999")

if __name__ == "__main__":
    unittest.main()
