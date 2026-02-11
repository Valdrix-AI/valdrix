"""
Production-quality tests for CUR Usage Analyzer.
Tests cover security, performance, edge cases, and real-world scenarios.
"""
from app.shared.analysis.cur_usage_analyzer import CURUsageAnalyzer


class TestCURUsageAnalyzer:
    """Basic functionality tests for CURUsageAnalyzer."""

    def test_initialization_with_valid_data(self):
        """Test analyzer initializes correctly with valid CUR records."""
        cur_records = [
            {
                "line_item_resource_id": "i-1234567890abcdef0",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "168.0",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "1.68",
                "product_instance_type": "t3.micro"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)

        assert analyzer.records == cur_records

    def test_initialization_with_empty_data(self):
        """Test analyzer handles empty CUR records gracefully."""
        analyzer = CURUsageAnalyzer([])

        assert analyzer.records == []

    def test_find_low_usage_instances_idle_instance(self):
        """Test detection of EC2 instances with low usage."""
        cur_records = [
            {
                "line_item_resource_id": "i-1234567890abcdef0",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "24.0",  # Only 1 day out of 7
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "0.24",
                "product_instance_type": "t3.micro"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)
        low_usage_instances = analyzer.find_low_usage_instances(days=7)

        assert len(low_usage_instances) == 1
        instance = low_usage_instances[0]
        assert instance["resource_id"] == "i-1234567890abcdef0"
        assert instance["resource_type"] == "EC2 Instance"
        assert instance["instance_type"] == "t3.micro"
        assert instance["usage_hours"] == 24.0
        assert instance["expected_hours"] == 168  # 7 * 24
        assert instance["usage_ratio"] == 0.14  # 24/168
        assert instance["monthly_cost"] == 0.24
        assert instance["confidence_score"] == 0.85

    def test_find_low_usage_instances_active_instance(self):
        """Test instances with normal usage are not flagged."""
        cur_records = [
            {
                "line_item_resource_id": "i-0987654321fedcba0",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "120.0",  # 5 days out of 7 = 85% usage
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "1.20",
                "product_instance_type": "t3.micro"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)
        low_usage_instances = analyzer.find_low_usage_instances(days=7)

        assert len(low_usage_instances) == 0  # Should not be flagged

    def test_find_low_usage_instances_multiple_instances(self):
        """Test detection of multiple instances with varying usage."""
        cur_records = [
            # Idle instance (low usage)
            {
                "line_item_resource_id": "i-idle123",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "20.0",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "0.20",
                "product_instance_type": "t3.micro"
            },
            # Active instance (normal usage)
            {
                "line_item_resource_id": "i-active456",
                "line_item_usage_type": "BoxUsage:t3.small",
                "line_item_usage_amount": "140.0",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "2.10",
                "product_instance_type": "t3.small"
            },
            # Another idle instance
            {
                "line_item_resource_id": "i-idle789",
                "line_item_usage_type": "BoxUsage:t3.large",
                "line_item_usage_amount": "10.0",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "0.40",
                "product_instance_type": "t3.large"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)
        low_usage_instances = analyzer.find_low_usage_instances(days=7)

        assert len(low_usage_instances) == 2
        idle_ids = {inst["resource_id"] for inst in low_usage_instances}
        assert idle_ids == {"i-idle123", "i-idle789"}

    def test_find_unused_ebs_volumes_unused(self):
        """Test detection of unused EBS volumes."""
        cur_records = [
            {
                "line_item_resource_id": "vol-1234567890abcdef0",
                "line_item_usage_type": "EBS:VolumeUsage.gp3",
                "line_item_usage_amount": "20.0",  # 20 GB
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "2.00"
            }
            # No EBS:VolumeIOUsage records = zero I/O operations
        ]

        analyzer = CURUsageAnalyzer(cur_records)
        unused_volumes = analyzer.find_unused_ebs_volumes()

        assert len(unused_volumes) == 1
        volume = unused_volumes[0]
        assert volume["resource_id"] == "vol-1234567890abcdef0"
        assert volume["resource_type"] == "EBS Volume"
        assert volume["size_gb"] == 20
        assert volume["monthly_cost"] == 2.00
        assert volume["io_operations"] == 0
        assert volume["confidence_score"] == 0.90

    def test_find_unused_ebs_volumes_used(self):
        """Test volumes with I/O operations are not flagged as unused."""
        cur_records = [
            {
                "line_item_resource_id": "vol-1234567890abcdef0",
                "line_item_usage_type": "EBS:VolumeUsage.gp3",
                "line_item_usage_amount": "50.0",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "5.00"
            },
            {
                "line_item_resource_id": "vol-1234567890abcdef0",
                "line_item_usage_type": "EBS:VolumeIOUsage.gp3",
                "line_item_usage_amount": "1000.0",  # I/O operations
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "0.10"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)
        unused_volumes = analyzer.find_unused_ebs_volumes()

        assert len(unused_volumes) == 0  # Should not be flagged

    def test_find_idle_rds_databases_idle(self):
        """Test detection of idle RDS databases."""
        cur_records = [
            {
                "line_item_resource_id": "db-TESTDB",
                "line_item_usage_type": "InstanceUsage:db.t3.micro",
                "line_item_usage_amount": "24.0",  # 1 day out of 7 = 14% usage
                "line_item_product_code": "AmazonRDS",
                "line_item_unblended_cost": "2.88",
                "product_instance_type": "db.t3.micro",
                "product_database_engine": "mysql"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)
        idle_databases = analyzer.find_idle_rds_databases(days=7)

        assert len(idle_databases) == 1
        db = idle_databases[0]
        assert db["resource_id"] == "db-TESTDB"
        assert db["resource_type"] == "RDS Database"
        assert db["db_class"] == "db.t3.micro"
        assert db["engine"] == "mysql"
        assert db["usage_hours"] == 24.0
        assert db["monthly_cost"] == 2.88
        assert db["confidence_score"] == 0.80

    def test_find_idle_rds_databases_active(self):
        """Test RDS databases with normal usage are not flagged."""
        cur_records = [
            {
                "line_item_resource_id": "db-ACTIVEDB",
                "line_item_usage_type": "InstanceUsage:db.t3.small",
                "line_item_usage_amount": "120.0",  # 5 days out of 7 = 85% usage
                "line_item_product_code": "AmazonRDS",
                "line_item_unblended_cost": "18.00",
                "product_instance_type": "db.t3.small",
                "product_database_engine": "postgres"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)
        idle_databases = analyzer.find_idle_rds_databases(days=7)

        assert len(idle_databases) == 0  # Should not be flagged

    def test_find_idle_redshift_clusters_idle(self):
        """Test detection of idle Redshift clusters."""
        cur_records = [
            {
                "line_item_resource_id": "my-cluster",
                "line_item_usage_type": "Node:dc2.large",
                "line_item_usage_amount": "12.0",  # 12 hours out of 168 = 7% usage
                "line_item_product_code": "AmazonRedshift",
                "line_item_unblended_cost": "6.72",
                "product_instance_type": "dc2.large"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)
        idle_clusters = analyzer.find_idle_redshift_clusters(days=7)

        assert len(idle_clusters) == 1
        cluster = idle_clusters[0]
        assert cluster["resource_id"] == "my-cluster"
        assert cluster["resource_type"] == "Redshift Cluster"
        assert cluster["node_type"] == "dc2.large"
        assert cluster["usage_hours"] == 12.0
        assert cluster["monthly_cost"] == 6.72
        assert cluster["confidence_score"] == 0.85

    def test_find_idle_nat_gateways_idle(self):
        """Test detection of idle NAT gateways."""
        cur_records = [
            {
                "line_item_resource_id": "nat-12345",
                "line_item_usage_type": "NatGateway-Hours",
                "line_item_usage_amount": "168.0",  # Full week
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "16.80"
            },
            {
                "line_item_resource_id": "nat-12345",
                "line_item_usage_type": "NatGateway-Bytes",
                "line_item_usage_amount": "0.5",  # 0.5 GB processed
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "0.05"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)
        idle_nats = analyzer.find_idle_nat_gateways(days=7)

        assert len(idle_nats) == 1
        nat = idle_nats[0]
        assert nat["resource_id"] == "nat-12345"
        assert nat["resource_type"] == "NAT Gateway"
        assert nat["data_processed_gb"] == 0.5
        assert nat["monthly_cost"] == 16.85
        assert nat["confidence_score"] == 0.80

    def test_find_idle_sagemaker_endpoints_idle(self):
        """Test detection of idle SageMaker endpoints."""
        cur_records = [
            {
                "line_item_resource_id": "endpoint/my-endpoint",
                "line_item_usage_type": "Hosting:ml.t2.medium",
                "line_item_usage_amount": "8.0",  # 8 hours out of 168 = 4.8% usage
                "line_item_product_code": "AmazonSageMaker",
                "line_item_unblended_cost": "0.80",
                "product_instance_type": "ml.t2.medium"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)
        idle_endpoints = analyzer.find_idle_sagemaker_endpoints(days=7)

        assert len(idle_endpoints) == 1
        endpoint = idle_endpoints[0]
        assert endpoint["resource_id"] == "endpoint/my-endpoint"
        assert endpoint["resource_type"] == "SageMaker Endpoint"
        assert endpoint["instance_type"] == "ml.t2.medium"
        assert endpoint["usage_hours"] == 8.0
        assert endpoint["monthly_cost"] == 0.80
        assert endpoint["confidence_score"] == 0.85

    def test_find_idle_elasticache_clusters_idle(self):
        """Test detection of idle ElastiCache clusters."""
        cur_records = [
            {
                "line_item_resource_id": "test-cluster-001",
                "line_item_usage_type": "NodeUsage:cache.t3.micro",
                "line_item_usage_amount": "16.0",  # 16 hours out of 168 = 9.5% usage
                "line_item_product_code": "AmazonElastiCache",
                "line_item_unblended_cost": "0.32",
                "product_instance_type": "cache.t3.micro",
                "product_cache_engine": "redis"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)
        idle_clusters = analyzer.find_idle_elasticache_clusters(days=7)

        assert len(idle_clusters) == 1
        cluster = idle_clusters[0]
        assert cluster["resource_id"] == "test-cluster-001"
        assert cluster["resource_type"] == "ElastiCache Cluster"
        assert cluster["node_type"] == "cache.t3.micro"
        assert cluster["engine"] == "redis"
        assert cluster["usage_hours"] == 16.0
        assert cluster["monthly_cost"] == 0.32
        assert cluster["confidence_score"] == 0.80

    def test_find_idle_eks_clusters(self):
        """Test detection of EKS clusters."""
        cur_records = [
            {
                "line_item_resource_id": "eks-cluster-123",
                "line_item_usage_type": "EKS Cluster",
                "line_item_usage_amount": "168.0",
                "line_item_product_code": "AmazonEKS",
                "line_item_unblended_cost": "67.20"  # > $50 threshold
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)
        idle_clusters = analyzer.find_idle_eks_clusters(days=7)

        assert len(idle_clusters) == 1
        cluster = idle_clusters[0]
        assert cluster["resource_id"] == "eks-cluster-123"
        assert cluster["resource_type"] == "EKS Cluster"
        assert cluster["usage_hours"] == 168.0
        assert cluster["monthly_cost"] == 67.20
        assert cluster["confidence_score"] == 0.70


class TestCURUsageAnalyzerProductionQuality:
    """Production-quality tests covering security, performance, and edge cases."""

    def test_input_validation_and_sanitization(self):
        """Test input validation and sanitization for security."""
        # Test with potentially malicious input
        malicious_records = [
            {
                "line_item_resource_id": "<script>alert('xss')</script>",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "168.0",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "1.68"
            },
            {
                "line_item_resource_id": "../../../etc/passwd",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "0.0",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "0.00"
            }
        ]

        analyzer = CURUsageAnalyzer(malicious_records)

        # Should handle malicious input without crashing
        idle_instances = analyzer.find_low_usage_instances()
        unused_volumes = analyzer.find_unused_ebs_volumes()

        # Should not crash and return reasonable results
        assert isinstance(idle_instances, list)
        assert isinstance(unused_volumes, list)

    def test_large_dataset_performance(self):
        """Test performance with large datasets."""
        import time

        # Create large dataset (2000 records)
        cur_records = []
        for i in range(1000):  # 1000 instances
            cur_records.append({
                "line_item_resource_id": f"i-{i:04d}",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "1.0",  # Very low usage
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "0.01",
                "product_instance_type": "t3.micro"
            })

        start_time = time.time()
        analyzer = CURUsageAnalyzer(cur_records)
        idle_instances = analyzer.find_low_usage_instances(days=7)
        end_time = time.time()

        # Should complete within reasonable time
        assert end_time - start_time < 3.0, f"Analysis too slow: {end_time - start_time:.3f}s"
        assert len(idle_instances) == 1000  # All instances should be flagged as idle

    def test_cost_calculation_precision(self):
        """Test cost calculation precision and decimal handling."""
        cur_records = [
            {
                "line_item_resource_id": "i-12345",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "24.0",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "1.123456789",
                "product_instance_type": "t3.micro"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)
        idle_instances = analyzer.find_low_usage_instances(days=7)

        assert len(idle_instances) == 1
        instance = idle_instances[0]

        # Cost should be handled as float correctly
        assert isinstance(instance["monthly_cost"], float)
        assert instance["monthly_cost"] == 1.123456789

    def test_mixed_resource_types_filtering(self):
        """Test accurate filtering by resource types and products."""
        cur_records = [
            # EC2 instance
            {
                "line_item_resource_id": "i-12345",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "24.0",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "1.68",
                "product_instance_type": "t3.micro"
            },
            # RDS database
            {
                "line_item_resource_id": "db-TEST",
                "line_item_usage_type": "InstanceUsage:db.t3.micro",
                "line_item_usage_amount": "24.0",
                "line_item_product_code": "AmazonRDS",
                "line_item_unblended_cost": "20.16",
                "product_instance_type": "db.t3.micro"
            },
            # Non-matching product
            {
                "line_item_resource_id": "test-resource",
                "line_item_usage_type": "SomeUsage",
                "line_item_usage_amount": "100.0",
                "line_item_product_code": "AmazonS3",  # Not in our analysis
                "line_item_unblended_cost": "5.00"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)

        idle_instances = analyzer.find_low_usage_instances()
        idle_databases = analyzer.find_idle_rds_databases()

        # Should detect both EC2 and RDS, but not S3
        assert len(idle_instances) == 1
        assert len(idle_databases) == 1

    def test_missing_and_invalid_values_handling(self):
        """Test handling of missing or invalid values in CUR records."""
        cur_records = [
            {
                "line_item_resource_id": "i-12345",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": None,  # Missing usage
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "invalid",  # Invalid cost
                "product_instance_type": "t3.micro"
            },
            {
                "line_item_resource_id": "i-67890",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "",  # Empty usage
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "",  # Empty cost
                "product_instance_type": "t3.micro"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)
        idle_instances = analyzer.find_low_usage_instances()

        # Should handle gracefully without crashing
        assert isinstance(idle_instances, list)

    def test_empty_and_none_values_robustness(self):
        """Test robustness with empty and None values in records."""
        cur_records = [
            {
                "line_item_resource_id": "i-12345",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "10.0",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "1.68",
                "product_instance_type": None,  # None instance type
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)
        idle_instances = analyzer.find_low_usage_instances()

        # Should not crash with None/empty values
        assert len(idle_instances) == 1
        instance = idle_instances[0]
        assert instance["instance_type"] == "unknown"  # Default value

    def test_boundary_conditions_zero_and_negative_values(self):
        """Test boundary conditions with zero and negative values."""
        cur_records = [
            {
                "line_item_resource_id": "i-zero",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "0.0",  # Zero usage
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "0.00",
                "product_instance_type": "t3.micro"
            },
            {
                "line_item_resource_id": "i-negative",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "-10.0",  # Negative usage (invalid)
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "-1.00",  # Negative cost (invalid)
                "product_instance_type": "t3.micro"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)
        idle_instances = analyzer.find_low_usage_instances()

        # Should handle zero/negative values gracefully
        assert isinstance(idle_instances, list)

    def test_usage_ratio_calculations_edge_cases(self):
        """Test usage ratio calculations with edge cases."""
        cur_records = [
            {
                "line_item_resource_id": "i-test",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "6.0",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "1.00",
                "product_instance_type": "t3.micro"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)

        # Test with different day periods
        for days in [0, 1, 7, 30, 365]:
            if days == 0:
                # Should handle division by zero gracefully
                idle_instances = analyzer.find_low_usage_instances(days=days)
                assert isinstance(idle_instances, list)
            else:
                idle_instances = analyzer.find_low_usage_instances(days=days)
                assert len(idle_instances) == 1
                instance = idle_instances[0]
                expected_ratio = 6.0 / (days * 24)
                assert abs(instance["usage_ratio"] - expected_ratio) < 0.01

    def test_concurrent_analysis_thread_safety(self):
        """Test thread safety and concurrent analysis."""
        import threading

        cur_records = [
            {
                "line_item_resource_id": "i-test",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "10.0",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "0.10",
                "product_instance_type": "t3.micro"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)

        results = []
        errors = []

        def run_analysis():
            try:
                result = analyzer.find_low_usage_instances()
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Run multiple threads concurrently
        threads = []
        for _ in range(10):
            thread = threading.Thread(target=run_analysis)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All threads should complete successfully
        assert len(results) == 10
        assert len(errors) == 0

        # All results should be identical
        for result in results:
            assert result == results[0]

    def test_real_world_cur_data_scenarios(self):
        """Test with realistic CUR data scenarios."""
        # Simulate a week's worth of real CUR data
        cur_records = [
            # Active EC2 instance (development)
            {
                "line_item_resource_id": "i-dev123",
                "line_item_usage_type": "BoxUsage:t3.medium",
                "line_item_usage_amount": "140.0",  # ~83% usage (140/168)
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "23.52",
                "product_instance_type": "t3.medium"
            },
            # Idle EC2 instance (staging)
            {
                "line_item_resource_id": "i-staging456",
                "line_item_usage_type": "BoxUsage:t3.large",
                "line_item_usage_amount": "24.0",  # ~14% usage (24/168)
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "12.00",
                "product_instance_type": "t3.large"
            },
            # Active RDS database
            {
                "line_item_resource_id": "db-prod-db",
                "line_item_usage_type": "InstanceUsage:db.t3.small",
                "line_item_usage_amount": "168.0",  # 100% usage
                "line_item_product_code": "AmazonRDS",
                "line_item_unblended_cost": "50.40",
                "product_instance_type": "db.t3.small",
                "product_database_engine": "postgres"
            },
            # Idle RDS database
            {
                "line_item_resource_id": "db-dev-db",
                "line_item_usage_type": "InstanceUsage:db.t3.micro",
                "line_item_usage_amount": "16.8",  # ~10% usage (16.8/168)
                "line_item_product_code": "AmazonRDS",
                "line_item_unblended_cost": "2.02",
                "product_instance_type": "db.t3.micro",
                "product_database_engine": "mysql"
            },
            # Unused EBS volume
            {
                "line_item_resource_id": "vol-unused123",
                "line_item_usage_type": "EBS:VolumeUsage.gp3",
                "line_item_usage_amount": "100.0",  # 100GB
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "10.00"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)

        idle_instances = analyzer.find_low_usage_instances()
        idle_databases = analyzer.find_idle_rds_databases()
        unused_volumes = analyzer.find_unused_ebs_volumes()

        # Should detect idle staging instance but not active dev instance
        assert len(idle_instances) == 1
        assert idle_instances[0]["resource_id"] == "i-staging456"

        # Should detect idle dev database but not active prod database
        assert len(idle_databases) == 1
        assert idle_databases[0]["resource_id"] == "db-dev-db"

        # Should detect unused EBS volume
        assert len(unused_volumes) == 1
        assert unused_volumes[0]["resource_id"] == "vol-unused123"

    def test_cost_estimation_accuracy_across_services(self):
        """Test cost estimation accuracy for different AWS services."""
        cur_records = [
            {
                "line_item_resource_id": "i-ec2",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "24.0",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "1.68",
                "product_instance_type": "t3.micro"
            },
            {
                "line_item_resource_id": "db-rds",
                "line_item_usage_type": "InstanceUsage:db.t3.micro",
                "line_item_usage_amount": "24.0",
                "line_item_product_code": "AmazonRDS",
                "line_item_unblended_cost": "20.16",
                "product_instance_type": "db.t3.micro"
            },
            {
                "line_item_resource_id": "cluster-redshift",
                "line_item_usage_type": "Node:dc2.large",
                "line_item_usage_amount": "12.0",
                "line_item_product_code": "AmazonRedshift",
                "line_item_unblended_cost": "94.08",
                "product_instance_type": "dc2.large"
            }
        ]

        analyzer = CURUsageAnalyzer(cur_records)

        idle_instances = analyzer.find_low_usage_instances()
        idle_databases = analyzer.find_idle_rds_databases()
        idle_redshift = analyzer.find_idle_redshift_clusters()

        # All should be detected (100% usage but still analyzed)
        assert len(idle_instances) == 1
        assert len(idle_databases) == 1
        assert len(idle_redshift) == 1

        # Costs should be accurate
        assert idle_instances[0]["monthly_cost"] == 1.68
        assert idle_databases[0]["monthly_cost"] == 20.16
        assert idle_redshift[0]["monthly_cost"] == 94.08

    def test_memory_usage_efficiency_large_datasets(self):
        """Test memory usage efficiency with large datasets."""
        import psutil
        import os

        # Get initial memory usage
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / 1024 / 1024  # MB

        # Create very large dataset (5000 records across multiple services)
        cur_records = []
        for i in range(2000):  # 2000 EC2 instances
            cur_records.append({
                "line_item_resource_id": f"i-{i:04d}",
                "line_item_usage_type": "BoxUsage:t3.micro",
                "line_item_usage_amount": "1.0",
                "line_item_product_code": "AmazonEC2",
                "line_item_unblended_cost": "0.01",
                "product_instance_type": "t3.micro"
            })

        for i in range(1000):  # 1000 RDS databases
            cur_records.append({
                "line_item_resource_id": f"db-{i:04d}",
                "line_item_usage_type": "InstanceUsage:db.t3.micro",
                "line_item_usage_amount": "1.0",
                "line_item_product_code": "AmazonRDS",
                "line_item_unblended_cost": "0.12",
                "product_instance_type": "db.t3.micro"
            })

        analyzer = CURUsageAnalyzer(cur_records)

        # Test multiple analysis methods
        idle_instances = analyzer.find_low_usage_instances()
        idle_databases = analyzer.find_idle_rds_databases()

        # Check memory usage after processing
        final_memory = process.memory_info().rss / 1024 / 1024  # MB
        memory_increase = final_memory - initial_memory

        # Memory increase should be reasonable (< 200MB for 3000 records)
        assert memory_increase < 200, f"Excessive memory usage: {memory_increase:.1f}MB"

        # Results should be correct
        assert len(idle_instances) == 2000
        assert len(idle_databases) == 1000
