"""
Scheduler Service - Package Entry Point

This file maintains backward compatibility by proxying calls to the
refactored SchedulerOrchestrator in the .orchestrator sub-module.
"""

from .orchestrator import SchedulerOrchestrator, SchedulerService
from .cohorts import TenantCohort, get_tenant_cohort

__all__ = [
    "SchedulerService",
    "SchedulerOrchestrator",
    "TenantCohort",
    "get_tenant_cohort",
]
