from __future__ import annotations

_MICROSOFT_LICENSE_VENDORS = {
    "microsoft_365",
    "microsoft365",
    "m365",
    "microsoft",
}
_GOOGLE_LICENSE_VENDORS = {
    "google_workspace",
    "googleworkspace",
    "gsuite",
    "google",
}
_GITHUB_LICENSE_VENDORS = {"github", "github_enterprise"}
_SLACK_LICENSE_VENDORS = {"slack", "slack_enterprise"}
_ZOOM_LICENSE_VENDORS = {"zoom"}
_SALESFORCE_LICENSE_VENDORS = {"salesforce", "sfdc"}

_NATIVE_VENDOR_ALIAS_MAP = {
    **{alias: "microsoft_365" for alias in _MICROSOFT_LICENSE_VENDORS},
    **{alias: "google_workspace" for alias in _GOOGLE_LICENSE_VENDORS},
    **{alias: "github" for alias in _GITHUB_LICENSE_VENDORS},
    **{alias: "slack" for alias in _SLACK_LICENSE_VENDORS},
    **{alias: "zoom" for alias in _ZOOM_LICENSE_VENDORS},
    **{alias: "salesforce" for alias in _SALESFORCE_LICENSE_VENDORS},
}


def resolve_native_vendor(*, auth_method: str, vendor: str) -> str | None:
    if auth_method not in {"api_key", "oauth"}:
        return None
    return _NATIVE_VENDOR_ALIAS_MAP.get(vendor)
