from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.generate_feature_enforceability_matrix import generate_matrix
from scripts.verify_feature_enforceability_matrix import verify_matrix


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_generated_feature_enforceability_matrix_verifies(tmp_path: Path) -> None:
    payload = generate_matrix(repo_root=REPO_ROOT)
    features = payload.get("features", {})
    assert features["api_access"]["status"] == "runtime_gated"
    assert features["policy_configuration"]["status"] == "runtime_gated"
    out = tmp_path / "matrix.json"
    out.write_text(json.dumps(payload), encoding="utf-8")
    verify_matrix(artifact_path=out, repo_root=REPO_ROOT)


def test_verify_feature_enforceability_matrix_rejects_missing_paid_feature(
    tmp_path: Path,
) -> None:
    payload = generate_matrix(repo_root=REPO_ROOT)
    features = dict(payload.get("features", {}))
    features.pop(next(iter(features.keys())))
    payload["features"] = features
    out = tmp_path / "matrix.json"
    out.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="missing paid-tier features"):
        verify_matrix(artifact_path=out, repo_root=REPO_ROOT)
