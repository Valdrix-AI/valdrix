from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from app.models.remediation import RemediationRequest


def sanitize_tf_identifier(provider: str, resource_type: str, resource_id: str) -> str:
    """
    Produce a Terraform-safe identifier with deterministic collision resistance.
    """
    normalized = re.sub(r"[^a-zA-Z0-9_]", "_", resource_id).strip("_").lower()
    if not normalized:
        normalized = "resource"
    if normalized[0].isdigit():
        normalized = f"r_{normalized}"
    stem = normalized[:48]
    digest_input = f"{provider}:{resource_type}:{resource_id}".encode()
    digest = hashlib.sha256(digest_input).hexdigest()[:10]
    return f"{stem}_{digest}"


async def generate_iac_plan_for_request(
    service: Any,
    request: RemediationRequest,
    tenant_id: UUID,
    *,
    tenant_tier: str | Any | None = None,
) -> str:
    """
    Generates a Terraform decommissioning plan for the resource.
    Supports `state rm` and `removed` blocks for GitOps workflows.
    """
    from app.shared.core.pricing import (
        FeatureFlag,
        get_tenant_tier,
        is_feature_enabled,
    )

    resolved_tier = (
        tenant_tier
        if tenant_tier is not None
        else await get_tenant_tier(tenant_id, service.db)
    )

    if not is_feature_enabled(resolved_tier, FeatureFlag.GITOPS_REMEDIATION):
        return "# GitOps Remediation is a Pro-tier feature. Please upgrade to unlock IaC plans."

    resource_id = request.resource_id
    provider = request.provider.lower()

    tf_mapping = {
        "EC2 Instance": "aws_instance",
        "Elastic IP": "aws_eip",
        "EBS Volume": "aws_ebs_volume",
        "RDS Instance": "aws_db_instance",
        "S3 Bucket": "aws_s3_bucket",
        "Snapshot": "aws_ebs_snapshot",
        "Azure VM": "azurerm_virtual_machine",
        "Managed Disk": "azurerm_managed_disk",
        "Public IP": "azurerm_public_ip",
        "GCP Instance": "google_compute_instance",
        "Address": "google_compute_address",
        "Disk": "google_compute_disk",
    }

    tf_type = tf_mapping.get(request.resource_type, "cloud_resource")
    tf_id = sanitize_tf_identifier(provider, request.resource_type, resource_id)

    planlines = [
        "# Valdrix GitOps Remediation Plan",
        f"# Resource: {resource_id} ({request.resource_type})",
        f"# Savings: ${request.estimated_monthly_savings}/mo",
        f"# Action: {request.action.value}",
        "",
    ]

    if provider == "aws":
        planlines.append("# Option 1: Manual State Removal")
        planlines.append(f"terraform state rm {tf_type}.{tf_id}")
        planlines.append("")
        planlines.append("# Option 2: Terraform 'removed' block (Recommended for TF 1.7+)")
        planlines.append("removed {")
        planlines.append(f"  from = {tf_type}.{tf_id}")
        planlines.append("  lifecycle {")
        planlines.append("    destroy = true")
        planlines.append("  }")
        planlines.append("}")
    elif provider in {"azure", "gcp"}:
        planlines.append("# Option 1: Manual State Removal")
        planlines.append(f"terraform state rm {tf_type}.{tf_id}")
        planlines.append("")
        planlines.append("# Option 2: Terraform 'removed' block")
        planlines.append("removed {")
        planlines.append(f"  from = {tf_type}.{tf_id}")
        planlines.append("  lifecycle {")
        planlines.append("    destroy = true")
        planlines.append("  }")
        planlines.append("}")
    else:
        planlines.append("# Option 1: Manual State Removal")
        planlines.append(f"terraform state rm cloud_resource.{tf_id}")
        planlines.append("")
        planlines.append("# Option 2: Terraform 'removed' block")
        planlines.append("removed {")
        planlines.append(f"  from = cloud_resource.{tf_id}")
        planlines.append("  lifecycle {")
        planlines.append("    destroy = true")
        planlines.append("  }")
        planlines.append("}")

    return "\n".join(planlines)


async def bulk_generate_iac_plan_for_requests(
    service: Any,
    requests: list[RemediationRequest],
    tenant_id: UUID,
) -> str:
    from app.shared.core.pricing import get_tenant_tier

    tenant_tier = await get_tenant_tier(tenant_id, service.db)
    plans = [
        await generate_iac_plan_for_request(service, req, tenant_id, tenant_tier=tenant_tier)
        for req in requests
    ]
    header = (
        "# Valdrix Bulk IaC Remediation Plan\n"
        f"# Generated: {datetime.now(timezone.utc).isoformat()}\n\n"
    )
    return header + "\n\n" + "\n" + "-" * 40 + "\n".join(plans)
