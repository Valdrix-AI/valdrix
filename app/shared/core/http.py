"""
Async HTTP Client Shared Infrastructure (2026 Standards)

Ensures singleton httpx.AsyncClient usage across both FastAPI lifespan
and background workers to prevent socket exhaustion and optimize latency.
"""

import inspect
from typing import Optional
import httpx
import structlog

logger = structlog.get_logger()

# Singleton instances
_client: Optional[httpx.AsyncClient] = None
_insecure_client: Optional[httpx.AsyncClient] = None


def get_http_client(
    verify: bool = True, timeout: Optional[float] = None
) -> httpx.AsyncClient:
    """
    Returns a global shared httpx.AsyncClient.
    Maintains separate pools for secure and insecure (verify=False) connections.
    """
    global _client, _insecure_client

    target = _client if verify else _insecure_client

    if target is None:
        logger.warning(
            "http_client_lazy_initialized",
            verify=verify,
            msg="Client was not pre-initialized",
        )
        new_client = httpx.AsyncClient(
            timeout=httpx.Timeout(timeout or 20.0, connect=10.0),
            limits=httpx.Limits(max_connections=100, max_keepalive_connections=20),
            http2=True,
            verify=verify,
        )
        if verify:
            _client = new_client
        else:
            _insecure_client = new_client
        return new_client

    return target


async def init_http_client() -> None:
    """
    Initializes the global httpx.AsyncClient with 2026 production settings.
    """
    global _client
    if _client is not None:
        logger.warning("http_client_already_initialized")
        return

    _client = httpx.AsyncClient(
        http2=True,  # Mandatory for 2026 performance
        timeout=httpx.Timeout(20.0, connect=10.0),
        limits=httpx.Limits(
            max_connections=500,  # High throughput for concurrent AI/Billing calls
            max_keepalive_connections=50,
            keepalive_expiry=30.0,
        ),
        # Add production headers here if needed
        headers={"User-Agent": "Valdrix-AI/2026.02"},
    )
    logger.info("http_client_initialized", http2=True, max_connections=500)


async def close_http_client() -> None:
    """
    Gracefully shuts down the global client, flushing all connection pools.
    """
    global _client, _insecure_client

    async def _close_one(client: object | None, label: str) -> None:
        if not client:
            return

        close_result = None
        aclose = getattr(client, "aclose", None)
        if callable(aclose):
            close_result = aclose()
        else:
            close = getattr(client, "close", None)
            if callable(close):
                close_result = close()

        if inspect.isawaitable(close_result):
            await close_result

        logger.info("http_client_closed", verify=label == "secure")

    await _close_one(_client, "secure")
    await _close_one(_insecure_client, "insecure")
    _client = None
    _insecure_client = None
