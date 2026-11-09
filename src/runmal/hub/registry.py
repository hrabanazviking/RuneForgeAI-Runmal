"""Hub registry (P-187, Part XII opener - DERIVED).

The roadmap gives Part XII one line only ("The Hub,
Sovereign Shape", P-187..P-202); this slice's scope is
derived from Runmal's own in-tree record - see
docs/HUB_REGISTRY_2026-11-09.md and
hidden_files/P187_SCOUT.md / P187_DESIGN.md.

What the derivation found: the sharing roads already
land, one sealed pack at a time - P-045 lorebook packs
(format runmal-lorebook-pack), P-063 prompt packs
(runmal-prompt-pack), P-054 preset bundle shares
(runmal-preset-bundle) and P-141 scenario packs
(runmal-scenario-pack) - and each doc names Part XII's
hub as their carrier. The delta table's VX-59 row rules
the shape: DELIBERATELY-DIFFERENT, no central store -
signed local packs and friend-instance exchange instead.
What no banked slice kept was any record of the packs
themselves: which packs an owner holds, of which kind,
and where each one lives. This module is that record:

- ONE owner-scoped index entry per registered pack
  artefact: its kind under the closed HUB_KINDS law
  (each kind mapped to the sealed format it indexes),
  a title, the operator's locator stored verbatim as
  data, an optional caller-claimed content checksum,
  and an optional note. Re-registering the same
  (owner, kind, locator) is refused - remove-then-
  register, never a silent overwrite (the P-169 law).
- The locator LAW is P-121/P-169's: the locator is the
  operator's own locator, stored as data; registering
  never claims the file exists - existence is a
  READ-TIME fact, judged live from the filesystem on
  every document this module builds, under the closed
  LOCATOR_STATES law, and a missing / not-a-file /
  unreadable locator is a named state, never an error
  and never dressed as ready.
- The checksum is caller-CLAIMED data: registering
  validates only its shape (64 hex digits when one is
  supplied). This module never opens the pack, so it
  never presents a checksum as verified - verification
  is each pack layer's own inspect road, and signing
  is a later Part XII slice, named open.
- Persistence rides the P-117 house pattern, as reused
  by P-169: a versioned JSON index (hub.json) in the
  data dir, tolerant load - a corrupt store reads as
  empty and never bricks the surface. NO migration:
  head stays 0041.

Honest boundaries: an entry is DATA ONLY. This slice
opens no pack, parses nothing, copies nothing, imports
nothing, installs nothing, fetches nothing, reaches no
network, runs nothing and grants nothing - the pack
layers own inspect/import, and signing, exchange and
browse are later Part XII slices, named open in the
slice doc. There is no central store, no catalogue and
no creator profile here, by VX-59's ruling, not by
omission. Content stays data, never code (P-027).
"""

from __future__ import annotations

import json
import os
import re
import stat as stat_module
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

REGISTRY_VERSION = 1
REGISTRY_FILENAME = "hub.json"

ENTRY_SCHEMA = "runmal-p187-hub-entry-v1"
LIST_SCHEMA = "runmal-p187-hub-list-v1"

KIND_LOREBOOK_PACK = "lorebook_pack"
KIND_PROMPT_PACK = "prompt_pack"
KIND_PRESET_BUNDLE = "preset_bundle"
KIND_SCENARIO_PACK = "scenario_pack"

KIND_FORMATS = {
    KIND_LOREBOOK_PACK: "runmal-lorebook-pack",
    KIND_PROMPT_PACK: "runmal-prompt-pack",
    KIND_PRESET_BUNDLE: "runmal-preset-bundle",
    KIND_SCENARIO_PACK: "runmal-scenario-pack",
}
HUB_KINDS = frozenset(KIND_FORMATS)

LOCATOR_READY = "ready"
LOCATOR_MISSING = "missing"
LOCATOR_NOT_A_FILE = "not_a_file"
LOCATOR_UNREADABLE = "unreadable"
LOCATOR_STATES = frozenset({
    LOCATOR_READY, LOCATOR_MISSING,
    LOCATOR_NOT_A_FILE, LOCATOR_UNREADABLE,
})

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")

NOTES = (
    "An entry is data only: this surface opens no pack, "
    "parses nothing, copies nothing, imports nothing, "
    "installs nothing, fetches nothing and grants "
    "nothing - inspect and import stay with each pack "
    "layer's own roads, and signing, exchange and "
    "browse are later Part XII work, named open.",
    "The locator is the operator's own locator, stored "
    "as data and never claimed to exist; the locator "
    "state in this document was judged live from the "
    "filesystem at read time, and a missing, not-a-file "
    "or unreadable locator is a named state, never an "
    "error dressed as success.",
    "A content checksum here is the caller's claim, "
    "shape-checked at register time and stored verbatim; "
    "this surface has not read the pack and never "
    "presents the checksum as verified.",
    "One entry per (owner, kind, locator): registering "
    "the same pack locator again under the same kind is "
    "refused - remove the entry, then register; the same "
    "locator under a different kind or owner is a "
    "different entry.",
    "Owner scoped throughout: an entry is visible only "
    "to its owner, and a foreign entry is answered "
    "exactly like an unknown one.",
    "There is no central store, no catalogue and no "
    "creator profile on this road: the hub is the "
    "owner's own index of their own local packs (the "
    "VX-59 sovereign shape).",
)


class HubError(ValueError):
    """A hub operation the state of the world forbids."""


def registry_path(data_dir: Path | None = None) -> Path:
    base = data_dir or Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return base / REGISTRY_FILENAME


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass(frozen=True)
class HubEntry:
    """One indexed pack artefact, as registered."""

    id: str
    owner_id: str
    kind: str
    title: str
    locator: str
    content_sha256: str
    note: str
    created_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "kind": self.kind,
            "format": KIND_FORMATS.get(self.kind, ""),
            "title": self.title,
            "locator": self.locator,
            "content_sha256": self.content_sha256,
            "note": self.note,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> HubEntry:
        return cls(
            id=str(data.get("id", "")),
            owner_id=str(data.get("owner_id", "")),
            kind=str(data.get("kind", "")),
            title=str(data.get("title", "")),
            locator=str(data.get("locator", "")),
            content_sha256=str(data.get("content_sha256", "")),
            note=str(data.get("note", "")),
            created_at=str(data.get("created_at", "")),
        )


class HubStore:
    """Durable hub index: one JSON file in the data dir.

    A corrupt index reads as empty and never bricks the
    surface (the P-117 tolerant-load stance, as in P-169).
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.index_path = self.data_dir / REGISTRY_FILENAME

    def _load(self) -> list[HubEntry]:
        try:
            doc = json.loads(self.index_path.read_text())
        except (OSError, ValueError):
            return []
        if not isinstance(doc, dict):
            return []
        rows: list[HubEntry] = []
        raw = doc.get("entries")
        if isinstance(raw, list):
            for row in raw:
                if isinstance(row, dict):
                    rows.append(HubEntry.from_dict(row))
        return rows

    def _save(self, entries: list[HubEntry]) -> None:
        doc = {
            "version": REGISTRY_VERSION,
            "entries": [row.to_dict() for row in entries],
        }
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(doc, indent=2, sort_keys=True))

    def add_entry(self, entry: HubEntry) -> HubEntry:
        rows = self._load()
        self._save(rows + [entry])
        return entry

    def get_entry(self, entry_id: str) -> HubEntry | None:
        for row in self._load():
            if row.id == entry_id:
                return row
        return None

    def find_entry(self, owner_id: str, kind: str,
                   locator: str) -> HubEntry | None:
        for row in self._load():
            if (row.owner_id == owner_id and row.kind == kind
                    and row.locator == locator):
                return row
        return None

    def list_for_owner(self, owner_id: str) -> list[HubEntry]:
        return [row for row in self._load() if row.owner_id == owner_id]

    def remove_entry(self, entry_id: str) -> HubEntry | None:
        """Remove exactly one entry; a miss writes nothing."""
        rows = self._load()
        removed = [row for row in rows if row.id == entry_id]
        if not removed:
            return None
        self._save([row for row in rows if row.id != entry_id])
        return removed[0]


def register_entry(
    store: HubStore,
    *,
    owner_id: str,
    kind: str,
    title: str,
    locator: str,
    content_sha256: str = "",
    note: str = "",
    now: str | None = None,
) -> HubEntry:
    """Index one pack artefact (the locator stored as data).

    Refusals are plain and total - nothing is stored: an
    empty title, an empty locator, a kind outside the
    closed HUB_KINDS law, a supplied checksum that is not
    64 hex digits, and an already-indexed (owner, kind,
    locator) triple each raise HubError. The locator is
    NOT required to name an existing file and is never
    inspected here: existence is a read-time fact, never
    faked at register time (the P-121/P-169 law).
    """
    cleaned_title = (title or "").strip()
    if not cleaned_title:
        raise HubError("a hub entry title is required")
    cleaned_locator = (locator or "").strip()
    if not cleaned_locator:
        raise HubError("a hub entry locator is required")
    cleaned_kind = (kind or "").strip()
    if cleaned_kind not in HUB_KINDS:
        raise HubError(
            "unknown hub kind: " + (cleaned_kind or "(empty)")
            + " (kinds: " + ", ".join(sorted(HUB_KINDS)) + ")")
    cleaned_sha = (content_sha256 or "").strip()
    if cleaned_sha and not _SHA256_RE.match(cleaned_sha):
        raise HubError(
            "content_sha256 must be 64 hex digits when supplied")
    if store.find_entry(owner_id, cleaned_kind, cleaned_locator) is not None:
        raise HubError(
            "this locator is already indexed under this kind; "
            "remove the entry first")
    entry = HubEntry(
        id=str(uuid.uuid4()),
        owner_id=owner_id,
        kind=cleaned_kind,
        title=cleaned_title,
        locator=cleaned_locator,
        content_sha256=cleaned_sha.lower(),
        note=(note or "").strip(),
        created_at=now or _now_iso(),
    )
    return store.add_entry(entry)


def locator_state(locator: str) -> str:
    """Judge one locator LIVE, under LOCATOR_STATES.

    Follows symlinks as the filesystem does; never raises
    for a bad locator. A path that cannot be stat'ed
    because it does not exist is missing; a stat failure
    for any other reason is unreadable - the file may well
    exist, and this judgement does not claim otherwise.
    An existing path that is not a regular file is
    not_a_file; a regular file the process cannot read
    is unreadable.
    """
    try:
        info = os.stat(locator)
    except FileNotFoundError:
        return LOCATOR_MISSING
    except OSError:
        return LOCATOR_UNREADABLE
    if not stat_module.S_ISREG(info.st_mode):
        return LOCATOR_NOT_A_FILE
    if not os.access(locator, os.R_OK):
        return LOCATOR_UNREADABLE
    return LOCATOR_READY


def entry_document(entry: HubEntry) -> dict:
    """The single-entry document: the entry verbatim plus
    its locator state judged live at this call."""
    return {
        "schema": ENTRY_SCHEMA,
        "entry": entry.to_dict(),
        "locator_state": locator_state(entry.locator),
        "notes": list(NOTES),
    }


def list_document(entries: list[HubEntry]) -> dict:
    """The owner list document: entries in store order,
    each with its live locator state, and counts computed
    from the entries themselves - by kind (every kind in
    the law, zero-filled) and by locator state (every
    state in the law, zero-filled)."""
    rows = []
    by_kind = {kind: 0 for kind in sorted(HUB_KINDS)}
    by_state = {state: 0 for state in sorted(LOCATOR_STATES)}
    for entry in entries:
        state = locator_state(entry.locator)
        row = entry.to_dict()
        row["locator_state"] = state
        rows.append(row)
        if entry.kind in by_kind:
            by_kind[entry.kind] += 1
        by_state[state] += 1
    return {
        "schema": LIST_SCHEMA,
        "entries": rows,
        "count": len(rows),
        "by_kind": by_kind,
        "by_locator_state": by_state,
        "kind_formats": dict(KIND_FORMATS),
        "notes": list(NOTES),
    }
