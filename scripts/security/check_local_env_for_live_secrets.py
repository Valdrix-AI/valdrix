#!/usr/bin/env python3
"""
Fail-fast local scanner for accidental live secrets in .env.

This script is intentionally conservative and only prints key names, never values.
"""

from __future__ import annotations

import re
from pathlib import Path


PATTERNS: dict[str, re.Pattern[str]] = {
    "PAYSTACK_SECRET_KEY": re.compile(r"^sk_live_[A-Za-z0-9]+$"),
    "PAYSTACK_PUBLIC_KEY": re.compile(r"^pk_live_[A-Za-z0-9]+$"),
    "SLACK_BOT_TOKEN": re.compile(r"^xox[baprs]-[A-Za-z0-9-]+$"),
    "GROQ_API_KEY": re.compile(r"^gsk_[A-Za-z0-9]+$"),
    "OPENAI_API_KEY": re.compile(r"^sk-[A-Za-z0-9]+$"),
    "AWS_ACCESS_KEY_ID": re.compile(r"^AKIA[0-9A-Z]{16}$"),
    "AWS_SECRET_ACCESS_KEY": re.compile(r"^[A-Za-z0-9/+=]{40}$"),
    "DATABASE_URL": re.compile(r"^postgres(?:ql(?:\+asyncpg)?)://[^:]+:[^@]+@.+$"),
    "REDIS_URL": re.compile(r"^rediss?://.+$"),
}


def main() -> int:
    env_path = Path(".env")
    if not env_path.exists():
        print("No .env file found.")
        return 0

    risky_keys: list[str] = []
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or "=" not in line:
            continue
        is_commented = line.startswith("#")
        content = line[1:].strip() if is_commented else line
        if "=" not in content:
            continue
        key, _, raw_value = content.partition("=")
        key = key.strip()
        value = raw_value.strip().strip('"').strip("'")

        pattern = PATTERNS.get(key)
        if pattern and pattern.match(value):
            suffix = " (commented)" if is_commented else ""
            risky_keys.append(f"{key}{suffix}")

    if risky_keys:
        deduped = sorted(set(risky_keys))
        print("Potential live secrets detected in .env:")
        for key in deduped:
            print(f"- {key}")
        print("Rotate these secrets and replace .env with non-live placeholders.")
        return 1

    print("No known live-secret patterns detected in .env.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
