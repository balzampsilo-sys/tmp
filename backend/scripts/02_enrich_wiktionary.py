"""
Enrich word list via Wiktionary REST API.

Input:  data/wordlist_raw.csv
Output: data/wordlist_enriched.jsonl

For each word fetches:
  - IPA transcription
  - Russian translation(s)
  - Part of speech
  - Word forms (verb conjugations, noun plurals)
"""

import csv
import json
import time
import logging
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
INPUT    = DATA_DIR / "wordlist_raw.csv"
OUTPUT   = DATA_DIR / "wordlist_enriched.jsonl"
ERRORS   = DATA_DIR / "wiktionary_errors.txt"

# Wiktionary REST API (no key needed, rate limit ~200 req/s)
WIKI_API = "https://en.wiktionary.org/api/rest_v1/page/definition/{word}"

# polite: 10 req/s
REQUEST_DELAY = 0.1


def make_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503])
    session.mount("https://", HTTPAdapter(max_retries=retry))
    session.headers["User-Agent"] = "srs-platform/1.0 (educational; balzampsilo@gmail.com)"
    return session


def fetch_wiktionary(session: requests.Session, word: str) -> dict | None:
    url = WIKI_API.format(word=requests.utils.quote(word))
    try:
        resp = session.get(url, timeout=15)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        log.warning(f"  {word}: {e}")
        return None


def extract_ipa(data: dict) -> str:
    """Pull first IPA pronunciation from Wiktionary response."""
    for lang_entries in data.values():
        for entry in lang_entries:
            for pron in entry.get("pronunciations", []):
                ipa = pron.get("ipa", "")
                if ipa:
                    # strip /.../ or [...] wrappers
                    return ipa.strip("/[] ")
    return ""


def extract_pos(data: dict) -> str:
    """Return the first part-of-speech found for English entries."""
    for entry in data.get("en", []):
        pos = entry.get("partOfSpeech", "")
        if pos:
            return pos.lower()
    return ""


def extract_definitions(data: dict) -> list[str]:
    """Return English definitions (first 3)."""
    defs = []
    for entry in data.get("en", []):
        for d in entry.get("definitions", [])[:3]:
            text = d.get("definition", "")
            # strip HTML tags
            clean = __import__("re").sub(r"<[^>]+>", "", text).strip()
            if clean:
                defs.append(clean)
    return defs[:3]


def extract_russian(data: dict) -> list[str]:
    """
    Extract Russian translations from the English entry's translations section.
    Wiktionary stores them inside definition objects as links to Russian words.
    We pull from the 'parsedExamples' or look for 'ru' language links.
    """
    translations = []
    for entry in data.get("en", []):
        for d in entry.get("definitions", []):
            for ex in d.get("parsedExamples", []):
                # Sometimes Russian trans is embedded; skip for now
                pass
            # language links in definition text
            import re
            definition_html = d.get("definition", "")
            # Look for Russian words in [[...]] wikilinks tagged with lang=ru
            ru_links = re.findall(r'lang="ru"[^>]*>([^<]+)<', definition_html)
            translations.extend(ru_links)

    return list(dict.fromkeys(translations))[:5]  # dedup, max 5


def extract_forms(data: dict) -> list[str]:
    """Extract inflected forms (plural, past tense, etc.)."""
    forms = []
    for entry in data.get("en", []):
        for d in entry.get("definitions", []):
            import re
            html = d.get("definition", "")
            # forms often appear as ''word'' in definition
            found = re.findall(r"'''([a-z]+)'''", html)
            forms.extend(found)
    return list(dict.fromkeys(forms))[:6]


def enrich_word(session: requests.Session, row: dict) -> dict:
    word = row["word"]
    data = fetch_wiktionary(session, word)

    result = {
        "word":        word,
        "cefr_level":  row["cefr_level"],
        "pos":         row.get("pos", ""),
        "source":      row["source"],
        "ipa":         "",
        "translations_ru": [],
        "definitions_en":  [],
        "word_forms":  [],
        "wiktionary":  bool(data),
    }

    if not data:
        return result

    result["ipa"]             = extract_ipa(data)
    result["definitions_en"]  = extract_definitions(data)
    result["translations_ru"] = extract_russian(data)
    result["word_forms"]      = extract_forms(data)
    if not result["pos"]:
        result["pos"] = extract_pos(data)

    return result


def load_done() -> set[str]:
    """Words already written to output (for resumable runs)."""
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
        raise FileNotFoundError(f"{INPUT} not found — run 01_collect_wordlists.py first")

    with open(INPUT, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    done  = load_done()
    todo  = [r for r in rows if r["word"] not in done]

    log.info(f"Total: {len(rows)}, already done: {len(done)}, todo: {len(todo)}")

    session      = make_session()
    errors       = []
    out_file     = open(OUTPUT, "a", encoding="utf-8")

    try:
        for i, row in enumerate(todo, 1):
            result = enrich_word(session, row)
            out_file.write(json.dumps(result, ensure_ascii=False) + "\n")
            out_file.flush()

            if not result["wiktionary"]:
                errors.append(row["word"])

            if i % 100 == 0:
                hit_rate = (i - len(errors)) / i * 100
                log.info(f"  {i}/{len(todo)}  Wiktionary hit rate: {hit_rate:.1f}%")

            time.sleep(REQUEST_DELAY)
    finally:
        out_file.close()

    with open(ERRORS, "w", encoding="utf-8") as f:
        f.write("\n".join(errors))

    log.info(f"\nDone. Enriched: {len(todo)}  Wiktionary misses: {len(errors)} → {ERRORS}")
    log.info(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
