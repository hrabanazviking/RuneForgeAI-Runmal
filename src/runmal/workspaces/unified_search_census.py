"""Workspace unified search census (P-184, Part XI - DERIVED).

The roadmap gives Part XI one line only ("Workspaces -
the Companion That Works", P-169..P-186); this slice's
scope is derived from Runmal's own in-tree record - see
docs/WORKSPACE_UNIFIED_SEARCH_CENSUS_2026-11-09.md and
hidden_files/P184_SCOUT.md / P184_DESIGN.md.

What the derivation found: every banked census aggregates
a folder (P-174, P-181), an estate (P-171) or a history
(P-177) - none aggregates a SEARCH. P-182 banked the
unified search (one tree composed once, the filename and
content searches built from it, the union by path under
the matched_by law) and returns its capped match list
with only three union counts; nothing states the union's
own distribution - how its returned matches split by
matched_by, kind, extension, depth, hidden or escaping
status, how many bytes and occurrences they carry, or
how its skipped files split by outcome. P-183's record
names census surfaces over the unified search a lawful
future cell once P-182 is banked; P-182 IS banked in
this base. This module is that census, in the house
census pattern (P-171 / P-174 / P-177 / P-181): a pure
aggregate composing the owning surface verbatim,
classified under a closed law, counts summed from the
composed document's own fields:

- the unified document is P-182's, composed VERBATIM -
  resolve_chat_unified_search (one tree at P-176's
  MAX_DEPTH ceiling, both banked searches built from
  that tree, the union by path), embedded whole; there
  is no second walk, listing law, folder-state law,
  search law or scan here;
- the returned axis sums the document's RETURNED
  matches only (exactly its match_count): the
  matched_by split (name_only / content_only /
  both_match, summing exactly to match_count), the
  kind split under P-170's ENTRY_KINDS, hidden and
  escaping counts, extension counts from file-match
  NAMES only, total matched file bytes and the largest
  match, the total occurrence count, and counts by
  depth (segments below the composed subpath);
- the source axis carries P-182's own uncapped counts
  VERBATIM beside the returned sums (total_matches,
  the source name / content / both counts and both
  source totals), so a capped union is censused as
  capped: the two truths are stated side by side and
  neither is dressed as the other;
- the skip axis sums the document's skipped_files rows
  by their own outcomes under P-172's closed OUTCOMES
  law plus refused (P-180's name), with P-180's files
  arithmetic carried verbatim beside it;
- the answer is classified under the closed
  UNIFIED_SEARCH_CENSUS_STATES law: folder_not_ready /
  no_matches / name_only / content_only / mixed. A
  non-ready folder is DATA, never an error: P-182's
  union of it is empty, and the census of it is the
  honest zero document.

Honest boundaries: this census is a pure read over one
query's answer - it searches nothing itself, records
nothing (P-182 stores nothing, and no search-history
surface is invented here: a history would need a
recording write, not a composition), writes, edits and
deletes nothing, runs and launches nothing, watches
nothing and grants nothing - no tool, backend or
process inherits any access from a binding existing
(P-169's law, restated). Writes wait for the VX-57
guard; execution is VX-55/56 territory (P-027
absolute). Counts are a point-in-time judgement over
one composed search. No store, no migration: head
stays 0041.
"""

from __future__ import annotations

from runmal.workspaces import content as content_service
from runmal.workspaces import content_search as content_search_service
from runmal.workspaces import unified_search as unified_search_service
from runmal.workspaces.bindings import FOLDER_READY
from runmal.workspaces.listing import (
    KIND_DIRECTORY,
    KIND_FILE,
    KIND_OTHER,
    KIND_SYMLINK,
)

UNIFIED_SEARCH_CENSUS_SCHEMA = \
    "runmal-p184-workspace-unified-search-census-v1"

STATE_FOLDER_NOT_READY = "folder_not_ready"
STATE_NO_MATCHES = "no_matches"
STATE_NAME_ONLY = "name_only"
STATE_CONTENT_ONLY = "content_only"
STATE_MIXED = "mixed"
UNIFIED_SEARCH_CENSUS_STATES = frozenset({
    STATE_FOLDER_NOT_READY, STATE_NO_MATCHES,
    STATE_NAME_ONLY, STATE_CONTENT_ONLY, STATE_MIXED,
})

NO_EXTENSION = "(none)"

SKIP_OUTCOMES = (
    content_service.OUTCOME_BINARY,
    content_service.OUTCOME_OVERSIZE,
    content_service.OUTCOME_UNREADABLE,
    content_service.OUTCOME_FOLDER_NOT_READY,
    content_search_service.OUTCOME_REFUSED,
)

UNIFIED_SEARCH_CENSUS_NOTES = (
    "Pure read over one chat's unified search for one "
    "query: this census stores, records, binds, unbinds, "
    "writes, edits, deletes, runs and watches nothing - "
    "it composes the banked unified search (P-182) and "
    "aggregates its answer; no search history is kept "
    "by it or by the search it composes.",
    "The unified search document is P-182's, composed "
    "verbatim and embedded whole: one tree composed "
    "once at P-176's own maximum depth, both banked "
    "searches built from that same tree, the union by "
    "folder-relative path under the matched_by law "
    "(name / content / both) - no second walk, listing "
    "law, folder-state law, search law or scan exists "
    "here.",
    "Returned counts sum the composed document's "
    "RETURNED matches only and add up exactly: "
    "name_only + content_only + both_match always "
    "equals the returned match_count. The source counts "
    "beside them are P-182's own uncapped counts, "
    "carried verbatim - when a source ran past its cap "
    "the two truths differ, and both are stated.",
    "Partiality is P-182's own verdict, carried "
    "verbatim: truncated names every partial answer "
    "(a capped source, a skipped file, the union's own "
    "cap) and coverage_complete is its explicit twin - "
    "a capped census is never dressed as complete, "
    "and matches a capped source never returned are "
    "not counted here because they were never returned.",
    "Extension counts describe file-match names, not "
    "contents, and byte counts sum file matches only - "
    "other kinds carry no size rather than an invented "
    "one (P-174's law). A name-only match contributes "
    "no occurrence count: no content fact is invented "
    "for a file the content road did not read as a "
    "match (P-182's kept-apart law).",
    "A census grants nothing: no tool, backend or "
    "process inherits any access from a binding "
    "existing, and workspace writes wait for the "
    "tool-calling guard (VX-57) while execution stays "
    "declined (P-027: content is data, never code).",
)


def _extension_of(name: str) -> str:
    if "." not in name:
        return NO_EXTENSION
    suffix = name.rsplit(".", 1)[1]
    if not suffix:
        return NO_EXTENSION
    return suffix.lower()


def _depth_of(path: str, subpath: str) -> int:
    relative = path
    if subpath:
        prefix = subpath + "/"
        if path.startswith(prefix):
            relative = path[len(prefix):]
        elif path == subpath:
            relative = ""
    if not relative:
        return 0
    return relative.count("/") + 1


def build_unified_search_census(unified_document: dict) -> dict:
    """The census document for one P-182 document.

    Sums only the unified document's own returned-match
    and skipped-file fields; the document is embedded
    whole, and its own uncapped counts ride verbatim
    beside the returned sums. A non-ready folder (P-169's
    law, carried by the search) is the folder_not_ready
    zero document - data, never an error.
    """
    matches = unified_document["matches"]
    subpath = unified_document["subpath"]
    folder_state = unified_document["folder_state"]

    name_only_count = 0
    content_only_count = 0
    both_match_count = 0
    has_name = False
    has_content = False
    kind_counts = {
        KIND_DIRECTORY: 0, KIND_FILE: 0,
        KIND_SYMLINK: 0, KIND_OTHER: 0}
    hidden_count = 0
    escaping_count = 0
    extension_counts: dict[str, int] = {}
    total_match_bytes = 0
    largest_match = None
    total_occurrences = 0
    depth_counts: dict[str, int] = {}
    deepest_level = 0

    for match in matches:
        matched_by = match["matched_by"]
        if matched_by == unified_search_service.MATCHED_BY_NAME:
            name_only_count += 1
        elif matched_by == unified_search_service.MATCHED_BY_CONTENT:
            content_only_count += 1
        elif matched_by == unified_search_service.MATCHED_BY_BOTH:
            both_match_count += 1
        if match["name_match"]:
            has_name = True
        if match["content_match"]:
            has_content = True
        kind = match["kind"]
        if kind in kind_counts:
            kind_counts[kind] += 1
        if match["hidden"]:
            hidden_count += 1
        if match["escapes"]:
            escaping_count += 1
        if match["occurrences"] is not None:
            total_occurrences += match["occurrences"]
        depth = _depth_of(match["path"], subpath)
        depth_counts[str(depth)] = depth_counts.get(str(depth), 0) + 1
        if depth > deepest_level:
            deepest_level = depth
        if kind == KIND_FILE:
            size = match["size_bytes"] or 0
            total_match_bytes += size
            ext = _extension_of(match["name"])
            extension_counts[ext] = extension_counts.get(ext, 0) + 1
            if largest_match is None or \
                    size > largest_match["size_bytes"]:
                largest_match = {
                    "name": match["name"], "path": match["path"],
                    "size_bytes": size, "matched_by": matched_by}

    skipped_files = unified_document["skipped_files"]
    skip_outcome_counts = {outcome: 0 for outcome in SKIP_OUTCOMES}
    for skipped in skipped_files:
        outcome = skipped["outcome"]
        if outcome in skip_outcome_counts:
            skip_outcome_counts[outcome] += 1

    if folder_state != FOLDER_READY:
        census_state = STATE_FOLDER_NOT_READY
    elif not matches:
        census_state = STATE_NO_MATCHES
    elif has_name and has_content:
        census_state = STATE_MIXED
    elif has_name:
        census_state = STATE_NAME_ONLY
    else:
        census_state = STATE_CONTENT_ONLY

    return {
        "schema": UNIFIED_SEARCH_CENSUS_SCHEMA,
        "census_state": census_state,
        "unified_search_document": unified_document,
        "binding_document": unified_document["binding_document"],
        "folder_state": folder_state,
        "subpath": subpath,
        "query": unified_document["query"],
        "match_count": len(matches),
        "name_only_count": name_only_count,
        "content_only_count": content_only_count,
        "both_match_count": both_match_count,
        "total_matches": unified_document["total_matches"],
        "source_name_match_count":
            unified_document["name_match_count"],
        "source_content_match_count":
            unified_document["content_match_count"],
        "source_both_count": unified_document["both_count"],
        "name_total_matches": unified_document["name_total_matches"],
        "content_total_matches":
            unified_document["content_total_matches"],
        "directory_match_count": kind_counts[KIND_DIRECTORY],
        "file_match_count": kind_counts[KIND_FILE],
        "symlink_match_count": kind_counts[KIND_SYMLINK],
        "other_match_count": kind_counts[KIND_OTHER],
        "kind_counts": kind_counts,
        "hidden_count": hidden_count,
        "escaping_count": escaping_count,
        "extension_counts": dict(sorted(extension_counts.items())),
        "total_match_bytes": total_match_bytes,
        "largest_match": largest_match,
        "total_occurrences": total_occurrences,
        "depth_counts": depth_counts,
        "deepest_level": deepest_level,
        "files_considered": unified_document["files_considered"],
        "files_searched": unified_document["files_searched"],
        "skipped_count": len(skipped_files),
        "skip_outcome_counts": skip_outcome_counts,
        "max_matches": unified_document["max_matches"],
        "max_content_bytes": unified_document["max_content_bytes"],
        "truncated": unified_document["truncated"],
        "coverage_complete": unified_document["coverage_complete"],
        "notes": list(UNIFIED_SEARCH_CENSUS_NOTES),
    }


async def resolve_chat_unified_search_census(session, store,
                                             user_id: str,
                                             chat_id: str,
                                             query: str,
                                             subpath: str = ""):
    """The unified search census for one chat, or None.

    The unified search is P-182's resolve composed
    verbatim: the query is validated by P-182 BEFORE the
    tree is composed (a blank or non-string query raises
    P-182's WorkspaceUnifiedSearchError unchanged), None
    exactly when P-182's resolve is None (the chat is
    missing or foreign - existence never leaks - or the
    chat is unbound), and a refused subpath raises
    P-170's own WorkspaceListingError unchanged.
    """
    unified_document = \
        await unified_search_service.resolve_chat_unified_search(
            session, store, user_id, chat_id, query, subpath)
    if unified_document is None:
        return None
    return build_unified_search_census(unified_document)


__all__ = [
    "NO_EXTENSION", "SKIP_OUTCOMES", "STATE_CONTENT_ONLY",
    "STATE_FOLDER_NOT_READY", "STATE_MIXED", "STATE_NAME_ONLY",
    "STATE_NO_MATCHES", "UNIFIED_SEARCH_CENSUS_NOTES",
    "UNIFIED_SEARCH_CENSUS_SCHEMA",
    "UNIFIED_SEARCH_CENSUS_STATES",
    "build_unified_search_census",
    "resolve_chat_unified_search_census",
]
