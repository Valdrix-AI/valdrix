from __future__ import annotations

from decimal import Decimal

import pytest

import app.modules.enforcement.domain.policy_document as policy_document_module
from app.modules.enforcement.domain.policy_document import (
    PolicyDocument,
    _normalize_json_value,
    canonical_policy_document_payload,
)


def test_normalize_json_value_handles_decimal_and_rejects_unsupported_type() -> None:
    assert _normalize_json_value(Decimal("1.23")) == "1.23"

    with pytest.raises(TypeError, match="Unsupported policy document value type"):
        _normalize_json_value(object())


def test_canonical_policy_document_payload_rejects_invalid_input_types(monkeypatch) -> None:
    with pytest.raises(TypeError, match="Unsupported policy document input type"):
        canonical_policy_document_payload(object())

    monkeypatch.setattr(policy_document_module, "_normalize_json_value", lambda _value: [])
    with pytest.raises(TypeError, match="must be a mapping"):
        canonical_policy_document_payload(PolicyDocument())
