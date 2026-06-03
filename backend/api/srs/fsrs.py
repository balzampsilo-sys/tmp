"""
FSRS 4.5 — Free Spaced Repetition Scheduler.

Paper: https://github.com/open-spaced-repetition/fsrs4anki/wiki/The-Algorithm
Default weights from the paper (trained on 20k+ Anki reviews).
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import IntEnum

# ── Types ─────────────────────────────────────────────────────────────────────

class Rating(IntEnum):
    AGAIN = 1
    HARD  = 2
    GOOD  = 3
    EASY  = 4


class State(IntEnum):
    NEW        = 0
    LEARNING   = 1
    REVIEW     = 2
    RELEARNING = 3


@dataclass
class CardState:
    stability:  float = 0.0
    difficulty: float = 0.0
    due_date:   datetime = None   # type: ignore[assignment]
    last_review: datetime | None = None
    reps:       int = 0
    lapses:     int = 0
    state:      State = State.NEW

    def __post_init__(self):
        if self.due_date is None:
            self.due_date = datetime.now(timezone.utc)


@dataclass
class ScheduleResult:
    card:           CardState
    review_log:     dict   # fields to write to review_logs


# ── FSRS 4.5 weights (default) ────────────────────────────────────────────────

W = [
    0.4072,   # w0  initial stability: again
    1.1829,   # w1  initial stability: hard
    3.1262,   # w2  initial stability: good
    15.4722,  # w3  initial stability: easy
    7.2102,   # w4  initial difficulty
    0.5316,   # w5  difficulty target (mean reversion target)
    1.0651,   # w6  difficulty change per rating step
    0.0589,   # w7  difficulty mean reversion rate
    1.5330,   # w8  recall stability multiplier
    0.1544,   # w9  stability power decay (recall)
    0.9956,   # w10 stability boost from retrievability (recall)
    1.9955,   # w11 forget stability multiplier
    0.1100,   # w12 forget stability: difficulty factor
    0.2900,   # w13 forget stability: stability factor
    2.2700,   # w14 forget stability: retrievability factor
    0.2500,   # w15 hard penalty multiplier
    2.9898,   # w16 easy bonus multiplier
]

DECAY            = -0.5
FACTOR           = 19 / 81   # ≈ 0.2346
REQUEST_RETENTION = 0.9

# Learning steps (minutes) — cards cycle through these before graduating to Review
LEARNING_STEPS   = [1, 10]
RELEARNING_STEPS = [10]


# ── Core formulas ─────────────────────────────────────────────────────────────

def retrievability(elapsed_days: float, stability: float) -> float:
    """Probability of recall: R(t,S) = (1 + FACTOR·t/S)^DECAY"""
    if stability <= 0:
        return 0.0
    return (1 + FACTOR * elapsed_days / stability) ** DECAY


def next_interval(stability: float, retention: float = REQUEST_RETENTION) -> int:
    """Optimal review interval in days for target retention."""
    interval = stability / FACTOR * (retention ** (1 / DECAY) - 1)
    return max(1, round(interval))


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def _init_difficulty(rating: Rating, w: list[float] = W) -> float:
    return _clamp(w[4] - w[5] * (rating - 3), 1.0, 10.0)


def _init_stability(rating: Rating, w: list[float] = W) -> float:
    return max(w[rating - 1], 0.1)


def _next_difficulty(d: float, rating: Rating, w: list[float] = W) -> float:
    d_prime = d - w[6] * (rating - 3)
    # mean reversion toward w[4]
    return _clamp(w[4] * w[7] + (1 - w[7]) * d_prime, 1.0, 10.0)


def _next_stability_recall(d: float, s: float, r: float, rating: Rating, w: list[float] = W) -> float:
    hard_penalty = w[15] if rating == Rating.HARD else 1.0
    easy_bonus   = w[16] if rating == Rating.EASY else 1.0
    return s * (
        math.exp(w[8] * (11 - d) * s ** (-w[9]) * (math.exp(w[10] * (1 - r)) - 1))
        * hard_penalty * easy_bonus
        + 1
    )


def _next_stability_forget(d: float, s: float, r: float, w: list[float] = W) -> float:
    return (
        w[11]
        * d ** (-w[12])
        * ((s + 1) ** w[13] - 1)
        * math.exp(w[14] * (1 - r))
    )


# ── Scheduler ─────────────────────────────────────────────────────────────────

class FSRS:
    def __init__(
        self,
        weights: list[float] = W,
        target_retention: float = REQUEST_RETENTION,
    ):
        self.w  = weights
        self.tr = target_retention

    def schedule(self, card: CardState, rating: Rating, now: datetime | None = None) -> ScheduleResult:
        now = now or datetime.now(timezone.utc)

        elapsed_days = 0.0
        if card.last_review:
            elapsed_days = max(0, (now - card.last_review).total_seconds() / 86400)

        r = retrievability(elapsed_days, card.stability) if card.stability > 0 else 0.0

        snapshot = {
            "stability_before":   card.stability,
            "difficulty_before":  card.difficulty,
            "interval_before":    round(elapsed_days),
        }

        new_card = CardState(
            stability=card.stability,
            difficulty=card.difficulty,
            last_review=now,
            reps=card.reps,
            lapses=card.lapses,
            state=card.state,
        )

        w = self.w

        if card.state == State.NEW:
            new_card.stability  = _init_stability(rating, w)
            new_card.difficulty = _init_difficulty(rating, w)

            if rating == Rating.AGAIN:
                new_card.state    = State.LEARNING
                new_card.due_date = now + timedelta(minutes=LEARNING_STEPS[0])
            elif rating == Rating.HARD:
                new_card.state    = State.LEARNING
                new_card.due_date = now + timedelta(minutes=LEARNING_STEPS[0])
            elif rating == Rating.GOOD:
                new_card.state    = State.LEARNING
                new_card.due_date = now + timedelta(minutes=LEARNING_STEPS[-1])
            else:  # EASY
                new_card.state    = State.REVIEW
                new_card.reps    += 1
                new_card.due_date = now + timedelta(days=next_interval(new_card.stability, self.tr))

        elif card.state == State.LEARNING:
            if rating == Rating.AGAIN:
                new_card.due_date = now + timedelta(minutes=LEARNING_STEPS[0])
            elif rating in (Rating.HARD, Rating.GOOD):
                new_card.due_date = now + timedelta(minutes=LEARNING_STEPS[-1])
            else:  # EASY — graduate immediately
                new_card.state    = State.REVIEW
                new_card.reps    += 1
                new_card.due_date = now + timedelta(days=next_interval(new_card.stability, self.tr))

        elif card.state == State.REVIEW:
            new_card.difficulty = _next_difficulty(card.difficulty, rating, w)

            if rating == Rating.AGAIN:
                new_card.stability = _next_stability_forget(card.difficulty, card.stability, r, w)
                new_card.lapses   += 1
                new_card.state     = State.RELEARNING
                new_card.due_date  = now + timedelta(minutes=RELEARNING_STEPS[0])
            else:
                new_card.stability = _next_stability_recall(card.difficulty, card.stability, r, rating, w)
                new_card.reps     += 1
                new_card.due_date  = now + timedelta(days=next_interval(new_card.stability, self.tr))

        elif card.state == State.RELEARNING:
            if rating == Rating.AGAIN:
                new_card.due_date = now + timedelta(minutes=RELEARNING_STEPS[0])
            else:
                new_card.stability = _next_stability_recall(card.difficulty, card.stability, r, rating, w)
                new_card.state     = State.REVIEW
                new_card.reps     += 1
                new_card.due_date  = now + timedelta(days=next_interval(new_card.stability, self.tr))

        return ScheduleResult(card=new_card, review_log=snapshot)


# Singleton
fsrs = FSRS()
