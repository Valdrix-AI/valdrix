"""
Settings API Module

Aggregates all settings sub-routers into a single router.

Structure:
- notifications.py - Slack and alert settings
- carbon.py - Carbon budget settings
- llm.py - LLM provider and budget settings
- activeops.py - Autonomous remediation settings
- safety.py - Circuit breaker and safety controls
"""

from fastapi import APIRouter

from .notifications import router as notifications_router
from .carbon import router as carbon_router
from .llm import router as llm_router
from .activeops import router as activeops_router
from .safety import router as safety_router

# Main settings router - aggregates all sub-routers
router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])

# Include all sub-routers
router.include_router(notifications_router)
router.include_router(carbon_router)
router.include_router(llm_router)
router.include_router(activeops_router)
router.include_router(safety_router)
