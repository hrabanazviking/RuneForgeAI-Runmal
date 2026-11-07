"""Lorebook migration: existing lorebooks upgraded in place (P-047).

Roadmap line: *Migration: existing Runmal lorebooks upgraded in
place, behaviour-preserving, fixture-proven.*

Two layers of "existing lorebook" exist, and this module upgrades
both, in place, with a report of exactly what was filled in:

1. **Files.** The native format was never version-bumped (still
   ``runmal-lorebook`` version 1), so a pre-Part-III native file is
   told from a current one only by its missing keys: book-level
   ``scan_mode`` / ``scan_external_context`` (P-037) and the entry
   fields Part III added (``selective_logic`` P-032,
   ``inclusion_group`` / ``group_weight`` P-034, ``vectorised``
   P-035, ``probability`` / ``use_probability`` P-036, ``depth`` /
   ``role`` P-038). Until this slice the tolerant import
   normalisers defaulted those silently, with no record -- and one
   field (``use_probability`` on the native leg of
   ``transfer.parse_import``) was dropped outright; that fold is
   fixed in ``transfer._native_entry`` by this slice, and the
   upgrade report counts the entries it corrects as
   ``defect_fixes`` rather than pretending they are behaviour
   deltas. :func:`upgrade_lorebook` materialises every current
   field explicitly, in the SAME format the file arrived in:
   native stays native (raw-seeded + overlay, so unknown keys
   survive verbatim -- neither stock exporter may be used, both
   drop ``extra``), and a world-info file is refreshed through
   the interop layer's own raw-seeded export (a world-info file
   is a foreign import, not an existing Runmal book; converting
   it would destroy uids, ``originalData`` and unknown position
   codes, violating the INV-009 preservation discipline).
2. **Databases.** A database frozen at any revision before the
   head (0032) holds lorebooks without the Part III columns.
   :func:`upgrade_database` snapshots the lore tables raw,
   runs the ordinary migration chain (``migrate_to_head``;
   revisions 0024-0032 are pure ADD COLUMN + new tables, zero
   UPDATEs), snapshots again, and proves: every pre-existing
   row survives by id, every pre-existing column value is
   byte-identical, and every new column holds exactly its
   behaviour-preserving default. This slice takes NO new
   migration: the head stays 0032.

Behaviour proof discipline: the file invariant is stated over
the interop layer (the lossless layer):
``native_fields()`` + ``native_book_fields()`` of the parsed
old file equal those of the parsed upgraded file, EXCEPT the
enumerated defect-fix entries, whose probability delta
(e.g. 30 -> 100 under an explicit ``use_probability=false``)
is asserted explicitly. ``depth`` is materialised as ``None``
(undeclared), never as the compose-time default 4;
``token_budget`` is copied verbatim (null stays null).
"""

from __future__ import annotations

import copy
import sqlite3
from pathlib import Path

from runmal.db.migrate import current_revision, migrate_to_head
from runmal.lorebooks.interop import (
    NATIVE_MAPPED_FIELDS,
    export_worldinfo,
    parse_lorebook_file,
)
from runmal.lorebooks.rng import DEFAULT_PROBABILITY, normalise_probability

#: Report schema stamp; P-048's gate consumes these keys as-is.
UPGRADE_SCHEMA = "runmal-p047-lorebook-upgrade-v1"

#: Book keys of the current native shape (interop's book set,
#: plus the format/version markers re-emitted canonically).
NATIVE_BOOK_KEYS = frozenset(
    {
        "name",
        "entries",
        "description",
        "scan_depth",
        "token_budget",
        "scan_mode",
        "scan_external_context",
        "format",
        "version",
    }
)

#: Book fields an upgrade materialises (name/entries always ride).
NATIVE_BOOK_MATERIALISED = (
    "description",
    "scan_depth",
    "token_budget",
    "scan_mode",
    "scan_external_context",
)

#: Entry fields of the current native shape, in native_fields()
#: order (the canonical upgraded-native field set).
NATIVE_ENTRY_MATERIALISED = (
    "name",
    "content",
    "keys",
    "secondary_keys",
    "selective_logic",
    "inclusion_group",
    "group_weight",
    "probability",
    "use_probability",
    "priority",
    "position",
    "depth",
    "role",
    "enabled",
    "constant",
    "vectorised",
    "case_sensitive",
    "whole_word",
    "sticky_prompts",
    "cooldown_prompts",
    "delay_prompts",
)

#: Mapped aliases: canonical key <- alias key. The alias is a
#: mapped field, not an unknown: the upgrade canonicalises it
#: and drops the alias spelling so no stale duplicate remains.
_ENTRY_ALIASES = {"vectorised": "vectorized", "use_probability": "useProbability"}

#: Expected defaults for columns added by revisions 0024-0032,
#: asserted exactly by upgrade_database for pre-existing rows.
EXPECTED_NEW_DEFAULTS = {
    "lorebooks": {"scan_mode": "depth", "scan_external_context": 0},
    "lore_entries": {
        "selective_logic": "and_any",
        "inclusion_group": "",
        "group_weight": 100,
        "vectorised": 0,
        "probability": 100,
        "depth": None,
        "role": "system",
    },
}

NEW_TABLES = ("chat_lore_entry_states", "character_book_bindings", "lorebook_scopes")

__all__ = [
    "UPGRADE_SCHEMA",
    "inspect_lorebook",
    "upgrade_lorebook",
    "upgrade_database",
]


def _as_dict(data) -> dict:
    """Accept a dict, or bytes/str/a parsed file's raw dict."""
    if isinstance(data, dict):
        return data
    parsed = parse_lorebook_file(data)
    return parsed.raw


def _entry_flag(raw: dict, snake: str, camel: str):
    """An entry's boolean flag under either spelling (snake wins)."""
    if raw.get(snake) is not None:
        return raw.get(snake)
    return raw.get(camel)


def _defect_fix_entries(data: dict, source_format: str) -> list[int]:
    """Indices of native entries the use_probability fold corrects.

    An entry is a defect fix when it carries an explicit
    use_probability/useProbability=false and a probability that
    normalises away from the gate-off default: before this
    slice the native DB leg stored the raw percent (gate live),
    after the fix (and in the upgraded file's stored form) the
    effective percent is 100. World-info entries are not defect
    fixes: their leg always folded.
    """
    if source_format != "native" or not isinstance(data.get("entries"), list):
        return []
    fixed: list[int] = []
    for index, raw in enumerate(data["entries"]):
        if not isinstance(raw, dict):
            continue
        flag = _entry_flag(raw, "use_probability", "useProbability")
        if flag is not None and not bool(flag):
            if normalise_probability(raw.get("probability")) != DEFAULT_PROBABILITY:
                fixed.append(index)
    return fixed


def _native_fields_map(parsed) -> list[dict]:
    return [entry.native_fields() for entry in parsed.entries]


def _behaviour_diffs(old, new, defect_indices: list[int]) -> list[str]:
    """Interop-layer behaviour diffs between two parsed files.

    Compares native book fields + per-entry native_fields().
    The probability delta on a defect-fix entry is the
    enumerated correction, not a behaviour diff, and is
    filtered here (asserted separately by the battery).
    """
    diffs: list[str] = []
    if old.native_book_fields() != new.native_book_fields():
        diffs.append("book")
    old_entries = _native_fields_map(old)
    new_entries = _native_fields_map(new)
    if len(old_entries) != len(new_entries):
        diffs.append("entry_count")
        return diffs
    for index, (before, after) in enumerate(zip(old_entries, new_entries, strict=True)):
        for key in before:
            if before[key] != after.get(key):
                if index in defect_indices and key in ("probability", "use_probability"):
                    continue
                diffs.append(f"entries[{index}].{key}")
    return diffs


def _inspect(data: dict) -> tuple[dict, object]:
    parsed = parse_lorebook_file(copy.deepcopy(data))
    source_format = parsed.source_format
    defect_indices = _defect_fix_entries(data, source_format)
    if source_format == "native":
        raw_entries = data.get("entries") or []
        book_missing = [f for f in NATIVE_BOOK_MATERIALISED if f not in data]
        entry_missing: dict[str, int] = {}
        unknown_entry: set[str] = set()
        preserved = 0
        for raw in raw_entries:
            if not isinstance(raw, dict):
                continue
            for field_name in NATIVE_ENTRY_MATERIALISED:
                if field_name in raw:
                    continue
                alias = _ENTRY_ALIASES.get(field_name)
                if alias and alias in raw:
                    continue
                entry_missing[field_name] = entry_missing.get(field_name, 0) + 1
            for key in raw:
                if key not in NATIVE_MAPPED_FIELDS:
                    unknown_entry.add(key)
                    preserved += 1
        unknown_book = sorted(k for k in data if k not in NATIVE_BOOK_KEYS)
        preserved += len(unknown_book)
        generation = (
            "native-current"
            if not book_missing and not entry_missing
            else "native-legacy"
        )
    else:
        book_missing = []
        entry_missing = {}
        unknown_entry = set()
        preserved = 0
        for entry in parsed.entries:
            for key in entry.extra:
                unknown_entry.add(key)
                preserved += 1
        unknown_book = sorted(parsed.extra.keys())
        preserved += len(unknown_book)
        if parsed.original_data is not None:
            preserved += 1
        generation = "worldinfo"
    upgraded, _ = _upgrade(data, parsed)
    reparsed = parse_lorebook_file(copy.deepcopy(upgraded))
    diffs = _behaviour_diffs(parsed, reparsed, defect_indices)
    report = {
        "schema": UPGRADE_SCHEMA,
        "format": source_format,
        "generation": generation,
        "entry_count": len(parsed.entries),
        "book_missing_fields": book_missing,
        "entry_missing_fields": entry_missing,
        "unknown_book_fields": unknown_book,
        "unknown_entry_fields": sorted(unknown_entry),
        "preserved_unknown_count": preserved,
        "defect_fixes": len(defect_indices),
        "defect_fix_entries": defect_indices,
        "would_change": upgraded != data,
        "behaviour_preserving": not diffs,
        "behaviour_diffs": diffs,
    }
    return report, parsed


def inspect_lorebook(data) -> dict:
    """Report what an in-place upgrade would do, changing nothing."""
    report, _ = _inspect(_as_dict(data))
    return report


def _upgrade(data: dict, parsed=None) -> tuple[dict, dict]:
    if parsed is None:
        parsed = parse_lorebook_file(copy.deepcopy(data))
    if parsed.source_format == "worldinfo":
        # Raw-seeded refresh through the interop layer itself:
        # mapped fields overlaid, extra/originalData/uids and
        # unknown position codes ride back verbatim.
        return export_worldinfo(parsed), parsed
    raw_entries = data.get("entries") or []
    upgraded: dict = copy.deepcopy(data)
    upgraded["format"] = "runmal-lorebook"
    upgraded["version"] = 1
    upgraded["name"] = parsed.name
    upgraded["description"] = parsed.description
    upgraded["scan_depth"] = parsed.scan_depth if parsed.scan_depth is not None else 4
    # token_budget verbatim: null stays null, a stringly value
    # stays stringly -- coercing it would change what
    # parse_import reads back.
    upgraded["token_budget"] = copy.deepcopy(data.get("token_budget"))
    upgraded["scan_mode"] = parsed.scan_mode
    upgraded["scan_external_context"] = parsed.scan_external_context
    entries_out: list[dict] = []
    for raw, entry in zip(raw_entries, parsed.entries, strict=True):
        if not isinstance(raw, dict):
            entries_out.append(copy.deepcopy(raw))
            continue
        merged: dict = copy.deepcopy(raw)
        fields = entry.native_fields()
        # The camelCase probability alias is a mapped field the
        # interop native parse does not read; carry it into the
        # canonical snake spelling so it is not stranded.
        if "use_probability" not in raw and raw.get("useProbability") is not None:
            fields["use_probability"] = bool(raw.get("useProbability"))
        for key, value in fields.items():
            merged[key] = copy.deepcopy(value)
        for canonical, alias in _ENTRY_ALIASES.items():
            if alias in merged and canonical in fields:
                del merged[alias]
        entries_out.append(merged)
    upgraded["entries"] = entries_out
    return upgraded, parsed


def upgrade_lorebook(data) -> tuple[dict, dict]:
    """Upgrade one lorebook file in place (same format returned).

    Returns (upgraded_dict, report) where the report is
    inspect_lorebook's report on the ORIGINAL plus
    ``fields_materialised`` (the count of mapped fields the
    upgrade filled in) and ``already_current``. The input is
    never mutated. Idempotent: upgrading the result again
    yields the identical dict.
    """
    original = _as_dict(data)
    report, parsed = _inspect(original)
    upgraded, _ = _upgrade(original, parsed)
    materialised = len(report["book_missing_fields"]) + sum(
        report["entry_missing_fields"].values()
    )
    full = dict(report)
    full["fields_materialised"] = materialised
    full["already_current"] = not report["would_change"]
    return upgraded, full


def _snapshot(conn: sqlite3.Connection, table: str) -> dict:
    """Raw rows of one table: {id: {column: (type_name, value)}}."""
    columns = [row[1] for row in conn.execute(f"PRAGMA table_info({table})")]
    id_index = columns.index("id")
    rows: dict = {}
    for record in conn.execute(f"SELECT * FROM {table}"):
        row = {}
        for column, value in zip(columns, record, strict=True):
            row[column] = (type(value).__name__, value)
        rows[str(record[id_index])] = row
    return rows


def _table_names(conn: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def upgrade_database(db_path) -> dict:
    """Upgrade a database's lorebooks in place, proven by snapshot.

    Snapshots ``lorebooks`` + ``lore_entries`` raw, runs the
    ordinary migration chain to head, snapshots again, and
    verifies: every pre-existing row survives by id, every
    pre-existing column value is identical (raw sqlite
    (type, value), compared by column name -- never through
    the ORM, whose normalisers would mask a real diff), row
    counts are unchanged, and each column added by revisions
    0024-0032 holds exactly its behaviour-preserving default
    on the pre-existing rows. A missing database reports
    ``missing``; a database with no lore tables reports
    ``no_lorebooks`` and is left untouched (report-and-stop:
    there is nothing to upgrade, and the application's own
    startup migration owns schema creation).
    """
    path = Path(db_path)
    base = {"schema": UPGRADE_SCHEMA, "db_path": str(path)}
    if not path.exists():
        return {**base, "status": "missing", "applied_revisions": []}
    conn = sqlite3.connect(path)
    try:
        tables = _table_names(conn)
        if "lorebooks" not in tables or "lore_entries" not in tables:
            # Report-and-stop WITHOUT touching the file: the
            # revision is read raw here because current_revision
            # (via applied_revisions) creates the version table
            # as a side effect, which would write into a database
            # this function promises to leave untouched.
            untouched_revision = None
            if "schema_migrations" in tables:
                rows = conn.execute(
                    "SELECT revision FROM schema_migrations ORDER BY revision"
                ).fetchall()
                untouched_revision = rows[-1][0] if rows else None
            return {
                **base,
                "status": "no_lorebooks",
                "before_revision": untouched_revision,
                "after_revision": untouched_revision,
                "applied_revisions": [],
            }
        before_revision = current_revision(path)
        before = {
            table: _snapshot(conn, table) for table in ("lorebooks", "lore_entries")
        }
        before_columns = {
            table: {
                column
                for row in rows.values()
                for column in row
            }
            for table, rows in before.items()
        }
    finally:
        conn.close()
    applied = migrate_to_head(path)
    after_revision = current_revision(path)
    conn = sqlite3.connect(path)
    try:
        tables_after = _table_names(conn)
        after = {
            table: _snapshot(conn, table) for table in ("lorebooks", "lore_entries")
        }
    finally:
        conn.close()
    mismatches: list[str] = []
    rows_verified = 0
    defaults_ok = True
    for table in ("lorebooks", "lore_entries"):
        for row_id, before_row in before[table].items():
            after_row = after[table].get(row_id)
            if after_row is None:
                mismatches.append(f"{table}:{row_id} missing after upgrade")
                continue
            rows_verified += 1
            for column, typed_value in before_row.items():
                if after_row.get(column) != typed_value:
                    mismatches.append(
                        f"{table}:{row_id}.{column} changed "
                        f"{typed_value!r} -> {after_row.get(column)!r}"
                    )
            for column, expected in EXPECTED_NEW_DEFAULTS[table].items():
                if column in before_columns[table]:
                    continue
                actual = after_row.get(column)
                if actual != (type(expected).__name__, expected):
                    defaults_ok = False
                    mismatches.append(
                        f"{table}:{row_id}.{column} default "
                        f"{actual!r} != {expected!r}"
                    )
    return {
        **base,
        "status": "upgraded" if applied else "already_current",
        "before_revision": before_revision,
        "after_revision": after_revision,
        "applied_revisions": applied,
        "books_before": len(before["lorebooks"]),
        "books_after": len(after["lorebooks"]),
        "entries_before": len(before["lore_entries"]),
        "entries_after": len(after["lore_entries"]),
        "rows_verified": rows_verified,
        "defaults_verified": defaults_ok and not mismatches,
        "new_tables_present": sorted(t for t in NEW_TABLES if t in tables_after),
        "mismatches": mismatches,
        "behaviour_preserving": not mismatches,
    }
