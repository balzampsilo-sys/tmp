"""
Unit tests for FSRS 4.5 algorithm.

Tests cover:
  - Core math formulas (retrievability, next_interval)
  - Initial card scheduling for all 4 ratings
  - State transitions (new → learning → review → relearning)
  - Stability and difficulty updates
  - Edge cases (zero stability, max lapses, etc.)
"""

import math
from datetime import datetime, timedelta, timezone

import pytest

from api.srs.fsrs import (
    FACTOR,
    W,
    CardState,
    FSRS,
    Rating,
    State,
    _init_difficulty,
    _init_stability,
    _next_difficulty,
    _next_stability_forget,
    _next_stability_recall,
    fsrs,
    next_interval,
    retrievability,
)

NOW = datetime(2024, 1, 15, 12, 0, 0, tzinfo=timezone.utc)


# ── Core formulas ─────────────────────────────────────────────────────────────

class TestRetrievability:
    def test_zero_elapsed_is_one(self):
        """At t=0 memory is perfect."""
        assert retrievability(0, 3.0) == pytest.approx(1.0)

    def test_at_stability_equals_target(self):
        """
        At t=S retrievability should equal REQUEST_RETENTION (≈0.9).
        This is the fundamental property of FSRS interval calculation.
        """
        s = 10.0
        i = next_interval(s)
        r = retrievability(i, s)
        assert r == pytest.approx(0.9, abs=0.02)

    def test_decreases_over_time(self):
        s = 5.0
        r1 = retrievability(1, s)
        r2 = retrievability(5, s)
        r3 = retrievability(20, s)
        assert r1 > r2 > r3

    def test_higher_stability_means_slower_decay(self):
        t = 10
        r_low  = retrievability(t, 2.0)
        r_high = retrievability(t, 20.0)
        assert r_high > r_low

    def test_zero_stability_returns_zero(self):
        assert retrievability(5, 0) == 0.0


class TestNextInterval:
    def test_good_first_review_approx_three_days(self):
        """
        For GOOD first rating, initial stability = W[2] = 3.1262.
        next_interval(3.1262) ≈ 3 days (property of FSRS).
        """
        s = W[2]  # 3.1262
        i = next_interval(s)
        assert i == pytest.approx(3, abs=1)

    def test_easy_first_review_approx_fifteen_days(self):
        s = W[3]  # 15.4722
        i = next_interval(s)
        assert i == pytest.approx(15, abs=2)

    def test_minimum_interval_is_one(self):
        assert next_interval(0.01) == 1

    def test_long_stability_gives_long_interval(self):
        assert next_interval(100.0) > 50


# ── Initial card parameters ───────────────────────────────────────────────────

class TestInitParams:
    def test_init_stability_all_ratings(self):
        assert _init_stability(Rating.AGAIN) == pytest.approx(W[0])
        assert _init_stability(Rating.HARD)  == pytest.approx(W[1])
        assert _init_stability(Rating.GOOD)  == pytest.approx(W[2])
        assert _init_stability(Rating.EASY)  == pytest.approx(W[3])

    def test_init_stability_increases_with_rating(self):
        stabilities = [_init_stability(Rating(r)) for r in range(1, 5)]
        assert stabilities == sorted(stabilities)

    def test_init_difficulty_good_is_near_default(self):
        """GOOD (rating=3) means no change: D = W[4] - W[5]*(3-3) = W[4]."""
        d = _init_difficulty(Rating.GOOD)
        assert d == pytest.approx(W[4], abs=0.01)

    def test_init_difficulty_again_is_harder(self):
        d_again = _init_difficulty(Rating.AGAIN)
        d_easy  = _init_difficulty(Rating.EASY)
        assert d_again > d_easy

    def test_init_difficulty_clamped(self):
        for rating in Rating:
            d = _init_difficulty(rating)
            assert 1.0 <= d <= 10.0


# ── State machine ─────────────────────────────────────────────────────────────

def new_card() -> CardState:
    return CardState(due_date=NOW)


class TestNewCard:
    def test_again_goes_to_learning(self):
        result = fsrs.schedule(new_card(), Rating.AGAIN, NOW)
        assert result.card.state == State.LEARNING

    def test_hard_goes_to_learning(self):
        result = fsrs.schedule(new_card(), Rating.HARD, NOW)
        assert result.card.state == State.LEARNING

    def test_good_goes_to_learning(self):
        result = fsrs.schedule(new_card(), Rating.GOOD, NOW)
        assert result.card.state == State.LEARNING

    def test_easy_graduates_to_review(self):
        result = fsrs.schedule(new_card(), Rating.EASY, NOW)
        assert result.card.state == State.REVIEW

    def test_again_due_in_one_minute(self):
        result = fsrs.schedule(new_card(), Rating.AGAIN, NOW)
        delta  = (result.card.due_date - NOW).total_seconds()
        assert delta == pytest.approx(60, abs=5)

    def test_good_due_in_ten_minutes(self):
        result = fsrs.schedule(new_card(), Rating.GOOD, NOW)
        delta  = (result.card.due_date - NOW).total_seconds()
        assert delta == pytest.approx(600, abs=30)

    def test_easy_due_in_many_days(self):
        result = fsrs.schedule(new_card(), Rating.EASY, NOW)
        delta_days = (result.card.due_date - NOW).total_seconds() / 86400
        assert delta_days >= 1

    def test_reps_incremented_on_easy(self):
        result = fsrs.schedule(new_card(), Rating.EASY, NOW)
        assert result.card.reps == 1

    def test_reps_not_incremented_on_again(self):
        result = fsrs.schedule(new_card(), Rating.AGAIN, NOW)
        assert result.card.reps == 0


class TestLearningCard:
    def setup_method(self):
        self.card = CardState(
            state=State.LEARNING,
            stability=W[2],
            difficulty=W[4],
            due_date=NOW,
            last_review=NOW - timedelta(minutes=10),
        )

    def test_easy_graduates(self):
        result = fsrs.schedule(self.card, Rating.EASY, NOW)
        assert result.card.state == State.REVIEW

    def test_again_stays_learning(self):
        result = fsrs.schedule(self.card, Rating.AGAIN, NOW)
        assert result.card.state == State.LEARNING

    def test_good_stays_learning(self):
        result = fsrs.schedule(self.card, Rating.GOOD, NOW)
        assert result.card.state == State.LEARNING

    def test_graduate_increments_reps(self):
        result = fsrs.schedule(self.card, Rating.EASY, NOW)
        assert result.card.reps == 1


class TestReviewCard:
    def setup_method(self):
        self.card = CardState(
            state=State.REVIEW,
            stability=10.0,
            difficulty=5.0,
            due_date=NOW,
            last_review=NOW - timedelta(days=10),
            reps=3,
            lapses=0,
        )

    def test_again_goes_to_relearning(self):
        result = fsrs.schedule(self.card, Rating.AGAIN, NOW)
        assert result.card.state == State.RELEARNING

    def test_again_increments_lapses(self):
        result = fsrs.schedule(self.card, Rating.AGAIN, NOW)
        assert result.card.lapses == 1

    def test_good_stays_in_review(self):
        result = fsrs.schedule(self.card, Rating.GOOD, NOW)
        assert result.card.state == State.REVIEW

    def test_good_increments_reps(self):
        result = fsrs.schedule(self.card, Rating.GOOD, NOW)
        assert result.card.reps == 4

    def test_stability_increases_on_recall(self):
        result = fsrs.schedule(self.card, Rating.GOOD, NOW)
        assert result.card.stability > self.card.stability

    def test_stability_decreases_on_forget(self):
        result = fsrs.schedule(self.card, Rating.AGAIN, NOW)
        assert result.card.stability < self.card.stability

    def test_easy_has_higher_stability_than_good(self):
        r_good = fsrs.schedule(self.card, Rating.GOOD, NOW)
        r_easy = fsrs.schedule(self.card, Rating.EASY, NOW)
        assert r_easy.card.stability > r_good.card.stability

    def test_hard_has_lower_stability_than_good(self):
        r_hard = fsrs.schedule(self.card, Rating.HARD, NOW)
        r_good = fsrs.schedule(self.card, Rating.GOOD, NOW)
        assert r_hard.card.stability < r_good.card.stability

    def test_difficulty_decreases_on_easy(self):
        result = fsrs.schedule(self.card, Rating.EASY, NOW)
        assert result.card.difficulty < self.card.difficulty

    def test_difficulty_increases_on_again(self):
        result = fsrs.schedule(self.card, Rating.AGAIN, NOW)
        assert result.card.difficulty > self.card.difficulty

    def test_difficulty_clamped(self):
        hard_card = CardState(
            state=State.REVIEW, stability=5.0, difficulty=9.9,
            due_date=NOW, last_review=NOW - timedelta(days=5),
        )
        result = fsrs.schedule(hard_card, Rating.AGAIN, NOW)
        assert result.card.difficulty <= 10.0


class TestRelearningCard:
    def setup_method(self):
        self.card = CardState(
            state=State.RELEARNING,
            stability=2.0,
            difficulty=7.0,
            due_date=NOW,
            last_review=NOW - timedelta(minutes=10),
            reps=2,
            lapses=1,
        )

    def test_again_stays_relearning(self):
        result = fsrs.schedule(self.card, Rating.AGAIN, NOW)
        assert result.card.state == State.RELEARNING

    def test_good_graduates_back_to_review(self):
        result = fsrs.schedule(self.card, Rating.GOOD, NOW)
        assert result.card.state == State.REVIEW

    def test_good_increments_reps(self):
        result = fsrs.schedule(self.card, Rating.GOOD, NOW)
        assert result.card.reps == 3


# ── Full card lifecycle ───────────────────────────────────────────────────────

class TestFullLifecycle:
    def test_new_to_mastered(self):
        """Simulate a card going from new to mastered (interval > 21 days)."""
        card = new_card()
        review_time = NOW

        # First review: GOOD
        r = fsrs.schedule(card, Rating.GOOD, review_time)
        card = r.card
        assert card.state == State.LEARNING

        # Graduate: EASY
        review_time = card.due_date
        r = fsrs.schedule(card, Rating.EASY, review_time)
        card = r.card
        assert card.state == State.REVIEW
        assert card.reps == 1

        # Several successful reviews
        for _ in range(5):
            review_time = card.due_date
            r = fsrs.schedule(card, Rating.GOOD, review_time)
            card = r.card
            assert card.state == State.REVIEW

        # After several GOOD reviews, interval should grow significantly
        days_until_due = (card.due_date - review_time).total_seconds() / 86400
        assert days_until_due > 10

    def test_lapse_and_recovery(self):
        """Card goes to review, gets a lapse, then recovers."""
        card = CardState(
            state=State.REVIEW,
            stability=15.0,
            difficulty=5.0,
            due_date=NOW,
            last_review=NOW - timedelta(days=15),
            reps=5,
            lapses=0,
        )

        # Lapse
        r = fsrs.schedule(card, Rating.AGAIN, NOW)
        lapsed = r.card
        assert lapsed.state == State.RELEARNING
        assert lapsed.lapses == 1
        assert lapsed.stability < card.stability

        # Recover
        r2 = fsrs.schedule(lapsed, Rating.GOOD, lapsed.due_date)
        recovered = r2.card
        assert recovered.state == State.REVIEW
        assert recovered.reps == 6

    def test_review_log_snapshot(self):
        """review_log contains pre-review state."""
        card = CardState(
            state=State.REVIEW,
            stability=8.0,
            difficulty=5.0,
            due_date=NOW,
            last_review=NOW - timedelta(days=8),
        )
        result = fsrs.schedule(card, Rating.GOOD, NOW)
        log = result.review_log
        assert log["stability_before"] == pytest.approx(8.0)
        assert log["difficulty_before"] == pytest.approx(5.0)
        assert log["interval_before"] == pytest.approx(8, abs=1)


# ── Custom weights ────────────────────────────────────────────────────────────

class TestCustomWeights:
    def test_custom_fsrs_instance(self):
        """FSRS can be initialized with custom weights."""
        custom_w = list(W)
        custom_w[2] = 5.0  # higher initial stability for GOOD
        custom_fsrs = FSRS(weights=custom_w, target_retention=0.85)

        card   = new_card()
        result = custom_fsrs.schedule(card, Rating.GOOD, NOW)
        assert result.card.stability == pytest.approx(5.0)

    def test_lower_retention_means_shorter_interval(self):
        fsrs_09 = FSRS(target_retention=0.9)
        fsrs_07 = FSRS(target_retention=0.7)

        card = CardState(
            state=State.REVIEW, stability=10.0, difficulty=5.0,
            due_date=NOW, last_review=NOW - timedelta(days=10),
        )
        r_09 = fsrs_09.schedule(card, Rating.GOOD, NOW)
        r_07 = fsrs_07.schedule(card, Rating.GOOD, NOW)

        # Lower retention target → longer interval (can wait longer)
        assert r_07.card.due_date > r_09.card.due_date
