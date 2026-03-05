from .service import ZombieService, OptimizationService
from .factory import ZombieDetectorFactory
from .remediation import RemediationService
from .registry import registry as plugins
from app.modules.optimization.adapters.aws.detector import (
    AWSZombieDetector as ZombieDetector,
)

__all__ = [
    "ZombieService",
    "OptimizationService",
    "ZombieDetector",
    "ZombieDetectorFactory",
    "RemediationService",
    "plugins",
]
