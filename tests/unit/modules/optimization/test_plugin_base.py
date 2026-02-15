from unittest.mock import MagicMock, patch

from app.modules.optimization.domain.plugin import ZombiePlugin


class _TestPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "test"

    async def scan(
        self, session, region, credentials=None, config=None, inventory=None
    ):
        return []


def test_get_client_includes_endpoint_credentials_and_config():
    plugin = _TestPlugin()
    session = MagicMock()

    credentials = {
        "AccessKeyId": "AKIA",
        "SecretAccessKey": "SECRET",
        "SessionToken": "TOKEN",
    }

    with patch("app.shared.core.config.get_settings") as mock_settings:
        mock_settings.return_value.AWS_ENDPOINT_URL = "http://localhost:4566"
        plugin._get_client(
            session=session,
            service_name="ec2",
            region="us-east-1",
            credentials=credentials,
            config="cfg",
        )

    session.client.assert_called_once()
    _, kwargs = session.client.call_args
    assert kwargs["region_name"] == "us-east-1"
    assert kwargs["endpoint_url"] == "http://localhost:4566"
    assert kwargs["aws_access_key_id"] == "AKIA"
    assert kwargs["aws_secret_access_key"] == "SECRET"
    assert kwargs["aws_session_token"] == "TOKEN"
    assert kwargs["config"] == "cfg"
