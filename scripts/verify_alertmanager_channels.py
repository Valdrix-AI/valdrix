"""Verify Alertmanager channels are actively configured (not silent by default)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

_REQUIRED_RECEIVERS = {
    "default-receiver",
    "critical-receiver",
    "warning-receiver",
    "info-receiver",
}

_TRANSPORT_KEYS = (
    "slack_configs",
    "webhook_configs",
    "email_configs",
    "pagerduty_configs",
    "opsgenie_configs",
    "sns_configs",
    "victorops_configs",
)


class AlertmanagerVerificationError(RuntimeError):
    pass


def _receiver_has_transport(receiver: dict[str, Any]) -> bool:
    return any(bool(receiver.get(key)) for key in _TRANSPORT_KEYS)


def _collect_route_receivers(route: dict[str, Any]) -> list[str]:
    receivers: list[str] = []
    route_receiver = route.get("receiver")
    if isinstance(route_receiver, str) and route_receiver.strip():
        receivers.append(route_receiver.strip())

    nested_routes = route.get("routes")
    if isinstance(nested_routes, list):
        for child in nested_routes:
            if isinstance(child, dict):
                receivers.extend(_collect_route_receivers(child))

    return receivers


def _collect_severity_route_receivers(route: dict[str, Any]) -> dict[str, str]:
    by_severity: dict[str, str] = {}
    nested_routes = route.get("routes")
    if not isinstance(nested_routes, list):
        return by_severity

    for child in nested_routes:
        if not isinstance(child, dict):
            continue
        receiver = child.get("receiver")
        if not isinstance(receiver, str) or not receiver.strip():
            continue

        severity = None
        match = child.get("match")
        if isinstance(match, dict):
            value = match.get("severity")
            if isinstance(value, str) and value.strip():
                severity = value.strip().lower()

        if severity:
            by_severity[severity] = receiver.strip()

    return by_severity


def verify_alertmanager_config(raw_config: dict[str, Any]) -> None:
    if not isinstance(raw_config, dict):
        raise AlertmanagerVerificationError("Alertmanager config must be a mapping.")

    global_config = raw_config.get("global")
    if not isinstance(global_config, dict):
        raise AlertmanagerVerificationError("Missing global config block.")

    has_slack_secret = bool(
        str(global_config.get("slack_api_url_file") or "").strip()
        or str(global_config.get("slack_api_url") or "").strip()
    )
    if not has_slack_secret:
        raise AlertmanagerVerificationError(
            "global.slack_api_url_file (or slack_api_url) must be configured."
        )

    receivers = raw_config.get("receivers")
    if not isinstance(receivers, list) or not receivers:
        raise AlertmanagerVerificationError("Missing receivers list.")

    receiver_by_name: dict[str, dict[str, Any]] = {}
    for receiver in receivers:
        if not isinstance(receiver, dict):
            continue
        name = str(receiver.get("name") or "").strip()
        if not name:
            continue
        receiver_by_name[name] = receiver

    missing_required = sorted(_REQUIRED_RECEIVERS - set(receiver_by_name))
    if missing_required:
        raise AlertmanagerVerificationError(
            f"Missing required receivers: {', '.join(missing_required)}"
        )

    for name in sorted(_REQUIRED_RECEIVERS):
        receiver = receiver_by_name[name]
        if not _receiver_has_transport(receiver):
            raise AlertmanagerVerificationError(
                f"Receiver '{name}' has no active transport configuration."
            )

    route = raw_config.get("route")
    if not isinstance(route, dict):
        raise AlertmanagerVerificationError("Missing top-level route block.")

    default_receiver = str(route.get("receiver") or "").strip()
    if default_receiver != "default-receiver":
        raise AlertmanagerVerificationError(
            "Top-level route receiver must be 'default-receiver'."
        )

    for receiver in _collect_route_receivers(route):
        if receiver not in receiver_by_name:
            raise AlertmanagerVerificationError(
                f"Route references unknown receiver: {receiver}"
            )

    severity_receivers = _collect_severity_route_receivers(route)
    expected_by_severity = {
        "critical": "critical-receiver",
        "warning": "warning-receiver",
        "info": "info-receiver",
    }
    for severity, expected_receiver in expected_by_severity.items():
        actual_receiver = severity_receivers.get(severity)
        if actual_receiver != expected_receiver:
            raise AlertmanagerVerificationError(
                f"Severity route '{severity}' must target '{expected_receiver}', found '{actual_receiver}'."
            )


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise AlertmanagerVerificationError(f"Alertmanager config not found: {path}") from exc
    except yaml.YAMLError as exc:
        raise AlertmanagerVerificationError(f"Invalid YAML in {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise AlertmanagerVerificationError(f"Config root must be a mapping: {path}")
    return raw


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Alertmanager channels are active and wired by severity."
    )
    parser.add_argument(
        "--config-path",
        default="prometheus/alertmanager.yml",
        help="Path to Alertmanager YAML config.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config_path)
    try:
        config = _load_yaml(config_path)
        verify_alertmanager_config(config)
    except AlertmanagerVerificationError as exc:
        print(f"[alertmanager-verify] failed: {exc}")
        return 2

    print(f"[alertmanager-verify] passed: {config_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
