"""P-030 acceptance: Part II gate — a stranger's library imports whole with an honest report.

Roadmap: Part II gate (P-030). The stranger's library legs: a whole
folder of somebody else's cards + lorebooks goes through bulk import
(P-022) and every file is accounted for exactly once — accepted,
repaired, refused with a reason, or skipped — with the report
matching the database reality; the shapes bulk import refuses
(presets P-021, personas P-018, chats P-020, scenarios P-026) are
then redeemed whole through their home importers; and the imported
library rides the portable archive (P-028) round-trip.

Gate findings pinned below, probed against the code as it stands:
- A Voxta scenario spelled with Voxta's own keys (scenarioText,
  chatFlow, roles, bootstrapMessages) and no card fields is refused
  ``unrecognized_content``: bulk import has no scenario home.
- The same scenario carrying ``description``/``scenario`` fields is
  instead swallowed as a v1 card (see the finding test at the end).
- A chat .jsonl refusal carries its home slice (P-020) in the reason
  text only; the preset refusal also records detected_shape /
  home_slice notes. Both are pinned as they honestly are.
- An oversize CHARX asset is a parser-level refusal
  (``asset_too_large``), never a silent drop.

Clean-room note: all fixtures authored fresh in this module — P-005
discipline, no real user files. No SillyTavern/Voxta source was read;
shapes rest on the repo's own parsers and prior slices' contracts.
"""

from __future__ import annotations

import copy
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest

from runmal.assets.service import list_assets
from runmal.cards.archive import export_charx
from runmal.cards.exporter import export_png
from runmal.cards.parser import MAX_ASSET_BYTES, import_card
from runmal.characters.provenance import parse_provenance
from runmal.characters.service import get_character, list_characters
from runmal.chats.filebridge import field_diff
from runmal.chats.fileexport import export_chat_jsonl
from runmal.chats.fileimport import parse_chat_file
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.library import organise
from runmal.library.models import RepairCode
from runmal.library.service import import_library_folder, import_library_uploads
from runmal.lorebooks import service as lore_service
from runmal.persona.interop import export_persona, parse_persona
from runmal.portable.archive import export_archive, validate_archive
from runmal.portable.restore import import_archive
from runmal.presets.interop import parse_preset
from runmal.presets.service import import_preset
from runmal.scenarios.fileexport import export_voxta
from runmal.scenarios.fileimport import parse_scenario_file

DESC_MARKER = "STRANGER-DESC-MARKER"


@pytest.fixture(autouse=True)
def _data_dir(tmp_path, monkeypatch):
    # Asset bytes (P-023) live under the data dir; keep them in tmp.
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))


# ---------------------------------------------------------------- helpers

def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory) -> str:
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        return user.id


def write(folder: Path, relpath: str, data: bytes) -> Path:
    path = folder / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


def by_relpath(report) -> dict:
    return {e.relpath: e for e in report.entries}


async def counts(factory, user_id):
    async with factory() as session:
        chars = await list_characters(session, user_id)
        books = await lore_service.list_lorebooks(session, user_id)
        return len(chars), len(books)


# ---------------------------------------------------------------- fixtures (all authored fresh)

def v2_card_bytes(name: str = "Ara Vell", **over) -> bytes:
    card = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": name,
        "description": f"{DESC_MARKER}: a stranger's card for {name}.",
        "personality": "Steady.",
        "scenario": "A test hall.",
        "first_mes": "Hail!",
        "mes_example": "<START>Yo<END>",
        "creator_notes": "",
        "system_prompt": "",
        "post_history_instructions": "",
        "alternate_greetings": [],
        "tags": ["stranger", "tide"],
        "creator": "stranger-forge",
        "extensions": {},
        "x_stranger_unknown": {"kept": [1, 2]},
    }
    card.update(over)
    return json.dumps(card).encode()


def v3_card_bytes() -> bytes:
    return json.dumps(
        {
            "spec": "chara_card_v3",
            "spec_version": "3.0",
            "data": {
                "name": "Bram Hollow",
                "description": f"{DESC_MARKER}: a v3 stranger.",
                "personality": "Dry.",
                "scenario": "A stair.",
                "first_mes": "Mind it.",
                "mes_example": "",
                "tags": ["stranger", "stairs"],
                "creator": "stranger-forge",
                "group_only_greetings": ["Together, then."],
                "assets": [
                    {"type": "icon", "uri": "embeded://avatar.png",
                     "name": "main", "ext": "png"},
                    {"type": "background",
                     "uri": "https://example.invalid/hall.jpg",
                     "name": "hall", "ext": "jpg"},
                ],
                "x_v3_unknown": "keepme",
            },
        }
    ).encode()


def png_card_bytes() -> bytes:
    card = import_card(v2_card_bytes("Cira Lune"))
    return export_png(card)


def world_lorebook_bytes() -> bytes:
    entries = {}
    for i, (key, comment) in enumerate(
        [("gale", "Gale"), ("tithe", "Tithe"), ("law", "Law")]
    ):
        entries[str(i)] = {
            "key": [key], "keysecondary": [], "comment": comment,
            "content": f"World fact {i}.", "constant": i == 1,
            "disable": i == 2, "order": 100 - i * 10, "position": i % 5,
            "selective": True, "selectiveLogic": 0,
        }
    return json.dumps({"name": "Stranger World", "entries": entries}).encode()


def native_lorebook_bytes(name: str | None = "Native Lore") -> bytes:
    book = {
        "format": "runmal-lorebook",
        "version": 1,
        "description": "A native stranger lorebook.",
        "scan_depth": 4,
        "token_budget": None,
        "entries": [
            {
                "name": "The Ferry", "content": "The ferry crosses at dawn.",
                "keys": ["ferry"], "secondary_keys": [], "priority": 100,
                "position": "before_char", "enabled": True, "constant": False,
                "case_sensitive": False, "whole_word": True,
                "sticky_prompts": 0, "cooldown_prompts": 0, "delay_prompts": 0,
            }
        ],
    }
    if name is not None:
        book["name"] = name
    return json.dumps(book).encode()


def lorebook_bytes(name: str = "Bulk Lore", entries=None) -> bytes:
    # Kept in P-022's spirit for the archive leg's vocabulary parity.
    return native_lorebook_bytes(name)


def scripty_card_bytes() -> bytes:
    return json.dumps(
        {
            "spec": "chara_card_v3",
            "spec_version": "3.0",
            "data": {
                "name": "Scripty Stranger",
                "description": "<script>alert('p030')</script> and {{eval::1+1}}",
                "personality": "Calm.",
                "scenario": "A test hall.",
                "first_mes": "Hail.",
                "tags": ["stranger"],
                "creator": "stranger-forge",
                "extensions": {
                    "custom_script": "<script>alert('p030')</script>",
                    "onload": "javascript:alert(1)",
                },
                "assets": [
                    {"type": "background", "uri": "javascript:alert(1)",
                     "name": "js-uri", "ext": "js"}
                ],
            },
        }
    ).encode()


def evil_charx_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("card.json", v2_card_bytes("Evil One"))
        zf.writestr("../../evil.txt", b"pwned")
    return buf.getvalue()


def big_charx_bytes() -> bytes:
    card = import_card(v2_card_bytes("Big Stranger"))
    card.assets = {"big.bin": b"\x07" * (MAX_ASSET_BYTES + 1)}
    return export_charx(card)


def preset_bytes() -> bytes:
    return json.dumps(
        {
            "name": "Stranger Preset",
            "temperature": 0.85,
            "top_p": 0.95,
            "frequency_penalty": 0.1,
            "presence_penalty": 0.2,
            "max_tokens": 900,
            "openai_max_context": 32000,
            "prompts": [
                {"identifier": "main", "name": "Main", "role": "system",
                 "content": "Be kind.", "system_prompt": True}
            ],
            "prompt_order": [{"identifier": "main"}],
            "x_future_knob": True,
        }
    ).encode()


def chat_bytes() -> bytes:
    lines = [
        {"character_name": "Ara Vell", "user_name": "Stranger",
         "create_date": "2026-10-01 @20h 00m 00s 000ms",
         "chat_metadata": {"integrity": "stranger"}},
        {"name": "Ara Vell", "is_user": False, "mes": "Hail.",
         "send_date": "2026-10-01 @20h 00m 01s", "swipe_id": 0,
         "swipes": ["Hail."], "extra": {"api": "stranger"}},
        {"name": "Stranger", "is_user": True, "mes": "Well met.",
         "send_date": "2026-10-01 @20h 01m 00s", "swipe_id": 0,
         "swipes": ["Well met."]},
    ]
    return ("\n".join(json.dumps(x) for x in lines) + "\n").encode()


def scenario_bytes() -> bytes:
    # Voxta spelled with Voxta's own keys and no card fields at all.
    return json.dumps(
        {
            "name": "Stranger Scenario",
            "scenarioText": "Opening.",
            "chatFlow": "Chat",
            "chatStyle": "Companion",
            "roles": [{"name": "Guide", "characterName": "Ara Vell"}],
            "bootstrapMessages": [
                {"type": "char", "text": "Hello", "role": "Guide"}
            ],
            "scripts": [{"code": "x=1"}],
            "x_future": {"a": 1},
        }
    ).encode()


def persona_bytes() -> bytes:
    return json.dumps(
        {
            "name": "Stranger Self",
            "description": "The stranger.",
            "prompt": "I am.",
            "system_prompt": "",
            "title": "Traveller",
            "description_position": "in_chat",
            "depth": 2,
            "role": "user",
            "x_custom": "keepme",
        }
    ).encode()


def stranger_files() -> dict[str, bytes]:
    ara = v2_card_bytes("Ara Vell")
    return {
        "cards/ara_v2.json": ara,
        "cards/ara_v3.json": v3_card_bytes(),
        "cards/ara.png": png_card_bytes(),
        "lore/world.json": world_lorebook_bytes(),
        "lore/native.json": native_lorebook_bytes("Native Lore"),
        "lore/unnamed.json": native_lorebook_bytes(None),
        "cards/bom_card.json": b"\xef\xbb\xbf" + v2_card_bytes("Bom Stranger"),
        "cards/ara_v2_copy.json": ara,
        "cards/ara_v2_revised.json": v2_card_bytes(
            "Ara Vell", description=f"{DESC_MARKER}: revised telling."
        ),
        "cards/corrupt.json": b'{"spec": "chara_card_v2", "name": "Ara Tru',
        "cards/future.json": json.dumps(
            {"spec": "chara_card_v99", "spec_version": "99.0",
             "name": "Future One", "description": "x"}
        ).encode(),
        "cards/scripty.json": scripty_card_bytes(),
        "cards/evil.charx": evil_charx_bytes(),
        "notes/readme.md": b"# hello",
        "presets/home.json": preset_bytes(),
        "chats/home.jsonl": chat_bytes(),
        "scenarios/home.json": scenario_bytes(),
        "cards/big.charx": big_charx_bytes(),
    }


def build_stranger_folder(tmp_path) -> tuple[Path, dict, bool]:
    files = stranger_files()
    folder = tmp_path / "stranger"
    for relpath, data in files.items():
        write(folder, relpath, data)
    outside = write(tmp_path, "outside.json", v2_card_bytes("Outside One"))
    symlink_ok = False
    try:
        linkdir = folder / "links"
        linkdir.mkdir(parents=True, exist_ok=True)
        (linkdir / "out.json").symlink_to(outside)
        symlink_ok = True
    except OSError:
        symlink_ok = False
    return folder, files, symlink_ok


async def run_stranger_import(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder, files, symlink_ok = build_stranger_folder(tmp_path)
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    return factory, user_id, folder, files, symlink_ok, report


EXPECTED_TOTALS_BASE = {"accepted": 7, "repaired": 2, "refused": 8}

# ---------------------------------------------------------------- bulk outcomes

async def test_stranger_library_bulk_outcomes(tmp_path):
    _, _, _, _, symlink_ok, report = await run_stranger_import(tmp_path)
    entries = by_relpath(report)
    expected = {
        "cards/ara.png": ("accepted", None, "card", "png"),
        "cards/ara_v2.json": ("accepted", None, "card", "json"),
        "cards/ara_v2_copy.json": ("refused", "duplicate_in_batch", "card", "json"),
        "cards/ara_v2_revised.json": ("accepted", None, "card", "json"),
        "cards/ara_v3.json": ("accepted", None, "card", "json"),
        "cards/big.charx": ("refused", "asset_too_large", "card", "charx"),
        "cards/bom_card.json": ("repaired", None, "card", "json"),
        "cards/corrupt.json": ("refused", "truncated", "unknown", None),
        "cards/evil.charx": ("refused", "path_traversal", "card", "charx"),
        "cards/future.json": ("refused", "unsupported_version", "card", "json"),
        "cards/scripty.json": ("accepted", None, "card", "json"),
        "chats/home.jsonl": ("refused", "unsupported_kind", "unknown", None),
        "lore/native.json": ("accepted", None, "lorebook", "json"),
        "lore/unnamed.json": ("repaired", None, "lorebook", "json"),
        "lore/world.json": ("accepted", None, "lorebook", "json"),
        "notes/readme.md": ("skipped", None, "unknown", None),
        "presets/home.json": ("refused", "unsupported_kind", "unknown", "json"),
        "scenarios/home.json": ("refused", "unrecognized_content", "unknown", "json"),
    }
    if symlink_ok:
        expected["links/out.json"] = ("skipped", None, "unknown", None)
    assert set(entries) == set(expected)
    for relpath, (outcome, code, kind, fmt) in expected.items():
        entry = entries[relpath]
        assert str(entry.outcome) == outcome, relpath
        assert (str(entry.reason_code) if entry.reason_code else None) == code, relpath
        assert str(entry.detected_kind) == kind, relpath
        assert entry.detected_format == fmt, relpath
    # Repairs pinned exactly.
    assert [str(r.code) for r in entries["cards/bom_card.json"].repairs] == ["bom_stripped"]
    assert [str(r.code) for r in entries["lore/unnamed.json"].repairs] == [
        "lorebook_name_from_filename"
    ]
    assert entries["lore/unnamed.json"].created_name == "unnamed"
    # The duplicate names its winner in the batch and creates nothing.
    dup = entries["cards/ara_v2_copy.json"]
    assert dup.duplicate_of == "cards/ara_v2.json"
    assert dup.created_id is None
    # Foreign homes point at their slices.
    preset = entries["presets/home.json"]
    assert "detected_shape:preset" in preset.notes
    assert "home_slice:P-021" in preset.notes
    chat = entries["chats/home.jsonl"]
    # Probed: the .jsonl path carries the home slice in the reason
    # text only, unlike the preset's notes — pinned as it is.
    assert "P-020" in chat.reason
    # Skips pinned by reason.
    assert entries["notes/readme.md"].reason == "unsupported_extension"
    if symlink_ok:
        assert entries["links/out.json"].reason == "symlink_not_followed"
    totals = report.totals
    assert totals["accepted"] == EXPECTED_TOTALS_BASE["accepted"]
    assert totals["repaired"] == EXPECTED_TOTALS_BASE["repaired"]
    assert totals["refused"] == EXPECTED_TOTALS_BASE["refused"]
    assert totals["skipped"] == (2 if symlink_ok else 1)


async def test_stranger_library_honest_report(tmp_path):
    factory, user_id, _, files, symlink_ok, report = await run_stranger_import(tmp_path)
    submitted = len(files) + (1 if symlink_ok else 0)
    assert report.totals == report.compute_totals()
    totals = report.totals
    assert totals["total_seen"] == len(report.entries) == submitted
    assert totals["total_seen"] == (
        totals["accepted"] + totals["repaired"] + totals["refused"] + totals["skipped"]
    )
    # Skipped files appear in BOTH entries and report.skipped.
    assert {s.relpath for s in report.skipped} == {
        e.relpath for e in report.entries if str(e.outcome) == "skipped"
    }
    skipped_reasons = {s.relpath: s.reason for s in report.skipped}
    for entry in report.entries:
        if str(entry.outcome) == "skipped":
            assert skipped_reasons[entry.relpath] == entry.reason
            assert entry.reason != ""
        if str(entry.outcome) == "refused":
            assert entry.reason_code is not None, entry.relpath
            assert entry.reason != "", entry.relpath
        if str(entry.outcome) == "repaired":
            assert entry.repairs, entry.relpath
            assert {str(r.code) for r in entry.repairs} <= {
                str(c) for c in RepairCode
            }, entry.relpath
        # Hashes and sizes are the submitted files' own — except for
        # skipped entries, which are never read.
        if entry.relpath in files and str(entry.outcome) != "skipped":
            data = files[entry.relpath]
            assert entry.sha256 == hashlib.sha256(data).hexdigest(), entry.relpath
            assert entry.size_bytes == len(data), entry.relpath
    # The report never carries file contents.
    assert DESC_MARKER not in json.dumps(report.to_dict())
    # Database reality matches the report exactly.
    assert await counts(factory, user_id) == (6, 3)
    async with factory() as session:
        books = {
            book.name: n
            for book, n in await lore_service.list_lorebooks(session, user_id)
        }
        assert books == {"Stranger World": 3, "Native Lore": 1, "unnamed": 1}
        for entry in report.entries:
            if str(entry.outcome) not in ("accepted", "repaired"):
                continue
            assert entry.created_id, entry.relpath
            if str(entry.detected_kind) == "card":
                row = await get_character(session, user_id, entry.created_id)
            else:
                row = await lore_service.get_lorebook(
                    session, user_id, entry.created_id
                )
            assert row is not None, entry.relpath
            assert row.name == entry.created_name, entry.relpath


async def test_stranger_v2_v3_normalised_storage(tmp_path):
    factory, user_id, _, _, _, report = await run_stranger_import(tmp_path)
    entries = by_relpath(report)
    async with factory() as session:
        chars = await list_characters(session, user_id)
        by_name = {c.name: c for c in chars}
        # v2: fields land whole and the unknown field survives.
        ara = next(c for c in chars if c.name == "Ara Vell" and c.version_no == 1)
        assert ara.version_no == 1
        reparsed = import_card(ara.card_json.encode(), "card.json")
        assert reparsed.name == "Ara Vell"
        assert reparsed.description == f"{DESC_MARKER}: a stranger's card for Ara Vell."
        assert reparsed.tags == ["stranger", "tide"]
        stored = json.loads(ara.card_json)
        unknown = stored.get("x_stranger_unknown") or (stored.get("data") or {}).get(
            "x_stranger_unknown"
        )
        assert unknown == {"kept": [1, 2]}
        # v3: the spec collapses to v2 in the store; the normalised
        # fields (held in the data envelope) are equal.
        bram = by_name["Bram Hollow"]
        stored3 = json.loads(bram.card_json)
        assert stored3["spec"] == "chara_card_v2"
        original = import_card(v3_card_bytes(), "card.json")
        data = stored3["data"]
        assert data["name"] == original.name
        assert data["description"] == original.description
        assert data["personality"] == original.personality
        assert data["group_only_greetings"] == original.group_only_greetings
        assert data["tags"] == original.tags
        assert data["x_v3_unknown"] == "keepme"


async def test_stranger_revised_card_versions_in_place(tmp_path):
    factory, user_id, _, _, _, report = await run_stranger_import(tmp_path)
    entries = by_relpath(report)
    assert any(
        n.startswith("versioned:v2")
        for n in entries["cards/ara_v2_revised.json"].notes
    )
    async with factory() as session:
        chars = await list_characters(session, user_id)
    aras = sorted(
        (c for c in chars if c.name == "Ara Vell"), key=lambda c: c.version_no
    )
    assert [c.version_no for c in aras] == [1, 2]
    assert aras[0].lineage_id == aras[1].lineage_id
    assert all(c.name == "Ara Vell" for c in aras)  # names unsuffixed (P-025)

# ---------------------------------------------------------------- safety + assets

async def test_stranger_scripty_inert_and_evil_charx_contained(tmp_path):
    factory, user_id, _, _, _, report = await run_stranger_import(tmp_path)
    entries = by_relpath(report)
    assert str(entries["cards/scripty.json"].outcome) == "accepted"
    assert str(entries["cards/evil.charx"].reason_code) == "path_traversal"
    async with factory() as session:
        chars = await list_characters(session, user_id)
        scripty = next(c for c in chars if c.name == "Scripty Stranger")
        # Stored literally, as inert data (P-027): nothing executed,
        # fetched, or stripped.
        assert "<script>alert('p030')</script>" in scripty.card_json
        assert "javascript:alert(1)" in scripty.card_json
        assert "{{eval::1+1}}" in scripty.card_json
        rows = await list_assets(session, user_id, scripty.id)
        assert [(r.name, r.status) for r in rows] == [("js-uri", "missing_bytes")]
    # The traversal member wrote nothing, anywhere.
    assert list(tmp_path.rglob("evil.txt")) == []


async def test_stranger_oversize_charx_refused_naming_the_asset(tmp_path):
    factory, user_id, _, _, _, report = await run_stranger_import(tmp_path)
    entry = by_relpath(report)["cards/big.charx"]
    # Probed outcome: parser-level refusal. The one unacceptable
    # outcome would be a silent accept with the asset gone and
    # nothing naming it — the refusal names the asset and its size.
    assert str(entry.outcome) == "refused"
    assert str(entry.reason_code) == "asset_too_large"
    assert "big.bin" in entry.reason
    assert str(MAX_ASSET_BYTES + 1) in entry.reason or "16777217" in entry.reason
    async with factory() as session:
        chars = await list_characters(session, user_id)
    assert "Big Stranger" not in {c.name for c in chars}


async def test_stranger_asset_reality(tmp_path):
    factory, user_id, _, _, _, report = await run_stranger_import(tmp_path)
    entries = by_relpath(report)
    async with factory() as session:
        # PNG card: the container art itself is stored (P-023).
        cira_id = entries["cards/ara.png"].created_id
        rows = await list_assets(session, user_id, cira_id)
        assert [(r.kind, r.name, r.status) for r in rows] == [
            ("card_art", "card_art", "stored")
        ]
        assert rows[0].byte_size > 0
        # v3 card: declared descriptors get honest rows — the embedded
        # icon's bytes never arrived, the background is external.
        bram_id = entries["cards/ara_v3.json"].created_id
        rows = await list_assets(session, user_id, bram_id)
        assert [(r.name, r.status, r.detail) for r in rows] == [
            ("main", "missing_bytes", "embedded_uri_unresolved"),
            ("hall", "external_unfetched", "external_uri_not_fetched"),
        ]


# ---------------------------------------------------------------- dry run + uploads

async def test_stranger_dry_run_identical_and_stores_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder, _, symlink_ok = build_stranger_folder(tmp_path)
    async with factory() as session:
        dry = await import_library_folder(session, user_id, folder, dry_run=True)
    assert dry.dry_run is True
    assert await counts(factory, user_id) == (0, 0)
    async with factory() as session:
        real = await import_library_folder(session, user_id, folder)
    assert dry.totals == real.totals
    assert {e.relpath: str(e.outcome) for e in dry.entries} == {
        e.relpath: str(e.outcome) for e in real.entries
    }
    assert await counts(factory, user_id) == (6, 3)


async def test_stranger_uploads_parity(tmp_path):
    files = stranger_files()
    subset = [
        ("cards/ara_v2.json", files["cards/ara_v2.json"]),
        ("cards/ara_v3.json", files["cards/ara_v3.json"]),
        ("lore/world.json", files["lore/world.json"]),
    ]
    (tmp_path / "up").mkdir(exist_ok=True)
    up_factory = make_factory(tmp_path / "up")
    up_user = await make_user(up_factory)
    async with up_factory() as session:
        report = await import_library_uploads(session, up_user, subset)
    entries = by_relpath(report)
    assert {r: str(e.outcome) for r, e in entries.items()} == {
        "cards/ara_v2.json": "accepted",
        "cards/ara_v3.json": "accepted",
        "lore/world.json": "accepted",
    }
    assert str(entries["cards/ara_v2.json"].detected_kind) == "card"
    assert str(entries["lore/world.json"].detected_kind) == "lorebook"
    assert await counts(up_factory, up_user) == (2, 1)


# ---------------------------------------------------------------- organisation + provenance

async def test_stranger_organisation_and_provenance(tmp_path):
    factory, user_id, _, files, _, report = await run_stranger_import(tmp_path)
    async with factory() as session:
        page = await organise.list_library(session, user_id, q="Ara Vell")
        assert {i["name"] for i in page["items"]} == {"Ara Vell"}
        assert page["total"] == 2  # both versions are findable
        tagged = await organise.list_library(session, user_id, tags=["tide"])
        assert {i["name"] for i in tagged["items"]} == {
            "Ara Vell", "Cira Lune", "Bom Stranger"
        }
        tag_keys = {t["tag_key"] for t in await organise.list_tags(session, user_id)}
        assert {"stranger", "tide", "stairs"} <= tag_keys
        chars = await list_characters(session, user_id)
        ara_v1 = next(
            c for c in chars if c.name == "Ara Vell" and c.version_no == 1
        )
        prov = parse_provenance(ara_v1)
        assert prov is not None
        assert prov["source_kind"] == "library_folder"
        assert prov["original_filename"] == "ara_v2.json"
        assert prov["relpath"] == "cards/ara_v2.json"
        data = files["cards/ara_v2.json"]
        assert prov["original_sha256"] == hashlib.sha256(data).hexdigest()
        assert prov["original_byte_length"] == len(data)

# ---------------------------------------------------------------- whole-library leg B2: home importers

async def test_home_preset_imports_whole_and_conflicts_by_name(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    parsed = parse_preset(preset_bytes())
    assert parsed.name == "Stranger Preset"
    async with factory() as session:
        row = await import_preset(session, user_id, parsed)
        assert row.name == "Stranger Preset"
        # The parameter bag lands whole.
        assert json.loads(row.params_json) == parsed.params == {
            "temperature": 0.85,
            "top_p": 0.95,
            "frequency_penalty": 0.1,
            "presence_penalty": 0.2,
            "max_tokens": 900,
            "context_length": 32000,
        }
        # Unknown-but-valid fields ride in the lossless carriage.
        carriage = json.loads(row.interop_json)
        assert carriage["raw"]["x_future_knob"] is True
        # Unlike cards — which version same-name content in place
        # (P-025) — a preset name conflict refuses by exception and
        # overwrites nothing.
        with pytest.raises(ValueError):
            await import_preset(session, user_id, parse_preset(preset_bytes()))


def test_home_persona_fixed_point():
    persona = parse_persona(persona_bytes())
    assert persona.name == "Stranger Self"
    assert persona.description_position == "in_chat"
    assert persona.depth == 2 and persona.role == "user"
    once = export_persona(persona)
    assert json.loads(once)["x_custom"] == "keepme"
    again = parse_persona(once)
    for field_name in (
        "name", "description", "prompt", "system_prompt", "title",
        "description_position", "depth", "role",
    ):
        assert getattr(again, field_name) == getattr(persona, field_name)
    assert export_persona(again) == once  # fixed point


def test_home_chat_fixed_point():
    result = parse_chat_file(chat_bytes())
    chat = result.chat
    assert chat.character_name == "Ara Vell"
    assert chat.user_name == "Stranger"
    assert len(chat.messages) == 2
    out = export_chat_jsonl(chat)
    reparsed = parse_chat_file(out).chat
    assert field_diff(chat, reparsed) == []


def test_home_scenario_fixed_point_and_unmappable_carried():
    scenario = parse_scenario_file(scenario_bytes())
    assert scenario.name == "Stranger Scenario"
    assert scenario.report is not None
    unmappable = scenario.report.to_dict()["unmappable"]
    assert [(u["path"], u["kind"]) for u in unmappable] == [
        ("scripts", "scripting")
    ]
    once = export_voxta(scenario)
    # Unmappable machinery and book-level unknowns hand back verbatim.
    assert once["scripts"] == [{"code": "x=1"}]
    assert once["x_future"] == {"a": 1}
    twice = export_voxta(parse_scenario_file(copy.deepcopy(once)))
    assert twice == once  # fixed point


# ---------------------------------------------------------------- archive leg

async def test_stranger_archive_roundtrip(tmp_path):
    factory, user_id, _, files, _, _ = await run_stranger_import(tmp_path)
    # Redeem the preset through its home so it rides the archive too.
    async with factory() as session:
        await import_preset(session, user_id, parse_preset(preset_bytes()))
    archive = tmp_path / "stranger.runmal"
    async with factory() as session:
        info = await export_archive(
            session, user_id, archive, base_dir=tmp_path / "data"
        )
    manifest = validate_archive(archive)
    assert manifest["contents"]["characters"] == 6
    assert manifest["contents"]["lorebooks"] == 3
    assert manifest["contents"]["presets"] == 1
    assert info.manifest["contents"] == manifest["contents"]
    report = await import_archive(archive, tmp_path / "restored")
    assert report.ok
    assert report.counts["characters"] == manifest["contents"]["characters"]
    assert report.counts["lorebooks"] == manifest["contents"]["lorebooks"]
    assert report.counts["sampling_presets"] == manifest["contents"]["presets"]
    assert report.counts["lore_entries"] == 5
    staged = create_session_factory(create_db_engine(Path(report.staged_db)))
    async with staged() as session:
        chars = await list_characters(session, user_id)
        books = await lore_service.list_lorebooks(session, user_id)
        assert len(chars) == 6 and len(books) == 3
        ara_v1 = next(
            c for c in chars if c.name == "Ara Vell" and c.version_no == 1
        )
        prov = parse_provenance(ara_v1)
        data = files["cards/ara_v2.json"]
        assert prov["original_sha256"] == hashlib.sha256(data).hexdigest()
        assert prov["relpath"] == "cards/ara_v2.json"
        second = tmp_path / "second.runmal"
        await export_archive(
            session, user_id, second, base_dir=Path(report.staged_root)
        )
    second_manifest = validate_archive(second)
    assert second_manifest["contents"] == manifest["contents"]
    for name, digest in manifest["checksums"].items():
        assert second_manifest["checksums"][name] == digest, name


# ---------------------------------------------------------------- gate finding

async def test_scenario_with_card_fields_is_swallowed_as_a_card_finding(tmp_path):
    # GATE FINDING (probed, pinned as current behaviour): a Voxta
    # scenario that also carries ``description``/``scenario`` fields
    # matches the bulk classifier's card shape (name + card fields)
    # and is imported as a v1 card — it never reaches a scenario
    # refusal. Bulk import has no scenario home either way; the
    # pure-Voxta spelling above is refused unrecognized_content.
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    folder = tmp_path / "stranger"
    write(
        folder,
        "scenarios/home.json",
        json.dumps(
            {
                "name": "Stranger Scenario",
                "description": "A scenario.",
                "scenario": "Opening.",
                "chatFlow": "Chat",
                "chatStyle": "Companion",
                "roles": [{"name": "Guide", "characterName": "Ara Vell"}],
            }
        ).encode(),
    )
    async with factory() as session:
        report = await import_library_folder(session, user_id, folder)
    entry = report.entries[0]
    assert str(entry.outcome) == "accepted"
    assert str(entry.detected_kind) == "card"
    assert entry.created_name == "Stranger Scenario"
