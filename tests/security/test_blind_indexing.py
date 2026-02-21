import uuid
from app.models.tenant import Tenant, User
from app.shared.core.security import generate_blind_index


def test_blind_index_generation():
    email = "test@example.com"
    expected_hash = generate_blind_index(email)

    # Check normalization
    assert generate_blind_index(" TEST@example.com ") == expected_hash
    assert expected_hash is not None
    assert len(expected_hash) == 64  # SHA256 hex digest


def test_tenant_blind_index_listener():
    tenant = Tenant(name="Acme Corp")
    # The listener should have triggered on name set
    assert tenant.name_bidx == generate_blind_index("Acme Corp")

    # Test update
    tenant.name = "Global Acme"
    assert tenant.name_bidx == generate_blind_index("Global Acme")


def test_user_blind_index_listener():
    tenant_id = uuid.uuid4()
    user = User(id=uuid.uuid4(), tenant_id=tenant_id, email="user@valdrix.ai")
    assert user.email_bidx == generate_blind_index("user@valdrix.ai", tenant_id=tenant_id)

    # Test update
    user.email = "new@valdrix.ai"
    assert user.email_bidx == generate_blind_index("new@valdrix.ai", tenant_id=tenant_id)
