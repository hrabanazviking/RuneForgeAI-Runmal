"""P-045 acceptance: lorebook sharing packs.

Roadmap line: *Book sharing: lorebooks as importable packs
(Part XII's hub carries them).*

Contract under test:
- ``runmal.lorebooks.packs`` mints a pack: a single JSON
  envelope (format ``runmal-lorebook-pack``, version 1,
  schema ``runmal-p045-lorebook-pack-v1``) around the
  UNCHANGED ``transfer.export_book`` native payload, adding a
  manifest (book name, entry count, content SHA-256,
  canonical payload byte length) and an honest provenance
  record (P-029 rules: unknown facts omitted, never
  fabricated; a bare-payload pack carries no source_book_id).
- The content checksum is defined over the payload's
  NORMALISED form (what ``transfer.parse_import`` would
  store), entries sorted, so entry order and cosmetic
  payload spellings are not part of a book's identity.
- ``parse_pack``/``inspect_pack`` validate everything before
  any write exists: format/version/kind, manifest against
  payload (name, count, byte length, payload format/version),
  the checksum (any tampering refused), provenance presence,
  and the payload through the import path's own validation.
- Import never silently overwrites (P-025 precedent): an
  exact duplicate (same content checksum, same owner)
  returns the existing book unwritten; a same-name
  different-contents import creates a FRESH book by default
  (``name_collision`` flagged, original untouched) or
  refuses under ``on_conflict="reject"``. Another owner's
  identical book is NOT this owner's duplicate — a shared
  pack imports as the receiver's own copy.
- Round trip: book -> pack -> import (fresh owner) -> pack
  again yields the same content checksum, and the imported
  book's entries match field-for-field.
- Surfaces: ``GET /lorebooks/{id}/pack``,
  ``POST /lorebooks/import-pack`` (201 created / 200 exact
  duplicate), ``POST /lorebooks/pack/inspect`` (no write).
  The two POST routes are registered before the
  ``/lorebooks/{book_id}`` family so they are not swallowed.
- No migration: the schema head stays 0032.
- Review fixes (builder-3): canonical identity fills the
  stored book-field defaults, so a world-info-SHAPED pack
  checksum-matches the book it imports as (duplicate
  detection cannot silently miss it); malformed entries
  (non-object entry, scalar keys) refuse as PackError --
  the router's 422 -- never a bare 500; a provenance
  content_sha256 that disagrees with the manifest is
  refused; build_pack_from_native_payload requires the
  native shape (world-info files pack via
  build_pack_from_file).

Fixtures are authored fresh here (P-005 discipline).
"""

from __future__ import annotations

import copy
import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.lorebooks import packs, service, transfer
from runmal.lorebooks.interop import parse_lorebook_file
from runmal.lorebooks.packs import PackError

STAMP = "2026-11-06T12:00:00+00:00"


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_factory(tmp_path):
    db_path = tmp_path / "svc.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def seed_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


def sample_book():
    return {
        "id": "book-1",
        "name": "Fjord Sagas",
        "description": "World lore — þ, ð, ǫ.",
        "scan_depth": 7,
        "token_budget": 900,
        "scan_mode": "depth",
        "scan_external_context": False,
        "created_at": "2026-01-01T00:00:00+00:00",
        "entry_count": 2,
    }


def sample_entries():
    return [
        {
            "id": "e1",
            "lorebook_id": "book-1",
            "name": "Niflheim",
            "content": "The mist world.",
            "keys": ["niflheim", "mist"],
            "secondary_keys": ["cold"],
            "selective_logic": "and_any",
            "inclusion_group": "",
            "group_weight": 100,
            "probability": 100,
            "priority": 120,
            "position": "before_char",
            "depth": None,
            "role": "system",
            "enabled": True,
            "constant": False,
            "vectorised": False,
            "case_sensitive": False,
            "whole_word": True,
            "sticky_prompts": 1,
            "cooldown_prompts": 0,
            "delay_prompts": 0,
            "created_at": "2026-01-01T00:00:00+00:00",
            "updated_at": None,
        },
        {
            "id": "e2",
            "lorebook_id": "book-1",
            "name": "Seiðr",
            "content": "The witch's art.",
            "keys": ["seiðr"],
            "secondary_keys": [],
            "selective_logic": "and_any",
            "inclusion_group": "arts",
            "group_weight": 80,
            "probability": 50,
            "priority": 90,
            "position": "at_depth",
            "depth": 2,
            "role": "user",
            "enabled": True,
            "constant": True,
            "vectorised": True,
            "case_sensitive": True,
            "whole_word": False,
            "sticky_prompts": 0,
            "cooldown_prompts": 3,
            "delay_prompts": 1,
            "created_at": "2026-01-01T00:01:00+00:00",
            "updated_at": None,
        },
    ]


def sample_pack():
    return packs.build_pack(sample_book(), sample_entries(), exported_at=STAMP)


# ------------------------------------------------------------------
# Minting + checksum identity (pure)


def test_build_pack_envelope_and_manifest():
    pack = sample_pack()
    assert pack["format"] == "runmal-lorebook-pack"
    assert pack["pack_version"] == 1
    assert pack["kind"] == "lorebook"
    assert pack["schema"] == "runmal-p045-lorebook-pack-v1"
    manifest = pack["manifest"]
    assert manifest["book_name"] == "Fjord Sagas"
    assert manifest["entry_count"] == 2
    assert manifest["payload_format"] == "runmal-lorebook"
    assert manifest["payload_version"] == 1
    assert manifest["payload_canonical_bytes"] > 0
    # The payload is the unchanged native export.
    assert pack["lorebook"] == transfer.export_book(sample_book(), sample_entries())
    # Provenance: stored-book facts present, stamp honoured.
    prov = pack["provenance"]
    assert prov["source_kind"] == "lorebook_pack_export"
    assert prov["source_book_id"] == "book-1"
    assert prov["source_book_name"] == "Fjord Sagas"
    assert prov["exported_at"] == STAMP
    assert prov["content_sha256"] == manifest["content_sha256"]
    assert "note" not in prov  # never fabricated


def test_build_pack_note_only_when_supplied():
    pack = packs.build_pack(
        sample_book(), sample_entries(), exported_at=STAMP, note="for the hub"
    )
    assert pack["provenance"]["note"] == "for the hub"


def test_checksum_ignores_entry_order():
    forward = packs.content_checksum(
        transfer.export_book(sample_book(), sample_entries())
    )
    backward = packs.content_checksum(
        transfer.export_book(sample_book(), list(reversed(sample_entries())))
    )
    assert forward == backward


def test_checksum_ignores_cosmetic_spellings():
    payload = transfer.export_book(sample_book(), sample_entries())
    cosmetic = copy.deepcopy(payload)
    # Defaults spelled out / folded spellings the import path
    # normalises away must not mint a different identity.
    cosmetic["entries"][0]["use_probability"] = True
    cosmetic["entries"][0]["probability"] = "100"
    assert packs.content_checksum(cosmetic) == packs.content_checksum(payload)


def test_checksum_changes_with_content():
    payload = transfer.export_book(sample_book(), sample_entries())
    altered = copy.deepcopy(payload)
    altered["entries"][0]["content"] = "Different mist."
    assert packs.content_checksum(altered) != packs.content_checksum(payload)


def test_build_pack_from_payload_omits_unknown_source_id():
    payload = transfer.export_book(sample_book(), sample_entries())
    pack = packs.build_pack_from_native_payload(payload, exported_at=STAMP)
    assert "source_book_id" not in pack["provenance"]
    assert pack["provenance"]["source_book_name"] == "Fjord Sagas"


def test_build_pack_from_file_model():
    book_file = parse_lorebook_file(
        json.dumps(
            {
                "name": "File Book",
                "entries": {
                    "0": {
                        "key": ["alpha"],
                        "content": "Alpha lore.",
                        "comment": "Alpha",
                    }
                },
            }
        )
    )
    pack = packs.build_pack_from_file(book_file, exported_at=STAMP)
    assert pack["manifest"]["book_name"] == "File Book"
    assert pack["manifest"]["entry_count"] == 1
    assert "source_book_id" not in pack["provenance"]
    parsed = packs.parse_pack(pack)
    assert parsed["lorebook"]["entries"][0]["content"] == "Alpha lore."


def test_empty_book_pack_round_trips_pure():
    book = sample_book()
    pack = packs.build_pack(book, [], exported_at=STAMP)
    assert pack["manifest"]["entry_count"] == 0
    report = packs.inspect_pack(pack)
    assert report["valid"] is True
    assert report["entry_count"] == 0


# ------------------------------------------------------------------
# Parse / inspect validation (pure)


def test_parse_pack_bytes_and_str_round_trip():
    pack = sample_pack()
    blob = packs.pack_to_bytes(pack)
    assert packs.parse_pack(blob)["manifest"] == pack["manifest"]
    assert packs.parse_pack(blob.decode("utf-8"))["lorebook"] == pack["lorebook"]


def test_pack_reserialisation_does_not_invalidate():
    pack = sample_pack()
    compact = json.dumps(pack, separators=(",", ":")).encode("utf-8")
    assert packs.inspect_pack(compact)["checksum_verified"] is True


def test_tampered_entry_refused():
    pack = sample_pack()
    pack["lorebook"]["entries"][0]["content"] = "Forged mist."
    with pytest.raises(PackError, match="checksum mismatch"):
        packs.parse_pack(pack)


def test_tampered_manifest_fields_refused():
    pack = sample_pack()
    pack["manifest"]["entry_count"] = 99
    with pytest.raises(PackError, match="entry_count"):
        packs.parse_pack(pack)
    pack = sample_pack()
    pack["manifest"]["book_name"] = "Other Book"
    with pytest.raises(PackError, match="book_name"):
        packs.parse_pack(pack)
    pack = sample_pack()
    pack["manifest"]["payload_canonical_bytes"] += 1
    with pytest.raises(PackError, match="payload_canonical_bytes"):
        packs.parse_pack(pack)


def test_envelope_refusals():
    with pytest.raises(PackError, match="format"):
        packs.parse_pack({"format": "other", "pack_version": 1})
    pack = sample_pack()
    pack["pack_version"] = 2
    with pytest.raises(PackError, match="unsupported lorebook pack version 2"):
        packs.parse_pack(pack)
    pack = sample_pack()
    del pack["provenance"]
    with pytest.raises(PackError, match="provenance"):
        packs.parse_pack(pack)
    pack = sample_pack()
    del pack["manifest"]
    with pytest.raises(PackError, match="manifest"):
        packs.parse_pack(pack)
    with pytest.raises(PackError):
        packs.parse_pack(b"{not json")
    with pytest.raises(PackError, match="must be a JSON object"):
        packs.parse_pack(b"[1, 2]")


def test_unknown_top_level_keys_tolerated():
    pack = sample_pack()
    pack["hub_annotation"] = {"carrier": "part-xii", "pinned": True}
    assert packs.inspect_pack(pack)["valid"] is True


def test_inspect_reports_provenance_verbatim():
    pack = sample_pack()
    pack["provenance"]["custom_origin"] = {"site": "friend-instance"}
    report = packs.inspect_pack(pack)
    assert report["provenance"]["custom_origin"] == {"site": "friend-instance"}
    assert report["book_name"] == "Fjord Sagas"
    assert report["checksum_verified"] is True


def test_oversize_input_refused(monkeypatch):
    monkeypatch.setattr(packs, "MAX_PACK_BYTES", 64)
    blob = packs.pack_to_bytes(sample_pack())
    assert len(blob) > 64
    with pytest.raises(PackError):
        packs.parse_pack(blob)


def test_no_migration_head_stays_0032():
    assert MIGRATIONS[-1][0] == "0035"  # head moved by P-057 (PROVISIONAL 0035)


# ------------------------------------------------------------------
# Import discipline (service level)


async def _make_book(factory, user_id, name="Fjord Sagas", content="The mist world."):
    async with factory() as session:
        book = await service.create_lorebook(session, user_id, name=name)
        await service.create_entry(
            session,
            user_id,
            book.id,
            name="Niflheim",
            content=content,
            keys=["niflheim"],
            priority=120,
        )
        return book.id


async def _export_pack(factory, user_id, book_id):
    async with factory() as session:
        book = await service.get_lorebook(session, user_id, book_id)
        entries = await service.list_entries(session, user_id, book_id) or []
        return packs.build_pack(
            service.lorebook_to_dict(book, len(entries)),
            [service.entry_to_dict(e) for e in entries],
            exported_at=STAMP,
        )


async def test_import_into_fresh_library_creates_copy(tmp_path):
    factory = make_factory(tmp_path)
    owner = await seed_user(factory, "owner")
    receiver = await seed_user(factory, "receiver")
    book_id = await _make_book(factory, owner)
    pack = await _export_pack(factory, owner, book_id)
    async with factory() as session:
        book, report = await packs.import_pack(session, receiver, pack)
        assert report["created"] is True
        assert report["duplicate_exact"] is False
        assert report["name_collision"] is False
        assert report["provenance"]["source_book_id"] == book_id
        assert book.id != book_id
        assert book.user_id == receiver
        entries = await service.list_entries(session, receiver, book.id)
        assert len(entries) == 1
        assert entries[0].content == "The mist world."


async def test_exact_duplicate_returns_existing_unwritten(tmp_path):
    factory = make_factory(tmp_path)
    owner = await seed_user(factory)
    book_id = await _make_book(factory, owner)
    pack = await _export_pack(factory, owner, book_id)
    async with factory() as session:
        book, report = await packs.import_pack(session, owner, pack)
        assert book.id == book_id
        assert report["created"] is False
        assert report["duplicate_exact"] is True
        assert report["name_collision"] is False
        books = await service.list_lorebooks(session, owner)
        assert len(books) == 1


async def test_same_name_different_content_creates_fresh_book(tmp_path):
    factory = make_factory(tmp_path)
    owner = await seed_user(factory)
    first_id = await _make_book(factory, owner, content="First telling.")
    other = await seed_user(factory, "other")
    changed_id = await _make_book(factory, other, content="Second telling.")
    pack = await _export_pack(factory, other, changed_id)
    async with factory() as session:
        book, report = await packs.import_pack(session, owner, pack)
        assert report["created"] is True
        assert report["name_collision"] is True
        assert book.id not in (first_id, changed_id)
        original = await service.get_lorebook(session, owner, first_id)
        entries = await service.list_entries(session, owner, first_id)
        assert entries[0].content == "First telling."  # untouched
        books = await service.list_lorebooks(session, owner)
        assert len(books) == 2
        assert original.name == "Fjord Sagas"


async def test_same_name_reject_mode_refuses_and_writes_nothing(tmp_path):
    factory = make_factory(tmp_path)
    owner = await seed_user(factory)
    await _make_book(factory, owner, content="First telling.")
    other = await seed_user(factory, "other")
    changed_id = await _make_book(factory, other, content="Second telling.")
    pack = await _export_pack(factory, other, changed_id)
    async with factory() as session:
        with pytest.raises(PackError, match="already exists"):
            await packs.import_pack(session, owner, pack, on_conflict="reject")
        books = await service.list_lorebooks(session, owner)
        assert len(books) == 1


async def test_import_unknown_conflict_mode_refused(tmp_path):
    factory = make_factory(tmp_path)
    owner = await seed_user(factory)
    async with factory() as session:
        with pytest.raises(PackError, match="on_conflict"):
            await packs.import_pack(
                session, owner, sample_pack(), on_conflict="merge"
            )


async def test_round_trip_checksum_stable_across_owners(tmp_path):
    factory = make_factory(tmp_path)
    owner = await seed_user(factory, "owner")
    receiver = await seed_user(factory, "receiver")
    book_id = await _make_book(factory, owner)
    pack = await _export_pack(factory, owner, book_id)
    async with factory() as session:
        book, _report = await packs.import_pack(session, receiver, pack)
        new_book_id = book.id
    pack2 = await _export_pack(factory, receiver, new_book_id)
    assert pack2["manifest"]["content_sha256"] == pack["manifest"]["content_sha256"]


async def test_imported_entries_field_for_field(tmp_path):
    factory = make_factory(tmp_path)
    owner = await seed_user(factory, "owner")
    receiver = await seed_user(factory, "receiver")
    async with factory() as session:
        book = await service.create_lorebook(
            session, owner, name="Deep Book", description="d", scan_depth=7,
            token_budget=900,
        )
        await service.create_entry(
            session, owner, book.id, name="Seiðr", content="The witch's art.",
            keys=["seiðr"], secondary_keys=["galdr"], selective_logic="and_any",
            inclusion_group="arts", group_weight=80, probability=50,
            priority=90, position="at_depth", depth=2, role="user",
            enabled=True, constant=True, vectorised=True,
            case_sensitive=True, whole_word=False, sticky_prompts=0,
            cooldown_prompts=3, delay_prompts=1,
        )
        book_id = book.id
    pack = await _export_pack(factory, owner, book_id)
    async with factory() as session:
        imported, _report = await packs.import_pack(session, receiver, pack)
        entries = await service.list_entries(session, receiver, imported.id)
        assert len(entries) == 1
        got = service.entry_to_dict(entries[0])
    want = transfer.export_book(
        {"name": "Deep Book", "description": "d", "scan_depth": 7,
         "token_budget": 900, "scan_mode": "depth",
         "scan_external_context": False},
        [got],
    )
    assert want["entries"][0]["name"] == "Seiðr"
    assert want["entries"][0]["keys"] == ["seiðr"]
    assert want["entries"][0]["probability"] == 50
    assert want["entries"][0]["position"] == "at_depth"
    assert want["entries"][0]["depth"] == 2
    assert want["entries"][0]["role"] == "user"
    assert want["entries"][0]["cooldown_prompts"] == 3


# ------------------------------------------------------------------
# API surface


def _api_book_with_entry(client):
    created = client.post("/api/v1/lorebooks", json={"name": "Fjord Sagas"})
    assert created.status_code == 201, created.text
    book_id = created.json()["id"]
    entry = client.post(
        f"/api/v1/lorebooks/{book_id}/entries",
        json={"name": "Niflheim", "content": "The mist world.",
              "keys": ["niflheim"], "priority": 120},
    )
    assert entry.status_code == 201, entry.text
    return book_id


def test_api_export_pack_and_inspect(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book_id = _api_book_with_entry(client)
    resp = client.get(f"/api/v1/lorebooks/{book_id}/pack")
    assert resp.status_code == 200, resp.text
    pack = resp.json()
    assert pack["format"] == "runmal-lorebook-pack"
    assert pack["provenance"]["source_book_id"] == book_id
    inspected = client.post("/api/v1/lorebooks/pack/inspect", json=pack)
    assert inspected.status_code == 200, inspected.text
    assert inspected.json()["valid"] is True
    # Inspect wrote nothing: still one book.
    assert len(client.get("/api/v1/lorebooks").json()) == 1


def test_api_import_pack_duplicate_then_fresh(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book_id = _api_book_with_entry(client)
    pack = client.get(f"/api/v1/lorebooks/{book_id}/pack").json()
    # Same owner re-import: exact duplicate, 200, no new book.
    dup = client.post("/api/v1/lorebooks/import-pack", json=pack)
    assert dup.status_code == 200, dup.text
    assert dup.json()["pack_import"]["duplicate_exact"] is True
    assert dup.json()["id"] == book_id
    assert len(client.get("/api/v1/lorebooks").json()) == 1
    # Tampered pack refused.
    forged = copy.deepcopy(pack)
    forged["lorebook"]["entries"][0]["content"] = "Forged."
    bad = client.post("/api/v1/lorebooks/import-pack", json=forged)
    assert bad.status_code == 422, bad.text
    # Changed contents under the same name: fresh book, 201.
    changed = copy.deepcopy(pack)
    changed["lorebook"]["entries"][0]["content"] = "Another telling."
    changed["manifest"]["content_sha256"] = packs.content_checksum(
        changed["lorebook"]
    )
    changed["manifest"]["payload_canonical_bytes"] = len(
        packs._canonical_bytes(packs.canonical_payload(changed["lorebook"]))
    )
    changed["provenance"]["content_sha256"] = changed["manifest"]["content_sha256"]
    made = client.post("/api/v1/lorebooks/import-pack", json=changed)
    assert made.status_code == 201, made.text
    assert made.json()["pack_import"]["name_collision"] is True
    assert made.json()["id"] != book_id
    assert len(client.get("/api/v1/lorebooks").json()) == 2
    # A third telling under reject mode: name collides, contents
    # match no owned book, so the import refuses outright.
    third = copy.deepcopy(changed)
    third["lorebook"]["entries"][0]["content"] = "A third telling."
    third["manifest"]["content_sha256"] = packs.content_checksum(
        third["lorebook"]
    )
    third["manifest"]["payload_canonical_bytes"] = len(
        packs._canonical_bytes(packs.canonical_payload(third["lorebook"]))
    )
    third["provenance"]["content_sha256"] = third["manifest"]["content_sha256"]
    rejected = client.post(
        "/api/v1/lorebooks/import-pack?on_conflict=reject", json=third
    )
    assert rejected.status_code == 422, rejected.text
    assert len(client.get("/api/v1/lorebooks").json()) == 2


def test_api_pack_unknown_book_404(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    assert client.get("/api/v1/lorebooks/nope/pack").status_code == 404


def test_api_inspect_tampered_pack_422(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    pack = sample_pack()
    pack["lorebook"]["entries"][1]["keys"] = ["forged"]
    resp = client.post("/api/v1/lorebooks/pack/inspect", json=pack)
    assert resp.status_code == 422, resp.text
# ------------------------------------------------------------------
# Review fixes (builder-3 Mediums)


def _hand_pack(payload):
    """A pack envelope built by hand around any payload shape,
    with a correct manifest -- the foreign-pack case."""
    book_fields, entry_fields = transfer.parse_import(payload)
    checksum = packs.content_checksum(payload)
    return {
        "format": "runmal-lorebook-pack",
        "pack_version": 1,
        "kind": "lorebook",
        "schema": "runmal-p045-lorebook-pack-v1",
        "manifest": {
            "book_name": book_fields["name"],
            "entry_count": len(entry_fields),
            "content_sha256": checksum,
            "payload_canonical_bytes": len(
                packs._canonical_bytes(packs.canonical_payload(payload))
            ),
            "exported_at": STAMP,
            "app_version": "0.1.0",
        },
        "provenance": {
            "provenance_version": 1,
            "source_kind": "lorebook_pack_export",
            "source_book_name": book_fields["name"],
            "exported_at": STAMP,
            "content_sha256": checksum,
        },
        "lorebook": payload,
    }


def test_build_rejects_worldinfo_shaped_payload():
    worldinfo = {
        "name": "WI Book",
        "entries": {"0": {"key": ["a"], "content": "A.", "comment": "A"}},
    }
    with pytest.raises(PackError, match="native runmal-lorebook shape"):
        packs.build_pack_from_native_payload(worldinfo, exported_at=STAMP)


async def test_worldinfo_shaped_pack_duplicate_detected(tmp_path):
    factory = make_factory(tmp_path)
    receiver = await seed_user(factory, "receiver")
    worldinfo = {
        "name": "Shared WI Book",
        "entries": {
            "0": {"key": ["mist"], "content": "Mist lore.", "comment": "Mist"}
        },
    }
    pack = _hand_pack(worldinfo)
    async with factory() as session:
        book, report = await packs.import_pack(session, receiver, pack)
        assert report["created"] is True
        book2, report2 = await packs.import_pack(session, receiver, pack)
        assert book2.id == book.id
        assert report2["duplicate_exact"] is True
        books = await service.list_lorebooks(session, receiver)
        assert len(books) == 1


def test_malformed_entries_refuse_as_packerror():
    payload = transfer.export_book(sample_book(), sample_entries())
    bad = copy.deepcopy(payload)
    bad["entries"] = [42]
    with pytest.raises(PackError):
        packs.parse_pack(_hand_pack_loose(bad))
    bad2 = copy.deepcopy(payload)
    bad2["entries"][0]["keys"] = 42
    with pytest.raises(PackError):
        packs.content_checksum(bad2)


def _hand_pack_loose(payload):
    """Envelope with manifest fields copied from a valid pack
    where possible; parse must refuse on the PAYLOAD, before
    manifest cross-checks can pass it."""
    pack = sample_pack()
    pack["lorebook"] = payload
    return pack


def test_provenance_checksum_mismatch_refused():
    pack = sample_pack()
    pack["provenance"]["content_sha256"] = "0" * 64
    with pytest.raises(PackError, match="provenance content_sha256"):
        packs.parse_pack(pack)


def test_api_malformed_pack_is_422_not_500(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    pack = sample_pack()
    pack["lorebook"]["entries"] = [42]
    resp = client.post("/api/v1/lorebooks/pack/inspect", json=pack)
    assert resp.status_code == 422, resp.text
    resp2 = client.post("/api/v1/lorebooks/import-pack", json=pack)
    assert resp2.status_code == 422, resp2.text
