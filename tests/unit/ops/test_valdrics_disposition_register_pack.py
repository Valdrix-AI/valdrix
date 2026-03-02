from __future__ import annotations

from pathlib import Path

from scripts.verify_valdrics_disposition_freshness import verify_disposition_register


REPO_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_DIR = REPO_ROOT / "docs" / "ops" / "evidence"
REGISTER_PATH = EVIDENCE_DIR / "valdrics_disposition_register_2026-02-28.json"
TEMPLATE_PATH = EVIDENCE_DIR / "valdrics_disposition_register_TEMPLATE.json"


def test_valdrics_disposition_pack_contains_register_and_template() -> None:
    assert REGISTER_PATH.exists(), str(REGISTER_PATH)
    assert TEMPLATE_PATH.exists(), str(TEMPLATE_PATH)


def test_valdrics_disposition_register_pack_verifies() -> None:
    assert (
        verify_disposition_register(
            register_path=REGISTER_PATH,
            max_artifact_age_days=45.0,
            max_review_window_days=120.0,
        )
        == 0
    )
