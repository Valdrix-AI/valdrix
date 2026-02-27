from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess
import tempfile

import jsonschema
import pytest
import yaml


REPO_ROOT = Path(__file__).resolve().parents[3]
CHART_DIR = REPO_ROOT / "helm" / "valdrix"
VALUES_SCHEMA_PATH = CHART_DIR / "values.schema.json"


def _helm_template(overrides: dict[str, object]) -> subprocess.CompletedProcess[str]:
    if shutil.which("helm") is None:
        pytest.skip("helm binary is not available in this environment")

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as fh:
        yaml.safe_dump(overrides, fh, sort_keys=True)
        values_path = Path(fh.name)

    try:
        return subprocess.run(
            ["helm", "template", "valdrix-test", str(CHART_DIR), "-f", str(values_path)],
            check=False,
            capture_output=True,
            text=True,
        )
    finally:
        values_path.unlink(missing_ok=True)


def _rendered_objects(manifest: str) -> list[dict[str, object]]:
    return [
        doc
        for doc in yaml.safe_load_all(manifest)
        if isinstance(doc, dict)
    ]


def _find_kind(
    rendered: list[dict[str, object]],
    *,
    kind: str,
) -> dict[str, object] | None:
    for doc in rendered:
        if str(doc.get("kind") or "") == kind:
            return doc
    return None


def _valid_enforcement_webhook_values() -> dict[str, object]:
    return {
        "enforcementWebhook": {
            "enabled": True,
            "failurePolicy": "Ignore",
            "timeoutSeconds": 2,
            "matchPolicy": "Equivalent",
            "sideEffects": "None",
            "path": "/api/v1/enforcement/gate/k8s/admission/review",
            "admissionReviewVersions": ["v1"],
            "operations": ["CREATE", "UPDATE"],
            "apiGroups": ["*"],
            "apiVersions": ["*"],
            "resources": ["*/*"],
            "namespaceSelector": {
                "matchExpressions": [
                    {
                        "key": "kubernetes.io/metadata.name",
                        "operator": "NotIn",
                        "values": ["kube-system", "kube-public", "kube-node-lease"],
                    }
                ]
            },
            "objectSelector": {},
            "matchConditions": [
                {
                    "name": "exclude-leases",
                    "expression": "request.resource.resource != 'leases'",
                }
            ],
            "podDisruptionBudget": {"enabled": False, "maxUnavailable": 1},
            "service": {"namespace": "valdrix", "name": "valdrix-api", "port": 80},
            "certManager": {"enabled": False, "injectorSecretName": ""},
            "caBundle": "",
        }
    }


def test_enforcement_webhook_values_schema_accepts_valid_contract() -> None:
    schema = json.loads(VALUES_SCHEMA_PATH.read_text(encoding="utf-8"))
    values = _valid_enforcement_webhook_values()
    jsonschema.validate(instance=values, schema=schema)


def test_enforcement_webhook_values_schema_rejects_invalid_contracts() -> None:
    schema = json.loads(VALUES_SCHEMA_PATH.read_text(encoding="utf-8"))
    valid = _valid_enforcement_webhook_values()

    invalid_cases = [
        (
            "path must start with slash",
            {"enforcementWebhook": {**valid["enforcementWebhook"], "path": "invalid/path"}},
        ),
        (
            "admission review versions must include v1",
            {
                "enforcementWebhook": {
                    **valid["enforcementWebhook"],
                    "admissionReviewVersions": ["v1beta1"],
                }
            },
        ),
        (
            "timeout must be <= 5 for fail-closed",
            {
                "replicaCount": 2,
                "deploymentStrategy": {
                    "type": "RollingUpdate",
                    "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1},
                },
                "affinity": {
                    "podAntiAffinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": [
                            {"topologyKey": "kubernetes.io/hostname"}
                        ]
                    }
                },
                "enforcementWebhook": {
                    **valid["enforcementWebhook"],
                    "failurePolicy": "Fail",
                    "timeoutSeconds": 6,
                    "podDisruptionBudget": {"enabled": True, "maxUnavailable": 1},
                }
            },
        ),
        (
            "certManager requires injector secret name",
            {
                "enforcementWebhook": {
                    **valid["enforcementWebhook"],
                    "certManager": {"enabled": True, "injectorSecretName": ""},
                }
            },
        ),
        (
            "cannot mix certManager and static caBundle",
            {
                "enforcementWebhook": {
                    **valid["enforcementWebhook"],
                    "certManager": {
                        "enabled": True,
                        "injectorSecretName": "valdrix-webhook-ca",
                    },
                    "caBundle": "c3RhdGljLWNhLWJ1bmRsZQ==",
                }
            },
        ),
        (
            "Exists/DoesNotExist operators cannot define selector values",
            {
                "enforcementWebhook": {
                    **valid["enforcementWebhook"],
                    "namespaceSelector": {
                        "matchExpressions": [
                            {
                                "key": "kubernetes.io/metadata.name",
                                "operator": "Exists",
                                "values": ["kube-system"],
                            }
                        ]
                    },
                }
            },
        ),
        (
            "Fail-closed requires API HA when autoscaling disabled",
            {
                "replicaCount": 1,
                "autoscaling": {"enabled": False},
                "deploymentStrategy": {
                    "type": "RollingUpdate",
                    "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1},
                },
                "affinity": {
                    "podAntiAffinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": [
                            {"topologyKey": "kubernetes.io/hostname"}
                        ]
                    }
                },
                "enforcementWebhook": {
                    **valid["enforcementWebhook"],
                    "failurePolicy": "Fail",
                    "timeoutSeconds": 2,
                    "podDisruptionBudget": {"enabled": True, "maxUnavailable": 1},
                },
            },
        ),
        (
            "Fail-closed requires PodDisruptionBudget guard enabled",
            {
                "replicaCount": 2,
                "autoscaling": {"enabled": False},
                "deploymentStrategy": {
                    "type": "RollingUpdate",
                    "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1},
                },
                "affinity": {
                    "podAntiAffinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": [
                            {"topologyKey": "kubernetes.io/hostname"}
                        ]
                    }
                },
                "enforcementWebhook": {
                    **valid["enforcementWebhook"],
                    "failurePolicy": "Fail",
                    "timeoutSeconds": 2,
                    "podDisruptionBudget": {
                        "enabled": False,
                        "maxUnavailable": 1,
                    },
                },
            },
        ),
        (
            "Fail-closed requires conservative PodDisruptionBudget maxUnavailable",
            {
                "replicaCount": 2,
                "autoscaling": {"enabled": False},
                "deploymentStrategy": {
                    "type": "RollingUpdate",
                    "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1},
                },
                "affinity": {
                    "podAntiAffinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": [
                            {"topologyKey": "kubernetes.io/hostname"}
                        ]
                    }
                },
                "enforcementWebhook": {
                    **valid["enforcementWebhook"],
                    "failurePolicy": "Fail",
                    "timeoutSeconds": 2,
                    "podDisruptionBudget": {
                        "enabled": True,
                        "maxUnavailable": 2,
                    },
                },
            },
        ),
        (
            "Fail-closed requires RollingUpdate deployment strategy",
            {
                "replicaCount": 2,
                "autoscaling": {"enabled": False},
                "deploymentStrategy": {
                    "type": "Recreate",
                    "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1},
                },
                "affinity": {
                    "podAntiAffinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": [
                            {"topologyKey": "kubernetes.io/hostname"}
                        ]
                    }
                },
                "enforcementWebhook": {
                    **valid["enforcementWebhook"],
                    "failurePolicy": "Fail",
                    "timeoutSeconds": 2,
                    "podDisruptionBudget": {"enabled": True, "maxUnavailable": 1},
                },
            },
        ),
        (
            "Fail-closed requires hard anti-affinity on hostname",
            {
                "replicaCount": 2,
                "autoscaling": {"enabled": False},
                "deploymentStrategy": {
                    "type": "RollingUpdate",
                    "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1},
                },
                "affinity": {
                    "podAntiAffinity": {
                        "requiredDuringSchedulingIgnoredDuringExecution": [
                            {"topologyKey": "topology.kubernetes.io/zone"}
                        ]
                    }
                },
                "enforcementWebhook": {
                    **valid["enforcementWebhook"],
                    "failurePolicy": "Fail",
                    "timeoutSeconds": 2,
                    "podDisruptionBudget": {"enabled": True, "maxUnavailable": 1},
                },
            },
        ),
    ]

    for _, invalid in invalid_cases:
        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(instance=invalid, schema=schema)


def test_helm_webhook_disabled_renders_no_validating_webhook() -> None:
    rendered = _helm_template({})
    assert rendered.returncode == 0, rendered.stderr

    objects = _rendered_objects(rendered.stdout)
    webhook = _find_kind(objects, kind="ValidatingWebhookConfiguration")
    assert webhook is None


def test_helm_webhook_enabled_renders_hardened_defaults_and_match_conditions() -> None:
    rendered = _helm_template(
        {
            "enforcementWebhook": {
                "enabled": True,
                "service": {"namespace": "valdrix", "name": "valdrix-api", "port": 80},
                "matchConditions": [
                    {
                        "name": "exclude-leases",
                        "expression": "request.resource.resource != 'leases'",
                    }
                ],
            }
        }
    )
    assert rendered.returncode == 0, rendered.stderr

    objects = _rendered_objects(rendered.stdout)
    webhook_obj = _find_kind(objects, kind="ValidatingWebhookConfiguration")
    assert isinstance(webhook_obj, dict)

    webhooks = webhook_obj.get("webhooks")
    assert isinstance(webhooks, list) and webhooks
    webhook = webhooks[0]
    assert webhook["failurePolicy"] == "Ignore"
    assert webhook["timeoutSeconds"] == 2
    selector = webhook["namespaceSelector"]
    assert selector["matchExpressions"][0]["key"] == "kubernetes.io/metadata.name"
    assert selector["matchExpressions"][0]["operator"] == "NotIn"
    assert "kube-system" in selector["matchExpressions"][0]["values"]

    match_conditions = webhook.get("matchConditions")
    assert isinstance(match_conditions, list) and match_conditions
    assert match_conditions[0]["name"] == "exclude-leases"


def test_helm_webhook_cert_manager_requires_injector_secret_name() -> None:
    rendered = _helm_template(
        {
            "enforcementWebhook": {
                "enabled": True,
                "certManager": {"enabled": True, "injectorSecretName": ""},
            }
        }
    )
    assert rendered.returncode != 0
    assert "values don't meet the specifications" in rendered.stderr
    assert "injectorSecretName" in rendered.stderr
    assert "minLength" in rendered.stderr


def test_helm_webhook_rejects_cert_manager_and_ca_bundle_combo() -> None:
    rendered = _helm_template(
        {
            "enforcementWebhook": {
                "enabled": True,
                "certManager": {
                    "enabled": True,
                    "injectorSecretName": "valdrix-webhook-ca",
                },
                "caBundle": "c3RhdGljLWNhLWJ1bmRsZQ==",
            }
        }
    )
    assert rendered.returncode != 0
    assert "values don't meet the specifications" in rendered.stderr
    assert "/enforcementWebhook" in rendered.stderr
    assert "'not' failed" in rendered.stderr


def test_helm_webhook_rejects_fail_closed_with_high_timeout() -> None:
    rendered = _helm_template(
        {
            "enforcementWebhook": {
                "enabled": True,
                "failurePolicy": "Fail",
                "timeoutSeconds": 6,
                "podDisruptionBudget": {"enabled": True, "maxUnavailable": 1},
            }
        }
    )
    assert rendered.returncode != 0
    assert "values don't meet the specifications" in rendered.stderr
    assert "timeoutSeconds" in rendered.stderr
    assert "maximum" in rendered.stderr


def test_helm_webhook_rejects_fail_closed_without_ha_replicas() -> None:
    rendered = _helm_template(
        {
            "replicaCount": 1,
            "autoscaling": {"enabled": False},
            "enforcementWebhook": {
                "enabled": True,
                "failurePolicy": "Fail",
                "timeoutSeconds": 2,
                "podDisruptionBudget": {"enabled": True, "maxUnavailable": 1},
            },
        }
    )
    assert rendered.returncode != 0
    assert "values don't meet the specifications" in rendered.stderr
    assert "replicaCount" in rendered.stderr
    assert "minimum" in rendered.stderr


def test_helm_webhook_rejects_fail_closed_pdb_with_too_high_max_unavailable() -> None:
    rendered = _helm_template(
        {
            "replicaCount": 2,
            "autoscaling": {"enabled": False},
            "enforcementWebhook": {
                "enabled": True,
                "failurePolicy": "Fail",
                "timeoutSeconds": 2,
                "podDisruptionBudget": {"enabled": True, "maxUnavailable": 2},
            },
        }
    )
    assert rendered.returncode != 0
    assert "values don't meet the specifications" in rendered.stderr
    assert "maxUnavailable" in rendered.stderr
    assert "maximum" in rendered.stderr


def test_helm_webhook_rejects_fail_closed_with_recreate_strategy() -> None:
    rendered = _helm_template(
        {
            "replicaCount": 2,
            "autoscaling": {"enabled": False},
            "deploymentStrategy": {
                "type": "Recreate",
                "rollingUpdate": {"maxUnavailable": 0, "maxSurge": 1},
            },
            "enforcementWebhook": {
                "enabled": True,
                "failurePolicy": "Fail",
                "timeoutSeconds": 2,
                "podDisruptionBudget": {"enabled": True, "maxUnavailable": 1},
            },
        }
    )
    assert rendered.returncode != 0
    assert "values don't meet the specifications" in rendered.stderr
    assert "deploymentStrategy" in rendered.stderr
    assert "RollingUpdate" in rendered.stderr


def test_helm_webhook_rejects_fail_closed_without_hard_host_anti_affinity() -> None:
    rendered = _helm_template(
        {
            "replicaCount": 2,
            "autoscaling": {"enabled": False},
            "affinity": {
                "podAntiAffinity": {
                    "requiredDuringSchedulingIgnoredDuringExecution": [
                        {"topologyKey": "topology.kubernetes.io/zone"}
                    ]
                }
            },
            "enforcementWebhook": {
                "enabled": True,
                "failurePolicy": "Fail",
                "timeoutSeconds": 2,
                "podDisruptionBudget": {"enabled": True, "maxUnavailable": 1},
            },
        }
    )
    assert rendered.returncode != 0
    assert "values don't meet the specifications" in rendered.stderr
    assert "kubernetes.io/hostname" in rendered.stderr


def test_helm_webhook_fail_closed_accepts_manual_ha_replicas() -> None:
    rendered = _helm_template(
        {
            "replicaCount": 2,
            "autoscaling": {"enabled": False},
            "enforcementWebhook": {
                "enabled": True,
                "failurePolicy": "Fail",
                "timeoutSeconds": 2,
                "podDisruptionBudget": {"enabled": True, "maxUnavailable": 1},
            },
        }
    )
    assert rendered.returncode == 0, rendered.stderr

    objects = _rendered_objects(rendered.stdout)
    webhook_obj = _find_kind(objects, kind="ValidatingWebhookConfiguration")
    assert isinstance(webhook_obj, dict)
    webhooks = webhook_obj.get("webhooks")
    assert isinstance(webhooks, list) and webhooks
    assert webhooks[0]["failurePolicy"] == "Fail"
    assert webhooks[0]["timeoutSeconds"] == 2


def test_helm_webhook_fail_closed_accepts_hpa_high_availability() -> None:
    rendered = _helm_template(
        {
            "replicaCount": 1,
            "autoscaling": {"enabled": True, "minReplicas": 2, "maxReplicas": 4},
            "enforcementWebhook": {
                "enabled": True,
                "failurePolicy": "Fail",
                "timeoutSeconds": 2,
                "podDisruptionBudget": {"enabled": True, "maxUnavailable": 1},
            },
        }
    )
    assert rendered.returncode == 0, rendered.stderr

    objects = _rendered_objects(rendered.stdout)
    webhook_obj = _find_kind(objects, kind="ValidatingWebhookConfiguration")
    assert isinstance(webhook_obj, dict)
    webhooks = webhook_obj.get("webhooks")
    assert isinstance(webhooks, list) and webhooks
    assert webhooks[0]["failurePolicy"] == "Fail"


def test_helm_webhook_fail_closed_renders_pdb_guardrail() -> None:
    rendered = _helm_template(
        {
            "replicaCount": 2,
            "autoscaling": {"enabled": False},
            "enforcementWebhook": {
                "enabled": True,
                "failurePolicy": "Fail",
                "timeoutSeconds": 2,
                "podDisruptionBudget": {"enabled": True, "maxUnavailable": 1},
            },
        }
    )
    assert rendered.returncode == 0, rendered.stderr

    objects = _rendered_objects(rendered.stdout)
    pdb_obj = _find_kind(objects, kind="PodDisruptionBudget")
    assert isinstance(pdb_obj, dict)
    assert pdb_obj.get("apiVersion") == "policy/v1"
    spec = pdb_obj.get("spec")
    assert isinstance(spec, dict)
    assert spec.get("maxUnavailable") == 1
    selector = spec.get("selector")
    assert isinstance(selector, dict)
    labels = selector.get("matchLabels")
    assert isinstance(labels, dict)
    assert labels.get("app.kubernetes.io/component") == "api"


def test_helm_webhook_fail_open_does_not_render_pdb_by_default() -> None:
    rendered = _helm_template(
        {
            "enforcementWebhook": {
                "enabled": True,
                "failurePolicy": "Ignore",
                "timeoutSeconds": 2,
            }
        }
    )
    assert rendered.returncode == 0, rendered.stderr

    objects = _rendered_objects(rendered.stdout)
    pdb_obj = _find_kind(objects, kind="PodDisruptionBudget")
    assert pdb_obj is None
