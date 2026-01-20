"""
Graviton Migration Analyzer

Identifies EC2 instances that could benefit from migrating to
AWS Graviton (ARM-based) processors for up to 60% energy savings.

Valdrix Innovation: Helps customers reduce both costs and
carbon footprint by recommending Graviton migrations.

References:
- AWS Graviton processors use up to 60% less energy for same performance
- AWS Sustainability Pillar recommends Graviton for carbon reduction
"""

from typing import Dict, Any, Optional
import structlog
import aioboto3

logger = structlog.get_logger()


# Mapping of x86 instance types to Graviton equivalents
# Format: x86_type -> (graviton_type, estimated_savings_percent)
GRAVITON_EQUIVALENTS = {
    # General Purpose
    "m5.large": ("m7g.large", 40),
    "m5.xlarge": ("m7g.xlarge", 40),
    "m5.2xlarge": ("m7g.2xlarge", 40),
    "m5.4xlarge": ("m7g.4xlarge", 40),
    "m6i.large": ("m7g.large", 35),
    "m6i.xlarge": ("m7g.xlarge", 35),
    "m6i.2xlarge": ("m7g.2xlarge", 35),

    # Compute Optimized
    "c5.large": ("c7g.large", 40),
    "c5.xlarge": ("c7g.xlarge", 40),
    "c5.2xlarge": ("c7g.2xlarge", 40),
    "c6i.large": ("c7g.large", 35),
    "c6i.xlarge": ("c7g.xlarge", 35),

    # Memory Optimized
    "r5.large": ("r7g.large", 40),
    "r5.xlarge": ("r7g.xlarge", 40),
    "r5.2xlarge": ("r7g.2xlarge", 40),
    "r6i.large": ("r7g.large", 35),
    "r6i.xlarge": ("r7g.xlarge", 35),

    # Burstable
    "t3.micro": ("t4g.micro", 40),
    "t3.small": ("t4g.small", 40),
    "t3.medium": ("t4g.medium", 40),
    "t3.large": ("t4g.large", 40),
    "t3.xlarge": ("t4g.xlarge", 40),
}

# Workloads that are typically compatible with Graviton
COMPATIBLE_WORKLOADS = [
    "web servers (nginx, apache)",
    "containerized microservices (docker, k8s)",
    "caching layers (redis, memcached)",
    "open-source databases (mysql, postgres, mariadb)",
    "big data processing (hadoop, spark)",
    "media encoding (ffmpeg)",
    "eda/hpc workloads",
    "JVM-based apps (Java, Kotlin, Scala)",
    "interpreted languages (Python, Node.js, Ruby, PHP)",
    ".NET 5+ or .NET Core apps",
]

# Workloads that may require validation
REQUIRES_VALIDATION = [
    "Windows workloads (not supported by Graviton)",
    "x86-specific compiled binaries (requires re-compilation)",
    "legacy dotNET framework (requires .NET Core/5+)",
    "kernel-level drivers/software (requires ARM port)",
    "proprietary third-party agents without ARM support",
    "SIMD-accelerated code (AVX/AVX2 - requires Neon port)",
    "software with hard-coded x86 assembly",
    "older .NET Framework (< 5) apps",
]


class GravitonAnalyzer:
    """
    Analyzes EC2 instances for Graviton migration opportunities.

    Valdrix Innovation: Combines cost savings with carbon reduction
    by recommending energy-efficient ARM-based instances.
    """

    def __init__(self, credentials: Optional[Dict] = None, region: str = "us-east-1"):
        """
        Initialize the analyzer.

        Args:
            credentials: Optional STS credentials dict for multi-tenant access
            region: AWS region to scan
        """
        self.credentials = credentials
        self.region = region
        self.session = aioboto3.Session()

    def _get_ec2_client_context(self):
        """Get EC2 client context manager with optional STS credentials."""
        if self.credentials:
            return self.session.client(
                "ec2",
                region_name=self.region,
                aws_access_key_id=self.credentials["AccessKeyId"],
                aws_secret_access_key=self.credentials["SecretAccessKey"],
                aws_session_token=self.credentials["SessionToken"],
            )
        return self.session.client("ec2", region_name=self.region)

    async def analyze_instances(self) -> Dict[str, Any]:
        """
        Scan EC2 instances and identify Graviton migration candidates.

        Returns:
            Dict containing migration opportunities and estimated savings
        """
        try:
            async with self._get_ec2_client_context() as ec2:
                # Get all running instances with pagination
                candidates = []
                total_instances = 0
                graviton_instances = 0

                paginator = ec2.get_paginator("describe_instances")

                async for response in paginator.paginate(
                    Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
                ):
                    for reservation in response.get("Reservations", []):
                        for instance in reservation.get("Instances", []):
                            total_instances += 1
                            instance_type = instance.get("InstanceType", "")
                            instance_id = instance.get("InstanceId", "")

                            # Check if already on Graviton
                            if any(g in instance_type for g in ["g.", "7g.", "6g.", "4g."]):
                                graviton_instances += 1
                                continue

                            # Check if migration candidate exists
                            if instance_type in GRAVITON_EQUIVALENTS:
                                graviton_type, savings_percent = GRAVITON_EQUIVALENTS[instance_type]

                                # Get instance name from tags
                                name = ""
                                for tag in instance.get("Tags", []):
                                    if tag.get("Key") == "Name":
                                        name = tag.get("Value", "")
                                        break

                                candidates.append({
                                    "instance_id": instance_id,
                                    "name": name,
                                    "current_type": instance_type,
                                    "recommended_type": graviton_type,
                                    "energy_savings_percent": savings_percent,
                                    "carbon_reduction_percent": savings_percent,  # ~1:1 with energy
                                    "migration_complexity": "low",  # Most are compatible
                                })

            # Calculate summary
            result = {
                "total_instances": total_instances,
                "already_graviton": graviton_instances,
                "migration_candidates": len(candidates),
                "candidates": candidates,
                "potential_energy_reduction_percent": (
                    sum(c["energy_savings_percent"] for c in candidates) / len(candidates)
                    if candidates else 0
                ),
                "compatible_workloads": COMPATIBLE_WORKLOADS,
                "requires_validation": REQUIRES_VALIDATION,
            }

            logger.info(
                "graviton_analysis_complete",
                total=total_instances,
                candidates=len(candidates),
                already_graviton=graviton_instances,
            )

            return result

        except Exception as e:
            logger.error("graviton_analysis_failed", error=str(e))
            return {
                "error": str(e),
                "total_instances": 0,
                "migration_candidates": 0,
                "candidates": [],
            }

    def get_migration_guide(self, instance_type: str) -> Dict[str, Any]:
        """
        Get detailed migration guide for a specific instance type.

        Returns step-by-step instructions and compatibility notes.
        """
        if instance_type not in GRAVITON_EQUIVALENTS:
            return {"error": f"No Graviton equivalent found for {instance_type}"}

        graviton_type, savings = GRAVITON_EQUIVALENTS[instance_type]

        return {
            "current_type": instance_type,
            "target_type": graviton_type,
            "estimated_savings": {
                "energy_percent": savings,
                "cost_percent": savings - 5,  # Graviton is also cheaper
                "carbon_percent": savings,
            },
            "steps": [
                "1. Review application compatibility (most Linux workloads work)",
                "2. Create an AMI backup of your current instance",
                "3. Launch a test instance with Graviton type",
                "4. Deploy and test your application",
                "5. Run performance benchmarks",
                "6. If tests pass, migrate production workload",
            ],
            "compatibility_notes": [
                "Most Docker containers work without changes",
                "Python, Node.js, Java, Go work natively",
                "Use multi-arch Docker images when available",
                "Recompile C/C++ code for ARM64 if needed",
            ],
        }
