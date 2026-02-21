#!/usr/bin/env python3
"""Validate frontend API paths against backend router declarations.

This checker is evidence-focused:
- extracts backend paths from FastAPI router decorators + app router prefixes
- extracts frontend paths from edgeApiPath(...) and `${EDGE_API_BASE}/...` usages
- fails if a frontend path cannot be matched to any backend path template
"""

from __future__ import annotations

import argparse
import re
import sys
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FrontendPathRef:
    path: str
    file_path: Path
    expression: str


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def parse_backend_paths(repo_root: Path) -> set[str]:
    # Provide safe defaults for strict settings validation in local/CI audits.
    os.environ.setdefault("CSRF_SECRET_KEY", "abcdefghijklmnopqrstuvwxyz123456")
    os.environ.setdefault("ENCRYPTION_KEY", "abcdefghijklmnopqrstuvwxyz123456")
    os.environ.setdefault("SUPABASE_JWT_SECRET", "abcdefghijklmnopqrstuvwxyz123456")
    os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "abcdefghijklmnopqrstuvwxyz123456")
    os.environ.setdefault("SUPABASE_ANON_KEY", "abcdefghijklmnopqrstuvwxyz123456")
    os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
    os.environ.setdefault("KDF_SALT", "S0RGX1NBTFRfRk9SX1RFU1RJTkdfMzJfQllURVNfT0s=")
    os.environ.setdefault("CORS_ORIGINS", "[\"http://localhost:4173\"]")

    sys.path.insert(0, str(repo_root))
    from app.main import app  # pylint: disable=import-outside-toplevel

    backend_paths: set[str] = set()
    for route in app.routes:
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if not path or not methods:
            continue
        if any(method in {"GET", "POST", "PUT", "PATCH", "DELETE"} for method in methods):
            backend_paths.add(path)
    return backend_paths


EDGE_CALL_PATTERN = re.compile(r"edgeApiPath\(\s*([\"'`])(.*?)\1\s*\)", flags=re.DOTALL)
EDGE_BASE_PATTERN = re.compile(r"\$\{EDGE_API_BASE\}([^\"'`\n\r]*)")
TEMPLATE_EXPR_PATTERN = re.compile(r"\$\{[^}]+\}")


def normalize_front_path(raw_path: str) -> str:
    path = raw_path.strip()
    if not path:
        return ""
    path = TEMPLATE_EXPR_PATTERN.sub("{param}", path)
    path = path.split("?", 1)[0]
    path = re.sub(r"/{2,}", "/", path)
    if not path.startswith("/"):
        path = f"/{path}"
    return path


def parse_frontend_paths(repo_root: Path) -> list[FrontendPathRef]:
    src_root = repo_root / "dashboard/src"
    refs: list[FrontendPathRef] = []
    source_files = list(src_root.rglob("*.svelte")) + list(src_root.rglob("*.ts"))
    for file_path in source_files:
        if file_path.name.endswith(".test.ts"):
            continue
        source = _read_text(file_path)

        for match in EDGE_CALL_PATTERN.finditer(source):
            raw = match.group(2)
            normalized = normalize_front_path(raw)
            if not normalized or normalized == "/":
                continue
            # edgeApiPath('/foo') maps to backend '/api/v1/foo'
            backend_style = f"/api/v1{normalized}" if not normalized.startswith("/api/v1") else normalized
            refs.append(
                FrontendPathRef(
                    path=backend_style,
                    file_path=file_path.relative_to(repo_root),
                    expression=match.group(0).replace("\n", " "),
                )
            )

        for match in EDGE_BASE_PATTERN.finditer(source):
            raw = match.group(1)
            normalized = normalize_front_path(raw)
            if not normalized or normalized == "/" or not normalized.startswith("/"):
                continue
            backend_style = f"/api/v1{normalized}" if not normalized.startswith("/api/v1") else normalized
            refs.append(
                FrontendPathRef(
                    path=backend_style,
                    file_path=file_path.relative_to(repo_root),
                    expression=match.group(0).replace("\n", " "),
                )
            )

        # buildUnitEconomicsUrl(base, ...) is currently used with EDGE_API_BASE.
        if "buildUnitEconomicsUrl(EDGE_API_BASE" in source:
            refs.append(
                FrontendPathRef(
                    path="/api/v1/costs/unit-economics",
                    file_path=file_path.relative_to(repo_root),
                    expression="buildUnitEconomicsUrl(EDGE_API_BASE, ...)",
                )
            )

        if "buildCompliancePackPath(" in source:
            refs.append(
                FrontendPathRef(
                    path="/api/v1/audit/compliance-pack",
                    file_path=file_path.relative_to(repo_root),
                    expression="buildCompliancePackPath(...)",
                )
            )

        if "buildFocusExportPath(" in source:
            refs.append(
                FrontendPathRef(
                    path="/api/v1/costs/export/focus",
                    file_path=file_path.relative_to(repo_root),
                    expression="buildFocusExportPath(...)",
                )
            )

    return refs


def path_matches(front_path: str, backend_path: str) -> bool:
    if front_path == backend_path:
        return True
    front_parts = [p for p in front_path.split("/") if p]
    back_parts = [p for p in backend_path.split("/") if p]
    if len(front_parts) != len(back_parts):
        return False
    for front_part, back_part in zip(front_parts, back_parts, strict=True):
        if back_part.startswith("{") and back_part.endswith("}"):
            continue
        if front_part != back_part:
            return False
    return True


def run(repo_root: Path) -> int:
    backend_paths = parse_backend_paths(repo_root)
    frontend_refs = parse_frontend_paths(repo_root)

    # Keep only API/lifecycle routes we intentionally support from frontend.
    relevant_frontend_refs = [
        ref
        for ref in frontend_refs
        if ref.path.startswith("/api/v1/") or ref.path.startswith("/health/")
    ]
    missing: list[FrontendPathRef] = []
    for ref in relevant_frontend_refs:
        if not any(path_matches(ref.path, backend_path) for backend_path in backend_paths):
            missing.append(ref)

    print(
        f"[api-contract] backend paths: {len(backend_paths)} | frontend references: {len(relevant_frontend_refs)}"
    )
    if missing:
        print(f"[api-contract] missing backend matches: {len(missing)}")
        for ref in missing:
            print(f"  - {ref.path} :: {ref.file_path} :: {ref.expression}")
        return 1

    print("[api-contract] OK: all frontend API paths match backend-declared routes.")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        default=str(Path(__file__).resolve().parents[1]),
        help="Repository root path",
    )
    args = parser.parse_args()
    return run(Path(args.repo_root).resolve())


if __name__ == "__main__":
    raise SystemExit(main())
