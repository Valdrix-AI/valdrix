from app.modules.reporting.domain.canonicalization import (
    MAPPING_VERSION,
    map_canonical_charge_category,
)


def test_map_canonical_charge_category_maps_known_compute_service() -> None:
    mapping = map_canonical_charge_category(
        provider="aws",
        service="AmazonEC2",
        usage_type="BoxUsage",
    )

    assert mapping.category == "compute"
    assert mapping.is_mapped is True


def test_map_canonical_charge_category_maps_known_storage_service() -> None:
    mapping = map_canonical_charge_category(
        provider="azure",
        service="Storage",
        usage_type="Standard HDD Managed Disks",
    )

    assert mapping.category == "storage"
    assert mapping.is_mapped is True


def test_map_canonical_charge_category_flags_unmapped_values() -> None:
    mapping = map_canonical_charge_category(
        provider="gcp",
        service="FutureUnknownService",
        usage_type="FutureUnknownUsage",
    )

    assert mapping.category == "unmapped"
    assert mapping.is_mapped is False
    assert mapping.unmapped_reason == "unclassified_signature"


def test_map_canonical_charge_category_maps_known_network_service() -> None:
    mapping = map_canonical_charge_category(
        provider="aws",
        service="DataTransfer",
        usage_type="NatGateway-Bytes",
    )

    assert mapping.category == "network"
    assert mapping.subcategory == "transfer"
    assert mapping.confidence == 0.9
    assert mapping.mapping_version == MAPPING_VERSION


def test_map_canonical_charge_category_maps_known_database_service() -> None:
    mapping = map_canonical_charge_category(
        provider="gcp",
        service="BigQuery",
        usage_type="AnalysisBytes",
    )

    assert mapping.category == "database"
    assert mapping.subcategory == "managed"
    assert mapping.is_mapped is True


def test_map_canonical_charge_category_maps_known_financial_service() -> None:
    mapping = map_canonical_charge_category(
        provider="aws",
        service="Savings Plan Covered Usage",
        usage_type="Commitment",
    )

    assert mapping.category == "financial"
    assert mapping.subcategory == "adjustment"
    assert mapping.confidence == 0.8


def test_map_canonical_charge_category_empty_values_returns_unmapped() -> None:
    mapping = map_canonical_charge_category(
        provider=None,
        service="   ",
        usage_type="",
    )

    assert mapping.category == "unmapped"
    assert mapping.subcategory is None
    assert mapping.confidence == 0.0
    assert mapping.unmapped_reason == "missing_provider_service_usage"


def test_map_canonical_charge_category_flags_unsupported_provider() -> None:
    mapping = map_canonical_charge_category(
        provider="oracle",
        service="compute",
        usage_type="usage",
    )

    assert mapping.category == "unmapped"
    assert mapping.unmapped_reason == "unsupported_provider"
