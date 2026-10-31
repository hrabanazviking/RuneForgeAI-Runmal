"""P-017 acceptance: card export v2 + v3 — round-trip tests against
the P-005 corpus (import → export → field-diff clean).

The field-diff contract (docs/CARD_EXPORT_ROUNDTRIP_2026-10-31.md):
for every corpus card and every export shape (JSON v2, JSON v3,
PNG, CHARX) —

- every normalized field of the imported card is equal after
  export → re-import (the diff is taken on the normalized model,
  so the parser's defensive cleaning, e.g. null members dropped
  from string lists, is judged once at import, not again here);
- every unknown field survives with its exact value — compared
  level-agnostically, because a deliberate version conversion may
  move an unknown between the flat level and the `data` envelope,
  but may never lose, change, or invent one (INV-009);
- the re-imported card's spec version is the version the export
  was asked for (PNG: v3 when the card is v3 — the dual-chunk
  export below — else v2);
- the export is a fixed point: exporting the re-imported card
  reproduces the first export byte for byte.

Two exporter defects this slice found by the corpus probe and
fixed are pinned by name below: a v3 card exported as v2 lost its
data-level unknowns (the wrapped-envelope branch was gated on
spec_version "2"), and the PNG export carried no v3 payload, so
a v3 card's PNG round trip silently downgraded it to v2.
"""

from __future__ import annotations

import json
import struct
import zlib
from pathlib import Path

from runmal.cards import import_card
from runmal.cards.archive import export_charx
from runmal.cards.exporter import export_json, export_png

CORPUS = Path(__file__).parent / "fixtures" / "interop"
CARD_FILES = (
    "card_v1_minimal.json",
    "card_v2_rich.json",
    "card_v2_edge.json",
    "card_v3_rich.json",
    "card_dual_ccv3.png",
)

NORMALIZED_FIELDS = (
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
    "nickname",
    "group_only_greetings",
    "creator_notes_multilingual",
    "source",
    "creation_date",
    "modification_date",
    "asset_refs",
    "character_book",
    "extensions",
)

# Keys the exporter writes from the normalized model (the spec's
# `assets` key carries the model's `asset_refs`); everything else
# in a card file is an unknown for preservation purposes.
DATA_KNOWN = frozenset(NORMALIZED_FIELDS) | {"assets"}


def load(name: str):
    return import_card((CORPUS / name).read_bytes(), name)


def unknown_values(raw: dict) -> dict:
    """Unknown key -> sorted JSON values, ignoring envelope level."""
    values: dict[str, list[str]] = {}

    def collect(mapping: dict) -> None:
        for key, value in mapping.items():
            if key in DATA_KNOWN or key in ("spec", "spec_version"):
                continue
            values.setdefault(key, []).append(
                json.dumps(value, sort_keys=True, ensure_ascii=False)
            )

    data = raw.get("data")
    if isinstance(data, dict):
        collect(data)
        collect({k: v for k, v in raw.items() if k != "data"})
    else:
        collect(raw)
    return {key: sorted(vals) for key, vals in values.items()}


def assert_round_trip_clean(card, blob: bytes, filename: str, expected_spec: str):
    again = import_card(blob, filename)
    assert again.spec_version == expected_spec, filename
    for field in NORMALIZED_FIELDS:
        assert getattr(again, field) == getattr(card, field), (filename, field)
    assert again.assets == card.assets, filename
    assert unknown_values(again.raw) == unknown_values(card.raw), filename
    return again


def export_shape(card, shape: str) -> tuple[bytes, str]:
    if shape == "json2":
        return export_json(card, "2"), "export.json"
    if shape == "json3":
        return export_json(card, "3"), "export.json"
    if shape == "png":
        return export_png(card), "export.png"
    return export_charx(card), "export.charx"


SHAPES = ("json2", "json3", "png", "charx")


def expected_spec(card, shape: str) -> str:
    if shape in ("json3", "charx"):
        return "3"
    if shape == "png" and card.spec_version == "3":
        return "3"  # the ccv3 chunk keeps a v3 card v3 (below)
    return "2"


# --- the corpus matrix ----------------------------------------------------


def test_corpus_json_v2_exports_round_trip_clean() -> None:
    for name in CARD_FILES:
        card = load(name)
        blob, filename = export_shape(card, "json2")
        assert_round_trip_clean(card, blob, filename, "2")


def test_corpus_json_v3_exports_round_trip_clean() -> None:
    for name in CARD_FILES:
        card = load(name)
        blob, filename = export_shape(card, "json3")
        assert_round_trip_clean(card, blob, filename, "3")


def test_corpus_png_exports_round_trip_clean() -> None:
    for name in CARD_FILES:
        card = load(name)
        blob, filename = export_shape(card, "png")
        assert_round_trip_clean(card, blob, filename, expected_spec(card, "png"))


def test_corpus_charx_exports_round_trip_clean() -> None:
    for name in CARD_FILES:
        card = load(name)
        blob, filename = export_shape(card, "charx")
        assert_round_trip_clean(card, blob, filename, "3")


def test_corpus_exports_are_byte_stable_fixed_points() -> None:
    for name in CARD_FILES:
        card = load(name)
        for shape in SHAPES:
            blob, filename = export_shape(card, shape)
            again = import_card(blob, filename)
            reblob, _ = export_shape(again, shape)
            assert reblob == blob, (name, shape)


# --- the two defects, pinned by name ---------------------------------------


def test_v3_card_v2_export_keeps_data_level_unknowns() -> None:
    # Regression: the wrapped-envelope branch was gated on
    # spec_version "2", so a v3 card exported as v2 fell to the
    # flat path and its data-level unknowns were dropped.
    card = load("card_v3_rich.json")
    exported = json.loads(export_json(card, "2"))
    data = exported["data"]
    assert data["creator_character_version"] == "3.0-corpus"
    assert data["x_corpus_v3_unknown"] == {"must": "survive-v3-round-trip"}
    assert exported["x_corpus_top_level_unknown"] == "v3-top-level-must-survive"


def test_v3_card_v2_export_stays_wrapped_not_flattened() -> None:
    card = load("card_v3_rich.json")
    exported = json.loads(export_json(card, "2"))
    assert exported["spec"] == "chara_card_v2"
    assert exported["data"]["name"] == card.name
    assert exported["data"]["nickname"] == "Ninth"
    assert "name" not in exported  # fields live in the envelope


def png_text_keywords(png: bytes) -> list[str]:
    keywords = []
    pos = 8
    while pos + 8 <= len(png):
        length = struct.unpack(">I", png[pos : pos + 4])[0]
        ctype = png[pos + 4 : pos + 8]
        data = png[pos + 8 : pos + 8 + length]
        stored = struct.unpack(">I", png[pos + 8 + length : pos + 12 + length])[0]
        assert zlib.crc32(ctype + data) & 0xFFFFFFFF == stored, ctype
        if ctype == b"tEXt":
            keywords.append(data.partition(b"\x00")[0].decode("latin-1"))
        pos += 12 + length
        if ctype == b"IEND":
            break
    return keywords


def test_v3_card_png_carries_chara_and_ccv3_chunks() -> None:
    # Regression: PNG export carried only the v2 payload, so a v3
    # card came back from its own PNG as v2. The dual-published
    # shape (chara for wide readers, ccv3 preferred by importers
    # that know it) keeps the round trip at v3.
    card = load("card_v3_rich.json")
    png = export_png(card)
    assert png_text_keywords(png) == ["chara", "ccv3"]
    again = import_card(png, "export.png")
    assert again.spec_version == "3"
    assert again.nickname == "Ninth"


def test_v2_card_png_carries_chara_only() -> None:
    card = load("card_v2_rich.json")
    assert png_text_keywords(export_png(card)) == ["chara"]


def test_dual_chunk_corpus_card_png_round_trip_stays_v3() -> None:
    card = load("card_dual_ccv3.png")
    assert card.spec_version == "3"
    again = import_card(export_png(card), "export.png")
    assert again.spec_version == "3"
    assert again.name == card.name
    assert again.first_mes == card.first_mes
