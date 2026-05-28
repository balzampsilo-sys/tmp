#!/usr/bin/env bash
# Full content pipeline: collect → enrich → match → AI fill → audio → validate → import
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Step 1: Collect word lists ==="
python 01_collect_wordlists.py

echo "=== Step 2: Enrich via Wiktionary ==="
python 02_enrich_wiktionary.py

echo "=== Step 3: Match Tatoeba examples ==="
python 03_match_tatoeba.py

echo "=== Step 4: AI fallback (Claude) ==="
python 04_ai_fallback.py

echo "=== Step 5: Generate audio ==="
python 05_generate_audio.py

echo "=== Step 6: Validate ==="
python 06_validate.py

echo "=== Step 7: Import to DB ==="
python 07_import_db.py

echo ""
echo "Pipeline complete."
