"""S113 acceptance: CHARX export, safe asset extraction/storage, archive bounds."""

import io
import json
import zipfile
from pathlib import Path

import pytest

from runmal.cards import (
    CardErrorKind,
    CardParseError,
    export_charx,
    extract_assets,
    import_card,
)
from runmal.cards import parser as parser_module
from runmal.cards.models import CharacterCard

FIXTURES = Path(__file__).parent / "fixtures" / "cards"


def read(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def make_zip(entries: dict[str, bytes]) -> bytes:
    card_json = json.dumps(
        {"spec": "chara_card_v3", "spec_version": "3.0", "data": {"name": "Zip Test"}}
    )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("card.json", card_json)
        for name, data in entries.items():
            zf.writestr(name, data)
    return buf.getvalue()


def test_charx_round_trip_assets_byte_identical() -> None:
    card = import_card(read("card.charx"), "card.charx")
    blob = export_charx(card)
    card2 = import_card(blob, "roundtrip.charx")
    assert card2.source_format == "charx"
    assert card2.spec_version == "3"
    assert card2.name == card.name == "Test V3"
    assert card2.assets == card.assets
    assert card2.assets["avatar.png"] == b"FAKEPNGDATA"


def test_charx_export_is_deterministic() -> None:
    card = import_card(read("card.charx"), "card.charx")
    assert export_charx(card) == export_charx(card)


def test_full_fixture_round_trip_preserves_unknown_metadata() -> None:
    card = import_card(read("card_full.charx"), "card.charx")
    assert card.raw["data"]["x_custom_unknown"] == "must-survive-charx"
    card2 = import_card(export_charx(card), "roundtrip.charx")
    assert card2.name == "Test V3 Full"
    assert card2.raw["data"]["x_custom_unknown"] == "must-survive-charx"
    assert card2.extensions["talkativeness"] == 0.7
    assert card2.extensions["avatar"] == "embedded://avatar.png"
    assert card2.resolve_asset(card2.extensions["avatar"]) == b"FAKEPNGDATA-FULL"
    assert card2.assets["lore/notes.txt"] == b"fjord notes"
    assert card2.character_book["entries"][0]["keys"] == ["fjord"]


def test_export_upgrades_v2_card_to_v3_container() -> None:
    card = import_card(read("v2.json"), "card.json")
    card2 = import_card(export_charx(card), "up.charx")
    assert card2.spec_version == "3"
    assert card2.name == "Test V2"
    # v2 top-level unknowns move to the data level, per S105 semantics
    assert card2.raw["data"]["x_custom_unknown"] == "must-survive"


def test_export_rejects_unsafe_asset_name() -> None:
    card = import_card(read("card.charx"), "card.charx")
    card.assets["../evil.txt"] = b"evil"
    with pytest.raises(CardParseError) as exc_info:
        export_charx(card)
    assert exc_info.value.kind == CardErrorKind.PATH_TRAVERSAL


def test_export_rejects_card_json_collision() -> None:
    card = CharacterCard(name="Collision", assets={"card.json": b"{"})
    with pytest.raises(CardParseError) as exc_info:
        export_charx(card)
    assert exc_info.value.kind == CardErrorKind.BAD_ARCHIVE


def test_zip_bomb_style_asset_rejected() -> None:
    # 20 MiB of zeros compresses to ~20 KiB on the wire; the declared
    # uncompressed size trips the per-asset cap before any large read.
    blob = make_zip({"big.bin": b"\x00" * (20 * 1024 * 1024)})
    assert len(blob) < 1024 * 1024  # genuinely bomb-shaped on the wire
    with pytest.raises(CardParseError) as exc_info:
        import_card(blob, "bomb.charx")
    assert exc_info.value.kind == CardErrorKind.ASSET_TOO_LARGE


def test_too_many_files_rejected() -> None:
    blob = make_zip({f"f{i}.txt": b"x" for i in range(300)})
    with pytest.raises(CardParseError) as exc_info:
        import_card(blob, "many.charx")
    assert exc_info.value.kind == CardErrorKind.BAD_ARCHIVE


def test_total_asset_budget_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(parser_module, "MAX_TOTAL_ASSET_BYTES", 10)
    blob = make_zip({"a.bin": b"0123456789ABCDEF"})
    with pytest.raises(CardParseError) as exc_info:
        import_card(blob, "over.charx")
    assert exc_info.value.kind == CardErrorKind.ASSET_TOO_LARGE


def test_extract_assets_writes_inside_dest(tmp_path: Path) -> None:
    card = import_card(read("card_full.charx"), "card.charx")
    written = extract_assets(card, tmp_path / "out")
    assert written == ["avatar.png", "lore/notes.txt"]
    assert (tmp_path / "out" / "avatar.png").read_bytes() == b"FAKEPNGDATA-FULL"
    assert (tmp_path / "out" / "lore" / "notes.txt").read_bytes() == b"fjord notes"


def test_extract_assets_rejects_traversal(tmp_path: Path) -> None:
    card = CharacterCard(name="Evil", assets={"../evil.txt": b"evil"})
    with pytest.raises(CardParseError) as exc_info:
        extract_assets(card, tmp_path / "out")
    assert exc_info.value.kind == CardErrorKind.PATH_TRAVERSAL
    assert not (tmp_path / "evil.txt").exists()
