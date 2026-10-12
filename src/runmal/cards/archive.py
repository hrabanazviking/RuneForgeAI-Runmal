"""CHARX archive writing + safe asset extraction/storage (S113).

Import lives in parser.py; this module owns everything that *writes*
archives or materializes their contents:

- `validate_archive_name`: traversal-proof archive member names, shared by
  the importer (parser.py), the exporter, and the extractor.
- `export_charx`: CharacterCard -> deterministic v3 CHARX bytes
  (`card.json` + assets). CHARX is the v3 container format, so the embedded
  card.json is always v3; v1/v2 cards convert up per the S105 semantics
  (unknowns move to the data level).
- `extract_assets`: safely write a card's assets into a directory
  (the "storage" half of the slice).

All names are untrusted: validated before any zip entry is written and
containment-checked before any file touches the filesystem.
"""

from __future__ import annotations

import io
import posixpath
import zipfile
from pathlib import Path

from runmal.cards.errors import CardErrorKind, CardParseError
from runmal.cards.exporter import export_json
from runmal.cards.models import CharacterCard

# Fixed timestamp so exports are byte-deterministic: same card in ->
# same zip out (within a Python version).
_DETERMINISTIC_DATE = (2020, 1, 1, 0, 0, 0)

CARD_JSON_NAME = "card.json"


def validate_archive_name(name: str) -> None:
    """Reject archive member names that could escape the destination."""
    if not name or name.startswith(("/", "\\")):
        raise CardParseError(CardErrorKind.PATH_TRAVERSAL, f"unsafe archive name: {name!r}")
    normalized = posixpath.normpath(name)
    if normalized != name or normalized.startswith("..") or "\\" in name:
        raise CardParseError(CardErrorKind.PATH_TRAVERSAL, f"unsafe archive name: {name!r}")


def _zip_entry(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=_DETERMINISTIC_DATE)
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, data)


def export_charx(card: CharacterCard) -> bytes:
    """Export the card as a CHARX archive (v3 `card.json` + assets)."""
    for name in card.assets:
        validate_archive_name(name)
        if name == CARD_JSON_NAME:
            raise CardParseError(
                CardErrorKind.BAD_ARCHIVE,
                f"asset name collides with {CARD_JSON_NAME!r}",
            )
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as archive:
        _zip_entry(archive, CARD_JSON_NAME, export_json(card, "3"))
        for name in sorted(card.assets):
            _zip_entry(archive, name, card.assets[name])
    return buf.getvalue()


def extract_assets(card: CharacterCard, dest_dir: str | Path) -> list[str]:
    """Safely extract a card's assets into `dest_dir`; return written names.

    Every name is traversal-validated and containment-checked against the
    resolved destination directory. Nothing is written outside it.
    """
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    resolved_dest = dest.resolve()
    written: list[str] = []
    for name in sorted(card.assets):
        validate_archive_name(name)
        target = dest / name
        # Defense in depth: the validator already rejects escapes, but never
        # trust a name check alone before touching the filesystem.
        if not target.resolve().is_relative_to(resolved_dest):
            raise CardParseError(CardErrorKind.PATH_TRAVERSAL, f"unsafe archive name: {name!r}")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(card.assets[name])
        written.append(name)
    return written
