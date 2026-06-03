"""Integration tests for stats and heatmap endpoints."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from conftest import TEST_USER_ID, requires_db

NOW = datetime.now(timezone.utc)


@requires_db
class TestGetStats:
    @pytest.mark.asyncio
    async def test_empty_stats(self, client):
        resp = await client.get("/stats/me")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_cards_enrolled"] == 0
        assert data["streak_days"] == 0
        assert data["retention_rate"] == 0.0

    @pytest.mark.asyncio
    async def test_stats_after_enroll(self, client, platform_deck_id):
        await client.post(f"/decks/{platform_deck_id}/enroll")
        resp = await client.get("/stats/me")
        data = resp.json()
        assert data["total_cards_enrolled"] == 5

    @pytest.mark.asyncio
    async def test_retention_after_reviews(self, client, db_conn, platform_deck_id):
        await client.post(f"/decks/{platform_deck_id}/enroll")
        card_ids = await db_conn.fetch(
            "SELECT card_id FROM user_cards WHERE user_id=$1 LIMIT 3",
            TEST_USER_ID,
        )

        # 2 successful, 1 lapse
        for i, row in enumerate(card_ids):
            await db_conn.execute(
                """
                UPDATE user_cards SET reps=$1, lapses=$2
                WHERE user_id=$3 AND card_id=$4
                """,
                (1 if i < 2 else 0), (0 if i < 2 else 1),
                TEST_USER_ID, str(row["card_id"]),
            )

        resp = await client.get("/stats/me")
        data = resp.json()
        # retention = 2 / (2+1) ≈ 0.667
        assert 0.6 < data["retention_rate"] < 0.8

    @pytest.mark.asyncio
    async def test_streak_zero_initially(self, client):
        resp = await client.get("/stats/me")
        assert resp.json()["streak_days"] == 0

    @pytest.mark.asyncio
    async def test_streak_one_after_review_today(self, client, db_conn, platform_deck_id):
        await client.post(f"/decks/{platform_deck_id}/enroll")
        card_id = str((await db_conn.fetchrow(
            "SELECT card_id FROM user_cards WHERE user_id=$1 LIMIT 1",
            TEST_USER_ID,
        ))["card_id"])

        # Insert a review_log for today
        await db_conn.execute(
            """
            INSERT INTO review_logs (user_id, card_id, rating, reviewed_at)
            VALUES ($1, $2, 'good', NOW())
            """,
            TEST_USER_ID, card_id,
        )

        resp = await client.get("/stats/me")
        assert resp.json()["streak_days"] == 1

    @pytest.mark.asyncio
    async def test_required_fields_present(self, client):
        data = (await client.get("/stats/me")).json()
        for field in (
            "total_cards_enrolled", "cards_mastered", "cards_learning",
            "retention_rate", "streak_days", "reviews_today", "reviews_total",
        ):
            assert field in data


@requires_db
class TestHeatmap:
    @pytest.mark.asyncio
    async def test_heatmap_empty(self, client):
        resp = await client.get("/stats/me/heatmap")
        assert resp.status_code == 200
        assert resp.json()["entries"] == []

    @pytest.mark.asyncio
    async def test_heatmap_has_entry_after_review(self, client, db_conn, platform_deck_id):
        await client.post(f"/decks/{platform_deck_id}/enroll")
        card_id = str((await db_conn.fetchrow(
            "SELECT card_id FROM user_cards WHERE user_id=$1 LIMIT 1",
            TEST_USER_ID,
        ))["card_id"])

        await db_conn.execute(
            "INSERT INTO review_logs (user_id, card_id, rating) VALUES ($1, $2, 'good')",
            TEST_USER_ID, card_id,
        )

        resp = await client.get("/stats/me/heatmap")
        entries = resp.json()["entries"]
        assert len(entries) >= 1
        assert "date" in entries[0]
        assert "count" in entries[0]

    @pytest.mark.asyncio
    async def test_heatmap_multiple_reviews_same_day(self, client, db_conn, platform_deck_id):
        await client.post(f"/decks/{platform_deck_id}/enroll")
        card_ids = await db_conn.fetch(
            "SELECT card_id FROM user_cards WHERE user_id=$1 LIMIT 3",
            TEST_USER_ID,
        )
        for row in card_ids:
            await db_conn.execute(
                "INSERT INTO review_logs (user_id, card_id, rating) VALUES ($1, $2, 'good')",
                TEST_USER_ID, str(row["card_id"]),
            )

        resp = await client.get("/stats/me/heatmap")
        entries = resp.json()["entries"]
        today_entry = next((e for e in entries if e["count"] >= 3), None)
        assert today_entry is not None
        assert today_entry["count"] >= 3
