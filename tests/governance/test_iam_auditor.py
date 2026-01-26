import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from app.modules.governance.domain.security.iam_auditor import IAMAuditor

@pytest.mark.asyncio
async def test_iam_auditor_admin_risk():
    """Verify that the auditor flags Admin Access (*) as a critical risk."""
    
    # Mock credentials
    creds = {
        "aws_access_key_id": "test",
        "aws_secret_access_key": "test",
        "aws_session_token": "test"
    }
    
    with patch("aioboto3.Session") as mock_session_cls:
        mock_session = mock_session_cls.return_value
        
        # Create mock clients
        mock_sts = AsyncMock()
        mock_iam = AsyncMock()
        
        # Configure client factory
        def client_side_effect(service_name, **kwargs):
            mock_cm = MagicMock()
            if service_name == "sts":
                mock_cm.__aenter__.return_value = mock_sts
            elif service_name == "iam":
                mock_cm.__aenter__.return_value = mock_iam
            mock_cm.__aexit__.return_value = None
            return mock_cm

        mock_session.client.side_effect = client_side_effect
        
        # Mock Caller Identity
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:sts::123456789012:assumed-role/TestRole/Session"
        }
        
        # Mock Attached Policies
        mock_iam.list_attached_role_policies.return_value = {
            "AttachedPolicies": [{"PolicyName": "AdminPolicy", "PolicyArn": "arn:aws:iam::aws:policy/AdministratorAccess"}]
        }
        
        # Mock Policy Version & Document
        mock_iam.get_policy.return_value = {"Policy": {"DefaultVersionId": "v1"}}
        mock_iam.get_policy_version.return_value = {
            "PolicyVersion": {
                "Document": {
                    "Statement": [
                        {"Effect": "Allow", "Action": "*", "Resource": "*"}
                    ]
                }
            }
        }
        
        # Mock Inline Policies (empty)
        mock_iam.list_role_policies.return_value = {"PolicyNames": []}

        auditor = IAMAuditor(creds)
        report = await auditor.audit_current_role()
        
        assert report["role_name"] == "TestRole"
        assert report["status"] == "risk"
        assert any("Critical: Full Administrator Access" in r for r in report["risks"])
        assert report["score"] < 90

@pytest.mark.asyncio
async def test_iam_auditor_least_privilege_compliance():
    """Verify that a scoped policy gets a high score."""
    
    creds = {"aws_access_key_id": "test", "aws_secret_access_key": "test"}
    
    with patch("aioboto3.Session") as mock_session_cls:
        mock_session = mock_session_cls.return_value
        
        mock_sts = AsyncMock()
        mock_iam = AsyncMock()
        
        def client_side_effect(service_name, **kwargs):
            mock_cm = MagicMock()
            if service_name == "sts":
                mock_cm.__aenter__.return_value = mock_sts
            elif service_name == "iam":
                mock_cm.__aenter__.return_value = mock_iam
            mock_cm.__aexit__.return_value = None
            return mock_cm
            
        mock_session.client.side_effect = client_side_effect
        
        mock_sts.get_caller_identity.return_value = {
            "Arn": "arn:aws:sts::123456789012:assumed-role/GoodRole/Session"
        }
        
        mock_iam.list_attached_role_policies.return_value = {
            "AttachedPolicies": [{"PolicyName": "ReadS3", "PolicyArn": "arn:aws:iam::123:policy/ReadS3"}]
        }
        
        mock_iam.get_policy.return_value = {"Policy": {"DefaultVersionId": "v1"}}
        
        # Good Policy: Specific Action on Specific Resource
        mock_iam.get_policy_version.return_value = {
            "PolicyVersion": {
                "Document": {
                    "Statement": [
                        {"Effect": "Allow", "Action": "s3:GetObject", "Resource": "arn:aws:s3:::my-bucket/*"}
                    ]
                }
            }
        }
        
        mock_iam.list_role_policies.return_value = {"PolicyNames": []}

        auditor = IAMAuditor(creds)
        report = await auditor.audit_current_role()
        
        assert report["role_name"] == "GoodRole"
        assert report["status"] == "compliant"
        assert len(report["risks"]) == 0
        assert report["score"] == 100
