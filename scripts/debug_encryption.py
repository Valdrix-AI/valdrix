from app.shared.core.security import EncryptionKeyManager, encrypt_string
import os

os.environ["KDF_SALT"] = EncryptionKeyManager.generate_salt()
os.environ["ENVIRONMENT"] = "development"

encrypted = encrypt_string("test")
if encrypted:
    print("encryption_self_check_ok")
else:
    print("encryption_self_check_failed")
