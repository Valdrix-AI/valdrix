from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.verify_jwt_bcp_checklist import (
    DEFAULT_CHECKLIST_PATH,
    REQUIRED_CONTROL_IDS,
    load_checklist,
    validate_checklist,
    verify_checklist_file,
)


REPO_ROOT = Path(__file__).resolve().parents[3]


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def test_default_jwt_bcp_checklist_verifies() -> None:
    exit_code = verify_checklist_file(REPO_ROOT / DEFAULT_CHECKLIST_PATH)
    assert exit_code == 0


def test_validate_checklist_rejects_missing_required_control(tmp_path: Path) -> None:
    checklist = load_checklist(REPO_ROOT / DEFAULT_CHECKLIST_PATH)
    controls = list(checklist["controls"])
    checklist["controls"] = [
        c for c in controls if c.get("control_id") != REQUIRED_CONTROL_IDS[0]
    ]
    _write_json(tmp_path / "checklist.json", checklist)

    with pytest.raises(ValueError, match="missing required control IDs"):
        validate_checklist(load_checklist(tmp_path / "checklist.json"), repo_root=REPO_ROOT)


def test_validate_checklist_rejects_duplicate_control_id(tmp_path: Path) -> None:
    checklist = load_checklist(REPO_ROOT / DEFAULT_CHECKLIST_PATH)
    checklist["controls"].append(dict(checklist["controls"][0]))
    _write_json(tmp_path / "checklist.json", checklist)

    with pytest.raises(ValueError, match="Duplicate JWT BCP control_id"):
        validate_checklist(load_checklist(tmp_path / "checklist.json"), repo_root=REPO_ROOT)


def test_validate_checklist_rejects_missing_evidence_path(tmp_path: Path) -> None:
    checklist = load_checklist(REPO_ROOT / DEFAULT_CHECKLIST_PATH)
    checklist["controls"][0]["evidence"] = ["docs/security/does_not_exist.md"]
    _write_json(tmp_path / "checklist.json", checklist)

    with pytest.raises(ValueError, match="does not exist"):
        validate_checklist(load_checklist(tmp_path / "checklist.json"), repo_root=REPO_ROOT)


def test_validate_checklist_rejects_invalid_status(tmp_path: Path) -> None:
    checklist = load_checklist(REPO_ROOT / DEFAULT_CHECKLIST_PATH)
    checklist["controls"][0]["status"] = "invalid"
    _write_json(tmp_path / "checklist.json", checklist)

    with pytest.raises(ValueError, match="invalid status"):
        validate_checklist(load_checklist(tmp_path / "checklist.json"), repo_root=REPO_ROOT)
