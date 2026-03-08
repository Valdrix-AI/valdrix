from __future__ import annotations

import ipaddress
from typing import Any

from fastapi import Request

TRUSTED_PROXY_HEADER_RECOVERABLE_EXCEPTIONS = (TypeError, ValueError, AttributeError)
_FORWARDED_PROTO_ALLOWLIST = {"http", "https"}


def _as_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _trusted_proxy_networks(
    settings_obj: Any,
) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
    raw = getattr(settings_obj, "TRUSTED_PROXY_CIDRS", [])
    if isinstance(raw, str):
        cidr_values = [part.strip() for part in raw.split(",") if part.strip()]
    elif isinstance(raw, (list, tuple, set)):
        cidr_values = [str(part).strip() for part in raw if str(part).strip()]
    else:
        cidr_values = []

    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for cidr in cidr_values:
        try:
            networks.append(ipaddress.ip_network(cidr, strict=False))
        except ValueError:
            continue
    return networks


def _fallback_client_host(request: Request) -> str:
    if request.client and request.client.host:
        return str(request.client.host)
    return "unknown"


def _trusted_proxy_context(request: Request, settings_obj: Any) -> tuple[bool, str]:
    fallback = _fallback_client_host(request)
    if not _as_bool(getattr(settings_obj, "TRUST_PROXY_HEADERS", False)):
        return False, fallback

    networks = _trusted_proxy_networks(settings_obj)
    if not networks:
        return False, fallback

    try:
        peer_ip = ipaddress.ip_address(fallback)
    except ValueError:
        return False, fallback

    return any(peer_ip in network for network in networks), fallback


def _trusted_proxy_hops(settings_obj: Any) -> int:
    try:
        trusted_hops = int(getattr(settings_obj, "TRUSTED_PROXY_HOPS", 1))
    except TRUSTED_PROXY_HEADER_RECOVERABLE_EXCEPTIONS:
        trusted_hops = 1
    return min(max(trusted_hops, 1), 5)


def resolve_client_ip(request: Request, *, settings_obj: Any) -> str:
    trusted_proxy, fallback = _trusted_proxy_context(request, settings_obj)
    if not trusted_proxy:
        return fallback

    forwarded_for = str(request.headers.get("x-forwarded-for", "") or "").strip()
    if not forwarded_for:
        return fallback

    valid_ips: list[str] = []
    for raw in forwarded_for.split(","):
        candidate = raw.strip()
        if not candidate:
            continue
        try:
            valid_ips.append(str(ipaddress.ip_address(candidate)))
        except ValueError:
            continue
    if not valid_ips:
        return fallback

    idx = len(valid_ips) - _trusted_proxy_hops(settings_obj)
    if idx < 0:
        return fallback
    if idx >= len(valid_ips):
        return valid_ips[-1]
    return valid_ips[idx]


def resolve_request_scheme(request: Request, *, settings_obj: Any) -> str:
    fallback = str(request.url.scheme or "http").strip().lower() or "http"
    trusted_proxy, _ = _trusted_proxy_context(request, settings_obj)
    if not trusted_proxy:
        return fallback

    forwarded_proto = str(request.headers.get("x-forwarded-proto", "") or "").strip()
    if not forwarded_proto:
        return fallback

    values = [
        value.strip().lower()
        for value in forwarded_proto.split(",")
        if value.strip()
    ]
    if not values:
        return fallback

    idx = len(values) - _trusted_proxy_hops(settings_obj)
    if idx < 0:
        return fallback
    if idx >= len(values):
        candidate = values[-1]
    else:
        candidate = values[idx]
    if candidate not in _FORWARDED_PROTO_ALLOWLIST:
        return fallback
    return candidate


def apply_trusted_proxy_headers(request: Request, *, settings_obj: Any) -> tuple[str, str]:
    client_ip = resolve_client_ip(request, settings_obj=settings_obj)
    scheme = resolve_request_scheme(request, settings_obj=settings_obj)

    current_client = request.scope.get("client")
    if isinstance(current_client, tuple) and len(current_client) >= 2:
        request.scope["client"] = (client_ip, current_client[1])
    else:
        request.scope["client"] = (client_ip, 0)
    request.scope["scheme"] = scheme
    return client_ip, scheme


__all__ = [
    "apply_trusted_proxy_headers",
    "resolve_client_ip",
    "resolve_request_scheme",
]
