"""
Unified connections API router.

This module only composes sub-routers. Business logic lives in dedicated modules:
- connections_helpers.py
- connections_setup_aws_discovery.py
- connections_azure_gcp.py
- connections_cloud_plus.py
"""

from fastapi import APIRouter

from app.modules.governance.api.v1.settings.connections_azure_gcp import (
    router as azure_gcp_router,
)
from app.modules.governance.api.v1.settings.connections_cloud_plus import (
    router as cloud_plus_router,
)
from app.modules.governance.api.v1.settings.connections_setup_aws_discovery import (
    router as setup_aws_discovery_router,
)
router = APIRouter(tags=["connections"])
router.include_router(setup_aws_discovery_router)
router.include_router(azure_gcp_router)
router.include_router(cloud_plus_router)
