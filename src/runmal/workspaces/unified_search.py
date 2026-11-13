"""Workspace unified search (P-182, Part XI - DERIVED).

P-178 banked the filename search and P-180 the content
search, both over P-176's tree - as two disjoint roads.
An owner hunting one file had to run both, over two
separately composed trees (two point-in-time judgements
that can disagree), and merge the answers by hand; no
document ever said, for one path, whether the NAME
spoke, the CONTENT spoke, or both did. This module is
that composing cell, in the house census pattern - a
pure read over banked documents, no new search law:

- ONE tree: P-176's tree is composed once, verbatim, at
  its own MAX_DEPTH ceiling and embedded whole; both
  banked searches are built from THAT document, so the
  name answer and the content answer describe the same
  walk of the same folder at the same moment;
- the two searches are P-178's build_search and P-180's
  build_content_search, composed VERBATIM - their
  documents are embedded whole, their match laws are
  unchanged (a name match is the query casefolded in
  the entry's own name; a content match is the query
  casefolded in the file's decoded content, read only
  through P-172 under its stated cap), and there is no
  second walk, listing law, folder-state law or scan;
- the union is by folder-relative path: every returned
  path appears once, carrying matched_by under the
  closed law (name / content / both), the name fields
  verbatim, and - for content matches - the occurrence
  count and bounded excerpt verbatim (None for a
  name-only match: no content fact is invented);
- cap honesty: each banked search returns at most its
  own MAX_MATCHES (100, the same value both carry) and
  keeps its true total in total_matches. The union is
  over the two RETURNED match lists, exactly as banked;
  both source totals ride in this document as
  name_total_matches / content_total_matches, and when
  either source ran past its cap its truncated flag -
  and therefore this document's - is true: a capped
  union is named partial, never dressed as complete;
- file honesty is P-180's, carried verbatim:
  files_considered == files_searched + skipped, every
  skip named with its P-172 outcome or refused, and a
  file P-172 could not search can still NAME-match -
  the name answer is a tree-time fact and is never
  erased by the content road's refusal.

Honest boundaries: this search writes, edits and
deletes nothing, runs and launches nothing, watches
nothing and grants nothing (P-169's law, restated).
Writes wait for the VX-57 guard; execution is VX-55/56
territory (P-027 absolute). No store, no migration:
head stays 0041.
"""

from __future__ import annotations

from runmal.workspaces import content_search as content_search_service
from runmal.workspaces import search as search_service
from runmal.workspaces import tree as tree_service

UNIFIED_SEARCH_SCHEMA = "runmal-p182-workspace-unified-search-v1"

MAX_MATCHES = 100  # P-178/P-180's match cap, carried verbatim

MATCHED_BY_NAME = "name"
MATCHED_BY_CONTENT = "content"
MATCHED_BY_BOTH = "both"
MATCHED_BY = frozenset({
    MATCHED_BY_NAME, MATCHED_BY_CONTENT, MATCHED_BY_BOTH})

UNIFIED_SEARCH_NOTES = (
    "Pure read over one chat's bound folder: this "
    "search stores, binds, unbinds, writes, edits, "
    "deletes, runs and watches nothing - it composes "
    "the banked filename search (P-178) and content "
    "search (P-180) over ONE tree composed once.",
    "The tree is P-176's document composed verbatim at "
    "its own maximum depth and embedded whole; both "
    "embedded search documents were built from that "
    "same tree, so the name answer and the content "
    "answer describe the same walk - no second walk, "
    "listing law, folder-state law or scan exists here.",
    "matched_by names, per path, which banked law "
    "matched: name (the query in the entry's own name), "
    "content (the query in the file's decoded text, "
    "read only through P-172 under its stated cap), or "
    "both. A name-only match carries no occurrence "
    "count and no excerpt - no content fact is invented "
    "for a file the content road did not read as a match.",
    "Cap honesty: each banked search returns at most "
    "100 matches and keeps its true total in its own "
    "document; this union is over the two returned "
    "lists, name_total_matches and content_total_matches "
    "carry the sources' true totals verbatim, and "
    "truncated - the sources' truncation, any skipped "
    "file, or this document's own cap - names every "
    "partial answer, with coverage_complete its twin.",
    "File honesty is P-180's, carried verbatim: "
    "files_considered always equals files_searched "
    "plus the skipped count, every skipped file is "
    "named with its outcome, and a file the content "
    "road could not search can still name-match - the "
    "name answer is a fact of the composed tree and "
    "is never erased by a content refusal.",
    "A search grants nothing: no tool, backend or "
    "process inherits any access from a binding "
    "existing, and workspace writes wait for the "
    "tool-calling guard (VX-57) while execution stays "
    "declined (P-027: content is data, never code).",
)


class WorkspaceUnifiedSearchError(ValueError):
    """A unified search request the stated law forbids."""


def _normalise_query(query) -> str:
    if not isinstance(query, str):
        raise WorkspaceUnifiedSearchError(
            "a search query is required")
    cleaned = query.strip()
    if not cleaned:
        raise WorkspaceUnifiedSearchError(
            "a search query is required")
    return cleaned


def _join(prefix: str, name: str) -> str:
    return f"{prefix}/{name}" if prefix else name


def _tree_order(tree_document: dict) -> dict:
    """Depth-first position of every expanded node's path.

    The walk is P-178/P-180's own coverage walk over the
    composed tree document (expanded nodes only, the
    tree's own order); it judges nothing and reads
    nothing - it only numbers the paths the two banked
    searches could return, so the union can ride in the
    tree's own order.
    """
    order: dict[str, int] = {}

    def walk(children, prefix: str) -> None:
        for node in children or []:
            path = _join(prefix, node["name"])
            order[path] = len(order)
            if node.get("expanded"):
                walk(node.get("children"), path)

    root = tree_document["tree"]
    if root.get("expanded"):
        walk(root.get("children"), tree_document["subpath"])
    return order


def build_unified_search(tree_document: dict, query: str) -> dict:
    """The unified search document for one resolved tree.

    ``tree_document`` is P-176's tree document, composed
    verbatim and embedded whole; P-178's build_search
    and P-180's build_content_search are built from
    THAT document and embedded whole themselves. The
    union merges their RETURNED matches by path, in
    the tree's own depth-first order. Raises
    WorkspaceUnifiedSearchError for an empty or blank
    query - refused plainly, never treated as
    match-everything.
    """
    cleaned = _normalise_query(query)
    name_document = search_service.build_search(
        tree_document, cleaned)
    content_document = content_search_service.build_content_search(
        tree_document, cleaned)

    by_path: dict[str, dict] = {}
    for match in name_document["matches"]:
        by_path[match["path"]] = {
            "name": match["name"],
            "kind": match["kind"],
            "size_bytes": match["size_bytes"],
            "hidden": match["hidden"],
            "escapes": match["escapes"],
            "path": match["path"],
            "matched_by": MATCHED_BY_NAME,
            "name_match": True,
            "content_match": False,
            "occurrences": None,
            "excerpt": None,
        }
    for match in content_document["matches"]:
        entry = by_path.get(match["path"])
        if entry is None:
            by_path[match["path"]] = {
                "name": match["name"],
                "kind": match["kind"],
                "size_bytes": match["size_bytes"],
                "hidden": match["hidden"],
                "escapes": match["escapes"],
                "path": match["path"],
                "matched_by": MATCHED_BY_CONTENT,
                "name_match": False,
                "content_match": True,
                "occurrences": match["occurrences"],
                "excerpt": match["excerpt"],
            }
        else:
            entry["matched_by"] = MATCHED_BY_BOTH
            entry["content_match"] = True
            entry["occurrences"] = match["occurrences"]
            entry["excerpt"] = match["excerpt"]

    order = _tree_order(tree_document)
    merged = sorted(
        by_path.values(),
        key=lambda entry: order.get(entry["path"], len(order)))
    truncated = bool(name_document["truncated"]) or \
        bool(content_document["truncated"]) or \
        len(merged) > MAX_MATCHES
    return {
        "schema": UNIFIED_SEARCH_SCHEMA,
        "tree_document": tree_document,
        "name_search_document": name_document,
        "content_search_document": content_document,
        "binding_document": tree_document["binding_document"],
        "folder_state": tree_document["folder_state"],
        "subpath": tree_document["subpath"],
        "query": cleaned,
        "matches": merged[:MAX_MATCHES],
        "match_count": min(len(merged), MAX_MATCHES),
        "total_matches": len(merged),
        "name_match_count": sum(
            1 for entry in merged if entry["name_match"]),
        "content_match_count": sum(
            1 for entry in merged if entry["content_match"]),
        "both_count": sum(
            1 for entry in merged
            if entry["matched_by"] == MATCHED_BY_BOTH),
        "name_total_matches": name_document["total_matches"],
        "content_total_matches": content_document["total_matches"],
        "files_considered": content_document["files_considered"],
        "files_searched": content_document["files_searched"],
        "skipped_files": content_document["skipped_files"],
        "max_matches": MAX_MATCHES,
        "max_content_bytes": content_document["max_content_bytes"],
        "truncated": truncated,
        "coverage_complete": not truncated,
        "notes": list(UNIFIED_SEARCH_NOTES),
    }


async def resolve_chat_unified_search(session, store, user_id: str,
                                      chat_id: str, query: str,
                                      subpath: str = ""):
    """The unified search for one chat, or None.

    The query is validated BEFORE the tree is composed
    (fail fast on the caller's own error). None exactly
    when P-176's resolve_chat_tree is None (the chat is
    missing or foreign - existence never leaks - or the
    chat is unbound). A refused subpath raises P-170's
    own WorkspaceListingError unchanged. The tree is
    composed ONCE, at P-176's MAX_DEPTH, its stated
    ceiling, and both banked searches build from it.
    """
    cleaned = _normalise_query(query)
    tree_document = await tree_service.resolve_chat_tree(
        session, store, user_id, chat_id, subpath,
        tree_service.MAX_DEPTH)
    if tree_document is None:
        return None
    return build_unified_search(tree_document, cleaned)


__all__ = [
    "MATCHED_BY", "MATCHED_BY_BOTH", "MATCHED_BY_CONTENT",
    "MATCHED_BY_NAME", "MAX_MATCHES", "UNIFIED_SEARCH_NOTES",
    "UNIFIED_SEARCH_SCHEMA", "WorkspaceUnifiedSearchError",
    "build_unified_search", "resolve_chat_unified_search",
]
