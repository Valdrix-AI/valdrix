import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

print("🔍 Importing get_settings...", flush=True)
from app.shared.core.config import get_settings  # noqa: E402
print("✅ Config imported!", flush=True)
settings = get_settings()
print(f"✅ Loaded settings! Enc Key present: {bool(settings.ENCRYPTION_KEY)}", flush=True)
