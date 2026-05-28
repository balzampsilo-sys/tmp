"""User progress and analytics endpoints."""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends

from ..auth import CurrentUser, get_current_user
from ..database import get_conn
from ..models import HeatmapEntry, HeatmapOut, StatsOut

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("/me", response_model=StatsOut)
async def get_my_stats(current: CurrentUser = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    async with get_conn() as conn:
        card_stats = await conn.fetchrow(
            """
            SELECT
                COUNT(*)                                               AS total_enrolled,
                COUNT(*) FILTER (WHERE interval_days > 21)            AS mastered,
                COUNT(*) FILTER (WHERE state IN ('learning','relearning')) AS learning,
                COALESCE(SUM(reps), 0)                                AS total_reps,
                COALESCE(SUM(lapses), 0)                              AS total_lapses
            FROM (
                SELECT uc.reps, uc.lapses, uc.state,
                       GREATEST(0, EXTRACT(EPOCH FROM (uc.due_date - uc.last_review)) / 86400)::int
                           AS interval_days
                FROM user_cards uc
                WHERE uc.user_id = $1
            ) sub
            """,
            current.user_id,
        )

        reviews_today = await conn.fetchval(
            "SELECT COUNT(*) FROM review_logs WHERE user_id = $1 AND reviewed_at >= $2",
            current.user_id, today_start,
        ) or 0

        reviews_total = await conn.fetchval(
            "SELECT COUNT(*) FROM review_logs WHERE user_id = $1",
            current.user_id,
        ) or 0

        streak = await _calc_streak(conn, current.user_id, today_start)

    total_reps   = card_stats["total_reps"]
    total_lapses = card_stats["total_lapses"]
    retention    = total_reps / (total_reps + total_lapses) if (total_reps + total_lapses) > 0 else 0.0

    return StatsOut(
        total_cards_enrolled=card_stats["total_enrolled"],
        cards_mastered=card_stats["mastered"],
        cards_learning=card_stats["learning"],
        retention_rate=round(retention, 3),
        streak_days=streak,
        reviews_today=reviews_today,
        reviews_total=reviews_total,
    )


async def _calc_streak(conn, user_id: str, today_start: datetime) -> int:
    """Count consecutive days with at least 1 review, going backwards from today."""
    rows = await conn.fetch(
        """
        SELECT DISTINCT date_trunc('day', reviewed_at AT TIME ZONE 'UTC')::date AS day
        FROM review_logs
        WHERE user_id = $1
          AND reviewed_at >= NOW() - INTERVAL '365 days'
        ORDER BY day DESC
        """,
        user_id,
    )
    if not rows:
        return 0

    active_days = {r["day"] for r in rows}
    streak = 0
    check  = today_start.date()
    while check in active_days:
        streak += 1
        check  -= timedelta(days=1)
    return streak


@router.get("/me/heatmap", response_model=HeatmapOut)
async def get_heatmap(
    current: CurrentUser = Depends(get_current_user),
    days: int = 365,
):
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT
                date_trunc('day', reviewed_at AT TIME ZONE 'UTC')::date AS day,
                COUNT(*) AS cnt
            FROM review_logs
            WHERE user_id = $1
              AND reviewed_at >= NOW() - ($2 || ' days')::INTERVAL
            GROUP BY day
            ORDER BY day
            """,
            current.user_id, str(days),
        )

    return HeatmapOut(
        entries=[
            HeatmapEntry(date=str(r["day"]), count=r["cnt"])
            for r in rows
        ]
    )
