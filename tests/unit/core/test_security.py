import pytest
import os
import base64
from uuid import uuid4
from unittest.mock import patch
from app.shared.core.security import (
    EncryptionKeyManager,
    encrypt_string,
    decrypt_string,
    generate_blind_index,
    generate_secret_blind_index,
)


@pytest.fixture
def mock_settings():
    with patch("app.shared.core.security.get_settings") as mock:
        mock.return_value.ENCRYPTION_KEY = "32-byte-long-test-encryption-key"
        mock.return_value.API_KEY_ENCRYPTION_KEY = None
        mock.return_value.PII_ENCRYPTION_KEY = None
        mock.return_value.BLIND_INDEX_KEY = "blind-index-key-for-testing"
        mock.return_value.ENCRYPTION_FALLBACK_KEYS = []
        yield mock


@pytest.fixture
def mock_env_salt():
    # base64("0" * 32) => 32 bytes after decode (required).
    with patch.dict(
        os.environ, {"KDF_SALT": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="}
    ):
        yield


def test_encryption_decryption_cycle(mock_settings, mock_env_salt):
    """Test full encryption/decryption round trip."""
    original = "secret_message"
    encrypted = encrypt_string(original)
    decrypted = decrypt_string(encrypted)

    assert original == decrypted
    assert original != encrypted


def test_context_encryption(mock_settings, mock_env_salt):
    """Test context-specific key usage."""
    # Setup specific keys for contexts
    mock_settings.return_value.API_KEY_ENCRYPTION_KEY = (
        "api-key-specific-encryption-key-32"
    )
    mock_settings.return_value.PII_ENCRYPTION_KEY = (
        "pii-data-specific-encryption-key-32"
    )

    # Encrypt with different contexts
    enc_generic = encrypt_string("data", context="generic")
    enc_api = encrypt_string("data", context="api_key")
    enc_pii = encrypt_string("data", context="pii")

    # They should produce different ciphertexts (even if randomness makes them different anyway,
    # decrypting with wrong context should fail)

    # Decrypt generic with correct context
    assert decrypt_string(enc_generic, context="generic") == "data"

    # Decrypt API with correct context
    assert decrypt_string(enc_api, context="api_key") == "data"

    # Decrypt PII with correct context
    assert decrypt_string(enc_pii, context="pii") == "data"


def test_kdf_salt_generation():
    """Test salt generation and retrieval."""
    salt = EncryptionKeyManager.generate_salt()
    assert len(base64.b64decode(salt)) == 32

    with patch("app.shared.core.security.get_settings") as mock_get:
        mock_get.return_value.KDF_SALT = None
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ValueError, match="KDF_SALT is required"):
                EncryptionKeyManager.get_or_create_salt()


def test_blind_index_deterministic(mock_settings):
    """Test blind index generation is deterministic."""
    val1 = generate_blind_index("user@example.com")
    val2 = generate_blind_index("user@example.com")
    val3 = generate_blind_index("other@example.com")

    assert val1 == val2
    assert val1 != val3


def test_blind_index_normalization(mock_settings):
    """Test blind index normalizes case and whitespace."""
    val1 = generate_blind_index(" user@Example.com ")
    val2 = generate_blind_index("user@example.com")

    assert val1 == val2


class TestSaltedBlindIndex:
    """Tests for SEC-HAR-11: Salted Blind Indexes (Finding #H17).

    Verifies cross-tenant isolation: the same plaintext value must
    produce different blind index hashes when different tenant_ids
    are used as HMAC salts.
    """

    def test_same_value_different_tenants_yields_different_hashes(self, mock_settings):
        """Two tenants encrypting the same email must get distinct hashes."""
        tenant_a = uuid4()
        tenant_b = uuid4()

        hash_a = generate_blind_index("shared@example.com", tenant_id=tenant_a)
        hash_b = generate_blind_index("shared@example.com", tenant_id=tenant_b)

        assert hash_a is not None
        assert hash_b is not None
        assert hash_a != hash_b, "Same value with different tenant_ids must produce different hashes"

    def test_same_value_same_tenant_is_deterministic(self, mock_settings):
        """Same value + same tenant must be repeatable."""
        tenant = uuid4()

        hash_1 = generate_blind_index("user@example.com", tenant_id=tenant)
        hash_2 = generate_blind_index("user@example.com", tenant_id=tenant)

        assert hash_1 == hash_2

    def test_unsalted_differs_from_salted(self, mock_settings):
        """Hash without tenant salt must differ from hash with tenant salt."""
        tenant = uuid4()

        unsalted = generate_blind_index("shared@example.com")
        salted = generate_blind_index("shared@example.com", tenant_id=tenant)

        assert unsalted != salted, "Salted hash must differ from unsalted hash"

    def test_empty_value_returns_none(self, mock_settings):
        """Empty or blank values return None regardless of tenant_id."""
        assert generate_blind_index("", tenant_id=uuid4()) is None
        assert generate_blind_index("  ", tenant_id=uuid4()) is None

    def test_none_value_returns_none(self, mock_settings):
        """None value returns None."""
        assert generate_blind_index(None, tenant_id=uuid4()) is None


class TestSecretSaltedBlindIndex:
    """Tests for generate_secret_blind_index with tenant salting.

    Secret blind indexes preserve case (e.g. API keys, tokens)
    but still support per-tenant isolation.
    """

    def test_secret_preserves_case(self, mock_settings):
        """Secret blind index must NOT lowercase the value."""
        tenant = uuid4()

        hash_lower = generate_secret_blind_index("mySecretKey", tenant_id=tenant)
        hash_upper = generate_secret_blind_index("MYSECRETKEY", tenant_id=tenant)

        assert hash_lower != hash_upper, "Secret blind index must preserve case"

    def test_secret_same_value_different_tenants(self, mock_settings):
        """Same secret in different tenants yields different hashes."""
        tenant_a = uuid4()
        tenant_b = uuid4()

        hash_a = generate_secret_blind_index("sk-live-abc123", tenant_id=tenant_a)
        hash_b = generate_secret_blind_index("sk-live-abc123", tenant_id=tenant_b)

        assert hash_a is not None
        assert hash_b is not None
        assert hash_a != hash_b

    def test_secret_deterministic_with_same_tenant(self, mock_settings):
        """Same secret + same tenant must be repeatable."""
        tenant = uuid4()

        hash_1 = generate_secret_blind_index("api-key-xyz", tenant_id=tenant)
        hash_2 = generate_secret_blind_index("api-key-xyz", tenant_id=tenant)

        assert hash_1 == hash_2

    def test_secret_empty_returns_none(self, mock_settings):
        """Empty secrets return None."""
        assert generate_secret_blind_index("", tenant_id=uuid4()) is None
        assert generate_secret_blind_index(None, tenant_id=uuid4()) is None
