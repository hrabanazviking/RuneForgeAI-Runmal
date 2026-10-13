"""S804 (roadmap): runmal doctor diagnostics.

Acceptance: injected faults produce SPECIFIC actionable findings —
corrupt DB, broken provenance, missing assets, busy port, dead
provider — and no finding ever leaks a secret value.
"""

from __future__ import annotations

import json
import socket
import sqlite3
from pathlib import Path

from runmal.__main__ import main as runmal_main
from runmal.db.migrate import migrate_to_head
from runmal.diagnostics.doctor import FAIL, OK, WARN, run_doctor

TS = "2026-01-01T00:00:00+00:00"
CANARY = "SECRET-CANARY-804"


def make_install(tmp_path: Path) -> Path:
    db = tmp_path / "runmal.db"
    migrate_to_head(db)
    return db


def seed(db: Path, statements: list[tuple[str, tuple]]) -> None:
    conn = sqlite3.connect(db)
    try:
        for sql, params in statements:
            conn.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def seed_user_character(db: Path, tmp_path: Path, *, avatar: bool = True) -> None:
    seed(
        db,
        [
            ("INSERT INTO users (id, name, created_at) VALUES ('u1', 'volmarr', ?)", (TS,)),
            (
                "INSERT INTO characters (id, user_id, name, card_json, "
                "avatar_asset, created_at) VALUES ('c1', 'u1', 'Yrsa', '{}', "
                "?, ?)",
                ("avatar.png" if avatar else None, TS),
            ),
        ],
    )
    if avatar:
        asset = tmp_path / "assets" / "characters" / "c1" / "avatar.png"
        asset.parent.mkdir(parents=True)
        asset.write_bytes(b"png")


def by_check(report) -> dict:
    return {f.check: f for f in report.findings}


def test_healthy_install_has_no_failures(tmp_path):
    db = make_install(tmp_path)
    seed_user_character(db, tmp_path)
    report = run_doctor(
        db_path=db,
        base_dir=tmp_path,
        port=0 if False else _free_port(),
        provider_probe=lambda b, u: (True, "HTTP 200"),
        audio_probe=lambda: (2, "fake-audio"),
    )
    assert report.ok
    checks = by_check(report)
    assert checks["database_integrity"].status == OK
    assert checks["schema_revision"].status == OK
    assert checks["sqlite_vec"].status == OK
    assert checks["assets"].status == OK
    assert checks["provenance"].status == OK


def test_corrupt_database_is_a_specific_failure(tmp_path):
    db = make_install(tmp_path)
    db.write_bytes(b"this is not sqlite at all" * 64)
    report = run_doctor(db_path=db, base_dir=tmp_path, audio_probe=lambda: (1, "x"))
    finding = by_check(report)["database_integrity"]
    assert finding.status == FAIL
    assert finding.action  # actionable, not just red
    assert not report.ok


def test_missing_database_and_old_schema(tmp_path):
    report = run_doctor(
        db_path=tmp_path / "runmal.db", base_dir=tmp_path, audio_probe=lambda: (1, "x")
    )
    assert by_check(report)["database"].status == FAIL

    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE schema_migrations (revision TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
    )
    conn.execute("INSERT INTO schema_migrations VALUES ('0001', ?)", (TS,))
    conn.execute(
        "CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT NOT NULL)"
    )
    conn.commit()
    conn.close()
    report = run_doctor(db_path=db, base_dir=tmp_path, audio_probe=lambda: (1, "x"))
    finding = by_check(report)["schema_revision"]
    assert finding.status == WARN and "0001" in finding.detail


def test_injected_provenance_faults(tmp_path):
    db = make_install(tmp_path)
    seed_user_character(db, tmp_path, avatar=False)
    seed(
        db,
        [
            (
                "INSERT INTO memories (id, user_id, content, created_at, "
                "embedding_json) VALUES ('m1', 'u1', 'tea', ?, "
                '\'{"provider": "ollama", "model": "nomic", "dims": 768, "version": "1"}\')',
                (TS,),
            ),
            # chunk disagrees with the memory's provider AND has bad dims
            (
                "INSERT INTO memory_chunks (id, memory_id, chunk_index, text, "
                "provider, model, dims, version) VALUES ('k1', 'm1', 0, 'tea', "
                "'aesir', 'other', 0, '1')",
                (),
            ),
            # source pointing at a chat that does not exist
            (
                "INSERT INTO memory_sources (memory_id, source_kind, source_id, "
                "chat_id) VALUES ('m1', 'chat', 'gone', 'gone')",
                (),
            ),
        ],
    )
    report = run_doctor(db_path=db, base_dir=tmp_path, audio_probe=lambda: (1, "x"))
    checks = by_check(report)
    assert checks["provenance_provider_mismatch"].status == FAIL
    assert checks["provenance_chunk_dims"].status == FAIL
    assert checks["provenance_dangling_sources"].status == WARN
    assert not report.ok


def test_missing_and_orphaned_assets(tmp_path):
    db = make_install(tmp_path)
    seed_user_character(db, tmp_path)
    (tmp_path / "assets" / "characters" / "c1" / "avatar.png").unlink()
    orphan = tmp_path / "assets" / "characters" / "ghost"
    orphan.mkdir(parents=True)
    (orphan / "x.png").write_bytes(b"x")
    report = run_doctor(db_path=db, base_dir=tmp_path, audio_probe=lambda: (1, "x"))
    checks = by_check(report)
    assert checks["assets_missing"].status == WARN
    assert "c1/avatar.png" in checks["assets_missing"].detail
    assert checks["assets_orphaned"].status == WARN


def test_port_and_provider_and_audio_probes(tmp_path):
    db = make_install(tmp_path)
    seed(
        db,
        [
            ("INSERT INTO users (id, name, created_at) VALUES ('u1', 'v', ?)", (TS,)),
            (
                "INSERT INTO backend_profiles (id, user_id, name, chat_backend, "
                "chat_model, embedding_backend, embedding_model, stt_ref, "
                "tts_ref, chat_secret_ref, embedding_secret_ref, config_json, "
                "created_at) VALUES ('p1', 'u1', 'local', 'ollama', 'llama3.1', "
                "'', '', '', '', '', '', '{}', ?)",
                (TS,),
            ),
        ],
    )
    blocker = socket.socket()
    blocker.bind(("127.0.0.1", 0))
    busy_port = blocker.getsockname()[1]
    try:
        report = run_doctor(
            db_path=db,
            base_dir=tmp_path,
            port=busy_port,
            provider_probe=lambda b, u: (False, "unreachable: ConnectError"),
            audio_probe=lambda: (_ for _ in ()).throw(ImportError("no portaudio")),
        )
    finally:
        blocker.close()
    checks = by_check(report)
    assert checks["port"].status == WARN
    assert checks["provider:ollama"].status == WARN
    assert "start the provider" in checks["provider:ollama"].action
    assert checks["audio_devices"].status == WARN
    assert report.ok  # warnings degrade; they do not fail the doctor


def test_doctor_never_leaks_secret_values(tmp_path):
    db = make_install(tmp_path)
    seed(
        db,
        [
            ("INSERT INTO users (id, name, created_at) VALUES ('u1', 'v', ?)", (TS,)),
            (
                "INSERT INTO secrets (ref, user_id, value, created_at) VALUES ('secret:x', 'u1', ?, ?)",
                (CANARY, TS),
            ),
            (
                "INSERT INTO backend_profiles (id, user_id, name, chat_backend, "
                "chat_model, embedding_backend, embedding_model, stt_ref, "
                "tts_ref, chat_secret_ref, embedding_secret_ref, config_json, "
                "created_at) VALUES ('p1', 'u1', 'cloud', 'openrouter', 'm', "
                "'', '', '', '', 'secret:x', '', '{}', ?)",
                (TS,),
            ),
        ],
    )
    report = run_doctor(
        db_path=db,
        base_dir=tmp_path,
        provider_probe=lambda b, u: (True, "HTTP 200"),
        audio_probe=lambda: (1, "x"),
    )
    assert CANARY not in json.dumps(report.to_dict())


def _free_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def test_doctor_cli_exit_codes(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    migrate_to_head(tmp_path / "runmal.db")
    rc = runmal_main(["doctor", "--json", "--port", str(_free_port())])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is True
    (tmp_path / "runmal.db").write_bytes(b"garbage" * 128)
    rc = runmal_main(["doctor", "--json"])
    assert rc == 1
    out = json.loads(capsys.readouterr().out)
    assert out["ok"] is False
    assert CANARY not in json.dumps(out)
