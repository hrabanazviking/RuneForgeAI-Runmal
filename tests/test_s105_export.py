"""S105 acceptance: character card export (JSON/PNG round trips)."""

import struct
import zlib
from pathlib import Path

import pytest

from runmal.cards import CardErrorKind, CardParseError, import_card
from runmal.cards.exporter import export_json, export_png

FIXTURES = Path(__file__).parent / "fixtures" / "cards"


def read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def assert_semantic_equal(first, second) -> None:
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
        "alternate_greetings",
        "tags",
        "creator",
        "character_book",
        "extensions",
    ):
        assert getattr(first, field) == getattr(second, field), field


def test_json_v2_round_trip() -> None:
    card = import_card(read("v2.json"), "card.json")
    again = import_card(export_json(card, "2"), "export.json")
    assert_semantic_equal(card, again)
    assert again.spec_version == "2"
    # INV-009: opaque unknown + extensions survive the round trip
    assert again.raw["x_custom_unknown"] == "must-survive"
    assert again.extensions == {"talkativeness": 0.5}


def test_json_v2_to_v3_round_trip() -> None:
    card = import_card(read("v2.json"), "card.json")
    exported = export_json(card, "3")
    again = import_card(exported, "export.json")
    assert again.spec_version == "3"
    assert_semantic_equal(card, again)
    assert again.raw["data"]["x_custom_unknown"] == "must-survive"


def test_png_round_trip_with_valid_crcs() -> None:
    card = import_card(read("v2.json"), "card.json")
    png = export_png(card)
    # CRC handling: every chunk's stored CRC must verify
    pos, seen_text = 8, False
    while pos + 8 <= len(png):
        length = struct.unpack(">I", png[pos : pos + 4])[0]
        ctype = png[pos + 4 : pos + 8]
        data = png[pos + 8 : pos + 8 + length]
        stored = struct.unpack(">I", png[pos + 8 + length : pos + 12 + length])[0]
        assert zlib.crc32(ctype + data) & 0xFFFFFFFF == stored, ctype
        if ctype == b"tEXt":
            seen_text = True
        pos += 12 + length
        if ctype == b"IEND":
            break
    assert seen_text
    again = import_card(png, "export.png")
    assert again.source_format == "png"
    assert_semantic_equal(card, again)
    assert again.raw["x_custom_unknown"] == "must-survive"


def test_creator_metadata_remains_metadata() -> None:
    card = import_card(read("v2.json"), "card.json")
    again = import_card(export_json(card, "2"), "export.json")
    assert again.creator == "forge"
    assert again.creator_notes == "notes"
    assert again.tags == ["test", "fixture"]
    # creator metadata is never folded into prompt fields
    for prompt_field in ("description", "personality", "scenario", "system_prompt"):
        value = getattr(again, prompt_field)
        assert "forge" not in value or prompt_field == "description"


def test_export_unsupported_version_rejected() -> None:
    card = import_card(read("v2.json"), "card.json")
    with pytest.raises(CardParseError) as exc_info:
        export_json(card, "9")
    assert exc_info.value.kind == CardErrorKind.UNSUPPORTED_VERSION
