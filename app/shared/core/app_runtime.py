from __future__ import annotations

import os
import tempfile
from typing import Any

import structlog

from app.shared.core.config import get_settings
from app.shared.core.ops_metrics import record_runtime_carbon_emissions


logger = structlog.get_logger()


def _is_test_mode() -> bool:
    settings = get_settings()
    return settings.TESTING or bool(settings.PYTEST_CURRENT_TEST)


def _runtime_data_dir() -> str:
    settings = get_settings()
    configured = str(getattr(settings, "APP_RUNTIME_DATA_DIR", "") or "").strip()
    return configured or os.path.join(tempfile.gettempdir(), "valdrics")


def _api_documentation_allowed() -> bool:
    settings = get_settings()
    if settings.TESTING:
        return True
    if getattr(settings, "is_strict_environment", False):
        return bool(getattr(settings, "EXPOSE_API_DOCUMENTATION_PUBLICLY", False))
    return True


def _load_emissions_tracker() -> Any:
    if _is_test_mode():
        return None
    try:
        import warnings

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                message="The pynvml package is deprecated.*",
                category=FutureWarning,
            )
            from codecarbon import EmissionsTracker as Tracker
        return Tracker
    except (ImportError, AttributeError) as exc:
        logger.warning("emissions_tracker_unavailable", error=str(exc))
        return None


EmissionsTracker = _load_emissions_tracker()
EMISSIONS_TRACKER_STOP_RECOVERABLE_EXCEPTIONS = (
    RuntimeError,
    OSError,
    TypeError,
    ValueError,
    AttributeError,
)


def _stop_emissions_tracker(tracker: Any) -> None:
    if not tracker:
        return
    try:
        emissions_kg = tracker.stop()
    except EMISSIONS_TRACKER_STOP_RECOVERABLE_EXCEPTIONS as exc:  # pragma: no cover
        logger.warning("emissions_tracker_stop_failed", error=str(exc))
        return
    record_runtime_carbon_emissions(emissions_kg)


__all__ = [
    "_api_documentation_allowed",
    "_is_test_mode",
    "_load_emissions_tracker",
    "_runtime_data_dir",
    "_stop_emissions_tracker",
    "EmissionsTracker",
]
