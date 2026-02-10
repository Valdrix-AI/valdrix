import pytest
from pydantic import ValidationError

from app.schemas.connections import AzureConnectionCreate, GCPConnectionCreate


def test_azure_auth_method_normalizes():
    data = AzureConnectionCreate(
        name="Azure",
        azure_tenant_id="tenant",
        client_id="client",
        subscription_id="sub",
        client_secret="secret",
        auth_method=" SECRET "
    )
    assert data.auth_method == "secret"


def test_azure_secret_required_for_secret_auth():
    with pytest.raises(ValidationError):
        AzureConnectionCreate(
            name="Azure",
            azure_tenant_id="tenant",
            client_id="client",
            subscription_id="sub",
            auth_method="secret"
        )


def test_gcp_invalid_auth_method():
    with pytest.raises(ValidationError):
        GCPConnectionCreate(
            name="GCP",
            project_id="proj-12345",
            auth_method="token"
        )


def test_gcp_secret_requires_json():
    with pytest.raises(ValidationError):
        GCPConnectionCreate(
            name="GCP",
            project_id="proj-12345",
            auth_method="secret"
        )


def test_gcp_invalid_json_rejected():
    with pytest.raises(ValidationError):
        GCPConnectionCreate(
            name="GCP",
            project_id="proj-12345",
            auth_method="secret",
            service_account_json="{bad-json"
        )


def test_gcp_workload_identity_allows_missing_json():
    data = GCPConnectionCreate(
        name="GCP",
        project_id="proj-12345",
        auth_method="workload_identity"
    )
    assert data.service_account_json is None
    assert data.auth_method == "workload_identity"
