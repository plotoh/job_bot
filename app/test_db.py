import asyncio
import asyncpg
from app.config import DB_CONFIG

async def test():
    try:
        conn = await asyncpg.connect(**DB_CONFIG, timeout=10)
        print("Connected successfully!")
        await conn.close()
    except asyncpg.PostgresError as e:
        print(f"PostgreSQL error: {e}")
    except Exception as e:
        print(f"Other error: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test())