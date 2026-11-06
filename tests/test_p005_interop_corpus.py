"""P-005 acceptance: the interop corpus.

Real-world-shaped cards, lorebooks, presets, a chat file, and a
persona file (all authored fresh for this corpus — see
``manifest.json`` provenance) driven through Rúnmál's current
importers. What survives is asserted; what is still lost is pinned
exactly, with the losing field set named, so the Part II/III slices
that close a loss must update this test deliberately instead of the
loss being discovered by a user.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from runmal.cards import import_card
from runmal.cards.exporter import export_json
from runmal.lorebooks.transfer import parse_import
from runmal.presets.interop import parse_preset

CORPUS = Path(__file__).parent / "fixtures" / "interop"
MANIFEST = json.loads((CORPUS / "manifest.json").read_text(encoding="utf-8"))
ENTRIES = {entry["file"]: entry for entry in MANIFEST["fixtures"]}


def read(name: str) -> bytes:
    return (CORPUS / name).read_bytes()


def read_json(name: str) -> dict:
    return json.loads(read(name))


# --- manifest integrity -------------------------------------------------


def test_manifest_covers_every_fixture_file() -> None:
    on_disk = {
        p.name
        for p in CORPUS.iterdir()
        if p.is_file() and p.name not in ("manifest.json", "make_corpus.py")
    }
    assert on_disk == set(ENTRIES), "manifest and corpus directory disagree"
    assert len(ENTRIES) == 12


def test_manifest_hashes_match_bytes_on_disk() -> None:
    for name, entry in ENTRIES.items():
        data = read(name)
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], name
        assert len(data) == entry["bytes"], name
        assert entry["kind"] and entry["shape"] and entry["expectation"]


# --- character cards ----------------------------------------------------


def test_v2_rich_card_imports_with_full_depth() -> None:
    card = import_card(read("card_v2_rich.json"), "card.json")
    assert card.spec_version == "2"
    assert card.name.startswith("Sigríðr")
    assert len(card.alternate_greetings) == 3
    assert card.extensions["talkativeness"] == 0.65
    assert card.extensions["depth_prompt"]["depth"] == 4
    assert card.extensions["world"] == "Sigríðr's World"
    # embedded character book rides as opaque data today
    assert card.character_book["name"] == "Sigríðr's World"
    assert card.character_book["entries"]["0"]["keys"] == ["Hrafnkel", "longship"]


def test_v2_rich_unknown_fields_survive_both_export_round_trips() -> None:
    card = import_card(read("card_v2_rich.json"), "card.json")
    for version in ("2", "3"):
        again = import_card(export_json(card, version), "export.json")
        assert again.name == card.name
        assert again.description == card.description
        assert again.extensions["regex_scripts"][0]["scriptName"] == "Trim asterisks"
        raw = again.raw["data"] if version == "3" else again.raw
        assert raw["x_corpus_unknown_string"] == "must-survive"
        assert raw["x_corpus_unknown_number"] == 42.5
        assert raw["x_corpus_unknown_bool"] is False
        assert raw["x_corpus_unknown_null"] is None
        assert raw["x_corpus_unknown_array"] == ["a", 1, None, {"k": "v"}]
        assert raw["x_corpus_unknown_object"] == {"nested": {"list": [True, False]}}


def test_v3_rich_assets_and_group_greetings_survive_round_trip() -> None:
    card = import_card(read("card_v3_rich.json"), "card.json")
    assert card.spec_version == "3"
    again = import_card(export_json(card, "3"), "export.json")
    data = again.raw["data"]
    assert [a["type"] for a in data["assets"]] == ["icon", "emotion", "background"]
    assert data["group_only_greetings"][0].startswith('"A group,')
    assert data["nickname"] == "Ninth"
    assert data["creator_character_version"] == "3.0-corpus"
    assert data["x_corpus_v3_unknown"] == {"must": "survive-v3-round-trip"}
    assert again.raw["x_corpus_top_level_unknown"] == "v3-top-level-must-survive"


def test_v1_minimal_imports_with_empty_defaults() -> None:
    card = import_card(read("card_v1_minimal.json"), "card.json")
    assert card.spec_version == "1"
    assert card.name == "Old Bruni"
    assert card.personality == "" and card.tags == [] and card.extensions == {}


def test_v2_edge_nulls_in_lists_are_dropped_never_stringified() -> None:
    card = import_card(read("card_v2_edge.json"), "card.json")
    assert card.alternate_greetings == ["The one real greeting."]
    assert card.tags == ["edge"]
    assert card.raw["x_corpus_deep"]["a"]["b"]["c"]["d"][1][1][1] == {"e": "deep"}
    assert card.raw["x_corpus_zero"] == 0 and card.raw["x_corpus_null"] is None


def test_dual_chunk_png_prefers_ccv3_payload() -> None:
    card = import_card(read("card_dual_ccv3.png"), "card.png")
    assert card.spec_version == "3"
    assert card.name == "Dual Card (v3 payload)"
    assert card.first_mes == "New greeting."


# --- lorebooks ----------------------------------------------------------

# Source fields of lorebook_worldinfo_full.json entry 0 that today's
# importer still drops. Part III slices (selective logic P-032,
# timed effects P-033, groups P-034, depth P-038, probability P-036)
# own most of these; a slice that lands one must remove it here.
WORLDINFO_DROPPED_TODAY = {
    "automationId",
    "characterFilter",
    "decorators",
    "delayUntilRecursion",
    "depth",
    "displayIndex",
    "excludeRecursion",
    "group",
    "groupOverride",
    "groupWeight",
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
    "vectorized",
}
WORLDINFO_MAPPED_SOURCE_FIELDS = {
    "comment",
    "content",
    "key",
    "keysecondary",
    "selectiveLogic",
    "constant",
    "disable",
    "order",
    "position",
    "caseSensitive",
    "matchWholeWords",
    "sticky",
    "cooldown",
    "delay",
}


def test_worldinfo_full_mapped_fields_and_pinned_losses() -> None:
    source = read_json("lorebook_worldinfo_full.json")
    book, entries = parse_import(source)
    assert book["name"] == "Corpus Full-Feature World"
    assert len(entries) == 3
    gale = entries[0]
    assert gale["name"] == "The Gale-Bell"
    assert gale["keys"] == ["gale-bell", "bell"]
    assert gale["secondary_keys"] == ["weather"]
    assert gale["priority"] == 300
    assert gale["case_sensitive"] is True
    # P-005 fixes pinned: whole-word flag honoured, timed effects mapped
    assert gale["whole_word"] is False
    assert (gale["sticky_prompts"], gale["cooldown_prompts"], gale["delay_prompts"]) == (
        3,
        2,
        1,
    )
    # position 4 (at-depth in the mirror) collapses to before_char
    # today — pinned loss, P-038 owns the real mapping
    assert gale["position"] == "before_char"
    dropped = set(source["entries"]["0"]) - WORLDINFO_MAPPED_SOURCE_FIELDS
    assert dropped == WORLDINFO_DROPPED_TODAY


def test_worldinfo_null_fields_import_with_defaults() -> None:
    book, entries = parse_import(read_json("lorebook_worldinfo_nulls.json"))
    assert book["name"] == "Corpus Null-Field World"
    first, second = entries
    assert first["priority"] == 100 and first["position"] == "before_char"
    assert first["secondary_keys"] == []
    assert (first["sticky_prompts"], first["cooldown_prompts"]) == (0, 0)
    assert second["priority"] == 150 and second["sticky_prompts"] == 2


def test_native_rich_book_parses_fully() -> None:
    book, entries = parse_import(read_json("lorebook_native_rich.json"))
    assert book == {
        "name": "Corpus Native Book",
        "description": "Rúnmál native shape at full stretch (the S304 export shape).",
        "scan_depth": 5,
        "token_budget": 800,
    }
    ferry = entries[0]
    assert ferry["sticky_prompts"] == 3 and ferry["whole_word"] is False
    assert ferry["position"] == "at_depth"


# --- presets ------------------------------------------------------------


def test_st_textcompletion_preset_imports_with_real_mapping() -> None:
    parsed = parse_preset(read("preset_st_textcompletion.json"))
    assert parsed.name == "Corpus Community Preset"
    assert parsed.source_format == "st-text"
    # P-021's real mapping: mirror spellings land in the canonical bag
    assert parsed.params == {
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
    # seed -1 is the unset sentinel: absent from the bag, kept in raw
    assert "seed" not in parsed.params and parsed.raw["seed"] == -1
    # mirror-only sampler keys ride in raw carriage, never in the bag
    assert parsed.raw["tfs"] == 0.95 and "tfs" not in parsed.params
    assert parsed.raw["dry_base"] == 1.75 and "dry_base" not in parsed.params


def test_st_chatcompletion_preset_imports_with_bag_and_carriage() -> None:
    parsed = parse_preset(read("preset_st_chatcompletion.json"))
    assert parsed.source_format == "st-chat"
    assert parsed.name == "Imported preset"
    assert parsed.params == {
        "temperature": 0.85,
        "top_p": 0.95,
        "frequency_penalty": 0,
        "presence_penalty": 0,
        "max_tokens": 900,
        "context_length": 128000,
    }
    assert [p["identifier"] for p in parsed.prompts] == [
        "main",
        "worldInfoBefore",
        "jailbreak",
    ]
    assert parsed.prompts[0]["content"].startswith("You are an expert actor")
    assert [e["identifier"] for e in parsed.prompt_order] == [
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
        e for e in parsed.prompt_order if e["identifier"] == "charDescription"
    )
    assert char_entry["enabled"] is False
    # carriage: backend/model keys ride in raw, never in the bag
    assert parsed.raw["logit_bias"] == {} and "logit_bias" not in parsed.params
    assert parsed.raw["model"] == "corpus-model"


# --- chat + persona (formats whose importers land later) -----------------


def test_st_chat_jsonl_is_well_formed_with_swipes_as_data() -> None:
    lines = read("chat_st.jsonl").decode("utf-8").strip().splitlines()
    records = [json.loads(line) for line in lines]
    header, messages = records[0], records[1:]
    assert header["character_name"] == "Old Bruni"
    assert header["user_name"] == "Ferry Passenger"
    assert len(messages) == 3
    assert messages[0]["swipes"] == [
        "Mind the gap. It minds you.",
        "Step careful. The planks remember rain.",
    ]
    assert messages[0]["swipe_id"] == 0


def test_st_persona_shape_is_well_formed() -> None:
    persona = read_json("persona_st.json")
    assert persona["name"] == "Ferry Passenger"
    assert "{{user}}" in persona["prompt"]
    assert persona["description_position"] == "in_prompt"
