from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]


def _load_yaml(path: Path) -> object:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_helm_values_default_to_ha_api_and_internal_metrics() -> None:
    values = _load_yaml(REPO_ROOT / "helm/valdrics/values.yaml")
    assert isinstance(values, dict)

    assert int(values["replicaCount"]) >= 2
    assert values["env"]["WEB_CONCURRENCY"] == "2"
    assert values["env"]["ENABLE_SCHEDULER"] == "true"
    assert values["podAnnotations"]["prometheus.io/path"] == "/_internal/metrics"
    assert values["externalSecrets"]["enabled"] is True
    assert values["worker"]["podAnnotations"] == {}
    server_snippet = values["ingress"]["annotations"][
        "nginx.ingress.kubernetes.io/server-snippet"
    ]
    assert "/_internal/metrics" in server_snippet
    assert "location = /metrics" in server_snippet


def test_worker_template_is_conditionally_rendered_and_does_not_embed_beat() -> None:
    text = (
        REPO_ROOT / "helm/valdrics/templates/worker-deployment.yaml"
    ).read_text(encoding="utf-8")

    assert "{{- if .Values.worker.enabled }}" in text
    assert ".Values.worker.podAnnotations" in text
    assert ".Values.podAnnotations" not in text
    assert 'include "valdrics.runtimeSecretName" .' in text
    assert 'app.shared.core.celery_app:celery_app' in text
    assert '"-B"' not in text
    assert "startupProbe:" in text
    assert "livenessProbe:" in text
    assert "readinessProbe:" in text
    assert "inspect ping" in text


def test_api_template_uses_runtime_secret_helper() -> None:
    text = (REPO_ROOT / "helm/valdrics/templates/deployment.yaml").read_text(
        encoding="utf-8"
    )

    assert 'include "valdrics.runtimeSecretName" .' in text


def test_runtime_healthchecks_use_liveness_only() -> None:
    compose = _load_yaml(REPO_ROOT / "docker-compose.yml")
    prod_compose = _load_yaml(REPO_ROOT / "docker-compose.prod.yml")
    koyeb = _load_yaml(REPO_ROOT / "koyeb.yaml")

    assert isinstance(compose, dict)
    assert isinstance(prod_compose, dict)
    assert isinstance(koyeb, dict)

    compose_healthcheck = str(compose["services"]["api"]["healthcheck"]["test"]).lower()
    prod_healthcheck = str(prod_compose["services"]["api"]["healthcheck"]["test"]).lower()

    assert "/health/live" in compose_healthcheck
    assert "/health/live" in prod_healthcheck
    assert "curl" in compose_healthcheck
    assert "curl" in prod_healthcheck
    assert "urllib" not in compose_healthcheck
    assert "urllib" not in prod_healthcheck
    assert koyeb["definition"]["health_checks"][0]["path"] == "/health/live"


def test_release_images_are_immutable_and_observability_images_are_pinned() -> None:
    compose = _load_yaml(REPO_ROOT / "docker-compose.yml")
    prod_compose = _load_yaml(REPO_ROOT / "docker-compose.prod.yml")
    makefile_text = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")

    assert isinstance(compose, dict)
    assert isinstance(prod_compose, dict)

    assert compose["services"]["prometheus"]["image"] == "prom/prometheus:v2.54.1"
    assert compose["services"]["grafana"]["image"] == "grafana/grafana:11.4.0"
    assert ":latest" not in prod_compose["services"]["api"]["image"]
    assert ":latest" not in prod_compose["services"]["dashboard"]["image"]
    assert 'VERSION must be set to an immutable release tag' in makefile_text
    assert "ghcr.io/valdrics-ai/valdrics:$(VERSION)" in makefile_text


def test_local_compose_bootstraps_postgres_and_redis_for_offline_dev() -> None:
    compose = _load_yaml(REPO_ROOT / "docker-compose.yml")
    assert isinstance(compose, dict)

    services = compose["services"]
    assert services["postgres"]["image"] == "postgres:16.8-alpine"
    assert services["redis"]["image"] == "redis:7.2.5-alpine"

    pg_env = services["postgres"]["environment"]
    assert "POSTGRES_DB=${POSTGRES_DB:-valdrics}" in pg_env
    assert "POSTGRES_USER=${POSTGRES_USER:-postgres}" in pg_env
    assert "POSTGRES_PASSWORD=${POSTGRES_PASSWORD:-local-dev-change-me}" in pg_env

    api_env_files = services["api"]["env_file"]
    assert ".env" in api_env_files
    assert "environment" not in services["api"]

    api_depends_on = services["api"]["depends_on"]
    assert api_depends_on["postgres"]["condition"] == "service_healthy"
    assert api_depends_on["redis"]["condition"] == "service_healthy"


def test_backend_dockerfile_healthcheck_uses_curl_liveness_probe() -> None:
    dockerfile_text = (REPO_ROOT / "Dockerfile").read_text(encoding="utf-8").lower()

    assert "healthcheck" in dockerfile_text
    assert "/health/live" in dockerfile_text
    assert "curl --fail --silent --show-error" in dockerfile_text
    assert "urllib.request" not in dockerfile_text


def test_koyeb_and_prometheus_contracts_match_internal_metrics_and_ha_defaults() -> None:
    koyeb = _load_yaml(REPO_ROOT / "koyeb.yaml")
    koyeb_worker = _load_yaml(REPO_ROOT / "koyeb-worker.yaml")
    prometheus_text = (REPO_ROOT / "prometheus/prometheus.yml").read_text(
        encoding="utf-8"
    )

    assert isinstance(koyeb, dict)
    assert isinstance(koyeb_worker, dict)

    env_values = {
        item["name"]: item.get("value")
        for item in koyeb["definition"]["env"]
        if isinstance(item, dict) and "name" in item
    }
    assert int(koyeb["definition"]["scaling"]["min"]) >= 2
    assert env_values["WEB_CONCURRENCY"] == "2"
    assert env_values["ENABLE_SCHEDULER"] == "true"
    assert env_values["TRUST_PROXY_HEADERS"] == "true"
    assert env_values["APP_RUNTIME_DATA_DIR"] == "/tmp/valdrics"
    assert "metrics_path: /_internal/metrics" in prometheus_text
    assert env_values["FORECASTER_ALLOW_HOLT_WINTERS_FALLBACK"] is None
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in {
        item["name"] for item in koyeb["definition"]["env"] if "name" in item
    }
    assert "TRUSTED_PROXY_CIDRS" in {
        item["name"] for item in koyeb["definition"]["env"] if "name" in item
    }
    break_glass_reason = next(
        item
        for item in koyeb["definition"]["env"]
        if item.get("name") == "FORECASTER_BREAK_GLASS_REASON"
    )
    break_glass_expiry = next(
        item
        for item in koyeb["definition"]["env"]
        if item.get("name") == "FORECASTER_BREAK_GLASS_EXPIRES_AT"
    )
    assert break_glass_reason["secret"] == "valdrics-forecaster-break-glass-reason"
    assert (
        break_glass_expiry["secret"] == "valdrics-forecaster-break-glass-expires-at"
    )
    assert koyeb_worker["type"] == "WORKER"
    worker_env_names = {
        item["name"] for item in koyeb_worker["definition"]["env"] if "name" in item
    }
    assert "OTEL_EXPORTER_OTLP_ENDPOINT" in worker_env_names
    assert "SENTRY_DSN" in worker_env_names
    assert "REDIS_URL" in worker_env_names
    assert koyeb_worker["definition"]["command"][0:4] == [
        "uv",
        "run",
        "celery",
        "-A",
    ]


def test_deployment_docs_match_runtime_contracts() -> None:
    root_doc = (REPO_ROOT / "DEPLOYMENT.md").read_text(encoding="utf-8")
    ops_doc = (REPO_ROOT / "docs/DEPLOYMENT.md").read_text(encoding="utf-8")

    assert "/health/live" in root_doc
    assert "/_internal/metrics" in root_doc
    assert "503" in root_doc
    assert "--from-literal=DATABASE_URL=" in root_doc
    assert "--from-literal=ENCRYPTION_KEY=" in root_doc
    assert "--from-literal=OPENAI_API_KEY=" in root_doc
    assert "/health/live" in ops_doc
    assert "configured max break-glass window" in ops_doc
    assert "koyeb-worker.yaml" in ops_doc


def test_frontend_ci_node_version_matches_dashboard_container() -> None:
    ci_text = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    sbom_text = (REPO_ROOT / ".github/workflows/sbom.yml").read_text(encoding="utf-8")
    dockerfile_text = (REPO_ROOT / "Dockerfile.dashboard").read_text(encoding="utf-8")

    assert 'NODE_VERSION: "20"' in ci_text
    assert 'NODE_VERSION: "20"' in sbom_text
    assert "ARG NODE_BASE_IMAGE=node:20-slim" in dockerfile_text


def test_readme_does_not_reference_missing_raw_k8s_manifests() -> None:
    readme = (REPO_ROOT / "README.md").read_text(encoding="utf-8")

    assert "| **K8s Manifests** | `k8s/` |" not in readme


def test_dead_legacy_landing_component_is_removed() -> None:
    assert not (REPO_ROOT / "dashboard/LandingHero_legacy.svelte").exists()
