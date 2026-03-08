from __future__ import annotations

import httpx

from scripts.verify_pending_approval_flow import REQUEST_TIMEOUT, _build_client


def test_pending_approval_flow_uses_bounded_client_timeout() -> None:
    client = _build_client()
    assert isinstance(client.timeout, httpx.Timeout)
    assert client.timeout.connect == REQUEST_TIMEOUT.connect
    assert client.timeout.read == REQUEST_TIMEOUT.read
    assert client.timeout.write == REQUEST_TIMEOUT.write
    assert client.timeout.pool == REQUEST_TIMEOUT.pool
    client.close()
