
import asyncio
import sys
from datetime import timedelta
from dotenv import load_dotenv

async def generate_token():
    load_dotenv()
    # Import app internal logic
    from app.shared.core.auth import create_access_token
    from app.shared.db.session import async_session_maker
    from app.models.tenant import User
    from sqlalchemy import select

    try:
        async with async_session_maker() as db:
            # Query first user
            row = (await db.execute(select(User.id, User.email).limit(1))).first()
            if not row:
                print("No users found", file=sys.stderr)
                return

            uid, email = row
            token = create_access_token(
                {"sub": str(uid), "email": str(email)}, 
                expires_delta=timedelta(hours=24)
            )
            print(token)

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)

if __name__ == "__main__":
    asyncio.run(generate_token())
