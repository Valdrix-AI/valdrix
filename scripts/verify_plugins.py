
import asyncio
from app.modules.optimization.domain.registry import registry
import app.modules.optimization.adapters.aws.plugins  # Trigger registration
import structlog

logger = structlog.get_logger()

async def verify_registry():
    print("Verifying Plugin Registry...")
    plugins = registry.get_plugins_for_provider("aws")
    
    found_kms = False
    found_cf = False
    
    for p in plugins:
        # print(f"Found plugin: {p.category_key} ({p.__class__.__name__})")
        if p.category_key == "customer_managed_kms_keys":
            found_kms = True
            print(f"✅ KMS Plugin Registered: {p.__class__.__name__}")
        if p.category_key == "idle_cloudfront_distributions":
            found_cf = True
            print(f"✅ CloudFront Plugin Registered: {p.__class__.__name__}")
            
    if found_kms and found_cf:
        print("SUCCESS: All new plugins are registered.")
    else:
        print(f"FAILURE: Missing plugins. KMS: {found_kms}, CloudFront: {found_cf}")

if __name__ == "__main__":
    asyncio.run(verify_registry())
