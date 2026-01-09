"""
AWS Connection Router

Handles CRUD operations for AWS account connections.
Each endpoint enforces tenant isolation via JWT auth.

Endpoints:
- POST /connections/aws - Register new connection
- GET /connections/aws - List tenant's connections
- GET /connections/aws/{id} - Get specific connection
- POST /connections/aws/{id}/verify - Test connection works
- DELETE /connections/aws/{id} - Remove connection
"""

from uuid import UUID
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field
import structlog
import boto3
from botocore.exceptions import ClientError

from app.db.session import get_db
from app.models.aws_connection import AWSConnection
from app.core.config import get_settings
from app.core.auth import get_current_user, CurrentUser

logger = structlog.get_logger()
router = APIRouter(prefix="/connections/aws", tags=["connections"])


# ============================================================
# Pydantic Schemas
# ============================================================

class AWSConnectionCreate(BaseModel):
    """Request body for creating a new AWS connection."""
    aws_account_id: str = Field(..., pattern=r"^\d{12}$", description="12-digit AWS account ID")
    role_arn: str = Field(..., description="Full ARN of the IAM role to assume")
    region: str = Field(default="us-east-1", description="AWS region for Cost Explorer")


class AWSConnectionResponse(BaseModel):
    """Response body for AWS connection."""
    id: UUID
    aws_account_id: str
    role_arn: str
    external_id: str
    region: str
    status: str
    last_verified_at: datetime | None
    error_message: str | None
    created_at: datetime
    
    class Config:
        from_attributes = True


class AWSConnectionSetup(BaseModel):
    """Response for initial setup - includes external_id for CloudFormation."""
    external_id: str
    cloudformation_url: str
    instructions: str


# ============================================================
# Helper Functions
# ============================================================

async def get_tenant_id_from_auth() -> UUID:
    """
    TODO: Extract tenant_id from JWT token.
    For now, return a placeholder. This MUST be implemented properly.
    """
    # In production, this would decode the JWT and return the tenant_id
    # For development, we'll need to implement this with Supabase auth
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="Auth integration required. Implement JWT tenant extraction."
    )


def verify_aws_connection(role_arn: str, external_id: str) -> tuple[bool, str | None]:
    """
    Test if we can assume the IAM role.
    
    Returns:
        (success: bool, error_message: str | None)
    """
    try:
        sts_client = boto3.client("sts")
        
        # Try to assume the role
        response = sts_client.assume_role(
            RoleArn=role_arn,
            RoleSessionName="CloudSentinelVerification",
            ExternalId=external_id,
            DurationSeconds=900,  # Minimum duration
        )
        
        # If successful, we got temporary credentials
        logger.info("aws_connection_verified", role_arn=role_arn)
        return True, None
        
    except ClientError as e:
        error_code = e.response.get("Error", {}).get("Code", "Unknown")
        error_message = e.response.get("Error", {}).get("Message", str(e))
        
        logger.warning(
            "aws_connection_verification_failed",
            role_arn=role_arn,
            error_code=error_code,
            error_message=error_message,
        )
        
        return False, f"{error_code}: {error_message}"


# ============================================================
# API Endpoints
# ============================================================

@router.post("/setup", response_model=AWSConnectionSetup)
async def get_setup_info():
    """
    Get the external ID and CloudFormation URL for setting up a new connection.
    
    This is called BEFORE the user creates the IAM role.
    The external_id must be included in the role's trust policy.
    """
    external_id = AWSConnection.generate_external_id()
    
    # Build CloudFormation quick-create URL
    settings = get_settings()
    template_url = "https://raw.githubusercontent.com/daretechie/CloudSentinel-AI/main/cloudformation/cloudsentinel-role.yaml"
    
    cf_url = (
        f"https://console.aws.amazon.com/cloudformation/home#/stacks/create/review"
        f"?templateURL={template_url}"
        f"&stackName=CloudSentinelRole"
        f"&param_ExternalId={external_id}"
    )
    
    return AWSConnectionSetup(
        external_id=external_id,
        cloudformation_url=cf_url,
        instructions=(
            "1. Click the CloudFormation URL to deploy the IAM role\n"
            "2. Confirm the stack name and external ID\n"
            "3. Check the IAM capabilities box and create the stack\n"
            "4. Copy the RoleArn from the stack outputs\n"
            "5. Come back here and register the connection"
        )
    )


@router.post("", response_model=AWSConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_connection(
    data: AWSConnectionCreate,
    current_user: CurrentUser = Depends(get_current_user),  # <-- Auth dependency
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new AWS connection after the user has created the IAM role.
    
    Security:
    - Requires valid Supabase JWT
    - Creates connection tied to user's tenant_id
    - Validates AWS account ID format (12 digits via Pydantic)
    """
    # Check if connection already exists for this tenant + account
    existing = await db.execute(
        select(AWSConnection).where(
            AWSConnection.tenant_id == current_user.tenant_id,
            AWSConnection.aws_account_id == data.aws_account_id,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Connection for AWS account {data.aws_account_id} already exists"
        )
    
    # Create new connection
    connection = AWSConnection(
        tenant_id=current_user.tenant_id,
        aws_account_id=data.aws_account_id,
        role_arn=data.role_arn,
        external_id=AWSConnection.generate_external_id(),
        region=data.region,
        status="pending",
    )
    
    db.add(connection)
    await db.commit()
    await db.refresh(connection)
    
    logger.info(
        "aws_connection_created",
        connection_id=str(connection.id),
        tenant_id=str(current_user.tenant_id),
        aws_account_id=data.aws_account_id,
    )
    
    return connection


@router.get("", response_model=list[AWSConnectionResponse])
async def list_connections(
    current_user: CurrentUser = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all AWS connections for the current tenant.
    
    Security:
    - Only returns connections belonging to the authenticated user's tenant
    - Cannot see other tenants' connections
    """
    result = await db.execute(
        select(AWSConnection).where(AWSConnection.tenant_id == current_user.tenant_id)
    )
    connections = result.scalars().all()
    
    return connections

@router.post("/{connection_id}/verify")
async def verify_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),  # Add this
    db: AsyncSession = Depends(get_db),
):
    # Fetch connection AND verify tenant ownership
    result = await db.execute(
        select(AWSConnection).where(
            AWSConnection.id == connection_id,
            AWSConnection.tenant_id == current_user.tenant_id,  # Add tenant check
        )
    )
    connection = result.scalar_one_or_none()
    
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    # Verify the connection
    success, error = verify_aws_connection(connection.role_arn, connection.external_id)
    
    # Update status
    connection.status = "active" if success else "error"
    connection.last_verified_at = datetime.utcnow()
    connection.error_message = error
    await db.commit()
    
    if success:
        return {"status": "active", "message": "Connection verified successfully"}
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Connection verification failed: {error}"
        )


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    connection_id: UUID,
    current_user: CurrentUser = Depends(get_current_user),  # Add auth
    db: AsyncSession = Depends(get_db),
):
    """
    Remove an AWS connection.
    
    Security:
    - Requires authentication
    - Only allows deletion of connections belonging to the user's tenant
    """
    result = await db.execute(
        select(AWSConnection).where(
            AWSConnection.id == connection_id,
            AWSConnection.tenant_id == current_user.tenant_id,  # Add tenant check
        )
    )
    connection = result.scalar_one_or_none()
    
    if not connection:
        raise HTTPException(status_code=404, detail="Connection not found")
    
    await db.delete(connection)
    await db.commit()
    
    logger.info(
        "aws_connection_deleted",
        connection_id=str(connection_id),
        tenant_id=str(current_user.tenant_id),
    )
    
    return None