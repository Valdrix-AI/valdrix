"""SDK-backed client factories for remediation execution."""

from __future__ import annotations

from typing import Any

from app.modules.optimization.adapters.common.credentials import (
    resolve_azure_credentials,
    resolve_gcp_credentials,
)
from app.shared.adapters.aws_utils import map_aws_credentials


def remediation_action_recoverable_exceptions() -> tuple[type[Exception], ...]:
    base_exceptions: list[type[Exception]] = [
        OSError,
        RuntimeError,
        TypeError,
        ValueError,
        LookupError,
    ]
    try:
        from botocore.exceptions import ClientError
    except ImportError:
        pass
    else:
        base_exceptions.insert(0, ClientError)
    return tuple(base_exceptions)


def create_aws_session() -> Any:
    import aioboto3

    return aioboto3.Session()


def build_aws_client(
    *,
    session: Any,
    service_name: str,
    region: str,
    endpoint_url: str | None,
    raw_credentials: dict[str, Any] | None,
) -> Any:
    kwargs: dict[str, Any] = {"region_name": region}
    if endpoint_url:
        kwargs["endpoint_url"] = endpoint_url
    if raw_credentials:
        kwargs.update(map_aws_credentials(raw_credentials))
    return session.client(service_name, **kwargs)


def create_azure_action_credential(raw_credentials: Any) -> Any:
    return resolve_azure_credentials(raw_credentials)


def create_azure_compute_client(*, credential: Any, subscription_id: str) -> Any:
    from azure.mgmt.compute.aio import ComputeManagementClient

    return ComputeManagementClient(
        credential=credential,
        subscription_id=subscription_id,
    )


def create_gcp_action_credentials(raw_credentials: Any) -> Any:
    return resolve_gcp_credentials(raw_credentials)


def create_gcp_instances_client(raw_credentials: Any) -> Any:
    from google.cloud import compute_v1

    credentials = create_gcp_action_credentials(raw_credentials)
    return compute_v1.InstancesClient(credentials=credentials)

