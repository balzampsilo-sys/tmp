"""Pydantic request/response schemas."""

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, Field


# ── Auth ──────────────────────────────────────────────────────────────────────

class AuthTelegramRequest(BaseModel):
    init_data: str


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: "UserOut"


# ── Users ─────────────────────────────────────────────────────────────────────

class UserOut(BaseModel):
    id: UUID
    telegram_id: int
    username: str | None
    first_name: str | None
    created_at: datetime


class UserTenantOut(BaseModel):
    tenant_id: UUID
    tenant_name: str
    role: str
    sub_status: str
    sub_expires_at: datetime | None


# ── Decks ─────────────────────────────────────────────────────────────────────

class DeckOut(BaseModel):
    id: UUID
    name: str
    description: str | None
    cefr_level: str | None
    tags: list[str]
    card_count: int
    source: str
    is_public: bool
    enrolled: bool = False


class DeckCreateRequest(BaseModel):
    name: str = Field(..., min_length=2, max_length=120)
    description: str | None = None
    cefr_level: str | None = Field(None, pattern="^(A1|A2|B1|B2|C1|C2)$")
    tags: list[str] = []
    is_public: bool = False


# ── Cards ─────────────────────────────────────────────────────────────────────

class ExampleOut(BaseModel):
    en: str
    ru: str
    source: str


class CardOut(BaseModel):
    id: UUID
    deck_id: UUID
    card_type: str
    front: str
    back: str
    ipa: str | None
    pos: str | None
    cefr_level: str | None
    examples: list[ExampleOut]
    synonyms: list[str]
    audio_url: str | None


class DueCardOut(BaseModel):
    """Card served during a study session — includes SRS metadata."""
    id: UUID
    deck_id: UUID
    front: str
    back: str
    ipa: str | None
    pos: str | None
    cefr_level: str | None
    examples: list[ExampleOut]
    synonyms: list[str]
    audio_url: str | None
    # SRS state for the client (for UI hints like "this is your 5th review")
    reps: int
    lapses: int
    state: str


class DueCountOut(BaseModel):
    new: int
    learning: int
    review: int
    total: int


# ── Reviews ───────────────────────────────────────────────────────────────────

class ReviewRequest(BaseModel):
    card_id: UUID
    rating: int = Field(..., ge=1, le=4)  # 1=again 2=hard 3=good 4=easy
    elapsed_ms: int | None = None         # time spent on card


class ReviewResponse(BaseModel):
    card_id: UUID
    next_due: datetime
    new_interval_days: int
    new_stability: float
    new_state: str


# ── Stats ─────────────────────────────────────────────────────────────────────

class StatsOut(BaseModel):
    total_cards_enrolled: int
    cards_mastered: int        # interval > 21 days
    cards_learning: int
    retention_rate: float      # reps / (reps + lapses)
    streak_days: int
    reviews_today: int
    reviews_total: int


class HeatmapEntry(BaseModel):
    date: str           # YYYY-MM-DD
    count: int


class HeatmapOut(BaseModel):
    entries: list[HeatmapEntry]


# ── Placement test ────────────────────────────────────────────────────────────

class PlacementQuestion(BaseModel):
    index: int
    word: str
    options: list[str]          # 4 options, one is correct
    cefr_level: str


class PlacementQuestionsOut(BaseModel):
    questions: list[PlacementQuestion]


class PlacementAnswerIn(BaseModel):
    question_index: int
    chosen_option: str


class PlacementSubmitRequest(BaseModel):
    answers: list[PlacementAnswerIn]


class PlacementResult(BaseModel):
    cefr_level: str
    score: int
    total: int
    unlocked_decks: list[UUID]


# ── AI card generation ────────────────────────────────────────────────────────

class GenerateCardsRequest(BaseModel):
    text: str = Field(..., min_length=50, max_length=5000)
    deck_id: UUID
    max_cards: int = Field(10, ge=1, le=30)


class GeneratedCardOut(BaseModel):
    front: str
    back: str
    example_en: str
    example_ru: str
    level_hint: str | None


class GenerateCardsResponse(BaseModel):
    cards: list[GeneratedCardOut]
