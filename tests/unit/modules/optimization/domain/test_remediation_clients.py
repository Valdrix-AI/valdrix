from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.modules.optimization.adapters.common import remediation_clients


def test_build_aws_client_maps_endpoint_and_credentials() -> None:
    session = MagicMock()
    fake_client = object()
    session.client.return_value = fake_client

    with patch.object(
        remediation_clients,
        "map_aws_credentials",
        return_value={"aws_access_key_id": "mapped-ak"},
    ) as map_creds:
        client = remediation_clients.build_aws_client(
            session=session,
            service_name="ec2",
            region="us-east-1",
            endpoint_url="http://localstack:4566",
            raw_credentials={"aws_access_key_id": "ak"},
        )

    assert client is fake_client
    map_creds.assert_called_once_with({"aws_access_key_id": "ak"})
    session.client.assert_called_once_with(
        "ec2",
        region_name="us-east-1",
        endpoint_url="http://localstack:4566",
        aws_access_key_id="mapped-ak",
    )


def test_remediation_action_recoverable_exceptions_include_common_runtime_errors() -> None:
    exceptions = remediation_clients.remediation_action_recoverable_exceptions()

    assert OSError in exceptions
    assert RuntimeError in exceptions
    assert ValueError in exceptions
    assert LookupError in exceptions

