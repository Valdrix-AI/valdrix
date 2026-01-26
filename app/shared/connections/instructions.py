from app.shared.core.config import get_settings

class ConnectionInstructionService:
    """
    Generates setup instructions and CLI snippets for cloud connections.
    Encapsulates string building logic to keep API routes clean.
    """

    @staticmethod
    def get_azure_setup_snippet(tenant_id: str) -> dict:
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
    def get_gcp_setup_snippet(tenant_id: str) -> dict:
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
