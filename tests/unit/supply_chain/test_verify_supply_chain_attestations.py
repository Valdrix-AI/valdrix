from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

from scripts.verify_supply_chain_attestations import (
    MIN_GH_VERSION,
    build_verify_command,
    check_gh_cli_version,
    main,
    verify_attestations,
)


def _write(path: Path, content: str = "x") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_build_verify_command_includes_repo_workflow_and_json_output() -> None:
    cmd = build_verify_command(
        artifact=Path("/tmp/sbom.json"),
        repo="acme/valdrics",
        signer_workflow=".github/workflows/sbom.yml",
    )

    assert cmd[:4] == ["gh", "attestation", "verify", "/tmp/sbom.json"]
    assert "--repo" in cmd
    assert "acme/valdrics" in cmd
    assert "--signer-workflow" in cmd
    assert ".github/workflows/sbom.yml" in cmd
    assert cmd[-2:] == ["--format", "json"]


def test_verify_attestations_requires_repo() -> None:
    artifact = Path("artifact.json")
    _write(artifact)

    with pytest.raises(ValueError, match="repo"):
        verify_attestations(
            repo="",
            signer_workflow=".github/workflows/sbom.yml",
            artifacts=(artifact,),
            dry_run=True,
        )


def test_verify_attestations_requires_at_least_one_artifact() -> None:
    with pytest.raises(ValueError, match="At least one --artifact"):
        verify_attestations(
            repo="acme/valdrics",
            signer_workflow=".github/workflows/sbom.yml",
            artifacts=(),
            dry_run=True,
        )


def test_verify_attestations_rejects_missing_artifact_file() -> None:
    with pytest.raises(FileNotFoundError, match="Artifact path does not exist"):
        verify_attestations(
            repo="acme/valdrics",
            signer_workflow=".github/workflows/sbom.yml",
            artifacts=(Path("missing.json"),),
            dry_run=True,
        )


def test_check_gh_cli_version_rejects_old_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _fake_run(
        cmd: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert cmd == ["gh", "version"]
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="gh version 2.66.0 (2025-01-01)\n",
            stderr="",
        )

    monkeypatch.setattr(
        "scripts.verify_supply_chain_attestations.subprocess.run",
        _fake_run,
    )

    with pytest.raises(RuntimeError, match="too old"):
        check_gh_cli_version()


def test_check_gh_cli_version_rejects_missing_attestation_subcommand(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def _fake_run(
        cmd: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls["count"] += 1
        if calls["count"] == 1:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="gh version 2.67.0 (2025-05-06)\n",
                stderr="",
            )
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=1,
            stdout="",
            stderr='unknown command "attestation" for "gh"',
        )

    monkeypatch.setattr(
        "scripts.verify_supply_chain_attestations.subprocess.run",
        _fake_run,
    )

    with pytest.raises(RuntimeError, match="does not support"):
        check_gh_cli_version()


def test_check_gh_cli_version_accepts_supported_cli(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = {"count": 0}

    def _fake_run(
        cmd: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        calls["count"] += 1
        if calls["count"] == 1:
            return subprocess.CompletedProcess(
                args=cmd,
                returncode=0,
                stdout="gh version 2.67.0 (2025-05-06)\n",
                stderr="",
            )
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="Verify artifact attestations",
            stderr="",
        )

    monkeypatch.setattr(
        "scripts.verify_supply_chain_attestations.subprocess.run",
        _fake_run,
    )

    assert check_gh_cli_version() == (2, 67, 0)


def test_verify_attestations_executes_gh_verify_for_each_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact_one = tmp_path / "sbom-one.json"
    artifact_two = tmp_path / "sbom-two.json"
    _write(artifact_one, '{"a":1}')
    _write(artifact_two, '{"b":2}')

    commands: list[list[str]] = []

    def _fake_run(
        cmd: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        assert check is False
        assert capture_output is True
        assert text is True
        commands.append(cmd)
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout='[{"verificationResult":{"verifiedTimestamps":[]}}]',
            stderr="",
        )

    monkeypatch.setattr(
        "scripts.verify_supply_chain_attestations.check_gh_cli_version",
        lambda: MIN_GH_VERSION,
    )
    monkeypatch.setattr(
        "scripts.verify_supply_chain_attestations.subprocess.run",
        _fake_run,
    )

    exit_code = verify_attestations(
        repo="acme/valdrics",
        signer_workflow=".github/workflows/sbom.yml",
        artifacts=(artifact_one, artifact_two),
        dry_run=False,
    )

    assert exit_code == 0
    assert len(commands) == 2
    assert commands[0][0:3] == ["gh", "attestation", "verify"]
    assert commands[1][0:3] == ["gh", "attestation", "verify"]
    assert str(artifact_one.resolve()) in commands[0]
    assert str(artifact_two.resolve()) in commands[1]


def test_verify_attestations_rejects_empty_verification_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    artifact = tmp_path / "sbom.json"
    _write(artifact, '{"a":1}')

    def _fake_run(
        cmd: list[str],
        *,
        check: bool,
        capture_output: bool,
        text: bool,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(
            args=cmd,
            returncode=0,
            stdout="[]",
            stderr="",
        )

    monkeypatch.setattr(
        "scripts.verify_supply_chain_attestations.check_gh_cli_version",
        lambda: MIN_GH_VERSION,
    )
    monkeypatch.setattr(
        "scripts.verify_supply_chain_attestations.subprocess.run",
        _fake_run,
    )

    with pytest.raises(RuntimeError, match="no entries"):
        verify_attestations(
            repo="acme/valdrics",
            signer_workflow=".github/workflows/sbom.yml",
            artifacts=(artifact,),
            dry_run=False,
        )


def test_main_dry_run_succeeds(tmp_path: Path) -> None:
    artifact = tmp_path / "sbom.json"
    _write(artifact, '{"a":1}')

    exit_code = main(
        [
            "--repo",
            "acme/valdrics",
            "--signer-workflow",
            ".github/workflows/sbom.yml",
            "--artifact",
            str(artifact),
            "--dry-run",
        ]
    )
    assert exit_code == 0
