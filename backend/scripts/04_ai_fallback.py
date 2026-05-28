"""
AI fallback via Claude API.

For words missing translation or examples after Wiktionary + Tatoeba passes,
use Claude to generate them in batch.

Input:  data/wordlist_with_examples.jsonl
Output: data/wordlist_final.jsonl
"""

import json
import logging
import time
from pathlib import Path

import anthropic

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
INPUT    = DATA_DIR / "wordlist_with_examples.jsonl"
OUTPUT   = DATA_DIR / "wordlist_final.jsonl"

BATCH_SIZE  = 20   # words per Claude call
RATE_DELAY  = 0.5  # seconds between calls

client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env


def needs_fill(entry: dict) -> bool:
    missing_translation = not entry.get("translations_ru")
    missing_example     = not entry.get("examples")
    return missing_translation or missing_example


SYSTEM_PROMPT = """\
You are a dictionary assistant. Given a list of English words with their CEFR levels,
return a JSON array with one object per word.

Each object must have:
  "word":             string (same as input)
  "translations_ru":  array of 1-3 Russian translations (most common first)
  "example_en":       one clear example sentence using the word (length 10-25 words)
  "example_ru":       Russian translation of that sentence

Rules:
- Translations must be accurate modern Russian, not archaic
- Example sentences must match the CEFR level (simpler for A1-A2, more complex for C1-C2)
- Return ONLY valid JSON, no markdown, no explanation
"""


def build_prompt(batch: list[dict]) -> str:
    items = [
        {"word": e["word"], "level": e["cefr_level"], "pos": e.get("pos", "")}
        for e in batch
    ]
    return json.dumps(items, ensure_ascii=False)


def call_claude(batch: list[dict]) -> list[dict]:
    prompt = build_prompt(batch)
    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = message.content[0].text.strip()
    # strip possible markdown code fences
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1].rsplit("```", 1)[0]
    return json.loads(raw)


def apply_ai_results(entry: dict, ai: dict) -> dict:
    if not entry.get("translations_ru") and ai.get("translations_ru"):
        entry["translations_ru"] = ai["translations_ru"]

    if not entry.get("examples") and ai.get("example_en"):
        entry["examples"] = [{
            "en":     ai["example_en"],
            "ru":     ai.get("example_ru", ""),
            "source": "claude",
        }]

    entry["ai_filled"] = True
    return entry


def load_done() -> set[str]:
    done = set()
    if OUTPUT.exists():
        with open(OUTPUT, encoding="utf-8") as f:
            for line in f:
                try:
                    done.add(json.loads(line)["word"])
                except Exception:
                    pass
    return done


def main():
    if not INPUT.exists():
        raise FileNotFoundError(f"{INPUT} — run 03_match_tatoeba.py first")

    with open(INPUT, encoding="utf-8") as f:
        all_entries = [json.loads(line) for line in f]

    done = load_done()
    log.info(f"Total entries: {len(all_entries)}, already done: {len(done)}")

    # Split into: needs AI fill vs already complete
    need_ai  = [e for e in all_entries if e["word"] not in done and needs_fill(e)]
    passthru = [e for e in all_entries if e["word"] not in done and not needs_fill(e)]

    log.info(f"Needs AI: {len(need_ai)}, pass-through: {len(passthru)}")

    out = open(OUTPUT, "a", encoding="utf-8")

    # Write pass-through entries immediately
    for entry in passthru:
        out.write(json.dumps(entry, ensure_ascii=False) + "\n")
    out.flush()
    log.info(f"Wrote {len(passthru)} pass-through entries")

    # Process AI batches
    total_batches = (len(need_ai) + BATCH_SIZE - 1) // BATCH_SIZE
    filled = 0
    errors = 0

    for batch_num, i in enumerate(range(0, len(need_ai), BATCH_SIZE), 1):
        batch = need_ai[i : i + BATCH_SIZE]
        log.info(f"Batch {batch_num}/{total_batches} ({len(batch)} words)...")

        try:
            ai_results = call_claude(batch)
            ai_by_word = {r["word"]: r for r in ai_results}

            for entry in batch:
                ai_data = ai_by_word.get(entry["word"], {})
                enriched = apply_ai_results(entry, ai_data)
                out.write(json.dumps(enriched, ensure_ascii=False) + "\n")
                filled += 1

            out.flush()
        except Exception as e:
            log.error(f"Batch {batch_num} failed: {e}")
            # write originals without fill
            for entry in batch:
                out.write(json.dumps(entry, ensure_ascii=False) + "\n")
            errors += len(batch)

        time.sleep(RATE_DELAY)

    out.close()
    log.info(f"\nDone. AI-filled: {filled}, errors: {errors}")
    log.info(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
