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
        issuer = settings.API_URL.rstrip('/')
        
        snippet = (
            f"# 1. Create App Registration in Azure AD\n"
            f"# 2. Create a Federated Credential with these details:\n"
            f"Issuer: {issuer} (IMPORTANT: Must be publicly reachable by Azure)\n"
            f"Subject: tenant:{tenant_id}\n"
            f"Audience: api://AzureADTokenExchange\n"
            f"\n# Or run this via Azure CLI:\n"
            f"az ad app federated-credential create --id <YOUR_CLIENT_ID> "
            f"--parameters '{{\"name\":\"ValdrixTrust\",\"issuer\":\"{issuer}\",\"subject\":\"tenant:{tenant_id}\",\"audiences\":[\"api://AzureADTokenExchange\"]}}'"
        )
        
        return {
            "issuer": issuer,
            "subject": f"tenant:{tenant_id}",
            "audience": "api://AzureADTokenExchange",
            "snippet": snippet
        }

    @staticmethod
    def get_gcp_setup_snippet(tenant_id: str) -> dict[str, str]:
        """Generate GCP Identity Federation setup instructions."""
        settings = get_settings()
        issuer = settings.API_URL.rstrip('/')
        
        snippet = (
            f"# Run this to create an Identity Pool and Provider for Valdrix\n"
            f"# IMPORTANT: Your Valdrix instance must be reachable at {issuer}\n"
            f"gcloud iam workload-identity-pools create \"valdrix-pool\" --location=\"global\" --display-name=\"Valdrix Pool\"\n"
            f"gcloud iam workload-identity-pools providers create-oidc \"valdrix-provider\" "
            f"--location=\"global\" --workload-identity-pool=\"valdrix-pool\" "
            f"--issuer-uri=\"{issuer}\" "
            f"--attribute-mapping=\"google.subject=assertion.sub,attribute.tenant_id=assertion.tenant_id\""
        )
        
        return {
            "issuer": issuer,
            "subject": f"tenant:{tenant_id}",
            "snippet": snippet
        }

    @staticmethod
    def get_saas_setup_snippet(tenant_id: str) -> dict[str, str]:
        """Generate SaaS Cloud+ onboarding instructions."""
        settings = get_settings()
        api_url = settings.API_URL.rstrip("/")
        sample_payload = (
            '[\n'
            '  {\n'
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
            "# 1) API key mode (recommended for vendors with billing APIs)\n"
            "# 2) Manual/CSV feed mode for quick onboarding\n"
            "#\n"
            "# Tenant-scoped subject for API/OIDC trust:\n"
            f"tenant:{tenant_id}\n"
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
        }

    @staticmethod
    def get_license_setup_snippet(tenant_id: str) -> dict[str, str]:
        """Generate License/ITAM Cloud+ onboarding instructions."""
        settings = get_settings()
        api_url = settings.API_URL.rstrip("/")
        sample_payload = (
            '[\n'
            '  {\n'
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
            "# 1) API key mode for ITAM/license platforms\n"
            "# 2) Manual/CSV feed mode for contract exports\n"
            "#\n"
            "# Tenant-scoped subject for API/OIDC trust:\n"
            f"tenant:{tenant_id}\n"
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
        }
