"""Hub byte-size census (P-197, Part XII - DERIVED).

The roadmap gives Part XII one line only ("The Hub,
Sovereign Shape", P-187..P-202); this slice scope is
derived from Runmal own in-tree record - see
docs/HUB_SIZE_CENSUS_2026-11-09.md and
hidden_files/P197_SCOUT.md / P197_DESIGN.md.

What the derivation found: no banked hub document
carries a single field for how much storage an owner
estate occupies. Every hub surface stats each ready
pack file to enforce the 16 MiB browse bound and
discards the size: P-187 counts kinds and locator
states, P-189 counts browse verdicts and checksum
claims, P-193 counts payload string values and their
characters, P-194 aggregates one query answer, P-195
groups entries by verified identity and P-196 counts
payload node shapes. A locator is not a size, so the
estate byte footprint is not derivable from any
banked document - it exists only on the filesystem
at read time. P-196 scout declined this cell as the
weaker one beside shape and named it a lawful later
cell; P-196 is banked ahead of this slice, and this
is that later cell.

- Composition, verbatim roads only - never a second
  parser. Each entry is judged under P-187 locator
  law (registry.locator_state, judged live) and
  P-188 size bound (MAX_BROWSE_BYTES, imported: one
  bound law), then parsed through the owning layer
  OWN verified parse road, dispatched exactly as
  P-193 dispatches: lorebook_pack ->
  lorebooks.packs.parse_pack (payload member
  lorebook), prompt_pack -> presets.packs.parse_pack
  (payload member items), scenario_pack ->
  scenarios.packs.parse_pack (payload member
  scenario), preset_bundle -> presets.bundles.
  parse_share (the bundle it returns is the payload).
  Each parse road verifies format, manifest against
  payload, the content checksum and the payload
  itself: only a VERIFIED pack feeds the verified
  axes.
- The byte law, two halves never mixed. file_bytes
  is a FILESYSTEM fact: the stat size of the file at
  a ready locator, carried for every ready row
  whether or not its pack verifies - an oversize or
  corrupt file still occupies its bytes, and hiding
  them would understate the estate. It is null for
  any row whose locator is not ready or whose stat
  fails: no file, no number, never faked. The
  VERIFIED axes (total_verified_bytes, per-kind
  verified bytes, the size buckets, largest and
  smallest) sum file_bytes over PARSED rows only:
  no byte is presented as verified content bytes
  unless its pack verified. total_verified_bytes is
  therefore always at most total_file_bytes.
- The size buckets are a closed law (SIZE_BUCKETS)
  over parsed rows only: tiny (under 1024 bytes),
  small (1024 to under 16384), medium (16384 to
  under 262144), large (262144 to under 1048576),
  huge (1048576 and over, at most the bound). Bytes
  are per FILE and are never deduplicated: two
  registrations of byte-equal copies count twice,
  because two files occupy the bytes twice -
  duplicate identity is P-195 ground, never
  recounted here.
- DISTINCTNESS, stated plainly: this census measures
  the FILE as stored - envelope, manifest, formatting
  and payload together. It carries no P-193 volume
  field (payload string characters exclude the
  envelope and every non-string byte), no P-196 shape
  field (nodes, keys, depth), no P-189 verdict, no
  P-194 query axis and no P-195 grouping.
- No silent omission (the P-191 law): every entry
  ends parsed, or named by its row outcome -
  unavailable (the locator is not ready; no read
  attempted, file_bytes null) or invalid (the stat
  failed, the file exceeds the size bound, it is not
  valid JSON on the bundle road, or the owning layer
  own parse road refused it, its refusal carried
  verbatim; an invalid row whose stat succeeded
  still carries its file_bytes) - under P-193
  OUTCOMES law, imported (one law, never forked),
  and coverage_complete carries the truth as data:
  any non-parsed entry makes it false, and count
  always equals parsed plus unavailable plus invalid.
- NO content is retained or returned: this census
  carries sizes, counts, entry data and verified
  checksums only - never a byte of file content,
  never an excerpt and never a payload field,
  anywhere in the document (the P-183 law).
- The estate is classified under a closed census law
  (SIZE_CENSUS_STATES), judged on the parsed axis:
  no_entries / no_sizes / some_sizes / all_sizes.

Honest boundaries, and the cost stated plainly: a
size census parses every ready entry, so it READS
pack files - each through its own layer verified
parse road, under the 16 MiB bound, so an oversize,
corrupt or wrong-kind pack is an invalid row, never
a census failure. The census writes nothing, imports
nothing, installs nothing, copies nothing and grants
nothing; an entry registered checksum stays the
caller claim and is never upgraded by being counted
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

SIZE_CENSUS_SCHEMA = "runmal-p197-hub-size-census-v1"

MAX_BROWSE_BYTES = hub_browse.MAX_BROWSE_BYTES  # P-188 bound: one law

# P-193 outcomes law, imported: one law, never forked.
OUTCOME_PARSED = hub_content_census.OUTCOME_PARSED
OUTCOME_UNAVAILABLE = hub_content_census.OUTCOME_UNAVAILABLE
OUTCOME_INVALID = hub_content_census.OUTCOME_INVALID
OUTCOMES = hub_content_census.OUTCOMES

BUCKET_TINY = "tiny"
BUCKET_SMALL = "small"
BUCKET_MEDIUM = "medium"
BUCKET_LARGE = "large"
BUCKET_HUGE = "huge"
SIZE_BUCKETS = frozenset({
    BUCKET_TINY, BUCKET_SMALL, BUCKET_MEDIUM,
    BUCKET_LARGE, BUCKET_HUGE,
})

# Bucket edges in bytes: a parsed file of exactly an
# edge size belongs to the HIGHER bucket.
BUCKET_EDGES = (1024, 16384, 262144, 1048576)

SIZE_CENSUS_STATE_NO_ENTRIES = "no_entries"
SIZE_CENSUS_STATE_NO_SIZES = "no_sizes"
SIZE_CENSUS_STATE_SOME_SIZES = "some_sizes"
SIZE_CENSUS_STATE_ALL_SIZES = "all_sizes"
SIZE_CENSUS_STATES = frozenset({
    SIZE_CENSUS_STATE_NO_ENTRIES, SIZE_CENSUS_STATE_NO_SIZES,
    SIZE_CENSUS_STATE_SOME_SIZES, SIZE_CENSUS_STATE_ALL_SIZES,
})

NOTES = (
    "Pure read, owner scoped: only the caller own "
    "entries are censused; this census stores, "
    "registers, removes, imports, installs, copies "
    "and writes nothing.",
    "Distinctness: P-189 census counts browse "
    "verdicts and checksum claims, P-193 counts "
    "verified payload string volume, P-194 counts "
    "one query answer, P-195 groups entries by "
    "verified identity and P-196 counts payload node "
    "shape; this census measures the FILE each entry "
    "came from - envelope, manifest, formatting and "
    "payload together, exactly as stored - an axis "
    "no banked document carries.",
    "Byte law: file_bytes is the stat size of the "
    "file at a ready locator, carried for every ready "
    "row whether or not its pack verifies, and null "
    "when the locator is not ready or the stat "
    "fails. The verified axes - total_verified_bytes, "
    "per-kind verified bytes, the size buckets, "
    "largest and smallest - sum parsed rows only, "
    "so total_verified_bytes is always at most "
    "total_file_bytes.",
    "Cost law: a size census reads and verifies "
    "every ready pack in the estate, each through "
    "its own layer verified parse road and each "
    "under the browse size bound (max_browse_bytes "
    "in this document), plus one stat per ready "
    "entry - the price of measuring files the "
    "registry does not hold.",
    "Bytes are per file and are never deduplicated: "
    "two registrations of byte-equal copies count "
    "their bytes twice, because two files occupy "
    "them twice. Whether two entries hold the same "
    "verified content is P-195 census ground and is "
    "never stated here.",
    "No silent omission: every entry was parsed or "
    "is named by its row outcome - unavailable (its "
    "locator is not ready, file_bytes null) or "
    "invalid (its own layer road refused it, it "
    "could not be read, or it exceeds the size "
    "bound; an invalid row whose stat succeeded "
    "still carries its file_bytes). "
    "coverage_complete is false whenever any entry "
    "was not parsed, and count always equals parsed "
    "plus unavailable plus invalid.",
    "verified_content_sha256 on a row is the "
    "checksum the owning layer own parse road "
    "verified (empty for a bare preset bundle, whose "
    "road verifies none, and for any entry that was "
    "not parsed). A bare bundle parsed row still "
    "counts its real file_bytes as verified bytes: "
    "its road verified the share, and the checksum "
    "absence is stated, never filled in. An entry "
    "registered checksum stays the caller claim and "
    "is never upgraded by being counted.",
    "Signing and friend-instance exchange stay "
    "declined: no key or transport machinery is "
    "banked, and this census invents none. There is "
    "no central store, no catalogue and no creator "
    "profile on this road (the VX-59 sovereign "
    "shape).",
)


def size_bucket(file_bytes: int) -> str:
    """The closed bucket law for one parsed file size:
    a size exactly on an edge belongs to the higher
    bucket."""
    if file_bytes < BUCKET_EDGES[0]:
        return BUCKET_TINY
    if file_bytes < BUCKET_EDGES[1]:
        return BUCKET_SMALL
    if file_bytes < BUCKET_EDGES[2]:
        return BUCKET_MEDIUM
    if file_bytes < BUCKET_EDGES[3]:
        return BUCKET_LARGE
    return BUCKET_HUGE


def _parse_payload(entry: HubEntry, raw: bytes):
    """Dispatch to the owning layer own verified parse
    road; returns (payload, verified_content_sha256).
    P-193 dispatch, carried verbatim."""
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


def size_census_document(entries: list[HubEntry]) -> dict:
    """The hub byte-size census for one owner entries.

    entries is the owner own entry list (the
    router hands over HubStore.list_for_owner for the
    caller; a foreign owner entries are never in
    it). The P-187 list document is composed verbatim
    and embedded whole; each ready entry is statted
    and parsed through its own layer verified parse
    road, and its file measured under the byte law.
    Always a document, never an error for a bad pack:
    a pack the owning road refuses is an invalid row.
    """
    list_doc = hub_registry.list_document(entries)
    rows = []
    by_outcome = {outcome: 0 for outcome in sorted(OUTCOMES)}
    by_kind_size = {
        kind: {"entries": 0, "parsed": 0, "measured": 0,
               "bytes": 0, "verified_bytes": 0}
        for kind in sorted(hub_registry.HUB_KINDS)}
    by_size_bucket = {bucket: 0 for bucket in sorted(SIZE_BUCKETS)}
    measured_count = 0
    total_file_bytes = 0
    total_verified_bytes = 0
    largest = None
    smallest = None
    for entry in entries:
        row = entry.to_dict()
        state = hub_registry.locator_state(entry.locator)
        row["locator_state"] = state
        row["outcome"] = OUTCOME_UNAVAILABLE
        row["verified_content_sha256"] = ""
        row["file_bytes"] = None
        row["error"] = ""
        kind_axis = by_kind_size.get(entry.kind)
        if kind_axis is not None:
            kind_axis["entries"] += 1
        if state == hub_registry.LOCATOR_READY:
            try:
                size = Path(entry.locator).stat().st_size
            except OSError as exc:
                row["outcome"] = OUTCOME_INVALID
                row["error"] = "locator could not be read: " + str(exc)
            else:
                row["file_bytes"] = size
                if size > MAX_BROWSE_BYTES:
                    row["outcome"] = OUTCOME_INVALID
                    row["error"] = "pack file too large to size-census"
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
                            row["outcome"] = OUTCOME_PARSED
                            row["verified_content_sha256"] = verified
        rows.append(row)
        by_outcome[row["outcome"]] += 1
        if row["file_bytes"] is not None:
            measured_count += 1
            total_file_bytes += row["file_bytes"]
            if kind_axis is not None:
                kind_axis["measured"] += 1
                kind_axis["bytes"] += row["file_bytes"]
        if row["outcome"] == OUTCOME_PARSED:
            total_verified_bytes += row["file_bytes"]
            by_size_bucket[size_bucket(row["file_bytes"])] += 1
            if kind_axis is not None:
                kind_axis["parsed"] += 1
                kind_axis["verified_bytes"] += row["file_bytes"]
            named = {
                "id": row["id"], "title": row["title"],
                "kind": row["kind"],
                "file_bytes": row["file_bytes"],
                "verified_content_sha256": (
                    row["verified_content_sha256"]),
            }
            if largest is None or row["file_bytes"] > largest["file_bytes"]:
                largest = named
            if smallest is None or row["file_bytes"] < smallest["file_bytes"]:
                smallest = dict(named)
    total = len(rows)
    parsed = by_outcome[OUTCOME_PARSED]
    if total == 0:
        census_state = SIZE_CENSUS_STATE_NO_ENTRIES
    elif parsed == 0:
        census_state = SIZE_CENSUS_STATE_NO_SIZES
    elif parsed == total:
        census_state = SIZE_CENSUS_STATE_ALL_SIZES
    else:
        census_state = SIZE_CENSUS_STATE_SOME_SIZES
    return {
        "schema": SIZE_CENSUS_SCHEMA,
        "census_state": census_state,
        "count": total,
        "entries_considered": total,
        "parsed_count": parsed,
        "measured_count": measured_count,
        "coverage_complete": parsed == total,
        "list": list_doc,
        "entries": rows,
        "by_outcome": by_outcome,
        "by_kind_size": by_kind_size,
        "by_size_bucket": by_size_bucket,
        "total_file_bytes": total_file_bytes,
        "total_verified_bytes": total_verified_bytes,
        "largest_file_entry": largest,
        "smallest_file_entry": smallest,
        "max_browse_bytes": MAX_BROWSE_BYTES,
        "kind_formats": dict(hub_registry.KIND_FORMATS),
        "notes": list(NOTES),
    }
