"""
Placement test: 30 questions, 3 minutes, determines user's CEFR level.
"""

import random
import uuid

from fastapi import APIRouter, Depends, HTTPException

from ..auth import CurrentUser, get_current_user
from ..database import get_conn
from ..models import (
    PlacementQuestion,
    PlacementQuestionsOut,
    PlacementResult,
    PlacementSubmitRequest,
)

router = APIRouter(prefix="/placement", tags=["placement"])

LEVEL_ORDER = ["A1", "A2", "B1", "B2", "C1", "C2"]

# Questions per level in the test
QUESTIONS_PER_LEVEL = {"A1": 4, "A2": 5, "B1": 6, "B2": 7, "C1": 5, "C2": 3}  # = 30 total


@router.get("/questions", response_model=PlacementQuestionsOut)
async def get_questions(current: CurrentUser = Depends(get_current_user)):
    """
    Build a 30-question multiple-choice test.
    Each question: see the English word, pick the correct Russian translation.
    Questions go from A1 → C2.
    """
    async with get_conn() as conn:
        questions = []
        idx = 0
        for level, count in QUESTIONS_PER_LEVEL.items():
            # Fetch candidate cards for this level
            rows = await conn.fetch(
                """
                SELECT id, front, back FROM cards
                WHERE cefr_level = $1
                  AND deck_id IN (SELECT id FROM decks WHERE source = 'platform')
                  AND back != ''
                ORDER BY random()
                LIMIT $2
                """,
                level, count,
            )
            if not rows:
                continue

            # Build 3 wrong options per question from other levels
            all_backs = await conn.fetch(
                """
                SELECT DISTINCT back FROM cards
                WHERE cefr_level != $1
                  AND deck_id IN (SELECT id FROM decks WHERE source = 'platform')
                  AND back != ''
                ORDER BY random()
                LIMIT $2
                """,
                level, count * 10,
            )
            wrong_pool = [r["back"] for r in all_backs]

            for row in rows:
                correct = row["back"].split(",")[0].strip()
                # pick 3 wrong answers
                wrongs = random.sample([w.split(",")[0].strip() for w in wrong_pool
                                        if w.split(",")[0].strip() != correct], k=min(3, len(wrong_pool)))
                options = wrongs + [correct]
                random.shuffle(options)

                questions.append(PlacementQuestion(
                    index=idx,
                    word=row["front"],
                    options=options,
                    cefr_level=level,
                ))
                idx += 1

    return PlacementQuestionsOut(questions=questions)


@router.post("/submit", response_model=PlacementResult)
async def submit_placement(
    body: PlacementSubmitRequest,
    current: CurrentUser = Depends(get_current_user),
):
    """
    Score answers, determine CEFR level, save result, return unlocked decks.

    Algorithm: if user scores < 50% on level N, that's their ceiling.
    Otherwise check next level. Floor is A1.
    """
    async with get_conn() as conn:
        # Rebuild questions to verify answers (same seed would be ideal;
        # here we trust the client sends word+answer and we verify against DB)
        answer_map = {a.question_index: a.chosen_option for a in body.answers}

        # Score per level
        level_scores: dict[str, tuple[int, int]] = {l: (0, 0) for l in LEVEL_ORDER}

        # Fetch all platform cards used in placement (just needs front→back mapping)
        for answer in body.answers:
            row = await conn.fetchrow(
                """
                SELECT c.back, c.cefr_level FROM cards c
                JOIN decks d ON d.id = c.deck_id AND d.source = 'platform'
                WHERE c.front = (
                    SELECT front FROM cards
                    WHERE deck_id IN (SELECT id FROM decks WHERE source='platform')
                    LIMIT 1 OFFSET $1
                )
                LIMIT 1
                """,
                answer.question_index,
            )
            if not row:
                continue
            correct   = row["back"].split(",")[0].strip()
            level     = row["cefr_level"]
            correct_r, total_r = level_scores.get(level, (0, 0))
            level_scores[level] = (
                correct_r + (1 if answer.chosen_option == correct else 0),
                total_r + 1,
            )

        # Determine ceiling level
        determined_level = "A1"
        for lvl in LEVEL_ORDER:
            correct_n, total_n = level_scores[lvl]
            if total_n == 0:
                continue
            if correct_n / total_n >= 0.5:
                determined_level = lvl
            else:
                break

        total_correct = sum(c for c, _ in level_scores.values())
        total_q       = len(body.answers)

        # Save result
        tenant_row = await conn.fetchrow("SELECT id FROM tenants WHERE slug = 'platform'")
        if tenant_row:
            await conn.execute(
                """
                INSERT INTO placement_results (user_id, tenant_id, cefr_level, score, answers)
                VALUES ($1, $2, $3, $4, $5::jsonb)
                ON CONFLICT (user_id, tenant_id) DO UPDATE SET
                    cefr_level = EXCLUDED.cefr_level,
                    score      = EXCLUDED.score,
                    answers    = EXCLUDED.answers,
                    taken_at   = NOW()
                """,
                current.user_id, tenant_row["id"],
                determined_level, total_correct,
                __import__("json").dumps([a.model_dump() for a in body.answers]),
            )

        # Unlock all decks up to and including determined level
        level_idx = LEVEL_ORDER.index(determined_level)
        unlocked_levels = LEVEL_ORDER[: level_idx + 1]

        unlocked_decks = await conn.fetch(
            """
            SELECT id FROM decks
            WHERE source = 'platform' AND cefr_level = ANY($1::text[])
            """,
            unlocked_levels,
        )

    return PlacementResult(
        cefr_level=determined_level,
        score=total_correct,
        total=total_q,
        unlocked_decks=[r["id"] for r in unlocked_decks],
    )
