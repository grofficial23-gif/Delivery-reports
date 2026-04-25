from __future__ import annotations

from dataclasses import dataclass
import base64
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import parse_qsl


SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60
INIT_DATA_MAX_AGE_SECONDS = 24 * 60 * 60


@dataclass(frozen=True)
class MiniAppUser:
    telegram_user_id: int
    username: str
    full_name: str
    language_code: str
    raw_user: dict[str, Any]


def validate_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = INIT_DATA_MAX_AGE_SECONDS,
    now_ts: int | None = None,
) -> MiniAppUser:
    if not init_data.strip():
        raise ValueError("Missing init data.")
    if not bot_token.strip():
        raise ValueError("Missing bot token for Mini App validation.")

    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    payload = {key: value for key, value in pairs}
    received_hash = payload.get("hash", "")
    if not received_hash:
        raise ValueError("Mini App payload has no hash.")

    data_check_string = "\n".join(
        f"{key}={value}"
        for key, value in sorted(payload.items())
        if key != "hash"
    )
    secret_key = hmac.new(b"WebAppData", bot_token.encode("utf-8"), hashlib.sha256).digest()
    expected_hash = hmac.new(
        secret_key,
        data_check_string.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_hash, received_hash):
        raise ValueError("Mini App payload signature is invalid.")

    auth_date_text = payload.get("auth_date", "").strip()
    if not auth_date_text.isdigit():
        raise ValueError("Mini App payload has invalid auth_date.")
    auth_date = int(auth_date_text)
    current_ts = now_ts or int(time.time())
    if current_ts - auth_date > max_age_seconds:
        raise ValueError("Mini App payload expired. Reopen the app from Telegram.")

    user_json = payload.get("user", "").strip()
    if not user_json:
        raise ValueError("Mini App payload has no user data.")
    raw_user = json.loads(user_json)
    user_id = int(raw_user["id"])
    first_name = str(raw_user.get("first_name", "")).strip()
    last_name = str(raw_user.get("last_name", "")).strip()
    full_name = " ".join(part for part in [first_name, last_name] if part).strip() or str(user_id)
    return MiniAppUser(
        telegram_user_id=user_id,
        username=str(raw_user.get("username", "")).strip(),
        full_name=full_name,
        language_code=str(raw_user.get("language_code", "")).strip(),
        raw_user=raw_user,
    )


def issue_session_token(user_id: int, secret: str, issued_at: int | None = None) -> str:
    if not secret.strip():
        raise ValueError("Session secret is required.")
    payload = {
        "user_id": int(user_id),
        "issued_at": int(issued_at or time.time()),
    }
    payload_b64 = _urlsafe_b64encode(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"))
    signature = hmac.new(secret.encode("utf-8"), payload_b64.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload_b64}.{signature}"


def read_session_user_id(
    token: str,
    secret: str,
    max_age_seconds: int = SESSION_MAX_AGE_SECONDS,
    now_ts: int | None = None,
) -> int | None:
    if not token.strip() or not secret.strip():
        return None
    try:
        payload_b64, signature = token.split(".", 1)
    except ValueError:
        return None
    expected_signature = hmac.new(
        secret.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(expected_signature, signature):
        return None
    try:
        payload_raw = _urlsafe_b64decode(payload_b64)
        payload = json.loads(payload_raw)
        user_id = int(payload["user_id"])
        issued_at = int(payload["issued_at"])
    except (ValueError, KeyError, json.JSONDecodeError):
        return None
    current_ts = now_ts or int(time.time())
    if current_ts - issued_at > max_age_seconds:
        return None
    return user_id


def _urlsafe_b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _urlsafe_b64decode(value: str) -> str:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
