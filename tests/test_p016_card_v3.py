"""P-016 acceptance: character card v3 import — the newer spec's
additions mapped to Rúnmál's model with a written mapping.

Before this slice the v3 additions (assets, creator metadata,
group-only fields) survived only as opaque unknowns in `raw`
(P-005's round-trip pin). These tests pin the mapping in
docs/CARD_V3_IMPORT_2026-10-31.md: `nickname`,
`group_only_greetings`, `creator_notes_multilingual`, `source`,
`creation_date`, `modification_date`, and the declared `assets`
descriptors (model field `asset_refs`) are normalized on import,
defensively typed, and written back by the exporter — in full on
v3 export, set-only on v2 export so the v2-shaped storage path
keeps them. Cards are authored fresh in this module (P-005
discipline); the P-005 corpus fixture is read as well.
"""

from __future__ import annotations

import base64
import json
import struct
import zlib
from pathlib import Path

from runmal.cards import import_card
from runmal.cards.archive import export_charx
from runmal.cards.exporter import export_json, export_png

FIXTURES = Path(__file__).parent / "fixtures" / "interop"

V3_CARD = {
    "spec": "chara_card_v3",
    "spec_version": "3.0",
    "data": {
        "name": "Keeper of the Ninth Stair",
        "description": "A v3-shaped test card.",
        "personality": "Precise.",
        "scenario": "The tower library.",
        "first_mes": "Mind the ninth.",
        "mes_example": "",
        "creator_notes": "Notes in the default tongue.",
        "creator_notes_multilingual": {
            "en": "Notes in the default tongue.",
            "is": "Athugasemdir á íslensku.",
        },
        "system_prompt": "",
        "post_history_instructions": "",
        "alternate_greetings": ["Solo hello."],
        "group_only_greetings": ["A group, greeted.", "Together, then."],
        "tags": ["v3", "test"],
        "creator": "mapping-smith",
        "character_version": "3.1",
        "nickname": "Ninth",
        "source": ["https://example.invalid/cards/ninth", "Chub mirror"],
        "creation_date": 1759276800,
        "modification_date": 1761955200,
        "assets": [
            {
                "type": "icon",
                "uri": "embeded://avatar.png",
                "name": "main",
                "ext": "png",
            },
            {
                "type": "emotion",
                "uri": "embeded://expressions/amused.png",
                "name": "amused",
                "ext": "png",
                "x_packager_note": "extra keys ride verbatim",
            },
            {
                "type": "background",
                "uri": "https://example.invalid/stairs.jpg",
                "name": "stairs",
                "ext": "jpg",
            },
        ],
        "character_book": {},
        "extensions": {},
        "x_v3_unknown": {"must": "survive"},
    },
    "x_top_unknown": "top-level-must-survive",
}


def as_bytes(obj: dict) -> bytes:
    return json.dumps(obj).encode("utf-8")


def _png_chunk(ctype: bytes, data: bytes) -> bytes:
    chunk = struct.pack(">I", len(data)) + ctype + data
    return chunk + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)


def make_ccv3_png(obj: dict) -> bytes:
    payload = b"ccv3\x00" + base64.b64encode(as_bytes(obj))
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + _png_chunk(b"tEXt", payload)
        + _png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + _png_chunk(b"IEND", b"")
    )


def assert_additions_equal(first, second) -> None:
    for field in (
        "nickname",
        "group_only_greetings",
        "creator_notes_multilingual",
        "source",
        "creation_date",
        "modification_date",
        "asset_refs",
    ):
        assert getattr(first, field) == getattr(second, field), field


# --- the mapping ----------------------------------------------------------


def test_v3_additions_are_normalized() -> None:
    card = import_card(as_bytes(V3_CARD), "card.json")
    assert card.spec_version == "3"
    assert card.nickname == "Ninth"
    assert card.group_only_greetings == ["A group, greeted.", "Together, then."]
    assert card.creator_notes_multilingual == {
        "en": "Notes in the default tongue.",
        "is": "Athugasemdir á íslensku.",
    }
    assert card.source == ["https://example.invalid/cards/ninth", "Chub mirror"]
    assert card.creation_date == 1759276800
    assert card.modification_date == 1761955200
    assert [ref["type"] for ref in card.asset_refs] == [
        "icon",
        "emotion",
        "background",
    ]
    assert card.asset_refs[0]["uri"] == "embeded://avatar.png"
    # descriptor extra keys are the spec's extension room: verbatim
    assert card.asset_refs[1]["x_packager_note"] == "extra keys ride verbatim"
    # declared descriptors are not embedded bytes
    assert card.assets == {}


def test_find_asset_ref_matches_type_and_name() -> None:
    card = import_card(as_bytes(V3_CARD), "card.json")
    assert card.find_asset_ref(asset_type="icon")["name"] == "main"
    assert card.find_asset_ref(name="amused")["type"] == "emotion"
    assert card.find_asset_ref(asset_type="emotion", name="amused") is not None
    assert card.find_asset_ref(asset_type="emotion", name="main") is None
    assert card.find_asset_ref(asset_type="voice") is None


def test_p005_corpus_v3_card_normalizes() -> None:
    raw = (FIXTURES / "card_v3_rich.json").read_bytes()
    card = import_card(raw, "card.json")
    assert card.nickname == "Ninth"
    assert len(card.group_only_greetings) == 2
    assert [ref["type"] for ref in card.asset_refs] == [
        "icon",
        "emotion",
        "background",
    ]
    assert card.find_asset_ref(name="stairs")["ext"] == "jpg"


def test_ccv3_png_import_normalizes_additions() -> None:
    card = import_card(make_ccv3_png(V3_CARD), "card.png")
    assert card.spec_version == "3"
    assert card.nickname == "Ninth"
    assert card.group_only_greetings[0] == "A group, greeted."
    assert len(card.asset_refs) == 3


def test_v3_fields_recognized_by_name_on_flat_v2() -> None:
    flat = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": "Flat Carrier",
        "nickname": "Flatty",
        "group_only_greetings": ["Group hi."],
        "creation_date": 1700000000,
    }
    card = import_card(as_bytes(flat), "card.json")
    assert card.spec_version == "2"
    assert card.nickname == "Flatty"
    assert card.group_only_greetings == ["Group hi."]
    assert card.creation_date == 1700000000
    assert card.modification_date is None


# --- defensive typing -----------------------------------------------------


def test_additions_are_defensively_typed() -> None:
    hostile = json.loads(as_bytes(V3_CARD))
    data = hostile["data"]
    data["group_only_greetings"] = ["kept", None, 42, True]
    data["source"] = ["kept", None, {"x": 1}]
    data["creator_notes_multilingual"] = {"en": "kept", "fr": 7, "de": None}
    data["assets"] = [{"type": "icon"}, "not-an-object", None, 5]
    data["nickname"] = 42
    card = import_card(as_bytes(hostile), "card.json")
    assert card.group_only_greetings == ["kept"]
    assert card.source == ["kept"]
    assert card.creator_notes_multilingual == {"en": "kept"}
    assert card.asset_refs == [{"type": "icon"}]
    assert card.nickname == ""


def test_timestamps_accept_int_and_integral_float_only() -> None:
    obj = json.loads(as_bytes(V3_CARD))
    obj["data"]["creation_date"] = 1759276800.0
    obj["data"]["modification_date"] = True
    card = import_card(as_bytes(obj), "card.json")
    assert card.creation_date == 1759276800
    assert card.modification_date is None  # a bool is not a timestamp
    obj["data"]["creation_date"] = "1759276800"
    obj["data"]["modification_date"] = 1.5
    card = import_card(as_bytes(obj), "card.json")
    assert card.creation_date is None  # strings are not coerced
    assert card.modification_date is None  # fractional seconds rejected


# --- export is the other half of the mapping -------------------------------


def test_v3_export_round_trip_keeps_additions_normalized() -> None:
    card = import_card(as_bytes(V3_CARD), "card.json")
    exported = json.loads(export_json(card, "3"))
    data = exported["data"]
    assert data["nickname"] == "Ninth"
    assert data["group_only_greetings"] == card.group_only_greetings
    assert data["assets"][1]["x_packager_note"] == "extra keys ride verbatim"
    assert data["creation_date"] == 1759276800
    assert data["x_v3_unknown"] == {"must": "survive"}
    assert exported["x_top_unknown"] == "top-level-must-survive"
    again = import_card(export_json(card, "3"), "export.json")
    assert_additions_equal(card, again)


def test_v3_export_omits_absent_timestamps_never_fabricates() -> None:
    raw = (Path(__file__).parent / "fixtures" / "cards" / "v3.json").read_bytes()
    card = import_card(raw, "card.json")
    assert card.creation_date is None and card.modification_date is None
    data = json.loads(export_json(card, "3"))["data"]
    assert "creation_date" not in data
    assert "modification_date" not in data
    # the structural additions are written in full on v3 export
    assert data["nickname"] == ""
    assert data["group_only_greetings"] == []
    assert data["assets"] == []


def test_v2_export_keeps_set_additions_for_the_storage_path() -> None:
    # characters/service.py stores cards through export_json(card, "2");
    # a v3 card's additions must survive that storage shape.
    card = import_card(as_bytes(V3_CARD), "card.json")
    stored = export_json(card, "2")
    again = import_card(stored, "card.json")
    assert_additions_equal(card, again)


def test_v2_export_of_plain_v2_card_gains_no_v3_keys() -> None:
    raw = (Path(__file__).parent / "fixtures" / "cards" / "v2.json").read_bytes()
    card = import_card(raw, "card.json")
    exported = json.loads(export_json(card, "2"))
    for key in (
        "nickname",
        "group_only_greetings",
        "creator_notes_multilingual",
        "source",
        "assets",
        "creation_date",
        "modification_date",
    ):
        assert key not in exported, key
    # and its PNG export (the same v2 payload) gains none either
    png_card = import_card(export_png(card), "card.png")
    assert png_card.nickname == "" and png_card.asset_refs == []


def test_charx_round_trip_keeps_additions_and_separates_bytes() -> None:
    card = import_card(as_bytes(V3_CARD), "card.json")
    card.assets = {"avatar.png": b"\x89PNG-fake-bytes"}
    again = import_card(export_charx(card), "card.charx")
    assert_additions_equal(card, again)
    # embedded bytes resolve through the declared embeded:// URI
    ref = again.find_asset_ref(asset_type="icon")
    assert again.resolve_asset(ref["uri"]) == b"\x89PNG-fake-bytes"
