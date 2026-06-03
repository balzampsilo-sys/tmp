"""Integration tests for study session endpoints (due cards + review)."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from conftest import TEST_USER_ID, requires_db

NOW = datetime.now(timezone.utc)


async def enroll_and_get_card_id(client, db_conn, deck_id: str) -> str:
    """Helper: enroll in deck, return first card_id."""
    await client.post(f"/decks/{deck_id}/enroll")
    row = await db_conn.fetchrow(
        "SELECT card_id FROM user_cards WHERE user_id = $1 LIMIT 1",
        TEST_USER_ID,
    )
    return str(row["card_id"])


@requires_db
class TestDueCount:
    @pytest.mark.asyncio
    async def test_count_zero_when_not_enrolled(self, client):
        resp = await client.get("/study/due/count")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    @pytest.mark.asyncio
    async def test_count_new_after_enroll(self, client, platform_deck_id):
        await client.post(f"/decks/{platform_deck_id}/enroll")
        resp = await client.get("/study/due/count")
        data = resp.json()
        assert data["new"] == 5
        assert data["total"] == 5


@requires_db
class TestGetDueCards:
    @pytest.mark.asyncio
    async def test_empty_when_not_enrolled(self, client):
        resp = await client.get("/study/due")
        assert resp.status_code == 200
        assert resp.json() == []

    @pytest.mark.asyncio
    async def test_returns_new_cards_after_enroll(self, client, platform_deck_id):
        await client.post(f"/decks/{platform_deck_id}/enroll")
        resp = await client.get("/study/due")
        assert resp.status_code == 200
        cards = resp.json()
        assert len(cards) > 0
        assert all(c["state"] == "new" for c in cards)

    @pytest.mark.asyncio
    async def test_card_has_required_fields(self, client, platform_deck_id):
        await client.post(f"/decks/{platform_deck_id}/enroll")
        cards = (await client.get("/study/due")).json()
        card  = cards[0]
        for field in ("id", "front", "back", "state", "reps", "lapses"):
            assert field in card

    @pytest.mark.asyncio
    async def test_limit_parameter(self, client, platform_deck_id):
        await client.post(f"/decks/{platform_deck_id}/enroll")
        resp = await client.get("/study/due?limit=2")
        assert len(resp.json()) <= 2

    @pytest.mark.asyncio
    async def test_learning_cards_come_before_new(self, client, db_conn, platform_deck_id):
        await client.post(f"/decks/{platform_deck_id}/enroll")

        # Force one card to LEARNING state (due now)
        card_id = await db_conn.fetchval(
            "SELECT card_id FROM user_cards WHERE user_id = $1 LIMIT 1",
            TEST_USER_ID,
        )
        await db_conn.execute(
            """
            UPDATE user_cards SET state='learning', due_date=$1
            WHERE user_id=$2 AND card_id=$3
            """,
            NOW - timedelta(minutes=1), TEST_USER_ID, str(card_id),
        )

        cards = (await client.get("/study/due")).json()
        assert cards[0]["state"] == "learning"


@requires_db
class TestSubmitReview:
    @pytest.mark.asyncio
    async def test_review_again_stays_learning(self, client, db_conn, platform_deck_id):
        card_id = await enroll_and_get_card_id(client, db_conn, platform_deck_id)
        resp = await client.post("/study/review", json={
            "card_id": card_id,
            "rating": 1,  # AGAIN
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_state"] == "learning"
        assert data["new_interval_days"] == 0

    @pytest.mark.asyncio
    async def test_review_easy_graduates(self, client, db_conn, platform_deck_id):
        card_id = await enroll_and_get_card_id(client, db_conn, platform_deck_id)
        resp = await client.post("/study/review", json={
            "card_id": card_id,
            "rating": 4,  # EASY
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["new_state"] == "review"
        assert data["new_interval_days"] >= 1

    @pytest.mark.asyncio
    async def test_review_persists_to_db(self, client, db_conn, platform_deck_id):
        card_id = await enroll_and_get_card_id(client, db_conn, platform_deck_id)
        await client.post("/study/review", json={"card_id": card_id, "rating": 3})

        row = await db_conn.fetchrow(
            "SELECT state, reps FROM user_cards WHERE user_id=$1 AND card_id=$2",
            TEST_USER_ID, card_id,
        )
        assert row["state"] in ("learning", "review")

    @pytest.mark.asyncio
    async def test_review_creates_log_entry(self, client, db_conn, platform_deck_id):
        card_id = await enroll_and_get_card_id(client, db_conn, platform_deck_id)
        await client.post("/study/review", json={
            "card_id": card_id,
            "rating": 3,
            "elapsed_ms": 2500,
        })

        log = await db_conn.fetchrow(
            "SELECT rating, elapsed_ms FROM review_logs WHERE user_id=$1 AND card_id=$2",
            TEST_USER_ID, card_id,
        )
        assert log is not None
        assert log["rating"] == "good"
        assert log["elapsed_ms"] == 2500

    @pytest.mark.asyncio
    async def test_review_invalid_rating(self, client, db_conn, platform_deck_id):
        card_id = await enroll_and_get_card_id(client, db_conn, platform_deck_id)
        resp = await client.post("/study/review", json={
            "card_id": card_id,
            "rating": 99,
        })
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_review_nonexistent_card(self, client):
        resp = await client.post("/study/review", json={
            "card_id": str(uuid.uuid4()),
            "rating": 3,
        })
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_full_new_to_review_cycle(self, client, db_conn, platform_deck_id):
        """Simulate new → GOOD → EASY → REVIEW state via API."""
        card_id = await enroll_and_get_card_id(client, db_conn, platform_deck_id)

        # GOOD: new → learning
        r1 = (await client.post("/study/review", json={"card_id": card_id, "rating": 3})).json()
        assert r1["new_state"] == "learning"

        # EASY: learning → review
        r2 = (await client.post("/study/review", json={"card_id": card_id, "rating": 4})).json()
        assert r2["new_state"] == "review"
        assert r2["new_interval_days"] >= 1
        assert r2["new_stability"] > 0
