import psutil
from typing import Any


def safe_cpu_percent() -> float:
    """Non-blocking CPU percent sample for async-safe health checks."""
    return psutil.cpu_percent(interval=None)


def safe_virtual_memory() -> Any:
    """Wrapper for virtual memory sampling."""
    return psutil.virtual_memory()


def safe_disk_usage(path: str = "/") -> Any:
    """Wrapper for disk usage sampling."""
    return psutil.disk_usage(path)
