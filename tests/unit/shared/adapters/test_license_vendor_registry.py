from app.shared.adapters.license_vendor_registry import resolve_native_vendor


def test_resolve_native_vendor_supports_aliases() -> None:
    assert resolve_native_vendor(auth_method="oauth", vendor="m365") == "microsoft_365"
    assert resolve_native_vendor(auth_method="api_key", vendor="gsuite") == "google_workspace"
    assert resolve_native_vendor(auth_method="oauth", vendor="sfdc") == "salesforce"


def test_resolve_native_vendor_rejects_manual_mode_and_unknown_vendor() -> None:
    assert resolve_native_vendor(auth_method="manual", vendor="m365") is None
    assert resolve_native_vendor(auth_method="oauth", vendor="custom") is None
