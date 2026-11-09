"""Hub unified search census (P-194, Part XII - DERIVED).

The roadmap gives Part XII one line only ("The Hub,
Sovereign Shape", P-187..P-202); this slice's scope is
derived from Runmal's own in-tree record - see
docs/HUB_UNIFIED_SEARCH_CENSUS_2026-11-09.md and
hidden_files/P194_SCOUT.md / P194_DESIGN.md.

What the derivation found: every banked hub census
aggregates an estate (P-189: browse verdicts and
checksum claims, no query) or content volume (P-193:
verified payload string counts, no query) - none
aggregates a SEARCH ANSWER. P-192 banked the unified
hub search (one query composed over P-190's metadata
search and P-191's pack-content search, the union by
entry id under the matched_by law) and returns its
capped match list with only three full-union counts;
nothing states the RETURNED union's own distribution -
how its returned matches split by matched_by, kind and
matched metadata field, how many occurrences they
carry in total or which entry carries the most, or how
the content side's skipped entries split by outcome.
P-193's scout names this census (the P-184 workspace
shape) a lawful later cell once P-192 is banked; P-192
IS banked in this base. This module is that census, in
the house census pattern (P-184 / P-189): a pure
aggregate composing the owning surface verbatim,
classified under a closed law, counts summed from the
composed document's own fields:

- the unified document is P-192's, composed VERBATIM
  (the same entry list, cleaned query and kind handed
  to unified_search_document; its own validation law
  refuses first - a blank query or unknown kind raises
  P-192's HubUnifiedSearchError unchanged) and embedded
  whole; there is no second search, parse, walk or
  counting law here;
- the returned axis sums the document's RETURNED
  matches only (exactly its match_count): the
  matched_by split (metadata / content / both, summing
  exactly to match_count), the kind split under
  P-187's HUB_KINDS, the matched-field split under
  P-190's SEARCH_FIELDS (summing fields, not rows),
  the total occurrence count, and the returned row
  carrying the most occurrences;
- the source axis carries P-192's own full-union
  counts VERBATIM beside the returned sums
  (total_matches, the source metadata / content / both
  counts and both source totals), so a capped union is
  censused as capped: the two truths are stated side
  by side and neither is dressed as the other;
- the skip axis sums the document's skipped_entries
  rows by their own outcomes under P-191's closed
  OUTCOMES law (the searched outcome never appears
  there), with P-191's coverage arithmetic and the
  composed truncated / coverage_complete verdicts
  carried verbatim beside it;
- the answer is classified under the closed
  CENSUS_STATES law, judged on the RETURNED matches'
  sides: no_matches / metadata_only / content_only /
  mixed.

Honest boundaries: this census is a pure read over one
query's answer - it searches nothing itself beyond the
one composition, records nothing (P-192 stores
nothing, and no search-history surface is invented
here: a history would need a recording write, not a
composition), writes, registers, removes, imports,
installs, copies and grants nothing. Its own fields
carry counts, ids, titles and kinds only - no content
text is stated here; excerpts live solely inside the
embedded P-192 document, that search's own answer. The
cost is P-192's cost paid once: a unified search pays
P-191's full cost (every ready pack in the
kind-narrowed estate read and verified under P-188's
16 MiB bound); P-190's metadata search alone stays the
cheap road. Signing and friend-instance exchange stay
declined - no key or transport machinery is banked.
There is no central store, no catalogue and no creator
profile here (VX-59). No migration: head stays 0041.
"""

from __future__ import annotations

from runmal.hub import content_search as hub_content_search
from runmal.hub import registry as hub_registry
from runmal.hub import search as hub_search
from runmal.hub import unified_search as hub_unified_search
from runmal.hub.registry import HubEntry

UNIFIED_SEARCH_CENSUS_SCHEMA = (
    "runmal-p194-hub-unified-search-census-v1")

CENSUS_STATE_NO_MATCHES = "no_matches"
CENSUS_STATE_METADATA_ONLY = "metadata_only"
CENSUS_STATE_CONTENT_ONLY = "content_only"
CENSUS_STATE_MIXED = "mixed"
CENSUS_STATES = frozenset({
    CENSUS_STATE_NO_MATCHES, CENSUS_STATE_METADATA_ONLY,
    CENSUS_STATE_CONTENT_ONLY, CENSUS_STATE_MIXED,
})

SKIP_OUTCOMES = (
    hub_content_search.OUTCOME_UNAVAILABLE,
    hub_content_search.OUTCOME_INVALID,
)

NOTES = (
    "Pure read over one query's unified hub search: "
    "this census stores, records, registers, removes, "
    "imports, installs, copies, writes and grants "
    "nothing - it composes the banked unified search "
    "(P-192) and aggregates its answer; no search "
    "history is kept by it or by the search it "
    "composes.",
    "The unified search document is P-192's, composed "
    "verbatim and embedded whole: one query and one "
    "entry list handed to the banked metadata search "
    "(P-190) and pack-content search (P-191), the "
    "union by entry id under the matched_by law "
    "(metadata / content / both) - no second search, "
    "parse, walk or counting law exists here.",
    "Returned counts sum the composed document's "
    "RETURNED matches only and add up exactly: "
    "metadata + content + both in by_matched_by always "
    "equals the returned match_count. The source "
    "counts beside them are P-192's own full-union "
    "counts, carried verbatim - when a source or the "
    "union ran past its cap the two truths differ, "
    "and both are stated.",
    "Partiality is P-192's own verdict, carried "
    "verbatim: truncated names every capped answer "
    "and coverage_complete is false whenever the "
    "answer was truncated or the content search "
    "skipped any entry - a capped census is never "
    "dressed as complete, and matches a capped source "
    "never returned are not counted here because they "
    "were never returned.",
    "A metadata-only match contributes no occurrence "
    "count: no content fact is invented for an entry "
    "the content road did not match (P-192's "
    "kept-apart law). The by_matched_field axis sums "
    "the returned rows' matched_fields under P-190's "
    "field law: a row matching two fields counts "
    "under both, so the axis sums fields, not rows.",
    "Cost law: this census pays the unified search's "
    "full cost once - it reads and verifies every "
    "ready pack in the searched estate, each through "
    "its own layer's verified parse road and each "
    "under the browse size bound (see the embedded "
    "content search). The metadata search alone "
    "(P-190) stays the cheap road.",
    "Distinctness: P-189's census counts browse "
    "verdicts and checksum claims over the estate and "
    "P-193's counts verified payload string volume; "
    "neither answers for one query. This census "
    "counts one query's union answer only and "
    "measures neither browse verdicts, checksum "
    "claims nor string volume.",
    "Signing and friend-instance exchange stay "
    "declined: no key or transport machinery is "
    "banked, and this census invents none. There is "
    "no central store, no catalogue and no creator "
    "profile on this road (the VX-59 sovereign "
    "shape).",
)


def build_unified_search_census(unified_document: dict) -> dict:
    """The census document for one P-192 document.

    Sums only the unified document's own returned-match
    and skipped-entry fields; the document is embedded
    whole, and its own full-union counts ride verbatim
    beside the returned sums. The census state is
    judged on the returned matches' sides only.
    """
    matches = unified_document["matches"]
    by_matched_by = {
        key: 0 for key in sorted(hub_unified_search.MATCHED_BY)}
    by_kind = {kind: 0 for kind in sorted(hub_registry.HUB_KINDS)}
    by_matched_field = {field: 0 for field in hub_search.SEARCH_FIELDS}
    total_occurrences = 0
    most_occurrences = None
    has_metadata = False
    has_content = False
    for row in matches:
        matched_by = row["matched_by"]
        if matched_by in by_matched_by:
            by_matched_by[matched_by] += 1
        if row["metadata_match"]:
            has_metadata = True
        if row["content_match"]:
            has_content = True
        if row["kind"] in by_kind:
            by_kind[row["kind"]] += 1
        for field in row["matched_fields"]:
            if field in by_matched_field:
                by_matched_field[field] += 1
        occurrences = row["occurrences"]
        if occurrences is not None:
            total_occurrences += occurrences
            if (most_occurrences is None
                    or occurrences > most_occurrences["occurrences"]):
                most_occurrences = {
                    "id": row["id"], "title": row["title"],
                    "kind": row["kind"],
                    "occurrences": occurrences}
    skipped = unified_document["skipped_entries"]
    by_skip_outcome = {outcome: 0 for outcome in SKIP_OUTCOMES}
    for row in skipped:
        outcome = row["outcome"]
        if outcome in by_skip_outcome:
            by_skip_outcome[outcome] += 1
    if not matches:
        census_state = CENSUS_STATE_NO_MATCHES
    elif has_metadata and has_content:
        census_state = CENSUS_STATE_MIXED
    elif has_metadata:
        census_state = CENSUS_STATE_METADATA_ONLY
    else:
        census_state = CENSUS_STATE_CONTENT_ONLY
    return {
        "schema": UNIFIED_SEARCH_CENSUS_SCHEMA,
        "census_state": census_state,
        "query": unified_document["query"],
        "kind": unified_document["kind"],
        "unified_search": unified_document,
        "match_count": len(matches),
        "by_matched_by": by_matched_by,
        "by_kind": by_kind,
        "by_matched_field": by_matched_field,
        "total_occurrences": total_occurrences,
        "most_occurrences": most_occurrences,
        "total_matches": unified_document["total_matches"],
        "source_metadata_match_count": (
            unified_document["metadata_match_count"]),
        "source_content_match_count": (
            unified_document["content_match_count"]),
        "source_both_count": unified_document["both_count"],
        "metadata_total_matches": (
            unified_document["metadata_total_matches"]),
        "content_total_matches": (
            unified_document["content_total_matches"]),
        "entries_considered": unified_document["entries_considered"],
        "entries_searched": unified_document["entries_searched"],
        "skipped_count": len(skipped),
        "by_skip_outcome": by_skip_outcome,
        "truncated": unified_document["truncated"],
        "coverage_complete": unified_document["coverage_complete"],
        "kind_formats": dict(hub_registry.KIND_FORMATS),
        "notes": list(NOTES),
    }


def unified_search_census_document(
    entries: list[HubEntry],
    query: str,
    kind: str | None = None,
) -> dict:
    """The unified search census for one owner's entries.

    ``entries`` is the owner's own entry list (the
    router hands over HubStore.list_for_owner for the
    caller; a foreign owner's entries are never in
    it). The unified search is P-192's document composed
    verbatim: the query and kind are validated by
    P-192 BEFORE anything is aggregated (a blank or
    non-string query and an unknown kind raise P-192's
    HubUnifiedSearchError unchanged - refused plainly,
    never treated as match-everything), and the census
    aggregates that one document's answer.
    """
    unified_document = hub_unified_search.unified_search_document(
        entries, query, kind=kind)
    return build_unified_search_census(unified_document)


__all__ = [
    "CENSUS_STATE_CONTENT_ONLY", "CENSUS_STATE_METADATA_ONLY",
    "CENSUS_STATE_MIXED", "CENSUS_STATE_NO_MATCHES",
    "CENSUS_STATES", "NOTES", "SKIP_OUTCOMES",
    "UNIFIED_SEARCH_CENSUS_SCHEMA",
    "build_unified_search_census",
    "unified_search_census_document",
]
