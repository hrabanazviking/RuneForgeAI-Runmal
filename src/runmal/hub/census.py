"""Hub census (P-189, Part XII - DERIVED).

P-187 landed the hub registry: an owner-scoped index
of the pack artefacts an owner holds, with a list
document that counts any entry list it is handed by
kind and by live locator state. P-188 landed hub-side
browse: one entry at a time, its pack read through the
owning layer's own verified inspect road. Neither
answers the estate question: across everything an
owner holds, how many packs actually inspect, how
many are unavailable or invalid, and how the callers'
checksum claims stand against the verified checksums.
This module is that estate view, on the house census
pattern (P-171 workspaces, the scenario census
family): a pure read composing the owning surfaces
verbatim, classified under a closed law, counts
summed from the composed documents' own values.

- The P-187 list document is composed VERBATIM and
  embedded whole: the total, the by-kind counts and
  the by-locator-state counts are the registry's own
  arithmetic, never recomputed under a second law.
- Each row carries one entry's P-188 browse verdict
  VERBATIM - its browse_state, locator_state,
  verified_content_sha256, checksum_match and error
  are the browse document's own fields. The browse
  inspection itself is NOT embedded: the full
  inspection stays on P-188's per-entry road.
- The browse axis sums the rows' browse_state values
  under P-188's closed BROWSE_STATES law; the
  checksum axis sums checksum_match verbatim under
  three closed keys - match, mismatch, undetermined
  (None: no claim, no verified checksum, or a browse
  that never reached inspection - never separated by
  guessing why). The entry's checksum stays the
  caller's CLAIM throughout.
- The estate is classified under a closed census law
  (CENSUS_STATES), judged on the browse axis:
  no_entries / none_inspected / some_inspected /
  all_inspected.

Honest boundaries, and the cost stated plainly: a
census browses every ready entry, so it READS pack
files - each through P-188's own law, under its
16 MiB bound, so an oversize, corrupt or wrong-kind
pack is an invalid row, never a census failure. The
census writes nothing, imports nothing, installs
nothing, copies nothing and grants nothing; signing
and friend-instance exchange stay declined - no key
or transport machinery is banked (the P-187/P-188
records). There is no central store, no catalogue
and no creator profile here (VX-59). No migration:
head stays 0041.
"""

from __future__ import annotations

from runmal.hub import browse as hub_browse
from runmal.hub import registry as hub_registry
from runmal.hub.registry import HubEntry

CENSUS_SCHEMA = "runmal-p189-hub-census-v1"

CENSUS_STATE_NO_ENTRIES = "no_entries"
CENSUS_STATE_NONE_INSPECTED = "none_inspected"
CENSUS_STATE_SOME_INSPECTED = "some_inspected"
CENSUS_STATE_ALL_INSPECTED = "all_inspected"
CENSUS_STATES = frozenset({
    CENSUS_STATE_NO_ENTRIES, CENSUS_STATE_NONE_INSPECTED,
    CENSUS_STATE_SOME_INSPECTED, CENSUS_STATE_ALL_INSPECTED,
})

CHECKSUM_MATCH = "match"
CHECKSUM_MISMATCH = "mismatch"
CHECKSUM_UNDETERMINED = "undetermined"
CHECKSUM_KEYS = frozenset({
    CHECKSUM_MATCH, CHECKSUM_MISMATCH, CHECKSUM_UNDETERMINED,
})

NOTES = (
    "Pure read, owner scoped: only the caller's own "
    "entries are censused; this census stores, "
    "registers, removes, imports, installs, copies "
    "and writes nothing.",
    "The registry list embedded here is P-187's list "
    "document composed verbatim - its count, by-kind "
    "and by-locator-state arithmetic is the "
    "registry's own, never recomputed under a second "
    "law - and every row's browse fields are that "
    "entry's P-188 browse document carried verbatim.",
    "A census browses every ready entry through "
    "P-188's own law, so it reads pack files, each "
    "under the browse size bound: an oversize, "
    "corrupt or wrong-kind pack is an invalid row, "
    "never a census failure. The full inspection "
    "documents are not embedded here; they stay on "
    "P-188's per-entry browse road.",
    "The checksum axis sums the browse documents' "
    "checksum_match verbatim: match, mismatch, or "
    "undetermined when the verdict was null - no "
    "claim, no verified checksum, or a browse that "
    "never reached inspection. An entry's checksum "
    "stays the caller's claim and is never upgraded "
    "to verified by being counted.",
    "The census state is judged on the browse axis "
    "only: no entries, none inspected, some "
    "inspected, or all inspected - a point-in-time "
    "judgement at this call, from live locator and "
    "browse states, never a stored fact.",
    "Signing and friend-instance exchange stay "
    "declined: no key or transport machinery is "
    "banked, and this census invents none. There is "
    "no central store, no catalogue and no creator "
    "profile on this road (the VX-59 sovereign "
    "shape).",
)


def _checksum_key(value: bool | None) -> str:
    if value is True:
        return CHECKSUM_MATCH
    if value is False:
        return CHECKSUM_MISMATCH
    return CHECKSUM_UNDETERMINED


def census_document(entries: list[HubEntry]) -> dict:
    """The hub census for one owner's entries.

    ``entries`` is the owner's own entry list (the
    router hands over HubStore.list_for_owner for the
    caller; a foreign owner's entries are never in
    it). The P-187 list document is composed verbatim
    and embedded whole; each entry is then browsed
    through P-188's own road and the row carries that
    browse document's verdict fields verbatim.
    Always a document, never an error for a bad pack:
    a pack the owning road refuses is an invalid row.
    """
    list_doc = hub_registry.list_document(entries)
    rows = []
    by_browse_state = {
        state: 0 for state in sorted(hub_browse.BROWSE_STATES)}
    by_checksum_match = {
        key: 0 for key in sorted(CHECKSUM_KEYS)}
    inspected = 0
    for entry in entries:
        browse_doc = hub_browse.browse_document(entry)
        row = entry.to_dict()
        row["locator_state"] = browse_doc["locator_state"]
        row["browse_state"] = browse_doc["browse_state"]
        row["verified_content_sha256"] = (
            browse_doc["verified_content_sha256"])
        row["checksum_match"] = browse_doc["checksum_match"]
        row["error"] = browse_doc["error"]
        rows.append(row)
        by_browse_state[row["browse_state"]] += 1
        by_checksum_match[_checksum_key(row["checksum_match"])] += 1
        if row["browse_state"] == hub_browse.BROWSE_INSPECTED:
            inspected += 1
    total = len(rows)
    if total == 0:
        census_state = CENSUS_STATE_NO_ENTRIES
    elif inspected == 0:
        census_state = CENSUS_STATE_NONE_INSPECTED
    elif inspected == total:
        census_state = CENSUS_STATE_ALL_INSPECTED
    else:
        census_state = CENSUS_STATE_SOME_INSPECTED
    return {
        "schema": CENSUS_SCHEMA,
        "census_state": census_state,
        "count": total,
        "list": list_doc,
        "entries": rows,
        "by_browse_state": by_browse_state,
        "by_checksum_match": by_checksum_match,
        "kind_formats": dict(hub_registry.KIND_FORMATS),
        "notes": list(NOTES),
    }
