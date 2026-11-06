"""P-030 acceptance: Part II gate — corpus round-trips.

Roadmap line: the Part II gate — every interop format built in
Part II (cards P-015..P-017/P-023, persona P-018, lorebooks P-019,
chats P-020, presets P-021, bulk/store paths P-022, provenance
P-029, scenarios P-026 as a supplementary non-corpus leg) proves
clean round trips against the one shared P-005 corpus before
Part III behaviour work is allowed to build on them.

Contract under test (corpus = tests/fixtures/interop, exactly 12
fixtures: 5 cards, 3 lorebooks, 2 presets, 1 chat, 1 persona):

- the manifest still pins the corpus itself (sha256 + byte size
  per fixture), so the gate cannot pass on a silently changed
  corpus;
- file legs are full-clean: import -> export -> re-import keeps
  every normalised/mapped field, every unknown field (compared
  level-agnostically for cards, in extra/raw carriage for
  lorebooks, presets and persona), and every export is a
  byte-stable fixed point;
- store legs are mapped-only clean where a store exists: the
  value read back from the database exports to exactly the
  mapped field set the file leg parsed. Persona has NO store in
  Part II — its leg is file-model only, deliberately.
- the only allowed losses are the pinned ones, each named and
  exact in this module: (a) lorebook DB-path dropped field set
  (22 world-info fields, P-005) and position code 4 collapsing
  to before_char at the DB layer (P-038 owns the real mapping),
  plus the native at_depth entry the DB layer cannot hold yet;
  (b) the chat live-projection loss report (P-020), pinned as an
  exact list; (c) card spec_version collapsing to "2" through
  the character store, which stores the v2 export shape;
  (d) PNG export synthesising a 1x1 carrier — fields are
  asserted, never pixels.

Clean-room note: shapes rest only on the P-005 authored corpus,
the public format documentation behind the Part II slices, and
this repository's own code and tests. No third-party
implementation source was inspected.
"""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from runmal.cards.archive import export_charx
from runmal.cards.exporter import export_json, export_png
from runmal.cards.parser import import_card
from runmal.chats.filebridge import field_diff, loss_report
from runmal.chats.fileexport import export_chat_jsonl
from runmal.chats.fileimport import parse_chat_file, parse_chat_jsonl
from runmal.characters.provenance import parse_provenance
from runmal.characters.service import create_character_from_card
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.lorebooks import service as lore_service
from runmal.lorebooks.interop import (
    export_native,
    export_worldinfo,
    export_worldinfo_bytes,
    parse_lorebook_file,
)
from runmal.lorebooks.transfer import (
    export_book,
    import_book_transactional,
    parse_import,
)
from runmal.persona.interop import export_persona, parse_persona
from runmal.presets import service as preset_service
from runmal.presets.interop import PresetFileView, export_preset, parse_preset
from runmal.scenarios.fileexport import export_native as export_scenario_native
from runmal.scenarios.fileexport import export_voxta
from runmal.scenarios.fileimport import parse_scenario_file

CORPUS = Path(__file__).parent / "fixtures" / "interop"
MANIFEST = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
ENTRIES = {entry["file"]: entry for entry in MANIFEST["fixtures"]}

CARD_FILES = (
    "card_v1_minimal.json",
    "card_v2_rich.json",
    "card_v2_edge.json",
    "card_v3_rich.json",
    "card_dual_ccv3.png",
)
LOREBOOK_FILES = (
    "lorebook_worldinfo_full.json",
    "lorebook_worldinfo_nulls.json",
    "lorebook_native_rich.json",
)
PRESET_FILES = (
    "preset_st_textcompletion.json",
    "preset_st_chatcompletion.json",
)


def read(name: str) -> bytes:
    return (CORPUS / name).read_bytes()


def read_json(name: str) -> dict:
    return json.loads(read(name))


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


# --- 1. manifest integrity (P-005's checks, carried into the gate) --------


def test_manifest_pins_exactly_twelve_fixtures() -> None:
    on_disk = {
        p.name
        for p in CORPUS.iterdir()
        if p.is_file() and p.name not in ("manifest.json", "make_corpus.py")
    }
    assert on_disk == set(ENTRIES), "manifest and corpus directory disagree"
    assert len(ENTRIES) == 12
    kinds = [entry["kind"] for entry in MANIFEST["fixtures"]]
    assert kinds.count("character-card") == 5
    assert kinds.count("lorebook") == 3
    assert kinds.count("preset") == 2
    assert kinds.count("chat") == 1
    assert kinds.count("persona") == 1


def test_manifest_hashes_and_sizes_match_disk() -> None:
    for name, entry in ENTRIES.items():
        data = read(name)
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], name
        assert len(data) == entry["bytes"], name
        assert entry["kind"] and entry["shape"] and entry["expectation"]


# --- 2. cards, file leg (P-017's contract, re-proven at the gate) ---------

# P-017's normalised field set, reused verbatim.
NORMALIZED_FIELDS = (
    "name",
    "description",
    "personality",
    "scenario",
    "first_mes",
    "mes_example",
    "creator_notes",
    "system_prompt",
    "post_history_instructions",
    "alternate_greetings",
    "tags",
    "creator",
    "character_version",
    "nickname",
    "group_only_greetings",
    "creator_notes_multilingual",
    "source",
    "creation_date",
    "modification_date",
    "asset_refs",
    "character_book",
    "extensions",
)
DATA_KNOWN = frozenset(NORMALIZED_FIELDS) | {"assets"}


def unknown_values(raw: dict) -> dict:
    """Unknown key -> sorted JSON values, ignoring envelope level
    (P-017's level-agnostic comparison: a version conversion may
    move an unknown between flat and `data`, never lose/change it)."""
    values: dict[str, list[str]] = {}

    def collect(mapping: dict) -> None:
        for key, value in mapping.items():
            if key in DATA_KNOWN or key in ("spec", "spec_version"):
                continue
            values.setdefault(key, []).append(
                json.dumps(value, sort_keys=True, ensure_ascii=False)
            )

    data = raw.get("data")
    if isinstance(data, dict):
        collect(data)
        collect({k: v for k, v in raw.items() if k != "data"})
    else:
        collect(raw)
    return {key: sorted(vals) for key, vals in values.items()}


def assert_card_fields_equal(card, again, filename: str) -> None:
    for field in NORMALIZED_FIELDS:
        assert getattr(again, field) == getattr(card, field), (filename, field)
    assert again.assets == card.assets, filename
    assert unknown_values(again.raw) == unknown_values(card.raw), filename


def export_shape(card, shape: str) -> tuple[bytes, str]:
    if shape == "json2":
        return export_json(card, "2"), "export.json"
    if shape == "json3":
        return export_json(card, "3"), "export.json"
    if shape == "png":
        return export_png(card), "export.png"
    return export_charx(card), "export.charx"


SHAPES = ("json2", "json3", "png", "charx")


def expected_spec(card, shape: str) -> str:
    if shape in ("json3", "charx"):
        return "3"
    if shape == "png" and card.spec_version == "3":
        return "3"
    return "2"


def test_cards_file_leg_json_v2_round_trip_clean() -> None:
    for name in CARD_FILES:
        card = import_card(read(name), name)
        blob, filename = export_shape(card, "json2")
        again = import_card(blob, filename)
        assert again.spec_version == "2", name
        assert_card_fields_equal(card, again, name)


def test_cards_file_leg_json_v3_round_trip_clean() -> None:
    for name in CARD_FILES:
        card = import_card(read(name), name)
        blob, filename = export_shape(card, "json3")
        again = import_card(blob, filename)
        assert again.spec_version == "3", name
        assert_card_fields_equal(card, again, name)


def test_cards_file_leg_png_round_trip_fields_only() -> None:
    # export_png synthesises a 1x1 carrier image: FIELDS are the
    # contract here, never pixel equality with the source PNG.
    for name in CARD_FILES:
        card = import_card(read(name), name)
        blob, filename = export_shape(card, "png")
        again = import_card(blob, filename)
        assert again.spec_version == expected_spec(card, "png"), name
        assert_card_fields_equal(card, again, name)


def test_cards_file_leg_charx_round_trip_clean() -> None:
    for name in CARD_FILES:
        card = import_card(read(name), name)
        blob, filename = export_shape(card, "charx")
        again = import_card(blob, filename)
        assert again.spec_version == "3", name
        assert_card_fields_equal(card, again, name)


def test_cards_file_leg_exports_are_fixed_points() -> None:
    for name in CARD_FILES:
        card = import_card(read(name), name)
        for shape in SHAPES:
            blob, filename = export_shape(card, shape)
            again = import_card(blob, filename)
            reblob, _ = export_shape(again, shape)
            assert reblob == blob, (name, shape)


def test_dual_chunk_png_imports_as_v3_payload() -> None:
    card = import_card(read("card_dual_ccv3.png"), "card_dual_ccv3.png")
    assert card.spec_version == "3"
    assert card.name == "Dual Card (v3 payload)"
    assert card.first_mes == "New greeting."


# --- 3. cards, store leg ---------------------------------------------------


async def test_cards_store_leg_round_trip_clean(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    for name in CARD_FILES:
        data = read(name)
        card = import_card(data, name)
        async with factory() as session:
            character = await create_character_from_card(
                session, user_id, card, source_bytes=data
            )
            stored_text = character.card_json
        stored = import_card(stored_text.encode("utf-8"), "stored.json")
        # PINNED LOSS (c): the store holds export_json(card, "2"),
        # so spec_version collapses to "2" through the store even
        # for v3 / dual-chunk cards. Normalised fields and unknowns
        # must still be exactly the file leg's.
        assert stored.spec_version == "2", name
        assert_card_fields_equal(card, stored, name)


async def test_cards_store_provenance_carried_but_not_exported(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    name = "card_v2_rich.json"
    data = read(name)
    card = import_card(data, name)
    async with factory() as session:
        character = await create_character_from_card(
            session,
            user_id,
            card,
            source_bytes=data,
            provenance={"source_kind": "library_upload", "original_filename": name},
        )
        stored_text = character.card_json
        provenance = parse_provenance(character)
    assert provenance is not None
    assert provenance["source_kind"] == "library_upload"
    assert provenance["original_filename"] == name
    assert provenance["original_sha256"] == hashlib.sha256(data).hexdigest()
    assert provenance["original_byte_length"] == len(data)
    # Provenance is the character's own record: it does NOT travel
    # in card exports (P-029).
    stored = import_card(stored_text.encode("utf-8"), "stored.json")
    for version in ("2", "3"):
        blob = export_json(stored, version)
        assert name.encode("utf-8") not in blob
        assert b"library_upload" not in blob
        assert b"imported_at" not in blob
        assert b"provenance" not in blob


# --- 4. lorebooks, file leg (full clean, P-019's contract) -----------------

# The 19 fields P-005 pinned as dropped by the DB-path importer
# (group/groupWeight were promoted to first-class fields by
# P-034, vectorized by P-035). The file layer preserves all of
# them as data: depth/role as first-class at-depth companions,
# the other 17 verbatim in extra.
WORLDINFO_DROPPED_TODAY = frozenset(
    {
        "automationId",
        "characterFilter",
        "decorators",
        "delayUntilRecursion",
        "depth",
        "displayIndex",
        "excludeRecursion",
        "groupOverride",
        "id",
        "ignoreBudget",
        "outletName",
        "preventRecursion",
        "probability",
        "role",
        "scanDepth",
        "selective",
        "triggers",
        "useGroupScoring",
        "useProbability",
    }
)
assert len(WORLDINFO_DROPPED_TODAY) == 19  # group/groupWeight landed in P-034, vectorized in P-035

# Source fields the DB-path transfer layer maps (P-005's set).
WORLDINFO_TRANSFER_MAPPED_SOURCE = frozenset(
    {
        "comment",
        "content",
        "key",
        "keysecondary",
        "selectiveLogic",
        "group",
        "groupWeight",
        "constant",
        "vectorized",
        "disable",
        "order",
        "position",
        "caseSensitive",
        "matchWholeWords",
        "sticky",
        "cooldown",
        "delay",
    }
)

MAPPED_ENTRY_KEYS = (
    "name",
    "content",
    "keys",
    "secondary_keys",
    "selective_logic",
    "inclusion_group",
    "group_weight",
    "priority",
    "enabled",
    "constant",
    "vectorised",
    "case_sensitive",
    "whole_word",
    "sticky_prompts",
    "cooldown_prompts",
    "delay_prompts",
)


def test_lorebooks_file_leg_mapped_fields_equal() -> None:
    for name in LOREBOOK_FILES:
        book = parse_lorebook_file(read(name))
        parsed_book, parsed_entries = parse_import(read_json(name))
        assert book.name == parsed_book["name"], name
        assert len(book.entries) == len(parsed_entries), name
        for entry, parsed in zip(book.entries, parsed_entries):
            native = entry.native_fields()
            for key in MAPPED_ENTRY_KEYS:
                assert native[key] == parsed[key], (name, entry.name, key)
            # position is asserted separately: the file layer keeps
            # at_depth as data where the transfer layer collapses it.
            if parsed["position"] == "at_depth":
                assert entry.position == "at_depth", name
            elif entry.position_code == 4:
                assert entry.position == "at_depth", name
                assert parsed["position"] == "before_char", name
            else:
                assert native["position"] == parsed["position"], name
    # book-level fields of the native fixture ride the file model
    native = parse_lorebook_file(read("lorebook_native_rich.json"))
    assert native.source_format == "native"
    assert native.description == (
        "Rúnmál native shape at full stretch (the S304 export shape)."
    )
    assert native.scan_depth == 5 and native.token_budget == 800
    full = parse_lorebook_file(read("lorebook_worldinfo_full.json"))
    assert full.source_format == "worldinfo"
    assert full.original_data == {"scan_depth": 4}


def test_lorebooks_file_leg_dropped_fields_survive_as_data() -> None:
    source = read_json("lorebook_worldinfo_full.json")
    book = parse_lorebook_file(read("lorebook_worldinfo_full.json"))
    for entry, uid in zip(book.entries, sorted(source["entries"])):
        raw_entry = source["entries"][uid]
        expected_extra = {
            key
            for key in raw_entry
            if key in WORLDINFO_DROPPED_TODAY - {"depth", "role"}
        }
        assert set(entry.extra) == expected_extra, entry.name
        for key in expected_extra:
            assert entry.extra[key] == raw_entry[key], (entry.name, key)
        if "depth" in raw_entry:
            assert entry.depth == raw_entry["depth"], entry.name
        if "role" in raw_entry:
            assert entry.role == raw_entry["role"], entry.name
    gale = book.entries[0]
    assert set(gale.extra) == WORLDINFO_DROPPED_TODAY - {"depth", "role"}
    assert gale.depth == 4 and gale.role == 0
    assert gale.selective_logic == "not_all"
    assert gale.extra["scanDepth"] is None  # explicit null kept, not dropped


def test_lorebooks_file_leg_position_code_4_is_at_depth() -> None:
    book = parse_lorebook_file(read("lorebook_worldinfo_full.json"))
    gale, harbour, tithe = book.entries
    assert gale.position == "at_depth" and gale.position_code == 4
    assert harbour.position == "before_char" and harbour.position_code == 0
    assert tithe.position == "after_char" and tithe.position_code == 1
    world = export_worldinfo(book)
    assert world["entries"]["0"]["position"] == 4  # at_depth -> code 4
    assert world["entries"]["0"]["depth"] == 4
    assert world["entries"]["0"]["role"] == 0
    for uid in ("1", "2"):
        assert "depth" not in world["entries"][uid]
        assert "role" not in world["entries"][uid]
    native = parse_lorebook_file(read("lorebook_native_rich.json"))
    ferry = native.entries[0]
    assert ferry.position == "at_depth" and ferry.position_code == 4
    assert export_worldinfo(native)["entries"]["0"]["position"] == 4
    assert export_native(native)["entries"][0]["position"] == "at_depth"


def test_lorebooks_file_leg_exports_are_fixed_points() -> None:
    for name in LOREBOOK_FILES:
        book = parse_lorebook_file(read(name))
        world_once = export_worldinfo(book)
        world_twice = export_worldinfo(parse_lorebook_file(world_once))
        assert world_twice == world_once, name
        assert export_worldinfo_bytes(book) == export_worldinfo_bytes(
            parse_lorebook_file(world_once)
        ), name
        native_once = export_native(book)
        native_twice = export_native(parse_lorebook_file(native_once))
        assert native_twice == native_once, name
        # re-parsing either export keeps name + entry count; the
        # byte/dict fixed points above prove the fields themselves
        for exported in (world_once, native_once):
            again = parse_lorebook_file(exported)
            assert again.name == book.name, name
            assert len(again.entries) == len(book.entries), name


def test_lorebooks_worldinfo_nulls_coerce_never_typeerror() -> None:
    # bytes and dict inputs both parse; explicit nulls and numeric
    # strings coerce to defaults / numbers, never a bare TypeError.
    for source in (
        read("lorebook_worldinfo_nulls.json"),
        read_json("lorebook_worldinfo_nulls.json"),
    ):
        book = parse_lorebook_file(source)
        first, second = book.entries
        assert first.priority == 100 and first.position_code is None
        assert first.position == "before_char"
        assert first.secondary_keys == []
        assert (first.sticky_prompts, first.cooldown_prompts) == (0, 0)
        assert second.priority == 150 and second.sticky_prompts == 2


# --- 5. lorebooks, store leg (mapped-only clean, pinned DB loss) -----------


def _sorted_entries(entries: list[dict]) -> list[dict]:
    return sorted(entries, key=lambda e: e["name"])


async def _store_round_trip(factory, user_id, name: str) -> dict:
    data = read_json(name)
    async with factory() as session:
        book = await import_book_transactional(session, user_id, data)
        stored_entries = await lore_service.list_entries(session, user_id, book.id)
        assert stored_entries is not None
        exported = export_book(
            lore_service.lorebook_to_dict(book),
            [lore_service.entry_to_dict(e) for e in stored_entries],
        )
    return exported


async def test_lorebooks_store_leg_worldinfo_mapped_only_clean(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    for name in ("lorebook_worldinfo_full.json", "lorebook_worldinfo_nulls.json"):
        _parsed_book, parsed_entries = parse_import(read_json(name))
        exported = await _store_round_trip(factory, user_id, name)
        # the world-info shape carries no book settings of its own:
        # the store's defaults are the read-back contract here.
        assert exported["name"] == _parsed_book["name"], name
        assert exported["description"] == "", name
        assert exported["scan_depth"] == 4, name
        assert exported["token_budget"] is None, name
        # entry mapped fields exactly equal the transfer parse,
        # compared order-free (the store orders by priority).
        assert _sorted_entries(exported["entries"]) == _sorted_entries(
            parsed_entries
        ), name
        for entry in exported["entries"]:
            assert set(entry) == {
                "name", "content", "keys", "secondary_keys", "selective_logic", "inclusion_group", "group_weight", "priority",
                "position", "enabled", "constant", "vectorised", "case_sensitive",
                "whole_word", "sticky_prompts", "cooldown_prompts",
                "delay_prompts",
            }, name
    # PINNED LOSS (a), position half: source code 4 (at_depth) is
    # stored as before_char by the DB path — P-038 owns the fix.
    exported = await _store_round_trip(
        factory, user_id, "lorebook_worldinfo_full.json"
    )
    # (second import of the same book is a distinct stored book;
    # read the Gale-Bell entry from this fresh export)
    gale = next(e for e in exported["entries"] if e["name"] == "The Gale-Bell")
    assert gale["position"] == "before_char"


def test_lorebooks_store_leg_dropped_set_is_pinned_exactly() -> None:
    # PINNED LOSS (a), field half: source keys minus the transfer-
    # mapped set EQUALS the named 19-field frozenset. A future
    # slice that shrinks this loss must edit this pin deliberately.
    source = read_json("lorebook_worldinfo_full.json")
    dropped = set(source["entries"]["0"]) - WORLDINFO_TRANSFER_MAPPED_SOURCE
    assert dropped == WORLDINFO_DROPPED_TODAY
    assert len(dropped) == 19


async def test_lorebooks_store_leg_native_at_depth_pinned_limitation(
    tmp_path,
) -> None:
    # PINNED LIMITATION (a, native half): the native fixture's
    # at_depth entry is data the file layer holds whole, but the
    # DB layer's positions are only before_char / after_char
    # today, so the transactional store import refuses the book
    # whole (nothing is left behind). P-038 owns at-depth in the
    # DB; when it lands, this pin must be replaced by a clean
    # native store round trip.
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        with pytest.raises(ValueError, match="at_depth"):
            await import_book_transactional(
                session, user_id, read_json("lorebook_native_rich.json")
            )
        await session.rollback()
        books = await lore_service.list_lorebooks(session, user_id)
    assert books == []


# --- 6. presets, file + store legs -----------------------------------------

TEXT_BAG = {
    "temperature": 0.9,
    "top_p": 0.92,
    "top_k": 40,
    "min_p": 0.05,
    "repetition_penalty": 1.08,
    "frequency_penalty": 0,
    "presence_penalty": 0,
    "max_tokens": 350,
    "context_length": 8192,
}
CHAT_BAG = {
    "temperature": 0.85,
    "top_p": 0.95,
    "frequency_penalty": 0,
    "presence_penalty": 0,
    "max_tokens": 900,
    "context_length": 128000,
}
EXPECTED_BAGS = {
    "preset_st_textcompletion.json": TEXT_BAG,
    "preset_st_chatcompletion.json": CHAT_BAG,
}


def mirror_keys(raw: dict) -> list[str]:
    """Mirror-only carriage keys: in raw, never in the bag."""
    return sorted(
        key
        for key in raw
        if key == "tfs"
        or key.startswith("dry_")
        or key.startswith("dynatemp")
        or key in ("logit_bias", "model")
    )


def assert_preset_clean(parsed, reparsed, exported_obj: dict) -> None:
    assert reparsed.name == parsed.name
    assert reparsed.params == parsed.params  # canonical bag, exactly
    assert reparsed.template_ref == parsed.template_ref
    assert reparsed.source_format == parsed.source_format
    assert reparsed.raw == parsed.raw
    assert reparsed.prompts == parsed.prompts
    assert reparsed.prompt_order == parsed.prompt_order
    mirrors = mirror_keys(parsed.raw)
    assert mirrors, "corpus presets must carry mirror-only keys"
    for key in mirrors:
        assert key not in parsed.params, key
        assert exported_obj[key] == parsed.raw[key], key
    # prompt / prompt_order identity: identifiers, order, enabled
    assert [p["identifier"] for p in reparsed.prompts] == [
        p["identifier"] for p in parsed.prompts
    ]
    assert [
        (e["identifier"], e.get("enabled", True))
        for e in reparsed.prompt_order
    ] == [(e["identifier"], e.get("enabled", True)) for e in parsed.prompt_order]


def test_presets_file_leg_fixed_point() -> None:
    for name in PRESET_FILES:
        parsed = parse_preset(read(name))
        assert parsed.params == EXPECTED_BAGS[name], name
        once = export_preset(parsed)
        reparsed = parse_preset(once)
        assert_preset_clean(parsed, reparsed, json.loads(once))
        assert export_preset(reparsed) == once, name  # byte fixed point


def test_presets_file_leg_chat_prompts_and_seed_sentinel() -> None:
    chat = parse_preset(read("preset_st_chatcompletion.json"))
    assert [p["identifier"] for p in chat.prompts] == [
        "main",
        "worldInfoBefore",
        "jailbreak",
    ]
    assert [e["identifier"] for e in chat.prompt_order] == [
        "main",
        "worldInfoBefore",
        "personaDescription",
        "charDescription",
        "scenario",
        "dialogueExamples",
        "chatHistory",
        "jailbreak",
    ]
    char_entry = next(
        e for e in chat.prompt_order if e["identifier"] == "charDescription"
    )
    assert char_entry["enabled"] is False
    assert chat.raw["logit_bias"] == {} and chat.raw["model"] == "corpus-model"
    # seed == -1 is the unset sentinel: out of the bag, in raw,
    # and restored verbatim on export (text-completion fixture).
    text = parse_preset(read("preset_st_textcompletion.json"))
    assert "seed" not in text.params and text.raw["seed"] == -1
    assert json.loads(export_preset(text))["seed"] == -1
    assert text.raw["tfs"] == 0.95 and text.raw["dry_base"] == 1.75


async def test_presets_store_leg_round_trip_clean(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    for name in PRESET_FILES:
        parsed = parse_preset(read(name))
        async with factory() as session:
            preset = await preset_service.import_preset(session, user_id, parsed)
            view_dict = preset_service.preset_to_dict(preset)
            carriage = preset_service.interop_data(preset)
        assert view_dict["params"] == parsed.params, name
        assert carriage["raw"] == parsed.raw, name
        assert carriage["prompts"] == parsed.prompts, name
        assert carriage["prompt_order"] == parsed.prompt_order, name
        view = PresetFileView(
            name=view_dict["name"],
            params=view_dict["params"],
            template_ref=view_dict["template_ref"],
            source_format=view_dict["source_format"],
            raw=carriage.get("raw"),
            prompts=carriage.get("prompts") or [],
            prompt_order=carriage.get("prompt_order") or [],
        )
        blob = export_preset(view)
        reparsed = parse_preset(blob)
        assert_preset_clean(parsed, reparsed, json.loads(blob))
        assert export_preset(reparsed) == blob, name


# --- 7. chat, file leg ------------------------------------------------------

# PINNED LOSS (b): the live projection's exact loss report for
# the corpus chat (P-020's filebridge). Equality, nothing more,
# nothing less — a slice that closes one of these losses, or
# adds a new one, must edit this pin deliberately.
EXPECTED_LOSS_REPORT = [
    "chat_metadata key 'integrity' has no live-projection column",
    "messages[0]: 1 alternate swipe(s) beyond the active one "
    "cannot be held by the live projection",
    "messages[0]: extra provenance present (keys: api, model) "
    "cannot be held by the live projection",
    "messages[0]: send_date present with no full-fidelity live column",
    "messages[1]: send_date present with no full-fidelity live column",
    "messages[2]: send_date present with no full-fidelity live column",
]


def _corpus_chat():
    return parse_chat_jsonl(read("chat_st.jsonl")).chat


def test_chat_file_leg_round_trip_clean() -> None:
    chat = _corpus_chat()
    assert chat.user_name == "Ferry Passenger"
    assert chat.character_name == "Old Bruni"
    assert chat.chat_metadata == {"integrity": "corpus-placeholder"}
    assert len(chat.messages) == 3
    blob = export_chat_jsonl(chat)
    again = parse_chat_jsonl(blob).chat
    assert field_diff(chat, again) == []
    # header + per-message fields, asserted explicitly as well
    assert again.user_name == chat.user_name
    assert again.character_name == chat.character_name
    assert again.chat_metadata == chat.chat_metadata
    assert again.header_raw == chat.header_raw
    # dates are compared as parsed values (P-020: a numeric date
    # would reformat to an ST millisecond string on export; the
    # parsed instant is the contract, not the spelling)
    assert again.create_date_parsed == chat.create_date_parsed
    for first, second in zip(chat.messages, again.messages):
        assert second.content == first.content  # the line's mes
        assert second.role == first.role
        assert second.speaker_name == first.speaker_name
        assert second.swipes == first.swipes
        assert second.swipe_id == first.swipe_id
        assert second.swipe_info == first.swipe_info
        assert second.extra == first.extra
        assert second.raw == first.raw  # unknowns survive verbatim
        assert second.send_date_parsed == first.send_date_parsed
    # corpus specifics pinned by name
    first = chat.messages[0]
    assert first.swipes == [
        "Mind the gap. It minds you.",
        "Step careful. The planks remember rain.",
    ]
    assert first.swipe_id == 0
    assert first.extra == {"api": "corpus", "model": "corpus-model"}


def test_chat_file_leg_second_export_byte_identical() -> None:
    chat = _corpus_chat()
    once = export_chat_jsonl(chat)
    twice = export_chat_jsonl(parse_chat_jsonl(once).chat)
    assert twice == once


def test_chat_parse_chat_file_matches_jsonl_entry_point() -> None:
    via_file = parse_chat_file(read("chat_st.jsonl")).chat
    via_jsonl = _corpus_chat()
    assert via_file == via_jsonl
    assert field_diff(via_file, via_jsonl) == []


def test_chat_live_projection_loss_report_is_pinned_exactly() -> None:
    assert loss_report(_corpus_chat()) == EXPECTED_LOSS_REPORT


# --- 8. persona, file leg only (no store exists in Part II) ----------------

PERSONA_FIELDS = (
    "name",
    "description",
    "prompt",
    "system_prompt",
    "title",
    "description_position",
    "depth",
    "role",
    "position",
)


def test_persona_file_leg_round_trip_clean() -> None:
    persona = parse_persona(read("persona_st.json"))
    assert persona.name == "Ferry Passenger"
    assert persona.description_position == "in_prompt"
    assert persona.position == 0  # legacy numeric preserved verbatim
    once = export_persona(persona)
    again = parse_persona(once)
    for field in PERSONA_FIELDS:
        assert getattr(again, field) == getattr(persona, field), field
    assert again.raw == persona.raw  # unknowns ride in raw, equal
    assert again == persona


def test_persona_file_leg_fixed_point_and_no_fabrication() -> None:
    persona = parse_persona(read("persona_st.json"))
    once = export_persona(persona)
    twice = export_persona(parse_persona(once))
    assert twice == once
    out = json.loads(once)
    # P-018: export fabricates no depth/role the file never carried
    assert persona.depth is None and persona.role == ""
    assert "depth" not in out and "role" not in out
    assert "description_depth" not in out and "description_role" not in out


# --- 9. scenarios, supplementary (NOT corpus) -------------------------------
#
# Scenarios have no corpus fixture; this leg authors a P-026-shaped
# Voxta scenario inline (the P-026 pattern) and proves the same
# gate properties: fixed-point exports in both shapes, unmappable
# elements re-emitted verbatim from unmappable_values, and the
# parse report (unmappable entries + warnings) reproduced exactly.

SCENARIO_VOXTA = {
    "name": "Gate Harbour",
    "description": "A supplementary gate scenario.",
    "scenario": "The ferry waits at dawn.",
    "chatFlow": "Story",
    "chatStyle": "Roleplay",
    "roles": [
        {"name": "Hero", "characterName": "Aria",
         "enabledOnStart": False, "canSpeak": True},
        {"role": "Guide", "character": "Borin"},
    ],
    "systemPrompt": {"text": "Be vivid", "mode": "replace"},
    "scenarioTemplate": "Tpl {{name}}",
    "bootstrapMessages": [
        {"type": "char", "text": "Hello", "role": "Hero"},
        {"kind": "alien", "text": "Unmapped kind text"},
    ],
    "impersonation": {"name": "Imp", "description": "Imp desc"},
    "narrator": {"name": "Narr", "voice": "deep"},
    "memoryBooks": ["Book One", {"name": "Book Two"}],
    "flags": ["started", "met_hero"],
    "variables": {"gold": 10, "mood": "calm"},
    "contexts": [
        {"key": "k1", "text": "Ctx text", "condition": "gold>5",
         "role": "Hero", "position": "before"},
    ],
    "parent": "Parent Scenario",
    "thumbnail": "thumb.png",
    "scripts": [{"code": "x=1", "opaque": [1, 2, {"deep": True}]}],
    "events": [{"for": "events"}, 42],
    "x_unknown": {"a": 1},
}

EXPECTED_SCENARIO_WARNINGS = [
    "bootstrap message kind 'alien' is not natively mapped; "
    "carried as 'message'"
]


def test_scenario_supplementary_voxta_fixed_points() -> None:
    parsed = parse_scenario_file(copy.deepcopy(SCENARIO_VOXTA))
    assert parsed.source_format == "voxta"
    assert parsed.name == "Gate Harbour"
    assert parsed.flow == "story" and parsed.style == "roleplay"
    voxta_once = export_voxta(parsed)
    voxta_twice = export_voxta(parse_scenario_file(copy.deepcopy(voxta_once)))
    assert voxta_twice == voxta_once
    native_once = export_scenario_native(parsed)
    native_twice = export_scenario_native(
        parse_scenario_file(copy.deepcopy(native_once))
    )
    assert native_twice == native_once
    assert native_once["source_format"] == "native"


def test_scenario_supplementary_unmappable_and_report_reproduced() -> None:
    parsed = parse_scenario_file(copy.deepcopy(SCENARIO_VOXTA))
    # the parse report, pinned: warnings exact, unmappable named
    assert parsed.report.warnings == EXPECTED_SCENARIO_WARNINGS
    unmappable = parsed.report.to_dict()["unmappable"]
    assert [(e["path"], e["kind"]) for e in unmappable] == [
        ("scripts", "scripting"),
        ("events", "event"),
    ]
    assert parsed.unmappable_values["scripts"] == SCENARIO_VOXTA["scripts"]
    assert parsed.unmappable_values["events"] == SCENARIO_VOXTA["events"]
    # unmappable elements are re-emitted verbatim on Voxta export,
    # so a re-parse reproduces the same report entries exactly
    out = export_voxta(parsed)
    assert out["scripts"] == SCENARIO_VOXTA["scripts"]
    assert out["events"] == SCENARIO_VOXTA["events"]
    assert out["x_unknown"] == {"a": 1}
    reparsed = parse_scenario_file(copy.deepcopy(out))
    assert reparsed.report.to_dict()["unmappable"] == unmappable
    assert reparsed.unmappable_values == parsed.unmappable_values
