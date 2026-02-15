from app.modules.optimization.domain.waste_rightsizing import (
    build_waste_rightsizing_payload,
)


def test_build_waste_rightsizing_payload_maps_required_classes_actions() -> None:
    scan_results = {
        "idle_instances": [
            {
                "resource_id": "i-idle-1",
                "monthly_cost": 100.0,
                "utilization_percent": 2,
                "days_idle": 14,
                "provider": "aws",
            }
        ],
        "underused_nat_gateways": [
            {"resource_id": "nat-1", "monthly_cost": 80.0, "utilization_pct": 10}
        ],
        "orphan_load_balancers": [{"resource_id": "lb-1", "monthly_cost": 30.0}],
        "unattached_volumes": [{"resource_id": "vol-1", "monthly_cost": 25.0}],
        "custom_category": [{"resource_id": "custom-1", "monthly_cost": 999.0}],
        "scanned_connections": 1,
        "total_monthly_waste": 235.0,
    }

    payload = build_waste_rightsizing_payload(scan_results)

    assert payload["deterministic"] is True
    assert payload["summary"]["total_recommendations"] == 4
    assert payload["summary"]["by_detection_class"] == {
        "idle_compute": 1,
        "orphaned_assets": 1,
        "over_provisioned_resources": 1,
        "unattached_storage": 1,
    }

    recommendations = payload["recommendations"]
    assert recommendations[0]["resource_id"] == "i-idle-1"
    assert recommendations[0]["detection_class"] == "idle_compute"
    assert recommendations[0]["required_action"] == "stop_or_terminate_compute"
    assert recommendations[0]["estimated_monthly_savings"] == {
        "low": 55.0,
        "mid": 75.0,
        "high": 95.0,
    }

    detached_volume = next(
        rec for rec in recommendations if rec["resource_id"] == "vol-1"
    )
    assert detached_volume["detection_class"] == "unattached_storage"
    assert (
        detached_volume["required_action"] == "delete_or_snapshot_then_delete_storage"
    )


def test_build_waste_rightsizing_payload_is_deterministic_for_same_input() -> None:
    scan_results = {
        "idle_instances": [{"resource_id": "i-1", "monthly_cost": 50.0}],
        "unattached_volumes": [{"resource_id": "vol-1", "monthly_cost": 20.0}],
    }

    first = build_waste_rightsizing_payload(scan_results)
    second = build_waste_rightsizing_payload(scan_results)

    assert first == second


def test_confidence_is_penalized_for_dependencies_and_production() -> None:
    scan_results = {
        "idle_instances": [
            {
                "resource_id": "i-prod",
                "monthly_cost": 120.0,
                "utilization_percent": 50,
                "days_idle": 1,
                "has_dependencies": True,
                "is_production": True,
            }
        ]
    }

    payload = build_waste_rightsizing_payload(scan_results)
    recommendation = payload["recommendations"][0]

    assert recommendation["confidence"] < 0.70


def test_build_waste_rightsizing_payload_includes_container_serverless_and_network_categories() -> (
    None
):
    scan_results = {
        "idle_container_clusters": [
            {
                "resource_id": "gke-empty-1",
                "monthly_cost": 120.0,
                "provider": "gcp",
            }
        ],
        "unused_app_service_plans": [
            {
                "resource_id": "asp-1",
                "monthly_cost": 60.0,
                "provider": "azure",
            }
        ],
        "idle_serverless_functions": [
            {
                "resource_id": "fn-1",
                "monthly_cost": 15.0,
                "provider": "gcp",
            }
        ],
        "orphan_network_components": [
            {
                "resource_id": "nsg-1",
                "monthly_cost": 0.0,
                "provider": "azure",
            }
        ],
    }

    payload = build_waste_rightsizing_payload(scan_results)

    assert payload["deterministic"] is True
    assert payload["summary"]["total_recommendations"] == 4

    by_class = payload["summary"]["by_detection_class"]
    assert by_class["idle_compute"] == 1
    assert by_class["over_provisioned_resources"] == 2
    assert by_class["orphaned_assets"] == 1

    rec_by_id = {rec["resource_id"]: rec for rec in payload["recommendations"]}
    assert rec_by_id["gke-empty-1"]["required_action"] == "scale_down_or_delete_cluster"
    assert (
        rec_by_id["asp-1"]["required_action"] == "delete_or_downgrade_app_service_plan"
    )
    assert (
        rec_by_id["fn-1"]["required_action"]
        == "remove_reserved_capacity_or_delete_function"
    )
    assert rec_by_id["nsg-1"]["required_action"] == "delete_orphan_network_component"
