"""Scenario library organisation (P-134, Part IX — DERIVED scope).

The roadmap gives Part IX one line only; this slice's scope
is derived — see the P-134 slice doc. P-131's weighing
declined organisation ("No tags, favourites or search yet"),
P-132 declined it again behind consumption, and P-133's
scout declined it a third time behind export parity alone.
Those slices have landed or bank ahead of this one, so the
thrice-deferred slice is this one. What lands:

- organisation as its own truth: a versioned, owner-scoped
  JSON document ``scenario_organisation.json`` beside
  P-131's ``scenarios.json`` (house pattern, tolerant load,
  NO migration — head stays 0041). The P-131 definitions
  document and its storage shape are untouched, so the
  stored definition stays exactly the P-026 native shape
  and P-133's native-identity law is preserved.
- the tag law is P-024's own law, imported —
  ``normalise_tag`` / ``normalise_tags`` from
  runmal.library.organise (display form + casefold key,
  first display wins). No second normalisation law is
  invented for scenarios.
- findability at library scale (P-024's roadmap spirit):
  a pure query service over the owner's definitions —
  text search, tag filtering (any / all), favourites,
  named sorts, limit / offset — with the filtered total
  reported before paging, never after.
- honesty bounds: an unorganised definition's empty view
  is computed, never persisted; organisation rows for a
  deleted definition are orphans that are filtered at
  every read and can never surface; nothing here plays,
  evaluates or executes any definition content (P-027:
  content is data, never code).
"""

from __future__ import annotations

import copy
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from runmal.library.organise import normalise_tag, normalise_tags
from runmal.scenarios.store import ScenarioDefinition

ORGANISATION_VERSION = 1
ORGANISATION_FILENAME = "scenario_organisation.json"

SORTS = ("oldest", "newest", "name", "name_desc", "favourites_first")
TAG_MODES = ("any", "all")
DEFAULT_SORT = "oldest"


class ScenarioOrganisationError(ValueError):
    """An organisation operation the state of the world forbids."""


def organisation_path(data_dir: Path | None = None) -> Path:
    base = data_dir or Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return base / ORGANISATION_FILENAME


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ------------------------------------------------------------ record


@dataclass(frozen=True)
class ScenarioOrganisation:
    """One definition's organisation, owned by one user.

    ``tags`` holds DISPLAY forms in the order they were
    set; identity is the P-024 casefold key, so two rows
    can never disagree about whether a tag is present.
    """

    definition_id: str
    owner_id: str
    tags: tuple = ()
    is_favourite: bool = False
    updated_at: str = ""

    def to_dict(self) -> dict:
        return {
            "definition_id": self.definition_id,
            "owner_id": self.owner_id,
            "tags": list(self.tags),
            "is_favourite": bool(self.is_favourite),
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ScenarioOrganisation:
        tags = data.get("tags")
        return cls(
            definition_id=str(data.get("definition_id", "")),
            owner_id=str(data.get("owner_id", "")),
            tags=tuple(tags) if isinstance(tags, list) else (),
            is_favourite=bool(data.get("is_favourite", False)),
            updated_at=str(data.get("updated_at", "")),
        )


def organisation_view(
    definition: ScenarioDefinition,
    record: ScenarioOrganisation | None,
) -> dict:
    """The per-definition organisation view (computed default)."""
    return {
        "definition_id": definition.id,
        "name": definition.name,
        "tags": list(record.tags) if record else [],
        "is_favourite": bool(record.is_favourite) if record else False,
    }


def enrich_summary(summary: dict, record: ScenarioOrganisation | None) -> dict:
    """A P-131 summary plus its organisation (two additive keys)."""
    out = dict(summary)
    out["tags"] = list(record.tags) if record else []
    out["is_favourite"] = bool(record.is_favourite) if record else False
    return out


# ------------------------------------------------------------- store


class ScenarioOrganisationStore:
    """Durable organisation store: scenario_organisation.json."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def _load(self) -> list[ScenarioOrganisation]:
        try:
            doc = json.loads(self.path.read_text())
        except (OSError, ValueError):
            return []
        if not isinstance(doc, dict):
            return []
        rows = doc.get("organisations")
        if not isinstance(rows, list):
            return []
        out: list[ScenarioOrganisation] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                out.append(ScenarioOrganisation.from_dict(row))
            except (TypeError, ValueError):
                continue
        return out

    def _save(self, rows: list[ScenarioOrganisation]) -> None:
        doc = {
            "version": ORGANISATION_VERSION,
            "organisations": [row.to_dict() for row in rows],
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(doc, indent=2, sort_keys=True))

    def get(
        self, definition_id: str, owner_id: str
    ) -> ScenarioOrganisation | None:
        """The persisted row for one owned definition, or None."""
        for row in self._load():
            if row.definition_id == definition_id and row.owner_id == owner_id:
                return row
        return None

    def list_for_owner(self, owner_id: str) -> list[ScenarioOrganisation]:
        return [row for row in self._load() if row.owner_id == owner_id]

    def _upsert(
        self,
        definition_id: str,
        owner_id: str,
        *,
        tags: tuple,
        is_favourite: bool,
        now: str | None,
    ) -> ScenarioOrganisation:
        rows = self._load()
        record = ScenarioOrganisation(
            definition_id=definition_id,
            owner_id=owner_id,
            tags=tuple(tags),
            is_favourite=bool(is_favourite),
            updated_at=now or _now_iso(),
        )
        for i, row in enumerate(rows):
            if row.definition_id == definition_id and row.owner_id == owner_id:
                rows[i] = record
                self._save(rows)
                return record
        rows.append(record)
        self._save(rows)
        return record

    def set_tags(
        self, definition_id: str, owner_id: str, raw_tags, *, now: str | None = None
    ) -> ScenarioOrganisation:
        """Replace the tag set (P-024 law decides validity)."""
        try:
            pairs = normalise_tags(raw_tags)
        except ValueError as exc:
            raise ScenarioOrganisationError(str(exc)) from exc
        current = self.get(definition_id, owner_id)
        return self._upsert(
            definition_id,
            owner_id,
            tags=tuple(display for display, _key in pairs),
            is_favourite=current.is_favourite if current else False,
            now=now,
        )

    def add_tags(
        self, definition_id: str, owner_id: str, raw_tags, *, now: str | None = None
    ) -> ScenarioOrganisation:
        """Add tags; existing keys keep their first display form."""
        current = self.get(definition_id, owner_id)
        existing = list(current.tags) if current else []
        try:
            pairs = normalise_tags(existing + list(raw_tags)) if isinstance(raw_tags, list) else normalise_tags(raw_tags)
        except ValueError as exc:
            raise ScenarioOrganisationError(str(exc)) from exc
        return self._upsert(
            definition_id,
            owner_id,
            tags=tuple(display for display, _key in pairs),
            is_favourite=current.is_favourite if current else False,
            now=now,
        )

    def remove_tag(
        self, definition_id: str, owner_id: str, raw_tag, *, now: str | None = None
    ) -> ScenarioOrganisation:
        """Remove one tag by its P-024 key; absent is a no-op."""
        try:
            _display, key = normalise_tag(raw_tag)
        except ValueError as exc:
            raise ScenarioOrganisationError(str(exc)) from exc
        current = self.get(definition_id, owner_id)
        existing = list(current.tags) if current else []
        kept = [t for t in existing if normalise_tag(t)[1] != key]
        if current is not None and kept == existing:
            return current
        return self._upsert(
            definition_id,
            owner_id,
            tags=tuple(kept),
            is_favourite=current.is_favourite if current else False,
            now=now,
        )

    def set_favourite(
        self, definition_id: str, owner_id: str, is_favourite, *, now: str | None = None
    ) -> ScenarioOrganisation:
        if not isinstance(is_favourite, bool):
            raise ScenarioOrganisationError("is_favourite must be a boolean")
        current = self.get(definition_id, owner_id)
        return self._upsert(
            definition_id,
            owner_id,
            tags=tuple(current.tags) if current else (),
            is_favourite=is_favourite,
            now=now,
        )


# ------------------------------------------------------------- query


def _tag_keys(record: ScenarioOrganisation | None) -> set:
    if record is None:
        return set()
    keys = set()
    for tag in record.tags:
        try:
            keys.add(normalise_tag(tag)[1])
        except ValueError:
            continue
    return keys


def _search_text(definition: ScenarioDefinition) -> str:
    parts = [definition.name]
    for field in ("description", "scenario_text"):
        value = definition.definition.get(field)
        if isinstance(value, str):
            parts.append(value)
    return "\n".join(parts).casefold()


def query_definitions(
    definitions: list,
    records_by_id: dict,
    *,
    q: str | None = None,
    tags: list | None = None,
    tag_mode: str = "any",
    favourites_only: bool = False,
    sort: str = DEFAULT_SORT,
    limit: int | None = None,
    offset: int = 0,
):
    """Filter, sort and page *definitions*; return (page, total).

    ``records_by_id`` maps definition id -> organisation
    row (or None). Page rows are enriched P-131 summaries.
    Every invalid parameter raises ScenarioOrganisationError
    before any filtering happens.
    """
    if tag_mode not in TAG_MODES:
        raise ScenarioOrganisationError(
            f"unknown tag_mode: {tag_mode!r} (valid: any, all)"
        )
    if sort not in SORTS:
        raise ScenarioOrganisationError(
            f"unknown sort: {sort!r} (valid: {', '.join(SORTS)})"
        )
    if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or limit < 1):
        raise ScenarioOrganisationError("limit must be a positive integer")
    if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
        raise ScenarioOrganisationError("offset must be a non-negative integer")
    wanted_keys: set = set()
    if tags:
        try:
            wanted_keys = {key for _d, key in normalise_tags(list(tags))}
        except ValueError as exc:
            raise ScenarioOrganisationError(str(exc)) from exc
    needle = q.casefold().strip() if isinstance(q, str) else ""
    rows = list(definitions)
    if needle:
        rows = [d for d in rows if needle in _search_text(d)]
    if wanted_keys:
        def _matches(d):
            keys = _tag_keys(records_by_id.get(d.id))
            return bool(keys & wanted_keys) if tag_mode == "any" else wanted_keys <= keys
        rows = [d for d in rows if _matches(d)]
    if favourites_only:
        rows = [
            d for d in rows
            if records_by_id.get(d.id) is not None and records_by_id[d.id].is_favourite
        ]
    if sort == "newest":
        rows = list(reversed(rows))
    elif sort == "name":
        rows = sorted(rows, key=lambda d: d.name.casefold())
    elif sort == "name_desc":
        rows = sorted(rows, key=lambda d: d.name.casefold(), reverse=True)
    elif sort == "favourites_first":
        rows = sorted(
            rows,
            key=lambda d: 0 if (records_by_id.get(d.id) and records_by_id[d.id].is_favourite) else 1,
        )
    total = len(rows)
    page = rows[offset:]
    if limit is not None:
        page = page[:limit]
    return (
        [enrich_summary(d.summary(), records_by_id.get(d.id)) for d in page],
        total,
    )


def list_tags(definitions: list, records_by_id: dict) -> list:
    """The owner's tag census over EXISTING definitions only.

    Orphan organisation rows (their definition is gone)
    never surface here. Display is the first-seen form;
    rows are sorted by key.
    """
    census: dict = {}
    for definition in definitions:
        record = records_by_id.get(definition.id)
        if record is None:
            continue
        seen_here = set()
        for tag in record.tags:
            try:
                display, key = normalise_tag(tag)
            except ValueError:
                continue
            if key in seen_here:
                continue
            seen_here.add(key)
            entry = census.setdefault(key, {"tag": display, "key": key, "count": 0})
            entry["count"] += 1
    return [census[key] for key in sorted(census)]


__all__ = [
    "DEFAULT_SORT",
    "ORGANISATION_FILENAME",
    "ORGANISATION_VERSION",
    "SORTS",
    "TAG_MODES",
    "ScenarioOrganisation",
    "ScenarioOrganisationError",
    "ScenarioOrganisationStore",
    "enrich_summary",
    "list_tags",
    "organisation_path",
    "organisation_view",
    "query_definitions",
]
