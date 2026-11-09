"""Hub content-shape census (P-196, Part XII - DERIVED).

The roadmap gives Part XII one line only ("The Hub,
Sovereign Shape", P-187..P-202); this slice's scope is
derived from Runmal's own in-tree record - see
docs/HUB_CONTENT_SHAPE_CENSUS_2026-11-09.md and
hidden_files/P196_SCOUT.md / P196_DESIGN.md.

What the derivation found: every banked hub surface
that opens a pack reads its payload through exactly
one lens - TEXT. P-191 searches string values and
P-193 counts string values and their characters, both
under a walk law that excludes by name the facts this
census measures: dict KEYS (structure, not content),
NON-STRING values (numbers, booleans, nulls - the
settings, weights, flags and thresholds a pack is
mostly made of) and the CONTAINERS themselves (objects
and arrays, and how deeply they nest). No banked
document carries a single field for any of these:
P-189 counts browse verdicts and checksum claims,
P-193 counts string volume, P-194 aggregates one
query's answer and P-195 groups entries by verified
identity. This module is the structural census, in
the P-193 shape: a pure aggregate composing the
owning surfaces verbatim, classified under a closed
law, counts summed from the composed reads' own
values.

- Composition, verbatim roads only - never a second
  parser. Each entry is judged under P-188's locator
  law (registry.locator_state, judged live) and
  P-188's size bound (MAX_BROWSE_BYTES, imported: one
  bound law), then parsed through the owning layer's
  OWN verified parse road, dispatched exactly as
  P-193 dispatches: lorebook_pack ->
  lorebooks.packs.parse_pack (payload member lorebook),
  prompt_pack -> presets.packs.parse_pack (payload
  member items), scenario_pack -> scenarios.packs.
  parse_pack (payload member scenario), preset_bundle
  -> presets.bundles.parse_share (the bundle it
  returns is the payload). Each parse road verifies
  format, manifest against payload, the content
  checksum and the payload itself before anything is
  measured: only a VERIFIED payload is walked.
- The walk law: every NODE in the verified payload
  counts exactly once under the closed NODE_TYPES law
  (object, array, string, number, boolean, null - a
  boolean is never counted as a number), every dict
  KEY counts once toward the key count (keys are
  structure: counted as counts only, and key NAMES
  are never returned anywhere), and max_depth is the
  deepest nesting with the payload root at depth 1.
  A member under a content_sha256 key is excluded
  WHOLE - neither the key nor its value subtree is
  counted (P-191's identity exclusion carried to the
  pair: the pack's identity is not its shape).
- DISTINCTNESS, stated plainly: the string NODE count
  here necessarily equals P-193's string-value count
  on the same estate - the same nodes, counted as
  nodes rather than measured for length - and that
  agreement is expected, not the new fact (as P-193's
  parsed counts agree with P-189's inspected counts,
  because inspect stands on parse). The new facts are
  the other five node types, the key totals, the node
  totals and the depth axes, none of which any banked
  document carries. This census carries no P-193
  volume field (no character is ever counted), no
  P-189 verdict, no P-194 query axis and no P-195
  grouping: verified checksums ride per row as the
  parse roads' own facts, as at P-193, and are never
  compared across rows here.
- No silent omission (the P-191 law): every entry
  ends parsed, or named by its row's outcome -
  unavailable (the locator is not ready; no read
  attempted) or invalid (unreadable at read time,
  over the size bound, not valid JSON on the bundle
  road, or the owning layer's own parse road refused
  it, its refusal carried verbatim) - under P-193's
  OUTCOMES law, imported (one law, never forked), and
  coverage_complete carries the truth as data: any
  non-parsed entry makes it false, and count always
  equals parsed plus unavailable plus invalid.
- NO content is retained or returned: this census
  carries counts, entry data and verified checksums
  only - never a key name, never a value, never an
  excerpt and never a payload field, anywhere in the
  document (the P-183 law).
- The estate is classified under a closed census law
  (SHAPE_CENSUS_STATES), judged on the parsed axis:
  no_entries / no_shape / some_shape / all_shape.

Honest boundaries, and the cost stated plainly: a
shape census parses every ready entry, so it READS
pack files - each through its own layer's verified
parse road, under the 16 MiB bound, so an oversize,
corrupt or wrong-kind pack is an invalid row, never
a census failure. The census writes nothing, imports
nothing, installs nothing, copies nothing and grants
nothing; an entry's registered checksum stays the
caller's claim and is never upgraded by being counted
beside the verified one. Signing and friend-instance
exchange stay declined - no key or transport
machinery is banked. There is no central store, no
catalogue and no creator profile here (VX-59). No
migration: head stays 0041.
"""

from __future__ import annotations

import json
from pathlib import Path

from runmal.hub import browse as hub_browse
from runmal.hub import content_census as hub_content_census
from runmal.hub import registry as hub_registry
from runmal.hub.registry import HubEntry
from runmal.lorebooks import packs as lorebook_packs
from runmal.presets import bundles as preset_bundles
from runmal.presets import packs as prompt_packs
from runmal.scenarios import packs as scenario_packs

CONTENT_SHAPE_CENSUS_SCHEMA = "runmal-p196-hub-content-shape-census-v1"

MAX_BROWSE_BYTES = hub_browse.MAX_BROWSE_BYTES  # P-188's bound: one law

# P-193's outcomes law, imported: one law, never forked.
OUTCOME_PARSED = hub_content_census.OUTCOME_PARSED
OUTCOME_UNAVAILABLE = hub_content_census.OUTCOME_UNAVAILABLE
OUTCOME_INVALID = hub_content_census.OUTCOME_INVALID
OUTCOMES = hub_content_census.OUTCOMES

NODE_OBJECT = "object"
NODE_ARRAY = "array"
NODE_STRING = "string"
NODE_NUMBER = "number"
NODE_BOOLEAN = "boolean"
NODE_NULL = "null"
NODE_TYPES = frozenset({
    NODE_OBJECT, NODE_ARRAY, NODE_STRING,
    NODE_NUMBER, NODE_BOOLEAN, NODE_NULL,
})

SHAPE_CENSUS_STATE_NO_ENTRIES = "no_entries"
SHAPE_CENSUS_STATE_NO_SHAPE = "no_shape"
SHAPE_CENSUS_STATE_SOME_SHAPE = "some_shape"
SHAPE_CENSUS_STATE_ALL_SHAPE = "all_shape"
SHAPE_CENSUS_STATES = frozenset({
    SHAPE_CENSUS_STATE_NO_ENTRIES, SHAPE_CENSUS_STATE_NO_SHAPE,
    SHAPE_CENSUS_STATE_SOME_SHAPE, SHAPE_CENSUS_STATE_ALL_SHAPE,
})

NOTES = (
    "Pure read, owner scoped: only the caller's own "
    "entries are censused; this census stores, "
    "registers, removes, imports, installs, copies "
    "and writes nothing.",
    "Distinctness: P-189's census counts browse "
    "verdicts and checksum claims, P-193's counts "
    "verified payload string VOLUME (values and "
    "characters), P-194's counts one query's answer "
    "and P-195's groups entries by verified identity; "
    "this census measures the verified payloads' "
    "STRUCTURE - node types, keys and depth. Its "
    "string count is a node count, never a length: it "
    "necessarily equals P-193's string-value count on "
    "the same estate (the same nodes, counted not "
    "measured), and that agreement is expected and "
    "stated; the other node types, the keys and the "
    "depth are the new facts.",
    "Cost law: a shape census reads and verifies "
    "every ready pack in the estate, each through its "
    "own layer's verified parse road and each under "
    "the browse size bound (max_browse_bytes in this "
    "document) - the price of measuring contents the "
    "registry does not hold.",
    "The walk counts every payload node exactly once "
    "by type (object, array, string, number, boolean, "
    "null - a boolean is never a number) and every "
    "dict key once as structure. Key names and values "
    "are never returned: counts only, anywhere in "
    "this document. A member under a content_sha256 "
    "key is the pack's identity, not its shape, and "
    "is excluded whole - neither the key nor its "
    "subtree is counted. The pack envelope (manifest "
    "and provenance) lives outside the payload member "
    "and is never walked.",
    "No silent omission: every entry was parsed or "
    "is named by its row's outcome - unavailable (its "
    "locator is not ready) or invalid (its own layer's "
    "road refused it, it could not be read, or it "
    "exceeds the size bound) - under P-193's outcomes "
    "law, imported whole. coverage_complete is false "
    "whenever any entry was not parsed, and count "
    "always equals parsed plus unavailable plus "
    "invalid.",
    "verified_content_sha256 on a row is the checksum "
    "the owning layer's own parse road verified "
    "(empty for a bare preset bundle, whose road "
    "verifies none, and for any entry that was not "
    "parsed). It rides as that road's fact and is "
    "never compared across rows here. An entry's "
    "registered checksum stays the caller's claim and "
    "is never upgraded by being counted.",
    "Signing and friend-instance exchange stay "
    "declined: no key or transport machinery is "
    "banked, and this census invents none. There is "
    "no central store, no catalogue and no creator "
    "profile on this road (the VX-59 sovereign "
    "shape).",
)


def _parse_payload(entry: HubEntry, raw: bytes):
    """Dispatch to the owning layer's own verified parse
    road; returns (payload, verified_content_sha256).
    P-193's dispatch, carried verbatim."""
    if entry.kind == hub_registry.KIND_LOREBOOK_PACK:
        pack = lorebook_packs.parse_pack(raw)
        return pack["lorebook"], pack["manifest"]["content_sha256"]
    if entry.kind == hub_registry.KIND_PROMPT_PACK:
        pack = prompt_packs.parse_pack(raw)
        return pack["items"], pack["manifest"]["content_sha256"]
    if entry.kind == hub_registry.KIND_SCENARIO_PACK:
        pack = scenario_packs.parse_pack(raw)
        return pack["scenario"], pack["manifest"]["content_sha256"]
    if entry.kind == hub_registry.KIND_PRESET_BUNDLE:
        try:
            data = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise preset_bundles.BundleError(
                "pack file is not valid JSON: " + str(exc)) from None
        bundle, report = preset_bundles.parse_share(data)
        verified = ""
        if report.get("checksum_verified"):
            manifest = data.get("manifest") if isinstance(data, dict) else None
            if isinstance(manifest, dict):
                candidate = manifest.get("content_sha256")
                if isinstance(candidate, str):
                    verified = candidate
        return bundle, verified
    raise hub_registry.HubError("unknown hub kind: " + entry.kind)


def _empty_shape() -> dict:
    return {
        "object_count": 0, "array_count": 0, "string_count": 0,
        "number_count": 0, "boolean_count": 0, "null_count": 0,
        "node_count": 0, "key_count": 0, "max_depth": 0,
    }


def _shape_stats(payload) -> dict:
    """The structural measure of one verified payload,
    under the walk law: every node counted once by
    type, every dict key counted once as structure,
    the payload root at depth 1, and a member under a
    content_sha256 key excluded whole."""
    stats = _empty_shape()

    def walk(node, depth: int) -> None:
        if depth > stats["max_depth"]:
            stats["max_depth"] = depth
        stats["node_count"] += 1
        if isinstance(node, dict):
            stats["object_count"] += 1
            for key, value in node.items():
                if key == "content_sha256":
                    continue
                stats["key_count"] += 1
                walk(value, depth + 1)
        elif isinstance(node, list):
            stats["array_count"] += 1
            for item in node:
                walk(item, depth + 1)
        elif isinstance(node, bool):
            stats["boolean_count"] += 1
        elif isinstance(node, str):
            stats["string_count"] += 1
        elif isinstance(node, (int, float)):
            stats["number_count"] += 1
        else:
            stats["null_count"] += 1

    walk(payload, 1)
    return stats


def content_shape_census_document(entries: list[HubEntry]) -> dict:
    """The hub content-shape census for one owner's
    entries.

    ``entries`` is the owner's own entry list (the
    router hands over HubStore.list_for_owner for the
    caller; a foreign owner's entries are never in
    it). The P-187 list document is composed verbatim
    and embedded whole; each entry is then parsed
    through its own layer's verified parse road and
    its verified payload walked under the shape law.
    Always a document, never an error for a bad pack:
    a pack the owning road refuses is an invalid row.
    """
    list_doc = hub_registry.list_document(entries)
    rows = []
    by_outcome = {outcome: 0 for outcome in sorted(OUTCOMES)}
    by_kind_shape = {
        kind: {"entries": 0, "parsed": 0, "objects": 0,
               "arrays": 0, "strings": 0, "numbers": 0,
               "booleans": 0, "nulls": 0, "nodes": 0,
               "keys": 0, "max_depth": 0}
        for kind in sorted(hub_registry.HUB_KINDS)}
    totals = _empty_shape()
    deepest = None
    for entry in entries:
        row = entry.to_dict()
        state = hub_registry.locator_state(entry.locator)
        row["locator_state"] = state
        row["outcome"] = OUTCOME_UNAVAILABLE
        row["verified_content_sha256"] = ""
        shape = _empty_shape()
        row["error"] = ""
        kind_axis = by_kind_shape.get(entry.kind)
        if kind_axis is not None:
            kind_axis["entries"] += 1
        if state == hub_registry.LOCATOR_READY:
            try:
                size = Path(entry.locator).stat().st_size
            except OSError as exc:
                row["outcome"] = OUTCOME_INVALID
                row["error"] = "locator could not be read: " + str(exc)
            else:
                if size > MAX_BROWSE_BYTES:
                    row["outcome"] = OUTCOME_INVALID
                    row["error"] = "pack file too large to shape-census"
                else:
                    try:
                        raw = Path(entry.locator).read_bytes()
                    except OSError as exc:
                        row["outcome"] = OUTCOME_INVALID
                        row["error"] = (
                            "locator could not be read: " + str(exc))
                    else:
                        try:
                            payload, verified = _parse_payload(entry, raw)
                        except (ValueError, TypeError) as exc:
                            row["outcome"] = OUTCOME_INVALID
                            row["error"] = str(exc)
                        else:
                            shape = _shape_stats(payload)
                            row["outcome"] = OUTCOME_PARSED
                            row["verified_content_sha256"] = verified
        row.update(shape)
        rows.append(row)
        by_outcome[row["outcome"]] += 1
        if row["outcome"] == OUTCOME_PARSED:
            for field in totals:
                if field != "max_depth":
                    totals[field] += shape[field]
            if shape["max_depth"] > totals["max_depth"]:
                totals["max_depth"] = shape["max_depth"]
            if kind_axis is not None:
                kind_axis["parsed"] += 1
                kind_axis["objects"] += shape["object_count"]
                kind_axis["arrays"] += shape["array_count"]
                kind_axis["strings"] += shape["string_count"]
                kind_axis["numbers"] += shape["number_count"]
                kind_axis["booleans"] += shape["boolean_count"]
                kind_axis["nulls"] += shape["null_count"]
                kind_axis["nodes"] += shape["node_count"]
                kind_axis["keys"] += shape["key_count"]
                if shape["max_depth"] > kind_axis["max_depth"]:
                    kind_axis["max_depth"] = shape["max_depth"]
            if (deepest is None
                    or shape["max_depth"] > deepest["max_depth"]):
                deepest = {
                    "id": row["id"], "title": row["title"],
                    "kind": row["kind"],
                    "max_depth": shape["max_depth"],
                    "node_count": shape["node_count"],
                }
    total = len(rows)
    parsed = by_outcome[OUTCOME_PARSED]
    if total == 0:
        census_state = SHAPE_CENSUS_STATE_NO_ENTRIES
    elif parsed == 0:
        census_state = SHAPE_CENSUS_STATE_NO_SHAPE
    elif parsed == total:
        census_state = SHAPE_CENSUS_STATE_ALL_SHAPE
    else:
        census_state = SHAPE_CENSUS_STATE_SOME_SHAPE
    return {
        "schema": CONTENT_SHAPE_CENSUS_SCHEMA,
        "census_state": census_state,
        "count": total,
        "entries_considered": total,
        "parsed_count": parsed,
        "coverage_complete": parsed == total,
        "list": list_doc,
        "entries": rows,
        "by_outcome": by_outcome,
        "by_kind_shape": by_kind_shape,
        "by_node_type": {
            "array": totals["array_count"],
            "boolean": totals["boolean_count"],
            "null": totals["null_count"],
            "number": totals["number_count"],
            "object": totals["object_count"],
            "string": totals["string_count"],
        },
        "total_objects": totals["object_count"],
        "total_arrays": totals["array_count"],
        "total_strings": totals["string_count"],
        "total_numbers": totals["number_count"],
        "total_booleans": totals["boolean_count"],
        "total_nulls": totals["null_count"],
        "total_nodes": totals["node_count"],
        "total_keys": totals["key_count"],
        "max_depth": totals["max_depth"],
        "deepest_entry": deepest,
        "max_browse_bytes": MAX_BROWSE_BYTES,
        "kind_formats": dict(hub_registry.KIND_FORMATS),
        "notes": list(NOTES),
    }
