"""
Validate final word list before DB import.

Checks:
  - All required fields present
  - Translations not empty
  - At least one example per word
  - CEFR level valid
  - No duplicate words

Prints a report and writes data/validation_report.json.
"""

import json
import logging
from collections import Counter, defaultdict
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
INPUT    = DATA_DIR / "wordlist_with_audio.jsonl"
REPORT   = DATA_DIR / "validation_report.json"

VALID_LEVELS = {"A1", "A2", "B1", "B2", "C1", "C2"}
REQUIRED     = {"word", "cefr_level", "translations_ru", "examples"}


def validate(entries: list[dict]) -> dict:
    issues: dict[str, list[str]] = defaultdict(list)
    seen_words: dict[str, int] = {}
    stats = Counter()

    for i, e in enumerate(entries):
        word = e.get("word", f"[row {i}]")

        # duplicate check
        if word in seen_words:
            issues["duplicates"].append(f"{word} (rows {seen_words[word]} and {i})")
        seen_words[word] = i

        # required fields
        for field in REQUIRED:
            if field not in e or e[field] is None:
                issues["missing_field"].append(f"{word}: missing {field}")

        # CEFR level
        if e.get("cefr_level") not in VALID_LEVELS:
            issues["bad_level"].append(f"{word}: '{e.get('cefr_level')}'")

        # translations
        if not e.get("translations_ru"):
            issues["no_translation"].append(word)
        else:
            stats["has_translation"] += 1

        # examples
        if not e.get("examples"):
            issues["no_example"].append(word)
        else:
            stats["has_example"] += 1

        # audio
        if e.get("audio_url"):
            stats["has_audio"] += 1

        stats["total"] += 1
        stats[f"level_{e.get('cefr_level', '??')}"] += 1

    return {"issues": dict(issues), "stats": dict(stats)}


def print_report(report: dict, total: int) -> None:
    stats  = report["stats"]
    issues = report["issues"]

    print("\n" + "═" * 50)
    print("  VALIDATION REPORT")
    print("═" * 50)
    print(f"\nTotal words: {total}")

    print("\nBy CEFR level:")
    for lvl in ["A1", "A2", "B1", "B2", "C1", "C2"]:
        n   = stats.get(f"level_{lvl}", 0)
        bar = "█" * (n // 15)
        print(f"  {lvl}: {n:>5}  {bar}")

    print("\nCoverage:")
    for key, label in [
        ("has_translation", "Has RU translation"),
        ("has_example",     "Has example sentence"),
        ("has_audio",       "Has audio"),
    ]:
        n   = stats.get(key, 0)
        pct = n / total * 100 if total else 0
        print(f"  {label:<25} {n:>5} / {total}  ({pct:.1f}%)")

    print("\nIssues:")
    if not any(issues.values()):
        print("  ✓ No issues found")
    else:
        for category, items in issues.items():
            if items:
                print(f"  {category}: {len(items)}")
                for item in items[:5]:
                    print(f"    - {item}")
                if len(items) > 5:
                    print(f"    ... and {len(items) - 5} more")

    print("═" * 50)


def main():
    if not INPUT.exists():
        raise FileNotFoundError(f"{INPUT} — run 05_generate_audio.py first")

    with open(INPUT, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f]

    report = validate(entries)
    print_report(report, len(entries))

    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    log.info(f"\nFull report saved to {REPORT}")

    # Exit with error code if critical issues exist
    critical = (
        report["issues"].get("missing_field", []) +
        report["issues"].get("duplicates", []) +
        report["issues"].get("bad_level", [])
    )
    if critical:
        log.error(f"{len(critical)} critical issues — fix before importing")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
