import sys
from unittest.mock import MagicMock

# GLOBAL MOCKING FOR PROBLEM ENVIRONMENT
# We mock these BEFORE any other imports to prevent C-extension failures
if "pandas" not in sys.modules:
    sys.modules["pandas"] = MagicMock()
if "numpy" not in sys.modules:
    sys.modules["numpy"] = MagicMock()
if "prophet" not in sys.modules:
    sys.modules["prophet"] = MagicMock()
if "tiktoken" not in sys.modules:
    sys.modules["tiktoken"] = MagicMock()

# Global tenacity mock to prevent long waits and recursion issues
import tenacity
def mock_retry(*args, **kwargs):
    def decorator(f):
        return f
    return decorator
tenacity.retry = mock_retry
