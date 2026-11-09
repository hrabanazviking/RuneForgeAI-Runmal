"""Hub breadth census (P-198, Part XII - DERIVED).

The roadmap gives Part XII one line only ("The Hub,
Sovereign Shape", P-187..P-202); this slice's scope is
derived from Runmal's own in-tree record - see
docs/HUB_BREADTH_CENSUS_2026-11-09.md and
hidden_files/P198_SCOUT.md / P198_DESIGN.md.

What the derivation found: P-196's content-shape census
measures the DEPTH axis of verified payloads - node
counts by type, key totals and max_depth - and discards
how WIDE any single container spreads. No banked hub
document carries a single container-size field: a
payload holding one array of five hundred items and a
payload holding five hundred arrays of one item sit in
the same P-196 totals class, yet their breadth is
opposite. P-187 counts kinds and locator states, P-189
counts browse verdicts and checksum claims, P-193
counts payload string volume, P-194 aggregates one
query's answer, P-195 groups entries by verified
identity and P-197 measures file bytes as stored. The
width of the widest container, the per-container size
distribution and the summed breadth of an estate exist
in no banked document - they are discarded by every
banked walk. This module is the breadth census, in the
P-193 shape: a pure aggregate composing the owning
surfaces verbatim, classified under a closed law,
counts summed from the composed reads' own values.

- Composition, verbatim roads only - never a second
  parser. Each entry is judged under P-187's locator
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
- The breadth law: every CONTAINER in the verified
  payload (every dict and every list) has a WIDTH -
  its immediate child count. A dict's width is its
  counted keys: a member under a content_sha256 key
  is excluded WHOLE, exactly as P-196 excludes it -
  it adds nothing to the width and its value subtree
  is never walked (the pack's identity is not its
  breadth). A list's width is its length. Per payload
  the census carries the container count, the summed
  breadth (the total of all widths), the widest
  container width, the widest object width and the
  widest array width (each 0 when no container of that
  kind exists). Scalars are not containers and
  contribute nothing. The payload root counts as a
  container when it is a dict or a list.
- The bucket law is closed (BREADTH_BUCKETS) over the
  containers of parsed rows only: empty (width 0),
  narrow (1 to 2), medium (3 to 5), wide (6 to 10),
  vast (11 and over); a width exactly on an edge
  belongs to the higher bucket.
- DISTINCTNESS, stated plainly: P-196's object and
  array COUNTS agree with this census's container
  count on the same estate by construction - the same
  containers, counted there and measured here - and
  that agreement is expected, not the new fact (as
  P-196's string count agrees with P-193's). The new
  facts are the widths themselves: per-container
  sizes, the widest container, the bucket distribution
  and the summed breadth, none of which any banked
  document carries. This census carries no P-196
  depth or node-type field, no P-193 volume field, no
  P-197 byte field, no P-189 verdict, no P-194 query
  axis and no P-195 grouping: verified checksums ride
  per row as the parse roads' own facts, as at P-193,
  and are never compared across rows here.
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
  (BREADTH_CENSUS_STATES), judged on the parsed axis:
  no_entries / no_breadth / some_breadth / all_breadth.

Honest boundaries, and the cost stated plainly: a
breadth census parses every ready entry, so it READS
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

BREADTH_CENSUS_SCHEMA = "runmal-p198-hub-breadth-census-v1"

MAX_BROWSE_BYTES = hub_browse.MAX_BROWSE_BYTES  # P-188's bound: one law

# P-193's outcomes law, imported: one law, never forked.
OUTCOME_PARSED = hub_content_census.OUTCOME_PARSED
OUTCOME_UNAVAILABLE = hub_content_census.OUTCOME_UNAVAILABLE
OUTCOME_INVALID = hub_content_census.OUTCOME_INVALID
OUTCOMES = hub_content_census.OUTCOMES

BUCKET_EMPTY = "empty"
BUCKET_NARROW = "narrow"
BUCKET_MEDIUM = "medium"
BUCKET_WIDE = "wide"
BUCKET_VAST = "vast"
BREADTH_BUCKETS = frozenset({
    BUCKET_EMPTY, BUCKET_NARROW, BUCKET_MEDIUM,
    BUCKET_WIDE, BUCKET_VAST,
})

# Bucket edges in container width: a width exactly on
# an edge belongs to the HIGHER bucket.
BUCKET_EDGES = (1, 3, 6, 11)

BREADTH_CENSUS_STATE_NO_ENTRIES = "no_entries"
BREADTH_CENSUS_STATE_NO_BREADTH = "no_breadth"
BREADTH_CENSUS_STATE_SOME_BREADTH = "some_breadth"
BREADTH_CENSUS_STATE_ALL_BREADTH = "all_breadth"
BREADTH_CENSUS_STATES = frozenset({
    BREADTH_CENSUS_STATE_NO_ENTRIES,
    BREADTH_CENSUS_STATE_NO_BREADTH,
    BREADTH_CENSUS_STATE_SOME_BREADTH,
    BREADTH_CENSUS_STATE_ALL_BREADTH,
})

NOTES = (
    "Pure read, owner scoped: only the caller's own "
    "entries are censused; this census stores, "
    "registers, removes, imports, installs, copies "
    "and writes nothing.",
    "Distinctness: P-189's census counts browse "
    "verdicts and checksum claims, P-193's counts "
    "verified payload string VOLUME, P-194's counts "
    "one query's answer, P-195's groups entries by "
    "verified identity, P-196's counts payload node "
    "shape and depth and P-197's measures file bytes; "
    "this census measures the verified payloads' "
    "container BREADTH - how wide each object and "
    "array spreads. Its container count necessarily "
    "equals P-196's object plus array counts on the "
    "same estate (the same containers, counted there "
    "and measured here), and that agreement is "
    "expected and stated; the widths, the widest "
    "container, the bucket distribution and the "
    "summed breadth are the new facts.",
    "Cost law: a breadth census reads and verifies "
    "every ready pack in the estate, each through its "
    "own layer's verified parse road and each under "
    "the browse size bound (max_browse_bytes in this "
    "document) - the price of measuring contents the "
    "registry does not hold.",
    "The walk measures every container in the "
    "verified payload exactly once: a dict's width "
    "is its counted keys and a list's width is its "
    "length. Key names and values are never "
    "returned: counts only, anywhere in this "
    "document. A member under a content_sha256 key "
    "is the pack's identity, not its breadth, and "
    "is excluded whole - it adds nothing to its "
    "container's width and its subtree is never "
    "walked. The pack envelope (manifest and "
    "provenance) lives outside the payload member "
    "and is never walked.",
    "No silent omission: every entry was parsed or "
    "is named by its row's outcome - unavailable (its "
    "locator is not ready) or invalid (its own "
    "layer's road refused it, it could not be read, "
    "or it exceeds the size bound) - under P-193's "
    "outcomes law, imported whole. "
    "coverage_complete is false whenever any entry "
    "was not parsed, and count always equals parsed "
    "plus unavailable plus invalid.",
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


def container_bucket(width: int) -> str:
    """The closed bucket law for one container width:
    a width exactly on an edge belongs to the higher
    bucket."""
    if width < BUCKET_EDGES[0]:
        return BUCKET_EMPTY
    if width < BUCKET_EDGES[1]:
        return BUCKET_NARROW
    if width < BUCKET_EDGES[2]:
        return BUCKET_MEDIUM
    if width < BUCKET_EDGES[3]:
        return BUCKET_WIDE
    return BUCKET_VAST


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


def _empty_breadth() -> dict:
    return {
        "breadth_container_count": 0, "breadth_total": 0,
        "widest_container_width": 0, "widest_object_width": 0,
        "widest_array_width": 0,
    }


def _breadth_stats(payload):
    """The breadth measure of one verified payload,
    under the breadth law. Returns (stats, widths):
    stats carries the per-payload breadth fields and
    widths lists every container width exactly once
    (the bucket law's input)."""
    stats = _empty_breadth()
    widths: list[int] = []

    def walk(node) -> None:
        if isinstance(node, dict):
            counted = [
                value for key, value in node.items()
                if key != "content_sha256"]
            width = len(counted)
            widths.append(width)
            stats["breadth_container_count"] += 1
            stats["breadth_total"] += width
            if width > stats["widest_container_width"]:
                stats["widest_container_width"] = width
            if width > stats["widest_object_width"]:
                stats["widest_object_width"] = width
            for value in counted:
                walk(value)
        elif isinstance(node, list):
            width = len(node)
            widths.append(width)
            stats["breadth_container_count"] += 1
            stats["breadth_total"] += width
            if width > stats["widest_container_width"]:
                stats["widest_container_width"] = width
            if width > stats["widest_array_width"]:
                stats["widest_array_width"] = width
            for item in node:
                walk(item)

    walk(payload)
    return stats, widths


def breadth_census_document(entries: list[HubEntry]) -> dict:
    """The hub breadth census for one owner's entries.

    ``entries`` is the owner's own entry list (the
    router hands over HubStore.list_for_owner for the
    caller; a foreign owner's entries are never in
    it). The P-187 list document is composed verbatim
    and embedded whole; each entry is then parsed
    through its own layer's verified parse road and
    its verified payload walked under the breadth law.
    Always a document, never an error for a bad pack:
    a pack the owning road refuses is an invalid row.
    """
    list_doc = hub_registry.list_document(entries)
    rows = []
    by_outcome = {outcome: 0 for outcome in sorted(OUTCOMES)}
    by_kind_breadth = {
        kind: {"entries": 0, "parsed": 0, "containers": 0,
               "breadth": 0, "widest_container_width": 0}
        for kind in sorted(hub_registry.HUB_KINDS)}
    by_breadth_bucket = {
        bucket: 0 for bucket in sorted(BREADTH_BUCKETS)}
    total_containers = 0
    total_breadth = 0
    estate_widest = 0
    widest = None
    for entry in entries:
        row = entry.to_dict()
        state = hub_registry.locator_state(entry.locator)
        row["locator_state"] = state
        row["outcome"] = OUTCOME_UNAVAILABLE
        row["verified_content_sha256"] = ""
        stats = _empty_breadth()
        widths: list[int] = []
        row["error"] = ""
        kind_axis = by_kind_breadth.get(entry.kind)
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
                    row["error"] = "pack file too large to breadth-census"
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
                            stats, widths = _breadth_stats(payload)
                            row["outcome"] = OUTCOME_PARSED
                            row["verified_content_sha256"] = verified
        row.update(stats)
        rows.append(row)
        by_outcome[row["outcome"]] += 1
        if row["outcome"] == OUTCOME_PARSED:
            total_containers += stats["breadth_container_count"]
            total_breadth += stats["breadth_total"]
            for width in widths:
                by_breadth_bucket[container_bucket(width)] += 1
            if stats["widest_container_width"] > estate_widest:
                estate_widest = stats["widest_container_width"]
            if kind_axis is not None:
                kind_axis["parsed"] += 1
                kind_axis["containers"] += (
                    stats["breadth_container_count"])
                kind_axis["breadth"] += stats["breadth_total"]
                if (stats["widest_container_width"]
                        > kind_axis["widest_container_width"]):
                    kind_axis["widest_container_width"] = (
                        stats["widest_container_width"])
            if (widest is None or stats["widest_container_width"]
                    > widest["widest_container_width"]):
                widest = {
                    "id": row["id"], "title": row["title"],
                    "kind": row["kind"],
                    "widest_container_width": (
                        stats["widest_container_width"]),
                    "breadth_container_count": (
                        stats["breadth_container_count"]),
                }
    total = len(rows)
    parsed = by_outcome[OUTCOME_PARSED]
    if total == 0:
        census_state = BREADTH_CENSUS_STATE_NO_ENTRIES
    elif parsed == 0:
        census_state = BREADTH_CENSUS_STATE_NO_BREADTH
    elif parsed == total:
        census_state = BREADTH_CENSUS_STATE_ALL_BREADTH
    else:
        census_state = BREADTH_CENSUS_STATE_SOME_BREADTH
    return {
        "schema": BREADTH_CENSUS_SCHEMA,
        "census_state": census_state,
        "count": total,
        "entries_considered": total,
        "parsed_count": parsed,
        "coverage_complete": parsed == total,
        "list": list_doc,
        "entries": rows,
        "by_outcome": by_outcome,
        "by_kind_breadth": by_kind_breadth,
        "by_breadth_bucket": by_breadth_bucket,
        "total_containers": total_containers,
        "total_breadth": total_breadth,
        "widest_container_width": estate_widest,
        "widest_entry": widest,
        "max_browse_bytes": MAX_BROWSE_BYTES,
        "kind_formats": dict(hub_registry.KIND_FORMATS),
        "notes": list(NOTES),
    }
