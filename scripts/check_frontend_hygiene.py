#!/usr/bin/env python3
"""Frontend hygiene checks for production safety and consistency.

Checks:
- `PUBLIC_API_URL` usage is restricted to approved proxy/config files.
- Every `<button>` explicitly declares `type=...`.
- Every `target="_blank"` anchor includes `rel="noopener noreferrer"`.
- `{@html ...}` usage requires DOMPurify sanitization in the same file.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path


ALLOWED_PUBLIC_API_URL_FILES = {
    Path("dashboard/src/lib/edgeProxy.ts"),
    Path("dashboard/src/routes/api/edge/[...path]/+server.ts"),
    Path("dashboard/src/lib/components/IdentitySettingsCard.svelte"),
}

SOURCE_EXTENSIONS = {".svelte", ".ts"}
TEST_SUFFIXES = (".test.ts", ".spec.ts")

TARGET_BLANK_ANCHOR_PATTERN = re.compile(
    r"<a\b[^>]*\btarget\s*=\s*([\"'])_blank\1[^>]*>", flags=re.IGNORECASE | re.DOTALL
)
BUTTON_WITHOUT_TYPE_PATTERN = re.compile(
    r"<button(?![^>]*\btype\s*=)[^>]*>", flags=re.IGNORECASE | re.DOTALL
)
HTML_INJECTION_PATTERN = re.compile(r"\{@html\b")


@dataclass(frozen=True)
class Issue:
    file_path: Path
    message: str
    snippet: str


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _iter_source_files(repo_root: Path) -> list[Path]:
    src_root = repo_root / "dashboard" / "src"
    files: list[Path] = []
    for path in src_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix not in SOURCE_EXTENSIONS:
            continue
        if path.name.endswith(TEST_SUFFIXES):
            continue
        files.append(path)
    return files


def _has_rel_noopener_noreferrer(anchor_tag: str) -> bool:
    rel_match = re.search(r"\brel\s*=\s*([\"'])(.*?)\1", anchor_tag, flags=re.IGNORECASE | re.DOTALL)
    if not rel_match:
        return False
    rel_tokens = {token.strip().lower() for token in rel_match.group(2).split() if token.strip()}
    return "noopener" in rel_tokens and "noreferrer" in rel_tokens


def run(repo_root: Path) -> int:
    issues: list[Issue] = []
    for source_file in _iter_source_files(repo_root):
        rel_path = source_file.relative_to(repo_root)
        source = _read_text(source_file)

        if "PUBLIC_API_URL" in source and rel_path not in ALLOWED_PUBLIC_API_URL_FILES:
            issues.append(
                Issue(
                    file_path=rel_path,
                    message="PUBLIC_API_URL is only allowed in edge proxy/config files.",
                    snippet="PUBLIC_API_URL",
                )
            )

        for anchor_match in TARGET_BLANK_ANCHOR_PATTERN.finditer(source):
            anchor_tag = anchor_match.group(0).replace("\n", " ")
            if not _has_rel_noopener_noreferrer(anchor_tag):
                issues.append(
                    Issue(
                        file_path=rel_path,
                        message='target="_blank" anchor must include rel="noopener noreferrer".',
                        snippet=anchor_tag,
                    )
                )

        for button_match in BUTTON_WITHOUT_TYPE_PATTERN.finditer(source):
            button_tag = button_match.group(0).replace("\n", " ")
            issues.append(
                Issue(
                    file_path=rel_path,
                    message="<button> must declare an explicit type attribute.",
                    snippet=button_tag,
                )
            )

        if HTML_INJECTION_PATTERN.search(source) and "DOMPurify.sanitize(" not in source:
            issues.append(
                Issue(
                    file_path=rel_path,
                    message="`{@html ...}` requires DOMPurify.sanitize(...) in the same file.",
                    snippet="{@html ...}",
                )
            )

    if issues:
        print(f"[frontend-hygiene] FAIL: {len(issues)} issue(s) found")
        for issue in issues:
            print(f"  - {issue.file_path}: {issue.message} :: {issue.snippet}")
        return 1

    print("[frontend-hygiene] OK: no hygiene violations found")
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
