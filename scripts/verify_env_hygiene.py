"""Verify environment-file hygiene for release-critical config surfaces."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

FORBIDDEN_PERSONAL_EMAIL_DOMAINS: frozenset[str] = frozenset(
    {
        "gmail.com",
        "yahoo.com",
        "hotmail.com",
        "outlook.com",
        "icloud.com",
        "proton.me",
        "protonmail.com",
    }
)

REQUIRED_POSITIVE_INTEGER_KEYS: tuple[str, ...] = (
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "DB_POOL_TIMEOUT",
)

DEFAULT_TEMPLATE_PATH = Path(".env.example")


def _strip_wrapping_quotes(value: str) -> str:
    stripped = value.strip()
    if len(stripped) >= 2 and stripped[0] == stripped[-1] and stripped[0] in {"'", '"'}:
        return stripped[1:-1].strip()
    return stripped


def _parse_env_file(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        data[key] = _strip_wrapping_quotes(value)
    return data


def _is_env_file_tracked(repo_root: Path) -> bool:
    proc = subprocess.run(
        ["git", "ls-files", "--error-unmatch", ".env"],
        cwd=repo_root,
        check=False,
        capture_output=True,
        text=True,
    )
    return proc.returncode == 0


def _validate_positive_integer(values: dict[str, str], key: str) -> str | None:
    raw = values.get(key)
    if raw is None:
        return f"Missing required key in .env.example: {key}"
    value = raw.strip()
    if not value:
        return f"Required key is empty in .env.example: {key}"
    try:
        parsed = int(value)
    except ValueError:
        return f"Required key must be an integer in .env.example: {key}={value!r}"
    if parsed <= 0:
        return f"Required key must be > 0 in .env.example: {key}={parsed}"
    return None


def verify_env_hygiene(*, repo_root: Path, template_path: Path) -> tuple[str, ...]:
    errors: list[str] = []
    resolved_template = (
        template_path
        if template_path.is_absolute()
        else (repo_root / template_path).resolve()
    )

    if _is_env_file_tracked(repo_root):
        errors.append("`.env` is tracked by git. Secrets must never be committed.")

    if not resolved_template.exists():
        errors.append(f"Template file does not exist: {resolved_template.as_posix()}")
        return tuple(errors)

    values = _parse_env_file(resolved_template)

    app_name = values.get("APP_NAME", "").strip()
    if app_name != "Valdrics":
        errors.append(
            "APP_NAME in .env.example must be exactly `Valdrics` "
            f"(found: {app_name or '<empty>'})."
        )

    csrf_key = values.get("CSRF_SECRET_KEY", "").strip()
    if csrf_key:
        errors.append("CSRF_SECRET_KEY in .env.example must be empty.")

    smtp_user = values.get("SMTP_USER", "").strip()
    if smtp_user:
        errors.append("SMTP_USER in .env.example must be empty.")
        if "@" in smtp_user:
            domain = smtp_user.rsplit("@", 1)[-1].lower()
            if domain in FORBIDDEN_PERSONAL_EMAIL_DOMAINS:
                errors.append(
                    f"SMTP_USER uses forbidden personal email domain: {domain}"
                )

    cloudformation_url = values.get("CLOUDFORMATION_TEMPLATE_URL", "")
    if "valdrix" in cloudformation_url.lower():
        errors.append(
            "CLOUDFORMATION_TEMPLATE_URL still references old `valdrix` branding."
        )

    for key in REQUIRED_POSITIVE_INTEGER_KEYS:
        failure = _validate_positive_integer(values, key)
        if failure:
            errors.append(failure)

    return tuple(errors)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Verify environment-file hygiene and secret-management guardrails."
    )
    parser.add_argument(
        "--template-path",
        type=Path,
        default=DEFAULT_TEMPLATE_PATH,
        help="Path to .env template file (default: .env.example).",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path("."),
        help="Repository root to validate (default: current directory).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    repo_root = args.repo_root.resolve()
    errors = verify_env_hygiene(
        repo_root=repo_root,
        template_path=args.template_path,
    )
    if errors:
        print("[env-hygiene] FAILED")
        for issue in errors:
            print(f"- {issue}")
        return 1
    print(
        "[env-hygiene] ok "
        f"repo_root={repo_root.as_posix()} template_path={args.template_path.as_posix()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
