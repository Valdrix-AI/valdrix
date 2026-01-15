from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
import aioboto3
from botocore.exceptions import ClientError
import structlog
from app.services.zombies.zombie_plugin import ZombiePlugin
from app.services.pricing.service import PricingService

logger = structlog.get_logger()

class IdleSageMakerPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "idle_sagemaker_endpoints"

    async def scan(self, session: aioboto3.Session, region: str, credentials: Dict[str, str] = None) -> List[Dict[str, Any]]:
        zombies = []
        try:
            async with await self._get_client(session, "sagemaker", region, credentials) as sagemaker:
                paginator = sagemaker.get_paginator("list_endpoints")
                async with await self._get_client(session, "cloudwatch", region, credentials) as cloudwatch:
                    async for page in paginator.paginate(StatusEquals="InService"):
                        for ep in page.get("Endpoints", []):
                            name = ep["EndpointName"]
                            try:
                                end_time = datetime.now(timezone.utc)
                                start_time = end_time - timedelta(days=7)

                                metrics = await cloudwatch.get_metric_statistics(
                                    Namespace="AWS/SageMaker",
                                    MetricName="Invocations",
                                    Dimensions=[{"Name": "EndpointName", "Value": name}],
                                    StartTime=start_time, EndTime=end_time, Period=604800, Statistics=["Sum"]
                                )
                                total_invocations = sum(d.get("Sum", 0) for d in metrics.get("Datapoints", []))
                                if total_invocations == 0:
                                    zombies.append({
                                        "resource_id": name,
                                        "resource_type": "SageMaker Endpoint",
                                        "monthly_cost": PricingService.estimate_monthly_waste(
                                            provider="aws",
                                            resource_type="sagemaker",
                                            region=region
                                        ),
                                        "recommendation": "Delete idle endpoint",
                                        "action": "delete_sagemaker_endpoint",
                                        "explainability_notes": "SageMaker endpoint has had 0 invocations over the last 7 days.",
                                        "confidence_score": 0.98
                                    })
                            except ClientError as e:
                                logger.warning("sagemaker_metric_fetch_failed", endpoint=name, error=str(e))
        except ClientError as e:
             logger.warning("sagemaker_scan_error", error=str(e))
        return zombies
