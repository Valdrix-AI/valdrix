from __future__ import annotations

import ipaddress
from typing import Any
from urllib.parse import urlparse


def _is_private_or_link_local(host: str) -> bool:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False

    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
    )


def _host_allowed(host: str, allowlist: set[str]) -> bool:
    if not allowlist:
        return False
    if host in allowlist:
        return True
    return any(host.endswith(f".{allowed}") for allowed in allowlist)


def sanitize_webhook_headers(headers: dict[str, Any]) -> dict[str, str]:
    sanitized: dict[str, str] = {}
    if not isinstance(headers, dict):
        return {"Content-Type": "application/json"}

    for key, value in headers.items():
        if not isinstance(key, str) or not isinstance(value, str):
            continue
        key_lower = key.strip().lower()
        if key_lower == "content-type":
            content_type = value.split(";")[0].strip().lower()
            if content_type != "application/json":
                raise ValueError(
                    "content-type must be application/json for webhook delivery"
                )
            sanitized["Content-Type"] = "application/json"
        elif key_lower in {"authorization", "user-agent"} or key_lower.startswith("x-"):
            sanitized[key] = value

    if "Content-Type" not in sanitized:
        sanitized["Content-Type"] = "application/json"
    return sanitized


def validate_webhook_url(
    *,
    url: str,
    allowlist: set[str],
    require_https: bool,
    block_private_ips: bool,
) -> None:
    parsed = urlparse(url)
    if require_https and parsed.scheme.lower() != "https":
        raise ValueError("Webhook URL must use HTTPS")
    if not parsed.hostname:
        raise ValueError("Webhook URL must include a host")
    if parsed.username or parsed.password:
        raise ValueError("Webhook URL must not include credentials")

    host = parsed.hostname.lower()
    if block_private_ips and (host in {"localhost"} or host.endswith(".local")):
        raise ValueError("Webhook URL must not target local hostnames")
    if block_private_ips and _is_private_or_link_local(host):
        raise ValueError("Webhook URL must not target private or link-local addresses")
    if not _host_allowed(host, allowlist):
        raise ValueError("Webhook URL host is not in allowlist")


__all__ = ["sanitize_webhook_headers", "validate_webhook_url"]
