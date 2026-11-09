"""Workspace tree census (P-181, Part XI - DERIVED).

The roadmap gives Part XI one line only ("Workspaces -
the Companion That Works", P-169..P-186); this slice's
scope is derived from Runmal's own in-tree record - see
docs/WORKSPACE_TREE_CENSUS_2026-11-09.md and
hidden_files/P181_SCOUT.md / P181_DESIGN.md.

What the derivation found: P-174 banked the aggregate
of ONE chat's bound folder at ONE level and declined,
by name, a recursive or whole-tree census - a tree
walk would need a new path law and a new cap law, and
(as P-176's own derivation puts it) a census aggregates
a walked tree under a new honesty law for partial
walks. Every missing presupposition has since banked:
P-176 is the tree itself (every level P-170's listing
composed verbatim, depth and node caps stated,
directories left unexpanded named as unexpanded, never
dressed as empty) and it aggregates nothing; P-179
fixed the tree's truncated flag at the depth cap at
the source, so truncated now names every partial tree;
P-178 / P-180 proved document-side partiality reading
over the composed tree. The cell no surface took is
the aggregate of the whole composed tree. The house
pattern for exactly this is the census (P-148 / P-164
/ P-171 / P-174 / P-177): a pure read composing the
owning surface verbatim, classified under a closed
law, counts summed from the composed document's own
fields. That is what lives here:

- the tree is P-176's, composed VERBATIM -
  resolve_chat_tree at its own MAX_DEPTH ceiling, its
  document embedded whole in this one, its nodes the
  only entries summed; there is no second walk, no
  second listing law, no second folder-state law and
  no second scan here;
- the kind axis sums the nodes' own kind values under
  P-170's closed ENTRY_KINDS law; the counted nodes
  are exactly P-176's node_count (the tree's root node
  is the subpath's synthetic node and is never
  counted);
- the byte axis sums the file nodes' own size_bytes
  (P-170 gives directories, symlinks and other kinds
  no size rather than an invented one, so only files
  carry bytes here too - P-174's law carried over);
- the extension axis counts file NAMES only (the
  suffix after the final dot, lowercased; no suffix
  is the honest key "(none)") - no file is opened, so
  an extension never claims what the content is;
- the tree axes count what only a tree can name:
  directories expanded vs left unexpanded, expansions
  refused at the read (expand_refused), entries per
  depth level, and the largest file carrying its
  folder-relative path (exactly the input P-172's
  read consumes) as well as its name;
- the folder is classified under the closed
  TREE_CENSUS_STATES law: folder_not_ready / empty /
  no_files / has_files - P-174's census law carried
  to the tree. A non-ready folder is DATA, never an
  error: P-176's tree of it is the unexpanded root,
  and the census of it is the honest zero document.

Partiality honesty: counts describe the composed
nodes only. truncated is True when P-176's own
truncated flag is set (post-P-179 it names depth caps,
node caps and truncated levels at the source), or when
any directory node in the composed document is
unexpanded, or when any node carries expand_refused -
the P-178 document-side reading, kept as a safety net:
a correct no-op for depth caps against the fixed tree,
still load-bearing for refused expansions, which the
tree names by expand_refused alone. What sits below an
unexpanded directory was not seen and is not counted.

Honest boundaries: this census opens NO file and reads
NO file contents (the per-file text read is P-172's
road; content search over the tree is P-180's), writes,
edits and deletes nothing, runs and launches nothing,
watches nothing and grants nothing - no tool, backend
or process inherits any access from a binding existing
(P-169's law, restated). Writes wait for the VX-57
guard; execution is VX-55/56 territory (P-027
absolute). Counts are a point-in-time judgement
composed from one tree read. No store, no migration:
head stays 0041.
"""

from __future__ import annotations

from runmal.workspaces import tree as tree_service
from runmal.workspaces.bindings import FOLDER_READY
from runmal.workspaces.listing import (
    KIND_DIRECTORY,
    KIND_FILE,
    KIND_OTHER,
    KIND_SYMLINK,
)

TREE_CENSUS_SCHEMA = "runmal-p181-workspace-tree-census-v1"

STATE_FOLDER_NOT_READY = "folder_not_ready"
STATE_EMPTY = "empty"
STATE_NO_FILES = "no_files"
STATE_HAS_FILES = "has_files"
TREE_CENSUS_STATES = frozenset({
    STATE_FOLDER_NOT_READY, STATE_EMPTY, STATE_NO_FILES,
    STATE_HAS_FILES,
})

NO_EXTENSION = "(none)"

TREE_CENSUS_NOTES = (
    "Pure read over one chat's bound folder as a whole "
    "depth-limited tree: this census stores, binds, "
    "unbinds, writes, edits, deletes, runs and watches "
    "nothing, opens no file and reads no file contents "
    "- the per-file text read is a separate Part XI "
    "road (P-172).",
    "Every count is summed from P-176's tree document, "
    "composed verbatim at its own maximum depth and "
    "embedded whole: its path law, kind law, honest "
    "sizes and folder state are P-176/P-170's own - no "
    "second listing law, folder-state law, walk or "
    "scan exists here.",
    "Counts describe the composed nodes only - exactly "
    "the tree's node_count. What sits below a directory "
    "the tree left unexpanded was not seen and is not "
    "counted, and truncated names every partial census: "
    "the tree's own truncation, any unexpanded "
    "directory, or any refused expansion.",
    "Extension counts describe file names, not "
    "contents: no file is opened by this census, so a "
    "name never claims what the bytes are.",
    "A census grants nothing: no tool, backend or "
    "process inherits any access from a binding "
    "existing, and workspace writes wait for the "
    "tool-calling guard (VX-57) while execution stays "
    "declined (P-027: content is data, never code).",
    "Counts are a point-in-time judgement composed "
    "from one tree read; the folder can change between "
    "this census and any later consumer.",
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


def build_tree_census(tree_document: dict) -> dict:
    """The tree census document for one tree document.

    Sums only the tree document's own node fields, in
    the tree's own depth-first order (the order the
    children arrays carry, which is P-170's order per
    level); the tree document is embedded whole. The
    root node itself is never counted - the counted
    nodes are exactly the tree's node_count. A
    non-ready folder (P-169's law, carried by the tree)
    is the folder_not_ready zero document - data,
    never an error.
    """
    folder_state = tree_document["folder_state"]
    subpath = tree_document["subpath"]
    kind_counts = {
        KIND_DIRECTORY: 0, KIND_FILE: 0,
        KIND_SYMLINK: 0, KIND_OTHER: 0}
    total_file_bytes = 0
    hidden_count = 0
    escaping_symlink_count = 0
    extension_counts: dict[str, int] = {}
    largest_file = None
    expanded_directory_count = 0
    unexpanded_directory_count = 0
    expand_refused_count = 0
    depth_counts: dict[str, int] = {}
    deepest_level = 0
    counted = 0

    def walk(children, prefix: str, level: int) -> None:
        nonlocal total_file_bytes, hidden_count
        nonlocal escaping_symlink_count, largest_file
        nonlocal expanded_directory_count
        nonlocal unexpanded_directory_count
        nonlocal expand_refused_count, deepest_level, counted
        for node in children or []:
            counted += 1
            depth_counts[str(level)] = depth_counts.get(str(level), 0) + 1
            if level > deepest_level:
                deepest_level = level
            path = _join(prefix, node["name"])
            kind = node["kind"]
            if kind in kind_counts:
                kind_counts[kind] += 1
            if node["hidden"]:
                hidden_count += 1
            if node.get("expand_refused"):
                expand_refused_count += 1
            if kind == KIND_SYMLINK and node["escapes"]:
                escaping_symlink_count += 1
            if kind == KIND_DIRECTORY:
                if node.get("expanded"):
                    expanded_directory_count += 1
                else:
                    unexpanded_directory_count += 1
            if kind == KIND_FILE:
                size = node["size_bytes"] or 0
                total_file_bytes += size
                ext = _extension_of(node["name"])
                extension_counts[ext] = extension_counts.get(ext, 0) + 1
                if largest_file is None or size > largest_file["size_bytes"]:
                    largest_file = {
                        "name": node["name"], "path": path,
                        "size_bytes": size}
            if node.get("expanded"):
                walk(node.get("children"), path, level + 1)

    root = tree_document["tree"]
    if root.get("expanded"):
        walk(root.get("children"), subpath, 1)
    truncated = bool(tree_document["truncated"]) or \
        unexpanded_directory_count > 0 or expand_refused_count > 0
    if folder_state != FOLDER_READY:
        census_state = STATE_FOLDER_NOT_READY
    elif counted == 0:
        census_state = STATE_EMPTY
    elif kind_counts[KIND_FILE] == 0:
        census_state = STATE_NO_FILES
    else:
        census_state = STATE_HAS_FILES
    return {
        "schema": TREE_CENSUS_SCHEMA,
        "census_state": census_state,
        "tree_document": tree_document,
        "binding_document": tree_document["binding_document"],
        "folder_state": folder_state,
        "subpath": subpath,
        "max_depth": tree_document["max_depth"],
        "node_count": tree_document["node_count"],
        "truncated": truncated,
        "directory_count": kind_counts[KIND_DIRECTORY],
        "file_count": kind_counts[KIND_FILE],
        "symlink_count": kind_counts[KIND_SYMLINK],
        "other_count": kind_counts[KIND_OTHER],
        "kind_counts": kind_counts,
        "total_file_bytes": total_file_bytes,
        "hidden_count": hidden_count,
        "escaping_symlink_count": escaping_symlink_count,
        "extension_counts": dict(sorted(extension_counts.items())),
        "largest_file": largest_file,
        "expanded_directory_count": expanded_directory_count,
        "unexpanded_directory_count": unexpanded_directory_count,
        "expand_refused_count": expand_refused_count,
        "depth_counts": depth_counts,
        "deepest_level": deepest_level,
        "notes": list(TREE_CENSUS_NOTES),
    }


async def resolve_chat_tree_census(session, store, user_id: str,
                                   chat_id: str,
                                   subpath: str = ""):
    """The tree census for one chat, or None.

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
    return build_tree_census(tree_document)


__all__ = [
    "NO_EXTENSION", "STATE_EMPTY", "STATE_FOLDER_NOT_READY",
    "STATE_HAS_FILES", "STATE_NO_FILES", "TREE_CENSUS_NOTES",
    "TREE_CENSUS_SCHEMA", "TREE_CENSUS_STATES",
    "build_tree_census", "resolve_chat_tree_census",
]
