"""
Canonical charge category mapping for cost ingestion.

This provides a lightweight, deterministic mapping layer for provider service names
into a stable category set used by dashboard quality checks.
"""

from dataclasses import dataclass

MAPPING_VERSION = "focus-1.3-v1"
UNMAPPED_CATEGORY = "unmapped"


@dataclass(frozen=True)
class CanonicalChargeMapping:
    category: str
    subcategory: str | None
    is_mapped: bool
    confidence: float
    mapping_version: str = MAPPING_VERSION
    unmapped_reason: str | None = None


def _contains_any(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)


def map_canonical_charge_category(
    provider: str | None,
    service: str | None,
    usage_type: str | None,
) -> CanonicalChargeMapping:
    """
    Map raw service/usage values into a canonical category set.

    The mapping is intentionally simple for the first implementation and should
    be expanded as new service signatures are observed in production telemetry.
    """
    supported_providers = {
        "aws",
        "azure",
        "gcp",
        "saas",
        "license",
        "platform",
        "hybrid",
        "generic",
    }
    provider_key = (provider or "").strip().lower()
    service_key = (service or "").strip().lower()
    usage_key = (usage_type or "").strip().lower()
    combined = f"{provider_key} {service_key} {usage_key}".strip()

    if not combined:
        return CanonicalChargeMapping(
            category=UNMAPPED_CATEGORY,
            subcategory=None,
            is_mapped=False,
            confidence=0.0,
            unmapped_reason="missing_provider_service_usage",
        )

    if provider_key and provider_key not in supported_providers:
        return CanonicalChargeMapping(
            category=UNMAPPED_CATEGORY,
            subcategory=None,
            is_mapped=False,
            confidence=0.0,
            unmapped_reason="unsupported_provider",
        )

    if _contains_any(
        combined,
        (
            "ec2",
            "compute",
            "vm",
            "virtual machine",
            "instance",
            "lambda",
            "functions",
            "fargate",
            "app service",
            "cloud run",
            "kubernetes engine",
            "eks",
            "aks",
            "gke",
        ),
    ):
        return CanonicalChargeMapping(
            category="compute",
            subcategory="runtime",
            is_mapped=True,
            confidence=0.95,
            unmapped_reason=None,
        )

    if _contains_any(
        combined,
        (
            "s3",
            "storage",
            "ebs",
            "disk",
            "blob",
            "snapshot",
            "bucket",
            "persistent disk",
            "managed disk",
            "gcs",
        ),
    ):
        return CanonicalChargeMapping(
            category="storage",
            subcategory="capacity",
            is_mapped=True,
            confidence=0.95,
            unmapped_reason=None,
        )

    if _contains_any(
        combined,
        (
            "nat",
            "egress",
            "ingress",
            "bandwidth",
            "data transfer",
            "network",
            "load balancer",
            "cdn",
            "gateway",
            "vpc",
        ),
    ):
        return CanonicalChargeMapping(
            category="network",
            subcategory="transfer",
            is_mapped=True,
            confidence=0.9,
            unmapped_reason=None,
        )

    if _contains_any(
        combined,
        (
            "rds",
            "sql",
            "database",
            "cosmos",
            "spanner",
            "bigquery",
            "dynamodb",
            "redis",
            "cache",
        ),
    ):
        return CanonicalChargeMapping(
            category="database",
            subcategory="managed",
            is_mapped=True,
            confidence=0.9,
            unmapped_reason=None,
        )

    if _contains_any(
        combined,
        (
            "support",
            "tax",
            "credit",
            "refund",
            "marketplace",
            "plan",
            "reservation",
            "savings plan",
            "commitment",
        ),
    ):
        return CanonicalChargeMapping(
            category="financial",
            subcategory="adjustment",
            is_mapped=True,
            confidence=0.8,
            unmapped_reason=None,
        )

    unmapped_reason = "unclassified_signature"
    if not service_key and not usage_key:
        unmapped_reason = "missing_service_and_usage"
    elif not service_key:
        unmapped_reason = "missing_service"
    elif not usage_key:
        unmapped_reason = "missing_usage_type"

    return CanonicalChargeMapping(
        category=UNMAPPED_CATEGORY,
        subcategory=None,
        is_mapped=False,
        confidence=0.0,
        unmapped_reason=unmapped_reason,
    )
