"""P-029 acceptance: provenance on import.

Roadmap line: *Provenance on import: where a card came from and
when, kept with it (creator credit survives in Runmal).*

Contract under test:
- Migration 0023 (PROVISIONAL -- the keeper may renumber it at
  banking if P-028 takes 0023) adds ``characters.provenance_json``;
  a legacy-style row (``provenance_json == '{}'``) serialises its
  provenance as None and is never backfilled.
- Every create path records a provenance snapshot at import time:
  the API JSON path is ``api_json`` with byte fields honestly null
  (a re-serialisation is never hashed and passed off as the
  original file's bytes); library uploads and folder imports are
  ``library_upload`` / ``library_folder`` with the original file's
  real SHA-256, byte length and basename; a copy is ``copy`` with
  ``parent_character_id`` set and byte fields null.
- The snapshot carries the card's own creator fields (creator,
  character_version, source list, creation/modification dates)
  plus the live stored-form ``content_hash`` at import time.
- An exact-duplicate re-import creates no row and leaves the
  first import's provenance untouched (first import wins); a
  changed same-name card becomes a new version carrying its OWN
  provenance, and the versions list/detail expose provenance.
- Update and editor rewrites never touch provenance.
- Provenance does not travel in card exports: exported v2/v3
  bytes contain neither the original filename nor the imported_at
  stamp, and the exported card's content identity is unchanged.
  Provenance DOES travel in the portable .runmal archive.

Fixtures are authored fresh here (P-005 discipline); helper
patterns mirror test_p025_character_versions.py and
test_p022_bulk_library_import.py.
"""

from __future__ import annotations

import base64
import hashlib
import json
import sqlite3
import struct
import zlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.cards import import_card
from runmal.cards.exporter import export_json
from runmal.characters import versioning
from runmal.characters.provenance import parse_provenance
from runmal.characters.service import (
    character_to_dict,
    create_character,
    get_character,
    list_characters,
)
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Character, User
from runmal.library.service import import_library_folder, import_library_uploads
from runmal.portable.archive import export_archive
from runmal.portable.restore import import_archive

# ---------------------------------------------------------------- helpers


@pytest.fixture(autouse=True)
def _isolated_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))


def card_dict(name="Sifna", **over):
    card = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": name,
        "description": "First description.",
        "personality": "Steady.",
        "scenario": "A test hall.",
        "first_mes": "Hail!",
        "mes_example": "",
        "creator_notes": "",
        "system_prompt": "",
        "post_history_instructions": "",
        "alternate_greetings": [],
        "tags": [],
        "creator": "prov-smith",
        "character_version": "1.0",
        "extensions": {},
    }
    card.update(over)
    return card


def v3_card_dict():
    return {
        "spec": "chara_card_v3",
        "spec_version": "3.0",
        "data": {
            "name": "Keeper of Provenance",
            "description": "A v3-shaped provenance test card.",
            "personality": "Precise.",
            "scenario": "The archive stair.",
            "first_mes": "Mind the record.",
            "mes_example": "",
            "creator_notes": "Notes.",
            "system_prompt": "",
            "post_history_instructions": "",
            "alternate_greetings": [],
            "tags": ["prov"],
            "creator": "prov-archivist",
            "character_version": "2.7",
            "source": [
                "https://example.invalid/cards/keeper",
                "Prov mirror",
            ],
            "creation_date": 1759000000,
            "modification_date": 1759600000,
            "extensions": {},
        },
    }


def _png_chunk(ctype: bytes, data: bytes) -> bytes:
    chunk = struct.pack(">I", len(data)) + ctype + data
    return chunk + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)


def make_png_card_bytes(name="Sifna Png", creator="png-smith") -> bytes:
    data = {
        "name": name,
        "description": "A PNG-carried provenance test card.",
        "personality": "Steady.",
        "scenario": "A test hall.",
        "first_mes": "Hail!",
        "mes_example": "",
        "creator_notes": "",
        "system_prompt": "",
        "post_history_instructions": "",
        "alternate_greetings": [],
        "tags": [],
        "creator": creator,
        "character_version": "1.2",
        "extensions": {},
    }
    obj = {"spec": "chara_card_v2", "spec_version": "2.0", "data": data}
    payload = b"chara\x00" + base64.b64encode(json.dumps(obj).encode())
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + _png_chunk(b"tEXt", payload)
        + _png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + _png_chunk(b"IEND", b"")
    )


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory, name="volmarr") -> str:
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


def post_card(client, card, name=None, expect=None):
    body = {"card": card}
    if name is not None:
        body["name"] = name
    resp = client.post("/api/v1/characters", json=body)
    if expect is not None:
        assert resp.status_code == expect, resp.text
    return resp


async def only_character_dict(factory, user_id) -> dict:
    async with factory() as session:
        rows = await list_characters(session, user_id)
        assert len(rows) == 1
        return character_to_dict(rows[0])


# ---------------------------------------------------------------- migration


def test_migration_head_is_0029_p037() -> None:
    """Head pin: the head moved with P-036's provisional 0028
    (0027 reserved for P-035), then with P-037's 0029; the keeper
    may renumber at banking, in which case this pin moves."""
    assert MIGRATIONS[-1][0] == "0032"
def test_migration_head_is_0030_provisional_p038() -> None:
    """Head pin: the head moved with P-038's provisional 0030
    (0029 reserved for P-037); the keeper may renumber at banking,
    in which case this pin moves with it."""
    assert MIGRATIONS[-1][0] == "0032"


def test_migration_0023_column_exists(tmp_path) -> None:
    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0032"
    conn = sqlite3.connect(db_path)
    try:
        columns = {
            row[1] for row in conn.execute("PRAGMA table_info(characters)")
        }
        assert "provenance_json" in columns
    finally:
        conn.close()


async def test_legacy_row_serialises_provenance_none(tmp_path) -> None:
    """A legacy-style row (provenance_json == '{}') serialises its
    provenance as None -- legacy rows are never backfilled."""
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    card = import_card(json.dumps(card_dict()).encode(), "card.json")
    stored_text = export_json(card, "2").decode("utf-8")
    async with factory() as session:
        legacy = Character(
            user_id=user_id,
            name="Sifna",
            card_json=stored_text,
            provenance_json="{}",
        )
        session.add(legacy)
        await session.commit()
        legacy_id = legacy.id
    async with factory() as session:
        row = await get_character(session, user_id, legacy_id)
        assert row is not None
        assert parse_provenance(row) is None
        assert character_to_dict(row)["provenance"] is None


# ---------------------------------------------------------------- API create


def test_api_create_provenance_is_api_json(app_client) -> None:
    created = post_card(app_client, card_dict(), expect=201).json()
    prov = created["provenance"]
    assert prov is not None
    assert prov["provenance_version"] == 1
    assert prov["source_kind"] == "api_json"
    assert prov["card_format"] == "json"
    # Creator snapshot equals the card's own creator field.
    assert prov["creator"] == "prov-smith"
    assert prov["character_version"] == "1.0"
    # Honesty: the API path never saw original file bytes, so the
    # byte facts are null -- never a hash of the re-serialised dict.
    assert prov["original_sha256"] is None
    assert prov["original_byte_length"] is None
    assert "original_filename" not in prov
    # Import stamp present, and the recorded identity is the live
    # effective stored-form hash.
    assert prov["imported_at"]
    assert prov["content_hash"] == created["content_hash"]


def test_api_create_v3_card_fields_snapshot(app_client) -> None:
    created = post_card(app_client, v3_card_dict(), expect=201).json()
    prov = created["provenance"]
    assert prov is not None
    assert prov["source_kind"] == "api_json"
    assert prov["spec_version"].startswith("3")
    assert prov["creator"] == "prov-archivist"
    assert prov["character_version"] == "2.7"
    assert prov["source"] == [
        "https://example.invalid/cards/keeper",
        "Prov mirror",
    ]
    assert prov["card_creation_date"] == 1759000000
    assert prov["card_modification_date"] == 1759600000
    assert prov["content_hash"] == created["content_hash"]


# ---------------------------------------------------------------- library paths


async def test_library_upload_png_byte_provenance(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    blob = make_png_card_bytes()
    async with factory() as session:
        report = await import_library_uploads(
            session, user_id, [("sifna-card.png", blob)]
        )
    entry = report.entries[0]
    assert entry.outcome == "accepted"
    assert entry.created_id
    shown = await only_character_dict(factory, user_id)
    prov = shown["provenance"]
    assert prov is not None
    assert prov["source_kind"] == "library_upload"
    # Byte honesty: the recorded hash/length are the uploaded
    # file's own, not the normalised stored form's.
    assert prov["original_sha256"] == hashlib.sha256(blob).hexdigest()
    assert prov["original_byte_length"] == len(blob)
    assert prov["original_filename"] == "sifna-card.png"
    assert prov["card_format"] == "png"
    assert prov["creator"] == "png-smith"
    assert prov["content_hash"] == shown["content_hash"]
    assert prov["content_hash"] != prov["original_sha256"]
    assert prov["imported_at"]


async def test_library_upload_json_byte_provenance(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    # Indent + trailing newline: the uploaded bytes deliberately
    # differ from the normalised stored form.
    blob = (json.dumps(card_dict(), indent=1) + "\n").encode()
    async with factory() as session:
        report = await import_library_uploads(
            session, user_id, [("sifna-original.json", blob)]
        )
    entry = report.entries[0]
    assert entry.outcome == "accepted"
    shown = await only_character_dict(factory, user_id)
    prov = shown["provenance"]
    assert prov is not None
    assert prov["source_kind"] == "library_upload"
    assert prov["original_sha256"] == hashlib.sha256(blob).hexdigest()
    assert prov["original_byte_length"] == len(blob)
    assert prov["original_filename"] == "sifna-original.json"
    assert prov["card_format"] == "json"
    assert prov["content_hash"] == shown["content_hash"]
    assert prov["content_hash"] != prov["original_sha256"]


async def test_library_folder_provenance(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    blob = json.dumps(card_dict()).encode()
    folder = tmp_path / "library"
    target = folder / "shelf" / "sifna-folder.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(blob)
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    entry = report.entries[0]
    assert entry.outcome == "accepted"
    assert entry.relpath == "shelf/sifna-folder.json"
    shown = await only_character_dict(factory, user_id)
    prov = shown["provenance"]
    assert prov is not None
    assert prov["source_kind"] == "library_folder"
    assert prov["original_sha256"] == hashlib.sha256(blob).hexdigest()
    assert prov["original_byte_length"] == len(blob)
    # Only the basename is kept as the filename; the folder
    # structure rides separately as the relpath.
    assert prov["original_filename"] == "sifna-folder.json"
    assert prov["relpath"] == "shelf/sifna-folder.json"
    assert prov["content_hash"] == shown["content_hash"]


# ---------------------------------------------------------------- duplicates & versions


def test_exact_duplicate_reimport_keeps_first_provenance(app_client) -> None:
    first = post_card(app_client, card_dict(), expect=201).json()
    again = post_card(app_client, card_dict(), expect=200)
    payload = again.json()
    assert payload["duplicate_exact"] is True
    assert payload["id"] == first["id"]
    # No new record is stored on a duplicate re-import: the
    # sibling's provenance -- imported_at included -- is the
    # first import's, unchanged (first import wins).
    assert payload["provenance"] == first["provenance"]
    fetched = app_client.get(f"/api/v1/characters/{first['id']}").json()
    assert fetched["provenance"] == first["provenance"]
    assert fetched["provenance"]["imported_at"] == (
        first["provenance"]["imported_at"]
    )
    listed = app_client.get("/api/v1/characters").json()
    assert [c["id"] for c in listed] == [first["id"]]


def test_new_version_has_own_provenance(app_client) -> None:
    first = post_card(app_client, card_dict(), expect=201).json()
    second = post_card(
        app_client,
        card_dict(description="Second description."),
        expect=201,
    ).json()
    assert second["version_no"] == 2
    prov1 = first["provenance"]
    prov2 = second["provenance"]
    # The new version carries its OWN provenance snapshot...
    assert prov2["source_kind"] == "api_json"
    assert prov2["content_hash"] == second["content_hash"]
    assert prov2["content_hash"] != prov1["content_hash"]
    assert prov2["imported_at"] != prov1["imported_at"]
    # ...and the first version's record is untouched.
    fetched_first = app_client.get(
        f"/api/v1/characters/{first['id']}"
    ).json()
    assert fetched_first["provenance"] == prov1
    # The versions list and detail expose each row's provenance.
    listing = app_client.get(
        f"/api/v1/characters/{first['id']}/versions"
    ).json()
    by_no = {v["version_no"]: v for v in listing["versions"]}
    assert by_no[1]["provenance"] == prov1
    assert by_no[2]["provenance"] == prov2
    detail2 = app_client.get(
        f"/api/v1/characters/{first['id']}/versions/2"
    ).json()
    assert detail2["provenance"] == prov2
    detail1 = app_client.get(
        f"/api/v1/characters/{first['id']}/versions/1"
    ).json()
    assert detail1["provenance"] == prov1


# ---------------------------------------------------------------- copy


def test_copy_provenance(app_client) -> None:
    first = post_card(app_client, card_dict(), expect=201).json()
    resp = app_client.post(f"/api/v1/characters/{first['id']}/duplicate")
    assert resp.status_code == 201, resp.text
    copy = resp.json()
    assert copy["name"] == "Sifna (copy)"
    prov = copy["provenance"]
    assert prov is not None
    assert prov["source_kind"] == "copy"
    assert prov["parent_character_id"] == first["id"]
    # A copy has no original file: byte facts stay honestly null.
    assert prov["original_sha256"] is None
    assert prov["original_byte_length"] is None
    assert "original_filename" not in prov
    assert prov["content_hash"] == copy["content_hash"]
    assert prov["imported_at"]
    # The source's own provenance is untouched by the copy.
    fetched = app_client.get(f"/api/v1/characters/{first['id']}").json()
    assert fetched["provenance"] == first["provenance"]


# ---------------------------------------------------------------- update / editor


def test_update_and_editor_do_not_change_provenance(app_client) -> None:
    created = post_card(app_client, card_dict(), expect=201).json()
    prov_before = created["provenance"]
    cid = created["id"]
    patched = app_client.patch(
        f"/api/v1/characters/{cid}",
        json={"card": card_dict(description="Patched description.")},
    )
    assert patched.status_code == 200, patched.text
    # The content moved; the import record did not.
    assert patched.json()["content_hash"] != created["content_hash"]
    assert patched.json()["provenance"] == prov_before
    edited = app_client.patch(
        f"/api/v1/characters/{cid}/editor",
        json={"description": "Editor description."},
    )
    assert edited.status_code == 200, edited.text
    fetched = app_client.get(f"/api/v1/characters/{cid}").json()
    assert fetched["provenance"] == prov_before


# ---------------------------------------------------------------- export


async def test_export_does_not_carry_provenance(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    blob = json.dumps(card_dict()).encode()
    async with factory() as session:
        report = await import_library_uploads(
            session, user_id, [("sifna-original-name.json", blob)]
        )
    assert report.entries[0].outcome == "accepted"
    async with factory() as session:
        rows = await list_characters(session, user_id)
        assert len(rows) == 1
        row = rows[0]
        shown = character_to_dict(row)
        stored_text = row.card_json
    prov = shown["provenance"]
    assert prov["original_filename"] == "sifna-original-name.json"
    card = import_card(stored_text.encode(), "card.json")
    for spec in ("2", "3"):
        exported = export_json(card, spec)
        # Provenance stays home: neither the original filename
        # nor the import stamp rides in a card export. (The
        # creator credit inside the card itself does travel --
        # it is card content, not provenance.)
        assert b"sifna-original-name" not in exported
        assert prov["imported_at"].encode() not in exported
    # Export is a read: the v2 export IS the stored form, so the
    # exported card's content identity is unchanged, and a
    # re-import of the export hashes to the same identity.
    exported_v2 = export_json(card, "2")
    assert hashlib.sha256(exported_v2).hexdigest() == shown["content_hash"]
    reimported = import_card(exported_v2, "card.json")
    assert versioning.content_hash_of(
        export_json(reimported, "2").decode("utf-8")
    ) == shown["content_hash"]


# ---------------------------------------------------------------- .runmal round-trip


async def test_runmal_archive_roundtrip_preserves_provenance(tmp_path) -> None:
    """Provenance travels via the portable .runmal archive: a
    character exported and restored into a fresh staging install
    keeps its provenance record exactly."""
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        created = await create_character(session, user_id, card_dict())
        char_id = created.id
    async with factory() as session:
        row = await get_character(session, user_id, char_id)
        assert row is not None
        before = character_to_dict(row)["provenance"]
    assert before is not None
    assert before["source_kind"] == "api_json"

    archive = tmp_path / "world.runmal"
    base_dir = tmp_path / "src"
    base_dir.mkdir()
    async with factory() as session:
        await export_archive(session, user_id, archive, base_dir=base_dir)
    staging = tmp_path / "restored"
    report = await import_archive(archive, staging)
    assert report.ok
    assert report.counts["characters"] == 1

    restored_factory = create_session_factory(
        create_db_engine(Path(report.staged_db))
    )
    async with restored_factory() as session:
        restored = await session.get(Character, char_id)
        assert restored is not None
        assert parse_provenance(restored) == before
        assert character_to_dict(restored)["provenance"] == before
