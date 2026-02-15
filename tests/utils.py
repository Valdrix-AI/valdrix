import jwt
from uuid import UUID
from datetime import datetime, timezone, timedelta
from app.shared.core.config import get_settings

settings = get_settings()


def create_test_token(user_id: UUID, email: str):
    """Generate a valid test JWT for Supabase authentication."""
    payload = {
        "sub": str(user_id),
        "email": email,
        "aud": "authenticated",  # Match Supabase default aud
        "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp()),
    }
    return jwt.encode(payload, settings.SUPABASE_JWT_SECRET, algorithm="HS256")
