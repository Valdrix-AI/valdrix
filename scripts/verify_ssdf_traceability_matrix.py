"""Validate SSDF traceability matrix structure and evidence-path integrity."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_MATRIX_PATH = Path("docs/security/ssdf_traceability_matrix_2026-02-25.json")

REQUIRED_PRACTICE_IDS: tuple[str, ...] = (
    "PO.1",
    "PO.2",
    "PO.3",
    "PO.4",
    "PO.5",
    "PS.1",
    "PS.2",
    "PS.3",
    "PW.1",
    "PW.2",
    "PW.4",
    "PW.5",
    "PW.6",
    "PW.7",
    "PW.8",
    "PW.9",
    "RV.1",
    "RV.2",
    "RV.3",
)

ALLOWED_STATUSES: set[str] = {"implemented_baseline", "partial", "planned"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def load_matrix(matrix_path: Path) -> dict[str, Any]:
    if not matrix_path.exists():
        raise FileNotFoundError(f"SSDF matrix file not found: {matrix_path}")
    raw = matrix_path.read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in SSDF matrix: {matrix_path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("SSDF matrix root must be an object")
    return payload


def validate_matrix(matrix: dict[str, Any], *, repo_root: Path) -> None:
    metadata = matrix.get("metadata")
    if not isinstance(metadata, dict):
        raise ValueError("SSDF matrix must include object metadata")

    source_urls = metadata.get("source_urls")
    if not isinstance(source_urls, list) or not source_urls:
        raise ValueError("SSDF metadata.source_urls must be a non-empty array")
    source_urls_text = " ".join(str(item) for item in source_urls)
    if "csrc.nist.gov/pubs/sp/800/218/final" not in source_urls_text:
        raise ValueError("SSDF source_urls must include NIST SP 800-218 final URL")

    practices = matrix.get("practices")
    if not isinstance(practices, list) or not practices:
        raise ValueError("SSDF matrix must include a non-empty practices array")

    seen_ids: set[str] = set()
    for idx, practice in enumerate(practices):
        if not isinstance(practice, dict):
            raise ValueError(f"Practice entry at index {idx} must be an object")

        practice_id = practice.get("practice_id")
        if not isinstance(practice_id, str) or not practice_id.strip():
            raise ValueError(f"Practice entry at index {idx} has invalid practice_id")
        if practice_id in seen_ids:
            raise ValueError(f"Duplicate SSDF practice_id found: {practice_id}")
        seen_ids.add(practice_id)

        status = practice.get("status")
        if status not in ALLOWED_STATUSES:
            raise ValueError(
                f"Practice {practice_id} has invalid status: {status!r}; "
                f"allowed={sorted(ALLOWED_STATUSES)}"
            )

        title = practice.get("title")
        if not isinstance(title, str) or not title.strip():
            raise ValueError(f"Practice {practice_id} is missing title")

        summary = practice.get("summary")
        if not isinstance(summary, str) or not summary.strip():
            raise ValueError(f"Practice {practice_id} is missing summary")

        evidence = practice.get("evidence")
        if not isinstance(evidence, list) or not evidence:
            raise ValueError(f"Practice {practice_id} must include evidence paths")

        for raw_path in evidence:
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise ValueError(f"Practice {practice_id} has invalid evidence path entry")
            rel_path = Path(raw_path)
            if rel_path.is_absolute():
                raise ValueError(
                    f"Practice {practice_id} evidence path must be relative: {raw_path}"
                )
            full_path = repo_root / rel_path
            if not full_path.exists():
                raise ValueError(
                    f"Practice {practice_id} evidence path does not exist: {raw_path}"
                )

    missing = sorted(set(REQUIRED_PRACTICE_IDS) - seen_ids)
    if missing:
        raise ValueError(
            "SSDF matrix missing required practice IDs: " + ", ".join(missing)
        )


def verify_matrix_file(matrix_path: Path) -> int:
    matrix = load_matrix(matrix_path)
    validate_matrix(matrix, repo_root=_repo_root())
    print(
        f"SSDF traceability matrix verified: {matrix_path} "
        f"({len(matrix.get('practices', []))} practices)"
    )
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate SSDF traceability matrix structure and evidence paths."
    )
    parser.add_argument(
        "--matrix-path",
        default=str(DEFAULT_MATRIX_PATH),
        help="Path to the SSDF traceability matrix JSON file.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    matrix_path = Path(str(args.matrix_path))
    return verify_matrix_file(matrix_path)


if __name__ == "__main__":
    raise SystemExit(main())
