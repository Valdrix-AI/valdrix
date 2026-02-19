"""
Graviton Migration Analyzer

Identifies EC2 instances that could benefit from migrating to
AWS Graviton (ARM-based) processors for up to 60% energy savings.
"""

from typing import Any, Dict, Optional
import structlog

from app.modules.reporting.domain.arm_analyzer import ArmMigrationAnalyzer

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
    "older .NET framework workloads (requires .NET Core/5+)",
    "kernel-level drivers/software (requires ARM port)",
    "proprietary third-party agents without ARM support",
    "SIMD-accelerated code (AVX/AVX2 - requires Neon port)",
    "software with hard-coded x86 assembly",
    "older .NET Framework (< 5) apps",
]


class GravitonAnalyzer(ArmMigrationAnalyzer):
    """
    Analyzes EC2 instances for Graviton migration opportunities.
    """

    def is_arm(self, instance_type: str) -> bool:
        return any(g in instance_type.lower() for g in ["g.", "7g.", "6g.", "4g."])

    def get_equivalent(self, instance_type: str) -> Optional[tuple[str, int]]:
        return GRAVITON_EQUIVALENTS.get(instance_type)

    def get_instance_type_from_resource(self, resource: Dict[str, Any]) -> Optional[str]:
        # For AWS, MultiTenantAWSAdapter returns the instance type in the 'type' field
        return resource.get("type")

    async def analyze_instances(self) -> Dict[str, Any]:
        """
        Legacy compatibility method for original GravitonAnalyzer interface.
        """
        return await self.analyze()

    async def analyze(self) -> Dict[str, Any]:
        """
        Scan EC2 instances and identify Graviton migration candidates.
        """
        base_result = await super().analyze()
        
        # Enrich with AWS-specific metadata
        base_result.update({
            "already_graviton": base_result.get("arm_instances", 0),
            "potential_energy_reduction_percent": (
                sum(c["savings_percent"] for c in base_result["candidates"])
                / len(base_result["candidates"])
                if base_result["candidates"]
                else 0
            ),
            "compatible_workloads": COMPATIBLE_WORKLOADS,
            "requires_validation": REQUIRES_VALIDATION,
        })

        logger.info(
            "graviton_analysis_complete",
            total=base_result.get("total_instances"),
            candidates=base_result.get("migration_candidates"),
        )

        return base_result

    def get_migration_guide(self, instance_type: str) -> Dict[str, Any]:
        """
        Get detailed migration guide for a specific instance type.
        """
        if instance_type not in GRAVITON_EQUIVALENTS:
            return {"error": f"No Graviton equivalent found for {instance_type}"}

        graviton_type, savings = GRAVITON_EQUIVALENTS[instance_type]

        return {
            "current_type": instance_type,
            "target_type": graviton_type,
            "estimated_savings": {
                "energy_percent": savings,
                "cost_percent": savings - 5,
                "carbon_percent": savings,
            },
            "steps": [
                "1. Review application compatibility",
                "2. Create an AMI backup",
                "3. Launch a test instance with Graviton",
                "4. Deploy and test application",
                "5. Run performance benchmarks",
                "6. Migrate production workload",
            ],
            "compatibility_notes": [
                "Most Docker containers work",
                "Python, Node.js, Java, Go work natively",
                "Use multi-arch Docker images",
            ],
        }
