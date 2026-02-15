from app.modules.optimization.domain.architectural_inefficiency import (
    build_architectural_inefficiency_payload,
)


def test_detects_overbuilt_and_unjustified_multi_zone_patterns() -> None:
    scan_results = {
        "idle_instances": [
            {
                "resource_id": "i-dev-1",
                "provider": "aws",
                "resource_type": "ec2",
                "environment": "dev",
                "availability_zones": ["us-east-1a", "us-east-1b", "us-east-1c"],
                "monthly_cost": 240.0,
                "slo_target": 99.5,
                "business_criticality": "low",
                "owner": "team-platform",
            }
        ]
    }

    payload = build_architectural_inefficiency_payload(scan_results)

    assert payload["deterministic"] is True
    assert payload["summary"]["total_findings"] == 2
    assert payload["summary"]["by_type"] == {
        "overbuilt_availability_pattern": 1,
        "unjustified_multi_zone_deployment": 1,
    }

    finding_types = {f["finding_type"] for f in payload["findings"]}
    assert "overbuilt_availability_pattern" in finding_types
    assert "unjustified_multi_zone_deployment" in finding_types
    assert all("expected_monthly_savings" in finding for finding in payload["findings"])


def test_detects_duplicated_non_production_environments() -> None:
    scan_results = {
        "idle_instances": [
            {
                "resource_id": "i-staging-a",
                "provider": "aws",
                "service": "checkout",
                "environment": "staging",
                "monthly_cost": 90.0,
            },
            {
                "resource_id": "i-staging-b",
                "provider": "aws",
                "service": "checkout",
                "environment": "staging",
                "monthly_cost": 110.0,
            },
        ]
    }

    payload = build_architectural_inefficiency_payload(scan_results)

    duplicated = next(
        finding
        for finding in payload["findings"]
        if finding["finding_type"] == "duplicated_non_production_environment"
    )

    assert duplicated["resource_ids"] == ["i-staging-a", "i-staging-b"]
    assert (
        duplicated["required_action"]
        == "consolidate_duplicate_non_production_resources"
    )
    assert duplicated["policy_route"] == "review_required"
    assert duplicated["expected_monthly_savings"]["mid"] > 0


def test_architectural_payload_is_deterministic() -> None:
    scan_results = {
        "idle_instances": [
            {
                "resource_id": "i-a",
                "provider": "aws",
                "environment": "dev",
                "availability_zones": "us-east-1a,us-east-1b",
                "monthly_cost": 120.0,
                "service": "api",
            },
            {
                "resource_id": "i-b",
                "provider": "aws",
                "environment": "dev",
                "availability_zones": "us-east-1a,us-east-1b",
                "monthly_cost": 80.0,
                "service": "api",
            },
        ]
    }

    first = build_architectural_inefficiency_payload(scan_results)
    second = build_architectural_inefficiency_payload(scan_results)

    assert first == second
