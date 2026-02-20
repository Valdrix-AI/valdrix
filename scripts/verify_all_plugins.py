
import asyncio
from app.modules.optimization.domain.registry import registry
import structlog

logger = structlog.get_logger()

async def verify_registry():
    print("Verifying Plugin Registry...")
    
    providers = ["aws", "azure", "gcp"]
    results = {}

    for provider in providers:
        print(f"\n--- {provider.upper()} ---")
        plugins = registry.get_plugins_for_provider(provider)
        results[provider] = [p.category_key for p in plugins]
        for p in plugins:
            print(f"✅ {p.category_key}")

    # Validation Logic
    missing = []
    
    # AWS
    if "customer_managed_kms_keys" not in results["aws"]: missing.append("AWS: KMS")
    if "idle_cloudfront_distributions" not in results["aws"]: missing.append("AWS: CloudFront")
    if "idle_dynamodb_tables" not in results["aws"]: missing.append("AWS: DynamoDB")
    if "empty_efs_volumes" not in results["aws"]: missing.append("AWS: EFS")
    
    # Azure
    if "unattached_azure_disks" not in results["azure"]: missing.append("Azure: Disks")
    if "orphan_azure_ips" not in results["azure"]: missing.append("Azure: IPs")
    if "stopped_azure_vms" not in results["azure"]: missing.append("Azure: StoppedVMs")
    
    # GCP
    if "unattached_gcp_disks" not in results["gcp"]: missing.append("GCP: Disks")
    if "stopped_gcp_instances" not in results["gcp"]: missing.append("GCP: StoppedVMs")

    print("\n--- SUMMARY ---")
    if not missing:
        print("🎉 SUCCESS: All required plugins are registered!")
    else:
        print(f"❌ FAILURE: Missing plugins: {', '.join(missing)}")

if __name__ == "__main__":
    asyncio.run(verify_registry())
