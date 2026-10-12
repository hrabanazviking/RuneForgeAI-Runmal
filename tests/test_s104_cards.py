"""S104 acceptance: character card import (v1/v2/v3 JSON, PNG, CHARX)."""

from pathlib import Path

import pytest

import runmal.cards.parser as parser
from runmal.cards import CardErrorKind, CardParseError, import_card

FIXTURES = Path(__file__).parent / "fixtures" / "cards"


def read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_v1_json_imports() -> None:
    card = import_card(read("v1.json"), "card.json")
    assert card.spec_version == "1"
    assert card.name == "Test V1"
    assert card.first_mes == "Hello!"
    assert card.source_format == "json"


def test_v2_json_imports_with_unknown_fields_preserved() -> None:
    card = import_card(read("v2.json"), "card.json")
    assert card.spec_version == "2"
    assert card.name == "Test V2"
    assert card.alternate_greetings == ["Hi!", "Hey!"]
    assert card.tags == ["test", "fixture"]
    assert card.extensions == {"talkativeness": 0.5}
    assert card.character_book["name"] == "Lore"
    # INV-009: unknown-but-valid fields survive in raw
    assert card.raw["x_custom_unknown"] == "must-survive"


def test_v3_json_imports_data_object() -> None:
    card = import_card(read("v3.json"), "card.json")
    assert card.spec_version == "3"
    assert card.name == "Test V3"
    assert card.raw["data"]["x_custom_unknown"] == "must-survive-v3"


def test_png_chara_chunk_imports() -> None:
    card = import_card(read("card.png"), "card.png")
    assert card.source_format == "png"
    assert card.name == "Test V2"
    assert card.raw["x_custom_unknown"] == "must-survive"


def test_charx_imports_card_and_assets() -> None:
    card = import_card(read("card.charx"), "card.charx")
    assert card.source_format == "charx"
    assert card.spec_version == "3"
    assert card.name == "Test V3"
    assert card.assets["avatar.png"] == b"FAKEPNGDATA"
    # both URI spellings resolve
    assert card.resolve_asset("embeded://avatar.png") == b"FAKEPNGDATA"
    assert card.resolve_asset("embedded://avatar.png") == b"FAKEPNGDATA"


def test_truncated_json_typed_error() -> None:
    with pytest.raises(CardParseError) as exc_info:
        import_card(read("bad-truncated.json"), "card.json")
    assert exc_info.value.kind == CardErrorKind.TRUNCATED


def test_invalid_json_typed_error() -> None:
    with pytest.raises(CardParseError) as exc_info:
        import_card(read("bad-invalid.json"), "card.json")
    assert exc_info.value.kind == CardErrorKind.INVALID_JSON


def test_traversal_charx_rejected() -> None:
    with pytest.raises(CardParseError) as exc_info:
        import_card(read("traversal.charx"), "evil.charx")
    assert exc_info.value.kind == CardErrorKind.PATH_TRAVERSAL


def test_png_without_card_data_rejected() -> None:
    with pytest.raises(CardParseError) as exc_info:
        import_card(read("no-card.png"), "plain.png")
    assert exc_info.value.kind == CardErrorKind.NO_CARD_DATA


def test_oversized_input_rejected(monkeypatch) -> None:
    monkeypatch.setattr(parser, "MAX_INPUT_BYTES", 16)
    with pytest.raises(CardParseError) as exc_info:
        import_card(b"x" * 17, "card.json")
    assert exc_info.value.kind == CardErrorKind.INPUT_TOO_LARGE


def test_unsupported_spec_version_rejected() -> None:
    with pytest.raises(CardParseError) as exc_info:
        import_card(b'{"spec": "chara_card_v9", "spec_version": "9.0", "name": "X"}')
    assert exc_info.value.kind == CardErrorKind.UNSUPPORTED_VERSION


def test_card_without_name_rejected() -> None:
    with pytest.raises(CardParseError) as exc_info:
        import_card(b'{"description": "nameless"}')
    assert exc_info.value.kind == CardErrorKind.NOT_A_CARD
