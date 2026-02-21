#!/usr/bin/env python3
"""
Runtime environment preflight validator.

Validates:
- Settings contract (required secrets/env, security constraints)
- Runtime dependency contract (tiktoken, prophet fallback policy, sentry-sdk when DSN set)
"""

from __future__ import annotations

import argparse
import os
import sys

from app.shared.core.config import get_settings
from app.shared.core.runtime_dependencies import validate_runtime_dependencies


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate runtime env + dependency contract before deployment."
    )
    parser.add_argument(
        "--environment",
        choices=["local", "development", "staging", "production"],
        default=None,
        help="Override ENVIRONMENT for validation.",
    )
    parser.add_argument(
        "--allow-testing",
        action="store_true",
        help="Do not force TESTING=false (default forces production-style validation).",
    )
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.environment:
        os.environ["ENVIRONMENT"] = args.environment
    if not args.allow_testing:
        os.environ["TESTING"] = "false"

    # Rebuild settings from current environment.
    get_settings.cache_clear()

    try:
        settings = get_settings()
        validate_runtime_dependencies(settings)
    except Exception as exc:
        print(f"runtime_env_validation_failed: {exc}", file=sys.stderr)
        return 1

    print(
        "runtime_env_validation_passed",
        f"environment={settings.ENVIRONMENT}",
        f"testing={settings.TESTING}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

