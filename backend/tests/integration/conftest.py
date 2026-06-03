"""
Pytest fixtures for API integration tests.

Uses a real PostgreSQL database (DATABASE_URL env var).
If DATABASE_URL is not set, integration tests are skipped.

Fixtures:
  - app_client  — httpx AsyncClient with auth override
  - db_conn     — raw asyncpg connection for test setup/teardown
  - authed      — helper to set Authorization header
"""

import os
import uuid
from collections.abc import AsyncGenerator
from unittest.mock import AsyncMock, patch

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from api.auth import CurrentUser, get_current_user
from api.main import app

TEST_DB_URL = os.getenv("DATABASE_URL", "")
TEST_USER_ID = str(uuid.uuid4())
TEST_TG_ID   = 999_000_001


# ── Skip marker ───────────────────────────────────────────────────────────────

requires_db = pytest.mark.skipif(
    not TEST_DB_URL,
    reason="DATABASE_URL not set — skipping integration tests",
)


# ── DB fixtures ───────────────────────────────────────────────────────────────

@pytest_asyncio.fixture(scope="session")
async def db_pool():
    if not TEST_DB_URL:
        pytest.skip("DATABASE_URL not set")
    pool = await asyncpg.create_pool(TEST_DB_URL, min_size=1, max_size=5)
    yield pool
    await pool.close()


@pytest_asyncio.fixture
async def db_conn(db_pool) -> AsyncGenerator[asyncpg.Connection, None]:
    async with db_pool.acquire() as conn:
        async with conn.transaction():
            # Seed a test user
            await conn.execute(
                """
                INSERT INTO users (id, telegram_id, first_name)
                VALUES ($1, $2, 'TestUser')
                ON CONFLICT (telegram_id) DO UPDATE SET id = EXCLUDED.id
                """,
                TEST_USER_ID, TEST_TG_ID,
            )
            yield conn
            # Transaction rolls back automatically — test data is cleaned up


# ── App client with mocked auth ───────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db_pool) -> AsyncGenerator[AsyncClient, None]:
    """
    httpx AsyncClient connected to the FastAPI app.
    Auth dependency is overridden to return a fixed test user.
    DB pool is patched to use the test pool.
    """
    async def mock_auth() -> CurrentUser:
        return CurrentUser(user_id=TEST_USER_ID, telegram_id=TEST_TG_ID)

    app.dependency_overrides[get_current_user] = mock_auth

    # Patch the DB pool
    with patch("api.database._pool", db_pool):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as c:
            yield c

    app.dependency_overrides.clear()


@pytest_asyncio.fixture
async def platform_deck_id(db_conn) -> str:
    """Insert a minimal platform deck + 5 cards. Returns deck_id."""
    # Ensure platform tenant exists
    tenant_id = str(uuid.uuid4())
    await db_conn.execute(
        """
        INSERT INTO tenants (id, slug, name)
        VALUES ($1, 'platform', 'Platform')
        ON CONFLICT (slug) DO UPDATE SET id = tenants.id
        RETURNING id
        """,
        tenant_id,
    )
    row = await db_conn.fetchrow("SELECT id FROM tenants WHERE slug = 'platform'")
    tenant_id = str(row["id"])

    deck_id = str(uuid.uuid4())
    await db_conn.execute(
        """
        INSERT INTO decks (id, tenant_id, source, name, cefr_level, is_public)
        VALUES ($1, $2, 'platform', 'Test Deck B1', 'B1', TRUE)
        ON CONFLICT DO NOTHING
        """,
        deck_id, tenant_id,
    )

    # Insert 5 cards
    for i in range(5):
        await db_conn.execute(
            """
            INSERT INTO cards (id, deck_id, front, back, cefr_level)
            VALUES ($1, $2, $3, $4, 'B1')
            ON CONFLICT DO NOTHING
            """,
            str(uuid.uuid4()), deck_id, f"word_{i}", f"слово_{i}",
        )

    return deck_id
