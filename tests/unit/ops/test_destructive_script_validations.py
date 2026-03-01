from __future__ import annotations

import pytest

from scripts import database_wipe, force_wipe_app


def _allow_noninteractive(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("VALDRICS_ALLOW_NONINTERACTIVE_WIPE", "true")


@pytest.mark.parametrize(
    "module",
    [force_wipe_app, database_wipe],
)
def test_wipe_validation_accepts_explicit_confirmation(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
) -> None:
    _allow_noninteractive(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "development")

    module._validate_wipe_request(  # type: ignore[attr-defined]
        force=True,
        phrase="WIPE_VALDRICS_DATA",
        confirm_environment="development",
        no_prompt=True,
    )


@pytest.mark.parametrize(
    "module",
    [force_wipe_app, database_wipe],
)
def test_wipe_validation_requires_environment_match(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
) -> None:
    _allow_noninteractive(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "development")

    with pytest.raises(RuntimeError, match="confirm-environment"):
        module._validate_wipe_request(  # type: ignore[attr-defined]
            force=True,
            phrase="WIPE_VALDRICS_DATA",
            confirm_environment="staging",
            no_prompt=True,
        )


@pytest.mark.parametrize(
    "module",
    [force_wipe_app, database_wipe],
)
def test_wipe_validation_rejects_protected_env_without_bypass(
    monkeypatch: pytest.MonkeyPatch,
    module: object,
) -> None:
    _allow_noninteractive(monkeypatch)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.delenv("VALDRICS_ALLOW_PROD_WIPE", raising=False)

    with pytest.raises(RuntimeError, match="protected environment"):
        module._validate_wipe_request(  # type: ignore[attr-defined]
            force=True,
            phrase="WIPE_VALDRICS_DATA",
            confirm_environment="production",
            no_prompt=True,
        )
