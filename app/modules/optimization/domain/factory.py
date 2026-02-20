from typing import Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.modules.optimization.domain.ports import BaseZombieDetector
from app.modules.optimization.adapters.aws.detector import AWSZombieDetector
from app.modules.optimization.adapters.azure.detector import AzureZombieDetector
from app.modules.optimization.adapters.gcp.detector import GCPZombieDetector
from app.modules.optimization.adapters.saas.detector import SaaSZombieDetector
from app.modules.optimization.adapters.license.detector import LicenseZombieDetector
from app.modules.optimization.adapters.platform.detector import PlatformZombieDetector
from app.modules.optimization.adapters.hybrid.detector import HybridZombieDetector
from app.shared.core.config import get_settings
from app.shared.core.connection_state import resolve_connection_region
from app.shared.core.provider import normalize_provider, resolve_provider_from_connection


class ZombieDetectorFactory:
    """
    Factory to instantiate the correct ZombieDetector based on connection type.
    """

    @staticmethod
    def get_detector(
        connection: Any, region: str = "", db: Optional[AsyncSession] = None
    ) -> BaseZombieDetector:
        class_name = (
            getattr(getattr(connection, "__class__", None), "__name__", "")
            or type(connection).__name__
        )
        type_name = class_name.strip().lower()
        provider = normalize_provider(resolve_provider_from_connection(connection))
        requested_region = str(region or "").strip()
        connection_region = resolve_connection_region(connection)
        effective_region = requested_region or connection_region

        if provider == "aws" or (not provider and "awsconnection" in type_name):
            # Treat "global" as a region hint and resolve to connection/default region
            # so AWS scans are not unintentionally pinned to a hardcoded region.
            aws_region = effective_region
            if aws_region == "global":
                aws_region = connection_region
            if not aws_region or aws_region == "global":
                aws_region = str(get_settings().AWS_DEFAULT_REGION or "").strip() or "us-east-1"
            return AWSZombieDetector(region=aws_region, connection=connection, db=db)

        elif provider == "azure" or (not provider and "azureconnection" in type_name):
            return AzureZombieDetector(region=effective_region, connection=connection, db=db)

        elif provider == "gcp" or (not provider and "gcpconnection" in type_name):
            return GCPZombieDetector(region=effective_region, connection=connection, db=db)

        elif provider == "saas" or (not provider and "saasconnection" in type_name):
            connector_config = getattr(connection, "connector_config", None)
            spend_feed = getattr(connection, "spend_feed", None)
            credentials = {
                "vendor": getattr(connection, "vendor", None),
                "auth_method": getattr(connection, "auth_method", None),
                "api_key": getattr(connection, "api_key", None),
                "connector_config": (
                    connector_config if isinstance(connector_config, dict) else {}
                ),
                "spend_feed": spend_feed if isinstance(spend_feed, list) else [],
            }
            return SaaSZombieDetector(
                region="global",
                connection=connection,
                credentials=credentials,
                db=db,
            )

        elif provider == "license" or (
            not provider and "licenseconnection" in type_name
        ):
            connector_config = getattr(connection, "connector_config", None)
            license_feed = getattr(connection, "license_feed", None)
            credentials = {
                "vendor": getattr(connection, "vendor", None),
                "auth_method": getattr(connection, "auth_method", None),
                "api_key": getattr(connection, "api_key", None),
                "connector_config": (
                    connector_config if isinstance(connector_config, dict) else {}
                ),
                "license_feed": license_feed if isinstance(license_feed, list) else [],
            }
            return LicenseZombieDetector(
                region="global",
                connection=connection,
                credentials=credentials,
                db=db,
            )

        elif provider == "platform" or (
            not provider and "platformconnection" in type_name
        ):
            connector_config = getattr(connection, "connector_config", None)
            spend_feed = getattr(connection, "spend_feed", None)
            credentials = {
                "vendor": getattr(connection, "vendor", None),
                "auth_method": getattr(connection, "auth_method", None),
                "api_key": getattr(connection, "api_key", None),
                "api_secret": getattr(connection, "api_secret", None),
                "connector_config": (
                    connector_config if isinstance(connector_config, dict) else {}
                ),
                "spend_feed": spend_feed if isinstance(spend_feed, list) else [],
            }
            return PlatformZombieDetector(
                region="global",
                connection=connection,
                credentials=credentials,
                db=db,
            )

        elif provider == "hybrid" or (not provider and "hybridconnection" in type_name):
            connector_config = getattr(connection, "connector_config", None)
            spend_feed = getattr(connection, "spend_feed", None)
            credentials = {
                "vendor": getattr(connection, "vendor", None),
                "auth_method": getattr(connection, "auth_method", None),
                "api_key": getattr(connection, "api_key", None),
                "api_secret": getattr(connection, "api_secret", None),
                "connector_config": (
                    connector_config if isinstance(connector_config, dict) else {}
                ),
                "spend_feed": spend_feed if isinstance(spend_feed, list) else [],
            }
            return HybridZombieDetector(
                region="global",
                connection=connection,
                credentials=credentials,
                db=db,
            )

        raise ValueError(
            f"Unsupported connection type: {type_name} (provider={provider})"
        )
