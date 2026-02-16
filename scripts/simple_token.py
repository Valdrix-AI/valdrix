
import jwt
import os
import base64
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

load_dotenv()
secret_str = os.getenv('SUPABASE_JWT_SECRET')
# Supabase secrets are often base64 encoded.
try:
    secret = base64.b64decode(secret_str)
except Exception:
    secret = secret_str

uid = "ffb600f6-46cc-410e-a9f3-275d942663f3"
email = "admin@jirasmo.ke"

payload = {
    "sub": uid,
    "email": email,
    "aud": "authenticated",
    "iss": "supabase",
    "exp": int((datetime.now(timezone.utc) + timedelta(hours=100)).timestamp())
}

token = jwt.encode(payload, secret, algorithm="HS256")
print(token)
