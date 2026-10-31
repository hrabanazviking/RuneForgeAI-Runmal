"""Character Card export (S105): deliberate supported JSON/PNG versions.

Supported exports: JSON v2 (`chara_card_v2`), JSON v3 (`chara_card_v3`),
PNG with a `chara` tEXt chunk (v2 JSON payload) — plus a `ccv3`
chunk (v3 payload) when the card is v3, the dual-published shape
the importer already prefers (P-017). CHARX export lives in
archive.py (`export_charx`) — the v3 container format needs the archive
writer, not just the JSON serializer.

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
    "character_version",
    "character_book",
    "extensions",
)


# P-016: the v3 additions, model attribute → spec key. `assets` is
# the spec key for the model's `asset_refs` descriptors.
_V3_FIELD_KEYS = (
    ("nickname", "nickname"),
    ("group_only_greetings", "group_only_greetings"),
    ("creator_notes_multilingual", "creator_notes_multilingual"),
    ("source", "source"),
    ("asset_refs", "assets"),
)
_V3_SPEC_KEYS = frozenset(
    [key for _, key in _V3_FIELD_KEYS] + ["creation_date", "modification_date"]
)


def _known_field_map(card: CharacterCard) -> dict:
    return {field: getattr(card, field) for field in _KNOWN_FIELDS}


def _v3_field_map(card: CharacterCard, *, only_set: bool = False) -> dict:
    """The normalized v3 additions under their spec keys.

    Full form (v3 export) always writes the five structural fields;
    timestamps are written only when the card carries them — an
    absent timestamp is omitted, never fabricated as 0/null.
    `only_set` (v2 export) writes just the additions that differ
    from their defaults, as flat data-level fields, so a v3 card
    stored through the v2-shaped storage path keeps them.
    """
    out: dict = {}
    for attr, key in _V3_FIELD_KEYS:
        value = copy.deepcopy(getattr(card, attr))
        if only_set and not value:
            continue
        out[key] = value
    for attr in ("creation_date", "modification_date"):
        value = getattr(card, attr)
        if value is not None:
            out[attr] = value
    return out


def _unknown_top_level(card: CharacterCard) -> dict:
    return {
        key: copy.deepcopy(value)
        for key, value in card.raw.items()
        if key not in _KNOWN_FIELDS
        and key not in _V3_SPEC_KEYS
        and key not in ("spec", "spec_version", "data")
    }


def export_json(card: CharacterCard, spec_version: str = "2") -> bytes:
    """Export the card as JSON for a deliberate supported spec version."""
    if spec_version not in SUPPORTED_JSON_VERSIONS:
        raise CardParseError(
            CardErrorKind.UNSUPPORTED_VERSION,
            f"supported export versions are {SUPPORTED_JSON_VERSIONS}; got {spec_version!r}",
        )
    known = _known_field_map(card)
    raw_data = card.raw.get("data")
    wrapped = isinstance(raw_data, dict)
    if spec_version == "3":
        if card.spec_version in ("2", "3") and wrapped:
            # P-015: a wrapped v2 card converts up the same way a
            # native v3 card round-trips — its data-level unknowns
            # stay at the data level and its top-level unknowns
            # stay at the top level; neither level is dropped.
            data_unknowns = {
                k: copy.deepcopy(v)
                for k, v in raw_data.items()
                if k not in _KNOWN_FIELDS and k not in _V3_SPEC_KEYS
            }
            obj: dict = _unknown_top_level(card)
        else:
            # converting up from v1/flat v2: unknowns become data-level fields
            data_unknowns = {
                k: copy.deepcopy(v)
                for k, v in card.raw.items()
                if k not in _KNOWN_FIELDS
                and k not in _V3_SPEC_KEYS
                and k not in ("spec", "spec_version", "data")
            }
            obj = {}
        obj["spec"] = "chara_card_v3"
        obj["spec_version"] = "3.0"
        obj["data"] = {**data_unknowns, **known, **_v3_field_map(card)}
    elif wrapped:
        # P-015: a wrapped card exports in the envelope it arrived
        # in — data-level unknowns verbatim inside `data`,
        # top-level unknowns verbatim outside it, known fields
        # overlaid from the normalized card at the data level.
        # P-017: this holds for a v3 card exported as v2 too —
        # gating the branch on spec_version "2" sent v3 cards down
        # the flat path below, which dropped their data-level
        # unknowns (the P-005 corpus v3 card lost two).
        obj = _unknown_top_level(card)
        obj["spec"] = "chara_card_v2"
        obj["spec_version"] = "2.0"
        data_unknowns = {
            k: copy.deepcopy(v)
            for k, v in raw_data.items()
            if k not in _KNOWN_FIELDS and k not in _V3_SPEC_KEYS
        }
        obj["data"] = {
            **data_unknowns,
            **known,
            **_v3_field_map(card, only_set=True),
        }
    else:
        obj = _unknown_top_level(card)
        if "data" in card.raw and not wrapped:
            # A non-dict top-level `data` on a flat card is an
            # unknown field, not an envelope — preserve it verbatim
            # instead of letting the envelope key swallow it.
            obj["data"] = copy.deepcopy(card.raw["data"])
        obj["spec"] = "chara_card_v2"
        obj["spec_version"] = "2.0"
        obj.update(known)
        obj.update(_v3_field_map(card, only_set=True))
    return json.dumps(obj, ensure_ascii=False, indent=2).encode("utf-8")


def _png_chunk(ctype: bytes, data: bytes) -> bytes:
    chunk = struct.pack(">I", len(data)) + ctype + data
    return chunk + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF)


def export_png(card: CharacterCard) -> bytes:
    """Export the card as a PNG carrying card JSON in tEXt chunks.

    Every card gets a `chara` chunk (the v2 payload, readable by
    the widest set of tools). A v3 card additionally gets a `ccv3`
    chunk (the v3 payload) — the dual-published shape real cards
    circulate in (P-005's corpus fixture), which Rúnmál's importer
    already prefers, so a v3 card's PNG round trip stays v3
    (P-017). Before P-017 the PNG export carried v2 only and a v3
    card came back as v2.
    """
    text_chunks = [
        _png_chunk(b"tEXt", b"chara\x00" + base64.b64encode(export_json(card, "2")))
    ]
    if card.spec_version == "3":
        text_chunks.append(
            _png_chunk(
                b"tEXt", b"ccv3\x00" + base64.b64encode(export_json(card, "3"))
            )
        )
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
    idat = _png_chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00"))
    iend = _png_chunk(b"IEND", b"")
    return signature + ihdr + b"".join(text_chunks) + idat + iend
