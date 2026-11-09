"""Hub duplicate-content census (P-195, Part XII - DERIVED).

The roadmap gives Part XII one line only ("The Hub,
Sovereign Shape", P-187..P-202); this slice's scope is
derived from Runmal's own in-tree record - see
docs/HUB_DUPLICATE_CENSUS_2026-11-09.md and
hidden_files/P195_SCOUT.md / P195_DESIGN.md.

What the derivation found: every pack layer's own
import road treats the verified content checksum as a
pack's identity - lorebooks (P-045), presets (P-063)
and scenarios (P-141) each detect an exact duplicate
on import by comparing content checksums, owner
scoped. The hub, the index above those layers, has no
such view: an owner can register the same pack twice
(two copies of one file, two locators, two titles -
P-187's refusal law covers only the identical
(owner, kind, locator) triple) and no banked document
ever says so. P-189 compares each entry's CLAIM
against its own verified checksum, a per-entry
verdict; P-193 carries every parsed row's verified
checksum but its axes are content VOLUME; P-194
aggregates one query's answer. None compares
verified-vs-verified ACROSS entries. This module is
that census, in the house census pattern (P-194's
build-over-one-composed-document shape): a pure
aggregate composing the owning surface verbatim,
classified under a closed law, counts summed from the
composed document's own rows:

- the content census is P-193's, composed VERBATIM
  (the same entry list handed to
  content_census_document) and embedded whole; there
  is no second parse, walk or counting law here;
- a row's identity is its verified_content_sha256
  from the composed document, and ONLY a non-empty
  verified checksum is an identity: a row whose
  verified checksum is empty (a bare preset bundle,
  whose road verifies none, or any unavailable /
  invalid row) is UNIDENTIFIED and is never grouped,
  so two bare bundles are never declared duplicates -
  no identity was verified, and none is faked;
- the partition is exact: every entry is exactly one
  of duplicate (parsed, non-empty checksum, group
  size >= 2), unique (parsed, non-empty checksum,
  group size 1) or unidentified (verified checksum
  empty), and the three counts always sum to the
  estate count;
- grouping is by the verified checksum ALONE,
  regardless of kind or of the caller's claimed
  checksum: the checksum is the content's identity,
  the claim plays no part (a wrong claim can neither
  create nor break a group), and each member's kind
  rides on its row so a cross-kind group is stated,
  never hidden;
- the answer is classified under the closed
  DUPLICATE_CENSUS_STATES law, judged on the
  duplicate axis: no_entries / no_duplicates /
  some_duplicates / all_duplicates (every entry in
  the estate a member of a duplicate group - by the
  partition law, no unique and no unidentified entry).

Honest boundaries: this census is a pure read - it
parses nothing itself beyond the one composition,
records nothing, writes, registers, removes, imports,
installs, copies and grants nothing. Its own fields
carry counts, ids, titles, kinds and verified
checksums only - no content text is stated here;
volume facts live solely inside the embedded P-193
document. The cost is P-193's cost paid once: a
content census reads and verifies every ready pack
in the estate, each through its own layer's verified
parse road and each under P-188's 16 MiB bound.
Signing and friend-instance exchange stay declined -
no key or transport machinery is banked. There is no
central store, no catalogue and no creator profile
here (VX-59). No migration: head stays 0041.
"""

from __future__ import annotations

from runmal.hub import content_census as hub_content_census
from runmal.hub import registry as hub_registry
from runmal.hub.registry import HubEntry

DUPLICATE_CENSUS_SCHEMA = (
    "runmal-p195-hub-duplicate-census-v1")

DUPLICATE_CENSUS_STATE_NO_ENTRIES = "no_entries"
DUPLICATE_CENSUS_STATE_NO_DUPLICATES = "no_duplicates"
DUPLICATE_CENSUS_STATE_SOME_DUPLICATES = "some_duplicates"
DUPLICATE_CENSUS_STATE_ALL_DUPLICATES = "all_duplicates"
DUPLICATE_CENSUS_STATES = frozenset({
    DUPLICATE_CENSUS_STATE_NO_ENTRIES,
    DUPLICATE_CENSUS_STATE_NO_DUPLICATES,
    DUPLICATE_CENSUS_STATE_SOME_DUPLICATES,
    DUPLICATE_CENSUS_STATE_ALL_DUPLICATES,
})

NOTES = (
    "Pure read, owner scoped: only the caller's own "
    "entries are censused; this census stores, "
    "records, registers, removes, imports, installs, "
    "copies, writes and grants nothing - it composes "
    "the banked hub content census (P-193) and "
    "aggregates its rows by verified content identity.",
    "The content census document is P-193's, composed "
    "verbatim and embedded whole: every entry parsed "
    "through its own layer's verified parse road under "
    "the browse size bound, each row carrying that "
    "road's own verified_content_sha256 - no second "
    "parse, walk or counting law exists here.",
    "Identity law: only a non-empty verified checksum "
    "is an identity. A row whose verified checksum is "
    "empty - a bare preset bundle, whose road verifies "
    "none, or any entry that was not parsed - is "
    "unidentified and is never grouped: two bare "
    "bundles are never declared duplicates, because "
    "no identity was verified for either and none is "
    "faked here.",
    "Partition law: every entry is exactly one of "
    "duplicate (its verified checksum is shared by "
    "two or more entries), unique (its verified "
    "checksum is its alone) or unidentified (no "
    "verified checksum), and duplicate plus unique "
    "plus unidentified always equals the estate "
    "count. Grouping is by the verified checksum "
    "alone, regardless of kind: a group's members "
    "carry their own kinds, so a cross-kind group is "
    "stated, never hidden.",
    "An entry's registered checksum is the caller's "
    "claim and plays no part in grouping: a wrong "
    "claim can neither create nor break a duplicate "
    "group, and being counted here never upgrades a "
    "claim to verified. P-189's census is the road "
    "that judges claims against verified checksums, "
    "per entry.",
    "Distinctness: P-189 counts browse verdicts and "
    "checksum claims, P-193 counts verified payload "
    "string volume and P-194 counts one query's "
    "unified answer; none compares verified checksums "
    "across entries. This census states duplicate "
    "holdings only and measures neither verdicts, "
    "claims, volume nor any query's answer - those "
    "facts live inside the embedded P-193 document, "
    "which is that census's own answer.",
    "Cost law: this census pays the content census's "
    "full cost once - it reads and verifies every "
    "ready pack in the estate, each through its own "
    "layer's verified parse road and each under the "
    "browse size bound (see the embedded content "
    "census). The registry list alone (P-187) stays "
    "the cheap road.",
    "Signing and friend-instance exchange stay "
    "declined: no key or transport machinery is "
    "banked, and this census invents none. There is "
    "no central store, no catalogue and no creator "
    "profile on this road (the VX-59 sovereign "
    "shape).",
)


def build_duplicate_census(content_census_document: dict) -> dict:
    """The duplicate census for one P-193 document.

    Groups only the composed document's own rows, by
    their verified_content_sha256 fields; the document
    is embedded whole, and its own parsed count and
    coverage verdict ride verbatim beside the groups.
    The census state is judged on the duplicate axis
    only.
    """
    rows = content_census_document["entries"]
    groups_by_sha: dict[str, dict] = {}
    group_order: list[str] = []
    distinct: set[str] = set()
    unidentified = 0
    by_kind = {
        kind: {"entries": 0, "duplicate_entries": 0}
        for kind in sorted(hub_registry.HUB_KINDS)}
    for row in rows:
        if row["kind"] in by_kind:
            by_kind[row["kind"]]["entries"] += 1
        verified = row["verified_content_sha256"]
        if row["outcome"] != hub_content_census.OUTCOME_PARSED \
                or not verified:
            unidentified += 1
            continue
        distinct.add(verified)
        group = groups_by_sha.get(verified)
        if group is None:
            group = {
                "verified_content_sha256": verified,
                "count": 0,
                "entries": [],
            }
            groups_by_sha[verified] = group
            group_order.append(verified)
        group["count"] += 1
        group["entries"].append({
            "id": row["id"], "title": row["title"],
            "kind": row["kind"],
            "string_value_count": row["string_value_count"],
            "string_char_count": row["string_char_count"],
        })
    duplicate_groups = [
        groups_by_sha[sha] for sha in group_order
        if groups_by_sha[sha]["count"] >= 2]
    duplicate_entry_count = sum(
        group["count"] for group in duplicate_groups)
    unique_entry_count = sum(
        groups_by_sha[sha]["count"] for sha in group_order
        if groups_by_sha[sha]["count"] == 1)
    for group in duplicate_groups:
        for member in group["entries"]:
            if member["kind"] in by_kind:
                by_kind[member["kind"]]["duplicate_entries"] += 1
    largest = None
    for group in duplicate_groups:
        if largest is None or group["count"] > largest["count"]:
            largest = {
                "verified_content_sha256": (
                    group["verified_content_sha256"]),
                "count": group["count"],
            }
    total = content_census_document["count"]
    if total == 0:
        census_state = DUPLICATE_CENSUS_STATE_NO_ENTRIES
    elif duplicate_entry_count == 0:
        census_state = DUPLICATE_CENSUS_STATE_NO_DUPLICATES
    elif duplicate_entry_count == total:
        census_state = DUPLICATE_CENSUS_STATE_ALL_DUPLICATES
    else:
        census_state = DUPLICATE_CENSUS_STATE_SOME_DUPLICATES
    return {
        "schema": DUPLICATE_CENSUS_SCHEMA,
        "census_state": census_state,
        "count": total,
        "content_census": content_census_document,
        "duplicate_groups": duplicate_groups,
        "duplicate_group_count": len(duplicate_groups),
        "duplicate_entry_count": duplicate_entry_count,
        "redundant_copy_count": (
            duplicate_entry_count - len(duplicate_groups)),
        "distinct_content_count": len(distinct),
        "unique_entry_count": unique_entry_count,
        "unidentified_entry_count": unidentified,
        "parsed_count": content_census_document["parsed_count"],
        "coverage_complete": (
            content_census_document["coverage_complete"]),
        "by_kind": by_kind,
        "largest_duplicate_group": largest,
        "kind_formats": dict(hub_registry.KIND_FORMATS),
        "notes": list(NOTES),
    }


def duplicate_census_document(entries: list[HubEntry]) -> dict:
    """The hub duplicate-content census for one owner's
    entries.

    ``entries`` is the owner's own entry list (the
    router hands over HubStore.list_for_owner for the
    caller; a foreign owner's entries are never in
    it). P-193's content census is composed verbatim
    over the same list and embedded whole; the groups
    are summed from its rows only. Always a document,
    never an error for a bad pack: a pack the owning
    road refuses is an unidentified row in the
    composed census, named there by its outcome.
    """
    content_doc = hub_content_census.content_census_document(entries)
    return build_duplicate_census(content_doc)
