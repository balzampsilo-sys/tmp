"""
Collect and normalize word lists from open sources:
  - Oxford 3000 / 5000 (scraped from oxfordlearnersdictionaries.com)
  - Academic Word List (AWL)
  - ФИПИ ЕГЭ word list (from fipi.ru PDF)

Output: data/wordlist_raw.csv
  word, cefr_level, pos, source
"""

import csv
import re
import time
import requests
from pathlib import Path
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).parent / "data"
DATA_DIR.mkdir(exist_ok=True)

OUTPUT = DATA_DIR / "wordlist_raw.csv"

# ── AWL (Academic Word List) ──────────────────────────────────────────────────
# Source: https://www.wgtn.ac.nz/lals/resources/academicwordlist/publications
# Sublist 1-10, ~570 head words, mapped to B2-C1

AWL_URL = "https://www.wgtn.ac.nz/lals/resources/academicwordlist/information/academic-word-list"

def fetch_awl() -> list[dict]:
    """Parse AWL from Victoria University page."""
    print("Fetching AWL...")
    resp = requests.get(AWL_URL, timeout=30)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    words = []
    # AWL sublists 1-5 → B2, sublists 6-10 → C1
    for tag in soup.find_all(["p", "li"]):
        text = tag.get_text(separator=" ")
        # words are plain lowercase tokens
        tokens = re.findall(r"\b[a-z]{3,}\b", text)
        for w in tokens:
            level = "B2"  # default; sublists 6-10 could be C1 but hard to split without structured data
            words.append({"word": w, "cefr_level": level, "pos": "", "source": "awl"})

    print(f"  AWL: {len(words)} entries (raw, needs dedup)")
    return words


# ── Oxford 3000 / 5000 ────────────────────────────────────────────────────────
# The Oxford lists are available as downloadable PDFs on the Oxford Learner's
# Dictionaries site. We parse the public HTML word list pages.

OXFORD_URLS = {
    "oxford3000": "https://www.oxfordlearnersdictionaries.com/wordlists/oxford3000-5000",
}

# Fallback: use a community-maintained CSV mirror on GitHub (CC0)
OXFORD_GITHUB_CSV = (
    "https://raw.githubusercontent.com/IlyaSemenov/oxford-dictionary/master/"
    "oxford-3000.txt"
)

OXFORD_LEVEL_MAP = {
    "a1": "A1", "a2": "A2", "b1": "B1", "b2": "B2", "c1": "C1",
}

def fetch_oxford_github() -> list[dict]:
    """
    Fallback: plain word list from community mirror.
    Format: one word per line, optionally: word TAB level TAB pos
    """
    print("Fetching Oxford 3000 from community mirror...")
    resp = requests.get(OXFORD_GITHUB_CSV, timeout=30)
    resp.raise_for_status()

    words = []
    for line in resp.text.splitlines():
        parts = line.strip().split("\t")
        word = parts[0].strip().lower()
        if not word or not word.isalpha():
            continue
        level = OXFORD_LEVEL_MAP.get(parts[1].strip().lower(), "B1") if len(parts) > 1 else "B1"
        pos   = parts[2].strip() if len(parts) > 2 else ""
        words.append({"word": word, "cefr_level": level, "pos": pos, "source": "oxford3000"})

    print(f"  Oxford 3000: {len(words)} entries")
    return words


def fetch_oxford_scrape() -> list[dict]:
    """
    Scrape Oxford Learner's Dictionaries word list page.
    The page renders lists with data-ox3000 / data-ox5000 / data-cefr attributes.
    """
    print("Scraping Oxford word lists...")
    headers = {"User-Agent": "Mozilla/5.0 (research bot; contact: research@example.com)"}
    words = []

    for page in range(1, 30):  # paginated, stop when empty
        url = f"https://www.oxfordlearnersdictionaries.com/wordlists/oxford3000-5000?page={page}"
        try:
            resp = requests.get(url, headers=headers, timeout=20)
            if resp.status_code == 404:
                break
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")

            entries = soup.select("[data-cefr]")
            if not entries:
                break

            for el in entries:
                word  = el.get_text(strip=True).lower()
                level = OXFORD_LEVEL_MAP.get(el.get("data-cefr", "").lower(), "B1")
                pos   = el.get("data-pos", "")
                src   = "oxford5000" if el.get("data-ox5000") else "oxford3000"
                words.append({"word": word, "cefr_level": level, "pos": pos, "source": src})

            time.sleep(1)  # polite crawl
        except Exception as e:
            print(f"  page {page} error: {e}")
            break

    print(f"  Oxford scrape: {len(words)} entries")
    return words


# ── ФИПИ ЕГЭ word list ───────────────────────────────────────────────────────
# Official ФИПИ vocabulary list for ЕГЭ по английскому языку.
# Available as PDF at fipi.ru — we use a pre-extracted plain-text mirror.
# Level: B1-B2 (maps to ЕГЭ profile)

FIPI_URL = (
    "https://raw.githubusercontent.com/nicholasgasior/ege-wordlist/main/ege_english.txt"
)

def fetch_fipi() -> list[dict]:
    """Load ЕГЭ ФИПИ word list from text mirror."""
    print("Fetching ФИПИ ЕГЭ word list...")
    try:
        resp = requests.get(FIPI_URL, timeout=20)
        resp.raise_for_status()
        words = []
        for line in resp.text.splitlines():
            word = line.strip().lower()
            if word and re.match(r"^[a-z '/-]+$", word):
                words.append({"word": word, "cefr_level": "B1", "pos": "", "source": "fipi_ege"})
        print(f"  ФИПИ: {len(words)} entries")
        return words
    except Exception as e:
        print(f"  ФИПИ fetch failed: {e}. Skipping.")
        return []


# ── Merge & deduplicate ───────────────────────────────────────────────────────

LEVEL_ORDER = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}

def merge(lists: list[list[dict]]) -> list[dict]:
    """
    Merge word lists. For duplicates, keep highest CEFR level and union sources.
    """
    seen: dict[str, dict] = {}
    for lst in lists:
        for entry in lst:
            w = entry["word"].strip().lower()
            if not w:
                continue
            if w not in seen:
                seen[w] = {**entry, "word": w, "sources": [entry["source"]]}
            else:
                existing = seen[w]
                # keep the higher CEFR level
                if LEVEL_ORDER.get(entry["cefr_level"], 0) > LEVEL_ORDER.get(existing["cefr_level"], 0):
                    existing["cefr_level"] = entry["cefr_level"]
                if entry["source"] not in existing["sources"]:
                    existing["sources"].append(entry["source"])
                if not existing["pos"] and entry["pos"]:
                    existing["pos"] = entry["pos"]

    result = list(seen.values())
    for r in result:
        r["source"] = ",".join(r.pop("sources"))
    return result


def save(words: list[dict]) -> None:
    fieldnames = ["word", "cefr_level", "pos", "source"]
    with open(OUTPUT, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(words)
    print(f"\nSaved {len(words)} unique words → {OUTPUT}")


# ── Stats ─────────────────────────────────────────────────────────────────────

def print_stats(words: list[dict]) -> None:
    from collections import Counter
    levels = Counter(w["cefr_level"] for w in words)
    print("\nWords by CEFR level:")
    for lvl in ["A1", "A2", "B1", "B2", "C1", "C2"]:
        bar = "█" * (levels[lvl] // 20)
        print(f"  {lvl}: {levels[lvl]:>5}  {bar}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    lists = []

    # Try scraping Oxford first, fall back to GitHub mirror
    oxford = fetch_oxford_scrape()
    if len(oxford) < 100:
        oxford = fetch_oxford_github()
    lists.append(oxford)

    lists.append(fetch_awl())
    lists.append(fetch_fipi())

    merged = merge(lists)
    print_stats(merged)
    save(merged)


if __name__ == "__main__":
    main()
