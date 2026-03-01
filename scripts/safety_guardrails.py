"""Shared safety guardrails for destructive or break-glass operational scripts."""

from __future__ import annotations

import os
import sys
from typing import Callable

PROTECTED_ENVS = {"production", "staging"}


def current_environment() -> str:
    """Return normalized runtime environment label."""
    return str(os.getenv("ENVIRONMENT", "development")).strip().lower() or "development"


def ensure_force_and_phrase(*, force: bool, phrase: str, expected_phrase: str) -> None:
    if not force:
        raise RuntimeError("Refusing operation without --force.")
    if phrase != expected_phrase:
        raise RuntimeError(
            f"Refusing operation: --confirm-phrase must exactly match {expected_phrase!r}."
        )


def ensure_environment_confirmation(
    *, confirm_environment: str, environment: str
) -> None:
    normalized_expected = str(environment).strip().lower()
    normalized_confirmed = str(confirm_environment).strip().lower()
    if not normalized_confirmed:
        raise RuntimeError("--confirm-environment is required for destructive operations.")
    if normalized_confirmed != normalized_expected:
        raise RuntimeError(
            "Refusing operation: --confirm-environment does not match current ENVIRONMENT "
            f"({normalized_expected!r})."
        )


def ensure_protected_environment_bypass(
    *,
    environment: str,
    bypass_env_var: str,
    bypass_phrase: str,
    operation_label: str,
) -> None:
    if environment not in PROTECTED_ENVS:
        return
    if str(os.getenv(bypass_env_var, "")).strip() != bypass_phrase:
        raise RuntimeError(
            f"Refusing {operation_label} in protected environment. "
            f"Set {bypass_env_var} to the explicit bypass phrase."
        )


def ensure_interactive_confirmation(
    *,
    token: str,
    no_prompt: bool,
    noninteractive_env_var: str,
    input_fn: Callable[[str], str] = input,
    is_tty_fn: Callable[[], bool] | None = None,
) -> None:
    """
    Require interactive typed confirmation unless explicit non-interactive bypass is enabled.
    """
    if no_prompt:
        if str(os.getenv(noninteractive_env_var, "")).strip().lower() == "true":
            return
        raise RuntimeError(
            "Refusing non-interactive execution. "
            f"Set {noninteractive_env_var}=true to bypass interactive confirmation."
        )

    tty_checker = is_tty_fn or (lambda: bool(sys.stdin.isatty()))
    if not tty_checker():
        raise RuntimeError(
            "Interactive confirmation requires a TTY. "
            "Use --no-prompt with the explicit non-interactive bypass env var if automation is required."
        )

    entered = str(input_fn(f"Type {token!r} to continue: ")).strip()
    if entered != token:
        raise RuntimeError("Interactive confirmation token mismatch.")
