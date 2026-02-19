"""
Model package initializer.

This module exists to make sure SQLAlchemy's registry is populated in any runtime
that uses the ORM outside of `app/main.py` (scripts, workers, one-off jobs).
"""

# Import side-effects: register ORM mappings.
from app.models import (  # noqa: F401
    anomaly_marker,
    attribution,
    aws_connection,
    azure_connection,
    background_job,
    carbon_factors,
    carbon_settings,
    cloud,
    cost_audit,
    discovery_candidate,
    discovered_account,
    gcp_connection,
    hybrid_connection,
    invoice,
    license_connection,
    llm,
    notification_settings,
    optimization,
    platform_connection,
    pricing,
    realized_savings,
    remediation,
    remediation_settings,
    saas_connection,
    scim_group,
    security,
    sso_domain_mapping,
    tenant,
    tenant_identity_settings,
    unit_economics_settings,
)
