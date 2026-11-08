"""Stored-definition file export (P-133, Part IX — DERIVED scope).

The roadmap gives Part IX one line only ("Scenarios — the
Visual Novel Engine", P-131..P-154); this slice's scope is
derived from the in-tree record — see the P-133 slice doc.
What the derivation found missing, and what lands here:

- the one missing leg of import/export parity, named by
  P-132 twice: P-131 made scenario files storable and
  P-132 gave the stored truth its first consumer (binding),
  but no road led from a STORED definition back to a FILE.
  The only export road (P-026) parses a caller-supplied
  body; nothing addressed a definition by id.

This module is the service behind the by-id export road.
It builds the file through P-026's OWN exporters — no
second export law is invented — from a reconstruction of
the stored definition, and it returns an honest report
beside the file: what the export restores, and by name
what it cannot.

The reconstruction law (scout finding F1): a stored
definition is the P-026 NATIVE shape — typed fields plus
``extra``. It holds no ``raw``: the original file was
never persisted (P-131). P-026's Voxta exporter is a raw
overlay, so handing it a parse of the stored dict (whose
``raw`` IS the native dict) would leak every native key
verbatim beside its Voxta spelling. The reconstruction
therefore parses the stored definition and then clears
``raw``, ``unmappable_values`` and every element's
``raw``: nothing is fabricated, and the Voxta file that
comes out is a clean typed-fields conversion. P-026's
stateless overlay behaviour itself is banked and pinned
by its own battery; this slice does not rewrite it — the
finding is carried in the scout and the evidence.

Honesty bounds, stated in every report:

- a Voxta file's unmappable raw values never persisted
  (P-131); an export cannot restore them. Each one is
  NAMED in the report's ``not_restored``, read from the
  record's own P-026 import report — never silently
  dropped, never invented back.
- the native export IS the stored definition (dict-equal,
  pinned by the battery for native- and Voxta-origin
  records alike): file→store→file and store→file→store
  round-trips are exact at the definition level.
- re-importing an exported native file cannot resurrect
  the unmappable naming: the native shape never carried
  those values, so the new record's report is a native
  report. The loss is one-way and is said so.
- a carried ``extra`` key whose spelling the requested
  format's own typed fields already write (a native file
  carrying ``variables`` beside ``initial_variables``, say)
  cannot ride that format's file twice: the typed value
  wins the key, and the carried value is NAMED in the
  report's ``carried_shadowed`` — never silently dropped
  (finisher finding F2; the native file, whose shape is
  the stored definition itself, shadows nothing).
- truth-as-data throughout (P-027): exporting a
  definition plays nothing back and executes nothing it
  carries; unmappable machinery stays a line in the
  report, never a running thing.
"""

from __future__ import annotations

import copy

from runmal.scenarios.fileexport import export_native, export_voxta
from runmal.scenarios.fileimport import parse_scenario_file
from runmal.scenarios.filemodels import ScenarioFile

#: Export formats a stored definition can be handed back in.
FORMATS = ("native", "voxta")

#: The default hand-back shape: the stored truth's own shape.
DEFAULT_FORMAT = "native"

_NOTE_NO_RAW = (
    "stored definitions are the P-026 native shape; no original "
    "raw file persists, so no raw overlay is applied"
)
_NOTE_VOXTA_CONVERSION = (
    "the Voxta file is a typed-fields conversion built by "
    "P-026's own exporter from the stored definition, not the "
    "original Voxta file"
)
_NOTE_NOT_RESTORED = (
    "each element named in not_restored was reported unmappable "
    "at import and its value was never persisted (P-131); no "
    "export can restore it"
)
_NOTE_NATIVE_REIMPORT = (
    "the native file is the stored definition itself; "
    "re-importing it creates a record whose native report "
    "cannot name unmappable elements the native shape never "
    "carried"
)
_NOTE_CARRIED_SHADOWED = (
    "each key named in carried_shadowed is carried in the "
    "stored definition under a spelling this format's own "
    "typed fields already write; the typed value wins the "
    "key and the carried value does not appear in the file"
)


class StoredExportError(ValueError):
    """A stored-export request the world forbids (unknown format)."""


def scenario_file_from_stored(definition: dict) -> ScenarioFile:
    """Rebuild a ScenarioFile from a stored definition dict.

    The parse is P-026's own (the store door's law, reused);
    the stored truth holds no raw, so the parse's raw —
    which for a native body is the body itself — is cleared,
    with ``unmappable_values`` and every element's ``raw``,
    before any exporter sees it. Typed fields and carried
    ``extra`` ride through untouched.
    """
    parsed = parse_scenario_file(copy.deepcopy(definition))
    parsed.raw = {}
    parsed.unmappable_values = {}
    for role in parsed.roles:
        role.raw = {}
    for message in parsed.bootstrap_messages:
        message.raw = {}
    for context in parsed.contexts:
        context.raw = {}
    return parsed


def _not_restored(record) -> list[dict]:
    """The record's own unmappable naming, as plain data.

    Read from the stored P-026 import report; a missing or
    malformed report reads as an empty list — the export
    still proceeds, and claims nothing it cannot read.
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


def _carried_shadowed(rebuilt, file_dict: dict) -> list[dict]:
    """Carried ``extra`` keys this file cannot also carry.

    A carried key rides the export under ``setdefault``
    (P-026's law), so it survives verbatim — UNLESS the
    format's own typed fields already wrote that key with
    a different value, in which case the carried value is
    not in the file at all. Those keys are named here,
    with the reason; a carried key whose value equals the
    written value loses nothing and is not named. On the
    native road this never fires: the native shape IS the
    stored definition, carried keys included.
    """
    out: list[dict] = []
    for key in sorted(rebuilt.extra):
        if key in file_dict and file_dict[key] != rebuilt.extra[key]:
            out.append(
                {
                    "key": key,
                    "reason": (
                        "carried value is shadowed by this "
                        "format's own typed field of the same "
                        "key; the typed value is in the file"
                    ),
                }
            )
    return out


def export_stored_definition(record, format: str = DEFAULT_FORMAT):
    """Export one stored definition record to a file shape.

    Returns ``(file_dict, report_dict)``. An unknown format
    raises :class:`StoredExportError` before any work. The
    file is built by P-026's own exporters over the honest
    reconstruction; the report names the format, the record
    it came from (id, name, pinned revision, the record's
    own source_format), the exported top-level keys, every
    not-restored element, and the standing honesty notes.
    """
    if format not in FORMATS:
        raise StoredExportError(
            f"unknown export format: {format!r} (valid: native, voxta)"
        )
    rebuilt = scenario_file_from_stored(record.definition)
    if format == "voxta":
        file_dict = export_voxta(rebuilt)
    else:
        file_dict = export_native(rebuilt)
    not_restored = _not_restored(record)
    shadowed = _carried_shadowed(rebuilt, file_dict)
    notes = [_NOTE_NO_RAW]
    if format == "voxta":
        notes.append(_NOTE_VOXTA_CONVERSION)
    if not_restored:
        notes.append(_NOTE_NOT_RESTORED)
    if format == "native":
        notes.append(_NOTE_NATIVE_REIMPORT)
    if shadowed:
        notes.append(_NOTE_CARRIED_SHADOWED)
    report = {
        "definition_id": record.id,
        "name": record.name,
        "revision": record.revision,
        "source_format": record.source_format,
        "format": format,
        "exported_keys": sorted(file_dict.keys()),
        "not_restored": not_restored,
        "carried_shadowed": shadowed,
        "notes": notes,
    }
    return file_dict, report


__all__ = [
    "DEFAULT_FORMAT",
    "FORMATS",
    "StoredExportError",
    "export_stored_definition",
    "scenario_file_from_stored",
]
