"""Local auth boundary (S102 + D002 browser bootstrap).

The API is a loopback-only service. Protected routes accept either the
original owner-only bearer credential or a short-lived signed browser
session created through the launcher bootstrap flow.

The permanent credential never appears in responses, logs, traces, or
launcher URLs (INV-023).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

CREDENTIAL_BYTES = 32
CREDENTIAL_FILENAME = "local_credential"

BOOTSTRAP_BYTES = 32
BOOTSTRAP_FILENAME = "launcher_bootstrap.json"
BOOTSTRAP_TTL_SECONDS = 90

SESSION_COOKIE_NAME = "runmal_session"
SESSION_TTL_SECONDS = 7 * 24 * 60 * 60
SESSION_VERSION = "v1"


def data_dir() -> Path:
    """Resolve the Rúnmál data directory (env-overridable for tests)."""
    override = os.environ.get("RUNMAL_DATA_DIR")
    base = Path(override) if override else Path.home() / ".local" / "share" / "runmal"
    base.mkdir(parents=True, exist_ok=True)
    return base


def _write_owner_only(path: Path, text: str) -> None:
    """Atomically write a small owner-only local state file."""
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)


def get_or_create_credential() -> str:
    """Load the local bearer credential, generating it on first run."""
    path = data_dir() / CREDENTIAL_FILENAME
    if path.is_file():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(CREDENTIAL_BYTES)
    _write_owner_only(path, token + "\n")
    return token


def verify_credential(presented: str, expected: str) -> bool:
    """Constant-time credential comparison; empty never verifies."""
    if not presented or not expected:
        return False
    return hmac.compare_digest(presented, expected)


def create_bootstrap_nonce(*, now: float | None = None) -> str:
    """Create a short-lived one-use launcher nonce.

    Only the SHA-256 digest is persisted. The raw nonce is returned to the
    launcher so it can be placed in a loopback-only bootstrap URL.
    """
    current = time.time() if now is None else now
    nonce = secrets.token_urlsafe(BOOTSTRAP_BYTES)
    payload = {
        "digest": hashlib.sha256(nonce.encode("utf-8")).hexdigest(),
        "expires_at": int(current + BOOTSTRAP_TTL_SECONDS),
    }
    path = data_dir() / BOOTSTRAP_FILENAME
    _write_owner_only(path, json.dumps(payload, sort_keys=True) + "\n")
    return nonce


def consume_bootstrap_nonce(nonce: str, *, now: float | None = None) -> bool:
    """Validate and consume a launcher nonce exactly once."""
    if not nonce:
        return False
    path = data_dir() / BOOTSTRAP_FILENAME
    if not path.is_file():
        return False

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        digest = str(payload["digest"])
        expires_at = int(payload["expires_at"])
    except (OSError, ValueError, KeyError, TypeError):
        path.unlink(missing_ok=True)
        return False

    current = time.time() if now is None else now
    if expires_at < current:
        path.unlink(missing_ok=True)
        return False

    presented = hashlib.sha256(nonce.encode("utf-8")).hexdigest()
    if not hmac.compare_digest(presented, digest):
        return False

    # Consume before issuing a session. A browser refresh cannot replay it.
    path.unlink(missing_ok=True)
    return True


def create_browser_session(*, now: float | None = None) -> str:
    """Create a signed browser-session token without exposing the bearer secret."""
    current = time.time() if now is None else now
    expires_at = int(current + SESSION_TTL_SECONDS)
    random_part = secrets.token_urlsafe(24)
    payload = f"{SESSION_VERSION}.{expires_at}.{random_part}"
    signature = hmac.new(
        get_or_create_credential().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return f"{payload}.{signature}"


def verify_browser_session(token: str, *, now: float | None = None) -> bool:
    """Verify a signed, unexpired browser-session token."""
    if not token:
        return False
    try:
        version, expiry_text, random_part, signature = token.split(".", 3)
        expires_at = int(expiry_text)
    except (ValueError, TypeError):
        return False
    if version != SESSION_VERSION or not random_part or not signature:
        return False

    current = time.time() if now is None else now
    if expires_at < current:
        return False

    payload = f"{version}.{expires_at}.{random_part}"
    expected = hmac.new(
        get_or_create_credential().encode("utf-8"),
        payload.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(signature, expected)
