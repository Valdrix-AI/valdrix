import aioboto3
from typing import Any, Dict, Optional
from botocore.config import Config as BotoConfig
from app.models.aws_connection import AWSConnection

# Standardized boto config with timeouts to prevent indefinite hangs
DEFAULT_BOTO_CONFIG = BotoConfig(
    read_timeout=30,
    connect_timeout=10,
    retries={"max_attempts": 3, "mode": "adaptive"}
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

async def get_aws_client(
    service_name: str, 
    connection: Optional[AWSConnection] = None,
    credentials: Optional[Dict[str, str]] = None,
    region: Optional[str] = None
) -> Any:
    """
    Returns an async AWS client for the specified service.
    Handles temporary credential injection if a connection is provided.
    """
    session = get_boto_session()
    
    kwargs = {
        "service_name": service_name,
        "config": DEFAULT_BOTO_CONFIG
    }
    
    if region:
        kwargs["region_name"] = region
    elif connection:
        kwargs["region_name"] = connection.region
        
    if connection:
        from app.shared.adapters.aws_multitenant import MultiTenantAWSAdapter
        adapter = MultiTenantAWSAdapter(connection)
        creds = await adapter.get_credentials()
        kwargs.update(map_aws_credentials(creds))
    elif credentials:
        kwargs.update(map_aws_credentials(credentials))
        
    return session.client(**kwargs)
