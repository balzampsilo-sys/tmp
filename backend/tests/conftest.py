"""Root conftest: set required env vars before any module imports settings."""

import os

# Must be set before api.config is imported
os.environ.setdefault("DATABASE_URL",          "postgresql://test:test@localhost/test")
os.environ.setdefault("TELEGRAM_BOT_TOKEN",    "123456789:AAABBBCCCDDDEEEFFFGGG")
os.environ.setdefault("JWT_SECRET",            "test-secret-key-for-unit-tests-only")
