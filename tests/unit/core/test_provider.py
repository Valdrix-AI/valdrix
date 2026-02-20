from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.aws_connection import AWSConnection
from app.shared.core.provider import normalize_provider, resolve_provider_from_connection


def test_normalize_provider_accepts_supported_values() -> None:
    assert normalize_provider("AWS") == "aws"
    assert normalize_provider(" azure ") == "azure"
    assert normalize_provider("gcp") == "gcp"
    assert normalize_provider("saas") == "saas"
    assert normalize_provider("license") == "license"
    assert normalize_provider("platform") == "platform"
    assert normalize_provider("hybrid") == "hybrid"


def test_normalize_provider_rejects_unknown_values() -> None:
    assert normalize_provider("oci") == ""
    assert normalize_provider(None) == ""
    assert normalize_provider("") == ""


def test_resolve_provider_prefers_explicit_supported_provider() -> None:
    conn = SimpleNamespace(provider="AWS")
    assert resolve_provider_from_connection(conn) == "aws"


def test_resolve_provider_preserves_explicit_custom_provider() -> None:
    class AzureConnection:
        provider = "not-a-provider"

    conn = AzureConnection()
    assert resolve_provider_from_connection(conn) == "not-a-provider"


def test_resolve_provider_uses_class_hint_when_explicit_missing() -> None:
    class AzureConnection:
        provider = ""

    conn = AzureConnection()
    assert resolve_provider_from_connection(conn) == "azure"


def test_resolve_provider_supports_mock_spec_class_hint() -> None:
    conn = MagicMock(spec=AWSConnection)
    conn.provider = MagicMock()  # explicit non-string should be ignored
    assert resolve_provider_from_connection(conn) == "aws"
