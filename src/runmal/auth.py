"""Local auth boundary (S102).

The API is a loopback-only service. Every protected route requires a
bearer credential: a high-entropy token generated once, stored
owner-readable-only in the data dir, and compared in constant time.
The credential never appears in responses, logs, or traces (INV-023).
"""

from __future__ import annotations

import hmac
import os
import secrets
from pathlib import Path

CREDENTIAL_BYTES = 32
CREDENTIAL_FILENAME = "local_credential"


def data_dir() -> Path:
    """Resolve the Rúnmál data directory (env-overridable for tests)."""
    override = os.environ.get("RUNMAL_DATA_DIR")
    base = Path(override) if override else Path.home() / ".local" / "share" / "runmal"
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_or_create_credential() -> str:
    """Load the local bearer credential, generating it on first run."""
    path = data_dir() / CREDENTIAL_FILENAME
    if path.is_file():
        token = path.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(CREDENTIAL_BYTES)
    tmp = path.with_name(CREDENTIAL_FILENAME + ".tmp")
    tmp.write_text(token + "\n", encoding="utf-8")
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    return token


def verify_credential(presented: str, expected: str) -> bool:
    """Constant-time credential comparison; empty never verifies."""
    if not presented or not expected:
        return False
    return hmac.compare_digest(presented, expected)
