"""
Telegram WebApp initData verification + JWT issuance.

Auth flow:
  1. Mini App sends initData (from Telegram.WebApp.initData)
  2. POST /auth/telegram → we verify HMAC, create/get user, return JWT
  3. Subsequent requests: Authorization: Bearer <jwt>
"""

import hashlib
import hmac
import json
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, unquote

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import base64
import hashlib
import hmac as _hmac

from .config import settings
from .database import get_conn

bearer = HTTPBearer()


# ── Telegram verification ─────────────────────────────────────────────────────

def verify_init_data(init_data: str) -> dict:
    """
    Verify Telegram WebApp initData signature.
    Returns parsed user dict on success, raises ValueError on failure.
    """
    parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    received_hash = parsed.pop("hash", "")

    data_check = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))

    secret = hmac.new(
        b"WebAppData",
        settings.telegram_bot_token.encode(),
        hashlib.sha256,
    ).digest()
    expected = hmac.new(secret, data_check.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, received_hash):
        raise ValueError("Invalid initData signature")

    user_raw = parsed.get("user", "{}")
    return json.loads(unquote(user_raw))


# ── JWT ───────────────────────────────────────────────────────────────────────

# ── Minimal HS256 JWT (no external crypto deps) ───────────────────────────────

def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    pad = 4 - len(data) % 4
    return base64.urlsafe_b64decode(data + "=" * pad)


def create_jwt(user_id: str, telegram_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_expire_hours)
    header  = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub": user_id,
        "tg":  telegram_id,
        "exp": int(expire.timestamp()),
    }).encode())
    msg = f"{header}.{payload}"
    sig = _b64url_encode(
        _hmac.new(settings.jwt_secret.encode(), msg.encode(), hashlib.sha256).digest()
    )
    return f"{msg}.{sig}"


def decode_jwt(token: str) -> dict:
    try:
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError("Malformed token")
        header, payload, sig = parts
        msg      = f"{header}.{payload}"
        expected = _b64url_encode(
            _hmac.new(settings.jwt_secret.encode(), msg.encode(), hashlib.sha256).digest()
        )
        if not _hmac.compare_digest(expected, sig):
            raise ValueError("Invalid signature")
        claims = json.loads(_b64url_decode(payload))
        if claims.get("exp", 0) < datetime.now(timezone.utc).timestamp():
            raise ValueError("Token expired")
        return claims
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e))


# ── FastAPI dependency: current user ─────────────────────────────────────────

class CurrentUser:
    def __init__(self, user_id: str, telegram_id: int):
        self.user_id     = user_id
        self.telegram_id = telegram_id


async def get_current_user(
    creds: HTTPAuthorizationCredentials = Depends(bearer),
) -> CurrentUser:
    payload = decode_jwt(creds.credentials)
    return CurrentUser(user_id=payload["sub"], telegram_id=payload["tg"])


# ── DB helpers ────────────────────────────────────────────────────────────────

async def upsert_user(tg_user: dict) -> dict:
    """Create or update user from Telegram data. Returns user row."""
    async with get_conn() as conn:
        row = await conn.fetchrow(
            """
            INSERT INTO users (id, telegram_id, username, first_name, language_code)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (telegram_id) DO UPDATE SET
                username    = EXCLUDED.username,
                first_name  = EXCLUDED.first_name
            RETURNING id, telegram_id, username, first_name
            """,
            str(uuid.uuid4()),
            tg_user["id"],
            tg_user.get("username"),
            tg_user.get("first_name", ""),
            tg_user.get("language_code", "ru"),
        )
        return dict(row)
