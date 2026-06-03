"""Integration tests for deck endpoints."""

import pytest
import pytest_asyncio

from conftest import requires_db


@requires_db
class TestListDecks:
    @pytest.mark.asyncio
    async def test_empty_returns_list(self, client):
        resp = await client.get("/decks")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    @pytest.mark.asyncio
    async def test_platform_deck_visible(self, client, platform_deck_id):
        resp = await client.get("/decks")
        assert resp.status_code == 200
        ids = [d["id"] for d in resp.json()]
        assert platform_deck_id in ids

    @pytest.mark.asyncio
    async def test_filter_by_level(self, client, platform_deck_id):
        resp = await client.get("/decks?level=B1")
        assert resp.status_code == 200
        for deck in resp.json():
            assert deck["cefr_level"] == "B1"

    @pytest.mark.asyncio
    async def test_invalid_level_rejected(self, client):
        resp = await client.get("/decks?level=X9")
        assert resp.status_code == 422


@requires_db
class TestGetDeck:
    @pytest.mark.asyncio
    async def test_get_existing_deck(self, client, platform_deck_id):
        resp = await client.get(f"/decks/{platform_deck_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == platform_deck_id
        assert data["card_count"] == 5

    @pytest.mark.asyncio
    async def test_get_nonexistent_deck(self, client):
        fake_id = "00000000-0000-0000-0000-000000000000"
        resp = await client.get(f"/decks/{fake_id}")
        assert resp.status_code == 404


@requires_db
class TestEnrollDeck:
    @pytest.mark.asyncio
    async def test_enroll_creates_user_cards(self, client, db_conn, platform_deck_id):
        resp = await client.post(f"/decks/{platform_deck_id}/enroll")
        assert resp.status_code == 204

        # Verify user_cards were created
        count = await db_conn.fetchval(
            """
            SELECT COUNT(*) FROM user_cards uc
            JOIN cards c ON c.id = uc.card_id
            WHERE c.deck_id = $1
            """,
            platform_deck_id,
        )
        assert count == 5

    @pytest.mark.asyncio
    async def test_enroll_idempotent(self, client, platform_deck_id):
        await client.post(f"/decks/{platform_deck_id}/enroll")
        resp = await client.post(f"/decks/{platform_deck_id}/enroll")
        assert resp.status_code == 204

    @pytest.mark.asyncio
    async def test_deck_marked_enrolled_after_enroll(self, client, platform_deck_id):
        await client.post(f"/decks/{platform_deck_id}/enroll")
        resp = await client.get(f"/decks/{platform_deck_id}")
        assert resp.json()["enrolled"] is True

    @pytest.mark.asyncio
    async def test_unenroll_removes_user_cards(self, client, db_conn, platform_deck_id):
        await client.post(f"/decks/{platform_deck_id}/enroll")
        resp = await client.delete(f"/decks/{platform_deck_id}/enroll")
        assert resp.status_code == 204

        count = await db_conn.fetchval(
            """
            SELECT COUNT(*) FROM user_cards uc
            JOIN cards c ON c.id = uc.card_id
            WHERE c.deck_id = $1
            """,
            platform_deck_id,
        )
        assert count == 0


@requires_db
class TestCreateDeck:
    @pytest.mark.asyncio
    async def test_create_personal_deck(self, client):
        resp = await client.post("/decks", json={
            "name": "My Custom Deck",
            "cefr_level": "B2",
            "is_public": False,
        })
        assert resp.status_code == 201
        data = resp.json()
        assert data["name"] == "My Custom Deck"
        assert data["source"] == "personal"
        assert data["enrolled"] is True

    @pytest.mark.asyncio
    async def test_create_deck_name_required(self, client):
        resp = await client.post("/decks", json={"cefr_level": "A1"})
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_create_deck_invalid_level(self, client):
        resp = await client.post("/decks", json={
            "name": "Test",
            "cefr_level": "D5",
        })
        assert resp.status_code == 422
