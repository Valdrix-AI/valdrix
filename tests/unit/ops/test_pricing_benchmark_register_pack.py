from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = REPO_ROOT / "docs" / "ops" / "evidence"
GAP_REGISTER = (
    REPO_ROOT / "docs" / "ops" / "enforcement_control_plane_gap_register_2026-02-23.md"
)


def test_pricing_benchmark_register_artifacts_exist() -> None:
    required_paths = [
        EVIDENCE_DIR / "pricing_benchmark_register_TEMPLATE.json",
        EVIDENCE_DIR / "pricing_benchmark_register_2026-02-27.json",
        REPO_ROOT / "scripts" / "verify_pricing_benchmark_register.py",
    ]
    for path in required_paths:
        assert path.exists(), str(path)


def test_pricing_benchmark_register_docs_include_required_contracts() -> None:
    readme_raw = (EVIDENCE_DIR / "README.md").read_text(encoding="utf-8")
    gap_raw = GAP_REGISTER.read_text(encoding="utf-8")

    assert "pricing_benchmark_register_YYYY-MM-DD.json" in readme_raw
    assert "scripts/verify_pricing_benchmark_register.py" in readme_raw
    assert "PKG-020" in gap_raw
