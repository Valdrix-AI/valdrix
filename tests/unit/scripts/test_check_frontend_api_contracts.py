from scripts.check_frontend_api_contracts import path_matches


def test_path_matches_exact_path() -> None:
    assert path_matches("/api/v1/settings/connections/aws", "/api/v1/settings/connections/aws")


def test_path_matches_backend_template_segment() -> None:
    assert path_matches(
        "/api/v1/settings/connections/aws/123/verify",
        "/api/v1/settings/connections/aws/{connection_id}/verify",
    )


def test_path_matches_frontend_template_segment() -> None:
    assert path_matches(
        "/api/v1/settings/connections/{param}/{param}/verify",
        "/api/v1/settings/connections/azure/{connection_id}/verify",
    )


def test_path_matches_rejects_different_path_shape() -> None:
    assert not path_matches(
        "/api/v1/settings/connections/{param}",
        "/api/v1/settings/connections/aws/{connection_id}/verify",
    )
