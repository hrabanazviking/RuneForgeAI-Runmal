"""Library unmappable-content census (P-145, Part IX - DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios - the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record - see the P-145 slice doc.
What the derivation found missing, and what lands here:

- every P-131 record carries its P-026 import report AS
  DATA, and that report's ``unmappable`` list is the one
  naming of the machinery a file carried that Rúnmál
  cannot map - recorded, never executed (P-027). P-139
  calls that report "the only naming" of a definition's
  unmappable elements and notes that deleting the record
  loses it. Yet the naming is reachable only one record
  at a time (the P-131 single read, P-133's per-definition
  not_restored, P-141's per-definition pack provenance),
  and the library list shape (P-131 summary) reduces the
  whole list to one bool, ``has_unmappable``. No road
  joined the reports across the caller's library, so an
  owner could not answer how much unmappable machinery
  their library carries, of what kinds, and in which
  definitions, except by fetching every record in full.

This module is the read service behind the census road:
one pure read over the caller's own records, in store
order. Every row's elements are read from the record's
own stored report through the exact reading law P-133's
``_not_restored`` established (a missing or malformed
report reads as no elements; a non-dict element row is
skipped; fields are str-coerced) - no second report law
is invented - and the row's definition is named by
P-131's ``summary()`` verbatim. Every count is summed
from the rows themselves, so the census cannot drift
from its own evidence (the P-144 construction).

Honesty bounds, stated in every answer:

- the census is a pure read: it writes, deletes and
  repairs nothing, and every definition and report
  named still stands as it stood;
- a census, not a cleanup: unmappable elements stay
  recorded on their definitions - named, never removed,
  converted or repaired;
- named, never executed: the elements are the P-131
  report's own naming, carried as data; censusing
  evaluates no condition, plays nothing back and
  executes nothing a definition carries (P-027);
- the report is the record: the census claims only what
  the stored reports name, as they stand now - a record
  whose report is missing or malformed reads as clean
  here exactly as P-133's export reads it, and a replace
  (P-131) re-parses and replaces the report, so the
  census always judges the current report of the
  current revision and keeps no history;
- the census carries the report rows themselves, which
  is its whole purpose, but no definition content - no
  scenario text, roles or bootstrap bodies; the full
  record stays on the P-131 single-read road.

No new store, no migration (the head stays 0041), no
storage-shape change, and no change to any banked answer.
"""

from __future__ import annotations

_NOTE_PURE_READ = (
    "this census is a read of the world as it stands; "
    "censusing has written, deleted and repaired "
    "nothing, and every definition named here still "
    "stands as it stood"
)
_NOTE_NOT_A_CLEANUP = (
    "a census, not a cleanup: unmappable elements stay "
    "recorded on their definitions - named here, never "
    "removed, converted or repaired, and no road cleans "
    "them up"
)
_NOTE_NAMED_NEVER_EXECUTED = (
    "named, never executed: every element here is the "
    "import report's own naming, carried as data - "
    "censusing evaluates no condition, plays nothing "
    "back and executes nothing a definition carries"
)
_NOTE_REPORT_IS_THE_RECORD = (
    "the report is the record: this census claims only "
    "what the stored import reports name, as they stand "
    "now - a definition whose report is missing or "
    "malformed reads as clean here, and a replace "
    "re-parses and replaces the report, so the census "
    "judges the current report of the current revision "
    "and keeps no history"
)
_NOTE_NO_DEFINITION_CONTENT = (
    "this census carries the reports' unmappable rows "
    "themselves but no definition content - no scenario "
    "text, roles or bootstrap bodies; the full record "
    "stays on the single-definition read road"
)


def _elements(record) -> list[dict]:
    """One record's unmappable naming, as plain data.

    P-133's reading law verbatim in effect: the rows of
    the stored report's ``unmappable`` list, dict rows
    only, each reduced to {path, kind, name, reason}
    with str-coerced fields. A missing or malformed
    report reads as an empty list - the census still
    proceeds, and claims nothing it cannot read.
    """
    report = record.report if isinstance(record.report, dict) else {}
    rows = report.get("unmappable")
    if not isinstance(rows, list):
        return []
    out: list[dict] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        out.append(
            {
                "path": str(row.get("path", "")),
                "kind": str(row.get("kind", "")),
                "name": str(row.get("name", "")),
                "reason": str(row.get("reason", "")),
            }
        )
    return out


def census_unmappable(definitions) -> dict:
    """The library unmappable-content census for one owner.

    ``definitions`` is the caller's own ScenarioDefinition
    records (the router passes the store's list_for_owner
    answer; owner scoping is the store's own). Rows, in
    store order, cover ONLY definitions whose stored
    report names at least one unmappable element; each
    row names its definition by P-131's summary()
    verbatim and carries the report's elements verbatim
    (in report order) with their kinds listed per element,
    so the kinds sum to the row's count. ``by_kind`` rolls
    the same elements up per kind in first-appearance
    order across the rows, and every count is summed from
    the rows themselves. Pure read: writes nothing,
    deletes nothing, repairs nothing.
    """
    rows: list[dict] = []
    for record in definitions:
        elements = _elements(record)
        if not elements:
            continue
        rows.append(
            {
                "definition": record.summary(),
                "source_format": record.source_format,
                "unmappable_count": len(elements),
                "kinds": [element["kind"] for element in elements],
                "unmappable": elements,
            }
        )
    by_kind: list[dict] = []
    kind_index: dict[str, dict] = {}
    for row in rows:
        for element in row["unmappable"]:
            entry = kind_index.get(element["kind"])
            if entry is None:
                entry = {"kind": element["kind"], "count": 0}
                kind_index[element["kind"]] = entry
                by_kind.append(entry)
            entry["count"] += 1
    total = len(definitions)
    counts = {
        "definitions_total": total,
        "definitions_with_unmappable": len(rows),
        "definitions_clean": total - len(rows),
        "unmappable_total": sum(
            row["unmappable_count"] for row in rows),
        "kinds_represented": len(by_kind),
    }
    return {
        "definitions": rows,
        "by_kind": by_kind,
        "counts": counts,
        "notes": [
            _NOTE_PURE_READ,
            _NOTE_NOT_A_CLEANUP,
            _NOTE_NAMED_NEVER_EXECUTED,
            _NOTE_REPORT_IS_THE_RECORD,
            _NOTE_NO_DEFINITION_CONTENT,
        ],
    }


__all__ = ["census_unmappable"]
