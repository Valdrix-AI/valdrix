from types import SimpleNamespace
from unittest.mock import patch

from app.shared.core.connection_state import (
    infer_is_production_from_name,
    resolve_connection_region,
    resolve_connection_profile,
)


def test_infer_is_production_from_name() -> None:
    assert infer_is_production_from_name("Production AWS") is True
    assert infer_is_production_from_name("dev-sandbox") is False
    assert infer_is_production_from_name("shared-account") is None


def test_resolve_connection_profile_prefers_explicit_flag() -> None:
    connection = SimpleNamespace(
        name="dev-account",
        is_production=True,
        connector_config={"environment": "development"},
    )

    profile = resolve_connection_profile(connection)

    assert profile["is_production"] is True
    assert profile["source"] == "explicit_is_production"


def test_resolve_connection_profile_uses_connector_config_environment() -> None:
    connection = SimpleNamespace(
        name="shared-account",
        connector_config={"environment": "staging", "criticality": "high"},
    )

    profile = resolve_connection_profile(connection)

    assert profile["is_production"] is False
    assert profile["source"] == "explicit_environment"
    assert profile["criticality"] == "high"


def test_resolve_connection_region_aws_uses_configured_default() -> None:
    connection = SimpleNamespace(provider="aws", region="")
    with patch(
        "app.shared.core.connection_state.get_settings",
        return_value=SimpleNamespace(AWS_DEFAULT_REGION="eu-west-1"),
    ):
        assert resolve_connection_region(connection) == "eu-west-1"


def test_resolve_connection_region_aws_global_uses_configured_default() -> None:
    connection = SimpleNamespace(provider="aws", region="global")
    with patch(
        "app.shared.core.connection_state.get_settings",
        return_value=SimpleNamespace(AWS_DEFAULT_REGION="ap-southeast-2"),
    ):
        assert resolve_connection_region(connection) == "ap-southeast-2"


def test_resolve_connection_region_non_aws_defaults_global() -> None:
    connection = SimpleNamespace(provider="azure", region="")
    assert resolve_connection_region(connection) == "global"
