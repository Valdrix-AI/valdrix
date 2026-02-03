import os
import sys
from unittest.mock import MagicMock
import pytest

# Ensure all models are registered for SQLAlchemy relationship mapping

# Set TESTING environment variable for tests
os.environ["TESTING"] = "true"

# GLOBAL MOCKING FOR PROBLEM ENVIRONMENT
# Removed global mocks for pandas, numpy, etc. as they are installed in the environment.
# Only mock if strictly necessary and missing.
if "tiktoken" not in sys.modules:
    sys.modules["tiktoken"] = MagicMock()

# Global tenacity mock to prevent long waits and recursion issues
import tenacity
def mock_retry(*args, **kwargs):
    def decorator(f):
        return f
    return decorator
tenacity.retry = mock_retry

@pytest.fixture(autouse=True)
def set_testing_env():
    """Ensure TESTING is set for all tests"""
    os.environ["TESTING"] = "true"
    yield

