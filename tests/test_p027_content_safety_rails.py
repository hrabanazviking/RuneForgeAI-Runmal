"""P-027 acceptance: content safety rails — imported content is data.

Hostile fixtures are authored INLINE in this module only — never as
new files under ``tests/fixtures/interop/`` (the corpus manifest
test fails on unlisted files). Shapes rest on the existing house
parsers: cards (S104/P-015/P-016), lorebooks (P-019), presets
(P-021), personas (P-018), chat files (P-020), CHARX (S113) and
``.runmal`` archives (S801/S802).

Groups: size caps; nesting depth + duplicate keys; decompression
bombs in PNG ``zTXt`` chunks; archive member audits + restore
traversal; inert-content pins (script-bearing extensions and
external asset URIs stay data, are never fetched, and round-trip
verbatim); refusal messages never leak payload body content; the
HTTP surface answers a hostile import with a client error, never
500; and the P-005 corpus still imports.
"""

from __future__ import annotations

import io
import json
import stat
import struct
import warnings
import zipfile
import zlib
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.assets.service import build_asset_plan
from runmal.auth import get_or_create_credential
from runmal.cards import CardErrorKind, CardParseError, import_card
from runmal.cards.exporter import export_json
from runmal.chats.fileimport import parse_chat_jsonl
from runmal.chats.filemodels import INVALID_JSON
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.lorebooks.interop import (
    MAX_LOREBOOK_BYTES,
    LorebookParseError,
    parse_lorebook_file,
)
from runmal.lorebooks.scan import ScanEntry, scan_entries
from runmal.lorebooks.transfer import parse_import
from runmal.persona.interop import (
    MAX_PERSONA_BYTES,
    PersonaParseError,
    parse_persona,
)
from runmal.portable.archive import ArchiveError, validate_archive
from runmal.portable.restore import import_archive
from runmal.presets.interop import PresetParseError, parse_preset
from runmal.prompt.variables import resolve_variables
from runmal.safety import (
    SafetyError,
    SafetyErrorKind,
    audit_zip_members,
    bounded_zlib_decompress,
    check_bytes,
    safe_json_loads,
    validate_json_tree,
)

CORPUS = Path(__file__).parent / "fixtures" / "interop"
MARKER = "P027LEAKMARKER7f3a9c"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def deep_obj_text(depth: int) -> str:
    return '{"k":' * depth + "1" + "}" * depth


def nested_value(depth: int):
    value = 1
    for _ in range(depth):
        value = [value]
    return value


def _png_chunk(ctype: bytes, data: bytes) -> bytes:
    chunk = struct.pack(">I", len(data)) + ctype + data
    return chunk + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)


def make_png(chunks: list[tuple[bytes, bytes]]) -> bytes:
    out = [PNG_SIGNATURE, _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))]
    out.extend(_png_chunk(ctype, data) for ctype, data in chunks)
    out.append(_png_chunk(b"IEND", b""))
    return b"".join(out)


def zip_bytes(members: list[tuple[object, bytes]]) -> bytes:
    buffer = io.BytesIO()
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        with zipfile.ZipFile(buffer, "w") as zf:
            for name, data in members:
                zf.writestr(name, data)
    return buffer.getvalue()


def write_zip(path: Path, members: list[tuple[object, bytes]]) -> Path:
    path.write_bytes(zip_bytes(members))
    return path


# --- 1. size caps ---------------------------------------------------------


def test_lorebook_just_over_32mib_refused_typed() -> None:
    with pytest.raises(LorebookParseError) as exc_info:
        parse_lorebook_file(b" " * (MAX_LOREBOOK_BYTES + 1))
    assert "exceeding limit" in str(exc_info.value)


def test_persona_just_over_8mib_refused_typed() -> None:
    with pytest.raises(PersonaParseError) as exc_info:
        parse_persona(b" " * (MAX_PERSONA_BYTES + 1))
    assert "exceeding limit" in str(exc_info.value)


def test_check_bytes_limit_boundary() -> None:
    assert check_bytes(b"1234", 4) is None
    with pytest.raises(SafetyError) as exc_info:
        check_bytes(b"12345", 4)
    assert exc_info.value.kind is SafetyErrorKind.INPUT_TOO_LARGE


def test_safe_json_loads_size_limit() -> None:
    assert safe_json_loads(b'{"a": 1}', limit=8) == {"a": 1}
    with pytest.raises(SafetyError) as exc_info:
        safe_json_loads(b'{"a": 1}', limit=4)
    assert exc_info.value.kind is SafetyErrorKind.INPUT_TOO_LARGE


# --- 2. depth + duplicate keys --------------------------------------------


def test_safe_json_loads_depth_boundary() -> None:
    ok = "[" * 100 + "1" + "]" * 100
    assert isinstance(safe_json_loads(ok), list)
    with pytest.raises(SafetyError) as exc_info:
        safe_json_loads("[" * 101 + "1" + "]" * 101)
    assert exc_info.value.kind is SafetyErrorKind.NESTING_TOO_DEEP
    with pytest.raises(SafetyError) as exc_info:
        safe_json_loads(deep_obj_text(10_000))
    assert exc_info.value.kind is SafetyErrorKind.NESTING_TOO_DEEP


def test_card_10k_deep_refused_typed_not_recursion() -> None:
    with pytest.raises(CardParseError) as exc_info:
        import_card(deep_obj_text(10_000).encode(), "card.json")
    assert exc_info.value.kind is CardErrorKind.INVALID_JSON
    assert "depth" in str(exc_info.value).lower()


def test_lorebook_10k_deep_refused_typed_not_recursion() -> None:
    with pytest.raises(LorebookParseError) as exc_info:
        parse_lorebook_file(deep_obj_text(10_000).encode())
    assert "depth" in str(exc_info.value).lower()


def test_preset_10k_deep_refused_typed_not_recursion() -> None:
    with pytest.raises(PresetParseError) as exc_info:
        parse_preset(deep_obj_text(10_000))
    assert "depth" in str(exc_info.value).lower()


def test_persona_10k_deep_refused_typed_not_recursion() -> None:
    with pytest.raises(PersonaParseError) as exc_info:
        parse_persona(deep_obj_text(10_000))
    assert "depth" in str(exc_info.value).lower()


def test_chat_line_10k_deep_is_typed_line_error_not_recursion() -> None:
    header = json.dumps({"character_name": "C", "user_name": "U"})
    data = header + "\n" + deep_obj_text(10_000)
    result = parse_chat_jsonl(data)
    deep_issues = [
        i for i in result.report.issues if i.kind == INVALID_JSON and i.line_no == 2
    ]
    assert deep_issues and "depth" in deep_issues[0].detail.lower()
    assert result.report.imported_messages == 0


def test_lorebook_transfer_deep_dict_refused_typed() -> None:
    data: dict = {"name": "B", "entries": []}
    node = data
    for _ in range(150):
        node["x"] = {}
        node = node["x"]
    with pytest.raises(ValueError) as exc_info:
        parse_import(data)
    assert "depth" in str(exc_info.value).lower()
    with pytest.raises(SafetyError) as exc_info:
        validate_json_tree(data)
    assert exc_info.value.kind is SafetyErrorKind.NESTING_TOO_DEEP


def test_duplicate_keys_refused_on_card_parser() -> None:
    with pytest.raises(CardParseError) as exc_info:
        import_card(b'{"name": "First", "name": "Second"}', "card.json")
    assert "duplicate" in str(exc_info.value).lower()


def test_duplicate_keys_refused_on_lorebook_file_parser() -> None:
    with pytest.raises(LorebookParseError) as exc_info:
        parse_lorebook_file(b'{"name": "A", "name": "B", "entries": {}}')
    assert "duplicate" in str(exc_info.value).lower()


def test_duplicate_keys_refused_on_preset_parser() -> None:
    with pytest.raises(PresetParseError) as exc_info:
        parse_preset('{"preset": "A", "preset": "B", "temperature": 0.9}')
    assert "duplicate" in str(exc_info.value).lower()


def test_duplicate_keys_refused_on_persona_parser() -> None:
    with pytest.raises(PersonaParseError) as exc_info:
        parse_persona('{"name": "A", "name": "B"}')
    assert "duplicate" in str(exc_info.value).lower()


def test_duplicate_keys_in_chat_line_are_typed_line_error() -> None:
    header = json.dumps({"character_name": "C", "user_name": "U"})
    line = '{"mes": "hi", "mes": "again", "is_user": true}'
    result = parse_chat_jsonl(header + "\n" + line)
    dup = [i for i in result.report.issues if i.kind == INVALID_JSON and i.line_no == 2]
    assert dup and "duplicate" in dup[0].detail.lower()


def test_valid_nested_imports_at_moderate_depth_are_fine() -> None:
    card = import_card(
        json.dumps({"name": "DeepOk", "extensions": {"deep": nested_value(50)}}).encode(),
        "card.json",
    )
    assert card.extensions["deep"] == nested_value(50)

    book = parse_lorebook_file(
        {
            "name": "DeepBook",
            "entries": {
                "0": {
                    "comment": "E",
                    "content": "c",
                    "key": ["k"],
                    "x_deep": nested_value(50),
                }
            },
        }
    )
    assert book.entries[0].extra["x_deep"] == nested_value(50)

    preset = parse_preset(
        json.dumps({"preset": "DeepPreset", "temp": 0.9, "top_p": 0.92, "top_k": 40, "x_deep": nested_value(50)})
    )
    assert preset.params["temperature"] == 0.9

    persona = parse_persona(json.dumps({"name": "DeepP", "x_deep": nested_value(50)}))
    assert persona.raw["x_deep"] == nested_value(50)

    book_fields, _entries = parse_import(
        {"name": "B", "entries": [], "x_deep": nested_value(50)}
    )
    assert book_fields["name"] == "B"


# --- 3. decompression (PNG zTXt) ------------------------------------------

CARD_OBJ = {"spec": "chara_card_v2", "spec_version": "2.0", "name": "Zed"}


def _ztxt(keyword: bytes, raw_text: bytes) -> bytes:
    return keyword + b"\x00\x00" + zlib.compress(raw_text)


def test_png_ztxt_inflating_past_cap_is_refused_safely() -> None:
    bomb = _ztxt(b"chara", b"A" * (32 * 1024 * 1024 + 1024))
    with pytest.raises(CardParseError) as exc_info:
        import_card(make_png([(b"zTXt", bomb)]), "card.png")
    assert exc_info.value.kind is CardErrorKind.NO_CARD_DATA


def test_png_ztxt_bomb_chunk_skipped_valid_text_chunk_still_parses() -> None:
    bomb = _ztxt(b"note", b"A" * (32 * 1024 * 1024 + 1024))
    payload = b"chara\x00" + __import__("base64").b64encode(json.dumps(CARD_OBJ).encode())
    card = import_card(make_png([(b"zTXt", bomb), (b"tEXt", payload)]), "card.png")
    assert card.name == "Zed"


def test_png_normal_ztxt_card_still_parses() -> None:
    import base64

    payload = _ztxt(b"chara", base64.b64encode(json.dumps(CARD_OBJ).encode()))
    card = import_card(make_png([(b"zTXt", payload)]), "card.png")
    assert card.name == "Zed" and card.source_format == "png"


def test_bounded_zlib_decompress_direct() -> None:
    assert bounded_zlib_decompress(zlib.compress(b"hello"), limit=16) == b"hello"
    with pytest.raises(SafetyError) as exc_info:
        bounded_zlib_decompress(zlib.compress(b"x" * 4096), limit=128)
    assert exc_info.value.kind is SafetyErrorKind.DECOMPRESSION_TOO_LARGE


# --- 4. archives ------------------------------------------------------------

CARD_JSON = json.dumps(CARD_OBJ).encode()


def test_charx_duplicate_member_is_bad_archive() -> None:
    blob = zip_bytes([("card.json", CARD_JSON), ("card.json", CARD_JSON)])
    with pytest.raises(CardParseError) as exc_info:
        import_card(blob, "evil.charx")
    assert exc_info.value.kind is CardErrorKind.BAD_ARCHIVE


def test_charx_symlink_member_is_bad_archive() -> None:
    info = zipfile.ZipInfo("assets/evil-link")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    blob = zip_bytes([("card.json", CARD_JSON), (info, b"/etc/passwd")])
    with pytest.raises(CardParseError) as exc_info:
        import_card(blob, "evil.charx")
    assert exc_info.value.kind is CardErrorKind.BAD_ARCHIVE


def test_runmal_validate_archive_duplicate_member(tmp_path) -> None:
    path = write_zip(
        tmp_path / "dup.runmal",
        [("manifest.json", b"{}"), ("manifest.json", b"{}")],
    )
    with pytest.raises(ArchiveError):
        validate_archive(path)


def test_runmal_validate_archive_link_member(tmp_path) -> None:
    info = zipfile.ZipInfo("assets/link")
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    path = write_zip(tmp_path / "link.runmal", [(info, b"/etc/passwd")])
    with pytest.raises(ArchiveError) as exc_info:
        validate_archive(path)
    assert "link" in str(exc_info.value).lower()


def test_runmal_validate_archive_oversized_declared_member(tmp_path) -> None:
    # Highly compressible: the zip stays small while the declared
    # (inflated) member size passes the 64 MiB member cap.
    path = write_zip(
        tmp_path / "big.runmal",
        [("assets/big.bin", b"\x00" * (64 * 1024 * 1024 + 1))],
    )
    with pytest.raises(ArchiveError) as exc_info:
        validate_archive(path)
    assert "exceeding limit" in str(exc_info.value)


def test_audit_zip_members_direct_kinds() -> None:
    def info(name, size=1, external_attr=0):
        return SimpleNamespace(filename=name, file_size=size, external_attr=external_attr)

    with pytest.raises(SafetyError) as dup:
        audit_zip_members(
            [info("a"), info("a")], max_members=10, max_member_bytes=10, max_total_bytes=10
        )
    assert dup.value.kind is SafetyErrorKind.DUPLICATE_MEMBER
    link_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(SafetyError) as link:
        audit_zip_members(
            [info("a", external_attr=link_attr)],
            max_members=10,
            max_member_bytes=10,
            max_total_bytes=10,
        )
    assert link.value.kind is SafetyErrorKind.LINK_MEMBER
    with pytest.raises(SafetyError) as big:
        audit_zip_members(
            [info("a", size=11)], max_members=10, max_member_bytes=10, max_total_bytes=100
        )
    assert big.value.kind is SafetyErrorKind.ARCHIVE_MEMBER_TOO_LARGE
    with pytest.raises(SafetyError) as total:
        audit_zip_members(
            [info("a", size=6), info("b", size=6)],
            max_members=10,
            max_member_bytes=10,
            max_total_bytes=10,
        )
    assert total.value.kind is SafetyErrorKind.ARCHIVE_TOTAL_TOO_LARGE


async def test_restore_traversal_asset_writes_nothing_outside_staging(tmp_path) -> None:
    path = write_zip(
        tmp_path / "evil.runmal",
        [("manifest.json", b"{}"), ("assets/../../escape.txt", MARKER.encode())],
    )
    staging = tmp_path / "staging"
    with pytest.raises(ArchiveError):
        await import_archive(path, staging)
    assert not (tmp_path / "escape.txt").exists()
    assert not staging.exists()


# --- 5. inert content pins --------------------------------------------------

INERT_CARD = {
    "spec": "chara_card_v3",
    "spec_version": "3.0",
    "data": {
        "name": "Inert",
        "description": "Macros stay literal: {{setvar::mood::calm}} {{getvar::mood}}",
        "extensions": {
            "custom_script": "<script>alert('p027')</script>",
            "onload": "javascript:alert(1)",
            "nested": {"code": "eval('1+1')", "html": "<img src=x onerror=alert(1)>"},
        },
        "assets": [
            {
                "type": "background",
                "uri": "https://example.invalid/stairs.jpg",
                "name": "ext-https",
                "ext": "jpg",
            },
            {
                "type": "background",
                "uri": "file:///etc/passwd",
                "name": "ext-file",
                "ext": "txt",
            },
        ],
    },
}


def test_script_bearing_card_imports_as_inert_data_and_round_trips() -> None:
    card = import_card(json.dumps(INERT_CARD).encode(), "card.json")
    assert card.extensions == INERT_CARD["data"]["extensions"]
    assert card.description == INERT_CARD["data"]["description"]
    assert card.asset_refs == INERT_CARD["data"]["assets"]
    # Nothing was fetched or embedded for the external URIs.
    assert card.assets == {}
    assert card.resolve_asset("https://example.invalid/stairs.jpg") is None
    assert card.resolve_asset("file:///etc/passwd") is None

    again = import_card(export_json(card, "3"), "card.json")
    assert again.extensions == card.extensions
    assert again.asset_refs == card.asset_refs
    assert again.description == card.description


def test_external_asset_uris_are_marked_external_unfetched() -> None:
    card = import_card(json.dumps(INERT_CARD).encode(), "card.json")
    plan = build_asset_plan(card, has_container_art=False, source_bytes=None)
    assert [(p.name, p.status) for p in plan] == [
        ("ext-https", "external_unfetched"),
        ("ext-file", "external_unfetched"),
    ]
    assert all(p.detail == "external_uri_not_fetched" for p in plan)
    assert all(p.data is None for p in plan)


def test_unknown_macros_survive_literal() -> None:
    resolution = resolve_variables(
        "Keep {{setvar::mood::calm}} and {{setvar}} but hi {{char}}",
        char_name="Inert",
    )
    assert "{{setvar::mood::calm}}" in resolution.text
    assert "{{setvar}}" in resolution.text
    assert "setvar" in resolution.unknown
    assert "hi Inert" in resolution.text


def test_lore_key_with_regex_metachars_matches_literally() -> None:
    entry = ScanEntry(id="1", keys=("(a+)+$",), whole_word=False)
    hits = scan_entries([entry], ["the literal (a+)+$ key"], 1)
    assert [h.entry_id for h in hits] == ["1"]
    # As a regex this pattern would match a run of a's; literally it must not.
    assert scan_entries([entry], ["aaaaaaaaaaaaaaaaaaaa"], 1) == []


# --- 6. no leakage in refusal messages --------------------------------------


def test_refusal_messages_do_not_contain_payload_marker() -> None:
    messages: list[str] = []

    with pytest.raises(SafetyError) as deep:
        safe_json_loads('{"k": "' + MARKER + '", "x": ' + "[" * 200 + "]" * 200 + "}")
    messages.append(str(deep.value))

    with pytest.raises(SafetyError) as dup:
        safe_json_loads('{"k": "' + MARKER + '", "k": "' + MARKER + '"}')
    messages.append(str(dup.value))

    with pytest.raises(SafetyError) as big:
        check_bytes((MARKER * 100).encode(), 8)
    messages.append(str(big.value))

    with pytest.raises(CardParseError) as card_exc:
        import_card(
            ('{"name": "' + MARKER + '", "name": "' + MARKER + '"}').encode(),
            "card.json",
        )
    messages.append(str(card_exc.value))

    with pytest.raises(LorebookParseError) as lore_exc:
        parse_lorebook_file(
            ('{"name": "' + MARKER + '", "name": "x", "entries": {}}').encode()
        )
    messages.append(str(lore_exc.value))

    assert messages and all(MARKER not in message for message in messages)


def test_archive_refusal_message_does_not_contain_member_body_marker(tmp_path) -> None:
    path = write_zip(
        tmp_path / "dup.runmal",
        [("manifest.json", MARKER.encode()), ("manifest.json", MARKER.encode())],
    )
    with pytest.raises(ArchiveError) as exc_info:
        validate_archive(path)
    assert MARKER not in str(exc_info.value)


# --- 7. HTTP surface ----------------------------------------------------------


def test_http_deeply_nested_lorebook_import_is_client_error_never_500(
    tmp_path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    nested = "1"
    for _ in range(200):
        nested = '{"x": ' + nested + "}"
    body_text = '{"name": "Deep", "entries": {}, "wrap": ' + nested + "}"
    response = client.post(
        "/api/v1/lorebooks/import",
        content=body_text.encode(),
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code in (400, 413, 422)
    assert response.status_code != 500


# --- 8. corpus regression -----------------------------------------------------


def test_p005_corpus_still_imports() -> None:
    for name in (
        "card_v1_minimal.json",
        "card_v2_rich.json",
        "card_v2_edge.json",
        "card_v3_rich.json",
        "card_dual_ccv3.png",
    ):
        assert import_card((CORPUS / name).read_bytes(), name).name
    assert parse_lorebook_file((CORPUS / "lorebook_worldinfo_full.json").read_bytes()).name
    assert parse_persona((CORPUS / "persona_st.json").read_bytes()).name
    assert parse_preset((CORPUS / "preset_st_textcompletion.json").read_bytes()).name
    assert parse_preset((CORPUS / "preset_st_chatcompletion.json").read_bytes()).name
    result = parse_chat_jsonl((CORPUS / "chat_st.jsonl").read_bytes())
    assert result.report.header_present and result.report.imported_messages >= 1
