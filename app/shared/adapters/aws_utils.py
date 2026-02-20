import aioboto3
from typing import Any, Dict, Optional
from botocore.config import Config as BotoConfig
from app.models.aws_connection import AWSConnection
from app.shared.core.config import get_settings

# Standardized boto config with timeouts to prevent indefinite hangs
DEFAULT_BOTO_CONFIG = BotoConfig(
    read_timeout=30, connect_timeout=10, retries={"max_attempts": 3, "mode": "adaptive"}
)

# Mapping CamelCase to snake_case for aioboto3/boto3 credentials
AWS_CREDENTIAL_MAPPING = {
    "AccessKeyId": "aws_access_key_id",
    "SecretAccessKey": "aws_secret_access_key",
    "SessionToken": "aws_session_token",
    "aws_access_key_id": "aws_access_key_id",
    "aws_secret_access_key": "aws_secret_access_key",
    "aws_session_token": "aws_session_token",
}


def map_aws_credentials(credentials: Dict[str, str]) -> Dict[str, str]:
    """
    Maps credentials dictionary to valid boto3/aioboto3 kwargs.
    Handles both CamelCase (AWS standard) and snake_case (boto3) keys.
    """
    mapped: Dict[str, str] = {}
    if not credentials:
        return mapped

    for src, dst in AWS_CREDENTIAL_MAPPING.items():
        if src in credentials:
            mapped[dst] = credentials[src]

    return mapped


def get_boto_session() -> aioboto3.Session:
    """Returns a centralized aioboto3 session."""
    return aioboto3.Session()


def resolve_aws_region_hint(region: Any) -> str:
    """
    Resolve AWS region hints to a concrete supported region.

    - Explicit non-global region wins (if supported list is empty or includes it)
    - Otherwise use configured AWS_DEFAULT_REGION (if valid)
    - Final fallback is us-east-1 for endpoint compatibility
    """
    settings = get_settings()
    supported = {
        str(r).strip()
        for r in getattr(settings, "AWS_SUPPORTED_REGIONS", [])
        if str(r).strip()
    }
    configured_default = str(getattr(settings, "AWS_DEFAULT_REGION", "") or "").strip()
    candidate = str(region or "").strip()

    if candidate and candidate != "global":
        if not supported or candidate in supported:
            return candidate

    if configured_default and (not supported or configured_default in supported):
        return configured_default

    return "us-east-1"


async def get_aws_client(
    service_name: str,
    connection: Optional[AWSConnection] = None,
    credentials: Optional[Dict[str, str]] = None,
    region: Optional[str] = None,
) -> Any:
    """
    Returns an async AWS client for the specified service.
    Handles temporary credential injection if a connection is provided.
    """
    session = get_boto_session()

    kwargs = {"service_name": service_name, "config": DEFAULT_BOTO_CONFIG}

    if region:
        kwargs["region_name"] = resolve_aws_region_hint(region)
    elif connection:
        kwargs["region_name"] = resolve_aws_region_hint(connection.region)

    if connection:
        from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
        from app.shared.core.credentials import AWSCredentials

        resolved_region = resolve_aws_region_hint(connection.region)
        creds = AWSCredentials(
            account_id=connection.aws_account_id,
            role_arn=connection.role_arn,
            external_id=connection.external_id,
            region=resolved_region,
            cur_bucket_name=connection.cur_bucket_name,
            cur_report_name=connection.cur_report_name,
            cur_prefix=connection.cur_prefix,
        )
        adapter = MultiTenantAWSAdapter(creds)
        creds = await adapter.get_credentials()
        kwargs.update(map_aws_credentials(creds))
    elif credentials:
        kwargs.update(map_aws_credentials(credentials))

    return session.client(**kwargs)

def map_aws_connection_to_credentials(connection: AWSConnection) -> Any:
    """
    Helper to convert an AWSConnection SQLAlchemy model to AWSCredentials Pydantic model.
    """
    from app.shared.core.credentials import AWSCredentials

    resolved_region = resolve_aws_region_hint(connection.region)

    return AWSCredentials(
        account_id=connection.aws_account_id,
        role_arn=connection.role_arn,
        external_id=connection.external_id,
        region=resolved_region,
        tenant_id=connection.tenant_id,
        cur_bucket_name=connection.cur_bucket_name,
        cur_report_name=connection.cur_report_name,
        cur_prefix=connection.cur_prefix,
    )
