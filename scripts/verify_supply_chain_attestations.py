"""Verify supply-chain artifact attestations with GitHub CLI."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import subprocess
from collections.abc import Sequence
from pathlib import Path

MIN_GH_VERSION: tuple[int, int, int] = (2, 67, 0)
DEFAULT_SIGNER_WORKFLOW = ".github/workflows/sbom.yml"


def _format_command(cmd: Sequence[str]) -> str:
    return " ".join(shlex.quote(part) for part in cmd)


def _parse_semver(version_text: str) -> tuple[int, int, int]:
    match = re.search(r"\b(\d+)\.(\d+)\.(\d+)\b", version_text)
    if match is None:
        raise ValueError(f"Unable to parse semantic version from: {version_text!r}")
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def check_gh_cli_version() -> tuple[int, int, int]:
    completed = subprocess.run(
        ["gh", "version"],
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"Failed to execute `gh version` for attestation verification: {message}"
        )

    version = _parse_semver(completed.stdout)
    if version < MIN_GH_VERSION:
        raise RuntimeError(
            "GitHub CLI version is too old for safe attestation verification: "
            f"found {version[0]}.{version[1]}.{version[2]}, "
            f"required >= {MIN_GH_VERSION[0]}.{MIN_GH_VERSION[1]}.{MIN_GH_VERSION[2]}"
        )

    attestation_help = subprocess.run(
        ["gh", "attestation", "verify", "--help"],
        check=False,
        capture_output=True,
        text=True,
    )
    if attestation_help.returncode != 0:
        details = attestation_help.stderr.strip() or attestation_help.stdout.strip()
        raise RuntimeError(
            "Installed GitHub CLI does not support `gh attestation verify`: "
            f"{details}"
        )
    return version


def build_verify_command(
    *,
    artifact: Path,
    repo: str,
    signer_workflow: str,
) -> list[str]:
    return [
        "gh",
        "attestation",
        "verify",
        str(artifact),
        "--repo",
        repo,
        "--signer-workflow",
        signer_workflow,
        "--format",
        "json",
    ]


def _assert_verification_output(stdout: str, *, artifact: Path) -> None:
    raw = stdout.strip()
    if not raw:
        raise RuntimeError(
            f"Attestation verification produced empty output for {artifact.as_posix()}"
        )

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Attestation verification did not return JSON for {artifact.as_posix()}"
        ) from exc

    if isinstance(payload, list):
        if len(payload) == 0:
            raise RuntimeError(
                f"Attestation verification returned no entries for {artifact.as_posix()}"
            )
        return

    if isinstance(payload, dict) and payload:
        return

    raise RuntimeError(
        "Attestation verification returned unsupported JSON payload type "
        f"for {artifact.as_posix()}: {type(payload).__name__}"
    )


def verify_attestations(
    *,
    repo: str,
    signer_workflow: str,
    artifacts: Sequence[Path],
    dry_run: bool,
) -> int:
    if not repo.strip():
        raise ValueError("`repo` is required (OWNER/REPO).")
    if not signer_workflow.strip():
        raise ValueError("`signer_workflow` must be non-empty.")
    if not artifacts:
        raise ValueError("At least one --artifact is required.")

    if not dry_run:
        gh_version = check_gh_cli_version()
        print(
            "[attestation-verify] using gh "
            f"{gh_version[0]}.{gh_version[1]}.{gh_version[2]}"
        )

    for artifact in artifacts:
        artifact_path = artifact.resolve()
        if not artifact_path.exists() or not artifact_path.is_file():
            raise FileNotFoundError(
                f"Artifact path does not exist or is not a file: {artifact.as_posix()}"
            )

        cmd = build_verify_command(
            artifact=artifact_path,
            repo=repo,
            signer_workflow=signer_workflow,
        )
        print(f"[attestation-verify] {_format_command(cmd)}")
        if dry_run:
            continue

        completed = subprocess.run(
            cmd,
            check=False,
            capture_output=True,
            text=True,
        )
        if completed.returncode != 0:
            details = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                f"Attestation verification failed for {artifact.as_posix()}: {details}"
            )
        _assert_verification_output(completed.stdout, artifact=artifact_path)
    return 0


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Verify GitHub artifact attestations for supply-chain evidence files."
        )
    )
    parser.add_argument(
        "--repo",
        default=os.environ.get("GITHUB_REPOSITORY", ""),
        help="Repository in OWNER/REPO format (defaults to $GITHUB_REPOSITORY).",
    )
    parser.add_argument(
        "--signer-workflow",
        default=DEFAULT_SIGNER_WORKFLOW,
        help=(
            "Expected signer workflow path used by GitHub attestation verification "
            "(default: .github/workflows/sbom.yml)."
        ),
    )
    parser.add_argument(
        "--artifact",
        action="append",
        default=[],
        metavar="PATH",
        help="Artifact file path to verify; may be supplied multiple times.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print verification commands without executing them.",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = _parse_args(argv)
    artifacts = tuple(Path(item) for item in args.artifact)
    return verify_attestations(
        repo=str(args.repo),
        signer_workflow=str(args.signer_workflow),
        artifacts=artifacts,
        dry_run=bool(args.dry_run),
    )


if __name__ == "__main__":
    raise SystemExit(main())
