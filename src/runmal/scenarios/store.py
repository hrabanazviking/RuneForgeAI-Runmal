"""Scenario definitions (P-131, Part IX opener — DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios — the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree census — see the P-131 slice doc.
What the derivation found missing, and what lands here:

- a scenario definition as a first-class, persistent,
  OWNER-SCOPED citizen: until now the P-026 package could
  parse a scenario file for a moment and hand it back, but
  nothing could be kept — its own router said "scenarios
  are not stored until Part IX". Part IX starts here.
- honest validation at the store door: a definition is
  stored only if P-026's own parser accepts the body.
  The store invents no second validation law, and the
  parser's import report rides with the record AS DATA —
  what was mapped, carried, warned on, and what was
  UNMAPPABLE is recorded on the definition itself.
- truth-as-data throughout (P-075 no-content law, P-027
  data-never-code law): the store keeps the author's own
  definition whole and does nothing else with it. No
  dialogue is fabricated, no scene is played, no carried
  scripting is executed — unmappable machinery stays a
  line in the report, never a running thing.
- persistence in the house JSON-store pattern (P-101 /
  P-117): a versioned document ``scenarios.json`` in the
  data dir, tolerant load — a corrupt store reads as
  empty and never bricks the scenario surface. NO
  migration: the SQL head stays 0041.

The stored shape is the P-026 NATIVE shape (export_native
of the parsed file): typed fields + ``extra``. One honest
consequence rides with it — a Voxta file's unmappable raw
values (carried in ``unmappable_values`` on the parse)
are not part of the native shape, so they do not persist;
the record's report names every one of them, and the
stateless P-026 import/export roads remain the lossless
hand-back road for raw files. Nothing is silently
dropped: the report is the record of it.

P-137 (Part IX, DERIVED scope) adds the store's
duplication verb: a faithful clone of one stored
definition under a fresh id. The definition and its
import report are deep-copied exactly — the report is
the one part of the record the composed export ->
create road provably cannot reproduce (P-133's
one-way naming law) — the source format is preserved,
and the name follows the characters S303 law (the
source's name + " (copy)"). The clone starts at
revision 1 as a new citizen; no organisation row and
no binding is carried to it.
"""

from __future__ import annotations

import copy
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from runmal.scenarios.fileexport import export_native
from runmal.scenarios.fileimport import parse_scenario_file
from runmal.scenarios.filemodels import ScenarioParseError

DEFINITIONS_VERSION = 1
DEFINITIONS_FILENAME = "scenarios.json"


class ScenarioStoreError(ValueError):
    """A scenario-store operation the state of the world forbids."""


def definitions_path(data_dir: Path | None = None) -> Path:
    base = data_dir or Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return base / DEFINITIONS_FILENAME


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ------------------------------------------------------------ record


@dataclass(frozen=True)
class ScenarioDefinition:
    """One persisted scenario definition, owned by one user.

    ``definition`` is the P-026 native shape, kept whole;
    ``report`` is the P-026 import report as plain data —
    the record's own account of what the file carried,
    including every unmappable element (recorded, never
    executed). ``revision`` starts at 1 and grows by one
    on every successful replace; ``created_at`` never
    moves, ``updated_at`` moves with each replace.
    """

    id: str
    owner_id: str
    name: str
    definition: dict
    source_format: str
    report: dict
    revision: int
    created_at: str
    updated_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "name": self.name,
            "definition": copy.deepcopy(self.definition),
            "source_format": self.source_format,
            "report": copy.deepcopy(self.report),
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    def summary(self) -> dict:
        """The list shape: identity + counts read from the
        definition itself, so they can never drift from it."""
        unmappable = []
        if isinstance(self.report, dict):
            unmappable = self.report.get("unmappable") or []
        roles = self.definition.get("roles")
        bootstrap = self.definition.get("bootstrap_messages")
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "name": self.name,
            "source_format": self.source_format,
            "revision": self.revision,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "role_count": len(roles) if isinstance(roles, list) else 0,
            "bootstrap_count": (
                len(bootstrap) if isinstance(bootstrap, list) else 0
            ),
            "has_unmappable": bool(unmappable),
        }

    @classmethod
    def from_dict(cls, data: dict) -> ScenarioDefinition:
        return cls(
            id=str(data.get("id", "")),
            owner_id=str(data.get("owner_id", "")),
            name=str(data.get("name", "")),
            definition=(
                copy.deepcopy(data["definition"])
                if isinstance(data.get("definition"), dict)
                else {}
            ),
            source_format=str(data.get("source_format", "")),
            report=(
                copy.deepcopy(data["report"])
                if isinstance(data.get("report"), dict)
                else {}
            ),
            revision=int(data.get("revision", 1)),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
        )


# ------------------------------------------------------------- store


class ScenarioStore:
    """Durable definition store: scenarios.json (house pattern)."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> list[ScenarioDefinition]:
        try:
            doc = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return []
        if not isinstance(doc, dict):
            return []
        rows = doc.get("definitions")
        if not isinstance(rows, list):
            return []
        out: list[ScenarioDefinition] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                out.append(ScenarioDefinition.from_dict(row))
            except (TypeError, ValueError):
                # Tolerant load (design §3): one malformed row
                # reads as absent; it never bricks the rows
                # beside it or the surface above them.
                continue
        return out

    def _save(self, rows: list[ScenarioDefinition]) -> None:
        doc = {
            "version": DEFINITIONS_VERSION,
            "definitions": [row.to_dict() for row in rows],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc, indent=2, sort_keys=True))

    # ------------------------------------------------------ verbs

    def create(
        self,
        owner_id: str,
        body: dict,
        *,
        now: str | None = None,
    ) -> ScenarioDefinition:
        """Validate *body* through P-026 and persist its native shape.

        A non-object body raises :class:`ScenarioStoreError`;
        a body P-026 refuses raises ``ScenarioParseError``.
        On any refusal nothing is stored.
        """
        parsed = _parse_body(body)
        stamp = now or _now_iso()
        record = ScenarioDefinition(
            id=str(uuid.uuid4()),
            owner_id=owner_id,
            name=parsed.name,
            definition=export_native(parsed),
            source_format=parsed.source_format,
            report=parsed.report.to_dict() if parsed.report else {},
            revision=1,
            created_at=stamp,
            updated_at=stamp,
        )
        rows = self._load()
        rows.append(record)
        self._save(rows)
        return record

    def get(
        self, definition_id: str, owner_id: str
    ) -> ScenarioDefinition | None:
        """One owned definition, or None — a foreign id answers
        exactly like an unknown one; existence never leaks."""
        for row in self._load():
            if row.id == definition_id and row.owner_id == owner_id:
                return row
        return None

    def list_for_owner(self, owner_id: str) -> list[ScenarioDefinition]:
        """The owner's definitions, in creation (store) order."""
        return [row for row in self._load() if row.owner_id == owner_id]

    def replace(
        self,
        definition_id: str,
        owner_id: str,
        body: dict,
        *,
        now: str | None = None,
    ) -> ScenarioDefinition | None:
        """Replace one owned definition's content, revision + 1.

        Unknown or foreign answers None BEFORE the body is
        looked at. The new body is parsed before anything is
        written, so a refused body leaves the stored record
        byte-untouched.
        """
        rows = self._load()
        index = next(
            (
                i
                for i, row in enumerate(rows)
                if row.id == definition_id and row.owner_id == owner_id
            ),
            None,
        )
        if index is None:
            return None
        parsed = _parse_body(body)
        old = rows[index]
        record = ScenarioDefinition(
            id=old.id,
            owner_id=old.owner_id,
            name=parsed.name,
            definition=export_native(parsed),
            source_format=parsed.source_format,
            report=parsed.report.to_dict() if parsed.report else {},
            revision=old.revision + 1,
            created_at=old.created_at,
            updated_at=now or _now_iso(),
        )
        rows[index] = record
        self._save(rows)
        return record

    def remove(
        self, definition_id: str, owner_id: str
    ) -> ScenarioDefinition | None:
        """Delete exactly one owned definition; return it or None."""
        rows = self._load()
        kept = [
            row
            for row in rows
            if not (row.id == definition_id and row.owner_id == owner_id)
        ]
        removed = [
            row
            for row in rows
            if row.id == definition_id and row.owner_id == owner_id
        ]
        if not removed:
            return None
        self._save(kept)
        return removed[0]

    def duplicate(
        self,
        definition_id: str,
        owner_id: str,
        *,
        now: str | None = None,
    ) -> ScenarioDefinition | None:
        """Clone one owned definition faithfully, or None.

        Unknown or foreign answers None BEFORE anything
        is copied or written — existence never leaks.
        The clone is a new citizen: fresh id, revision 1,
        one birth stamp, the source's owner. Its
        definition and its P-131 import report are
        deep-copied exactly (the report holds no name
        value, so the rename falsifies nothing in it),
        its source_format is preserved, and its name —
        on the record and on the definition's own name
        field alike, so the two never disagree — follows
        the characters S303 law: the source's name +
        " (copy)". Only the definitions document gains
        a row: no organisation row and no binding is
        carried to the clone.
        """
        rows = self._load()
        source = next(
            (
                row
                for row in rows
                if row.id == definition_id and row.owner_id == owner_id
            ),
            None,
        )
        if source is None:
            return None
        stamp = now or _now_iso()
        name = f"{source.name} (copy)"
        definition = copy.deepcopy(source.definition)
        if isinstance(definition.get("name"), str):
            definition["name"] = name
        record = ScenarioDefinition(
            id=str(uuid.uuid4()),
            owner_id=source.owner_id,
            name=name,
            definition=definition,
            source_format=source.source_format,
            report=copy.deepcopy(source.report),
            revision=1,
            created_at=stamp,
            updated_at=stamp,
        )
        rows.append(record)
        self._save(rows)
        return record


def _parse_body(body: dict):
    """The store door: P-026's parser is the only validation law."""
    if not isinstance(body, dict):
        raise ScenarioStoreError("scenario definition must be a JSON object")
    return parse_scenario_file(body)


__all__ = [
    "DEFINITIONS_FILENAME",
    "DEFINITIONS_VERSION",
    "ScenarioDefinition",
    "ScenarioParseError",
    "ScenarioStore",
    "ScenarioStoreError",
    "definitions_path",
]
