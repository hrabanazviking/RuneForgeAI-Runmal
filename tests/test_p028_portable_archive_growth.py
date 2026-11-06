"""P-028 (roadmap Part II): the ``.runmal`` archive grows.

Acceptance: character cards, lorebooks, and presets ride in the
portable archive with the same checksum discipline as every other
member (per-member SHA-256 in the manifest), and the archive
round-trips field-clean. Cards already rode as canonical rows; this
slice verifies their Part II growth is whole (P-025 version fields,
card_json unknown fields) and adds the missing piece: the P-024
library organisation (tags + favourite flags), which was user data
the archive silently left behind. Lorebooks (P-019) and presets
(P-021 interop carriage) are pinned field-for-field as well.

Backward compatibility: archives written before P-028 (no
``character_library`` members, no new count keys) still validate
and restore; FORMAT_VERSION stays 1 (the P-023 precedent: purely
additive member kinds do not bump it).
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import select

from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import (
    Character,
    CharacterOrganisation,
    CharacterTag,
    Lorebook,
    LoreEntry,
    SamplingPreset,
    SecretEntry,
    User,
)
from runmal.portable.archive import ArchiveError, export_archive, row_to_dict, validate_archive
from runmal.portable.restore import import_archive

SECRET_VALUE = "p028-secret-value-never-exported"


async def _seed(tmp_path, with_secret=True):
    """A small library: four cards (tagged+favourite, tagged,
    plain, favourite-only), a lorebook with entries, an interop-carried preset, and
    a second user's organised card that must never leak across."""
    src = tmp_path / "src"
    src.mkdir()
    db_path = src / "runmal.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    async with factory() as session:
        user = User(name="volmarr")
        other = User(name="stranger")
        session.add_all([user, other])
        await session.commit()

        card_json = json.dumps(
            {
                "spec": "chara_card_v3",
                "data": {
                    "name": "Yrsa",
                    "description": "Seidkona of the black fjord — þ, ð, ǫ.",
                    "tags": ["witch", "saga"],
                    "unknown_future_field": {"kept": ["verbatim", 42]},
                },
            }
        )
        char1 = Character(
            user_id=user.id,
            name="Yrsa",
            card_json=card_json,
            version_no=3,
            lineage_id="lineage-1",
            content_hash="a" * 64,
        )
        char2 = Character(user_id=user.id, name="Plain Tagged", card_json="{}")
        char3 = Character(user_id=user.id, name="Unorganised", card_json="{}")
        char4 = Character(user_id=user.id, name="Favourite Only", card_json="{}")
        foreign = Character(user_id=other.id, name="Foreign", card_json="{}")
        session.add_all([char1, char2, char3, char4, foreign])
        await session.commit()

        session.add_all(
            [
                CharacterTag(
                    character_id=char1.id, tag_key="witch", user_id=user.id, tag="Witch"
                ),
                CharacterTag(
                    character_id=char1.id, tag_key="saga", user_id=user.id, tag="Saga"
                ),
                CharacterTag(
                    character_id=char2.id, tag_key="witch", user_id=user.id, tag="Witch"
                ),
                CharacterTag(
                    character_id=foreign.id,
                    tag_key="foreign",
                    user_id=other.id,
                    tag="Foreign",
                ),
            ]
        )
        session.add(
            CharacterOrganisation(character_id=char1.id, user_id=user.id, is_favourite=True)
        )
        session.add(
            CharacterOrganisation(character_id=char4.id, user_id=user.id, is_favourite=False)
        )
        session.add(
            CharacterOrganisation(
                character_id=foreign.id, user_id=other.id, is_favourite=True
            )
        )
        book = Lorebook(user_id=user.id, name="sagas", description="world", scan_depth=7)
        session.add(book)
        await session.commit()
        session.add_all(
            [
                LoreEntry(
                    lorebook_id=book.id,
                    user_id=user.id,
                    name="odin",
                    keys_json='["odin", "all-father"]',
                    secondary_keys_json='["wisdom"]',
                    content="All-Father",
                    priority=42,
                    constant=True,
                ),
                LoreEntry(
                    lorebook_id=book.id,
                    user_id=user.id,
                    name="muted",
                    keys_json='["quiet"]',
                    content="disabled entry survives",
                    enabled=False,
                ),
            ]
        )
        session.add(
            SamplingPreset(
                user_id=user.id,
                name="calm",
                params_json='{"temperature": 0.7}',
                template_ref="chatml",
                source_format="sillytavern",
                interop_json='{"temperature": 0.7, "future_knob": true}',
            )
        )
        if with_secret:
            session.add(SecretEntry(ref="p028-ref", user_id=user.id, value=SECRET_VALUE))
        await session.commit()
        archive = tmp_path / "world.runmal"
        info = await export_archive(session, user.id, archive, base_dir=src)
        ids = {
            "user": user.id,
            "char1": char1.id,
            "char2": char2.id,
            "char3": char3.id,
            "char4": char4.id,
            "foreign": foreign.id,
            "book": book.id,
        }
        return archive, info, ids, factory


def _members(archive: Path) -> dict[str, bytes]:
    with zipfile.ZipFile(archive) as zf:
        return {name: zf.read(name) for name in zf.namelist()}


def _rewrite(archive: Path, members: dict[str, bytes]) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, blob in members.items():
            zf.writestr(name, blob)
    archive.write_bytes(buffer.getvalue())


async def test_export_bundles_and_checksums(tmp_path):
    archive, info, ids, _ = await _seed(tmp_path)
    members = _members(archive)
    bundles = sorted(n for n in members if n.startswith("character_library/"))
    assert set(bundles) == {
        f"character_library/{ids['char1']}.json",
        f"character_library/{ids['char2']}.json",
        f"character_library/{ids['char4']}.json",
    }
    bundle = json.loads(members[f"character_library/{ids['char1']}.json"])
    assert bundle["character_id"] == ids["char1"]
    assert [t["tag_key"] for t in bundle["tags"]] == ["saga", "witch"]
    assert [t["tag"] for t in bundle["tags"]] == ["Saga", "Witch"]
    assert bundle["organisation"]["is_favourite"] is True
    bundle2 = json.loads(members[f"character_library/{ids['char2']}.json"])
    assert bundle2["organisation"] is None and len(bundle2["tags"]) == 1
    bundle4 = json.loads(members[f"character_library/{ids['char4']}.json"])
    assert bundle4["tags"] == [] and bundle4["organisation"]["is_favourite"] is False

    manifest = validate_archive(archive)
    assert manifest["format_version"] == 1
    contents = manifest["contents"]
    assert contents["characters"] == 4
    assert contents["character_tags"] == 3
    assert contents["character_organisation"] == 2
    assert contents["lorebooks"] == 1 and contents["lore_entries"] == 2
    assert contents["presets"] == 1
    for name, expected in manifest["checksums"].items():
        assert hashlib.sha256(members[name]).hexdigest() == expected
    assert info.manifest["contents"] == contents


async def test_roundtrip_field_diff_clean(tmp_path):
    archive, _, ids, factory = await _seed(tmp_path)
    async with factory() as session:
        before = {
            "characters": [
                row_to_dict(r)
                for r in await session.scalars(select(Character).order_by(Character.id))
                if r.user_id == ids["user"]
            ],
            "tags": [
                row_to_dict(r)
                for r in await session.scalars(
                    select(CharacterTag).order_by(
                        CharacterTag.character_id, CharacterTag.tag_key
                    )
                )
                if r.user_id == ids["user"]
            ],
            "organisation": [
                row_to_dict(r)
                for r in await session.scalars(
                    select(CharacterOrganisation).order_by(CharacterOrganisation.character_id)
                )
                if r.user_id == ids["user"]
            ],
            "lorebooks": [
                row_to_dict(r) for r in await session.scalars(select(Lorebook))
            ],
            "entries": [
                row_to_dict(r)
                for r in await session.scalars(select(LoreEntry).order_by(LoreEntry.id))
            ],
            "presets": [
                row_to_dict(r) for r in await session.scalars(select(SamplingPreset))
            ],
        }
    report = await import_archive(archive, tmp_path / "restored")
    assert report.ok
    assert report.counts["character_tags"] == 3
    assert report.counts["character_organisation"] == 2
    assert report.counts["characters"] == 4
    assert report.counts["lore_entries"] == 2

    staged = create_session_factory(create_db_engine(Path(report.staged_db)))
    async with staged() as session:
        after = {
            "characters": [
                row_to_dict(r)
                for r in await session.scalars(select(Character).order_by(Character.id))
            ],
            "tags": [
                row_to_dict(r)
                for r in await session.scalars(
                    select(CharacterTag).order_by(
                        CharacterTag.character_id, CharacterTag.tag_key
                    )
                )
            ],
            "organisation": [
                row_to_dict(r)
                for r in await session.scalars(
                    select(CharacterOrganisation).order_by(CharacterOrganisation.character_id)
                )
            ],
            "lorebooks": [
                row_to_dict(r) for r in await session.scalars(select(Lorebook))
            ],
            "entries": [
                row_to_dict(r)
                for r in await session.scalars(select(LoreEntry).order_by(LoreEntry.id))
            ],
            "presets": [
                row_to_dict(r) for r in await session.scalars(select(SamplingPreset))
            ],
        }
    assert after == before
    card = next(c for c in after["characters"] if c["id"] == ids["char1"])
    assert card["version_no"] == 3 and card["lineage_id"] == "lineage-1"
    assert json.loads(card["card_json"])["data"]["unknown_future_field"] == {
        "kept": ["verbatim", 42]
    }
    assert after["presets"][0]["source_format"] == "sillytavern"
    assert after["presets"][0]["interop_json"] == '{"temperature": 0.7, "future_knob": true}'


async def test_tampered_bundle_rejected(tmp_path):
    archive, _, ids, _ = await _seed(tmp_path)
    members = _members(archive)
    name = f"character_library/{ids['char1']}.json"
    members[name] = members[name].replace(b"Witch", b"W1tch")
    assert members[name] != _members(archive)[name]
    _rewrite(archive, members)
    with pytest.raises(ArchiveError, match="checksum mismatch"):
        validate_archive(archive)
    staging = tmp_path / "restored"
    with pytest.raises(ArchiveError):
        await import_archive(archive, staging)
    assert not staging.exists()


async def test_unmanifested_member_rejected(tmp_path):
    archive, _, _, _ = await _seed(tmp_path)
    members = _members(archive)
    members["character_library/sneaked.json"] = b"{}"
    _rewrite(archive, members)
    with pytest.raises(ArchiveError, match="unmanifested"):
        validate_archive(archive)


async def test_pre_p028_archive_still_restores(tmp_path):
    archive, _, _, _ = await _seed(tmp_path)
    members = _members(archive)
    manifest = json.loads(members["manifest.json"])
    for name in [n for n in members if n.startswith("character_library/")]:
        del members[name]
        del manifest["checksums"][name]
    del manifest["contents"]["character_tags"]
    del manifest["contents"]["character_organisation"]
    members["manifest.json"] = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    _rewrite(archive, members)
    assert validate_archive(archive)["format_version"] == 1
    report = await import_archive(archive, tmp_path / "restored")
    assert report.ok
    assert report.counts.get("character_tags", 0) == 0
    assert report.counts.get("character_organisation", 0) == 0
    assert report.counts["characters"] == 4


async def test_owner_isolation_and_secret_absence(tmp_path):
    archive, _, ids, _ = await _seed(tmp_path)
    members = _members(archive)
    for blob in members.values():
        assert SECRET_VALUE.encode("utf-8") not in blob
        assert ids["foreign"].encode("utf-8") not in blob
    assert not any("foreign" in blob.decode("utf-8", "ignore") for blob in members.values())


async def test_reexport_of_restored_is_checksum_stable(tmp_path):
    archive, info, ids, _ = await _seed(tmp_path, with_secret=False)
    report = await import_archive(archive, tmp_path / "restored")
    staged = create_session_factory(create_db_engine(Path(report.staged_db)))
    second = tmp_path / "second.runmal"
    async with staged() as session:
        await export_archive(session, ids["user"], second, base_dir=tmp_path / "restored")
    first_manifest = info.manifest["checksums"]
    second_manifest = validate_archive(second)
    for name, digest in first_manifest.items():
        assert second_manifest["checksums"][name] == digest, name
    assert second_manifest["contents"] == info.manifest["contents"]


def _manifest_with(members: dict[str, bytes]) -> dict:
    return json.loads(members["manifest.json"])


def _seal(members: dict[str, bytes], name: str) -> None:
    """Re-seal one altered member: refresh manifest + its checksum."""
    manifest = _manifest_with(members)
    manifest["checksums"][name] = hashlib.sha256(members[name]).hexdigest()
    members["manifest.json"] = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


async def test_manifest_count_tamper_fails_restore(tmp_path):
    archive, _, _, _ = await _seed(tmp_path)
    members = _members(archive)
    manifest = _manifest_with(members)
    manifest["contents"]["character_tags"] = 99
    members["manifest.json"] = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    _rewrite(archive, members)
    validate_archive(archive)  # counts are a restore-time check
    staging = tmp_path / "restored"
    with pytest.raises(ArchiveError, match="count mismatches"):
        await import_archive(archive, staging)
    assert not staging.exists()


async def test_malformed_bundle_shape_rejected(tmp_path):
    archive, _, ids, _ = await _seed(tmp_path)
    members = _members(archive)
    name = f"character_library/{ids['char1']}.json"
    bundle = json.loads(members[name])
    del bundle["tags"]
    members[name] = json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()
    _seal(members, name)
    _rewrite(archive, members)
    with pytest.raises(ArchiveError, match="export schema"):
        validate_archive(archive)


async def test_duplicate_tag_in_bundle_fails_restore_cleanly(tmp_path):
    archive, _, ids, _ = await _seed(tmp_path)
    members = _members(archive)
    name = f"character_library/{ids['char1']}.json"
    bundle = json.loads(members[name])
    bundle["tags"].append(dict(bundle["tags"][0]))
    members[name] = json.dumps(bundle, sort_keys=True, separators=(",", ":")).encode()
    _seal(members, name)
    manifest = _manifest_with(members)
    manifest["contents"]["character_tags"] += 1
    members["manifest.json"] = json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    _rewrite(archive, members)
    validate_archive(archive)
    staging = tmp_path / "restored"
    with pytest.raises(Exception):
        await import_archive(archive, staging)
    assert not staging.exists()
