"""Character Card export (S105): deliberate supported JSON/PNG versions.

Supported exports: JSON v2 (`chara_card_v2`), JSON v3 (`chara_card_v3`),
PNG with a `chara` tEXt chunk (v2 JSON payload). CHARX export is S113.

Unknown-but-valid fields from the imported card are preserved (INV-009):
export starts from the card's raw mapping and overlays the normalized
known fields, so nothing opaque is dropped.
"""

from __future__ import annotations

import base64
import copy
import json
import struct
import zlib

from runmal.cards.errors import CardErrorKind, CardParseError
from runmal.cards.models import CharacterCard

SUPPORTED_JSON_VERSIONS = ("2", "3")

_KNOWN_FIELDS = (
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
)


def _known_field_map(card: CharacterCard) -> dict:
    return {field: getattr(card, field) for field in _KNOWN_FIELDS}


def _unknown_top_level(card: CharacterCard) -> dict:
    return {
        key: copy.deepcopy(value)
        for key, value in card.raw.items()
        if key not in _KNOWN_FIELDS and key not in ("spec", "spec_version", "data")
    }


def export_json(card: CharacterCard, spec_version: str = "2") -> bytes:
    """Export the card as JSON for a deliberate supported spec version."""
    if spec_version not in SUPPORTED_JSON_VERSIONS:
        raise CardParseError(
            CardErrorKind.UNSUPPORTED_VERSION,
            f"supported export versions are {SUPPORTED_JSON_VERSIONS}; got {spec_version!r}",
        )
    known = _known_field_map(card)
    if spec_version == "3":
        raw_data = card.raw.get("data")
        if card.spec_version == "3" and isinstance(raw_data, dict):
            data_unknowns = {
                k: copy.deepcopy(v) for k, v in raw_data.items() if k not in _KNOWN_FIELDS
            }
            obj: dict = _unknown_top_level(card)
        else:
            # converting up from v1/v2: unknowns become data-level fields
            data_unknowns = {
                k: copy.deepcopy(v)
                for k, v in card.raw.items()
                if k not in _KNOWN_FIELDS and k not in ("spec", "spec_version", "data")
            }
            obj = {}
        obj["spec"] = "chara_card_v3"
        obj["spec_version"] = "3.0"
        obj["data"] = {**data_unknowns, **known}
    else:
        obj = _unknown_top_level(card)
        obj["spec"] = "chara_card_v2"
        obj["spec_version"] = "2.0"
        obj.update(known)
    return json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")


def _png_chunk(ctype: bytes, data: bytes) -> bytes:
    chunk = struct.pack(">I", len(data)) + ctype + data
    return chunk + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)


def export_png(card: CharacterCard) -> bytes:
    """Export the card as a PNG carrying the v2 JSON in a `chara` tEXt chunk."""
    payload = b"chara\x00" + base64.b64encode(export_json(card, "2"))
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    text = _png_chunk(b"tEXt", payload)
    idat = _png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
    iend = _png_chunk(b"IEND", b"")
    return signature + ihdr + text + idat + iend
