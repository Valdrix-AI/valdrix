from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_terraform_secret_rotation_contract_enforces_90_day_ttl() -> None:
    root_main = (REPO_ROOT / "terraform/main.tf").read_text(encoding="utf-8")
    root_vars = (REPO_ROOT / "terraform/variables.tf").read_text(encoding="utf-8")
    module_main = (
        REPO_ROOT / "terraform/modules/secrets_rotation/main.tf"
    ).read_text(encoding="utf-8")
    module_vars = (
        REPO_ROOT / "terraform/modules/secrets_rotation/variables.tf"
    ).read_text(encoding="utf-8")

    assert 'module "secrets_rotation"' in root_main
    assert "enable_secret_rotation" in root_vars
    assert "secret_rotation_lambda_arn" in root_vars
    assert "enable_key_rotation     = true" in module_main
    assert 'resource "aws_secretsmanager_secret_rotation" "runtime"' in module_main
    assert "automatically_after_days = 90" in module_main
    assert "enable_secret_rotation must be true for prod/production environments." in module_main
    assert "rotation_lambda_arn must be set when enable_secret_rotation is true." in module_vars


def test_helm_external_secrets_contract_is_declared() -> None:
    values_text = (REPO_ROOT / "helm/valdrics/values.yaml").read_text(encoding="utf-8")
    template_text = (
        REPO_ROOT / "helm/valdrics/templates/external-secrets.yaml"
    ).read_text(encoding="utf-8")
    helpers_text = (
        REPO_ROOT / "helm/valdrics/templates/_helpers.tpl"
    ).read_text(encoding="utf-8")

    assert "externalSecrets:" in values_text
    assert "enabled: true" in values_text
    assert "remoteSecretKey: /valdrics/prod/app-runtime" in values_text
    assert 'define "valdrics.runtimeSecretName"' in helpers_text
    assert "apiVersion: external-secrets.io/v1beta1" in template_text
    assert "kind: ExternalSecret" in template_text
    assert "secretStoreRef:" in template_text
    assert "dataFrom:" in template_text
    assert "externalSecrets.enabled must be true when env.ENVIRONMENT=production" in template_text
