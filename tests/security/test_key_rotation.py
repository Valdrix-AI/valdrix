import pytest
from cryptography.fernet import Fernet
from app.shared.core.security import encrypt_string, decrypt_string
from unittest.mock import patch, MagicMock

@pytest.mark.asyncio
async def test_key_rotation_compatibility():
    """
    Verifies that shifting a key to the fallback list still allows decryption.
    Patches get_settings to return a mock that we can manipulate.
    """
    # 1. Generate two valid keys
    key_alpha = Fernet.generate_key().decode()
    key_beta = Fernet.generate_key().decode()
    original_text = "Secret Data 2026"

    # 2. Create a mock settings object
    mock_settings = MagicMock()
    mock_settings.ENCRYPTION_KEY = key_alpha
    mock_settings.ENCRYPTION_KEY_FALLBACKS = []
    mock_settings.LEGACY_ENCRYPTION_KEYS = []
    mock_settings.API_KEY_ENCRYPTION_KEY = None
    mock_settings.PII_ENCRYPTION_KEY = None
    mock_settings.KDF_SALT = "test-salt"
    mock_settings.KDF_ITERATIONS = 1000

    # 3. Patch get_settings in the security module
    with patch("app.shared.core.security.get_settings", return_value=mock_settings):
        # Initial encryption with key_alpha
        encrypted_alpha = encrypt_string(original_text)
        
        # 4. Rotate: Beta as primary, Alpha as fallback (LEGACY_ENCRYPTION_KEYS)
        mock_settings.ENCRYPTION_KEY = key_beta
        mock_settings.LEGACY_ENCRYPTION_KEYS = [key_alpha]
        
        # 5. Attempt decryption (should succeed because Alpha is in LEGACY_ENCRYPTION_KEYS)
        decrypted = decrypt_string(encrypted_alpha)
        assert decrypted == original_text
        
        # 6. Encrypt new data with Beta
        encrypted_beta = encrypt_string("New Secret")
        
        # 7. Verify decryption with primary key Beta
        assert decrypt_string(encrypted_beta) == "New Secret"
        
        # 8. Remove Alpha from fallbacks
        mock_settings.LEGACY_ENCRYPTION_KEYS = []
        
        # 9. Decryption of Alpha data should now fail (return None)
        assert decrypt_string(encrypted_alpha) is None
