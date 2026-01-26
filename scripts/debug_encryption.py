from app.shared.core.security import EncryptionKeyManager, encrypt_string
import os

os.environ["KDF_SALT"] = EncryptionKeyManager.generate_salt()
os.environ["ENVIRONMENT"] = "development"

print(f"EncryptionKeyManager: {EncryptionKeyManager}")
salt = EncryptionKeyManager.generate_salt()
print(f"Generated Salt: {salt}")

encrypted = encrypt_string("test")
print(f"Encrypted: {encrypted}")
