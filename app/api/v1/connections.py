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
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, Field, ConfigDict
import structlog
import aioboto3
from botocore.exceptions import ClientError

from app.db.session import get_db
from app.models.aws_connection import AWSConnection
from app.core.auth import CurrentUser, requires_role

logger = structlog.get_logger()
router = APIRouter(prefix="/connections/aws", tags=["connections"])


# ============================================================
# Pydantic Schemas
# ============================================================

class AWSConnectionCreate(BaseModel):
    """Request body for creating a new AWS connection."""
    aws_account_id: str = Field(..., pattern=r"^\d{12}$", description="12-digit AWS account ID")
    role_arn: str = Field(..., description="Full ARN of the IAM role to assume")
    external_id: str = Field(..., pattern=r"^vx-[a-f0-9]{32}$", description="External ID from setup step")
    region: str = Field(default="us-east-1", description="AWS region for Cost Explorer")


class AWSConnectionResponse(BaseModel):
    """Response body for AWS connection.

    Note: external_id is intentionally excluded for security.
    It should only be visible during initial /setup flow.
    """
    id: UUID
    aws_account_id: str
    role_arn: str
    # external_id: REMOVED - security risk to expose after initial setup
    region: str
    status: str
    last_verified_at: datetime | None
    error_message: str | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AWSConnectionSetup(BaseModel):
    """Response for initial setup - includes external_id for CloudFormation."""
    external_id: str
    cloudformation_url: str
    instructions: str


# ============================================================
# Helper Functions
# ============================================================

async def verify_aws_connection(role_arn: str, external_id: str) -> tuple[bool, str | None]:
    """
    Test if we can assume the IAM role (Async).

    Returns:
        (success: bool, error_message: str | None)
    """
    try:
        session = aioboto3.Session()
        async with session.client("sts") as sts_client:

            # Try to assume the role
            await sts_client.assume_role(
                RoleArn=role_arn,
                RoleSessionName="ValdrixVerification",
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

class TemplateResponse(BaseModel):
    """Response containing template content for IAM role setup."""
    external_id: str
    cloudformation_yaml: str
    terraform_hcl: str
    instructions: str
    permissions_summary: list[str]


@router.post("/setup", response_model=TemplateResponse)
async def get_setup_templates():
    """
    Get CloudFormation and Terraform templates with a unique External ID.

    Returns templates that users can copy/paste directly into AWS Console
    or their IaC repository. No external URL dependencies.

    Three Paths UX:
    - Path A: Copy YAML → Create Stack manually
    - Path B: Copy Terraform → Add to IaC repo
    - Path C: Download file → Upload to AWS
    """
    external_id = AWSConnection.generate_external_id()

    # CloudFormation YAML template with external_id embedded
    cloudformation_yaml = f'''AWSTemplateFormatVersion: '2010-09-09'
Description: Valdrix - Read-Only IAM Role for Cost Analysis and Resource Optimization

Resources:
  ValdrixRole:
    Type: AWS::IAM::Role
    Properties:
      RoleName: ValdrixReadOnly
      Description: Allows Valdrix to read cost data and detect zombie resources
      MaxSessionDuration: 3600
      AssumeRolePolicyDocument:
        Version: '2012-10-17'
        Statement:
          - Effect: Allow
            Principal:
              AWS: !Sub 'arn:aws:iam::${{AWS::AccountId}}:root'
            Action: sts:AssumeRole
            Condition:
              StringEquals:
                sts:ExternalId: '{external_id}'
      Policies:
        - PolicyName: ValdrixReadOnlyPolicy
          PolicyDocument:
            Version: '2012-10-17'
            Statement:
              - Sid: CostExplorerRead
                Effect: Allow
                Action:
                  - ce:GetCostAndUsage
                  - ce:GetCostForecast
                  - ce:GetDimensionValues
                  - ce:GetTags
                Resource: '*'
              - Sid: EC2ReadOnly
                Effect: Allow
                Action:
                  - ec2:DescribeInstances
                  - ec2:DescribeVolumes
                  - ec2:DescribeSnapshots
                  - ec2:DescribeAddresses
                  - ec2:DescribeNetworkInterfaces
                  - ec2:DescribeNatGateways
                  - ec2:DescribeSecurityGroups
                Resource: '*'
              - Sid: ELBReadOnly
                Effect: Allow
                Action:
                  - elasticloadbalancing:DescribeLoadBalancers
                  - elasticloadbalancing:DescribeTargetGroups
                  - elasticloadbalancing:DescribeTargetHealth
                Resource: '*'
              - Sid: RDSReadOnly
                Effect: Allow
                Action:
                  - rds:DescribeDBInstances
                  - rds:DescribeDBClusters
                Resource: '*'
              - Sid: RedshiftReadOnly
                Effect: Allow
                Action:
                  - redshift:DescribeClusters
                Resource: '*'
              - Sid: SageMakerReadOnly
                Effect: Allow
                Action:
                  - sagemaker:ListEndpoints
                  - sagemaker:ListNotebookInstances
                  - sagemaker:ListModels
                Resource: '*'
              - Sid: ECRReadOnly
                Effect: Allow
                Action:
                  - ecr:DescribeRepositories
                  - ecr:DescribeImages
                Resource: '*'
              - Sid: S3ReadOnly
                Effect: Allow
                Action:
                  - s3:ListAllMyBuckets
                  - s3:GetBucketLocation
                  - s3:GetBucketTagging
                Resource: '*'
              - Sid: CloudWatchRead
                Effect: Allow
                Action:
                  - cloudwatch:GetMetricData
                  - cloudwatch:GetMetricStatistics
                Resource: '*'

Outputs:
  RoleArn:
    Description: Copy this ARN to Valdrix
    Value: !GetAtt ValdrixRole.Arn'''

    # Terraform HCL template
    terraform_hcl = f'''# Valdrix - IAM Role for Cost Analysis and Resource Optimization
# Apply with: terraform apply

resource "aws_iam_role" "valdrix" {{
  name        = "ValdrixReadOnly"
  description = "Allows Valdrix to read cost data and detect zombie resources"

  assume_role_policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [{{
      Effect    = "Allow"
      Principal = {{ AWS = "arn:aws:iam::${{data.aws_caller_identity.current.account_id}}:root" }}
      Action    = "sts:AssumeRole"
      Condition = {{ StringEquals = {{ "sts:ExternalId" = "{external_id}" }} }}
    }}]
  }})
}}

data "aws_caller_identity" "current" {{}}

resource "aws_iam_role_policy" "valdrix_policy" {{
  name = "ValdrixReadOnlyPolicy"
  role = aws_iam_role.valdrix.id

  policy = jsonencode({{
    Version = "2012-10-17"
    Statement = [
      {{
        Sid      = "CostExplorerRead"
        Effect   = "Allow"
        Action   = ["ce:GetCostAndUsage", "ce:GetCostForecast", "ce:GetDimensionValues", "ce:GetTags"]
        Resource = "*"
      }},
      {{
        Sid      = "EC2ReadOnly"
        Effect   = "Allow"
        Action   = ["ec2:DescribeInstances", "ec2:DescribeVolumes", "ec2:DescribeSnapshots", "ec2:DescribeAddresses", "ec2:DescribeNetworkInterfaces", "ec2:DescribeNatGateways", "ec2:DescribeSecurityGroups"]
        Resource = "*"
      }},
      {{
        Sid      = "ELBReadOnly"
        Effect   = "Allow"
        Action   = ["elasticloadbalancing:DescribeLoadBalancers", "elasticloadbalancing:DescribeTargetGroups", "elasticloadbalancing:DescribeTargetHealth"]
        Resource = "*"
      }},
      {{
        Sid      = "RDSReadOnly"
        Effect   = "Allow"
        Action   = ["rds:DescribeDBInstances", "rds:DescribeDBClusters"]
        Resource = "*"
      }},
      {{
        Sid      = "RedshiftOnly"
        Effect   = "Allow"
        Action   = ["redshift:DescribeClusters"]
        Resource = "*"
      }},
      {{
        Sid      = "SageMakerReadOnly"
        Effect   = "Allow"
        Action   = ["sagemaker:ListEndpoints", "sagemaker:ListNotebookInstances", "sagemaker:ListModels"]
        Resource = "*"
      }},
      {{
        Sid      = "ECRReadOnly"
        Effect   = "Allow"
        Action   = ["ecr:DescribeRepositories", "ecr:DescribeImages"]
        Resource = "*"
      }},
      {{
        Sid      = "S3ReadOnly"
        Effect   = "Allow"
        Action   = ["s3:ListAllMyBuckets", "s3:GetBucketLocation", "s3:GetBucketTagging"]
        Resource = "*"
      }},
      {{
        Sid      = "CloudWatchRead"
        Effect   = "Allow"
        Action   = ["cloudwatch:GetMetricData", "cloudwatch:GetMetricStatistics"]
        Resource = "*"
      }}
    ]
  }})
}}

output "role_arn" {{
  value = aws_iam_role.valdrix.arn
}}'''

    return TemplateResponse(
        external_id=external_id,
        cloudformation_yaml=cloudformation_yaml,
        terraform_hcl=terraform_hcl,
        instructions=(
            "1. Copy the CloudFormation or Terraform template above\n"
            "2. Deploy it in your AWS account\n"
            "3. Copy the Role ARN from the outputs\n"
            "4. Paste the Role ARN below to verify connection"
        ),
        permissions_summary=[
            "ce:GetCostAndUsage - Read your cost data",
            "ce:GetCostForecast - View cost predictions",
            "ce:GetTags - Read cost allocation tags",
            "ec2:DescribeInstances - Detect idle EC2 instances",
            "ec2:DescribeVolumes - Detect unattached EBS volumes",
            "ec2:DescribeSnapshots - Detect old snapshots",
            "ec2:DescribeAddresses - Detect unused Elastic IPs",
            "ec2:DescribeNatGateways - Detect underused NAT gateways",
            "elasticloadbalancing:Describe* - Detect orphan load balancers",
            "rds:DescribeDBInstances - Detect idle RDS databases",
            "cloudwatch:GetMetricData - Monitor resource utilization",
        ]
    )


@router.post("", response_model=AWSConnectionResponse, status_code=status.HTTP_201_CREATED)
async def create_connection(
    data: AWSConnectionCreate,
    current_user: CurrentUser = Depends(requires_role("member")),  # <-- Auth dependency
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

    # Create new connection - use the SAME external_id from setup step
    connection = AWSConnection(
        tenant_id=current_user.tenant_id,
        aws_account_id=data.aws_account_id,
        role_arn=data.role_arn,
        external_id=data.external_id,  # Use ID from frontend, not generate new!
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
    current_user: CurrentUser = Depends(requires_role("member")),
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
    current_user: CurrentUser = Depends(requires_role("member")),  # Add this
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
    success, error = await verify_aws_connection(connection.role_arn, connection.external_id)

    # Update status
    connection.status = "active" if success else "error"
    # FIX: Use naive UTC datetime for SQLAlchemy DateTime column
    connection.last_verified_at = datetime.now(timezone.utc).replace(tzinfo=None)
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
    current_user: CurrentUser = Depends(requires_role("member")),  # Add auth
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
