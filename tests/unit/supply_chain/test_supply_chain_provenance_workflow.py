from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_sbom_workflow_has_attestation_permissions() -> None:
    text = (REPO_ROOT / ".github/workflows/sbom.yml").read_text(encoding="utf-8")

    assert "attestations: write" in text
    assert "id-token: write" in text


def test_sbom_workflow_verifies_dependency_locks_before_attestation() -> None:
    text = (REPO_ROOT / ".github/workflows/sbom.yml").read_text(encoding="utf-8")

    assert "uv lock --check" in text
    assert "pnpm install --frozen-lockfile" in text
    assert "pnpm audit --audit-level=high" in text


def test_sbom_workflow_attests_provenance_subjects() -> None:
    text = (REPO_ROOT / ".github/workflows/sbom.yml").read_text(encoding="utf-8")

    assert "scripts/generate_provenance_manifest.py" in text
    assert "actions/attest-build-provenance@" in text


def test_sbom_workflow_verifies_attestations_before_promotion() -> None:
    text = (REPO_ROOT / ".github/workflows/sbom.yml").read_text(encoding="utf-8")

    assert "scripts/verify_supply_chain_attestations.py" in text
    assert "--signer-workflow .github/workflows/sbom.yml" in text
    assert "--artifact ./sbom/valdrix-python-sbom.json" in text
    assert "--artifact ./sbom/valdrix-container-sbom.json" in text
    assert "--artifact ./provenance/supply-chain-manifest.json" in text


def test_ci_workflow_enforces_enterprise_placeholder_guard() -> None:
    text = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "scripts/verify_enterprise_placeholder_guards.py" in text


def test_ci_workflow_has_enterprise_tdd_quality_gate_job() -> None:
    text = (REPO_ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")

    assert "enterprise-tdd-quality-gate:" in text
    assert "Enterprise TDD Quality Gate" in text
    assert "scripts/run_enterprise_tdd_gate.py" in text
