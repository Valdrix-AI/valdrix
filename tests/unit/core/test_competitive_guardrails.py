from __future__ import annotations

import ast
import inspect
import re
import textwrap
from pathlib import Path

from app.modules.optimization.adapters.aws.plugins.compute import IdleInstancesPlugin
from app.shared.core.pricing import FeatureFlag, PricingTier, is_feature_enabled

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_no_cost_explorer_client_usage_in_app_code() -> None:
    """
    Guardrail: application code must not instantiate Cost Explorer clients.
    We intentionally ingest AWS cost via CUR, not CE API calls.
    """
    app_root = REPO_ROOT / "app"
    ce_client_patterns = (
        re.compile(r"client\(\s*['\"]ce['\"]\s*\)"),
        re.compile(r"resource\(\s*['\"]ce['\"]\s*\)"),
    )
    offenders: list[str] = []

    for path in app_root.rglob("*.py"):
        content = path.read_text(encoding="utf-8")
        if any(pattern.search(content) for pattern in ce_client_patterns):
            offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == [], f"Unexpected Cost Explorer client usage found: {offenders}"


def test_aws_role_template_excludes_cost_explorer_actions() -> None:
    """
    Guardrail: customer IAM template must not grant ce:* actions.
    """
    template_path = REPO_ROOT / "cloudformation" / "valdrix-role.yaml"
    content = template_path.read_text(encoding="utf-8")
    listed_actions = re.findall(
        r"^\s*-\s*([a-zA-Z0-9:*._-]+)\s*$",
        content,
        flags=re.MULTILINE,
    )
    ce_actions = sorted({action for action in listed_actions if action.lower().startswith("ce:")})
    assert ce_actions == [], f"Unexpected Cost Explorer IAM actions found: {ce_actions}"


def test_gpu_idle_detection_families_include_high_cost_gpu_lines() -> None:
    """
    Guardrail: AWS idle compute detection keeps explicit GPU family detection.
    """
    source = textwrap.dedent(inspect.getsource(IdleInstancesPlugin.scan))
    tree = ast.parse(source)

    gpu_families: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if not isinstance(target, ast.Name) or target.id != "gpu_families":
                continue
            if not isinstance(node.value, (ast.List, ast.Tuple)):
                continue
            for element in node.value.elts:
                if isinstance(element, ast.Constant) and isinstance(element.value, str):
                    gpu_families.add(element.value.lower())

    assert gpu_families, "Failed to locate gpu_families list in IdleInstancesPlugin.scan"
    assert {"p3", "p4", "g5"}.issubset(gpu_families)


def test_discovery_tier_guardrail_stage_a_vs_stage_b() -> None:
    """
    Guardrail: Stage A domain discovery remains broad, Stage B deep scan remains Pro+.
    """
    assert is_feature_enabled(PricingTier.FREE, FeatureFlag.DOMAIN_DISCOVERY) is True
    assert is_feature_enabled(PricingTier.GROWTH, FeatureFlag.DOMAIN_DISCOVERY) is True
    assert is_feature_enabled(PricingTier.GROWTH, FeatureFlag.IDP_DEEP_SCAN) is False
    assert is_feature_enabled(PricingTier.PRO, FeatureFlag.IDP_DEEP_SCAN) is True
