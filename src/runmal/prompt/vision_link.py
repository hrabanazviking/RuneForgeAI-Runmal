"""Vision description store link (P-118, Part VIII — DERIVED).

P-117 laid the vision foundation: descriptions bound to a chat,
persisted in ``vision_descriptions.json`` (version 1) in the data
dir by ``runmal.vision.service.VisionStore``. P-117 named two
things open, and this module is their read/custody side:

- the prompt composer consuming the last description as the
  VX-43/VX-50 template variable — :func:`last_for_chat` /
  :func:`last_description_text` are the lookup the S307 variable
  model resolves ``{{last_vision_description}}`` from;
- custody on chat deletion — :func:`purge_chat` removes a chat's
  rows when the chat dies, mirroring the voice custody precedent
  (``VoiceSessionStore.drop_chat``).

Why not import ``runmal.vision``? This slice was built from the
P-116 base, where P-117 (banked concurrently) is not yet merged;
the keeper merges P-117 first at banking. The store FORMAT is
therefore pinned here as data — version 1, the exact document
P-117's store writes — and this module is the one place to
re-pin if that format ever moves. The writer stays P-117's
``VisionStore``; this module never appends descriptions.

Honesty laws:
- Tolerant load, exactly like the store itself: a missing,
  corrupt, or wrong-shaped file reads as NO descriptions —
  never an exception, never an invented row.
- P-075 no-content law: no description is ever fabricated.
  A chat with no description yields ``None`` / ``""`` — an
  honest empty that the variable resolver substitutes as-is.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

DESCRIPTIONS_FILENAME = "vision_descriptions.json"
DESCRIPTIONS_VERSION = 1


def descriptions_path(data_dir: Path | None = None) -> Path:
    """The store path, resolved exactly as P-117's router does."""
    base = data_dir or Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return Path(base) / DESCRIPTIONS_FILENAME


def _load_doc(data_dir: Path | None = None) -> dict:
    try:
        doc = json.loads(descriptions_path(data_dir).read_text())
    except (OSError, ValueError):
        return {"version": DESCRIPTIONS_VERSION, "descriptions": []}
    if not isinstance(doc, dict):
        return {"version": DESCRIPTIONS_VERSION, "descriptions": []}
    rows = doc.get("descriptions")
    if not isinstance(rows, list):
        return {"version": DESCRIPTIONS_VERSION, "descriptions": []}
    return doc


def load_descriptions(data_dir: Path | None = None) -> list[dict]:
    """All stored description rows (dicts, store append order)."""
    rows = _load_doc(data_dir).get("descriptions") or []
    return [row for row in rows if isinstance(row, dict)]


def list_for_chat(chat_id: str, data_dir: Path | None = None) -> list[dict]:
    return [row for row in load_descriptions(data_dir)
            if row.get("chat_id") == chat_id]


def last_for_chat(chat_id: str, data_dir: Path | None = None) -> dict | None:
    """The chat's last description row, or None when it has none."""
    rows = list_for_chat(chat_id, data_dir)
    return rows[-1] if rows else None


def last_description_text(chat_id: str, data_dir: Path | None = None) -> str:
    """The chat's last description text, or "" — never invented."""
    row = last_for_chat(chat_id, data_dir)
    if row is None:
        return ""
    return str(row.get("description") or "")


def purge_chat(chat_id: str, data_dir: Path | None = None) -> int:
    """Custody: remove a chat's description rows; return the count.

    Other chats' rows and the document version are preserved.
    A missing/corrupt store purges nothing and creates no file;
    a store with nothing to purge is left byte-untouched.
    """
    path = descriptions_path(data_dir)
    if not path.exists():
        return 0
    doc = _load_doc(data_dir)
    rows = [row for row in (doc.get("descriptions") or [])
            if isinstance(row, dict)]
    kept = [row for row in rows if row.get("chat_id") != chat_id]
    removed = len(rows) - len(kept)
    if removed == 0:
        return 0
    out = {
        "version": doc.get("version", DESCRIPTIONS_VERSION),
        "descriptions": kept,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, indent=2, sort_keys=True))
    return removed
