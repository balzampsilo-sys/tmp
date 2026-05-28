import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..auth import CurrentUser, get_current_user
from ..database import get_conn
from ..models import DeckCreateRequest, DeckOut

router = APIRouter(prefix="/decks", tags=["decks"])


@router.get("", response_model=list[DeckOut])
async def list_decks(
    level: str | None = Query(None, pattern="^(A1|A2|B1|B2|C1|C2)$"),
    source: str | None = Query(None, pattern="^(platform|tenant|personal)$"),
    current: CurrentUser = Depends(get_current_user),
):
    """
    List decks visible to the current user:
      - all platform decks (is_public=true)
      - tenant decks for tenants the user belongs to
      - user's own personal decks
    Annotates each deck with `enrolled` flag.
    """
    async with get_conn() as conn:
        rows = await conn.fetch(
            """
            SELECT d.id, d.name, d.description, d.cefr_level, d.tags,
                   d.card_count, d.source, d.is_public,
                   (de.user_id IS NOT NULL) AS enrolled
            FROM decks d
            LEFT JOIN deck_enrollments de
                   ON de.deck_id = d.id AND de.user_id = $1
            WHERE
                -- platform public decks
                (d.source = 'platform' AND d.is_public = TRUE)
                OR
                -- tenant decks for user's tenants
                (d.source = 'tenant' AND d.tenant_id IN (
                    SELECT tenant_id FROM user_tenants WHERE user_id = $1
                ))
                OR
                -- personal decks
                (d.source = 'personal' AND d.owner_id = $1)
            AND ($2::text IS NULL OR d.cefr_level = $2)
            AND ($3::text IS NULL OR d.source = $3)
            ORDER BY d.cefr_level NULLS LAST, d.name
            """,
            current.user_id, level, source,
        )
    return [DeckOut(**dict(r)) for r in rows]


@router.get("/{deck_id}", response_model=DeckOut)
async def get_deck(
    deck_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
):
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            SELECT d.id, d.name, d.description, d.cefr_level, d.tags,
                   d.card_count, d.source, d.is_public,
                   (de.user_id IS NOT NULL) AS enrolled
            FROM decks d
            LEFT JOIN deck_enrollments de
                   ON de.deck_id = d.id AND de.user_id = $1
            WHERE d.id = $2
            """,
            current.user_id, str(deck_id),
        )
    if not row:
        raise HTTPException(status_code=404, detail="Deck not found")
    return DeckOut(**dict(row))


@router.post("/{deck_id}/enroll", status_code=status.HTTP_204_NO_CONTENT)
async def enroll(
    deck_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
):
    """Subscribe user to a deck. Creates user_cards rows for all cards (state=new)."""
    async with get_conn() as conn:
        # Verify deck exists and is accessible
        deck = await conn.fetchrow(
            "SELECT id, card_count FROM decks WHERE id = $1 AND is_public = TRUE",
            str(deck_id),
        )
        if not deck:
            raise HTTPException(status_code=404, detail="Deck not found or not accessible")

        async with conn.transaction():
            await conn.execute(
                """
                INSERT INTO deck_enrollments (user_id, deck_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                """,
                current.user_id, str(deck_id),
            )
            # Bulk-create user_cards for all cards in the deck (state = new)
            await conn.execute(
                """
                INSERT INTO user_cards (user_id, card_id)
                SELECT $1, id FROM cards WHERE deck_id = $2
                ON CONFLICT DO NOTHING
                """,
                current.user_id, str(deck_id),
            )


@router.delete("/{deck_id}/enroll", status_code=status.HTTP_204_NO_CONTENT)
async def unenroll(
    deck_id: uuid.UUID,
    current: CurrentUser = Depends(get_current_user),
):
    async with get_conn() as conn:
        async with conn.transaction():
            await conn.execute(
                "DELETE FROM deck_enrollments WHERE user_id = $1 AND deck_id = $2",
                current.user_id, str(deck_id),
            )
            await conn.execute(
                """
                DELETE FROM user_cards
                WHERE user_id = $1
                  AND card_id IN (SELECT id FROM cards WHERE deck_id = $2)
                """,
                current.user_id, str(deck_id),
            )


@router.post("", response_model=DeckOut, status_code=status.HTTP_201_CREATED)
async def create_deck(
    body: DeckCreateRequest,
    current: CurrentUser = Depends(get_current_user),
):
    """Create a personal deck (source=personal)."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO decks
                (id, owner_id, source, name, description, cefr_level, tags, is_public)
            VALUES ($1, $2, 'personal', $3, $4, $5, $6, $7)
            RETURNING id, name, description, cefr_level, tags, card_count, source, is_public
            """,
            str(uuid.uuid4()), current.user_id,
            body.name, body.description, body.cefr_level, body.tags, body.is_public,
        )
    return DeckOut(**dict(row), enrolled=True)
