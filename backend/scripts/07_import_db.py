"""
Import validated word list into PostgreSQL.

Creates:
  - platform tenant (slug="platform")
  - one deck per CEFR level
  - all cards linked to those decks

Input:  data/wordlist_with_audio.jsonl
Env:    DATABASE_URL=postgresql://user:pass@host:5432/srs
"""

import json
import logging
import os
import uuid
from pathlib import Path

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
INPUT    = DATA_DIR / "wordlist_with_audio.jsonl"

DATABASE_URL = os.environ["DATABASE_URL"]

PLATFORM_TENANT_SLUG = "platform"
PLATFORM_TENANT_NAME = "Платформа"

DECK_META = {
    "A1": {"name": "English A1 — Beginner",          "description": "Базовый словарь: числа, цвета, простые глаголы. ~500 слов"},
    "A2": {"name": "English A2 — Elementary",         "description": "Повседневная лексика, Past Simple. ~500 слов"},
    "B1": {"name": "English B1 — Intermediate / ЕГЭ","description": "Oxford 2000, ЕГЭ словник ФИПИ, Conditionals. ~800 слов"},
    "B2": {"name": "English B2 — Upper / FCE",        "description": "Oxford 3000, Phrasal verbs, FCE patterns. ~1000 слов"},
    "C1": {"name": "English C1 — Advanced / CAE",     "description": "Academic Word List, IELTS vocabulary. ~1200 слов"},
    "C2": {"name": "English C2 — Mastery / CPE",      "description": "Sophisticated vocabulary, literary expressions. ~800 слов"},
}


def get_or_create_tenant(cur) -> str:
    cur.execute("SELECT id FROM tenants WHERE slug = %s", (PLATFORM_TENANT_SLUG,))
    row = cur.fetchone()
    if row:
        return row["id"]

    tid = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO tenants (id, slug, name) VALUES (%s, %s, %s)",
        (tid, PLATFORM_TENANT_SLUG, PLATFORM_TENANT_NAME),
    )
    log.info(f"Created platform tenant: {tid}")
    return tid


def get_or_create_decks(cur, tenant_id: str) -> dict[str, str]:
    decks = {}
    for level, meta in DECK_META.items():
        cur.execute(
            "SELECT id FROM decks WHERE tenant_id = %s AND cefr_level = %s AND source = 'platform'",
            (tenant_id, level),
        )
        row = cur.fetchone()
        if row:
            decks[level] = row["id"]
        else:
            did = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO decks (id, tenant_id, source, name, description,
                                   language, cefr_level, is_public)
                VALUES (%s, %s, 'platform', %s, %s, 'en', %s, TRUE)
                """,
                (did, tenant_id, meta["name"], meta["description"], level),
            )
            decks[level] = did
            log.info(f"  Created deck {level}: {did}")
    return decks


def import_cards(cur, entries: list[dict], decks: dict[str, str]) -> int:
    imported = 0
    batch    = []

    for entry in entries:
        level   = entry.get("cefr_level", "B1")
        deck_id = decks.get(level)
        if not deck_id:
            log.warning(f"No deck for level {level}, skipping {entry['word']}")
            continue

        translations = entry.get("translations_ru", [])
        back = ", ".join(translations) if translations else entry["word"]

        examples = entry.get("examples", [])
        # strip 'score' field if present (from pipeline)
        clean_examples = [
            {k: v for k, v in ex.items() if k in ("en", "ru", "source")}
            for ex in examples
        ]

        synonyms   = entry.get("synonyms", []) or []
        word_forms = entry.get("word_forms", []) or []

        metadata = {
            "sources":     entry.get("source", ""),
            "definitions": entry.get("definitions_en", []),
            "ai_filled":   entry.get("ai_filled", False),
        }

        batch.append((
            str(uuid.uuid4()),       # id
            deck_id,                 # deck_id
            "basic",                 # card_type
            entry["word"],           # front
            back,                    # back
            entry.get("ipa", ""),    # ipa
            entry.get("pos", ""),    # pos
            level,                   # cefr_level
            json.dumps(clean_examples, ensure_ascii=False),  # examples
            synonyms,                # synonyms
            word_forms,              # word_forms
            entry.get("audio_url", ""),  # audio_url
            entry.get("tags", []),   # tags
            json.dumps(metadata, ensure_ascii=False),  # metadata
        ))

        if len(batch) >= 500:
            _flush(cur, batch)
            imported += len(batch)
            batch = []
            log.info(f"  Imported {imported} cards...")

    if batch:
        _flush(cur, batch)
        imported += len(batch)

    return imported


def _flush(cur, batch: list) -> None:
    psycopg2.extras.execute_values(
        cur,
        """
        INSERT INTO cards
            (id, deck_id, card_type, front, back, ipa, pos, cefr_level,
             examples, synonyms, word_forms, audio_url, tags, metadata)
        VALUES %s
        ON CONFLICT DO NOTHING
        """,
        batch,
        template=(
            "(%s, %s, %s, %s, %s, %s, %s, %s, "
            "%s::jsonb, %s, %s, %s, %s, %s::jsonb)"
        ),
    )


def main():
    if not INPUT.exists():
        raise FileNotFoundError(f"{INPUT} — run previous pipeline steps first")

    with open(INPUT, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f]
    log.info(f"Entries to import: {len(entries)}")

    conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = False

    try:
        with conn.cursor() as cur:
            tenant_id = get_or_create_tenant(cur)
            decks     = get_or_create_decks(cur, tenant_id)
            imported  = import_cards(cur, entries, decks)

        conn.commit()
        log.info(f"\n✓ Import complete. Cards imported: {imported}")

        # Print deck summaries
        with conn.cursor() as cur:
            cur.execute(
                "SELECT cefr_level, name, card_count FROM decks "
                "WHERE tenant_id = %s ORDER BY cefr_level",
                (tenant_id,),
            )
            print("\nDeck summary:")
            for row in cur.fetchall():
                print(f"  {row['cefr_level']}: {row['card_count']:>5} cards  — {row['name']}")

    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


if __name__ == "__main__":
    main()
