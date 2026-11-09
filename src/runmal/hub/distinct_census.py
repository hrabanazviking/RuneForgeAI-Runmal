"""Hub distinct-content census (P-199, Part XII - DERIVED).

The roadmap gives Part XII one line only ("The Hub,
Sovereign Shape", P-187..P-202); this slice's scope is
derived from Runmal's own in-tree record - see
docs/HUB_DISTINCT_CONTENT_CENSUS_2026-11-09.md and
hidden_files/P199_SCOUT.md / P199_DESIGN.md.

What the derivation found: every banked identity or
volume fact about verified payload text sits at one of
two grains, and the grain between them is stated
nowhere. P-195 groups entries by verified content
checksum - identity at WHOLE-PACK grain, exact only -
so two versions of one pack differing in a single
entry read there as simply unique and their overlap is
nowhere stated. P-193 counts string-value OCCURRENCES
and their characters - a value occurring forty times
and forty values occurring once read identically
there. No banked document states how many DISTINCT
string values an estate holds, how many repeat inside
one pack or across packs, or how many are shared
between entries - and none can be derived from, because
no banked document carries values. This module is the
distinct-content census, in the P-193 shape: a pure
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
- The walk law is P-191's string walk, carried
  verbatim as P-193 carries it: every STRING VALUE in
  the verified payload (dict values and list items)
  is an occurrence; dict keys are structure, never
  values; a value under a content_sha256 key is the
  pack's identity, not its content, and its subtree
  is never walked; the pack envelope lives outside
  the payload member and is never walked.
- The identity law: two occurrences are the same
  value iff the strings are EXACTLY equal - no case
  folding, no whitespace normalisation (the checksum
  law's exactness transposed to values; the search
  laws' folding is a search law, not an identity
  law). The empty string is a value like any other
  and counts. Comparison is by sha256 digest of the
  value's UTF-8 encoding, computed in memory only:
  digests are retained solely while counting and are
  NEVER carried in the document - a digest of a
  short string is a dictionary target, so carrying
  one would leak what the no-content law forbids
  returning.
- DISTINCTNESS, stated plainly: this census carries
  no P-193 volume field beyond the occurrence count
  itself (no character is ever counted; the
  occurrence count necessarily equals P-193's
  string-value count on the same estate - the same
  occurrences, counted for identity rather than
  measured for length - and that agreement is
  expected, not the new fact, as P-193's parsed
  counts agree with P-189's inspected counts). The
  new facts are the identity axes: distinct,
  repeated, shared and extra-copy counts. This
  census never groups entries and never compares
  verified checksums across rows (P-195's ground):
  a P-195-unique pair of packs sharing most of
  their text is stated here as sharing values, and
  one pack's internal repetition is stated with no
  P-195 signal at all. It carries no P-189 verdict,
  no P-194 query axis, no P-196 shape field, no
  P-197 byte field and no P-198 width field.
- No silent omission (the P-191 law): every entry
  ends parsed, or named by its row's outcome -
  unavailable (the locator is not ready; no read
  attempted) or invalid (unreadable at read time,
  over the size bound, not valid JSON on the bundle
  road, or the owning layer's own parse road refused
  it, its refusal carried verbatim) - under P-193's
  OUTCOMES law, imported (one law, never forked),
  and coverage_complete carries the truth as data:
  any non-parsed entry makes it false, and count
  always equals parsed plus unavailable plus invalid.
  Shared counts are computed over parsed entries
  only: a value in one parsed entry and one invalid
  entry is not shared, because the invalid entry's
  values were never verified or walked.
- NO content is retained or returned: this census
  carries counts, entry data and verified checksums
  only - never a value, never a value digest, never
  an excerpt and never a payload field, anywhere in
  the document (the P-183 law, extended to digests).
- The estate is classified under a closed census law
  (DISTINCT_CENSUS_STATES), judged on the parsed
  axis: no_entries / no_distinct / some_distinct /
  all_distinct.

Honest boundaries, and the cost stated plainly: a
distinct census parses every ready entry, so it READS
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

DISTINCT_CENSUS_SCHEMA = "runmal-p199-hub-distinct-content-census-v1"

MAX_BROWSE_BYTES = hub_browse.MAX_BROWSE_BYTES  # P-188's bound: one law

# P-193's outcomes law, imported: one law, never forked.
OUTCOME_PARSED = hub_content_census.OUTCOME_PARSED
OUTCOME_UNAVAILABLE = hub_content_census.OUTCOME_UNAVAILABLE
OUTCOME_INVALID = hub_content_census.OUTCOME_INVALID
OUTCOMES = hub_content_census.OUTCOMES

DISTINCT_CENSUS_STATE_NO_ENTRIES = "no_entries"
DISTINCT_CENSUS_STATE_NO_DISTINCT = "no_distinct"
DISTINCT_CENSUS_STATE_SOME_DISTINCT = "some_distinct"
DISTINCT_CENSUS_STATE_ALL_DISTINCT = "all_distinct"
DISTINCT_CENSUS_STATES = frozenset({
    DISTINCT_CENSUS_STATE_NO_ENTRIES,
    DISTINCT_CENSUS_STATE_NO_DISTINCT,
    DISTINCT_CENSUS_STATE_SOME_DISTINCT,
    DISTINCT_CENSUS_STATE_ALL_DISTINCT,
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
    "measures file bytes and P-198's measures "
    "container widths; this census measures the "
    "IDENTITY of the verified payloads' string "
    "values - how many are distinct, how many repeat "
    "and how many are shared across entries. Its "
    "occurrence count necessarily equals P-193's "
    "string-value count on the same estate (the same "
    "occurrences, counted for identity, not measured "
    "for length), and that agreement is expected and "
    "stated; no character is ever counted here.",
    "Cost law: a distinct census reads and verifies "
    "every ready pack in the estate, each through its "
    "own layer's verified parse road and each under "
    "the browse size bound (max_browse_bytes in this "
    "document) - the price of measuring contents the "
    "registry does not hold.",
    "Identity law: two occurrences are the same value "
    "only when the strings are exactly equal - no "
    "case folding and no normalisation. Values are "
    "compared by digest in memory only; neither a "
    "value nor a digest of one appears anywhere in "
    "this document - counts only. Dict keys are "
    "structure, never values, and any value under a "
    "content_sha256 key is the pack's identity, not "
    "its content, and its subtree is never walked.",
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


def _string_values(node, _skip: bool = False):
    """Every string value in a verified payload, in
    document order (P-191's walk, carried verbatim as
    P-193 carries it). A value under a content_sha256
    key is the pack's identity, not its content, and
    its subtree is never walked."""
    if _skip:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            yield from _string_values(value, key == "content_sha256")
    elif isinstance(node, list):
        for item in node:
            yield from _string_values(item)
    elif isinstance(node, str):
        yield node


def _digest(value: str) -> str:
    """The in-memory comparison digest of one value.
    Never carried in any document: a digest of a short
    string is a dictionary target."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _distinct_stats(payload) -> tuple[int, Counter]:
    """(occurrence count, per-digest occurrence counts)
    for one verified payload, under the walk and
    identity laws. Only digests are counted; the values
    themselves are never retained."""
    counts: Counter = Counter()
    total = 0
    for value in _string_values(payload):
        counts[_digest(value)] += 1
        total += 1
    return total, counts


def distinct_census_document(entries: list[HubEntry]) -> dict:
    """The hub distinct-content census for one owner's
    entries.

    ``entries`` is the owner's own entry list (the
    router hands over HubStore.list_for_owner for the
    caller; a foreign owner's entries are never in
    it). The P-187 list document is composed verbatim
    and embedded whole; each entry is then parsed
    through its own layer's verified parse road and
    its verified payload walked under P-191's walk
    law, its values compared for exact identity by
    in-memory digest only. Always a document, never
    an error for a bad pack: a pack the owning road
    refuses is an invalid row.
    """
    list_doc = hub_registry.list_document(entries)
    rows = []
    row_counters: list[Counter | None] = []
    by_outcome = {outcome: 0 for outcome in sorted(OUTCOMES)}
    by_kind_distinct = {
        kind: {"entries": 0, "parsed": 0, "string_values": 0,
               "distinct_values": 0, "extra_copies": 0}
        for kind in sorted(hub_registry.HUB_KINDS)}
    kind_digests: dict[str, set] = {
        kind: set() for kind in hub_registry.HUB_KINDS}
    estate_counts: Counter = Counter()
    estate_entries: dict[str, set] = {}
    total_string_values = 0
    largest = None
    for index, entry in enumerate(entries):
        row = entry.to_dict()
        state = hub_registry.locator_state(entry.locator)
        row["locator_state"] = state
        row["outcome"] = OUTCOME_UNAVAILABLE
        row["verified_content_sha256"] = ""
        row["string_value_count"] = 0
        row["distinct_value_count"] = 0
        row["repeated_value_count"] = 0
        row["extra_copy_count"] = 0
        row["shared_value_count"] = 0
        row["error"] = ""
        counter: Counter | None = None
        kind_axis = by_kind_distinct.get(entry.kind)
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
                    row["error"] = "pack file too large to distinct-census"
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
                            occurrences, counter = _distinct_stats(payload)
                            row["outcome"] = OUTCOME_PARSED
                            row["verified_content_sha256"] = verified
                            row["string_value_count"] = occurrences
                            row["distinct_value_count"] = len(counter)
                            row["repeated_value_count"] = sum(
                                1 for n in counter.values() if n >= 2)
                            row["extra_copy_count"] = (
                                occurrences - len(counter))
        rows.append(row)
        row_counters.append(counter)
        by_outcome[row["outcome"]] += 1
        if row["outcome"] == OUTCOME_PARSED and counter is not None:
            total_string_values += row["string_value_count"]
            estate_counts.update(counter)
            for digest in counter:
                estate_entries.setdefault(digest, set()).add(index)
            if kind_axis is not None:
                kind_axis["parsed"] += 1
                kind_axis["string_values"] += row["string_value_count"]
                kind_digests[entry.kind].update(counter)
            if (largest is None
                    or row["distinct_value_count"]
                    > largest["distinct_value_count"]):
                largest = {
                    "id": row["id"], "title": row["title"],
                    "kind": row["kind"],
                    "distinct_value_count": row["distinct_value_count"],
                    "string_value_count": row["string_value_count"],
                }
    # Second pass: a row's shared values are its distinct
    # values that also occur in at least one OTHER parsed
    # entry (parsed entries only, by construction above).
    for index, row in enumerate(rows):
        counter = row_counters[index]
        if row["outcome"] == OUTCOME_PARSED and counter is not None:
            row["shared_value_count"] = sum(
                1 for digest in counter
                if len(estate_entries.get(digest, ())) >= 2)
    for kind, axis in by_kind_distinct.items():
        axis["distinct_values"] = len(kind_digests[kind])
        axis["extra_copies"] = (
            axis["string_values"] - axis["distinct_values"])
    total_distinct_values = len(estate_counts)
    total_repeated_values = sum(
        1 for n in estate_counts.values() if n >= 2)
    total_shared_values = sum(
        1 for owners in estate_entries.values() if len(owners) >= 2)
    total = len(rows)
    parsed = by_outcome[OUTCOME_PARSED]
    if total == 0:
        census_state = DISTINCT_CENSUS_STATE_NO_ENTRIES
    elif parsed == 0:
        census_state = DISTINCT_CENSUS_STATE_NO_DISTINCT
    elif parsed == total:
        census_state = DISTINCT_CENSUS_STATE_ALL_DISTINCT
    else:
        census_state = DISTINCT_CENSUS_STATE_SOME_DISTINCT
    return {
        "schema": DISTINCT_CENSUS_SCHEMA,
        "census_state": census_state,
        "count": total,
        "entries_considered": total,
        "parsed_count": parsed,
        "coverage_complete": parsed == total,
        "list": list_doc,
        "entries": rows,
        "by_outcome": by_outcome,
        "by_kind_distinct": by_kind_distinct,
        "total_string_values": total_string_values,
        "total_distinct_values": total_distinct_values,
        "total_repeated_values": total_repeated_values,
        "total_shared_values": total_shared_values,
        "total_extra_copies": total_string_values - total_distinct_values,
        "largest_distinct_entry": largest,
        "max_browse_bytes": MAX_BROWSE_BYTES,
        "kind_formats": dict(hub_registry.KIND_FORMATS),
        "notes": list(NOTES),
    }
