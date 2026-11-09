"""Unified hub search (P-192, Part XII - DERIVED).

P-190 landed the hub metadata search: a literal search
over the registry's own entry data, opening no pack.
P-191 landed the hub pack-content search: a literal
search over the verified payload contents of the
owner's registered packs, through each layer's own
parse road. An owner hunting one word had to run both,
as two separate documents - two point-in-time
judgements that can disagree - and merge the answers
by hand; no document ever said, for one entry, whether
the METADATA spoke, the CONTENT spoke, or both did.
This module is that composing cell, on the house
precedent (workspace P-178 filename search + P-180
content search -> P-182 unified search): a pure read
over the two banked search documents, no new search law:

- ONE query, ONE estate: the same entry list, cleaned
  query and kind filter are handed to P-190's
  search_document and P-191's content_search_document;
  both documents are embedded WHOLE, their match laws
  unchanged (a metadata match is the query casefolded
  in a searched registry field; a content match is the
  query casefolded in a string value of the verified
  payload), and there is no second search, parse, walk
  or counting law here;
- the union is by entry id, in store order: every
  returned entry appears once, carrying matched_by
  under the closed law (metadata / content / both),
  the metadata side's matched_fields verbatim (empty
  for a content-only match - the metadata road's true
  answer) and - for content matches - the occurrence
  count, bounded excerpt and verified checksum verbatim
  (null for a metadata-only match: no content fact is
  invented for an entry the content road did not match,
  including one it skipped);
- cap honesty, composed: each banked search returns at
  most its own MAX_MATCHES (100, the same value both
  carry) and keeps its true total; the union is over
  the two RETURNED match lists, both source totals ride
  verbatim as metadata_total_matches /
  content_total_matches, and truncated - either source's
  truncation, or the union running past this module's
  cap - names every capped answer, never dressed as
  complete;
- coverage honesty is P-191's, carried verbatim: the
  content document's entries_considered,
  entries_searched and skipped_entries ride whole, and
  coverage_complete is false whenever the answer was
  truncated OR the content search skipped any entry -
  a metadata match on a skipped pack is still a row
  (its metadata answer is a registry-time fact), with
  null content facts, and the skip is named.

Honest boundaries, and the cost stated plainly: a
unified search pays P-191's cost in full - it reads
and verifies every ready pack in the (kind-narrowed)
estate, each under P-188's 16 MiB bound. P-190's
metadata search alone stays the cheap road. This
search writes nothing, registers nothing, imports
nothing, installs nothing, copies nothing and grants
nothing; signing and friend-instance exchange stay
declined - no key or transport machinery is banked.
There is no central store, no catalogue and no
creator profile here (VX-59). No migration: head
stays 0041.
"""

from __future__ import annotations

from runmal.hub import content_search as hub_content_search
from runmal.hub import registry as hub_registry
from runmal.hub import search as hub_search
from runmal.hub.registry import HubEntry

UNIFIED_SEARCH_SCHEMA = "runmal-p192-hub-unified-search-v1"

MAX_MATCHES = hub_search.MAX_MATCHES  # P-190's cap: one value, both sources carry it

MATCHED_BY_METADATA = "metadata"
MATCHED_BY_CONTENT = "content"
MATCHED_BY_BOTH = "both"
MATCHED_BY = frozenset({
    MATCHED_BY_METADATA, MATCHED_BY_CONTENT, MATCHED_BY_BOTH,
})

SEARCH_STATE_NO_MATCHES = "no_matches"
SEARCH_STATE_MATCHES = "matches"
SEARCH_STATE_MATCHES_TRUNCATED = "matches_truncated"
SEARCH_STATES = frozenset({
    SEARCH_STATE_NO_MATCHES, SEARCH_STATE_MATCHES,
    SEARCH_STATE_MATCHES_TRUNCATED,
})

NOTES = (
    "Pure read, owner scoped: only the caller's own "
    "entries are searched; this search stores, "
    "registers, removes, imports, installs, copies "
    "and writes nothing - it composes the banked hub "
    "metadata search (P-190) and pack-content search "
    "(P-191) over one query and one entry list, and "
    "both of their documents are embedded whole.",
    "Cost law: a unified search pays the content "
    "search's full cost - it reads and verifies every "
    "ready pack in the searched estate, each through "
    "its own layer's verified parse road and each "
    "under the browse size bound (max_browse_bytes in "
    "the embedded content search). The metadata search "
    "alone (P-190) stays the cheap road.",
    "matched_by names, per entry, which banked law "
    "matched: metadata (the query in the entry's "
    "registry fields), content (the query in a string "
    "value of the pack's verified payload), or both. "
    "A metadata-only match carries null occurrences, "
    "excerpt and verified checksum - no content fact "
    "is invented for an entry the content road did "
    "not match - and a content-only match carries an "
    "empty matched_fields, the metadata road's true "
    "answer for that entry.",
    "Cap honesty: each banked search returns at most "
    "100 matches and keeps its true total in its own "
    "document; this union is over the two returned "
    "lists, metadata_total_matches and "
    "content_total_matches carry the sources' true "
    "totals verbatim, and truncated - either source's "
    "truncation or this document's own cap - names "
    "every capped answer.",
    "Coverage honesty is the content search's, "
    "carried verbatim: entries_considered always "
    "equals entries_searched plus the skipped count "
    "in the embedded content search, every skipped "
    "entry is named there with its outcome, and "
    "coverage_complete is false whenever any entry "
    "was skipped or the answer was truncated. A "
    "skipped entry can still metadata-match: its "
    "metadata answer is a registry fact and is never "
    "erased by the content road's skip.",
    "A match is a literal match only, under each "
    "banked search's own law: there is no fuzzy, "
    "semantic, ranked or scored matching here, and "
    "this composition adds none.",
    "Signing and friend-instance exchange stay "
    "declined: no key or transport machinery is "
    "banked, and this search invents none. There is "
    "no central store, no catalogue and no creator "
    "profile on this road (the VX-59 sovereign "
    "shape).",
)


class HubUnifiedSearchError(ValueError):
    """A hub unified search request the law forbids."""


def _normalise_query(query) -> str:
    if not isinstance(query, str):
        raise HubUnifiedSearchError(
            "a hub unified search query is required")
    cleaned = query.strip()
    if not cleaned:
        raise HubUnifiedSearchError(
            "a hub unified search query is required")
    return cleaned


def _normalise_kind(kind) -> str | None:
    if kind is None:
        return None
    cleaned = kind.strip() if isinstance(kind, str) else kind
    if cleaned not in hub_registry.HUB_KINDS:
        raise HubUnifiedSearchError(
            "unknown hub kind: " + str(cleaned or "(empty)"))
    return cleaned


def unified_search_document(
    entries: list[HubEntry],
    query: str,
    kind: str | None = None,
) -> dict:
    """The unified hub search document for one owner's
    entries.

    ``entries`` is the owner's own entry list (the
    router hands over HubStore.list_for_owner for the
    caller; a foreign owner's entries are never in
    it). The query and kind are validated FIRST, by
    this module's own law, before either banked search
    runs - an empty or blank query and an unknown kind
    raise HubUnifiedSearchError, refused plainly, never
    treated as match-everything. The same entry list,
    cleaned query and kind are then handed to P-190's
    and P-191's search documents, which are embedded
    whole; the union merges their RETURNED matches by
    entry id, in store order, capped at MAX_MATCHES
    with the union's true total carried alongside.
    """
    cleaned = _normalise_query(query)
    cleaned_kind = _normalise_kind(kind)
    metadata_doc = hub_search.search_document(
        entries, cleaned, kind=cleaned_kind)
    content_doc = hub_content_search.content_search_document(
        entries, cleaned, kind=cleaned_kind)
    metadata_rows = {row["id"]: row for row in metadata_doc["matches"]}
    content_rows = {row["id"]: row for row in content_doc["matches"]}
    considered = [
        entry for entry in entries
        if cleaned_kind is None or entry.kind == cleaned_kind]
    merged: list[dict] = []
    for entry in considered:
        meta = metadata_rows.get(entry.id)
        content = content_rows.get(entry.id)
        if meta is None and content is None:
            continue
        base = dict(meta if meta is not None else content)
        if meta is not None and content is not None:
            matched_by = MATCHED_BY_BOTH
        elif meta is not None:
            matched_by = MATCHED_BY_METADATA
        else:
            matched_by = MATCHED_BY_CONTENT
        base["matched_by"] = matched_by
        base["metadata_match"] = meta is not None
        base["content_match"] = content is not None
        base["matched_fields"] = (
            list(meta["matched_fields"]) if meta is not None else [])
        if content is not None:
            base["occurrences"] = content["occurrences"]
            base["excerpt"] = content["excerpt"]
            base["verified_content_sha256"] = (
                content["verified_content_sha256"])
        else:
            base["occurrences"] = None
            base["excerpt"] = None
            base["verified_content_sha256"] = None
        merged.append(base)
    total = len(merged)
    truncated = bool(
        metadata_doc["truncated"] or content_doc["truncated"]
        or total > MAX_MATCHES)
    coverage_complete = bool(
        not truncated and content_doc["coverage_complete"])
    capped = merged[:MAX_MATCHES]
    capped_entries = []
    by_id = {entry.id: entry for entry in considered}
    for row in capped:
        entry = by_id.get(row["id"])
        if entry is not None:
            capped_entries.append(entry)
    list_doc = hub_registry.list_document(capped_entries)
    if total == 0:
        search_state = SEARCH_STATE_NO_MATCHES
    elif truncated:
        search_state = SEARCH_STATE_MATCHES_TRUNCATED
    else:
        search_state = SEARCH_STATE_MATCHES
    return {
        "schema": UNIFIED_SEARCH_SCHEMA,
        "query": cleaned,
        "kind": cleaned_kind,
        "search_state": search_state,
        "matches": capped,
        "match_count": len(capped),
        "total_matches": total,
        "truncated": truncated,
        "coverage_complete": coverage_complete,
        "metadata_match_count": sum(
            1 for row in merged if row["metadata_match"]),
        "content_match_count": sum(
            1 for row in merged if row["content_match"]),
        "both_count": sum(
            1 for row in merged
            if row["matched_by"] == MATCHED_BY_BOTH),
        "metadata_total_matches": metadata_doc["total_matches"],
        "content_total_matches": content_doc["total_matches"],
        "entries_considered": content_doc["entries_considered"],
        "entries_searched": content_doc["entries_searched"],
        "skipped_entries": content_doc["skipped_entries"],
        "metadata_search": metadata_doc,
        "content_search": content_doc,
        "list": list_doc,
        "kind_formats": dict(hub_registry.KIND_FORMATS),
        "notes": list(NOTES),
    }
