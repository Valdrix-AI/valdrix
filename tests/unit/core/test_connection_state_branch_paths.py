from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.shared.core.connection_state import (
    _coerce_bool,
    _coerce_criticality,
    _default_aws_region,
    _extract_profile_value,
    infer_is_production_from_name,
    is_connection_active,
    resolve_connection_profile,
    resolve_connection_region,
)


def test_default_aws_region_falls_back_when_setting_empty() -> None:
    with patch(
        "app.shared.core.connection_state.get_settings",
        return_value=SimpleNamespace(AWS_DEFAULT_REGION="   "),
    ):
        assert _default_aws_region() == "us-east-1"


def test_coerce_bool_supports_numeric_and_string_values() -> None:
    assert _coerce_bool(True) is True
    assert _coerce_bool(1) is True
    assert _coerce_bool(0) is False
    assert _coerce_bool(2) is None
    assert _coerce_bool(" yes ") is True
    assert _coerce_bool("off") is False
    assert _coerce_bool("maybe") is None


def test_coerce_criticality_rejects_unknown_value() -> None:
    assert _coerce_criticality("critical") == "critical"
    assert _coerce_criticality("urgent") is None


def test_extract_profile_value_falls_back_to_connector_config_and_none() -> None:
    connection = SimpleNamespace(environment=None, connector_config={"environment": "prod"})
    assert _extract_profile_value(connection, "environment") == "prod"

    missing = SimpleNamespace(connector_config="not-a-dict")
    assert _extract_profile_value(missing, "environment") is None


def test_infer_is_production_from_name_empty_returns_none() -> None:
    assert infer_is_production_from_name("   ") is None


def test_resolve_connection_profile_uses_production_environment_and_name_inference() -> None:
    env_connection = SimpleNamespace(
        name="ignored-name",
        connector_config={"environment": "production", "criticality": "urgent"},
    )
    env_profile = resolve_connection_profile(env_connection)
    assert env_profile == {
        "is_production": True,
        "criticality": None,
        "source": "explicit_environment",
    }

    name_connection = SimpleNamespace(name="prod-analytics-account", connector_config={})
    name_profile = resolve_connection_profile(name_connection)
    assert name_profile["is_production"] is True
    assert name_profile["source"] == "name_inference"


def test_is_connection_active_covers_status_and_is_active_fallbacks() -> None:
    assert is_connection_active(SimpleNamespace(status="ACTIVE")) is True
    assert is_connection_active(SimpleNamespace(status="disabled")) is False
    assert is_connection_active(SimpleNamespace(status=True)) is True
    assert is_connection_active(SimpleNamespace(status=False)) is False
    assert is_connection_active(SimpleNamespace(is_active=True)) is True
    assert is_connection_active(SimpleNamespace(is_active=False)) is False
    assert is_connection_active(SimpleNamespace()) is True

    instrumented_like = type("InstrumentedAttribute", (), {})()
    assert is_connection_active(SimpleNamespace(is_active=instrumented_like)) is True

    assert is_connection_active(SimpleNamespace(is_active=MagicMock())) is True


def test_resolve_connection_region_aws_preserves_concrete_region() -> None:
    connection = SimpleNamespace(provider="aws", region="us-west-2")
    assert resolve_connection_region(connection) == "us-west-2"
