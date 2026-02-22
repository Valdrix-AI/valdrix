from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def _extract_assignment_keys(path: Path) -> set[str]:
    keys: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key = line.split("=", 1)[0].strip()
        if key:
            keys.add(key)
    return keys


def _extract_koyeb_env_names(path: Path) -> set[str]:
    keys: set[str] = set()
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("- name:"):
            keys.add(line.split(":", 1)[1].strip())
    return keys


def test_env_example_contains_required_runtime_contract_keys() -> None:
    keys = _extract_assignment_keys(REPO_ROOT / ".env.example")

    required = {
        "ENVIRONMENT",
        "DATABASE_URL",
        "SUPABASE_JWT_SECRET",
        "ENCRYPTION_KEY",
        "KDF_SALT",
        "CSRF_SECRET_KEY",
        "ADMIN_API_KEY",
        "LLM_PROVIDER",
        "REDIS_URL",
        "SENTRY_DSN",
    }

    missing = required - keys
    assert not missing, f".env.example missing keys: {sorted(missing)}"


def test_prod_env_template_contains_required_runtime_contract_keys() -> None:
    keys = _extract_assignment_keys(REPO_ROOT / "prod.env.template")

    required = {
        "ENVIRONMENT",
        "DATABASE_URL",
        "REDIS_URL",
        "SUPABASE_JWT_SECRET",
        "ENCRYPTION_KEY",
        "KDF_SALT",
        "CSRF_SECRET_KEY",
        "ADMIN_API_KEY",
        "CORS_ORIGINS",
        "LLM_PROVIDER",
        "GROQ_API_KEY",
        "PAYSTACK_SECRET_KEY",
        "PAYSTACK_PUBLIC_KEY",
        "SAAS_STRICT_INTEGRATIONS",
        "SENTRY_DSN",
    }

    missing = required - keys
    assert not missing, f"prod.env.template missing keys: {sorted(missing)}"


def test_prod_env_template_does_not_use_legacy_paystack_plan_key() -> None:
    keys = _extract_assignment_keys(REPO_ROOT / "prod.env.template")
    assert "PAYSTACK_PLAN_PROFESSIONAL" not in keys
    assert "PAYSTACK_PLAN_PRO" in keys


def test_koyeb_manifest_declares_required_env_entries() -> None:
    keys = _extract_koyeb_env_names(REPO_ROOT / "koyeb.yaml")

    required = {
        "ENVIRONMENT",
        "WEB_CONCURRENCY",
        "DATABASE_URL",
        "REDIS_URL",
        "SUPABASE_JWT_SECRET",
        "ENCRYPTION_KEY",
        "KDF_SALT",
        "CSRF_SECRET_KEY",
        "ADMIN_API_KEY",
        "PAYSTACK_SECRET_KEY",
        "PAYSTACK_PUBLIC_KEY",
        "SENTRY_DSN",
    }

    missing = required - keys
    assert not missing, f"koyeb.yaml missing env entries: {sorted(missing)}"
    assert "WORKERS" not in keys
