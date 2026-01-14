"""
Zombies Services Module

Provides zombie resource detection and remediation:
- ZombieDetector: Scans for unused AWS resources
- RemediationService: Manages approval workflow
"""

from .detector import ZombieDetector, RemediationService

__all__ = ["ZombieDetector", "RemediationService"]
