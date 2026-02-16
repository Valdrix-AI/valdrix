
import asyncio
from sqlalchemy import text
from app.shared.db.session import async_session_maker

async def force_wipe():
    print('Forcing wipe by dropping public schema using app engine...')
    async with async_session_maker() as session:
        try:
            # Drop schema cascade is the most effective way
            await session.execute(text('DROP SCHEMA public CASCADE'))
            await session.execute(text('CREATE SCHEMA public'))
            await session.execute(text('GRANT ALL ON SCHEMA public TO postgres'))
            await session.execute(text('GRANT ALL ON SCHEMA public TO public'))
            await session.commit()
            print('✅ Database Wiped (Schema-level)')
        except Exception as e:
            print(f'❌ Error: {e}')
            await session.rollback()

if __name__ == '__main__':
    asyncio.run(force_wipe())
