from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture
def app() -> SimpleNamespace:
    """Lightweight app fixture for supply-chain tests that do not require FastAPI bootstrap."""
    return SimpleNamespace(dependency_overrides={})
