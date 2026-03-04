from __future__ import annotations

from pathlib import Path

from scripts.verify_env_hygiene import main, verify_env_hygiene


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _valid_template() -> str:
    return "\n".join(
        [
            'APP_NAME="Valdrics"',
            "CSRF_SECRET_KEY=",
            "SMTP_USER=",
            "CLOUDFORMATION_TEMPLATE_URL=",
            "DB_POOL_SIZE=20",
            "DB_MAX_OVERFLOW=10",
            "DB_POOL_TIMEOUT=30",
        ]
    )


def test_verify_env_hygiene_passes_for_hardened_template(
    tmp_path: Path, monkeypatch
) -> None:
    _write(tmp_path / ".env.example", _valid_template())
    monkeypatch.setattr(
        "scripts.verify_env_hygiene._is_env_file_tracked",
        lambda _repo_root: False,
    )

    errors = verify_env_hygiene(
        repo_root=tmp_path,
        template_path=Path(".env.example"),
    )

    assert errors == ()


def test_verify_env_hygiene_flags_tracked_env_and_secret_values(
    tmp_path: Path, monkeypatch
) -> None:
    _write(
        tmp_path / ".env.example",
        "\n".join(
            [
                'APP_NAME="Valdrix"',
                "CSRF_SECRET_KEY=super-secret",
                "SMTP_USER=deeprince2020@gmail.com",
                "CLOUDFORMATION_TEMPLATE_URL=https://valdrix-templates.example.com",
                "DB_POOL_SIZE=0",
                "DB_MAX_OVERFLOW=abc",
            ]
        ),
    )
    monkeypatch.setattr(
        "scripts.verify_env_hygiene._is_env_file_tracked",
        lambda _repo_root: True,
    )

    errors = verify_env_hygiene(
        repo_root=tmp_path,
        template_path=Path(".env.example"),
    )
    joined = "\n".join(errors)

    assert "`.env` is tracked by git" in joined
    assert "APP_NAME in .env.example must be exactly `Valdrics`" in joined
    assert "CSRF_SECRET_KEY in .env.example must be empty." in joined
    assert "SMTP_USER in .env.example must be empty." in joined
    assert "forbidden personal email domain: gmail.com" in joined
    assert "old `valdrix` branding" in joined
    assert "DB_POOL_SIZE=0" in joined
    assert "DB_MAX_OVERFLOW='abc'" in joined
    assert "Missing required key in .env.example: DB_POOL_TIMEOUT" in joined


def test_main_returns_failure_for_missing_template(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "scripts.verify_env_hygiene._is_env_file_tracked",
        lambda _repo_root: False,
    )

    exit_code = main(
        [
            "--repo-root",
            str(tmp_path),
            "--template-path",
            ".env.example",
        ]
    )

    assert exit_code == 1

