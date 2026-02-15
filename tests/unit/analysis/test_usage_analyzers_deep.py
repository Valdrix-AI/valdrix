from app.shared.analysis.cur_usage_analyzer import CURUsageAnalyzer
from app.shared.analysis.azure_usage_analyzer import AzureUsageAnalyzer


class TestCURUsageAnalyzer:
    def test_find_low_usage_instances(self):
        records = [
            # Idle instance (low usage amount)
            {
                "line_item_resource_id": "i-123",
                "line_item_usage_type": "USE2-BoxUsage:t3.micro",
                "line_item_usage_amount": "1.0",  # 1 hour of usage over 14 days (336 hours)
                "line_item_product_code": "AmazonEC2",
                "product_instance_type": "t3.micro",
                "line_item_unblended_cost": "0.01",
            },
            # Active instance
            {
                "line_item_resource_id": "i-active",
                "line_item_usage_type": "USE2-BoxUsage:t3.large",
                "line_item_usage_amount": "300.0",
                "line_item_product_code": "AmazonEC2",
                "product_instance_type": "t3.large",
                "line_item_unblended_cost": "10.0",
            },
        ]
        analyzer = CURUsageAnalyzer(records)
        results = analyzer.find_low_usage_instances(days=14)

        assert len(results) == 1
        assert results[0]["resource_id"] == "i-123"
        assert results[0]["usage_ratio"] < 0.30

    def test_find_unused_ebs_volumes(self):
        records = [
            # Unused volume (has cost, but no IO)
            {
                "line_item_resource_id": "vol-unused",
                "line_item_usage_type": "EBS:VolumeUsage.gp2",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "15.0",
                "line_item_usage_amount": "100",  # 100GB
            },
            # Active volume (has IOPS records)
            {
                "line_item_resource_id": "vol-active",
                "line_item_usage_type": "EBS:VolumeUsage.gp2",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "15.0",
                "line_item_usage_amount": "100",
            },
            {
                "line_item_resource_id": "vol-active",
                "line_item_usage_type": "EBS:VolumeIOUsage",
                "line_item_usage_amount": "5000",
                "line_item_product_code": "AmazonEC2",
            },
        ]
        analyzer = CURUsageAnalyzer(records)
        results = analyzer.find_unused_ebs_volumes()

        assert len(results) == 1
        assert results[0]["resource_id"] == "vol-unused"
        assert results[0]["size_gb"] == 100

    def test_find_idle_rds_databases(self):
        records = [
            # Idle RDS
            {
                "line_item_resource_id": "db-idle",
                "line_item_usage_type": "InstanceUsage:db.t3.medium",
                "line_item_product_code": "AmazonRDS",
                "line_item_usage_amount": "1.0",  # 1 hour in 7 days
                "product_instance_type": "db.t3.medium",
                "product_database_engine": "postgres",
                "line_item_unblended_cost": "0.05",
            }
        ]
        analyzer = CURUsageAnalyzer(records)
        results = analyzer.find_idle_rds_databases(days=7)
        assert len(results) == 1
        assert results[0]["resource_id"] == "db-idle"

    def test_find_idle_redshift_clusters(self):
        records = [
            # Idle Redshift
            {
                "line_item_resource_id": "redshift-idle",
                "line_item_usage_type": "Node:dc2.large",
                "line_item_product_code": "AmazonRedshift",
                "line_item_usage_amount": "1.0",
                "product_instance_type": "dc2.large",
                "line_item_unblended_cost": "0.25",
            }
        ]
        analyzer = CURUsageAnalyzer(records)
        results = analyzer.find_idle_redshift_clusters(days=7)
        assert len(results) == 1
        assert results[0]["resource_id"] == "redshift-idle"

    def test_find_idle_nat_gateways(self):
        records = [
            # Idle NAT (cost but no data)
            {
                "line_item_resource_id": "nat-idle",
                "line_item_usage_type": "USE2-NatGateway-Hours",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "20.0",
            },
            {
                "line_item_resource_id": "nat-idle",
                "line_item_usage_type": "USE2-NatGateway-Bytes",
                "line_item_usage_amount": "0.01",  # 10MB
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "0.01",
            },
        ]
        analyzer = CURUsageAnalyzer(records)
        results = analyzer.find_idle_nat_gateways(days=7)
        assert len(results) == 1
        assert results[0]["resource_id"] == "nat-idle"
        assert results[0]["data_processed_gb"] < 1.0

    def test_find_idle_sagemaker_endpoints(self):
        records = [
            {
                "line_item_resource_id": "sm-idle",
                "line_item_usage_type": "Hosting:ml.t2.medium",
                "line_item_product_code": "AmazonSageMaker",
                "line_item_usage_amount": "1.0",
                "product_instance_type": "ml.t2.medium",
                "line_item_unblended_cost": "0.10",
            }
        ]
        analyzer = CURUsageAnalyzer(records)
        results = analyzer.find_idle_sagemaker_endpoints(days=7)
        assert len(results) == 1
        assert results[0]["resource_id"] == "sm-idle"

    def test_find_idle_elasticache_clusters(self):
        records = [
            {
                "line_item_resource_id": "cache-idle",
                "line_item_usage_type": "NodeUsage:cache.t3.micro",
                "line_item_product_code": "AmazonElastiCache",
                "line_item_usage_amount": "1.0",
                "product_instance_type": "cache.t3.micro",
                "product_cache_engine": "redis",
                "line_item_unblended_cost": "0.05",
            }
        ]
        analyzer = CURUsageAnalyzer(records)
        results = analyzer.find_idle_elasticache_clusters(days=7)
        assert len(results) == 1
        assert results[0]["resource_id"] == "cache-idle"

    def test_find_idle_eks_clusters(self):
        records = [
            {
                "line_item_resource_id": "eks-active",
                "line_item_product_code": "AmazonEKS",
                "line_item_usage_amount": "168",  # Full week
                "line_item_unblended_cost": "60.0",  # $0.10 * 168 = $16.8, but $60 indicates something
            }
        ]
        analyzer = CURUsageAnalyzer(records)
        results = analyzer.find_idle_eks_clusters(days=7)
        assert len(results) == 1
        assert results[0]["resource_id"] == "eks-active"

    def test_find_low_usage_instances_exhaust_branches(self):
        records = [
            # Record with wrong product code
            {
                "line_item_product_code": "WrongService",
                "line_item_usage_type": "BoxUsage",
            },
            # Record with wrong usage type
            {
                "line_item_product_code": "AmazonEC2",
                "line_item_usage_type": "DataTransfer",
            },
            # Record with wrong resource ID prefix
            {
                "line_item_product_code": "AmazonEC2",
                "line_item_usage_type": "BoxUsage",
                "line_item_resource_id": "other-id",
            },
            # Valid idle instance
            {
                "line_item_resource_id": "i-123",
                "line_item_usage_type": "BoxUsage",
                "line_item_product_code": "AmazonEC2",
                "line_item_usage_amount": "1.0",
                "line_item_unblended_cost": "0.01",
            },
        ]
        analyzer = CURUsageAnalyzer(records)
        results = analyzer.find_low_usage_instances(days=14)
        assert len(results) == 1

    def test_find_unused_ebs_volumes_negative(self):
        records = [
            {"line_item_product_code": "AmazonS3"},  # Wrong product
            {
                "line_item_product_code": "AmazonEC2",
                "line_item_usage_type": "BoxUsage",
            },  # Wrong usage type
            {
                "line_item_resource_id": "vol-unused",
                "line_item_usage_type": "EBS:VolumeUsage",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "10.0",
            },
        ]
        analyzer = CURUsageAnalyzer(records)
        results = analyzer.find_unused_ebs_volumes()
        assert len(results) == 1

    def test_find_idle_rds_negative(self):
        records = [
            {"line_item_product_code": "AmazonEC2"},
            {"line_item_product_code": "AmazonRDS", "line_item_usage_type": "Storage"},
            {
                "line_item_resource_id": "db-idle",
                "line_item_product_code": "AmazonRDS",
                "line_item_usage_type": "InstanceUsage",
                "line_item_usage_amount": "0.1",
            },
        ]
        analyzer = CURUsageAnalyzer(records)
        assert len(analyzer.find_idle_rds_databases()) == 1

    def test_find_idle_redshift_negative(self):
        records = [
            {"line_item_product_code": "AmazonRDS"},
            {
                "line_item_product_code": "AmazonRedshift",
                "line_item_usage_type": "Storage",
            },
            {
                "line_item_resource_id": "rs-idle",
                "line_item_product_code": "AmazonRedshift",
                "line_item_usage_type": "Node",
                "line_item_usage_amount": "0.1",
            },
        ]
        analyzer = CURUsageAnalyzer(records)
        assert len(analyzer.find_idle_redshift_clusters()) == 1

    def test_find_idle_nat_negative(self):
        records = [
            {"line_item_product_code": "AmazonS3"},
            {"line_item_product_code": "AmazonEC2", "line_item_usage_type": "BoxUsage"},
            {
                "line_item_resource_id": "nat-idle",
                "line_item_product_code": "AmazonEC2",
                "line_item_usage_type": "NatGateway-Hours",
                "line_item_unblended_cost": "1.0",
            },
        ]
        analyzer = CURUsageAnalyzer(records)
        assert len(analyzer.find_idle_nat_gateways()) == 1

    def test_find_idle_sagemaker_negative(self):
        records = [
            {"line_item_product_code": "AmazonEC2"},
            {
                "line_item_product_code": "AmazonSageMaker",
                "line_item_usage_type": "Training",
            },
            {
                "line_item_resource_id": "sm-idle",
                "line_item_product_code": "AmazonSageMaker",
                "line_item_usage_type": "Hosting",
                "line_item_usage_amount": "0.1",
            },
        ]
        analyzer = CURUsageAnalyzer(records)
        assert len(analyzer.find_idle_sagemaker_endpoints()) == 1

    def test_find_idle_elasticache_negative(self):
        records = [
            {"line_item_product_code": "AmazonRDS"},
            {
                "line_item_product_code": "AmazonElastiCache",
                "line_item_usage_type": "Storage",
            },
            {
                "line_item_resource_id": "cache-idle",
                "line_item_product_code": "AmazonElastiCache",
                "line_item_usage_type": "NodeUsage",
                "line_item_usage_amount": "0.1",
            },
        ]
        analyzer = CURUsageAnalyzer(records)
        assert len(analyzer.find_idle_elasticache_clusters()) == 1

    def test_find_idle_eks_negative(self):
        records = [
            {"line_item_product_code": "AmazonEC2"},
            {
                "line_item_resource_id": "eks-idle",
                "line_item_product_code": "AmazonEKS",
                "line_item_unblended_cost": "60.0",
            },
        ]
        analyzer = CURUsageAnalyzer(records)
        assert len(analyzer.find_idle_eks_clusters()) == 1


class TestAzureUsageAnalyzer:
    def test_find_idle_vms_negative(self):
        records = [
            {"ResourceId": "other-resource"},
            {
                "ResourceId": "microsoft.compute/virtualmachines/vm1",
                "ServiceName": "Storage",
            },  # Wrong service
            {
                "ResourceId": "microsoft.compute/virtualmachines/vm-idle",
                "ServiceName": "Virtual Machines",
                "PreTaxCost": 60.0,
                "MeterCategory": "Virtual Machines",
            },
        ]
        analyzer = AzureUsageAnalyzer(records)
        assert len(analyzer.find_idle_vms()) == 1

    def test_find_unattached_disks_negative(self):
        records = [
            {"ResourceId": "microsoft.compute/virtualmachines/vm1"},  # Wrong type
            {
                "ResourceId": "microsoft.compute/disks/d1",
                "MeterCategory": "Bandwidth",
            },  # Wrong category
            {
                "ResourceId": "microsoft.compute/disks/d-orphan",
                "MeterCategory": "Managed Disks",
                "PreTaxCost": 10.0,
            },
        ]
        analyzer = AzureUsageAnalyzer(records)
        assert len(analyzer.find_unattached_disks()) == 1

    def test_find_idle_sql_negative(self):
        records = [
            {"ResourceId": "other"},
            {
                "ResourceId": "microsoft.sql/servers/s1/databases/db1",
                "ServiceName": "Storage",
            },  # Wrong service
            {
                "ResourceId": "microsoft.sql/servers/s1/databases/db-idle",
                "ServiceName": "Azure SQL Database",
                "PreTaxCost": 10.0,
                "MeterName": "vCore",
            },
        ]
        analyzer = AzureUsageAnalyzer(records)
        assert len(analyzer.find_idle_sql_databases()) == 1

    def test_find_idle_aks_negative(self):
        records = [
            {"ResourceId": "other"},
            {
                "ResourceId": "microsoft.containerservice/managedclusters/c1",
                "ServiceName": "Storage",
            },  # Wrong service
            {
                "ResourceId": "/subscriptions/s1/resourceGroups/g1/providers/Microsoft.ContainerService/managedClusters/aks-idle",
                "ServiceName": "Azure Kubernetes Service",
                "PreTaxCost": 70.0,
                "MeterName": "Uptime SLA",
            },
        ]
        analyzer = AzureUsageAnalyzer(records)
        assert len(analyzer.find_idle_aks_clusters()) == 1

    def test_find_orphan_ips_negative(self):
        records = [
            {"ResourceId": "other"},
            {
                "ResourceId": "microsoft.network/publicipaddresses/ip1",
                "MeterName": "Other",
            },  # Wrong meter
            {
                "ResourceId": "microsoft.network/publicipaddresses/ip-orphan",
                "MeterName": "Static IP Address",
                "PreTaxCost": 5.0,
            },
        ]
        analyzer = AzureUsageAnalyzer(records)
        assert len(analyzer.find_orphan_public_ips()) == 1

    def test_find_unused_app_service_negative(self):
        records = [
            {"ResourceId": "other"},
            {"ResourceId": "microsoft.web/serverfarms/p1", "ServiceName": "Other"},
            {
                "ResourceId": "microsoft.web/serverfarms/plan-idle",
                "ServiceName": "App Service",
                "PreTaxCost": 10.0,
            },
        ]
        analyzer = AzureUsageAnalyzer(records)
        assert len(analyzer.find_unused_app_service_plans()) == 1

    def test_find_old_snapshots_negative(self):
        records = [
            {"ResourceId": "other"},
            {"ResourceId": "microsoft.compute/snapshots/s1", "MeterCategory": "Other"},
            {
                "ResourceId": "microsoft.compute/snapshots/snap-old",
                "MeterCategory": "Disk Snapshots",
                "PreTaxCost": 5.0,
            },
        ]
        analyzer = AzureUsageAnalyzer(records)
        assert len(analyzer.find_old_snapshots()) == 1

    def test_find_orphan_nics(self):
        # Coverage for the empty method
        analyzer = AzureUsageAnalyzer(
            [{"ResourceId": "microsoft.network/networkinterfaces/nic1"}]
        )
        assert analyzer.find_orphan_nics() == []
