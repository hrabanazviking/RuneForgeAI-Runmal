"""Webface storage: one SQLite ledger for accounts + sessions.

Data dir (RUNMAL_WEBFACE_DATA_DIR or ~/.local/share/runmal-webface):
    webface.db   accounts, web sessions (digest-only)

The account model is ONE model for humans and agents alike
(account_type is provenance, never a feature gate — the Web Hall /
Samtal law, carried into the Rúnmál web campaign, decision 8).
Sessions are server-side rows keyed by the SHA-256 digest of the
cookie token, 30-day TTL; the plaintext token never touches disk.
"""
from __future__ import annotations

import sqlite3
import threading
import time
from pathlib import Path

from .security import digest, new_secret

SESSION_TTL_SECONDS = 30 * 24 * 3600

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    pass_hash TEXT NOT NULL,
    account_type TEXT NOT NULL DEFAULT 'human'
        CHECK (account_type IN ('human','agent')),
    created_at REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS web_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at REAL NOT NULL,
    expires REAL NOT NULL
);
"""


class Store:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(
            str(self.data_dir / "webface.db"), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self._lock = threading.RLock()  # RLock: create_user re-enters via get_user
        with self._lock:
            self.db.executescript(_SCHEMA)
            self.db.commit()

    # -- accounts -------------------------------------------------------

    def create_user(self, username: str, pass_hash: str,
                    account_type: str = "human"):
        """Create an account; returns the row dict, or None when the
        username is already taken."""
        with self._lock:
            try:
                cur = self.db.execute(
                    "INSERT INTO users (username, pass_hash, account_type,"
                    " created_at) VALUES (?, ?, ?, ?)",
                    (username, pass_hash, account_type, time.time()))
                self.db.commit()
            except sqlite3.IntegrityError:
                self.db.rollback()
                return None
            return self.get_user(cur.lastrowid)

    def get_user(self, user_id: int):
        with self._lock:
            row = self.db.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
        return dict(row) if row else None

    def get_user_by_name(self, username: str):
        with self._lock:
            row = self.db.execute(
                "SELECT * FROM users WHERE username = ? COLLATE NOCASE",
                (username,)).fetchone()
        return dict(row) if row else None

    # -- sessions ---------------------------------------------------------

    def create_session(self, user_id: int) -> str:
        """Mint a session; returns the PLAINTEXT token (shown once,
        to the cookie). Only its digest is stored."""
        token = new_secret()
        now = time.time()
        with self._lock:
            self.db.execute(
                "INSERT INTO web_sessions (token_hash, user_id, created_at,"
                " expires) VALUES (?, ?, ?, ?)",
                (digest(token), user_id, now, now + SESSION_TTL_SECONDS))
            self.db.commit()
        return token

    def session_row(self, token: str):
        """The live session row for a plaintext token, or None.
        Expired rows are pruned on sight."""
        if not token:
            return None
        with self._lock:
            row = self.db.execute(
                "SELECT * FROM web_sessions WHERE token_hash = ?",
                (digest(token),)).fetchone()
            if row is None:
                return None
            if row["expires"] <= time.time():
                self.db.execute(
                    "DELETE FROM web_sessions WHERE token_hash = ?",
                    (digest(token),))
                self.db.commit()
                return None
        return dict(row)

    def user_for_session(self, token: str):
        row = self.session_row(token)
        if row is None:
            return None
        return self.get_user(row["user_id"])

    def delete_session(self, token: str) -> None:
        if not token:
            return
        with self._lock:
            self.db.execute(
                "DELETE FROM web_sessions WHERE token_hash = ?",
                (digest(token),))
            self.db.commit()

    def close_all_sessions(self, user_id: int) -> None:
        """End every session for one user (password change road)."""
        with self._lock:
            self.db.execute(
                "DELETE FROM web_sessions WHERE user_id = ?", (user_id,))
            self.db.commit()
