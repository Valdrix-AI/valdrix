from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from scripts.verify_alertmanager_channels import (
    AlertmanagerVerificationError,
    verify_alertmanager_config,
)


def _load_repo_alertmanager_config() -> dict[str, object]:
    config_path = Path("prometheus/alertmanager.yml")
    return yaml.safe_load(config_path.read_text(encoding="utf-8"))


def test_verify_alertmanager_config_accepts_repo_config() -> None:
    config = _load_repo_alertmanager_config()
    verify_alertmanager_config(config)


def test_verify_alertmanager_config_rejects_missing_transport() -> None:
    config = _load_repo_alertmanager_config()
    assert isinstance(config, dict)
    receivers = config["receivers"]
    assert isinstance(receivers, list)
    for receiver in receivers:
        if receiver.get("name") == "critical-receiver":
            receiver["slack_configs"] = []

    with pytest.raises(AlertmanagerVerificationError, match="critical-receiver"):
        verify_alertmanager_config(config)


def test_verify_alertmanager_config_rejects_wrong_severity_mapping() -> None:
    config = _load_repo_alertmanager_config()
    assert isinstance(config, dict)
    route = config["route"]
    assert isinstance(route, dict)
    routes = route["routes"]
    assert isinstance(routes, list)
    for child in routes:
        if child.get("match", {}).get("severity") == "critical":
            child["receiver"] = "warning-receiver"

    with pytest.raises(AlertmanagerVerificationError, match="Severity route 'critical'"):
        verify_alertmanager_config(config)
