from __future__ import annotations

import pytest

from scripts.safety_guardrails import (
    ensure_environment_confirmation,
    ensure_force_and_phrase,
    ensure_interactive_confirmation,
    ensure_protected_environment_bypass,
)


def test_ensure_force_and_phrase_requires_force() -> None:
    with pytest.raises(RuntimeError, match="without --force"):
        ensure_force_and_phrase(
            force=False,
            phrase="WIPE_VALDRICS_DATA",
            expected_phrase="WIPE_VALDRICS_DATA",
        )


def test_ensure_environment_confirmation_requires_exact_match() -> None:
    with pytest.raises(RuntimeError, match="does not match"):
        ensure_environment_confirmation(
            confirm_environment="staging",
            environment="production",
        )


def test_ensure_protected_environment_bypass_rejects_missing_phrase(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VALDRICS_ALLOW_PROD_WIPE", raising=False)
    with pytest.raises(RuntimeError, match="protected environment"):
        ensure_protected_environment_bypass(
            environment="production",
            bypass_env_var="VALDRICS_ALLOW_PROD_WIPE",
            bypass_phrase="I_UNDERSTAND_THIS_WILL_DESTROY_DATA",
            operation_label="wipe",
        )


def test_ensure_interactive_confirmation_requires_tty_without_no_prompt() -> None:
    with pytest.raises(RuntimeError, match="requires a TTY"):
        ensure_interactive_confirmation(
            token="WIPE:DEVELOPMENT",
            no_prompt=False,
            noninteractive_env_var="VALDRICS_ALLOW_NONINTERACTIVE_WIPE",
            input_fn=lambda _prompt: "WIPE:DEVELOPMENT",
            is_tty_fn=lambda: False,
        )


def test_ensure_interactive_confirmation_requires_env_for_no_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("VALDRICS_ALLOW_NONINTERACTIVE_WIPE", raising=False)
    with pytest.raises(RuntimeError, match="non-interactive"):
        ensure_interactive_confirmation(
            token="WIPE:DEVELOPMENT",
            no_prompt=True,
            noninteractive_env_var="VALDRICS_ALLOW_NONINTERACTIVE_WIPE",
        )


def test_ensure_interactive_confirmation_accepts_explicit_noninteractive_bypass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VALDRICS_ALLOW_NONINTERACTIVE_WIPE", "true")
    ensure_interactive_confirmation(
        token="WIPE:DEVELOPMENT",
        no_prompt=True,
        noninteractive_env_var="VALDRICS_ALLOW_NONINTERACTIVE_WIPE",
    )


def test_ensure_interactive_confirmation_validates_entered_token() -> None:
    with pytest.raises(RuntimeError, match="token mismatch"):
        ensure_interactive_confirmation(
            token="ISSUE_VALDRICS_EMERGENCY_TOKEN",
            no_prompt=False,
            noninteractive_env_var="VALDRICS_ALLOW_NONINTERACTIVE_EMERGENCY_TOKEN",
            input_fn=lambda _prompt: "wrong-token",
            is_tty_fn=lambda: True,
        )
