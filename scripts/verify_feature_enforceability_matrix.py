#!/usr/bin/env python3
"""Verify feature enforceability matrix artifact integrity."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.shared.core.pricing import FeatureFlag, PricingTier, get_tier_config
from scripts.generate_feature_enforceability_matrix import collect_enforceability


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _assert(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _parse_paid_feature_union() -> set[FeatureFlag]:
    tiers = (
        PricingTier.STARTER,
        PricingTier.GROWTH,
        PricingTier.PRO,
        PricingTier.ENTERPRISE,
    )
    union: set[FeatureFlag] = set()
    for tier in tiers:
        for feature in get_tier_config(tier).get("features", set()):
            if isinstance(feature, FeatureFlag):
                union.add(feature)
            elif isinstance(feature, str):
                try:
                    union.add(FeatureFlag(feature))
                except ValueError:
                    continue
    return union


def _validate_timestamp(value: Any) -> None:
    _assert(isinstance(value, str) and value.strip(), "captured_at must be a non-empty ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    _assert(parsed.tzinfo is not None, "captured_at must be timezone-aware")
    _assert(parsed <= datetime.now(timezone.utc), "captured_at cannot be in the future")


def verify_matrix(*, artifact_path: Path, repo_root: Path) -> None:
    _assert(artifact_path.exists(), f"matrix artifact does not exist: {artifact_path}")
    raw = json.loads(artifact_path.read_text(encoding="utf-8"))

    _validate_timestamp(raw.get("captured_at"))
    features = raw.get("features")
    _assert(isinstance(features, dict), "features must be an object")

    paid_union = _parse_paid_feature_union()
    evidence_map = collect_enforceability(repo_root=repo_root)
    missing = [flag.value for flag in sorted(paid_union, key=lambda item: item.value) if flag.value not in features]
    _assert(not missing, f"matrix missing paid-tier features: {missing}")

    for feature in sorted(paid_union, key=lambda item: item.value):
        payload = features.get(feature.value)
        _assert(isinstance(payload, dict), f"{feature.value}: payload must be an object")
        status = payload.get("status")
        _assert(status in {"runtime_gated", "catalog_only"}, f"{feature.value}: invalid status {status!r}")
        evidence = payload.get("evidence")
        _assert(isinstance(evidence, list) and evidence, f"{feature.value}: evidence must be a non-empty list")
        expected_status = evidence_map[feature].status
        _assert(
            status == expected_status,
            (
                f"{feature.value}: status mismatch; artifact={status} expected={expected_status}"
            ),
        )
        token = f"FeatureFlag.{feature.name}"
        for rel in evidence:
            _assert(isinstance(rel, str) and rel.strip(), f"{feature.value}: invalid evidence path entry")
            path = (repo_root / rel).resolve()
            _assert(path.exists(), f"{feature.value}: evidence file does not exist: {rel}")
            text = path.read_text(encoding="utf-8")
            _assert(token in text, f"{feature.value}: evidence file missing token {token} in {rel}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify feature enforceability matrix artifact.")
    parser.add_argument(
        "--matrix-path",
        default="docs/ops/feature_enforceability_matrix_2026-02-27.json",
        help="Path to matrix JSON artifact.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = _repo_root()
    matrix_path = (repo_root / str(args.matrix_path)).resolve()
    verify_matrix(artifact_path=matrix_path, repo_root=repo_root)
    print(
        "Feature enforceability matrix verified: "
        f"path={matrix_path.relative_to(repo_root)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
