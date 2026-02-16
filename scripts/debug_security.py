import sys
import os

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

print("🔍 Importing get_settings...", flush=True)
from app.shared.core.config import get_settings  # noqa: E402
settings = get_settings()
print(f"✅ Loaded settings! Enc Key present: {bool(settings.ENCRYPTION_KEY)}", flush=True)

print("🔍 Importing security...", flush=True)
from app.shared.core.security import generate_blind_index, encrypt_string  # noqa: E402
print("✅ Security imported!", flush=True)

print("🔍 Testing encryption...", flush=True)
enc = encrypt_string("test")
print(f"✅ Encrypted: {enc[:10]}...", flush=True)

print("🔍 Testing blind index...", flush=True)
bidx = generate_blind_index("test")
print(f"✅ Blind Index: {bidx[:10]}...", flush=True)
