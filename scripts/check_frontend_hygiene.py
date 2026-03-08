#!/usr/bin/env python3
"""Frontend hygiene checks for production safety and consistency.

Checks:
- `PUBLIC_API_URL` usage is restricted to approved proxy/config files.
- Every `<button>` explicitly declares `type=...`.
- Every `target="_blank"` anchor includes `rel="noopener noreferrer"`.
- `{@html ...}` usage requires DOMPurify sanitization in the same file.
- `dashboard/svelte.config.js` must not allow CSP `unsafe-inline`.
- `dashboard/src/app.html` must not use manual inline style attributes.
- Svelte transition directives are disallowed because they require inline `<style>` tags under strict CSP.
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
    Path("dashboard/src/lib/components/IdentitySettingsCardContent.svelte"),
}

SOURCE_EXTENSIONS = {".svelte", ".ts"}
TEST_SUFFIXES = (".test.ts", ".spec.ts", ".test.setup.ts")

TARGET_BLANK_ANCHOR_PATTERN = re.compile(
    r"<a\b[^>]*\btarget\s*=\s*([\"'])_blank\1[^>]*>", flags=re.IGNORECASE | re.DOTALL
)
BUTTON_WITHOUT_TYPE_PATTERN = re.compile(
    r"<button(?![^>]*\btype\s*=)[^>]*>", flags=re.IGNORECASE | re.DOTALL
)
HTML_INJECTION_PATTERN = re.compile(r"\{@html\b")
STYLE_BLOCK_PATTERN = re.compile(r"<style\b[^>]*>.*?</style>", flags=re.IGNORECASE | re.DOTALL)
SVELTE_TRANSITION_DIRECTIVE_PATTERN = re.compile(
    r"<[^>]*\b(?:transition:|in:|out:|animate:)[^>]*>",
    flags=re.IGNORECASE | re.DOTALL,
)
INLINE_STYLE_ATTRIBUTE_PATTERN = re.compile(r"\bstyle\s*=", flags=re.IGNORECASE)
UNSAFE_INLINE_PATTERN = re.compile(r"['\"]unsafe-inline['\"]")


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


def _strip_style_blocks(source: str) -> str:
    return STYLE_BLOCK_PATTERN.sub("", source)


def run(repo_root: Path) -> int:
    issues: list[Issue] = []
    svelte_config = repo_root / "dashboard" / "svelte.config.js"
    app_html = repo_root / "dashboard" / "src" / "app.html"

    if svelte_config.exists():
        config_source = _read_text(svelte_config)
        if UNSAFE_INLINE_PATTERN.search(config_source):
            issues.append(
                Issue(
                    file_path=svelte_config.relative_to(repo_root),
                    message="dashboard CSP must not allow unsafe-inline.",
                    snippet="unsafe-inline",
                )
            )

    if app_html.exists():
        app_html_source = _read_text(app_html)
        if INLINE_STYLE_ATTRIBUTE_PATTERN.search(app_html_source):
            issues.append(
                Issue(
                    file_path=app_html.relative_to(repo_root),
                    message="dashboard app.html must not include manual inline styles.",
                    snippet='style="..."',
                )
            )

    for source_file in _iter_source_files(repo_root):
        rel_path = source_file.relative_to(repo_root)
        source = _read_text(source_file)
        source_without_style_blocks = _strip_style_blocks(source)

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

        if source_file.suffix == ".svelte":
            for directive_match in SVELTE_TRANSITION_DIRECTIVE_PATTERN.finditer(
                source_without_style_blocks
            ):
                directive = directive_match.group(0).replace("\n", " ")
                issues.append(
                    Issue(
                        file_path=rel_path,
                        message=(
                            "Svelte transition directives are disallowed under strict CSP; "
                            "use CSS animations instead."
                        ),
                        snippet=directive,
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
