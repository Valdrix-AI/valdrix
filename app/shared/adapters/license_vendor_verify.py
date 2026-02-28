from __future__ import annotations

from app.shared.core.exceptions import ExternalAPIError

from app.shared.adapters.license_vendor_types import LicenseVendorRuntime


async def verify_microsoft_365(runtime: LicenseVendorRuntime) -> None:
    token = runtime._resolve_api_key()
    await runtime._get_json(
        "https://graph.microsoft.com/v1.0/subscribedSkus",
        headers={"Authorization": f"Bearer {token}"},
    )


async def verify_google_workspace(runtime: LicenseVendorRuntime) -> None:
    token = runtime._resolve_api_key()
    await runtime._get_json(
        "https://admin.googleapis.com/admin/directory/v1/customer/my_customer",
        headers={"Authorization": f"Bearer {token}"},
    )


async def verify_github(runtime: LicenseVendorRuntime) -> None:
    token = runtime._resolve_api_key()
    await runtime._get_json(
        "https://api.github.com/user",
        headers={
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        },
    )


async def verify_slack(runtime: LicenseVendorRuntime) -> None:
    token = runtime._resolve_api_key()
    payload = await runtime._get_json(
        "https://slack.com/api/auth.test",
        headers={"Authorization": f"Bearer {token}"},
    )
    if not payload.get("ok"):
        raise ExternalAPIError(
            f"Slack auth.test failed: {payload.get('error') or 'unknown_error'}"
        )


async def verify_zoom(runtime: LicenseVendorRuntime) -> None:
    token = runtime._resolve_api_key()
    await runtime._get_json(
        "https://api.zoom.us/v2/users/me",
        headers={"Authorization": f"Bearer {token}"},
    )


async def verify_salesforce(runtime: LicenseVendorRuntime) -> None:
    token = runtime._resolve_api_key()
    instance_url = runtime._salesforce_instance_url()
    api_version = runtime._connector_config.get("salesforce_api_version", "v60.0")
    await runtime._get_json(
        f"{instance_url}/services/data/{api_version}/limits",
        headers={"Authorization": f"Bearer {token}"},
    )
