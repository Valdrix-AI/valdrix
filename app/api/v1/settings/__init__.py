"""
Settings API Module - Modular Structure

This package provides modular settings APIs for:
- notifications.py - Slack and alert preferences
- carbon.py - Carbon budget settings
- llm.py - LLM provider and budget settings
- activeops.py - Autonomous remediation settings
"""

from fastapi import APIRouter

from .notifications import router as notifications_router
from .carbon import router as carbon_router
from .llm import router as llm_router
from .activeops import router as activeops_router

# Create main settings router
router = APIRouter(prefix="/settings", tags=["Settings"])

# Include sub-routers
router.include_router(notifications_router)
router.include_router(carbon_router)
router.include_router(llm_router)
router.include_router(activeops_router)

__all__ = ["router"]
