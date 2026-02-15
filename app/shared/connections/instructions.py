from app.shared.core.config import get_settings


class ConnectionInstructionService:
    """
    Generates setup instructions and CLI snippets for cloud connections.
    Encapsulates string building logic to keep API routes clean.
    """

    @staticmethod
    def get_azure_setup_snippet(tenant_id: str) -> dict[str, str]:
        """Generate Azure Workload Identity setup instructions."""
        settings = get_settings()
        issuer = settings.API_URL.rstrip("/")

        snippet = (
            f"# 1. Create App Registration in Azure AD\n"
            f"# 2. Create a Federated Credential with these details:\n"
            f"Issuer: {issuer} (IMPORTANT: Must be publicly reachable by Azure)\n"
            f"Subject: tenant:{tenant_id}\n"
            f"Audience: api://AzureADTokenExchange\n"
            f"\n# Or run this via Azure CLI:\n"
            f"az ad app federated-credential create --id <YOUR_CLIENT_ID> "
            f'--parameters \'{{"name":"ValdrixTrust","issuer":"{issuer}","subject":"tenant:{tenant_id}","audiences":["api://AzureADTokenExchange"]}}\''
        )

        return {
            "issuer": issuer,
            "subject": f"tenant:{tenant_id}",
            "audience": "api://AzureADTokenExchange",
            "snippet": snippet,
        }

    @staticmethod
    def get_gcp_setup_snippet(tenant_id: str) -> dict[str, str]:
        """Generate GCP Identity Federation setup instructions."""
        settings = get_settings()
        issuer = settings.API_URL.rstrip("/")

        snippet = (
            f"# Run this to create an Identity Pool and Provider for Valdrix\n"
            f"# IMPORTANT: Your Valdrix instance must be reachable at {issuer}\n"
            f'gcloud iam workload-identity-pools create "valdrix-pool" --location="global" --display-name="Valdrix Pool"\n'
            f'gcloud iam workload-identity-pools providers create-oidc "valdrix-provider" '
            f'--location="global" --workload-identity-pool="valdrix-pool" '
            f'--issuer-uri="{issuer}" '
            f'--attribute-mapping="google.subject=assertion.sub,attribute.tenant_id=assertion.tenant_id"'
        )

        return {"issuer": issuer, "subject": f"tenant:{tenant_id}", "snippet": snippet}

    @staticmethod
    def get_saas_setup_snippet(tenant_id: str) -> dict[str, object]:
        """Generate SaaS Cloud+ onboarding instructions."""
        settings = get_settings()
        api_url = settings.API_URL.rstrip("/")
        saas_catalog = ConnectionInstructionService.get_saas_connector_catalog()
        stripe_native_payload = (
            "{\n"
            '  "name": "Stripe Billing",\n'
            '  "vendor": "stripe",\n'
            '  "auth_method": "api_key",\n'
            '  "api_key": "<stripe_api_key>",\n'
            '  "connector_config": {},\n'
            '  "spend_feed": []\n'
            "}"
        )
        salesforce_native_payload = (
            "{\n"
            '  "name": "Salesforce Contracts",\n'
            '  "vendor": "salesforce",\n'
            '  "auth_method": "oauth",\n'
            '  "api_key": "<access_token>",\n'
            '  "connector_config": {"instance_url": "https://your-org.my.salesforce.com"},\n'
            '  "spend_feed": []\n'
            "}"
        )
        sample_payload = (
            "[\n"
            "  {\n"
            '    "timestamp": "2026-02-01T00:00:00Z",\n'
            '    "vendor": "example_saas",\n'
            '    "service": "Example Workspace",\n'
            '    "usage_type": "subscription",\n'
            '    "cost_usd": 249.99,\n'
            '    "currency": "USD",\n'
            '    "tags": {"team": "growth", "environment": "prod"}\n'
            "  }\n"
            "]"
        )
        snippet = (
            "# SaaS Cloud+ onboarding options\n"
            "# 1) Native pull mode (recommended): Stripe, Salesforce\n"
            "# 2) Manual/CSV feed mode for quick onboarding\n"
            "#\n"
            "# Tenant-scoped subject for API/OIDC trust:\n"
            f"tenant:{tenant_id}\n"
            "#\n"
            "# Native Stripe connector payload:\n"
            f"{stripe_native_payload}\n"
            "#\n"
            "# Native Salesforce connector payload:\n"
            f"{salesforce_native_payload}\n"
            "#\n"
            "# Example SaaS spend feed payload (JSON array):\n"
            f"{sample_payload}\n"
            "#\n"
            "# Create connector via API:\n"
            f"POST {api_url}/settings/connections/saas\n"
        )
        return {
            "subject": f"tenant:{tenant_id}",
            "snippet": snippet,
            "sample_feed": sample_payload,
            "supported_vendors": "stripe,salesforce",
            "native_connectors": saas_catalog,
            "manual_feed_schema": {
                "required_fields": ["timestamp|date", "cost_usd|amount_usd"],
                "optional_fields": ["service", "usage_type", "currency", "tags"],
            },
        }

    @staticmethod
    def get_license_setup_snippet(tenant_id: str) -> dict[str, object]:
        """Generate License/ITAM Cloud+ onboarding instructions."""
        settings = get_settings()
        api_url = settings.API_URL.rstrip("/")
        license_catalog = ConnectionInstructionService.get_license_connector_catalog()
        native_payload = (
            "{\n"
            '  "name": "Microsoft 365 License Sync",\n'
            '  "vendor": "microsoft_365",\n'
            '  "auth_method": "oauth",\n'
            '  "api_key": "<graph_access_token>",\n'
            '  "connector_config": {\n'
            '    "default_seat_price_usd": 36,\n'
            '    "sku_prices": {"ENTERPRISEPREMIUM": 38, "SPE_E5": 57}\n'
            "  },\n"
            '  "license_feed": []\n'
            "}"
        )
        sample_payload = (
            "[\n"
            "  {\n"
            '    "timestamp": "2026-02-01T00:00:00Z",\n'
            '    "vendor": "example_vendor",\n'
            '    "service": "Enterprise Seat License",\n'
            '    "usage_type": "seat_license",\n'
            '    "cost_usd": 1200.00,\n'
            '    "currency": "USD",\n'
            '    "purchased_seats": 250,\n'
            '    "assigned_seats": 198,\n'
            '    "tags": {"cost_center": "it", "owner": "platform"}\n'
            "  }\n"
            "]"
        )
        snippet = (
            "# License / ITAM Cloud+ onboarding options\n"
            "# 1) Native pull mode (recommended): Microsoft 365 via Microsoft Graph\n"
            "# 2) Manual/CSV feed mode for contract exports\n"
            "#\n"
            "# Tenant-scoped subject for API/OIDC trust:\n"
            f"tenant:{tenant_id}\n"
            "#\n"
            "# Native Microsoft 365 connector payload:\n"
            f"{native_payload}\n"
            "#\n"
            "# Example license feed payload (JSON array):\n"
            f"{sample_payload}\n"
            "#\n"
            "# Create connector via API:\n"
            f"POST {api_url}/settings/connections/license\n"
        )
        return {
            "subject": f"tenant:{tenant_id}",
            "snippet": snippet,
            "sample_feed": sample_payload,
            "supported_vendors": "microsoft_365",
            "native_connectors": license_catalog,
            "manual_feed_schema": {
                "required_fields": ["timestamp|date", "cost_usd|amount_usd"],
                "optional_fields": [
                    "service",
                    "usage_type",
                    "currency",
                    "purchased_seats",
                    "assigned_seats",
                    "tags",
                ],
            },
        }

    @staticmethod
    def get_platform_setup_snippet(tenant_id: str) -> dict[str, object]:
        """Generate internal platform Cloud+ onboarding instructions (feed + native connectors)."""
        settings = get_settings()
        api_url = settings.API_URL.rstrip("/")
        ledger_payload = (
            "{\n"
            '  "name": "Platform Ledger API",\n'
            '  "vendor": "ledger_http",\n'
            '  "auth_method": "api_key",\n'
            '  "api_key": "<ledger_api_key_or_bearer_token>",\n'
            '  "connector_config": {\n'
            '    "base_url": "https://ledger.company.com",\n'
            '    "costs_path": "/api/v1/finops/costs"\n'
            "  },\n"
            '  "spend_feed": []\n'
            "}"
        )
        datadog_payload = (
            "{\n"
            '  "name": "Datadog Platform Usage (priced)",\n'
            '  "vendor": "datadog",\n'
            '  "auth_method": "api_key",\n'
            '  "api_key": "<datadog_api_key>",\n'
            '  "api_secret": "<datadog_application_key>",\n'
            '  "connector_config": {\n'
            '    "site": "datadoghq.com",\n'
            '    "unit_prices_usd": {"hosts": 2.0, "logs_indexed_gb": 0.5}\n'
            "  },\n"
            '  "spend_feed": []\n'
            "}"
        )
        newrelic_payload = (
            "{\n"
            '  "name": "New Relic Platform Usage (priced)",\n'
            '  "vendor": "newrelic",\n'
            '  "auth_method": "api_key",\n'
            '  "api_key": "<newrelic_user_api_key>",\n'
            '  "connector_config": {\n'
            '    "account_id": 123456,\n'
            "    \"nrql_template\": \"FROM NrMTDConsumption SELECT latest(gigabytes) AS gigabytes SINCE '{start}' UNTIL '{end}'\",\n"
            '    "unit_prices_usd": {"gigabytes": 0.5}\n'
            "  },\n"
            '  "spend_feed": []\n'
            "}"
        )
        sample_payload = (
            "[\n"
            "  {\n"
            '    "timestamp": "2026-02-01T00:00:00Z",\n'
            '    "service": "Shared Kubernetes Cluster",\n'
            '    "usage_type": "shared_service",\n'
            '    "cost_usd": 842.13,\n'
            '    "currency": "USD",\n'
            '    "region": "global",\n'
            '    "tags": {"team": "platform", "environment": "prod", "owner": "platform"}\n'
            "  }\n"
            "]"
        )
        snippet = (
            "# Internal Platform Cloud+ onboarding\n"
            "#\n"
            "# Supported modes:\n"
            "# 1) Native pull mode (recommended): ledger_http (your internal chargeback ledger / CMDB API)\n"
            "# 2) Vendor-native priced usage (optional): Datadog, New Relic\n"
            "# 2) Manual/CSV feed mode for quick onboarding\n"
            "#\n"
            "# Use this for shared platform spend not captured in cloud provider bills:\n"
            "# - shared Kubernetes/platform tooling\n"
            "# - shared services/platform ops costs\n"
            "# - internal chargeback ledgers\n"
            "#\n"
            "# Tenant-scoped subject for API/OIDC trust:\n"
            f"tenant:{tenant_id}\n"
            "#\n"
            "# Native ledger_http connector payload:\n"
            f"{ledger_payload}\n"
            "#\n"
            "# Datadog native payload (requires unit_prices_usd to convert usage -> cost):\n"
            f"{datadog_payload}\n"
            "#\n"
            "# New Relic native payload (requires NRQL template + unit_prices_usd):\n"
            f"{newrelic_payload}\n"
            "#\n"
            "# Example platform spend feed payload (JSON array):\n"
            f"{sample_payload}\n"
            "#\n"
            "# Create connector via API:\n"
            f"POST {api_url}/settings/connections/platform\n"
        )
        return {
            "subject": f"tenant:{tenant_id}",
            "snippet": snippet,
            "sample_feed": sample_payload,
            "supported_vendors": "ledger_http, datadog, newrelic (native) or any (manual/csv)",
            "native_connectors": [
                {
                    "vendor": "ledger_http",
                    "display_name": "Ledger HTTP (Platform)",
                    "recommended_auth_method": "api_key",
                    "supported_auth_methods": ["api_key", "manual", "csv"],
                    "required_connector_config_fields": ["base_url"],
                    "optional_connector_config_fields": [
                        "costs_path",
                        "start_param",
                        "end_param",
                        "api_key_header",
                    ],
                },
                {
                    "vendor": "datadog",
                    "display_name": "Datadog (Platform)",
                    "recommended_auth_method": "api_key",
                    "supported_auth_methods": ["api_key", "manual", "csv"],
                    "required_connector_config_fields": ["unit_prices_usd"],
                    "optional_connector_config_fields": [
                        "site",
                        "api_base_url",
                        "strict_pricing",
                    ],
                },
                {
                    "vendor": "newrelic",
                    "display_name": "New Relic (Platform)",
                    "recommended_auth_method": "api_key",
                    "supported_auth_methods": ["api_key", "manual", "csv"],
                    "required_connector_config_fields": [
                        "account_id",
                        "nrql_template",
                        "unit_prices_usd",
                    ],
                    "optional_connector_config_fields": [
                        "api_base_url",
                        "strict_pricing",
                    ],
                },
            ],
            "manual_feed_schema": {
                "required_fields": ["timestamp|date", "cost_usd|amount_usd"],
                "optional_fields": [
                    "service",
                    "usage_type",
                    "currency",
                    "region|location",
                    "tags",
                ],
            },
        }

    @staticmethod
    def get_hybrid_setup_snippet(tenant_id: str) -> dict[str, object]:
        """Generate private/hybrid infra Cloud+ onboarding instructions (feed + native connectors)."""
        settings = get_settings()
        api_url = settings.API_URL.rstrip("/")
        ledger_payload = (
            "{\n"
            '  "name": "Hybrid Ledger API",\n'
            '  "vendor": "ledger_http",\n'
            '  "auth_method": "api_key",\n'
            '  "api_key": "<ledger_api_key_or_bearer_token>",\n'
            '  "connector_config": {\n'
            '    "base_url": "https://ledger.company.com",\n'
            '    "costs_path": "/api/v1/finops/costs"\n'
            "  },\n"
            '  "spend_feed": []\n'
            "}"
        )
        cloudkitty_payload = (
            "{\n"
            '  "name": "OpenStack CloudKitty Rated Spend",\n'
            '  "vendor": "cloudkitty",\n'
            '  "auth_method": "api_key",\n'
            '  "api_key": "<application_credential_id>",\n'
            '  "api_secret": "<application_credential_secret>",\n'
            '  "connector_config": {\n'
            '    "auth_url": "https://keystone.company.com",\n'
            '    "cloudkitty_base_url": "https://cloudkitty.company.com",\n'
            '    "currency": "USD",\n'
            '    "groupby": "month"\n'
            "  },\n"
            '  "spend_feed": []\n'
            "}"
        )
        vmware_payload = (
            "{\n"
            '  "name": "VMware vCenter Inventory Estimate",\n'
            '  "vendor": "vmware",\n'
            '  "auth_method": "api_key",\n'
            '  "api_key": "<vcenter_username>",\n'
            '  "api_secret": "<vcenter_password>",\n'
            '  "connector_config": {\n'
            '    "base_url": "https://vcenter.company.com",\n'
            '    "cpu_hour_usd": 0.1,\n'
            '    "ram_gb_hour_usd": 0.01,\n'
            '    "verify_ssl": true\n'
            "  },\n"
            '  "spend_feed": []\n'
            "}"
        )
        sample_payload = (
            "[\n"
            "  {\n"
            '    "timestamp": "2026-02-01T00:00:00Z",\n'
            '    "service": "Datacenter Core",\n'
            '    "usage_type": "infrastructure",\n'
            '    "cost_usd": 5120.00,\n'
            '    "currency": "USD",\n'
            '    "location": "dc-1",\n'
            '    "tags": {"cost_center": "infra", "owner": "platform"}\n'
            "  }\n"
            "]"
        )
        snippet = (
            "# Private/Hybrid Infrastructure Cloud+ onboarding\n"
            "#\n"
            "# Supported modes:\n"
            "# 1) Native pull mode (recommended): ledger_http (your internal ledger / CMDB API)\n"
            "# 2) Vendor-native pulls (optional): OpenStack CloudKitty, VMware vCenter (estimated)\n"
            "# 2) Manual/CSV feed mode for invoice exports\n"
            "#\n"
            "# Use this for on-prem/colo/private-cloud spend you want in the same\n"
            "# allocation + reconciliation + reporting workflow as cloud providers.\n"
            "#\n"
            "# Tenant-scoped subject for API/OIDC trust:\n"
            f"tenant:{tenant_id}\n"
            "#\n"
            "# Native ledger_http connector payload:\n"
            f"{ledger_payload}\n"
            "#\n"
            "# OpenStack CloudKitty payload:\n"
            f"{cloudkitty_payload}\n"
            "#\n"
            "# VMware vCenter payload (estimated pricing):\n"
            f"{vmware_payload}\n"
            "#\n"
            "# Example hybrid spend feed payload (JSON array):\n"
            f"{sample_payload}\n"
            "#\n"
            "# Create connector via API:\n"
            f"POST {api_url}/settings/connections/hybrid\n"
        )
        return {
            "subject": f"tenant:{tenant_id}",
            "snippet": snippet,
            "sample_feed": sample_payload,
            "supported_vendors": "ledger_http, cloudkitty, vmware (native) or any (manual/csv)",
            "native_connectors": [
                {
                    "vendor": "ledger_http",
                    "display_name": "Ledger HTTP (Hybrid)",
                    "recommended_auth_method": "api_key",
                    "supported_auth_methods": ["api_key", "manual", "csv"],
                    "required_connector_config_fields": ["base_url"],
                    "optional_connector_config_fields": [
                        "costs_path",
                        "start_param",
                        "end_param",
                        "api_key_header",
                    ],
                },
                {
                    "vendor": "cloudkitty",
                    "display_name": "OpenStack CloudKitty (Hybrid)",
                    "recommended_auth_method": "api_key",
                    "supported_auth_methods": ["api_key", "manual", "csv"],
                    "required_connector_config_fields": [
                        "auth_url",
                        "cloudkitty_base_url",
                    ],
                    "optional_connector_config_fields": [
                        "currency",
                        "groupby",
                        "verify_ssl",
                    ],
                },
                {
                    "vendor": "vmware",
                    "display_name": "VMware vCenter (Hybrid, estimated)",
                    "recommended_auth_method": "api_key",
                    "supported_auth_methods": ["api_key", "manual", "csv"],
                    "required_connector_config_fields": [
                        "base_url",
                        "cpu_hour_usd",
                        "ram_gb_hour_usd",
                    ],
                    "optional_connector_config_fields": [
                        "location",
                        "include_powered_off",
                        "verify_ssl",
                    ],
                },
            ],
            "manual_feed_schema": {
                "required_fields": ["timestamp|date", "cost_usd|amount_usd"],
                "optional_fields": [
                    "service",
                    "usage_type",
                    "currency",
                    "region|location",
                    "tags",
                ],
            },
        }

    @staticmethod
    def get_saas_connector_catalog() -> list[dict[str, object]]:
        return [
            {
                "vendor": "stripe",
                "display_name": "Stripe",
                "recommended_auth_method": "api_key",
                "supported_auth_methods": ["api_key", "manual", "csv"],
                "required_connector_config_fields": [],
            },
            {
                "vendor": "salesforce",
                "display_name": "Salesforce",
                "recommended_auth_method": "oauth",
                "supported_auth_methods": ["oauth", "api_key", "manual", "csv"],
                "required_connector_config_fields": ["instance_url"],
            },
        ]

    @staticmethod
    def get_license_connector_catalog() -> list[dict[str, object]]:
        return [
            {
                "vendor": "microsoft_365",
                "display_name": "Microsoft 365",
                "recommended_auth_method": "oauth",
                "supported_auth_methods": ["oauth", "api_key", "manual", "csv"],
                "required_connector_config_fields": [],
                "optional_connector_config_fields": [
                    "default_seat_price_usd",
                    "sku_prices",
                    "currency",
                ],
            }
        ]
