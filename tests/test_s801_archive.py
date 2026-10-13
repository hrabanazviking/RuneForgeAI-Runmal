"""S801 (roadmap): portable .runmal archive — export + validation.

Acceptance: the export schema validates (manifest, checksums, member
shapes), and a planted secret canary is absent from the archive bytes —
secret values are never exported and profile secret references are
blanked by policy.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest

from runmal.backends.profiles import create_profile, put_secret
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import (
    Character,
    CharacterVoiceProfile,
    Chat,
    Group,
    GroupMember,
    Lorebook,
    LoreEntry,
    Memory,
    MemoryChunk,
    MemorySource,
    Message,
    SamplingPreset,
    User,
)
from runmal.portable.archive import (
    ArchiveError,
    export_archive,
    validate_archive,
)

CANARY = "SECRET-CANARY-801"
AVATAR_BYTES = b"\x89PNG\r\n\x1a\nfake-avatar-bytes"


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def seed_world(factory, base_dir: Path) -> str:
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        user_id = user.id

        ref = await put_secret(session, user_id, CANARY)
        await create_profile(
            session,
            user_id,
            name="cloud",
            chat_backend="openrouter",
            chat_model="openai/gpt-4o-mini",
            chat_secret_ref=ref,
        )

        character = Character(
            user_id=user_id, name="Yrsa", card_json='{"name": "Yrsa"}', avatar_asset="avatar.png"
        )
        session.add(character)
        await session.commit()
        asset_dir = base_dir / "assets" / "characters" / character.id
        asset_dir.mkdir(parents=True)
        (asset_dir / "avatar.png").write_bytes(AVATAR_BYTES)

        session.add(
            CharacterVoiceProfile(
                character_id=character.id,
                user_id=user_id,
                tts_backend="cosyvoice",
                voice_id="yrsa-default",
            )
        )
        chat = Chat(user_id=user_id, title="hearth", character_id=character.id)
        session.add(chat)
        await session.commit()
        session.add_all(
            [
                Message(chat_id=chat.id, role="user", content="hello"),
                Message(chat_id=chat.id, role="assistant", content="hail"),
            ]
        )
        book = Lorebook(user_id=user_id, name="sagas")
        session.add(book)
        await session.commit()
        session.add(
            LoreEntry(
                lorebook_id=book.id, user_id=user_id, keys_json='["odin"]', content="All-Father"
            )
        )
        memory = Memory(
            user_id=user_id, kind="semantic", content="Volmarr prefers tea", chat_id=chat.id
        )
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
        session.add(
            SamplingPreset(user_id=user_id, name="calm", params_json='{"temperature": 0.4}')
        )
        group = Group(user_id=user_id, name="warband")
        session.add(group)
        await session.commit()
        session.add(GroupMember(group_id=group.id, character_id=character.id, position=0))
        await session.commit()
        (base_dir / "voice_settings.json").write_text(
            json.dumps({"tts_backend": "cosyvoice"}), encoding="utf-8"
        )
        return user_id


async def test_export_validates_and_counts_match(tmp_path):
    factory = make_factory(tmp_path)
    base_dir = tmp_path / "data"
    base_dir.mkdir()
    user_id = await seed_world(factory, base_dir)
    dest = tmp_path / "out" / "world.runmal"
    async with factory() as session:
        info = await export_archive(session, user_id, dest, base_dir=base_dir)
    assert dest.is_file()
    manifest = validate_archive(dest)
    assert manifest["format"] == "runmal-archive"
    assert manifest["format_version"] == 1
    assert manifest["schema_revision"] == "0018"
    assert manifest["policy"]["secrets_included"] is False
    contents = manifest["contents"]
    assert contents["characters"] == 1
    assert contents["chats"] == 1 and contents["messages"] == 2
    assert contents["lorebooks"] == 1 and contents["lore_entries"] == 1
    assert contents["memories"] == 1 and contents["memory_chunks"] == 1
    assert contents["presets"] == 1 and contents["backend_profiles"] == 1
    assert contents["groups"] == 1 and contents["voice_profiles"] == 1
    assert contents["assets"] == 1
    assert info.warnings == []


async def test_secret_canary_absent_and_refs_blanked(tmp_path):
    factory = make_factory(tmp_path)
    base_dir = tmp_path / "data"
    base_dir.mkdir()
    user_id = await seed_world(factory, base_dir)
    dest = tmp_path / "world.runmal"
    async with factory() as session:
        await export_archive(session, user_id, dest, base_dir=base_dir)
    raw = dest.read_bytes()
    assert CANARY.encode() not in raw
    with zipfile.ZipFile(dest) as zf:
        profile_names = [n for n in zf.namelist() if n.startswith("profiles/")]
        assert len(profile_names) == 1
        profile = json.loads(zf.read(profile_names[0]))
        assert profile["chat_secret_ref"] == ""
        assert profile["has_chat_secret_ref"] is True
        settings = json.loads(zf.read("configuration/public-settings.json"))
        assert settings["voice_settings"] == {"tts_backend": "cosyvoice"}
        avatar_names = [n for n in zf.namelist() if n.startswith("assets/")]
        assert zf.read(avatar_names[0]) == AVATAR_BYTES


def _rezip(dest: Path, transform) -> None:
    with zipfile.ZipFile(dest) as zf:
        members = {n: zf.read(n) for n in zf.namelist()}
    members = transform(members)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        for name, blob in members.items():
            zf.writestr(name, blob)
    dest.write_bytes(buffer.getvalue())


async def _exported(tmp_path) -> Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    factory = make_factory(tmp_path)
    base_dir = tmp_path / "data"
    base_dir.mkdir()
    user_id = await seed_world(factory, base_dir)
    dest = tmp_path / "world.runmal"
    async with factory() as session:
        await export_archive(session, user_id, dest, base_dir=base_dir)
    return dest


async def test_validator_rejects_tampering(tmp_path):
    dest = await _exported(tmp_path)

    def flip(members):
        name = next(n for n in members if n.startswith("chats/"))
        members[name] = members[name].replace(b"hello", b"HELLO")
        return members

    _rezip(dest, flip)
    with pytest.raises(ArchiveError, match="checksum mismatch"):
        validate_archive(dest)


async def test_validator_rejects_extra_member_and_traversal(tmp_path):
    dest = await _exported(tmp_path)
    _rezip(dest, lambda m: {**m, "evil.txt": b"x"})
    with pytest.raises(ArchiveError, match="unmanifested"):
        validate_archive(dest)

    dest2 = await _exported(tmp_path / "second")
    _rezip(
        dest2,
        lambda m: {("../escape.json" if n.startswith("presets/") else n): b for n, b in m.items()},
    )
    with pytest.raises(ArchiveError, match="unsafe"):
        validate_archive(dest2)


async def test_validator_rejects_future_format_version(tmp_path):
    dest = await _exported(tmp_path)

    def bump(members):
        manifest = json.loads(members["manifest.json"])
        manifest["format_version"] = 99
        members["manifest.json"] = json.dumps(manifest).encode()
        return members

    _rezip(dest, bump)
    with pytest.raises(ArchiveError, match="unsupported archive format version 99"):
        validate_archive(dest)


async def test_export_members_deterministic(tmp_path):
    factory = make_factory(tmp_path)
    base_dir = tmp_path / "data"
    base_dir.mkdir()
    user_id = await seed_world(factory, base_dir)
    dest_a, dest_b = tmp_path / "a.runmal", tmp_path / "b.runmal"
    async with factory() as session:
        await export_archive(session, user_id, dest_a, base_dir=base_dir)
        await export_archive(session, user_id, dest_b, base_dir=base_dir)
    with zipfile.ZipFile(dest_a) as za, zipfile.ZipFile(dest_b) as zb:
        assert za.namelist() == zb.namelist()
        for name in za.namelist():
            if name == "manifest.json":
                continue  # exported_at differs; everything else is sealed
            assert za.read(name) == zb.read(name), name


async def test_missing_asset_warns_not_fails(tmp_path):
    factory = make_factory(tmp_path)
    base_dir = tmp_path / "data"
    base_dir.mkdir()
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        session.add(Character(user_id=user.id, name="Ghost", avatar_asset="gone.png"))
        await session.commit()
        info = await export_archive(session, user.id, tmp_path / "w.runmal", base_dir=base_dir)
    assert any("asset missing" in w for w in info.warnings)
    assert info.manifest["contents"].get("assets", 0) == 0
