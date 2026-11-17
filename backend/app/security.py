import base64
import hashlib
import hmac
import json
import os
import time
from pathlib import Path
from typing import Annotated

from fastapi import Cookie, HTTPException, status

SESSION_COOKIE_NAME = "cloudvault_session"
SESSION_MAX_AGE_SECONDS = 12 * 60 * 60
AUTH_FILE = Path(__file__).resolve().parents[1] / ".auth.json"


def _session_config() -> tuple[str, str, str]:
    email = os.getenv("CLOUDVAULT_ACCESS_EMAIL", "").strip().lower()
    password = os.getenv("CLOUDVAULT_ACCESS_PASSWORD", "")
    secret = os.getenv("CLOUDVAULT_SESSION_SECRET", "")
    if len(password) < 12:
        raise RuntimeError("CLOUDVAULT_ACCESS_PASSWORD must contain at least 12 characters.")
    if len(secret.encode("utf-8")) < 32:
        raise RuntimeError("CLOUDVAULT_SESSION_SECRET must contain at least 32 bytes.")
    if not email or "@" not in email:
        raise RuntimeError("CLOUDVAULT_ACCESS_EMAIL must be a valid email address.")
    return email, password, secret


def validate_auth_configuration() -> None:
    _session_config()


def is_valid_credentials(candidate_email: str, candidate_password: str) -> bool:
    # Local registrations are authoritative during development. Deployed
    # environments use the configured environment credentials because the
    # local registration file is not durable there.
    registered = None if os.getenv("VERCEL") else _read_registered_user()
    if registered:
        stored_email = registered.get("email", "")
        stored_hash = registered.get("password_hash", "")
        stored_salt = registered.get("salt", "")
        if not all(isinstance(value, str) for value in (stored_email, stored_hash, stored_salt)):
            return False
        candidate_hash = _hash_password(candidate_password, stored_salt)
        return hmac.compare_digest(candidate_email.strip().lower(), stored_email) and hmac.compare_digest(candidate_hash, stored_hash)

    email, password, _ = _session_config()
    return hmac.compare_digest(candidate_email.strip().lower(), email) and hmac.compare_digest(candidate_password, password)


def _hash_password(password: str, salt: str) -> str:
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), base64.urlsafe_b64decode(salt), 240_000)
    return base64.urlsafe_b64encode(digest).decode("ascii")


def _read_registered_user() -> dict | None:
    try:
        value = json.loads(AUTH_FILE.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else None
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def register_user(email: str, password: str) -> bool:
    normalized_email = email.strip().lower()
    if "@" not in normalized_email:
        raise ValueError("Enter a valid email address.")
    if len(password) < 12:
        raise ValueError("Password must contain at least 12 characters.")
    if _read_registered_user():
        return False
    salt = base64.urlsafe_b64encode(os.urandom(16)).decode("ascii")
    AUTH_FILE.write_text(
        json.dumps({"email": normalized_email, "salt": salt, "password_hash": _hash_password(password, salt)}),
        encoding="utf-8",
    )
    return True


def is_valid_password(candidate: str) -> bool:
    """Backward-compatible helper for callers that only validate a password."""
    password = os.getenv("CLOUDVAULT_ACCESS_PASSWORD", "")
    secret = os.getenv("CLOUDVAULT_SESSION_SECRET", "")
    if len(password) < 12 or len(secret.encode("utf-8")) < 32:
        _session_config()
    return hmac.compare_digest(candidate, password)


def create_session_token(secret: str, now: int | None = None) -> str:
    payload = json.dumps(
        {"expires": (int(time.time()) if now is None else now) + SESSION_MAX_AGE_SECONDS},
        separators=(",", ":"),
    ).encode("utf-8")
    encoded_payload = base64.urlsafe_b64encode(payload).rstrip(b"=").decode("ascii")
    signature = hmac.new(secret.encode("utf-8"), encoded_payload.encode("ascii"), hashlib.sha256)
    encoded_signature = base64.urlsafe_b64encode(signature.digest()).rstrip(b"=").decode("ascii")
    return f"{encoded_payload}.{encoded_signature}"


def issue_session_token() -> str:
    _, _, secret = _session_config()
    return create_session_token(secret)


def is_valid_session_token(token: str | None, secret: str, now: int | None = None) -> bool:
    if not token:
        return False
    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected = hmac.new(
            secret.encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        signature = base64.urlsafe_b64decode(
            encoded_signature + "=" * (-len(encoded_signature) % 4)
        )
        if not hmac.compare_digest(expected, signature):
            return False
        payload = base64.urlsafe_b64decode(
            encoded_payload + "=" * (-len(encoded_payload) % 4)
        )
        expires = json.loads(payload).get("expires")
        current_time = int(time.time()) if now is None else now
        return isinstance(expires, int) and expires > current_time
    except (ValueError, TypeError, UnicodeDecodeError, json.JSONDecodeError):
        return False


def require_authenticated(
    session: Annotated[str | None, Cookie(alias=SESSION_COOKIE_NAME)] = None,
) -> None:
    _, _, secret = _session_config()
    if not is_valid_session_token(session, secret):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in to access your files.",
        )


def has_authenticated_session(session: str | None) -> bool:
    _, _, secret = _session_config()
    return is_valid_session_token(session, secret)
