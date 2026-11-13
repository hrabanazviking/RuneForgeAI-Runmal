"""Hub search over entries (P-190, Part XII - DERIVED).

P-187 landed the hub registry: an owner-scoped index of
the pack artefacts an owner holds, whose list road
filters by kind only. P-188 landed per-entry browse and
P-189 the estate census; P-189's banking record named
hub search over entries open for a later Part XII slice
and fixed the order (census precedes search, the house
order of P-171 before P-178). This module is that search:
a literal text search over the ENTRY DATA the registry
itself holds, and nothing else.

- A match is a LITERAL match only: the query, casefolded,
  as a substring of a searched field's casefolded value
  (the P-178 match law). The searched fields are the
  closed SEARCH_FIELDS law - title, locator, note, kind,
  and the format string KIND_FORMATS maps the kind to -
  and each row carries matched_fields, the fields that
  matched, in that law's order.
- NOT searched, stated plainly: pack CONTENTS (this
  surface opens no pack - content lives behind P-188's
  per-entry browse and each pack layer's own inspect
  road), the claimed content_sha256 (caller-claimed data,
  and not search text), and id / owner_id / created_at.
  There is no fuzzy, semantic, ranked or scored matching
  here: no such machinery is banked, and none is faked.
- Composition is verbatim: the matched entries, in store
  order, are handed to P-187's list_document and that
  document is embedded whole - the rows are its own rows
  (entry verbatim, locator_state judged live by P-187
  itself) plus matched_fields, and the by-kind and
  by-locator-state counts are the registry's own
  arithmetic over the matched set.
- Cap honesty (the P-178 law): at most MAX_MATCHES rows
  are returned; total_matches carries the true total and
  truncated names a capped answer, which is classified
  matches_truncated under the closed SEARCH_STATES law
  and never dressed as complete.

Honest boundaries: search is a pure read over registry
metadata - it opens no pack, reads no file at any locator
(the locator state is P-187's stat-only judgement),
writes nothing, imports nothing, installs nothing,
copies nothing and grants nothing. Signing and
friend-instance exchange stay declined - no key or
transport machinery is banked. There is no central
store, no catalogue and no creator profile here (VX-59).
No migration: head stays 0041.
"""

from __future__ import annotations

from runmal.hub import registry as hub_registry
from runmal.hub.registry import HubEntry

SEARCH_SCHEMA = "runmal-p190-hub-search-v1"

MAX_MATCHES = 100

FIELD_TITLE = "title"
FIELD_LOCATOR = "locator"
FIELD_NOTE = "note"
FIELD_KIND = "kind"
FIELD_FORMAT = "format"
SEARCH_FIELDS = (
    FIELD_TITLE, FIELD_LOCATOR, FIELD_NOTE,
    FIELD_KIND, FIELD_FORMAT,
)

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
    "and writes nothing, and it opens no pack.",
    "A match is a literal match only: the query, "
    "casefolded, as a substring of a searched field's "
    "casefolded value. The searched fields are title, "
    "locator, note, kind and format; pack contents, "
    "the claimed content checksum, ids and timestamps "
    "are never searched, and there is no fuzzy, "
    "semantic, ranked or scored matching here.",
    "The list embedded here is P-187's list document "
    "composed verbatim over the returned (capped) "
    "matched entries - its count, by-kind and "
    "by-locator-state arithmetic is the registry's "
    "own, never recomputed under a second law, so "
    "list.count always equals match_count.",
    "At most 100 matches are returned: total_matches "
    "carries the true total and truncated names a "
    "capped answer, which is never dressed as "
    "complete.",
    "The by_matched_field axis sums the returned "
    "rows' matched_fields: a row matching two fields "
    "counts under both, so the axis sums fields, "
    "not rows.",
    "Signing and friend-instance exchange stay "
    "declined: no key or transport machinery is "
    "banked, and this search invents none. There is "
    "no central store, no catalogue and no creator "
    "profile on this road (the VX-59 sovereign "
    "shape).",
)


class HubSearchError(ValueError):
    """A hub search request the stated law forbids."""


def _normalise_query(query) -> str:
    if not isinstance(query, str):
        raise HubSearchError("a hub search query is required")
    cleaned = query.strip()
    if not cleaned:
        raise HubSearchError("a hub search query is required")
    return cleaned


def _field_values(entry: HubEntry) -> dict:
    return {
        FIELD_TITLE: entry.title,
        FIELD_LOCATOR: entry.locator,
        FIELD_NOTE: entry.note,
        FIELD_KIND: entry.kind,
        FIELD_FORMAT: hub_registry.KIND_FORMATS.get(entry.kind, ""),
    }


def search_document(
    entries: list[HubEntry],
    query: str,
    kind: str | None = None,
) -> dict:
    """The hub search document for one owner's entries.

    ``entries`` is the owner's own entry list (the router
    hands over HubStore.list_for_owner for the caller; a
    foreign owner's entries are never in it). ``kind``,
    when given, narrows the estate before searching (the
    list road's own filter law); an unknown kind raises
    HubSearchError, as does an empty or blank query -
    refused plainly, never treated as match-everything.
    Matches keep store order and are capped at
    MAX_MATCHES with the true total carried alongside.
    """
    cleaned = _normalise_query(query)
    cleaned_kind = None
    if kind is not None:
        cleaned_kind = kind.strip() if isinstance(kind, str) else kind
        if cleaned_kind not in hub_registry.HUB_KINDS:
            raise HubSearchError(
                "unknown hub kind: " + str(cleaned_kind or "(empty)"))
    needle = cleaned.casefold()
    matched: list[tuple[HubEntry, list[str]]] = []
    for entry in entries:
        if cleaned_kind is not None and entry.kind != cleaned_kind:
            continue
        values = _field_values(entry)
        fields = [
            field for field in SEARCH_FIELDS
            if needle in values[field].casefold()]
        if fields:
            matched.append((entry, fields))
    total = len(matched)
    truncated = total > MAX_MATCHES
    capped = matched[:MAX_MATCHES]
    list_doc = hub_registry.list_document([row for row, _ in capped])
    fields_by_id = {entry.id: fields for entry, fields in capped}
    rows = []
    by_matched_field = {field: 0 for field in SEARCH_FIELDS}
    for row in list_doc["entries"]:
        out = dict(row)
        out["matched_fields"] = fields_by_id.get(row["id"], [])
        rows.append(out)
        for field in out["matched_fields"]:
            by_matched_field[field] += 1
    if total == 0:
        search_state = SEARCH_STATE_NO_MATCHES
    elif truncated:
        search_state = SEARCH_STATE_MATCHES_TRUNCATED
    else:
        search_state = SEARCH_STATE_MATCHES
    return {
        "schema": SEARCH_SCHEMA,
        "query": cleaned,
        "kind": cleaned_kind,
        "search_state": search_state,
        "matches": rows,
        "match_count": len(rows),
        "total_matches": total,
        "truncated": truncated,
        "by_matched_field": by_matched_field,
        "searched_fields": list(SEARCH_FIELDS),
        "list": list_doc,
        "kind_formats": dict(hub_registry.KIND_FORMATS),
        "notes": list(NOTES),
    }
