"""Tests for Telegram initData verification."""

import hashlib
import hmac
import json
import time
import urllib.parse

import pytest

from api.auth import verify_init_data

# Matches TELEGRAM_BOT_TOKEN set in tests/conftest.py
BOT_TOKEN = "123456789:AAABBBCCCDDDEEEFFFGGG"
TEST_USER  = {"id": 123456, "first_name": "Ivan", "username": "ivan_test"}


def make_init_data(user: dict, bot_token: str) -> str:
    """
    Build a valid Telegram initData string for testing.

    Telegram's verify algorithm uses URL-decoded values for the data-check string
    (parse_qsl decodes them), but stores user JSON URL-encoded in the query string.
    """
    user_json = json.dumps(user, separators=(",", ":"))
    auth_date = str(int(time.time()))

    # data_check string uses decoded values (as parse_qsl would return)
    decoded_fields = {
        "user":      user_json,   # raw JSON, not URL-encoded
        "auth_date": auth_date,
        "chat_type": "private",
    }
    data_check = "\n".join(f"{k}={v}" for k, v in sorted(decoded_fields.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    hash_value = hmac.new(secret_key, data_check.encode(), hashlib.sha256).hexdigest()

    # Actual query string: user is URL-encoded (as Telegram sends it)
    return (
        f"user={urllib.parse.quote(user_json)}"
        f"&auth_date={auth_date}"
        f"&chat_type=private"
        f"&hash={hash_value}"
    )


class TestVerifyInitData:
    def test_valid_init_data(self):
        # BOT_TOKEN matches TELEGRAM_BOT_TOKEN in tests/conftest.py env setup
        init_data = make_init_data(TEST_USER, BOT_TOKEN)
        user = verify_init_data(init_data)
        assert user["id"] == TEST_USER["id"]
        assert user["first_name"] == TEST_USER["first_name"]

    def test_wrong_token_raises(self):
        # Build initData with correct token, but try to verify with wrong one
        init_data_wrong = make_init_data(TEST_USER, "wrong_token_999")
        with pytest.raises(ValueError, match="Invalid initData"):
            verify_init_data(init_data_wrong)

    def test_tampered_hash_raises(self):
        init_data = make_init_data(TEST_USER, BOT_TOKEN)
        # Corrupt the hash (last char)
        tampered  = init_data[:-1] + ("x" if init_data[-1] != "x" else "y")
        with pytest.raises(ValueError):
            verify_init_data(tampered)

    def test_missing_hash_raises(self):
        with pytest.raises(ValueError):
            verify_init_data("user=foo&auth_date=12345")
