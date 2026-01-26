from typing import Dict, Any

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
