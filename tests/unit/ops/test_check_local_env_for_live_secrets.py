from __future__ import annotations

from pathlib import Path

from scripts.security.check_local_env_for_live_secrets import main


def _write_env(tmp_path: Path, content: str) -> None:
    (tmp_path / ".env").write_text(content, encoding="utf-8")


def test_main_flags_live_paystack_keys(tmp_path: Path, monkeypatch, capsys) -> None:
    monkeypatch.chdir(tmp_path)
    _write_env(
        tmp_path,
        "PAYSTACK_SECRET_KEY=sk_live_1234567890\nPAYSTACK_PUBLIC_KEY=pk_live_1234567890\n",
    )

    assert main() == 1
    output = capsys.readouterr().out
    assert "PAYSTACK_SECRET_KEY" in output
    assert "PAYSTACK_PUBLIC_KEY" in output


def test_main_ignores_explicit_synthetic_validation_keys(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    monkeypatch.chdir(tmp_path)
    _write_env(
        tmp_path,
        (
            "PAYSTACK_SECRET_KEY=example_paystack_secret_ci_validation_only\n"
            "PAYSTACK_PUBLIC_KEY=example_paystack_public_ci_validation_only\n"
        ),
    )

    assert main() == 0
    assert "No known live-secret patterns detected" in capsys.readouterr().out
