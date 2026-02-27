from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.governance.domain.security.iam_auditor import IAMAuditor


def _mock_session_clients(*, caller_arn: str):
    mock_sts = AsyncMock()
    mock_iam = AsyncMock()
    mock_sts.get_caller_identity.return_value = {"Arn": caller_arn}

    def client_side_effect(service_name: str, **kwargs):
        del kwargs
        cm = MagicMock()
        if service_name == "sts":
            cm.__aenter__.return_value = mock_sts
        elif service_name == "iam":
            cm.__aenter__.return_value = mock_iam
        cm.__aexit__.return_value = None
        return cm

    return mock_sts, mock_iam, client_side_effect


@pytest.mark.asyncio
async def test_iam_auditor_audit_current_role_rejects_non_assumed_role() -> None:
    creds = {"aws_access_key_id": "a", "aws_secret_access_key": "b"}
    with patch("aioboto3.Session") as session_cls:
        _mock_sts, mock_iam, client_side_effect = _mock_session_clients(
            caller_arn="arn:aws:iam::123456789012:role/PlainRole"
        )
        session_cls.return_value.client.side_effect = client_side_effect

        report = await IAMAuditor(creds).audit_current_role()

    assert report["error"] == "Not running as an assumed role"
    assert report["arn"].endswith(":role/PlainRole")
    mock_iam.list_attached_role_policies.assert_not_awaited()


@pytest.mark.asyncio
async def test_iam_auditor_audit_current_role_handles_unparseable_assumed_role_arn() -> None:
    creds = {"aws_access_key_id": "a", "aws_secret_access_key": "b"}
    with patch("aioboto3.Session") as session_cls:
        _mock_sts, mock_iam, client_side_effect = _mock_session_clients(
            caller_arn="arn:aws:sts::123456789012:assumed-role"
        )
        session_cls.return_value.client.side_effect = client_side_effect

        report = await IAMAuditor(creds).audit_current_role()

    assert report["error"] == "Could not parse role name"
    mock_iam.list_attached_role_policies.assert_not_awaited()


@pytest.mark.asyncio
async def test_iam_auditor_audit_current_role_aggregates_inline_policy_risks() -> None:
    creds = {"aws_access_key_id": "a", "aws_secret_access_key": "b"}
    with patch("aioboto3.Session") as session_cls:
        _mock_sts, mock_iam, client_side_effect = _mock_session_clients(
            caller_arn="arn:aws:sts::123456789012:assumed-role/TestRole/Session"
        )
        session_cls.return_value.client.side_effect = client_side_effect

        mock_iam.list_attached_role_policies.return_value = {"AttachedPolicies": []}
        mock_iam.list_role_policies.return_value = {"PolicyNames": ["InlineDanger"]}
        mock_iam.get_role_policy.return_value = {
            "PolicyDocument": {
                "Statement": {
                    "Effect": "Allow",
                    "Action": "s3:*",
                    "Resource": "*",
                }
            }
        }

        report = await IAMAuditor(creds).audit_current_role()

    assert report["role_name"] == "TestRole"
    # One inline risk deducts 10 points (score=90), which is still "compliant" by current threshold.
    assert report["status"] == "compliant"
    assert any("Inline Policy InlineDanger" in risk for risk in report["risks"])
    assert report["score"] == 90


@pytest.mark.asyncio
async def test_iam_auditor_audit_current_role_inline_policy_with_no_risks_keeps_score() -> None:
    creds = {"aws_access_key_id": "a", "aws_secret_access_key": "b"}
    with patch("aioboto3.Session") as session_cls:
        _mock_sts, mock_iam, client_side_effect = _mock_session_clients(
            caller_arn="arn:aws:sts::123456789012:assumed-role/TestRole/Session"
        )
        session_cls.return_value.client.side_effect = client_side_effect

        mock_iam.list_attached_role_policies.return_value = {"AttachedPolicies": []}
        mock_iam.list_role_policies.return_value = {"PolicyNames": ["InlineSafe"]}
        mock_iam.get_role_policy.return_value = {
            "PolicyDocument": {
                "Statement": {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject"],
                    "Resource": ["arn:aws:s3:::bucket/*"],
                }
            }
        }

        report = await IAMAuditor(creds).audit_current_role()

    assert report["score"] == 100
    assert report["risks"] == []


@pytest.mark.asyncio
async def test_iam_auditor_audit_current_role_handles_exception() -> None:
    creds = {"aws_access_key_id": "a", "aws_secret_access_key": "b"}
    with (
        patch("aioboto3.Session") as session_cls,
        patch(
            "app.modules.governance.domain.security.iam_auditor.logger.error"
        ) as logger_error,
    ):
        mock_sts, _mock_iam, client_side_effect = _mock_session_clients(
            caller_arn="arn:aws:sts::123456789012:assumed-role/TestRole/Session"
        )
        mock_sts.get_caller_identity.side_effect = RuntimeError("sts down")
        session_cls.return_value.client.side_effect = client_side_effect

        report = await IAMAuditor(creds).audit_current_role()

    assert report["status"] == "failed"
    assert "sts down" in report["error"]
    logger_error.assert_called_once()


def test_iam_auditor_policy_document_analysis_branch_paths() -> None:
    auditor = IAMAuditor({"aws_access_key_id": "a", "aws_secret_access_key": "b"}, region="us-east-1")

    # Deny statements are ignored, dict inputs are normalized, and write wildcards are detected.
    analysis = auditor._analyze_policy_document(
        {
                "Statement": [
                    {"Effect": "Deny", "Action": "s3:*", "Resource": "*"},
                    {"Effect": "Allow", "Action": "custom:Delete*", "Resource": "*"},
                ]
            }
        )
    assert len(analysis["risks"]) == 1
    assert "Medium: Broad wildcard detected in write action" in analysis["risks"][0]

    # String Action/Resource inputs and sensitive wildcard detection.
    analysis_sensitive = auditor._analyze_policy_document(
        {
            "Statement": {
                "Effect": "Allow",
                "Action": "ec2:*",
                "Resource": "*",
            }
        }
    )
    assert any("High: Unscoped allow on sensitive action 'ec2:*'" in r for r in analysis_sensitive["risks"])

    # List Action/Resource branches with no wildcard risk should produce no findings.
    analysis_safe_lists = auditor._analyze_policy_document(
        {
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["s3:GetObject", "ec2:DescribeInstances"],
                    "Resource": ["arn:aws:s3:::bucket/*"],
                }
            ]
        }
    )
    assert analysis_safe_lists["risks"] == []

    # Resource wildcard with non-wildcard actions: enter the action loop and exhaust without breaks.
    analysis_resource_wildcard_no_risk = auditor._analyze_policy_document(
        {
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": ["ec2:DescribeInstances", "s3:GetObject"],
                    "Resource": "*",
                }
            ]
        }
    )
    assert analysis_resource_wildcard_no_risk["risks"] == []


def test_iam_auditor_init_prefers_explicit_region_over_config_default() -> None:
    with (
        patch(
            "app.modules.governance.domain.security.iam_auditor.get_settings",
            return_value=SimpleNamespace(AWS_DEFAULT_REGION="eu-west-2"),
        ),
        patch("aioboto3.Session") as session_cls,
    ):
        IAMAuditor(
            {"aws_access_key_id": "a", "aws_secret_access_key": "b"},
            region="ap-south-1",
        )

    assert session_cls.call_args is not None
    assert session_cls.call_args.kwargs["region_name"] == "ap-south-1"
