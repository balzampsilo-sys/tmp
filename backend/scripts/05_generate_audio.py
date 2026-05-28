"""
Generate pronunciation audio for each word using gTTS (Google Text-to-Speech).

Input:  data/wordlist_final.jsonl
Output: data/audio/{word}.mp3
        data/wordlist_final.jsonl updated with audio_url field

Uploads to S3-compatible storage (Yandex Object Storage or local MinIO).
"""

import json
import logging
import os
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from gtts import gTTS

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger(__name__)

DATA_DIR  = Path(__file__).parent / "data"
AUDIO_DIR = DATA_DIR / "audio"
INPUT     = DATA_DIR / "wordlist_final.jsonl"
OUTPUT    = DATA_DIR / "wordlist_with_audio.jsonl"

AUDIO_DIR.mkdir(exist_ok=True)

# S3 config — override via env vars
S3_ENDPOINT   = os.getenv("S3_ENDPOINT", "https://storage.yandexcloud.net")
S3_BUCKET     = os.getenv("S3_BUCKET", "srs-platform-cards")
S3_PREFIX     = os.getenv("S3_PREFIX", "audio/en/")
S3_ACCESS_KEY = os.getenv("S3_ACCESS_KEY", "")
S3_SECRET_KEY = os.getenv("S3_SECRET_KEY", "")
CDN_BASE      = os.getenv("CDN_BASE", f"{S3_ENDPOINT}/{S3_BUCKET}")

RATE_DELAY = 0.3  # gTTS is rate-limited


def make_s3_client():
    if not S3_ACCESS_KEY:
        return None
    return boto3.client(
        "s3",
        endpoint_url=S3_ENDPOINT,
        aws_access_key_id=S3_ACCESS_KEY,
        aws_secret_access_key=S3_SECRET_KEY,
    )


def generate_mp3(word: str) -> Path:
    path = AUDIO_DIR / f"{word}.mp3"
    if path.exists():
        return path
    tts = gTTS(text=word, lang="en", tld="co.uk")  # British English
    tts.save(str(path))
    return path


def upload_to_s3(client, local_path: Path, word: str) -> str:
    key = f"{S3_PREFIX}{word}.mp3"
    try:
        client.upload_file(
            str(local_path),
            S3_BUCKET,
            key,
            ExtraArgs={"ContentType": "audio/mpeg", "ACL": "public-read"},
        )
        return f"{CDN_BASE}/{key}"
    except ClientError as e:
        log.warning(f"S3 upload failed for {word}: {e}")
        return ""


def load_done() -> set[str]:
    done = set()
    if OUTPUT.exists():
        with open(OUTPUT, encoding="utf-8") as f:
            for line in f:
                try:
                    e = json.loads(line)
                    if e.get("audio_url"):
                        done.add(e["word"])
                except Exception:
                    pass
    return done


def main():
    if not INPUT.exists():
        raise FileNotFoundError(f"{INPUT} — run 04_ai_fallback.py first")

    with open(INPUT, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f]

    done     = load_done()
    todo     = [e for e in entries if e["word"] not in done]
    s3       = make_s3_client()

    if not s3:
        log.warning("S3 not configured — audio URLs will be local paths")

    log.info(f"Total: {len(entries)}, done: {len(done)}, todo: {len(todo)}")

    out = open(OUTPUT, "a", encoding="utf-8")
    generated = 0
    failed    = 0

    for i, entry in enumerate(todo, 1):
        word = entry["word"]
        try:
            mp3_path  = generate_mp3(word)
            if s3:
                audio_url = upload_to_s3(s3, mp3_path, word)
            else:
                audio_url = str(mp3_path)

            entry["audio_url"] = audio_url
            generated += 1
        except Exception as e:
            log.warning(f"  {word}: {e}")
            entry["audio_url"] = ""
            failed += 1

        out.write(json.dumps(entry, ensure_ascii=False) + "\n")

        if i % 100 == 0:
            log.info(f"  {i}/{len(todo)}  generated={generated} failed={failed}")
            out.flush()

        time.sleep(RATE_DELAY)

    out.close()
    log.info(f"\nDone. Generated: {generated}, failed: {failed}")
    log.info(f"Output: {OUTPUT}")


if __name__ == "__main__":
    main()
