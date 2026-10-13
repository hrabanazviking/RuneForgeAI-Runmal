"""S802 (roadmap): full backup + restore UI/CLI.

Acceptance: a full backup taken while the app is active restores
cleanly to staging with a report; failed validation cannot corrupt
the current install (live bytes identical, nothing left staged). The
portable archive imports into a fresh staging install with referential
integrity and manifest-exact counts.
"""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.__main__ import main as runmal_main
from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backups import full as full_service
from runmal.backups.service import BackupError
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import (
    Character,
    Chat,
    Lorebook,
    LoreEntry,
    Memory,
    MemoryChunk,
    MemorySource,
    Message,
    SamplingPreset,
    User,
)
from runmal.portable.archive import ArchiveError, export_archive
from runmal.portable.restore import import_archive

AVATAR = b"\x89PNG-fake"


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "runmal.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, db_path


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_full_backup_stage_restore_via_api(tmp_path, monkeypatch):
    client, db_path = make_client(tmp_path, monkeypatch)
    chat_id = client.post("/api/v1/chats", json={"title": "T"}).json()["id"]
    client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"role": "user", "content": "hello"},
    )
    asset = tmp_path / "assets" / "characters" / "c1" / "avatar.png"
    asset.parent.mkdir(parents=True)
    asset.write_bytes(AVATAR)
    live_before = _sha(db_path)

    created = client.post("/api/v1/backups/full")
    assert created.status_code == 201
    body = created.json()
    assert body["secrets_included"] is False
    assert body["asset_files"] == 1
    assert body["schema_revision"] == "0018"

    staged = client.post(f"/api/v1/backups/full/{body['name']}/stage")
    assert staged.status_code == 200
    report = staged.json()
    assert report["ok"] is True
    assert report["counts"]["chats"] == 1
    assert report["counts"]["messages"] == 1
    staged_db = Path(report["staged_db"])
    assert staged_db.is_file()
    conn = sqlite3.connect(staged_db)
    try:
        assert conn.execute("SELECT content FROM messages").fetchall() == [("hello",)]
    finally:
        conn.close()
    staged_asset = Path(report["staged_assets_dir"]) / "characters" / "c1" / "avatar.png"
    assert staged_asset.read_bytes() == AVATAR
    assert _sha(db_path) == live_before  # live install untouched


def test_full_backup_tampered_bundle_rejected(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "runmal.db"
    migrate_to_head(db_path)
    info = full_service.create_full_backup()
    bundle = Path(info.path)
    with zipfile.ZipFile(bundle) as zf:
        members = {n: zf.read(n) for n in zf.namelist()}
    members["runmal.db"] = members["runmal.db"][:-8] + b"corrupt!"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, blob in members.items():
            zf.writestr(name, blob)
    bundle.write_bytes(buffer.getvalue())

    staging_root = tmp_path / "staging-x"
    with pytest.raises(BackupError, match="checksum mismatch"):
        full_service.stage_full_restore(bundle, staging_root=staging_root)
    assert not staging_root.exists()  # nothing left staged
    assert _sha(db_path)  # live db still readable/present


async def _seed_and_export(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    db_path = src / "runmal.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        character = Character(user_id=user.id, name="Yrsa", avatar_asset="avatar.png")
        session.add(character)
        await session.commit()
        asset_dir = src / "assets" / "characters" / character.id
        asset_dir.mkdir(parents=True)
        (asset_dir / "avatar.png").write_bytes(AVATAR)
        chat = Chat(user_id=user.id, title="hearth", character_id=character.id)
        session.add(chat)
        await session.commit()
        session.add_all(
            [
                Message(chat_id=chat.id, role="user", content="hello"),
                Message(chat_id=chat.id, role="assistant", content="hail"),
            ]
        )
        book = Lorebook(user_id=user.id, name="sagas")
        session.add(book)
        await session.commit()
        session.add(
            LoreEntry(
                lorebook_id=book.id, user_id=user.id, keys_json='["odin"]', content="All-Father"
            )
        )
        memory = Memory(user_id=user.id, content="Volmarr prefers tea", chat_id=chat.id)
        session.add(memory)
        await session.commit()
        session.add(
            MemorySource(
                memory_id=memory.id, source_kind="chat", source_id=chat.id, chat_id=chat.id
            )
        )
        session.add(
            MemoryChunk(
                memory_id=memory.id,
                chunk_index=0,
                text="Volmarr prefers tea",
                provider="ollama",
                model="nomic-embed-text",
                dims=768,
                version="1",
            )
        )
        session.add(SamplingPreset(user_id=user.id, name="calm", params_json="{}"))
        await session.commit()
        (src / "voice_settings.json").write_text(
            json.dumps({"tts_backend": "cosyvoice"}), encoding="utf-8"
        )
        archive = tmp_path / "world.runmal"
        await export_archive(session, user.id, archive, base_dir=src)
        return archive, character.id


async def test_archive_import_roundtrip(tmp_path):
    archive, character_id = await _seed_and_export(tmp_path)
    staging_root = tmp_path / "restored"
    report = await import_archive(archive, staging_root)
    assert report.ok
    assert report.counts["characters"] == 1
    assert report.counts["chats"] == 1 and report.counts["messages"] == 2
    assert report.counts["memories"] == 1 and report.counts["memory_chunks"] == 1
    assert report.counts["assets"] == 1
    assert {c.name for c in report.checks} >= {"foreign_keys", "manifest_counts"}

    factory = create_session_factory(create_db_engine(Path(report.staged_db)))
    async with factory() as session:
        from sqlalchemy import select

        character = await session.get(Character, character_id)
        assert character is not None and character.name == "Yrsa"
        messages = list(
            await session.scalars(select(Message).order_by(Message.created_at, Message.id))
        )
        assert [m.content for m in messages] == ["hello", "hail"]
        chunk = (await session.scalars(select(MemoryChunk))).first()
        assert (chunk.provider, chunk.model, chunk.dims) == ("ollama", "nomic-embed-text", 768)
    restored_avatar = staging_root / "assets" / "characters" / character_id / "avatar.png"
    assert restored_avatar.read_bytes() == AVATAR
    settings = json.loads((staging_root / "voice_settings.json").read_text())
    assert settings == {"tts_backend": "cosyvoice"}


async def test_archive_import_rejects_tampered(tmp_path):
    archive, _ = await _seed_and_export(tmp_path)
    with zipfile.ZipFile(archive) as zf:
        members = {n: zf.read(n) for n in zf.namelist()}
    name = next(n for n in members if n.startswith("chats/"))
    members[name] = members[name].replace(b"hello", b"HELLO")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for n, blob in members.items():
            zf.writestr(n, blob)
    archive.write_bytes(buffer.getvalue())
    staging_root = tmp_path / "restored"
    with pytest.raises(ArchiveError):
        await import_archive(archive, staging_root)
    assert not staging_root.exists()


def test_cli_full_backup_and_archive_import(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    migrate_to_head(tmp_path / "runmal.db")
    assert runmal_main(["backup", "full-create"]) == 0
    bundles = list((tmp_path / "backups").glob("runmal-full-backup-*.zip"))
    assert len(bundles) == 1
    staging = tmp_path / "stage-full"
    assert runmal_main(["backup", "full-stage", str(bundles[0]), "--staging", str(staging)]) == 0
    assert (staging / "runmal.db").is_file()
    # A garbage bundle fails cleanly.
    junk = tmp_path / "junk.zip"
    junk.write_bytes(b"not a zip")
    assert runmal_main(["backup", "full-stage", str(junk)]) == 1
