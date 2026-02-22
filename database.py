import asyncpg
import config

_pool: asyncpg.Pool | None = None


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(config.DATABASE_URL, min_size=1, max_size=5)
    return _pool


async def init_db():
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tg_users (
                tg_id BIGINT PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS tg_messages (
                id SERIAL PRIMARY KEY,
                tg_id BIGINT REFERENCES tg_users(tg_id),
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                tokens_used INT,
                created_at TIMESTAMPTZ DEFAULT NOW()
            )
        """)


async def upsert_user(tg_id: int, username: str | None, first_name: str | None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO tg_users (tg_id, username, first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (tg_id) DO UPDATE
            SET username = EXCLUDED.username, first_name = EXCLUDED.first_name
        """, tg_id, username, first_name)


async def save_message(tg_id: int, role: str, content: str, tokens_used: int | None = None):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO tg_messages (tg_id, role, content, tokens_used)
            VALUES ($1, $2, $3, $4)
        """, tg_id, role, content, tokens_used)


async def get_history(tg_id: int, limit: int = 10) -> list[dict]:
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT role, content, created_at
            FROM tg_messages
            WHERE tg_id = $1
            ORDER BY created_at DESC
            LIMIT $2
        """, tg_id, limit)
    return [dict(r) for r in reversed(rows)]


async def clear_history(tg_id: int):
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM tg_messages WHERE tg_id = $1", tg_id)


async def get_stats() -> dict:
    pool = await get_pool()
    async with pool.acquire() as conn:
        users = await conn.fetchval("SELECT COUNT(*) FROM tg_users")
        messages = await conn.fetchval("SELECT COUNT(*) FROM tg_messages")
        tokens = await conn.fetchval("SELECT COALESCE(SUM(tokens_used), 0) FROM tg_messages WHERE tokens_used IS NOT NULL")
        active_today = await conn.fetchval("""
            SELECT COUNT(DISTINCT tg_id) FROM tg_messages
            WHERE created_at >= NOW() - INTERVAL '24 hours'
        """)
    return {
        "users": users,
        "messages": messages,
        "tokens": tokens,
        "active_today": active_today,
    }
