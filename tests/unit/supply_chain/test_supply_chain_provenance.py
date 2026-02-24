from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from scripts.generate_provenance_manifest import (
    DEFAULT_DEPENDENCY_INPUTS,
    generate_provenance_manifest,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_generate_provenance_manifest_emits_sha256_for_dependency_inputs(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", "[project]\nname='x'\n")
    _write(tmp_path / "uv.lock", "version = 1\n")
    _write(tmp_path / "Dockerfile", "FROM python:3.12-slim\n")
    _write(tmp_path / "Dockerfile.dashboard", "FROM node:24-alpine\n")
    _write(tmp_path / "dashboard/package.json", '{"name":"x"}\n')
    _write(tmp_path / "dashboard/pnpm-lock.yaml", "lockfileVersion: '9.0'\n")

    _write(tmp_path / "sbom/python.json", '{"bomFormat":"CycloneDX"}\n')

    env = {
        "GITHUB_REPOSITORY": "acme/valdrix",
        "GITHUB_SHA": "abc123",
        "GITHUB_REF": "refs/heads/main",
        "GITHUB_RUN_ID": "777",
        "GITHUB_RUN_ATTEMPT": "2",
        "GITHUB_WORKFLOW": "SBOM Generation",
    }

    manifest = generate_provenance_manifest(
        repo_root=tmp_path,
        dependency_inputs=DEFAULT_DEPENDENCY_INPUTS,
        sbom_dir=Path("sbom"),
        env=env,
    )

    assert manifest["build"]["git_sha"] == "abc123"
    assert manifest["build"]["workflow_run_id"] == "777"
    assert (
        manifest["build"]["workflow_run_url"]
        == "https://github.com/acme/valdrix/actions/runs/777"
    )
    assert len(manifest["dependency_inputs"]) == len(DEFAULT_DEPENDENCY_INPUTS)

    pyproject_digest = hashlib.sha256(
        (tmp_path / "pyproject.toml").read_bytes()
    ).hexdigest()
    pyproject_item = next(
        item for item in manifest["dependency_inputs"] if item["path"] == "pyproject.toml"
    )
    assert pyproject_item["sha256"] == pyproject_digest

    assert manifest["sbom_artifacts"]
    assert manifest["sbom_artifacts"][0]["path"] == "sbom/python.json"


def test_generate_provenance_manifest_requires_all_dependency_inputs(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", "[project]\nname='x'\n")
    _write(tmp_path / "dashboard/package.json", '{"name":"x"}\n')
    _write(tmp_path / "dashboard/pnpm-lock.yaml", "lockfileVersion: '9.0'\n")

    with pytest.raises(FileNotFoundError):
        generate_provenance_manifest(
            repo_root=tmp_path,
            dependency_inputs=DEFAULT_DEPENDENCY_INPUTS,
            sbom_dir=None,
            env={},
        )


def test_generate_provenance_manifest_is_json_serializable(tmp_path: Path) -> None:
    _write(tmp_path / "pyproject.toml", "[project]\nname='x'\n")
    _write(tmp_path / "uv.lock", "version = 1\n")
    _write(tmp_path / "Dockerfile", "FROM python:3.12-slim\n")
    _write(tmp_path / "Dockerfile.dashboard", "FROM node:24-alpine\n")
    _write(tmp_path / "dashboard/package.json", '{"name":"x"}\n')
    _write(tmp_path / "dashboard/pnpm-lock.yaml", "lockfileVersion: '9.0'\n")

    manifest = generate_provenance_manifest(
        repo_root=tmp_path,
        dependency_inputs=DEFAULT_DEPENDENCY_INPUTS,
        sbom_dir=None,
        env={},
    )

    encoded = json.dumps(manifest, sort_keys=True)
    assert "dependency_inputs" in encoded
