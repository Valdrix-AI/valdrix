from __future__ import annotations

import json
from pathlib import Path


CONTRACT_FILE = Path("docs/contracts/openapi_required_paths.json")


def test_openapi_required_paths_contract(client) -> None:
    """
    Contract guard: critical frontend-consumed routes must remain present.

    This catches accidental path/method removals before release.
    """
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()
    paths = spec.get("paths", {})

    contract = json.loads(CONTRACT_FILE.read_text(encoding="utf-8"))
    required_paths: dict[str, list[str]] = contract["required_paths"]

    for path, methods in required_paths.items():
        assert path in paths, f"Missing required OpenAPI path: {path}"
        declared_methods = {m.lower() for m in paths[path].keys()}
        for method in methods:
            assert (
                method.lower() in declared_methods
            ), f"Missing required operation: {method.upper()} {path}"


def test_openapi_operation_ids_are_unique(client) -> None:
    """
    Ensure operationId uniqueness to keep generated API clients stable.
    """
    response = client.get("/openapi.json")
    assert response.status_code == 200
    spec = response.json()

    operation_ids: list[str] = []
    for path_item in spec.get("paths", {}).values():
        for operation in path_item.values():
            if isinstance(operation, dict):
                operation_id = operation.get("operationId")
                if isinstance(operation_id, str) and operation_id.strip():
                    operation_ids.append(operation_id.strip())

    assert len(operation_ids) == len(set(operation_ids)), "Duplicate operationId found"
