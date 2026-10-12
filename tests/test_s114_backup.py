"""S114 acceptance: online backup while active, restore-to-staging safety."""

import hashlib
import sqlite3

import pytest
from fastapi.testclient import TestClient

from runmal.__main__ import main as runmal_main
from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backups.service import (
    BackupError,
    backup_database,
    stage_restore,
    verify_backup,
)
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head


def make_client(tmp_path, monkeypatch):
    """App whose live database is the default data-dir path (backup target)."""
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "runmal.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, db_path


def test_backup_while_app_active(tmp_path, monkeypatch) -> None:
    client, db_path = make_client(tmp_path, monkeypatch)
    chat_id = client.post("/api/v1/chats", json={"title": "T"}).json()["id"]
    client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"role": "user", "content": "hello"},
    )
    # The app (and its engine) is still live here: backup must not need it stopped.
    info = backup_database()
    assert info.size_bytes > 0
    assert info.secrets_included is False
    assert info.schema_revision  # migrations recorded in the copy
    # The backup opens cleanly, passes integrity, and holds the data.
    conn = sqlite3.connect(info.path)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
        rows = conn.execute("SELECT content FROM messages").fetchall()
        assert rows == [("hello",)]
    finally:
        conn.close()
    # sha256 in the metadata matches the file on disk.
    assert info.sha256 == hashlib.sha256(open(info.path, "rb").read()).hexdigest()


def test_backup_refuses_missing_database(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    with pytest.raises(BackupError):
        backup_database()


def test_verify_rejects_garbage(tmp_path) -> None:
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"this is not a database")
    with pytest.raises(BackupError):
        verify_backup(bad)


def test_stage_restore_verifies_staging_copy(tmp_path, monkeypatch) -> None:
    _client, _db = make_client(tmp_path, monkeypatch)
    info = backup_database()
    staged = stage_restore(info.path)
    assert staged.path != info.path
    assert staged.sha256 == info.sha256  # faithful copy
    conn = sqlite3.connect(staged.path)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    finally:
        conn.close()


def test_failed_restore_cannot_replace_working_db(tmp_path, monkeypatch) -> None:
    _client, db_path = make_client(tmp_path, monkeypatch)
    before = hashlib.sha256(db_path.read_bytes()).hexdigest()
    info = backup_database()
    # Corrupt the backup copy (not the live DB).
    corrupt = tmp_path / "corrupt.db"
    data = bytearray(open(info.path, "rb").read())
    data[100:200] = b"\x00" * 100
    corrupt.write_bytes(bytes(data))
    staging = tmp_path / "staging.db"
    with pytest.raises(BackupError):
        stage_restore(corrupt, staging_path=staging)
    # The staging file was cleaned up...
    assert not staging.exists()
    # ...and the working database is byte-identical and still opens.
    assert hashlib.sha256(db_path.read_bytes()).hexdigest() == before
    conn = sqlite3.connect(db_path)
    try:
        assert conn.execute("PRAGMA integrity_check").fetchall() == [("ok",)]
    finally:
        conn.close()


def test_backup_api(tmp_path, monkeypatch) -> None:
    client, _db = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/backups")
    assert created.status_code == 201
    body = created.json()
    assert body["sha256"] and body["size_bytes"] > 0
    assert body["secrets_included"] is False
    listed = client.get("/api/v1/backups").json()
    assert [b["name"] for b in listed] == [body["name"]]
    staged = client.post(f"/api/v1/backups/{body['name']}/stage")
    assert staged.status_code == 200
    assert staged.json()["sha256"] == body["sha256"]


def test_backup_api_auth_and_name_validation(tmp_path, monkeypatch) -> None:
    client, _db = make_client(tmp_path, monkeypatch)
    anon = TestClient(create_app(create_session_factory(create_db_engine(tmp_path / "runmal.db"))))
    assert anon.post("/api/v1/backups").status_code == 401
    assert anon.get("/api/v1/backups").status_code == 401
    # Traversal-shaped names are rejected, not resolved.
    assert client.post("/api/v1/backups/../runmal.db/stage").status_code in (400, 404)
    assert client.post("/api/v1/backups/evil.db/stage").status_code == 400
    assert client.post("/api/v1/backups/runmal-backup-20990101T000000.db/stage").status_code == 404


def test_backup_cli_create_and_verify(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    migrate_to_head(tmp_path / "runmal.db")
    assert runmal_main(["backup", "create"]) == 0
    backups = list((tmp_path / "backups").glob("runmal-backup-*.db"))
    assert len(backups) == 1
    assert runmal_main(["backup", "verify", str(backups[0])]) == 0
    assert runmal_main(["backup", "verify", str(tmp_path / "missing.db")]) == 1
    staged = tmp_path / "staged.db"
    assert runmal_main(["backup", "stage", str(backups[0]), "--staging", str(staged)]) == 0
    assert staged.is_file()
