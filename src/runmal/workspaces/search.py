"""Workspace filename search (P-178, Part XI - DERIVED).

P-176 banked the folder tree and named this cell in its
own record, twice: "Content search and filename search
over the tree" stand named open in its slice doc and its
carried-forward list. P-172 banked the read of one named
file - and presupposes the caller already knows the
file's path. In a bound folder deeper than one level
there was no way to FIND a file by name. This module is
the filename half of that named-open cell, in its
smallest honest form:

- the tree is P-176's, composed VERBATIM -
  resolve_chat_tree unchanged, its document embedded
  whole in this one, its nodes the only entries judged.
  There is no second walk, no second listing law, no
  second folder-state law and no second scan here;
- a match is a NAME match only: the query, casefolded,
  as a substring of the entry's own name. No file is
  opened, no content is read, no path component other
  than the name itself is matched;
- only EXPANDED nodes are searched: a directory the
  tree left unexpanded (depth cap, node cap, refused
  expansion) is never dressed as searched-and-empty -
  the tree's own truncated flag rides verbatim and the
  notes state the coverage plainly;
- each match carries the node's P-170 fields verbatim
  plus its path relative to the bound folder - exactly
  the input P-172's content read consumes.

Honest boundaries: this search reads directory entries
only, through P-176/P-170 - it opens no file (content
search, which would have to open files, stays named
open), writes, edits and deletes nothing, runs and
launches nothing, watches nothing and grants nothing
(P-169's law, restated). Writes wait for the VX-57
guard; execution is VX-55/56 territory (P-027 absolute).
No store, no migration: head stays 0041.
"""

from __future__ import annotations

from runmal.workspaces import tree as tree_service

SEARCH_SCHEMA = "runmal-p178-workspace-search-v1"

MAX_MATCHES = 100

SEARCH_NOTES = (
    "Pure read over one chat's bound folder: this "
    "search stores, binds, unbinds, writes, edits, "
    "deletes, runs and watches nothing, and opens no "
    "file - the per-file text read is a separate Part "
    "XI road (P-172), and content search stays named "
    "open.",
    "The searched tree is P-176's document composed "
    "verbatim at its own maximum depth and embedded "
    "whole: its path law, kind law, honest sizes and "
    "folder state are re-judged at this read by "
    "P-176/P-170 themselves - no second listing law, "
    "folder-state law, walk or scan exists here.",
    "A match is a name match only: the query, "
    "casefolded, as a substring of an entry's own "
    "name. No file content and no other path "
    "component is ever matched, and each match "
    "carries its folder-relative path - the input "
    "P-172's read consumes.",
    "Coverage is the EXPANDED tree only: a directory "
    "left unexpanded by P-176's caps or by a refused "
    "expansion was not searched, and truncated names "
    "every partial answer - the tree's truncation "
    "or the stated match cap.",
    "A search grants nothing: no tool, backend or "
    "process inherits any access from a binding "
    "existing, and workspace writes wait for the "
    "tool-calling guard (VX-57) while execution "
    "stays declined (P-027: content is data, never "
    "code).",
)


class WorkspaceSearchError(ValueError):
    """A search request the stated law forbids."""


def _normalise_query(query) -> str:
    if not isinstance(query, str):
        raise WorkspaceSearchError("a search query is required")
    cleaned = query.strip()
    if not cleaned:
        raise WorkspaceSearchError("a search query is required")
    return cleaned


def _join(prefix: str, name: str) -> str:
    return f"{prefix}/{name}" if prefix else name

def _all_nodes(node):
    yield node
    for child in node.get("children") or []:
        yield from _all_nodes(child)

def build_search(tree_document: dict, query: str) -> dict:
    """The search document for one resolved tree document.

    ``tree_document`` is P-176's tree document, composed
    verbatim and embedded whole; matches are filtered
    from its expanded nodes only, depth-first in the
    tree's own order. Raises WorkspaceSearchError for
    an empty or blank query - refused plainly, never
    treated as match-everything.
    """
    cleaned = _normalise_query(query)
    needle = cleaned.casefold()
    subpath = tree_document["subpath"]
    found = []

    def walk(children, prefix: str) -> None:
        for node in children or []:
            path = _join(prefix, node["name"])
            if needle in node["name"].casefold():
                found.append({
                    "name": node["name"],
                    "kind": node["kind"],
                    "size_bytes": node["size_bytes"],
                    "hidden": node["hidden"],
                    "escapes": node["escapes"],
                    "path": path,
                })
            if node.get("expanded"):
                walk(node.get("children"), path)

    root = tree_document["tree"]
    if root.get("expanded"):
        walk(root.get("children"), subpath)
    partial = any(
        node["kind"] == "directory" and not node.get("expanded")
        for node in _all_nodes(root))
    truncated = bool(tree_document["truncated"]) or partial or \
        len(found) > MAX_MATCHES
    return {
        "schema": SEARCH_SCHEMA,
        "tree_document": tree_document,
        "binding_document": tree_document["binding_document"],
        "folder_state": tree_document["folder_state"],
        "subpath": subpath,
        "query": cleaned,
        "matches": found[:MAX_MATCHES],
        "match_count": min(len(found), MAX_MATCHES),
        "total_matches": len(found),
        "truncated": truncated,
        "notes": list(SEARCH_NOTES),
    }


async def resolve_chat_search(session, store, user_id: str,
                              chat_id: str, query: str,
                              subpath: str = ""):
    """The filename search for one chat, or None.

    The query is validated BEFORE the tree is composed
    (fail fast on the caller's own error). None exactly
    when P-176's resolve_chat_tree is None (the chat is
    missing or foreign - existence never leaks - or the
    chat is unbound). A refused subpath raises P-170's
    own WorkspaceListingError unchanged. The tree is
    composed at P-176's MAX_DEPTH, its stated ceiling.
    """
    cleaned = _normalise_query(query)
    tree_document = await tree_service.resolve_chat_tree(
        session, store, user_id, chat_id, subpath,
        tree_service.MAX_DEPTH)
    if tree_document is None:
        return None
    return build_search(tree_document, cleaned)


__all__ = [
    "MAX_MATCHES", "SEARCH_NOTES", "SEARCH_SCHEMA",
    "WorkspaceSearchError", "build_search", "resolve_chat_search",
]
