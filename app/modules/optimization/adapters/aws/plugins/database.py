from typing import List, Dict, Any
from datetime import datetime, timedelta, timezone
from botocore.exceptions import ClientError
import structlog
from app.modules.optimization.domain.plugin import ZombiePlugin
from app.modules.optimization.domain.registry import registry
from app.modules.reporting.domain.pricing.service import PricingService

logger = structlog.get_logger()


@registry.register("aws")
class IdleRdsPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "idle_rds_databases"

    async def scan(


    

    self,


    

    session: Any,


    

    region: str,


    

    credentials: Dict[str, Any] | None = None,


    

    config: Any = None,


    

    inventory: Any = None,


    

    **kwargs: Any,


    ) -> List[Dict[str, Any]]:
        zombies = []
        dbs = []
        connection_threshold = 1
        days = 7

        # CUR-First Detection (Zero API Cost)
        cur_records = kwargs.get("cur_records")
        if cur_records:
            from app.shared.analysis.cur_usage_analyzer import CURUsageAnalyzer

            analyzer = CURUsageAnalyzer(cur_records)
            return analyzer.find_idle_rds_databases(days=days)

        try:
            async with self._get_client(
                session, "rds", region, credentials, config=config
            ) as rds:
                paginator = rds.get_paginator("describe_db_instances")
                async for page in paginator.paginate():
                    for db in page.get("DBInstances", []):
                        dbs.append(
                            {
                                "id": db["DBInstanceIdentifier"],
                                "class": db.get("DBInstanceClass", "unknown"),
                                "engine": db.get("Engine", "unknown"),
                            }
                        )

            if not dbs:
                return []

            end_time = datetime.now(timezone.utc)
            start_time = end_time - timedelta(days=days)

            async with self._get_client(
                session, "cloudwatch", region, credentials, config=config
            ) as cloudwatch:
                for i in range(0, len(dbs), 500):
                    batch = dbs[i : i + 500]
                    fixed_queries = []
                    for idx, db in enumerate(batch):
                        fixed_queries.append(
                            {
                                "Id": f"m{idx}",
                                "MetricStat": {
                                    "Metric": {
                                        "Namespace": "AWS/RDS",
                                        "MetricName": "DatabaseConnections",
                                        "Dimensions": [
                                            {
                                                "Name": "DBInstanceIdentifier",
                                                "Value": db["id"],
                                            }
                                        ],
                                    },
                                    "Period": 86400 * days,
                                    "Stat": "Average",
                                },
                            }
                        )

                    results = await cloudwatch.get_metric_data(
                        MetricDataQueries=fixed_queries,
                        StartTime=start_time,
                        EndTime=end_time,
                    )

                    for idx, db in enumerate(batch):
                        res = next(
                            (
                                r
                                for r in results.get("MetricDataResults", [])
                                if r["Id"] == f"m{idx}"
                            ),
                            None,
                        )
                        if res and res.get("Values"):
                            avg_connections = res["Values"][0]
                            if avg_connections < connection_threshold:
                                db_class = db["class"]
                                monthly_cost = PricingService.estimate_monthly_waste(
                                    provider="aws",
                                    resource_type="rds",
                                    resource_size=db_class,
                                    region=region,
                                )

                                zombies.append(
                                    {
                                        "resource_id": db["id"],
                                        "resource_type": "RDS Database",
                                        "db_class": db_class,
                                        "engine": db["engine"],
                                        "avg_connections": round(avg_connections, 2),
                                        "monthly_cost": round(monthly_cost, 2),
                                        "recommendation": "Stop or delete if not needed",
                                        "action": "stop_rds_instance",
                                        "supports_backup": True,
                                        "explainability_notes": f"Database has shown near-zero active connections (avg {round(avg_connections, 2)}) over the past {days} days.",
                                        "confidence_score": 0.96,
                                    }
                                )

        except ClientError as e:
            logger.warning("idle_rds_scan_error", error=str(e))

        return zombies


@registry.register("aws")
class ColdRedshiftPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "cold_redshift_clusters"

    async def scan(


    

    self,


    

    session: Any,


    

    region: str,


    

    credentials: Dict[str, Any] | None = None,


    

    config: Any = None,


    

    inventory: Any = None,


    

    **kwargs: Any,


    ) -> List[Dict[str, Any]]:
        zombies = []
        days = 7

        # CUR-First Detection (Zero API Cost)
        cur_records = kwargs.get("cur_records")
        if cur_records:
            from app.shared.analysis.cur_usage_analyzer import CURUsageAnalyzer

            analyzer = CURUsageAnalyzer(cur_records)
            return analyzer.find_idle_redshift_clusters(days=days)

        try:
            async with self._get_client(
                session, "redshift", region, credentials, config=config
            ) as redshift:
                paginator = redshift.get_paginator("describe_clusters")
                async with self._get_client(
                    session, "cloudwatch", region, credentials, config=config
                ) as cloudwatch:
                    async for page in paginator.paginate():
                        for cluster in page.get("Clusters", []):
                            cluster_id = cluster["ClusterIdentifier"]
                            try:
                                end_time = datetime.now(timezone.utc)
                                start_time = end_time - timedelta(days=7)

                                metrics = await cloudwatch.get_metric_statistics(
                                    Namespace="AWS/Redshift",
                                    MetricName="DatabaseConnections",
                                    Dimensions=[
                                        {
                                            "Name": "ClusterIdentifier",
                                            "Value": cluster_id,
                                        }
                                    ],
                                    StartTime=start_time,
                                    EndTime=end_time,
                                    Period=604800,
                                    Statistics=["Sum"],
                                )
                                total_conns = sum(
                                    d.get("Sum", 0)
                                    for d in metrics.get("Datapoints", [])
                                )
                                if total_conns == 0:
                                    zombies.append(
                                        {
                                            "resource_id": cluster_id,
                                            "resource_type": "Redshift Cluster",
                                            "monthly_cost": PricingService.estimate_monthly_waste(
                                                provider="aws",
                                                resource_type="redshift",
                                                region=region,
                                            ),
                                            "recommendation": "Delete idle cluster",
                                            "action": "delete_redshift_cluster",
                                            "explainability_notes": "Redshift cluster has had 0 database connections detected in the last 7 days.",
                                            "confidence_score": 0.97,
                                        }
                                    )
                            except ClientError as e:
                                logger.warning(
                                    "redshift_metric_fetch_failed",
                                    cluster=cluster_id,
                                    error=str(e),
                                )
        except ClientError as e:
            logger.warning("redshift_scan_error", error=str(e))
        return zombies


@registry.register("aws")
class IdleDynamoDbPlugin(ZombiePlugin):
    @property
    def category_key(self) -> str:
        return "idle_dynamodb_tables"

    async def scan(


    

    self,


    

    session: Any,


    

    region: str,


    

    credentials: Dict[str, Any] | None = None,


    

    config: Any = None,


    

    inventory: Any = None,


    

    **kwargs: Any,


    ) -> List[Dict[str, Any]]:
        zombies = []
        days = 7

        try:
            async with self._get_client(
                session, "dynamodb", region, credentials, config=config
            ) as ddb:
                paginator = ddb.get_paginator("list_tables")
                async with self._get_client(
                    session, "cloudwatch", region, credentials, config=config
                ) as cloudwatch:
                    async for page in paginator.paginate():
                        for table_name in page.get("TableNames", []):
                            try:
                                # Get capacity details
                                desc = await ddb.describe_table(TableName=table_name)
                                table = desc["Table"]
                                
                                # Skip On-Demand tables (pay-per-req) as they don't incur idle costs (mostly)
                                billing_mode = table.get("BillingModeSummary", {}).get("BillingMode", "PROVISIONED")
                                if billing_mode == "PAY_PER_REQUEST":
                                    continue

                                rcu = table.get("ProvisionedThroughput", {}).get("ReadCapacityUnits", 0)
                                wcu = table.get("ProvisionedThroughput", {}).get("WriteCapacityUnits", 0)
                                
                                if rcu == 0 and wcu == 0:
                                    continue

                                # Check usage metrics
                                end_time = datetime.now(timezone.utc)
                                start_time = end_time - timedelta(days=days)

                                metrics = await cloudwatch.get_metric_data(
                                    MetricDataQueries=[
                                        {
                                            "Id": "consumed_rcu",
                                            "MetricStat": {
                                                "Metric": {
                                                    "Namespace": "AWS/DynamoDB",
                                                    "MetricName": "ConsumedReadCapacityUnits",
                                                    "Dimensions": [{"Name": "TableName", "Value": table_name}],
                                                },
                                                "Period": 86400 * days,
                                                "Stat": "Sum",
                                            },
                                        },
                                        {
                                            "Id": "consumed_wcu",
                                            "MetricStat": {
                                                "Metric": {
                                                    "Namespace": "AWS/DynamoDB",
                                                    "MetricName": "ConsumedWriteCapacityUnits",
                                                    "Dimensions": [{"Name": "TableName", "Value": table_name}],
                                                },
                                                "Period": 86400 * days,
                                                "Stat": "Sum",
                                            },
                                        }
                                    ],
                                    StartTime=start_time,
                                    EndTime=end_time,
                                )

                                total_usage = 0
                                for res in metrics.get("MetricDataResults", []):
                                    total_usage += sum(res.get("Values", []))

                                if total_usage == 0:
                                    # Estimate Cost: ~$0.00013 per RCU-hr, ~$0.00065 per WCU-hr (Region dependent, using us-east-1 avg)
                                    # Monthly hours = 730
                                    cost_rcu = rcu * 0.00013 * 730
                                    cost_wcu = wcu * 0.00065 * 730
                                    monthly_cost = cost_rcu + cost_wcu

                                    zombies.append(
                                        {
                                            "resource_id": table_name,
                                            "resource_type": "DynamoDB Table",
                                            "rcu": rcu,
                                            "wcu": wcu,
                                            "monthly_cost": round(monthly_cost, 2),
                                            "recommendation": "Switch to On-Demand or Delete",
                                            "action": "modify_dynamodb_table",
                                            "explainability_notes": f"Table has Provisioned Capacity ({rcu} RCU / {wcu} WCU) but consumed 0 units in the last {days} days.",
                                            "confidence_score": 0.95,
                                        }
                                    )

                            except ClientError as e:
                                logger.warning("dynamodb_table_check_failed", table=table_name, error=str(e))

        except ClientError as e:
            logger.warning("dynamodb_scan_error", error=str(e))

        return zombies
