"""
Study session endpoints:
  GET  /study/due         — fetch due cards (new + learning + review)
  GET  /study/due/count   — count of due cards by state
  POST /study/review      — submit a rating, advance FSRS state
"""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import CurrentUser, get_current_user
from ..config import settings
from ..database import get_conn
from ..models import (
    DueCardOut,
    DueCountOut,
    ExampleOut,
    ReviewRequest,
    ReviewResponse,
)
from ..srs import CardState, Rating, State, fsrs

router = APIRouter(prefix="/study", tags=["study"])

_STATE_MAP = {"new": State.NEW, "learning": State.LEARNING,
              "review": State.REVIEW, "relearning": State.RELEARNING}


def _row_to_card_state(row: dict) -> CardState:
    return CardState(
        stability=row["stability"] or 0.0,
        difficulty=row["difficulty"] or 0.0,
        due_date=row["due_date"],
        last_review=row["last_review"],
        reps=row["reps"],
        lapses=row["lapses"],
        state=_STATE_MAP.get(row["state"], State.NEW),
    )


@router.get("/due/count", response_model=DueCountOut)
async def due_count(current: CurrentUser = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE uc.state = 'new')        AS new,
                COUNT(*) FILTER (WHERE uc.state = 'learning')   AS learning,
                COUNT(*) FILTER (WHERE uc.state IN ('review', 'relearning')
                                   AND uc.due_date <= $2)        AS review
            FROM user_cards uc
            WHERE uc.user_id = $1
            """,
            current.user_id, now,
        )
    return DueCountOut(
        new=row["new"],
        learning=row["learning"],
        review=row["review"],
        total=row["new"] + row["learning"] + row["review"],
    )


@router.get("/due", response_model=list[DueCardOut])
async def get_due_cards(
    limit: int = Query(20, ge=1, le=100),
    current: CurrentUser = Depends(get_current_user),
):
    """
    Return cards due for review. Priority order:
      1. Learning / Relearning (due_date <= now)
      2. Review (due_date <= now)
      3. New cards (up to daily limit)
    """
    now = datetime.now(timezone.utc)

    async with get_conn() as conn:
        # Check subscription for new-card daily limit
        sub = await conn.fetchrow(
            """
            SELECT sub_status FROM user_tenants ut
            JOIN tenants t ON t.id = ut.tenant_id AND t.slug = 'platform'
            WHERE ut.user_id = $1
            """,
            current.user_id,
        )
        daily_new_limit = (
            settings.pro_new_cards_per_day
            if sub and sub["sub_status"] == "pro"
            else settings.free_new_cards_per_day
        )

        new_today = await conn.fetchval(
            """
            SELECT COUNT(*) FROM review_logs
            WHERE user_id = $1
              AND reviewed_at >= date_trunc('day', $2::timestamptz)
              AND card_id IN (
                  SELECT card_id FROM user_cards WHERE user_id = $1 AND state = 'new'
              )
            """,
            current.user_id, now,
        ) or 0

        rows = await conn.fetch(
            """
            SELECT
                c.id, c.deck_id, c.front, c.back, c.ipa, c.pos,
                c.cefr_level, c.examples, c.synonyms, c.audio_url,
                uc.reps, uc.lapses, uc.state, uc.due_date
            FROM user_cards uc
            JOIN cards c ON c.id = uc.card_id
            WHERE uc.user_id = $1
              AND (
                  (uc.state IN ('learning', 'relearning') AND uc.due_date <= $2)
                  OR (uc.state = 'review' AND uc.due_date <= $2)
                  OR (uc.state = 'new')
              )
            ORDER BY
                CASE uc.state
                    WHEN 'learning'   THEN 1
                    WHEN 'relearning' THEN 1
                    WHEN 'review'     THEN 2
                    WHEN 'new'        THEN 3
                END,
                uc.due_date ASC NULLS LAST
            LIMIT $3
            """,
            current.user_id, now, limit + daily_new_limit,
        )

    # Apply new-card daily limit client-side after sorting
    result = []
    new_count = 0
    for row in rows:
        if row["state"] == "new":
            if new_count >= daily_new_limit - new_today:
                continue
            new_count += 1
        result.append(
            DueCardOut(
                id=row["id"],
                deck_id=row["deck_id"],
                front=row["front"],
                back=row["back"],
                ipa=row["ipa"],
                pos=row["pos"],
                cefr_level=row["cefr_level"],
                examples=[ExampleOut(**e) for e in (row["examples"] or [])],
                synonyms=row["synonyms"] or [],
                audio_url=row["audio_url"],
                reps=row["reps"],
                lapses=row["lapses"],
                state=row["state"],
            )
        )
        if len(result) >= limit:
            break

    return result


@router.post("/review", response_model=ReviewResponse)
async def submit_review(
    body: ReviewRequest,
    current: CurrentUser = Depends(get_current_user),
):
    """Submit a review rating and update FSRS state."""
    now = datetime.now(timezone.utc)

    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT stability, difficulty, due_date, last_review, reps, lapses, state
            FROM user_cards
            WHERE user_id = $1 AND card_id = $2
            """,
            current.user_id, str(body.card_id),
        )
        if not row:
            raise HTTPException(status_code=404, detail="Card not in study list")

        card_state  = _row_to_card_state(dict(row))
        rating      = Rating(body.rating)
        result      = fsrs.schedule(card_state, rating, now)
        new         = result.card

        rating_name = {1: "again", 2: "hard", 3: "good", 4: "easy"}[body.rating]

        async with conn.transaction():
            await conn.execute(
                """
                UPDATE user_cards SET
                    stability   = $3,
                    difficulty  = $4,
                    due_date    = $5,
                    last_review = $6,
                    reps        = $7,
                    lapses      = $8,
                    state       = $9
                WHERE user_id = $1 AND card_id = $2
                """,
                current.user_id, str(body.card_id),
                new.stability, new.difficulty, new.due_date, now,
                new.reps, new.lapses, new.state.name.lower(),
            )
            await conn.execute(
                """
                INSERT INTO review_logs
                    (user_id, card_id, rating, stability_before, difficulty_before,
                     interval_before, elapsed_ms, reviewed_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                current.user_id, str(body.card_id), rating_name,
                result.review_log["stability_before"],
                result.review_log["difficulty_before"],
                result.review_log["interval_before"],
                body.elapsed_ms, now,
            )

    interval_days = max(0, round((new.due_date - now).total_seconds() / 86400))

    return ReviewResponse(
        card_id=body.card_id,
        next_due=new.due_date,
        new_interval_days=interval_days,
        new_stability=round(new.stability, 2),
        new_state=new.state.name.lower(),
    )
