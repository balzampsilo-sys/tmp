import asyncpg
from contextlib import asynccontextmanager
from typing import AsyncGenerator

_pool: asyncpg.Pool | None = None


async def init_pool(dsn: str) -> None:
    global _pool
    _pool = await asyncpg.create_pool(
        dsn,
        min_size=2,
        max_size=20,
        command_timeout=30,
        # Return dicts instead of Record objects
        init=_set_codec,
    )


async def _set_codec(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb",
        encoder=__import__("json").dumps,
        decoder=__import__("json").loads,
        schema="pg_catalog",
    )
    await conn.set_type_codec(
        "json",
        encoder=__import__("json").dumps,
        decoder=__import__("json").loads,
        schema="pg_catalog",
    )


async def close_pool() -> None:
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


@asynccontextmanager
async def get_conn() -> AsyncGenerator[asyncpg.Connection, None]:
    assert _pool is not None, "DB pool not initialised"
    async with _pool.acquire() as conn:
        yield conn
