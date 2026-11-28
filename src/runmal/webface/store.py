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
CREATE TABLE IF NOT EXISTS user_appearance (
    user_id INTEGER PRIMARY KEY REFERENCES users(id),
    prefs TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS web_sessions (
    token_hash TEXT PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    created_at REAL NOT NULL,
    expires REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS recovery_codes (
    user_id INTEGER NOT NULL REFERENCES users(id),
    code_hash TEXT NOT NULL,
    created_at REAL NOT NULL,
    used_at REAL,
    PRIMARY KEY (user_id, code_hash)
);
CREATE TABLE IF NOT EXISTS recovery_attempts (
    username TEXT NOT NULL,
    ts REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS agent_tokens (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    name TEXT NOT NULL,
    token_hash TEXT NOT NULL UNIQUE,
    created_at REAL NOT NULL,
    revoked_at REAL,
    last_used_at REAL
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

    # -- appearance (W-09: webface-local, per account) --------------

    def get_appearance(self, user_id: int):
        """The account's stored appearance prefs dict, or None
        when none was ever saved. Stored as one JSON string;
        validation/normalisation is the W-09 layer's job."""
        import json as _json
        with self._lock:
            row = self.db.execute(
                "SELECT prefs FROM user_appearance WHERE user_id = ?",
                (user_id,)).fetchone()
        if row is None:
            return None
        try:
            data = _json.loads(row["prefs"])
        except ValueError:
            return None
        return data if isinstance(data, dict) else None

    def set_appearance(self, user_id: int, prefs: dict) -> None:
        import json as _json
        with self._lock:
            self.db.execute(
                "INSERT INTO user_appearance (user_id, prefs)"
                " VALUES (?, ?) ON CONFLICT(user_id) DO UPDATE"
                " SET prefs = excluded.prefs",
                (user_id, _json.dumps(prefs)))
            self.db.commit()

    def close_all_sessions(self, user_id: int) -> None:
        """End every session for one user (password change road)."""
        with self._lock:
            self.db.execute(
                "DELETE FROM web_sessions WHERE user_id = ?", (user_id,))
            self.db.commit()

    # -- W-10: password / recovery / agent tokens --------------------

    def set_password_hash(self, user_id: int, pass_hash: str) -> None:
        with self._lock:
            self.db.execute(
                "UPDATE users SET pass_hash = ? WHERE id = ?",
                (pass_hash, user_id))
            self.db.commit()

    def list_sessions(self, user_id: int):
        """Live session rows (created/expires only - a session's
        token digest is never a display value)."""
        now = time.time()
        with self._lock:
            rows = self.db.execute(
                "SELECT created_at, expires FROM web_sessions"
                " WHERE user_id = ? AND expires > ?"
                " ORDER BY created_at", (user_id, now)).fetchall()
        return [dict(r) for r in rows]

    def replace_recovery_codes(self, user_id: int, code_hashes) -> None:
        """Regenerating invalidates the previous set outright:
        every old row goes, the new digests land."""
        now = time.time()
        with self._lock:
            self.db.execute(
                "DELETE FROM recovery_codes WHERE user_id = ?", (user_id,))
            self.db.executemany(
                "INSERT INTO recovery_codes (user_id, code_hash,"
                " created_at) VALUES (?, ?, ?)",
                [(user_id, h, now) for h in code_hashes])
            self.db.commit()

    def recovery_code_row(self, user_id: int, code_hash: str):
        with self._lock:
            row = self.db.execute(
                "SELECT * FROM recovery_codes WHERE user_id = ?"
                " AND code_hash = ?", (user_id, code_hash)).fetchone()
        return dict(row) if row else None

    def mark_recovery_code_used(self, user_id: int, code_hash: str) -> bool:
        with self._lock:
            cur = self.db.execute(
                "UPDATE recovery_codes SET used_at = ? WHERE user_id = ?"
                " AND code_hash = ? AND used_at IS NULL",
                (time.time(), user_id, code_hash))
            self.db.commit()
        return cur.rowcount == 1

    def recovery_failures(self, username: str, window: float) -> int:
        with self._lock:
            row = self.db.execute(
                "SELECT COUNT(*) AS n FROM recovery_attempts"
                " WHERE username = ? COLLATE NOCASE AND ts > ?",
                (username, time.time() - window)).fetchone()
        return int(row["n"])

    def record_recovery_failure(self, username: str) -> None:
        with self._lock:
            self.db.execute(
                "INSERT INTO recovery_attempts (username, ts)"
                " VALUES (?, ?)", (username, time.time()))
            self.db.commit()

    def clear_recovery_failures(self, username: str) -> None:
        with self._lock:
            self.db.execute(
                "DELETE FROM recovery_attempts WHERE username = ?"
                " COLLATE NOCASE", (username,))
            self.db.commit()

    def create_agent_token(self, user_id: int, name: str) -> tuple:
        """Mint an agent API token; returns (row view, PLAINTEXT
        shown exactly once). Only the digest is stored."""
        token = "rma_" + new_secret()
        now = time.time()
        with self._lock:
            cur = self.db.execute(
                "INSERT INTO agent_tokens (user_id, name, token_hash,"
                " created_at) VALUES (?, ?, ?, ?)",
                (user_id, name, digest(token), now))
            self.db.commit()
            row = self.db.execute(
                "SELECT id, name, created_at, revoked_at, last_used_at"
                " FROM agent_tokens WHERE id = ?",
                (cur.lastrowid,)).fetchone()
        return dict(row), token

    def list_agent_tokens(self, user_id: int):
        """Name/date/state only - never a digest, never plaintext."""
        with self._lock:
            rows = self.db.execute(
                "SELECT id, name, created_at, revoked_at, last_used_at"
                " FROM agent_tokens WHERE user_id = ?"
                " ORDER BY created_at", (user_id,)).fetchall()
        return [dict(r) for r in rows]

    def revoke_agent_token(self, user_id: int, token_id: int) -> bool:
        with self._lock:
            cur = self.db.execute(
                "UPDATE agent_tokens SET revoked_at = ? WHERE id = ?"
                " AND user_id = ? AND revoked_at IS NULL",
                (time.time(), token_id, user_id))
            self.db.commit()
        return cur.rowcount == 1

    def agent_for_token(self, token: str):
        """The (token row, user row) for a live agent token, or
        None. Revoked tokens authenticate nothing, immediately."""
        if not token:
            return None
        with self._lock:
            row = self.db.execute(
                "SELECT * FROM agent_tokens WHERE token_hash = ?",
                (digest(token),)).fetchone()
            if row is None or row["revoked_at"] is not None:
                return None
            self.db.execute(
                "UPDATE agent_tokens SET last_used_at = ? WHERE id = ?",
                (time.time(), row["id"]))
            self.db.commit()
            view = {k: row[k] for k in
                    ("id", "name", "created_at", "revoked_at",
                     "last_used_at")}
        return view, self.get_user(row["user_id"])
