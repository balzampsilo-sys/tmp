"""
Match words to example sentences from Tatoeba corpus.

Tatoeba download: https://tatoeba.org/downloads
Files needed (place in data/tatoeba/):
  - sentences.csv      — id TAB lang TAB text
  - links.csv          — id TAB translation_id

We build an index: English sentences that contain our target words,
then find their Russian translations via links.csv.

Input:  data/wordlist_enriched.jsonl
        data/tatoeba/sentences.csv (download separately, ~2GB)
        data/tatoeba/links.csv
Output: data/wordlist_with_examples.jsonl
"""

import csv
import json
import re
import logging
from collections import defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR  = Path(__file__).parent / "data"
TATOEBA   = DATA_DIR / "tatoeba"
INPUT     = DATA_DIR / "wordlist_enriched.jsonl"
OUTPUT    = DATA_DIR / "wordlist_with_examples.jsonl"

SENTENCES_CSV = TATOEBA / "sentences.csv"
LINKS_CSV     = TATOEBA / "links.csv"

MAX_EXAMPLES_PER_WORD = 3
# prefer shorter sentences (more suitable for cards)
MAX_SENTENCE_LEN = 120
MIN_SENTENCE_LEN = 15


def load_words(path: Path) -> dict[str, dict]:
    words = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            words[entry["word"]] = entry
    return words


def load_sentences(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """
    Returns:
      en_sentences: {sentence_id: text}
      ru_sentences: {sentence_id: text}
    """
    log.info("Loading Tatoeba sentences (this may take a minute)...")
    en, ru = {}, {}
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) < 3:
                continue
            sid, lang, text = row[0], row[1], row[2]
            if lang == "eng":
                en[sid] = text
            elif lang == "rus":
                ru[sid] = text
    log.info(f"  EN: {len(en):,}  RU: {len(ru):,}")
    return en, ru


def load_links(path: Path) -> dict[str, list[str]]:
    """Returns {sentence_id: [translation_ids]}."""
    log.info("Loading Tatoeba links...")
    links: dict[str, list[str]] = defaultdict(list)
    with open(path, encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t")
        for row in reader:
            if len(row) >= 2:
                links[row[0]].append(row[1])
    log.info(f"  Links: {sum(len(v) for v in links.values()):,}")
    return links


def build_word_index(
    words: dict[str, dict],
    en_sentences: dict[str, str],
) -> dict[str, list[str]]:
    """
    Index: word → list of EN sentence IDs that contain the word.
    Uses whole-word matching to avoid substring hits (e.g. "age" in "stage").
    """
    log.info("Building word → sentence index...")
    # compile patterns once
    patterns = {
        w: re.compile(r"\b" + re.escape(w) + r"\b", re.IGNORECASE)
        for w in words
    }

    index: dict[str, list[str]] = defaultdict(list)
    for sid, text in en_sentences.items():
        if not (MIN_SENTENCE_LEN <= len(text) <= MAX_SENTENCE_LEN):
            continue
        for word, pattern in patterns.items():
            if pattern.search(text):
                index[word].append(sid)

    found = sum(1 for v in index.values() if v)
    log.info(f"  Words with ≥1 example: {found}/{len(words)}")
    return index


def pick_examples(
    word: str,
    sentence_ids: list[str],
    en_sentences: dict[str, str],
    ru_sentences: dict[str, str],
    links: dict[str, list[str]],
) -> list[dict]:
    """Pick up to MAX_EXAMPLES_PER_WORD best EN↔RU sentence pairs."""
    candidates = []
    for sid in sentence_ids:
        en_text = en_sentences.get(sid, "")
        # find a Russian translation
        for trans_id in links.get(sid, []):
            ru_text = ru_sentences.get(trans_id)
            if ru_text:
                candidates.append({
                    "en": en_text,
                    "ru": ru_text,
                    "source": "tatoeba",
                    "score": len(en_text),  # shorter = better
                })
                break

    # sort by sentence length (shorter first) and return top N
    candidates.sort(key=lambda x: x["score"])
    for c in candidates:
        del c["score"]
    return candidates[:MAX_EXAMPLES_PER_WORD]


def check_tatoeba_available() -> bool:
    if not SENTENCES_CSV.exists() or not LINKS_CSV.exists():
        log.warning(
            "Tatoeba files not found. Download from https://tatoeba.org/downloads\n"
            f"  Expected:\n  {SENTENCES_CSV}\n  {LINKS_CSV}\n"
            "Skipping example matching — words will get examples via AI fallback (script 04)."
        )
        return False
    return True


def main():
    if not INPUT.exists():
        raise FileNotFoundError(f"{INPUT} — run 02_enrich_wiktionary.py first")

    words = load_words(INPUT)
    log.info(f"Words to process: {len(words)}")

    if not check_tatoeba_available():
        # copy input to output unchanged; script 04 will fill examples
        import shutil
        shutil.copy(INPUT, OUTPUT)
        log.info(f"Copied {INPUT} → {OUTPUT} (no examples added)")
        return

    en_sentences, ru_sentences = load_sentences(SENTENCES_CSV)
    links                      = load_links(LINKS_CSV)
    index                      = build_word_index(words, en_sentences)

    log.info("Matching examples...")
    matched = 0
    with open(OUTPUT, "w", encoding="utf-8") as out:
        for word, entry in words.items():
            sentence_ids = index.get(word, [])
            examples = pick_examples(word, sentence_ids, en_sentences, ru_sentences, links)
            entry["examples"] = examples
            if examples:
                matched += 1
            out.write(json.dumps(entry, ensure_ascii=False) + "\n")

    coverage = matched / len(words) * 100
    log.info(f"\nDone. Examples found: {matched}/{len(words)} ({coverage:.1f}%)")
    log.info(f"Words without examples → will use AI fallback (script 04)")
    log.info(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
