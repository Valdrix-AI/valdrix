import os
from unittest.mock import MagicMock, patch

import app.shared.core.sentry as sentry_module
from app.shared.core.sentry import init_sentry


def _prepare_sentry_mocks():
    sentry_module.sentry_sdk = MagicMock()
    fastapi_integration = MagicMock()
    sqlalchemy_integration = MagicMock()
    logging_integration = MagicMock()
    sentry_module.FastApiIntegration = fastapi_integration
    sentry_module.SqlalchemyIntegration = sqlalchemy_integration
    sentry_module.LoggingIntegration = logging_integration
    return fastapi_integration, sqlalchemy_integration, logging_integration


def test_init_sentry_production_sampling_and_release():
    _prepare_sentry_mocks()
    with patch.object(sentry_module, "SENTRY_AVAILABLE", True):
        with patch.dict(
            os.environ,
            {
                "SENTRY_DSN": "https://test@sentry.io/1",
                "ENVIRONMENT": "production",
                "APP_VERSION": "2.3.4",
            },
            clear=False,
        ):
            assert init_sentry() is True

    _, kwargs = sentry_module.sentry_sdk.init.call_args
    assert kwargs["environment"] == "production"
    assert kwargs["release"] == "valdrics@2.3.4"
    assert kwargs["traces_sample_rate"] == 0.1
    assert kwargs["profiles_sample_rate"] == 0.1


def test_init_sentry_default_env_and_sampling():
    _prepare_sentry_mocks()
    with patch.object(sentry_module, "SENTRY_AVAILABLE", True):
        with patch.dict(
            os.environ, {"SENTRY_DSN": "https://test@sentry.io/1"}, clear=True
        ):
            assert init_sentry() is True

    _, kwargs = sentry_module.sentry_sdk.init.call_args
    assert kwargs["environment"] == "development"
    assert kwargs["release"] == "valdrics@0.1.0"
    assert kwargs["traces_sample_rate"] == 1.0
    assert kwargs["profiles_sample_rate"] == 1.0


def test_init_sentry_integrations_wired():
    fastapi_integration, sqlalchemy_integration, logging_integration = (
        _prepare_sentry_mocks()
    )
    with patch.object(sentry_module, "SENTRY_AVAILABLE", True):
        with patch.dict(
            os.environ, {"SENTRY_DSN": "https://test@sentry.io/1"}, clear=True
        ):
            assert init_sentry() is True

    fastapi_integration.assert_called_once_with(transaction_style="endpoint")
    sqlalchemy_integration.assert_called_once_with()
    logging_integration.assert_called_once_with(level=None, event_level=40)
