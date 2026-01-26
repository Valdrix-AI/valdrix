from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from app.shared.adapters.aws_utils import map_aws_credentials


# Estimated monthly costs (USD) used for zombie resource impact analysis
ESTIMATED_COSTS = {
    "ebs_volume_gb": 0.10,
    "elastic_ip": 3.60,
    "snapshot_gb": 0.05,
    "ec2_t3_micro": 7.50,
    "ec2_t3_small": 15.00,
    "ec2_t3_medium": 30.00,
    "ec2_m5_large": 69.12,
    "ec2_default": 10.00,
    "elb": 20.00,
    "s3_gb": 0.023,
    "ecr_gb": 0.10,
    "sagemaker_endpoint": 108.00,
    "redshift_cluster": 180.00,
    "nat_gateway": 32.40
}

class ZombiePlugin(ABC):
    """
    Abstract base class for Zombie Resource detection plugins.
    Each plugin is responsible for detecting a specific type of zombie resource.
    """

    @property
    @abstractmethod
    def category_key(self) -> str:
        """
        The dictionary key for results (e.g., 'unattached_volumes').
        Used to aggregate results in the final report.
        """
        pass

    @abstractmethod
    async def scan(self, *args, **kwargs) -> List[Dict[str, Any]]:
        """
        Scan for zombie resources.
        
        Subclasses should document their expected arguments (e.g., session, client, region).
        """
        pass

    def _get_client(self, session: Any, service_name: str, region: str, credentials: Dict[str, str] = None, config: Any = None):
        """Helper to get AWS client with optional credentials and config."""
        from app.shared.core.config import get_settings
        settings = get_settings()
        
        kwargs = {"region_name": region}
        if settings.AWS_ENDPOINT_URL:
            kwargs["endpoint_url"] = settings.AWS_ENDPOINT_URL
            
        if credentials:
            kwargs.update(map_aws_credentials(credentials))
            
        if config:
            kwargs["config"] = config
        return session.client(service_name, **kwargs)
