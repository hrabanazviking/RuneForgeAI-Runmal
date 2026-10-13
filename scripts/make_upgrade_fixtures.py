"""Build the S803 old-schema upgrade fixtures.

Creates ``tests/fixtures/upgrades/runmal-<revision>.db`` files: real
SQLite databases whose schemas are exactly what the migration runner
produces up to that revision, seeded with era-valid sentinel rows.
The S803 harness upgrades copies to HEAD and proves data survives.

Run: ``python scripts/make_upgrade_fixtures.py`` (deterministic IDs
and timestamps; safe to re-run — fixtures are rebuilt from scratch).
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from runmal.db.migrations import MIGRATIONS  # noqa: E402

OUT_DIR = Path(__file__).resolve().parent.parent / "tests" / "fixtures" / "upgrades"
TS = "2026-01-01T00:00:00+00:00"
U1 = "00000000-0000-4000-8000-000000000001"
C1 = "00000000-0000-4000-8000-000000000002"
CH1 = "00000000-0000-4000-8000-000000000003"
M1 = "00000000-0000-4000-8000-000000000004"
M2 = "00000000-0000-4000-8000-000000000005"

# Sentinel rows per fixture revision. Values are filtered to the
# columns that exist at that revision; every NOT NULL column without a
# DDL default must be covered or the build fails loudly.
SEEDS: dict[str, dict[str, list[dict]]] = {
    "0001": {
        "users": [{"id": U1, "name": "volmarr", "created_at": TS}],
        "characters": [{"id": C1, "user_id": U1, "name": "Yrsa", "created_at": TS}],
        "chats": [
            {
                "id": CH1,
                "user_id": U1,
                "character_id": C1,
                "title": "hearth",
                "created_at": TS,
            }
        ],
        "messages": [
            {"id": M1, "chat_id": CH1, "role": "user", "content": "hello", "created_at": TS},
            {"id": M2, "chat_id": CH1, "role": "assistant", "content": "hail", "created_at": TS},
        ],
    },
    "0009": {
        "users": [{"id": U1, "name": "volmarr", "created_at": TS}],
        "characters": [
            {
                "id": C1,
                "user_id": U1,
                "name": "Yrsa",
                "card_json": '{"name": "Yrsa"}',
                "avatar_asset": "avatar.png",
                "created_at": TS,
            }
        ],
        "chats": [
            {
                "id": CH1,
                "user_id": U1,
                "character_id": C1,
                "title": "hearth",
                "created_at": TS,
            }
        ],
        "messages": [
            {"id": M1, "chat_id": CH1, "role": "user", "content": "hello", "created_at": TS},
            {"id": M2, "chat_id": CH1, "role": "assistant", "content": "hail", "created_at": TS},
        ],
        "sampling_presets": [
            {
                "id": "00000000-0000-4000-8000-000000000006",
                "user_id": U1,
                "name": "calm",
                "params_json": '{"temperature": 0.4}',
                "template_ref": "",
                "created_at": TS,
            }
        ],
        "connection_profiles": [
            {
                "id": "00000000-0000-4000-8000-000000000007",
                "user_id": U1,
                "name": "local",
                "backend": "ollama",
                "base_url": "",
                "model": "llama3.1",
                "is_active": 1,
                "created_at": TS,
            }
        ],
    },
    "0016": {
        "users": [{"id": U1, "name": "volmarr", "created_at": TS}],
        "characters": [
            {
                "id": C1,
                "user_id": U1,
                "name": "Yrsa",
                "card_json": '{"name": "Yrsa"}',
                "avatar_asset": "avatar.png",
                "created_at": TS,
            }
        ],
        "chats": [
            {
                "id": CH1,
                "user_id": U1,
                "character_id": C1,
                "title": "hearth",
                "created_at": TS,
            }
        ],
        "messages": [
            {"id": M1, "chat_id": CH1, "role": "user", "content": "hello", "created_at": TS},
            {"id": M2, "chat_id": CH1, "role": "assistant", "content": "hail", "created_at": TS},
        ],
        "backend_profiles": [
            {
                "id": "00000000-0000-4000-8000-000000000008",
                "user_id": U1,
                "name": "local",
                "chat_backend": "ollama",
                "chat_model": "llama3.1",
                "embedding_backend": "ollama",
                "embedding_model": "nomic-embed-text",
                "stt_ref": "",
                "tts_ref": "",
                "chat_secret_ref": "",
                "embedding_secret_ref": "",
                "config_json": "{}",
                "created_at": TS,
            }
        ],
        "memories": [
            {
                "id": "00000000-0000-4000-8000-000000000009",
                "user_id": U1,
                "kind": "semantic",
                "content": "Volmarr prefers tea",
                "chat_id": CH1,
                "created_at": TS,
                "embedding_json": (
                    '{"provider": "ollama", "model": "nomic-embed-text",'
                    ' "dims": 768, "version": "1"}'
                ),
            }
        ],
        "memory_sources": [
            {
                "memory_id": "00000000-0000-4000-8000-000000000009",
                "source_kind": "chat",
                "source_id": CH1,
                "chat_id": CH1,
            }
        ],
        "memory_chunks": [
            {
                "id": "00000000-0000-4000-8000-00000000000a",
                "memory_id": "00000000-0000-4000-8000-000000000009",
                "chunk_index": 0,
                "text": "Volmarr prefers tea",
                "provider": "ollama",
                "model": "nomic-embed-text",
                "dims": 768,
                "version": "1",
            }
        ],
        "character_voice_profiles": [
            {
                "character_id": C1,
                "user_id": U1,
                "tts_backend": "cosyvoice",
                "voice_id": "yrsa-default",
                "language": "en-us",
                "params_json": "{}",
                "updated_at": TS,
            }
        ],
        "bridge_credentials": [
            {
                "id": "00000000-0000-4000-8000-00000000000b",
                "user_id": U1,
                "name": "fixture-bridge",
                "token_hash": "fixture-hash-not-a-secret",
                "scopes_json": '["chat:read"]',
                "created_at": TS,
            }
        ],
    },
}


def _columns(conn: sqlite3.Connection, table: str) -> list[tuple[str, bool, bool]]:
    """(name, notnull, has_default) per column of ``table``."""
    rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
    return [(r[1], bool(r[3]), r[4] is not None) for r in rows]


def build(revision: str, seeds: dict[str, list[dict]]) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"runmal-{revision}.db"
    path.unlink(missing_ok=True)
    conn = sqlite3.connect(path)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(revision TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for rev, _desc, module in MIGRATIONS:
            if rev > revision:
                break
            module.upgrade(conn)
            conn.execute(
                "INSERT INTO schema_migrations (revision, applied_at) VALUES (?, ?)",
                (rev, TS),
            )
        conn.commit()
        for table, rows in seeds.items():
            columns = _columns(conn, table)
            if not columns:
                raise SystemExit(f"fixture {revision}: no such table {table}")
            known = {name for name, _nn, _hd in columns}
            for row in rows:
                unknown = set(row) - known
                if unknown:
                    raise SystemExit(f"fixture {revision}: {table} has no columns {unknown}")
                missing = [
                    name
                    for name, notnull, has_default in columns
                    if notnull and not has_default and name not in row
                ]
                if missing:
                    raise SystemExit(
                        f"fixture {revision}: {table} seed misses required columns {missing}"
                    )
                cols = [c for c in row if c in known]
                conn.execute(
                    f"INSERT INTO {table} ({', '.join(cols)}) "  # noqa: S608
                    f"VALUES ({', '.join('?' for _ in cols)})",
                    [row[c] for c in cols],
                )
        conn.commit()
        problems = conn.execute("PRAGMA foreign_key_check").fetchall()
        if problems:
            raise SystemExit(f"fixture {revision}: FK problems {problems}")
        if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
            raise SystemExit(f"fixture {revision}: integrity_check failed")
    finally:
        conn.close()
    return path


def main() -> int:
    for revision, seeds in SEEDS.items():
        path = build(revision, seeds)
        print(f"built {path} ({path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
