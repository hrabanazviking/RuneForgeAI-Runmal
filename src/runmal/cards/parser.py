"""Character Card importers (S104).

Supported inputs:
- JSON: v1 (bare fields), v2 (`chara_card_v2`), v3 (`chara_card_v3`,
  fields under `data`)
- PNG: `chara` / `ccv3` textual chunks (tEXt, zTXt), base64 JSON
- CHARX: zip archive with `card.json` at root plus assets

All inputs are untrusted: size caps, traversal checks, typed errors.
"""

from __future__ import annotations

import base64
import binascii
import io
import json
import struct
import zipfile
import zlib

from runmal.cards.archive import validate_archive_name
from runmal.cards.errors import CardErrorKind, CardParseError
from runmal.cards.models import CharacterCard

MAX_INPUT_BYTES = 32 * 1024 * 1024
MAX_ASSET_BYTES = 16 * 1024 * 1024
MAX_TOTAL_ASSET_BYTES = 64 * 1024 * 1024
MAX_ARCHIVE_FILES = 256

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
ZIP_SIGNATURE = b"PK\x03\x04"


def _check_size(data: bytes) -> None:
    if len(data) > MAX_INPUT_BYTES:
        raise CardParseError(
            CardErrorKind.INPUT_TOO_LARGE,
            f"card input is {len(data)} bytes; limit is {MAX_INPUT_BYTES}",
        )


def _detect_spec_version(obj: dict) -> str:
    spec = str(obj.get("spec", ""))
    ver = str(obj.get("spec_version", ""))
    if spec == "chara_card_v3" or ver.startswith("3"):
        return "3"
    if spec == "chara_card_v2" or ver.startswith("2"):
        return "2"
    if not spec and not ver:
        return "1"
    major = ver.split(".")[0] if ver else ""
    if major not in ("1", "2", "3"):
        raise CardParseError(
            CardErrorKind.UNSUPPORTED_VERSION,
            f"unsupported character card spec: spec={spec!r} spec_version={ver!r}",
        )
    return major or "1"


def _as_str(value: object) -> str:
    return value if isinstance(value, str) else ""


def _as_str_list(value: object) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    return []


def _as_dict(value: object) -> dict:
    return dict(value) if isinstance(value, dict) else {}


def _normalize_card(
    obj: dict, source_format: str, assets: dict[str, bytes] | None = None
) -> CharacterCard:
    if not isinstance(obj, dict):
        raise CardParseError(CardErrorKind.NOT_A_CARD, "card JSON is not an object")
    spec_version = _detect_spec_version(obj)
    data = obj.get("data") if spec_version == "3" else obj
    if not isinstance(data, dict):
        raise CardParseError(CardErrorKind.NOT_A_CARD, "v3 card is missing its data object")
    name = _as_str(data.get("name"))
    if not name:
        raise CardParseError(CardErrorKind.NOT_A_CARD, "card has no name")
    return CharacterCard(
        name=name,
        description=_as_str(data.get("description")),
        personality=_as_str(data.get("personality")),
        scenario=_as_str(data.get("scenario")),
        first_mes=_as_str(data.get("first_mes")),
        mes_example=_as_str(data.get("mes_example")),
        creator_notes=_as_str(data.get("creator_notes")),
        system_prompt=_as_str(data.get("system_prompt")),
        post_history_instructions=_as_str(data.get("post_history_instructions")),
        alternate_greetings=_as_str_list(data.get("alternate_greetings")),
        tags=_as_str_list(data.get("tags")),
        creator=_as_str(data.get("creator")),
        character_book=_as_dict(data.get("character_book")),
        extensions=_as_dict(data.get("extensions")),
        assets=dict(assets) if assets else {},
        raw=dict(obj),
        spec_version=spec_version,
        source_format=source_format,
    )


def parse_json_card(data: bytes, source_format: str = "json") -> CharacterCard:
    _check_size(data)
    stripped = data.strip()
    if not stripped:
        raise CardParseError(CardErrorKind.INVALID_JSON, "empty card input")
    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError as exc:
        if exc.pos >= len(stripped) - 1 or "unterminated" in exc.msg.lower():
            raise CardParseError(
                CardErrorKind.TRUNCATED, f"card JSON is truncated: {exc.msg}"
            ) from exc
        raise CardParseError(
            CardErrorKind.INVALID_JSON, f"card JSON is invalid: {exc.msg}"
        ) from exc
    return _normalize_card(obj, source_format)


def _iter_png_chunks(data: bytes):
    if data[:8] != PNG_SIGNATURE:
        raise CardParseError(CardErrorKind.INVALID_PNG, "not a PNG file")
    pos = 8
    while pos + 8 <= len(data):
        length = struct.unpack(">I", data[pos : pos + 4])[0]
        ctype = data[pos + 4 : pos + 8]
        start = pos + 8
        end = start + length
        if end + 4 > len(data):
            raise CardParseError(CardErrorKind.TRUNCATED, "PNG truncated inside a chunk")
        yield ctype, data[start:end]
        pos = end + 4
        if ctype == b"IEND":
            break


def _decode_text_chunk(ctype: bytes, payload: bytes) -> tuple[str, str] | None:
    try:
        if ctype == b"tEXt":
            keyword, _, text = payload.partition(b"\x00")
            return keyword.decode("latin-1"), text.decode("latin-1")
        if ctype == b"zTXt":
            keyword, _, rest = payload.partition(b"\x00")
            if not rest or rest[0] != 0:
                return None
            text = zlib.decompress(rest[1:]).decode("latin-1")
            return keyword.decode("latin-1"), text
    except (UnicodeDecodeError, zlib.error):
        return None
    return None


def parse_png_card(data: bytes) -> CharacterCard:
    _check_size(data)
    found: dict[str, str] = {}
    for ctype, payload in _iter_png_chunks(data):
        if ctype not in (b"tEXt", b"zTXt"):
            continue
        decoded = _decode_text_chunk(ctype, payload)
        if decoded is None:
            continue
        keyword, text = decoded
        if keyword in ("chara", "ccv3"):
            found[keyword] = text
    for keyword in ("ccv3", "chara"):
        if keyword in found:
            try:
                raw = base64.b64decode(found[keyword], validate=True)
            except binascii.Error as exc:
                raise CardParseError(
                    CardErrorKind.INVALID_PNG, f"PNG {keyword} chunk is not valid base64"
                ) from exc
            return parse_json_card(raw, source_format="png")
    raise CardParseError(CardErrorKind.NO_CARD_DATA, "PNG has no chara/ccv3 metadata chunk")


def parse_charx(data: bytes) -> CharacterCard:
    _check_size(data)
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise CardParseError(CardErrorKind.BAD_ARCHIVE, "not a valid zip archive") from exc
    with archive:
        names = archive.namelist()
        if len(names) > MAX_ARCHIVE_FILES:
            raise CardParseError(
                CardErrorKind.BAD_ARCHIVE,
                f"archive has {len(names)} entries (limit {MAX_ARCHIVE_FILES})",
            )
        if "card.json" not in names:
            raise CardParseError(CardErrorKind.BAD_ARCHIVE, "CHARX archive is missing card.json")
        total = 0
        for name in names:
            if name == "card.json":
                continue
            validate_archive_name(name)
            size = archive.getinfo(name).file_size
            if size > MAX_ASSET_BYTES:
                raise CardParseError(
                    CardErrorKind.ASSET_TOO_LARGE, f"asset {name!r} is {size} bytes"
                )
            total += size
            if total > MAX_TOTAL_ASSET_BYTES:
                raise CardParseError(
                    CardErrorKind.ASSET_TOO_LARGE, "CHARX assets exceed total size budget"
                )
        assets = {name: archive.read(name) for name in names if name != "card.json"}
        card_json = archive.read("card.json")
    card = parse_json_card(card_json, source_format="charx")
    card.assets = assets
    return card


def import_card(data: bytes, filename: str = "card.json") -> CharacterCard:
    """Detect the card container and import it."""
    _check_size(data)
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if data[:8] == PNG_SIGNATURE or suffix == "png":
        return parse_png_card(data)
    if data[:4] == ZIP_SIGNATURE or suffix in ("charx", "zip"):
        return parse_charx(data)
    return parse_json_card(data)
