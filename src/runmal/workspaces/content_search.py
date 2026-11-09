"""Workspace content search (P-180, Part XI - DERIVED).

P-176 banked the folder tree, P-172 the read of one named
file, and P-178 the filename search over the tree - and
each of them named this cell open in its own record:
content search, which would have to open files under a
new partial-read honesty law. This module is that cell,
with the honesty law stated up front:

- coverage is P-176's tree composed VERBATIM at its own
  MAX_DEPTH ceiling, embedded whole - only its EXPANDED
  nodes are candidates, exactly as at P-178; a directory
  left unexpanded was not searched, and the document
  says so;
- each candidate file is read ONLY through P-172's own
  build_content_read, under its stated cap
  (MAX_CONTENT_BYTES, carried here as data): a file over
  the cap is not searched at all - never searched in
  part, never silently truncated - it is named in
  skipped_files with P-172's own outcome;
- no silent omission: every candidate file node ends as
  a match, a counted searched non-match, or a named skip
  (binary / oversize / unreadable / folder_not_ready, or
  refused - P-172's own refusal at the moment of use,
  the two-moment race the tree walk cannot see);
- partial is named partial: truncated is set by the
  tree's own truncation, by any unexpanded directory in
  the composed document, by any skip, or by the match
  cap, and coverage_complete carries the same truth as
  explicit data;
- a match is a CONTENT match only: the query, casefolded,
  as a substring of the file's decoded strict-UTF-8
  content - never the name (P-178's road), never a path
  component. Each match carries the node's fields
  verbatim plus its folder-relative path (the input
  P-172's read consumes), the occurrence count in that
  file, and one bounded excerpt around the first
  occurrence, sliced verbatim from P-172's content.

Only kind=file tree nodes are candidates: directories,
symlinks (never followed for content, P-172's law) and
other kinds hold no readable text under any banked law
and are visible as themselves in the embedded tree.

Honest boundaries: this search writes, edits and
deletes nothing, runs and launches nothing, watches
nothing and grants nothing (P-169's law, restated).
Writes wait for the VX-57 guard; execution is VX-55/56
territory (P-027 absolute). No store, no migration:
head stays 0041.
"""

from __future__ import annotations

from runmal.workspaces import content as content_service
from runmal.workspaces import tree as tree_service
from runmal.workspaces.listing import KIND_FILE

CONTENT_SEARCH_SCHEMA = "runmal-p180-workspace-content-search-v1"

MAX_MATCHES = 100  # P-178's match cap, carried verbatim
EXCERPT_CONTEXT = 40  # characters either side of a first match
OUTCOME_REFUSED = "refused"  # P-172 refused at the moment of use

CONTENT_SEARCH_NOTES = (
    "Pure read over one chat's bound folder: this "
    "search stores, binds, unbinds, writes, edits, "
    "deletes, runs and watches nothing - the per-file "
    "text read is P-172's road, composed verbatim for "
    "every candidate file.",
    "Coverage is the EXPANDED tree only, composed at "
    "P-176's maximum depth and embedded whole: a "
    "directory left unexpanded by the tree's caps or "
    "by a refused expansion was not searched, and "
    "truncated names every partial answer - the "
    "tree's truncation, any skipped file, or the "
    "stated match cap.",
    "Per-file honesty: a file is read only under "
    "P-172's stated byte cap (max_content_bytes in "
    "this document). An oversize file is not searched "
    "at all - never in part - and a binary, oversize, "
    "unreadable or refused file is named in "
    "skipped_files with its outcome, never silently "
    "omitted: files_considered always equals "
    "files_searched plus the skipped count.",
    "A match is a content match only: the query, "
    "casefolded, as a substring of the file's decoded "
    "text - never its name and never a path component. "
    "Each match carries its folder-relative path, its "
    "occurrence count, and one bounded excerpt around "
    "the first occurrence, quoted verbatim.",
    "A search grants nothing: no tool, backend or "
    "process inherits any access from a binding "
    "existing, and workspace writes wait for the "
    "tool-calling guard (VX-57) while execution "
    "stays declined (P-027: content is data, never "
    "code).",
)


class WorkspaceContentSearchError(ValueError):
    """A content search request the stated law forbids."""


def _normalise_query(query) -> str:
    if not isinstance(query, str):
        raise WorkspaceContentSearchError(
            "a search query is required")
    cleaned = query.strip()
    if not cleaned:
        raise WorkspaceContentSearchError(
            "a search query is required")
    return cleaned


def _join(prefix: str, name: str) -> str:
    return f"{prefix}/{name}" if prefix else name


def _all_nodes(node):
    yield node
    for child in node.get("children") or []:
        yield from _all_nodes(child)


def _candidates(tree_document: dict):
    """File nodes of the expanded tree, depth-first."""
    found = []

    def walk(children, prefix: str) -> None:
        for node in children or []:
            path = _join(prefix, node["name"])
            if node["kind"] == KIND_FILE:
                found.append((node, path))
            if node.get("expanded"):
                walk(node.get("children"), path)

    root = tree_document["tree"]
    if root.get("expanded"):
        walk(root.get("children"), tree_document["subpath"])
    return found


def build_content_search(tree_document: dict, query: str) -> dict:
    """The content search document for one resolved tree.

    ``tree_document`` is P-176's tree document, composed
    verbatim and embedded whole; every file node in its
    expanded coverage is read through P-172's own
    build_content_read at the moment of this search.
    Raises WorkspaceContentSearchError for an empty or
    blank query - refused plainly, never treated as
    match-everything.
    """
    cleaned = _normalise_query(query)
    needle = cleaned.casefold()
    binding_document = tree_document["binding_document"]
    folder_path = binding_document["binding"]["folder_path"]
    matches = []
    skipped = []
    searched = 0
    for node, path in _candidates(tree_document):
        try:
            read_doc = content_service.build_content_read(
                binding_document, folder_path, path)
        except content_service.WorkspaceContentError:
            skipped.append({
                "name": node["name"], "path": path,
                "size_bytes": node["size_bytes"],
                "outcome": OUTCOME_REFUSED})
            continue
        if read_doc["outcome"] != content_service.OUTCOME_OK:
            size = read_doc["size_bytes"]
            skipped.append({
                "name": node["name"], "path": path,
                "size_bytes": size if size is not None
                else node["size_bytes"],
                "outcome": read_doc["outcome"]})
            continue
        searched += 1
        text = read_doc["content"] or ""
        folded = text.casefold()
        occurrences = folded.count(needle)
        if not occurrences:
            continue
        start = folded.index(needle)
        excerpt = text[max(0, start - EXCERPT_CONTEXT):
                       start + len(cleaned) + EXCERPT_CONTEXT]
        matches.append({
            "name": node["name"], "kind": node["kind"],
            "size_bytes": node["size_bytes"],
            "hidden": node["hidden"],
            "escapes": node["escapes"], "path": path,
            "occurrences": occurrences, "excerpt": excerpt})
    root = tree_document["tree"]
    partial = any(
        node["kind"] == "directory" and not node.get("expanded")
        for node in _all_nodes(root))
    truncated = bool(tree_document["truncated"]) or partial or \
        bool(skipped) or len(matches) > MAX_MATCHES
    considered = searched + len(skipped)
    return {
        "schema": CONTENT_SEARCH_SCHEMA,
        "tree_document": tree_document,
        "binding_document": binding_document,
        "folder_state": tree_document["folder_state"],
        "subpath": tree_document["subpath"],
        "query": cleaned,
        "matches": matches[:MAX_MATCHES],
        "match_count": min(len(matches), MAX_MATCHES),
        "total_matches": len(matches),
        "files_considered": considered,
        "files_searched": searched,
        "skipped_files": skipped,
        "max_matches": MAX_MATCHES,
        "max_content_bytes": content_service.MAX_CONTENT_BYTES,
        "truncated": truncated,
        "coverage_complete": not truncated,
        "notes": list(CONTENT_SEARCH_NOTES),
    }


async def resolve_chat_content_search(session, store, user_id: str,
                                      chat_id: str, query: str,
                                      subpath: str = ""):
    """The content search for one chat, or None.

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
    return build_content_search(tree_document, cleaned)


__all__ = [
    "CONTENT_SEARCH_NOTES", "CONTENT_SEARCH_SCHEMA",
    "EXCERPT_CONTEXT", "MAX_MATCHES", "OUTCOME_REFUSED",
    "WorkspaceContentSearchError", "build_content_search",
    "resolve_chat_content_search",
]
