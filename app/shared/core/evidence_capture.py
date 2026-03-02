from __future__ import annotations

import re
from typing import Any

_SENSITIVE_KEY_FRAGMENTS = (
    "token",
    "secret",
    "password",
    "api_key",
    "apikey",
    "access_key",
    "private_key",
    "client_secret",
    "refresh_token",
)

_JWT_PART_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_JWT_RE = re.compile(r"([A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+)")


def sanitize_bearer_token(raw: str | None) -> str:
    """
    Extract a safe JWT token string for `Authorization: Bearer <token>` from operator inputs.

    Why this exists:
    - Operators often do: `VALDRICS_TOKEN=$(python scripts/dev_bearer_token.py ...)`.
      If any logs accidentally go to stdout, the env var becomes multiline and breaks HTTP headers.

    What we accept:
    - "<jwt>"
    - "Bearer <jwt>"
    - Strings containing other text/newlines, as long as a JWT-like substring exists.

    Returns:
    - The extracted JWT string (no whitespace), or "" if `raw` is empty.

    Raises:
    - ValueError if a non-empty input does not contain a valid JWT-like token.
    """
    value = str(raw or "").strip()
    if not value:
        return ""

    lowered = value.lower()
    if lowered.startswith("bearer "):
        value = value[7:].strip()

    # Common: shell exports with quotes.
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        value = value[1:-1].strip()

    matches = _JWT_RE.findall(value)
    candidate = (matches[-1] if matches else value).strip()

    if any(ch.isspace() for ch in candidate):
        raise ValueError("Token contains whitespace/newlines.")

    parts = candidate.split(".")
    if len(parts) != 3 or not all(parts):
        raise ValueError(
            "Token does not look like a JWT (expected 3 dot-separated segments)."
        )
    if not all(_JWT_PART_RE.match(p) for p in parts):
        raise ValueError("Token contains invalid characters (expected base64url).")

    return candidate


def redact_secrets(value: Any) -> Any:
    """
    Redact common secret-bearing keys from JSON-like payloads before writing evidence artifacts.

    This is intentionally conservative: if a key name looks sensitive, we replace its value.
    """
    if isinstance(value, list):
        return [redact_secrets(item) for item in value]
    if not isinstance(value, dict):
        return value

    redacted: dict[str, Any] = {}
    for k, v in value.items():
        key = str(k).lower()
        if any(fragment in key for fragment in _SENSITIVE_KEY_FRAGMENTS):
            redacted[k] = "***REDACTED***"
        else:
            redacted[k] = redact_secrets(v)
    return redacted
