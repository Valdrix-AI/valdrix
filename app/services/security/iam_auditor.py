import aioboto3
from typing import List, Dict, Any
import structlog

logger = structlog.get_logger()

class IAMAuditor:
    """
    Audits IAM policies for Least Privilege and Security Best Practices.
    Aligns with FAANG Zero-Trust standards (2026).
    """

    def __init__(self, credentials: Dict[str, str], region: str = "us-east-1"):
        """
        Initialize with AWS credentials.
        """
        self.session = aioboto3.Session(
            aws_access_key_id=credentials.get("aws_access_key_id"),
            aws_secret_access_key=credentials.get("aws_secret_access_key"),
            aws_session_token=credentials.get("aws_session_token"),
            region_name=region
        )

    async def audit_current_role(self) -> Dict[str, Any]:
        """
        Audits the currently assumed role's policies.
        Returns a report on permissiveness and potential risks.
        """
        try:
            async with self.session.client("sts") as sts:
                caller_identity = await sts.get_caller_identity()

            arn = caller_identity["Arn"]

            # Extract role name from ARN (arn:aws:sts::123:assumed-role/RoleName/Session)
            # Typically for assumed roles: arn:aws:sts::ACCOUNT:assumed-role/ROLE_NAME/SESSION_NAME
            # The actual IAM role ARN is arn:aws:iam::ACCOUNT:role/ROLE_NAME

            if "assumed-role" not in arn:
                return {"error": "Not running as an assumed role", "arn": arn}

            parts = arn.split("/")
            if len(parts) < 2:
                return {"error": "Could not parse role name", "arn": arn}

            role_name = parts[1]

            logger.info("auditing_role", role_name=role_name)

            risks = []
            score = 100 # Start with perfect score

            async with self.session.client("iam") as iam:
                # Fetch attached policies
                attached_policies = await iam.list_attached_role_policies(RoleName=role_name)

                # Analyze Attached Policies
                for policy in attached_policies.get("AttachedPolicies", []):
                    policy_arn = policy["PolicyArn"]
                    policy_info = await iam.get_policy(PolicyArn=policy_arn)
                    version = policy_info["Policy"]["DefaultVersionId"]

                    policy_version = await iam.get_policy_version(PolicyArn=policy_arn, VersionId=version)
                    doc = policy_version["PolicyVersion"]["Document"]

                    analysis = self._analyze_policy_document(doc)
                    if analysis["risks"]:
                        risks.extend([(f"Policy {policy['PolicyName']}: {r}") for r in analysis["risks"]])
                        score -= (len(analysis["risks"]) * 10)

                # Analyze Inline Policies
                inline_policies = await iam.list_role_policies(RoleName=role_name)
                for policy_name in inline_policies.get("PolicyNames", []):
                    policy_result = await iam.get_role_policy(RoleName=role_name, PolicyName=policy_name)
                    doc = policy_result["PolicyDocument"]
                    analysis = self._analyze_policy_document(doc)
                    if analysis["risks"]:
                        risks.extend([(f"Inline Policy {policy_name}: {r}") for r in analysis["risks"]])
                        score -= (len(analysis["risks"]) * 10)

            return {
                "role_name": role_name,
                "score": max(0, score),
                "status": "compliant" if score > 80 else "risk",
                "risks": risks,
                "zero_trust_aligned": score > 90
            }

        except Exception as e:
            logger.error("iam_audit_failed", error=str(e))
            return {"error": str(e), "status": "failed"}

    def _analyze_policy_document(self, doc: Dict) -> Dict[str, List[str]]:
        """
        Analyzes a policy document JSON for security risks.
        """
        risks = []
        statements = doc.get("Statement", [])
        if isinstance(statements, dict):
            statements = [statements]

        for stmt in statements:
            if stmt.get("Effect") != "Allow":
                continue

            actions = stmt.get("Action", [])
            if isinstance(actions, str):
                actions = [actions]

            resources = stmt.get("Resource", [])
            if isinstance(resources, str):
                resources = [resources]

            # Risk 1: Admin Access (* on *)
            if "*" in actions and "*" in resources:
                risks.append("Critical: Full Administrator Access detected ('*'). Violation of Least Privilege.")

            # Risk 2: Full Resource Access to sensitive services
            # In 2026, scoping strictly to resources is mandatory.
            if "*" in resources:
                # Check if actions are sensitive
                # Item 18: Enhanced detection for service-specific wildcards e.g. "s3:*" or "ec2:*"
                sensitive_prefixes = [
                    "ec2:*", "s3:*", "iam:*", "rds:*", "dynamodb:*", "lambda:*", 
                    "kms:*", "secretsmanager:*", "sqs:*", "sns:*", "logs:*"
                ]
                for action in actions:
                    action_lower = str(action).lower()
                    # Detect full wildcard "*" or service-level wildcard "s3:*" or prefix-level "s3:Get*"
                    if action == "*" or any(action_lower.startswith(p.replace("*", "").lower()) and "*" in action_lower for p in sensitive_prefixes):
                        risks.append(f"High: Unscoped allow on sensitive action '{action}'. Should rely on Resource ARNs for Zero Trust.")
                        break
                    
                    # Additional check for data-exfiltration or modification wildcards
                    if any(x in action_lower for x in ["delete", "put", "update", "create"]) and "*" in action_lower:
                        risks.append(f"Medium: Broad wildcard detected in write action '{action}'. Recommended to scope to ARNs.")
                        break

        return {"risks": risks}
