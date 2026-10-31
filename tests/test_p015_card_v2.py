"""P-015 acceptance: character card v2 import with full field fidelity.

The public v2 spec wraps the fields in a ``data`` envelope
(``{spec, spec_version, data}``); real files also circulate flat.
Before this slice the importer read v2 flat only, so the
spec-canonical wrapped shape — JSON and PNG alike — was rejected
with "card has no name". These tests pin: both shapes import,
every spec field is normalized (including ``character_version``,
newly a first-class field), unknown fields at both envelope
levels survive verbatim through v2 / v3 / PNG exports, and the
flat legacy shape keeps its founding export shape.
"""

from __future__ import annotations

import base64
import json
import struct
import zlib

from runmal.cards import import_card
from runmal.cards.exporter import export_json, export_png

WRAPPED_V2 = {
    "spec": "chara_card_v2",
    "spec_version": "2.0",
    "data": {
        "name": "Wrapped Witch",
        "description": "A spec-shaped card.",
        "personality": "Exact",
        "scenario": "A harbour at dawn.",
        "first_mes": "Envelope and all.",
        "mes_example": "<START>\n{{user}}: Hi\n{{char}}: Sealed.",
        "creator_notes": "Wrapped on purpose.",
        "system_prompt": "Stay wrapped.",
        "post_history_instructions": "Mind the envelope.",
        "alternate_greetings": ["One.", "Two."],
        "tags": ["wrapped", "spec"],
        "creator": "envelope-smith",
        "character_version": "2.1",
        "extensions": {"talkativeness": 0.4, "depth_prompt": {"depth": 2}},
        "character_book": {"name": "Envelope Lore", "entries": []},
        "x_data_unknown_string": "must-survive-inside",
        "x_data_unknown_number": 7.25,
        "x_data_unknown_bool": True,
        "x_data_unknown_null": None,
        "x_data_unknown_array": [1, "a", None, {"k": False}],
        "x_data_unknown_object": {"nested": {"list": [3, 2, 1]}},
    },
    "x_top_unknown": "must-survive-outside",
}


def as_bytes(obj: dict) -> bytes:
    return json.dumps(obj).encode("utf-8")


def _png_chunk(ctype: bytes, data: bytes) -> bytes:
    chunk = struct.pack(">I", len(data)) + ctype + data
    return chunk + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)


def make_png(obj: dict, chunk_type: bytes = b"tEXt") -> bytes:
    encoded = base64.b64encode(as_bytes(obj))
    if chunk_type == b"tEXt":
        payload = b"chara\x00" + encoded
    else:  # zTXt: keyword, NUL, compression byte 0, zlib stream
        payload = b"chara\x00\x00" + zlib.compress(encoded)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
        + _png_chunk(chunk_type, payload)
        + _png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
        + _png_chunk(b"IEND", b"")
    )


# --- the envelope imports -------------------------------------------------


def test_wrapped_v2_json_imports_every_spec_field() -> None:
    card = import_card(as_bytes(WRAPPED_V2), "card.json")
    assert card.spec_version == "2"
    assert card.source_format == "json"
    data = WRAPPED_V2["data"]
    for field in (
        "name",
        "description",
        "personality",
        "scenario",
        "first_mes",
        "mes_example",
        "creator_notes",
        "system_prompt",
        "post_history_instructions",
        "creator",
        "character_version",
    ):
        assert getattr(card, field) == data[field], field
    assert card.alternate_greetings == data["alternate_greetings"]
    assert card.tags == data["tags"]
    assert card.extensions == data["extensions"]
    assert card.character_book == data["character_book"]


def test_wrapped_v2_unknowns_kept_verbatim_in_raw() -> None:
    card = import_card(as_bytes(WRAPPED_V2), "card.json")
    data = card.raw["data"]
    assert data["x_data_unknown_string"] == "must-survive-inside"
    assert data["x_data_unknown_number"] == 7.25
    assert data["x_data_unknown_bool"] is True
    assert data["x_data_unknown_null"] is None
    assert data["x_data_unknown_array"] == [1, "a", None, {"k": False}]
    assert data["x_data_unknown_object"] == {"nested": {"list": [3, 2, 1]}}
    assert card.raw["x_top_unknown"] == "must-survive-outside"


def test_wrapped_v2_png_text_chunk_imports() -> None:
    card = import_card(make_png(WRAPPED_V2), "card.png")
    assert card.source_format == "png"
    assert card.spec_version == "2"
    assert card.name == "Wrapped Witch"
    assert card.character_version == "2.1"


def test_wrapped_v2_png_ztxt_chunk_imports() -> None:
    card = import_card(make_png(WRAPPED_V2, b"zTXt"), "card.png")
    assert card.name == "Wrapped Witch"
    assert card.first_mes == "Envelope and all."


def test_envelope_wins_and_top_level_fills_gaps() -> None:
    obj = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": "Top-Level Name (shadowed)",
        "personality": "from top level",
        "description": "only at the top level",
        "data": {"name": "Data Name", "personality": "from data"},
    }
    card = import_card(as_bytes(obj), "card.json")
    assert card.name == "Data Name"
    assert card.personality == "from data"
    assert card.description == "only at the top level"


def test_empty_envelope_falls_back_to_flat_fields() -> None:
    obj = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {},
        "name": "Flat Despite Envelope",
        "first_mes": "Still here.",
    }
    card = import_card(as_bytes(obj), "card.json")
    assert card.name == "Flat Despite Envelope"
    assert card.first_mes == "Still here."


def test_flat_v2_character_version_is_normalized() -> None:
    obj = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": "Flat",
        "character_version": "1.0-flat",
    }
    card = import_card(as_bytes(obj), "card.json")
    assert card.character_version == "1.0-flat"


def test_non_dict_data_on_flat_card_is_an_unknown_not_an_envelope() -> None:
    obj = {"name": "Odd", "data": "not-an-envelope"}
    card = import_card(as_bytes(obj), "card.json")
    assert card.name == "Odd"
    again = import_card(export_json(card, "2"), "export.json")
    assert again.raw["data"] == "not-an-envelope"


# --- round trips: nothing silently dropped -------------------------------


def test_wrapped_v2_round_trip_keeps_envelope_and_unknowns() -> None:
    card = import_card(as_bytes(WRAPPED_V2), "card.json")
    exported = json.loads(export_json(card, "2"))
    assert exported["spec"] == "chara_card_v2"
    assert exported["x_top_unknown"] == "must-survive-outside"
    data = exported["data"]
    assert data["name"] == "Wrapped Witch"
    assert data["character_version"] == "2.1"
    assert data["x_data_unknown_array"] == [1, "a", None, {"k": False}]
    assert data["x_data_unknown_object"] == {"nested": {"list": [3, 2, 1]}}
    assert data["x_data_unknown_null"] is None
    again = import_card(export_json(card, "2"), "export.json")
    assert again.name == card.name
    assert again.character_version == "2.1"
    assert again.extensions == card.extensions


def test_wrapped_v2_to_v3_keeps_both_unknown_levels() -> None:
    card = import_card(as_bytes(WRAPPED_V2), "card.json")
    again = import_card(export_json(card, "3"), "export.json")
    assert again.spec_version == "3"
    assert again.raw["x_top_unknown"] == "must-survive-outside"
    assert again.raw["data"]["x_data_unknown_string"] == "must-survive-inside"
    assert again.raw["data"]["character_version"] == "2.1"


def test_wrapped_v2_png_round_trip() -> None:
    card = import_card(as_bytes(WRAPPED_V2), "card.json")
    again = import_card(export_png(card), "export.png")
    assert again.name == "Wrapped Witch"
    assert again.raw["data"]["x_data_unknown_number"] == 7.25
    assert again.raw["x_top_unknown"] == "must-survive-outside"


def test_flat_v2_export_stays_flat() -> None:
    obj = {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": "Flat",
        "character_version": "0.9",
        "x_flat_unknown": [True],
    }
    card = import_card(as_bytes(obj), "card.json")
    exported = json.loads(export_json(card, "2"))
    assert "data" not in exported
    assert exported["name"] == "Flat"
    assert exported["character_version"] == "0.9"
    assert exported["x_flat_unknown"] == [True]
