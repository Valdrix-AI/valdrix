"""
Zombies Services Module

Provides zombie resource detection and remediation:
- ZombieDetector: Scans for unused AWS resources
- RemediationService: Manages approval workflow
"""

from .detector import ZombieDetector
from .remediation_service import RemediationService
from .service import ZombieService

__all__ = ["ZombieDetector", "RemediationService", "ZombieService"]
