import pytest
from pydantic import ValidationError

from app.schemas.connections import (
    AzureConnectionCreate,
    DiscoveryDeepScanRequest,
    GCPConnectionCreate,
)


def test_azure_auth_method_normalizes():
    data = AzureConnectionCreate(
        name="Azure",
        azure_tenant_id="tenant",
        client_id="client",
        subscription_id="sub",
        client_secret="secret",
        auth_method=" SECRET ",
    )
    assert data.auth_method == "secret"


def test_azure_secret_required_for_secret_auth():
    with pytest.raises(ValidationError):
        AzureConnectionCreate(
            name="Azure",
            azure_tenant_id="tenant",
            client_id="client",
            subscription_id="sub",
            auth_method="secret",
        )


def test_gcp_invalid_auth_method():
    with pytest.raises(ValidationError):
        GCPConnectionCreate(name="GCP", project_id="proj-12345", auth_method="token")


def test_gcp_secret_requires_json():
    with pytest.raises(ValidationError):
        GCPConnectionCreate(name="GCP", project_id="proj-12345", auth_method="secret")


def test_gcp_invalid_json_rejected():
    with pytest.raises(ValidationError):
        GCPConnectionCreate(
            name="GCP",
            project_id="proj-12345",
            auth_method="secret",
            service_account_json="{bad-json",
        )


def test_gcp_workload_identity_allows_missing_json():
    data = GCPConnectionCreate(
        name="GCP", project_id="proj-12345", auth_method="workload_identity"
    )
    assert data.service_account_json is None
    assert data.auth_method == "workload_identity"


def test_deep_scan_request_normalizes_domain_and_provider() -> None:
    request = DiscoveryDeepScanRequest(
        domain=" Example.COM. ",
        idp_provider=" GOOGLE_WORKSPACE ",
    )
    assert request.domain == "example.com"
    assert request.idp_provider == "google_workspace"


def test_deep_scan_request_requires_fqdn_domain() -> None:
    with pytest.raises(
        ValidationError, match="domain must be a fully qualified domain"
    ):
        DiscoveryDeepScanRequest(
            domain="localhost",
            idp_provider="microsoft_365",
        )


def test_deep_scan_request_rejects_unsupported_provider() -> None:
    with pytest.raises(
        ValidationError, match="idp_provider must be microsoft_365 or google_workspace"
    ):
        DiscoveryDeepScanRequest(
            domain="example.com",
            idp_provider="okta",
        )
