"""Workspace content census (P-183, Part XI - DERIVED).

The roadmap gives Part XI one line only ("Workspaces -
the Companion That Works", P-169..P-186); this slice's
scope is derived from Runmal's own in-tree record - see
docs/WORKSPACE_CONTENT_CENSUS_2026-11-09.md and
hidden_files/P183_SCOUT.md / P183_DESIGN.md.

What the derivation found: P-174 banked the aggregate of
one chat's bound folder at one level and P-181 the
aggregate over the whole composed tree - both from entry
NAMES and sizes only; neither opens a file, so in their
counts a binary or oversize file is indistinguishable
from readable text. P-172 banked the per-file readability
law (strict UTF-8 under a stated cap; binary / oversize /
unreadable are named outcomes), and P-180 reveals that
law's verdicts only as the skip list of a content search
- for a query the caller must supply, and both banked
searches refuse an empty query plainly. No query-free
document states how much of a bound folder the companion
can actually read as text. This module is that document,
in the house census pattern (P-171 / P-174 / P-177 /
P-181): a pure aggregate composing the owning surfaces
verbatim, classified under a closed law, counts summed
from the composed reads' own fields:

- the tree is P-176's, composed VERBATIM -
  resolve_chat_tree at its own MAX_DEPTH ceiling, its
  document embedded whole; the candidates are its
  expanded kind=file nodes in its own depth-first order
  (P-180's candidate walk over the composed document);
  there is no second walk of the filesystem, no second
  listing law and no second folder-state law here;
- every candidate is read ONLY through P-172's own
  build_content_read, at the moment of this census,
  under its stated cap; its outcome is P-172's own,
  under P-172's closed OUTCOMES law, plus ``refused`` -
  P-180's name for a read P-172 refused at the moment
  of use (the two-moment race);
- NO content is retained or returned: the read
  document's content is judged for its outcome and
  dropped - this census carries counts, names, paths
  and sizes only, never a content field and never an
  excerpt, anywhere in the document;
- no silent omission: every candidate ends as a counted
  readable file or as a named entry in
  unreadable_files with its outcome, so
  files_considered always equals the sum of the
  outcome counts;
- the folder is classified under the closed
  CONTENT_CENSUS_STATES law: folder_not_ready / empty /
  no_files / none_readable / some_readable /
  all_readable. A non-ready folder is DATA, never an
  error: P-176's tree of it is the unexpanded root, no
  candidate exists, and no file is opened.

Partiality honesty: counts describe the composed
coverage only. truncated is True when P-176's own
truncated flag is set, or when any directory node in
the composed document is unexpanded, or when any node
carries expand_refused - the P-181 document-side
reading. A non-ok outcome does NOT set truncated here:
every candidate under the composed coverage was judged
and counted under its outcome - the stated distinction
from P-180, where a skip means the search did not cover
that file's content. What sits below an unexpanded
directory was not seen and is not counted.

Honest boundaries: this census reads file contents
ONLY through P-172, only to judge readability, and
retains none of them; it writes, edits and deletes
nothing, runs and launches nothing, watches nothing
and grants nothing - no tool, backend or process
inherits any access from a binding existing (P-169's
law, restated). Writes wait for the VX-57 guard;
execution is VX-55/56 territory (P-027 absolute).
Counts are a point-in-time judgement composed from one
tree read and the per-file reads at this call. No
store, no migration: head stays 0041.
"""

from __future__ import annotations

from runmal.workspaces import content as content_service
from runmal.workspaces import tree as tree_service
from runmal.workspaces.bindings import FOLDER_READY
from runmal.workspaces.listing import KIND_DIRECTORY, KIND_FILE

CONTENT_CENSUS_SCHEMA = "runmal-p183-workspace-content-census-v1"

STATE_FOLDER_NOT_READY = "folder_not_ready"
STATE_EMPTY = "empty"
STATE_NO_FILES = "no_files"
STATE_NONE_READABLE = "none_readable"
STATE_SOME_READABLE = "some_readable"
STATE_ALL_READABLE = "all_readable"
CONTENT_CENSUS_STATES = frozenset({
    STATE_FOLDER_NOT_READY, STATE_EMPTY, STATE_NO_FILES,
    STATE_NONE_READABLE, STATE_SOME_READABLE,
    STATE_ALL_READABLE,
})

OUTCOME_REFUSED = "refused"  # P-180's name, carried verbatim

NO_EXTENSION = "(none)"

CONTENT_CENSUS_NOTES = (
    "Pure aggregate over one chat's bound folder: this "
    "census stores, binds, unbinds, writes, edits, "
    "deletes, runs and watches nothing - it reads file "
    "contents only through P-172's own read, only to "
    "judge readability, and retains none of them: no "
    "content and no excerpt appears anywhere in this "
    "document.",
    "The tree is P-176's document composed verbatim at "
    "its own maximum depth and embedded whole, and "
    "every candidate file was judged by P-172's own "
    "read under its stated cap at the moment of this "
    "census: outcomes are P-172's closed law (ok / "
    "binary / oversize / unreadable / folder_not_ready, "
    "judged live at this read) plus refused - P-172's "
    "refusal at the moment of use. No second content "
    "law, "
    "listing law, folder-state law, walk or scan "
    "exists here.",
    "No silent omission: files_considered always "
    "equals the sum of the outcome counts, and every "
    "file P-172 did not judge readable is named in "
    "unreadable_files with its outcome - a partial "
    "estate is never dressed as a readable one.",
    "Counts describe the composed coverage only: what "
    "sits below a directory the tree left unexpanded "
    "was not seen and is not counted, and truncated "
    "names that partiality - the tree's own truncation, "
    "any unexpanded directory, or any refused "
    "expansion. A binary, oversize, unreadable or "
    "refused file does not set truncated: it was "
    "judged and counted under its outcome, unlike a "
    "content search, where such a file is uncovered.",
    "Readable extension counts describe readable file "
    "NAMES only (the suffix after the final dot, "
    "lowercased; no suffix is the honest key "
    "'(none)'): readability itself was judged from the "
    "bytes through P-172, never from the name.",
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


def _join(prefix: str, name: str) -> str:
    return f"{prefix}/{name}" if prefix else name


def _all_nodes(node):
    yield node
    for child in node.get("children") or []:
        yield from _all_nodes(child)


def _candidates(tree_document: dict):
    """File nodes of the expanded tree, depth-first.

    P-180's candidate walk over the composed document:
    it judges nothing and scans nothing - it only reads
    the tree document P-176 already composed.
    """
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


def build_content_census(tree_document: dict) -> dict:
    """The content census document for one tree document.

    Every candidate file node is read through P-172's
    build_content_read at this call and counted under
    its outcome; the read content is never copied into
    this document. The tree document is embedded whole.
    A non-ready folder (P-169's law, carried by the
    tree) is the folder_not_ready zero document - data,
    never an error, and no file is opened for it.
    """
    binding_document = tree_document["binding_document"]
    folder_path = binding_document["binding"]["folder_path"]
    folder_state = tree_document["folder_state"]
    outcome_counts = {
        content_service.OUTCOME_OK: 0,
        content_service.OUTCOME_BINARY: 0,
        content_service.OUTCOME_OVERSIZE: 0,
        content_service.OUTCOME_UNREADABLE: 0,
        OUTCOME_REFUSED: 0,
        content_service.OUTCOME_FOLDER_NOT_READY: 0,
    }
    unreadable_files: list[dict] = []
    total_readable_bytes = 0
    readable_extension_counts: dict[str, int] = {}
    largest_readable_file = None
    candidates = _candidates(tree_document) \
        if folder_state == FOLDER_READY else []
    for node, path in candidates:
        try:
            read_doc = content_service.build_content_read(
                binding_document, folder_path, path)
        except content_service.WorkspaceContentError:
            outcome_counts[OUTCOME_REFUSED] += 1
            unreadable_files.append({
                "name": node["name"], "path": path,
                "size_bytes": node["size_bytes"],
                "outcome": OUTCOME_REFUSED})
            continue
        outcome = read_doc["outcome"]
        if outcome not in outcome_counts:
            outcome = content_service.OUTCOME_UNREADABLE
        outcome_counts[outcome] += 1
        if outcome != content_service.OUTCOME_OK:
            size = read_doc["size_bytes"]
            unreadable_files.append({
                "name": node["name"], "path": path,
                "size_bytes": size if size is not None
                else node["size_bytes"],
                "outcome": outcome})
            continue
        size = read_doc["size_bytes"] or 0
        total_readable_bytes += size
        ext = _extension_of(node["name"])
        readable_extension_counts[ext] = \
            readable_extension_counts.get(ext, 0) + 1
        if largest_readable_file is None or \
                size > largest_readable_file["size_bytes"]:
            largest_readable_file = {
                "name": node["name"], "path": path,
                "size_bytes": size}
    files_considered = len(candidates)
    readable_count = outcome_counts[content_service.OUTCOME_OK]
    root = tree_document["tree"]
    partial = any(
        node["kind"] == KIND_DIRECTORY and not node.get("expanded")
        for node in _all_nodes(root))
    refused_expansion = any(
        node.get("expand_refused") for node in _all_nodes(root))
    truncated = bool(tree_document["truncated"]) or partial or \
        refused_expansion
    if folder_state != FOLDER_READY:
        census_state = STATE_FOLDER_NOT_READY
    elif tree_document["node_count"] == 0:
        census_state = STATE_EMPTY
    elif files_considered == 0:
        census_state = STATE_NO_FILES
    elif readable_count == 0:
        census_state = STATE_NONE_READABLE
    elif readable_count == files_considered:
        census_state = STATE_ALL_READABLE
    else:
        census_state = STATE_SOME_READABLE
    return {
        "schema": CONTENT_CENSUS_SCHEMA,
        "census_state": census_state,
        "tree_document": tree_document,
        "binding_document": binding_document,
        "folder_state": folder_state,
        "subpath": tree_document["subpath"],
        "max_depth": tree_document["max_depth"],
        "node_count": tree_document["node_count"],
        "files_considered": files_considered,
        "readable_count": readable_count,
        "binary_count": outcome_counts[
            content_service.OUTCOME_BINARY],
        "oversize_count": outcome_counts[
            content_service.OUTCOME_OVERSIZE],
        "unreadable_count": outcome_counts[
            content_service.OUTCOME_UNREADABLE],
        "refused_count": outcome_counts[OUTCOME_REFUSED],
        "folder_not_ready_count": outcome_counts[
            content_service.OUTCOME_FOLDER_NOT_READY],
        "outcome_counts": outcome_counts,
        "unreadable_files": unreadable_files,
        "total_readable_bytes": total_readable_bytes,
        "readable_extension_counts": dict(
            sorted(readable_extension_counts.items())),
        "largest_readable_file": largest_readable_file,
        "max_content_bytes": content_service.MAX_CONTENT_BYTES,
        "truncated": truncated,
        "coverage_complete": not truncated,
        "notes": list(CONTENT_CENSUS_NOTES),
    }


async def resolve_chat_content_census(session, store, user_id: str,
                                      chat_id: str,
                                      subpath: str = ""):
    """The content census for one chat, or None.

    None exactly when P-176's resolve_chat_tree is None
    (the chat is missing or foreign - existence never
    leaks - or the chat is unbound); the road keeps the
    two 404 details apart by checking the chat first,
    the P-169 router pattern. Otherwise the census
    document; a refused subpath raises P-170's own
    WorkspaceListingError unchanged. The tree is
    composed at P-176's MAX_DEPTH, its stated ceiling -
    one stated coverage, in the P-178 precedent.
    """
    tree_document = await tree_service.resolve_chat_tree(
        session, store, user_id, chat_id, subpath,
        tree_service.MAX_DEPTH)
    if tree_document is None:
        return None
    return build_content_census(tree_document)


__all__ = [
    "CONTENT_CENSUS_NOTES", "CONTENT_CENSUS_SCHEMA",
    "CONTENT_CENSUS_STATES", "NO_EXTENSION", "OUTCOME_REFUSED",
    "STATE_ALL_READABLE", "STATE_EMPTY",
    "STATE_FOLDER_NOT_READY", "STATE_NONE_READABLE",
    "STATE_NO_FILES", "STATE_SOME_READABLE",
    "build_content_census", "resolve_chat_content_census",
]
