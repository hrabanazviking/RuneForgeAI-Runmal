"""S803 (roadmap): migration/upgrade harness.

Released old-schema fixtures (built by scripts/make_upgrade_fixtures.py
at revisions 0001, 0009, 0016) are upgraded to HEAD by the real
migration runner; the harness proves every fixture migrates, schema
and integrity invariants hold, and the era's sentinel data survives
byte-for-byte in the fields that era wrote.
"""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

import pytest

from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS

FIX = Path(__file__).parent / "fixtures" / "upgrades"
HEAD = MIGRATIONS[-1][0]
FIXTURES = {
    "0001": {
        "tables": {"users": 1, "characters": 1, "chats": 1, "messages": 2},
        "character_name": "Yrsa",
    },
    "0009": {
        "tables": {
            "users": 1,
            "characters": 1,
            "chats": 1,
            "messages": 2,
            "sampling_presets": 1,
            "connection_profiles": 1,
        },
        "character_name": "Yrsa",
    },
    "0016": {
        "tables": {
            "users": 1,
            "characters": 1,
            "chats": 1,
            "messages": 2,
            "backend_profiles": 1,
            "memories": 1,
            "memory_sources": 1,
            "memory_chunks": 1,
            "character_voice_profiles": 1,
            "bridge_credentials": 1,
        },
        "character_name": "Yrsa",
    },
}


def _counts(db_path: Path, tables) -> dict:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        return {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]  # noqa: S608
            for t in tables
        }
    finally:
        conn.close()


def _integrity(db_path: Path) -> tuple[str, list]:
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        return ok, fk
    finally:
        conn.close()


@pytest.mark.parametrize("revision", sorted(FIXTURES))
def test_old_schema_fixture_upgrades_to_head(tmp_path, revision):
    spec = FIXTURES[revision]
    fixture = FIX / f"runmal-{revision}.db"
    assert fixture.is_file(), "missing fixture; run scripts/make_upgrade_fixtures.py"
    work = tmp_path / f"runmal-{revision}.db"
    shutil.copy2(fixture, work)

    assert current_revision(work) == revision
    before = _counts(work, spec["tables"])
    assert before == spec["tables"]

    applied = migrate_to_head(work)
    expected_tail = [rev for rev, _d, _m in MIGRATIONS if rev > revision]
    assert applied == expected_tail
    assert current_revision(work) == HEAD

    ok, fk = _integrity(work)
    assert ok == "ok"
    assert fk == []
    assert _counts(work, spec["tables"]) == before

    conn = sqlite3.connect(f"file:{work}?mode=ro", uri=True)
    try:
        name = conn.execute(
            "SELECT name FROM characters WHERE id = ?",
            ("00000000-0000-4000-8000-000000000002",),
        ).fetchone()[0]
        assert name == spec["character_name"]
        contents = [
            r[0]
            for r in conn.execute("SELECT content FROM messages ORDER BY created_at, id").fetchall()
        ]
        assert contents == ["hello", "hail"]
        if revision == "0016":
            prov = conn.execute("SELECT provider, model, dims FROM memory_chunks").fetchone()
            assert prov == ("ollama", "nomic-embed-text", 768)
            content = conn.execute("SELECT content FROM memories").fetchone()[0]
            assert content == "Volmarr prefers tea"
    finally:
        conn.close()


def test_upgrade_is_idempotent_at_head(tmp_path):
    fixture = FIX / "runmal-0001.db"
    work = tmp_path / "runmal-0001.db"
    shutil.copy2(fixture, work)
    assert migrate_to_head(work)  # first pass applies the tail
    assert migrate_to_head(work) == []  # second pass is a no-op
    assert current_revision(work) == HEAD


def test_every_supported_fixture_is_covered():
    # The harness must not silently lose a fixture: every .db in the
    # upgrades directory has an explicit spec above.
    present = {p.stem.removeprefix("runmal-") for p in FIX.glob("*.db")}
    assert present == set(FIXTURES)
