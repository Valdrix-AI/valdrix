from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
import aioboto3
from botocore.exceptions import ClientError
import structlog
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
from app.modules.reporting.domain.pricing.service import PricingService

logger = structlog.get_logger()

@registry.register("aws")
class StaleEcrImagesPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "stale_ecr_images"

    async def scan(self, session: aioboto3.Session, region: str, credentials: Dict[str, str] = None, config: Any = None, inventory: Any = None, **kwargs) -> List[Dict[str, Any]]:
        zombies = []
        days_old = 30
        cutoff = datetime.now(timezone.utc) - timedelta(days=days_old)
        try:
            async with self._get_client(session, "ecr", region, credentials, config=config) as ecr:
                repo_paginator = ecr.get_paginator("describe_repositories")
                async for repo_page in repo_paginator.paginate():
                    for repo in repo_page.get("repositories", []):
                        name = repo["repositoryName"]

                        img_paginator = ecr.get_paginator("describe_images")
                        async for img_page in img_paginator.paginate(repositoryName=name):
                            for img in img_page.get("imageDetails", []):
                                if "imageTags" not in img:
                                    pushed_at = img.get("imagePushedAt")
                                    if pushed_at and pushed_at < cutoff:
                                        size_gb = img.get("imageSizeInBytes", 0) / (1024**3)
                                        monthly_cost = size_gb * PricingService.get_hourly_rate(
                                            provider="aws",
                                            resource_type="ecr",
                                            region=region
                                        ) * 730 # GB-month pricing logic simplified
                                        zombies.append({
                                            "resource_id": f"{name}@{img.get('imageDigest', 'unknown')}",
                                            "resource_type": "ECR Image",
                                            "monthly_cost": round(monthly_cost, 4),
                                            "recommendation": "Delete untagged image",
                                            "action": "delete_ecr_image",
                                            "explainability_notes": f"Untagged ECR image pushed on {pushed_at.date()} is not referenced by any standard tags.",
                                            "confidence_score": 0.94
                                        })
        except ClientError as e:
             logger.warning("ecr_scan_error", error=str(e))
        return zombies
