"""Hub schema census (P-200, Part XII - DERIVED).

The roadmap gives Part XII one line only ("The Hub,
Sovereign Shape", P-187..P-202); this slice's scope is
derived from Runmal's own in-tree record - see
docs/HUB_SCHEMA_CENSUS_2026-11-09.md and
hidden_files/P200_SCOUT.md / P200_DESIGN.md.

What the derivation found: identity in the banked hub
estate is measured at whole-pack grain (P-195 groups
entries by verified content checksum) and at value
grain (P-199 compares string values for exact
identity), while structure is measured as COUNTS only
- P-196 counts every payload node and every dict key
and P-198 measures every container's width, and both
discard the one fact that makes an object a SCHEMA:
which keys it holds together. Two payloads whose
objects share no key-set at all and two payloads built
from one repeated record shape read identically at
P-196 whenever their node and key totals match, and no
banked document states how many DISTINCT object
shapes an estate's verified payloads use, how many
repeat inside one pack or across packs, or how many
are shared between entries - nor can it be derived,
because no banked document carries a key name or a
key-set (P-196 returns counts only, by law), so shape
identity exists only at walk time. A hundred lorebook
entries with different text are ONE shape. This module
is the schema census, in the P-193 shape: a pure
aggregate composing the owning surfaces verbatim,
classified under a closed law, counts summed from the
composed reads' own values.

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
- The walk law is P-196's shape walk carried to
  identity: every DICT node in the verified payload
  is one object occurrence; a member under a
  content_sha256 key is excluded WHOLE - it is not a
  counted key of its parent object and its subtree
  is never walked (the pack's identity is not its
  schema, P-196's pair exclusion carried verbatim);
  lists and scalars are walked through and are never
  themselves shapes; the pack envelope lives outside
  the payload member and is never walked.
- The signature law: an object's shape is the SET of
  its counted keys - unordered (JSON object member
  order is not structure), exact names, no folding.
  The empty object has the empty signature, a shape
  like any other, and counts. Comparison is by sha256
  digest of the canonical encoding (the JSON array of
  the sorted key list), computed in memory only:
  digests are retained solely while counting and are
  NEVER carried in the document, and neither is any
  key name or per-key frequency - a digest of a small
  key-set is a dictionary target for the schema it
  names, so carrying one would leak what the
  no-content and no-key-name laws forbid returning.
- DISTINCTNESS, stated plainly: this census carries
  no P-196 count field beyond the object occurrence
  count itself (no key is ever counted as a quantity
  here, no node total, no depth; the occurrence count
  necessarily equals P-196's object_count on the same
  estate - the same objects, counted for identity
  rather than tallied - and that agreement is
  expected, not the new fact, as P-199's occurrence
  count was to P-193's). The new facts are the
  identity axes: distinct, repeated, shared and
  extra-shape counts. This census never groups
  entries and never compares verified checksums
  across rows (P-195's ground): a P-195-unique pair
  of packs built on one record shape is stated here
  as sharing shapes, and one pack's internal shape
  repetition is stated with no P-195 signal at all.
  It never compares a string value (P-199's ground:
  one pack can be all-distinct in values and
  one-shape here, and the reverse reads oppositely).
  It carries no P-189 verdict, no P-193 volume field,
  no P-194 query axis, no P-197 byte field and no
  P-198 width field.
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
  Shared counts are computed over parsed entries
  only: a shape in one parsed entry and one invalid
  entry is not shared, because the invalid entry's
  payload was never verified or walked.
- NO content or structure detail is retained or
  returned: this census carries counts, entry data
  and verified checksums only - never a key name,
  never a per-key frequency, never a signature
  digest, never a value, never an excerpt and never
  a payload field, anywhere in the document (the
  P-183 law, extended to key-sets as P-199 extended
  it to values).
- The estate is classified under a closed census law
  (SCHEMA_CENSUS_STATES), judged on the parsed axis:
  no_entries / no_schema / some_schema / all_schema.

Honest boundaries, and the cost stated plainly: a
schema census parses every ready entry, so it READS
pack files - each through its own layer's verified
parse road, under the 16 MiB bound, so an oversize,
corrupt or wrong-kind pack is an invalid row, never a
census failure. The census writes nothing, imports
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

import hashlib
import json
from collections import Counter
from pathlib import Path

from runmal.hub import browse as hub_browse
from runmal.hub import content_census as hub_content_census
from runmal.hub import registry as hub_registry
from runmal.hub.registry import HubEntry
from runmal.lorebooks import packs as lorebook_packs
from runmal.presets import bundles as preset_bundles
from runmal.presets import packs as prompt_packs
from runmal.scenarios import packs as scenario_packs

SCHEMA_CENSUS_SCHEMA = "runmal-p200-hub-schema-census-v1"

MAX_BROWSE_BYTES = hub_browse.MAX_BROWSE_BYTES  # P-188's bound: one law

# P-193's outcomes law, imported: one law, never forked.
OUTCOME_PARSED = hub_content_census.OUTCOME_PARSED
OUTCOME_UNAVAILABLE = hub_content_census.OUTCOME_UNAVAILABLE
OUTCOME_INVALID = hub_content_census.OUTCOME_INVALID
OUTCOMES = hub_content_census.OUTCOMES

SCHEMA_CENSUS_STATE_NO_ENTRIES = "no_entries"
SCHEMA_CENSUS_STATE_NO_SCHEMA = "no_schema"
SCHEMA_CENSUS_STATE_SOME_SCHEMA = "some_schema"
SCHEMA_CENSUS_STATE_ALL_SCHEMA = "all_schema"
SCHEMA_CENSUS_STATES = frozenset({
    SCHEMA_CENSUS_STATE_NO_ENTRIES,
    SCHEMA_CENSUS_STATE_NO_SCHEMA,
    SCHEMA_CENSUS_STATE_SOME_SCHEMA,
    SCHEMA_CENSUS_STATE_ALL_SCHEMA,
})

NOTES = (
    "Pure read, owner scoped: only the caller's own "
    "entries are censused; this census stores, "
    "registers, removes, imports, installs, copies "
    "and writes nothing.",
    "Distinctness: P-189's census counts browse "
    "verdicts and checksum claims, P-193's counts "
    "verified payload string VOLUME (values and "
    "characters), P-194's counts one query's answer, "
    "P-195's groups whole packs by verified checksum, "
    "P-196's counts payload node shape, P-197's "
    "measures file bytes, P-198's measures container "
    "widths and P-199's measures string-value "
    "identity; this census measures the IDENTITY of "
    "the verified payloads' OBJECT SHAPES - how many "
    "distinct key-sets their objects use, how many "
    "repeat and how many are shared across entries. "
    "Its object count necessarily equals P-196's "
    "object count on the same estate (the same "
    "objects, counted for identity, not tallied), "
    "and that agreement is expected and stated; no "
    "key is ever counted as a quantity here.",
    "Cost law: a schema census reads and verifies "
    "every ready pack in the estate, each through its "
    "own layer's verified parse road and each under "
    "the browse size bound (max_browse_bytes in this "
    "document) - the price of measuring contents the "
    "registry does not hold.",
    "Signature law: an object's shape is the set of "
    "its counted keys - unordered, exact, unfolded. "
    "Shapes are compared by digest in memory only; "
    "neither a key name, nor a per-key frequency, nor "
    "a digest of a key-set appears anywhere in this "
    "document - counts only. A member under a "
    "content_sha256 key is the pack's identity, not "
    "its schema, and is excluded whole - it is not a "
    "counted key of its parent object and its "
    "subtree is never walked. The pack envelope "
    "(manifest and provenance) lives outside the "
    "payload member and is never walked.",
    "No silent omission: every entry was parsed or "
    "is named by its row's outcome - unavailable (its "
    "locator is not ready) or invalid (its own layer's "
    "road refused it, it could not be read, or it "
    "exceeds the size bound) - under P-193's outcomes "
    "law, imported whole. coverage_complete is false "
    "whenever any entry was not parsed, and count "
    "always equals parsed plus unavailable plus "
    "invalid. Shared counts are computed over parsed "
    "entries only.",
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


def _signature(keys) -> str:
    """The in-memory comparison digest of one object's
    key-set: sha256 of the canonical encoding (the
    JSON array of the sorted key list, UTF-8). Never
    carried in any document: a digest of a small
    key-set is a dictionary target for the schema it
    names."""
    canonical = json.dumps(
        sorted(keys), ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _shape_stats(payload) -> tuple[int, Counter]:
    """(object occurrence count, per-signature
    occurrence counts) for one verified payload, under
    the walk and signature laws. Every DICT node is
    one object occurrence; a content_sha256 member is
    excluded whole - neither a counted key of its
    parent nor a walked subtree. Only digests are
    counted; key names are never retained beyond the
    walk of the object that holds them."""
    counts: Counter = Counter()
    total = 0

    def walk(node) -> None:
        nonlocal total
        if isinstance(node, dict):
            keys = [key for key in node if key != "content_sha256"]
            counts[_signature(keys)] += 1
            total += 1
            for key in keys:
                walk(node[key])
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(payload)
    return total, counts


def schema_census_document(entries: list[HubEntry]) -> dict:
    """The hub schema census for one owner's entries.

    ``entries`` is the owner's own entry list (the
    router hands over HubStore.list_for_owner for the
    caller; a foreign owner's entries are never in
    it). The P-187 list document is composed verbatim
    and embedded whole; each entry is then parsed
    through its own layer's verified parse road and
    its verified payload walked under P-196's walk
    law, its objects compared for exact key-set
    identity by in-memory digest only. Always a
    document, never an error for a bad pack: a pack
    the owning road refuses is an invalid row.
    """
    list_doc = hub_registry.list_document(entries)
    rows = []
    row_counters: list[Counter | None] = []
    by_outcome = {outcome: 0 for outcome in sorted(OUTCOMES)}
    by_kind_schema = {
        kind: {"entries": 0, "parsed": 0, "objects": 0,
               "distinct_shapes": 0, "extra_shapes": 0}
        for kind in sorted(hub_registry.HUB_KINDS)}
    kind_digests: dict[str, set] = {
        kind: set() for kind in hub_registry.HUB_KINDS}
    estate_counts: Counter = Counter()
    estate_entries: dict[str, set] = {}
    total_objects = 0
    largest = None
    for index, entry in enumerate(entries):
        row = entry.to_dict()
        state = hub_registry.locator_state(entry.locator)
        row["locator_state"] = state
        row["outcome"] = OUTCOME_UNAVAILABLE
        row["verified_content_sha256"] = ""
        row["object_count"] = 0
        row["distinct_shape_count"] = 0
        row["repeated_shape_count"] = 0
        row["extra_shape_count"] = 0
        row["shared_shape_count"] = 0
        row["error"] = ""
        counter: Counter | None = None
        kind_axis = by_kind_schema.get(entry.kind)
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
                    row["error"] = "pack file too large to schema-census"
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
                            occurrences, counter = _shape_stats(payload)
                            row["outcome"] = OUTCOME_PARSED
                            row["verified_content_sha256"] = verified
                            row["object_count"] = occurrences
                            row["distinct_shape_count"] = len(counter)
                            row["repeated_shape_count"] = sum(
                                1 for n in counter.values() if n >= 2)
                            row["extra_shape_count"] = (
                                occurrences - len(counter))
        rows.append(row)
        row_counters.append(counter)
        by_outcome[row["outcome"]] += 1
        if row["outcome"] == OUTCOME_PARSED and counter is not None:
            total_objects += row["object_count"]
            estate_counts.update(counter)
            for digest in counter:
                estate_entries.setdefault(digest, set()).add(index)
            if kind_axis is not None:
                kind_axis["parsed"] += 1
                kind_axis["objects"] += row["object_count"]
                kind_digests[entry.kind].update(counter)
            if (largest is None
                    or row["distinct_shape_count"]
                    > largest["distinct_shape_count"]):
                largest = {
                    "id": row["id"], "title": row["title"],
                    "kind": row["kind"],
                    "distinct_shape_count": row["distinct_shape_count"],
                    "object_count": row["object_count"],
                }
    # Second pass: a row's shared shapes are its distinct
    # shapes that also occur in at least one OTHER parsed
    # entry (parsed entries only, by construction above).
    for index, row in enumerate(rows):
        counter = row_counters[index]
        if row["outcome"] == OUTCOME_PARSED and counter is not None:
            row["shared_shape_count"] = sum(
                1 for digest in counter
                if len(estate_entries.get(digest, ())) >= 2)
    for kind, axis in by_kind_schema.items():
        axis["distinct_shapes"] = len(kind_digests[kind])
        axis["extra_shapes"] = (
            axis["objects"] - axis["distinct_shapes"])
    total_distinct_shapes = len(estate_counts)
    total_repeated_shapes = sum(
        1 for n in estate_counts.values() if n >= 2)
    total_shared_shapes = sum(
        1 for owners in estate_entries.values() if len(owners) >= 2)
    total = len(rows)
    parsed = by_outcome[OUTCOME_PARSED]
    if total == 0:
        census_state = SCHEMA_CENSUS_STATE_NO_ENTRIES
    elif parsed == 0:
        census_state = SCHEMA_CENSUS_STATE_NO_SCHEMA
    elif parsed == total:
        census_state = SCHEMA_CENSUS_STATE_ALL_SCHEMA
    else:
        census_state = SCHEMA_CENSUS_STATE_SOME_SCHEMA
    return {
        "schema": SCHEMA_CENSUS_SCHEMA,
        "census_state": census_state,
        "count": total,
        "entries_considered": total,
        "parsed_count": parsed,
        "coverage_complete": parsed == total,
        "list": list_doc,
        "entries": rows,
        "by_outcome": by_outcome,
        "by_kind_schema": by_kind_schema,
        "total_objects": total_objects,
        "total_distinct_shapes": total_distinct_shapes,
        "total_repeated_shapes": total_repeated_shapes,
        "total_shared_shapes": total_shared_shapes,
        "total_extra_shapes": total_objects - total_distinct_shapes,
        "largest_schema_entry": largest,
        "max_browse_bytes": MAX_BROWSE_BYTES,
        "kind_formats": dict(hub_registry.KIND_FORMATS),
        "notes": list(NOTES),
    }
