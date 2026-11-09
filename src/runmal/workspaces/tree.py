"""Workspace folder tree (P-176, Part XI - DERIVED).

P-170 banked the read-only folder listing and stated
its own shape plainly: one level deep. P-174 banked the
aggregate of that one level and declined, by name, a
recursive or whole-tree CENSUS - an aggregate over a
walked tree, which would need a new honesty law for
partial walks. The cell no surface took is neither of
those: it is NAVIGATION. A files browser that can show
exactly one level leaves the owner issuing one listing
per directory by hand and stitching the results
client-side; nothing composes P-170 across levels. This
module is that composition, and it aggregates nothing:

- every level is P-170's own build_listing, composed
  VERBATIM - the same store, the same binding document,
  the same folder_state() law, the same path law
  re-judged at this read for every level, the same
  entry fields carried whole into each node. There is
  no second listing law, no second folder-state law
  and no second scan in this module;
- child subpaths are built only from scandir entry
  names returned by the parent level's own listing (a
  filesystem name cannot contain "/" and cannot be
  "." or ".."), and each is re-judged by build_listing
  itself before a single entry is read from it;
- directories are expanded only to a stated depth cap
  and a stated total node cap; a directory at a cap is
  present with children None and expanded False -
  named as unexpanded, never dressed as empty;
- a symlink is never descended: it is a leaf carrying
  P-170's own escapes flag, and its target is never
  judged beyond that flag;
- a directory that refuses expansion at this read (it
  vanished, or stopped being contained, between the
  parent listing and its own - the two-moment race
  P-172 named) is DATA on its node (expand_refused),
  never a crashed read and never dressed as empty.
  The root subpath is the caller's own naming, so its
  refusal raises P-170's error unchanged, as at P-174.

Honest boundaries: this tree reads directory entries
only, through P-170 - it opens no file (the per-file
text read is P-172's road), writes, edits and deletes
nothing, runs and launches nothing, watches nothing
and grants nothing (P-169's law, restated). Writes
wait for the VX-57 guard; execution is VX-55/56
territory (P-027 absolute). The tree is a point-in-
time judgement composed from live per-level reads.
No store, no migration: head stays 0041.
"""

from __future__ import annotations

from runmal.workspaces import listing as listing_service
from runmal.workspaces.bindings import FOLDER_READY
from runmal.workspaces.listing import KIND_DIRECTORY

TREE_SCHEMA = "runmal-p176-workspace-tree-v1"

DEFAULT_DEPTH = 2
MAX_DEPTH = 4
MAX_NODES = 500  # P-170's per-level cap, carried to the tree

TREE_NOTES = (
    "Pure navigation read over one chat's bound folder: "
    "this tree stores, binds, unbinds, writes, edits, "
    "deletes, runs and watches nothing, and opens no "
    "file - the per-file text read is a separate Part "
    "XI road (P-172).",
    "Every level is P-170's listing composed verbatim: "
    "its path law, kind law, honest sizes and folder "
    "state are re-judged at this read for each level - "
    "no second listing law, folder-state law or scan "
    "exists here, and the root level's listing document "
    "is embedded whole.",
    "Depth and size are capped as stated in this "
    "document (max_depth, and the tree node cap): a "
    "directory at a cap is present but unexpanded - "
    "children None, expanded False - never dressed as "
    "empty, and truncated names every partial tree, "
    "including any single level P-170 itself truncated.",
    "A symlink is never descended: it stays a leaf "
    "carrying P-170's own escapes flag. A directory "
    "that refused expansion at this read carries "
    "expand_refused - the folder changed mid-walk, and "
    "that is stated as data, never hidden.",
    "A tree grants nothing: no tool, backend or process "
    "inherits any access from a binding existing, and "
    "workspace writes wait for the tool-calling guard "
    "(VX-57) while execution stays declined (P-027: "
    "content is data, never code).",
)


class WorkspaceTreeError(ValueError):
    """A tree request the stated caps forbid."""


def _join(subpath: str, name: str) -> str:
    return f"{subpath}/{name}" if subpath else name


def _leaf(entry: dict) -> dict:
    return {
        "name": entry["name"],
        "kind": entry["kind"],
        "size_bytes": entry["size_bytes"],
        "hidden": entry["hidden"],
        "escapes": entry["escapes"],
    }


def _dir_node(entry: dict) -> dict:
    node = _leaf(entry)
    node["children"] = None
    node["expanded"] = False
    return node


def build_tree(root_listing: dict, max_depth: int = DEFAULT_DEPTH) -> dict:
    """The tree document for one resolved root listing.

    ``root_listing`` is P-170's listing document for the
    requested subpath, composed verbatim and embedded
    whole; the binding document and folder path for
    deeper levels are read from it. Raises
    WorkspaceTreeError for a max_depth outside the
    closed 1..MAX_DEPTH range - refused plainly, never
    clamped silently.
    """
    if not isinstance(max_depth, int) or isinstance(max_depth, bool) \
            or max_depth < 1 or max_depth > MAX_DEPTH:
        raise WorkspaceTreeError(
            f"max_depth must be between 1 and {MAX_DEPTH}")
    folder_state = root_listing["folder_state"]
    subpath = root_listing["subpath"]
    binding_document = root_listing["binding_document"]
    folder_path = binding_document["binding"]["folder_path"]
    state = {"count": 0, "truncated": bool(root_listing["truncated"])}
    root = {
        "name": subpath.rsplit("/", 1)[-1] if subpath else "",
        "kind": KIND_DIRECTORY,
        "size_bytes": None,
        "hidden": False,
        "escapes": False,
        "children": None,
        "expanded": False,
    }
    document = {
        "schema": TREE_SCHEMA,
        "binding_document": binding_document,
        "root_listing": root_listing,
        "folder_state": folder_state,
        "subpath": subpath,
        "max_depth": max_depth,
        "tree": root,
        "node_count": 0,
        "truncated": state["truncated"],
        "notes": list(TREE_NOTES),
    }
    if folder_state != FOLDER_READY:
        return document

    def fill(node: dict, listing_doc: dict, node_subpath: str,
             level: int) -> None:
        entries = listing_doc["entries"]
        remaining = MAX_NODES - state["count"]
        if len(entries) > remaining:
            entries = entries[:max(remaining, 0)]
            state["truncated"] = True
        children = []
        for entry in entries:
            state["count"] += 1
            if entry["kind"] == KIND_DIRECTORY:
                children.append(_dir_node(entry))
            else:
                children.append(_leaf(entry))
        node["children"] = children
        node["expanded"] = True
        if level >= max_depth:
            return
        for child in children:
            if child["kind"] != KIND_DIRECTORY:
                continue
            if state["count"] >= MAX_NODES:
                state["truncated"] = True
                continue
            child_subpath = _join(node_subpath, child["name"])
            try:
                child_listing = listing_service.build_listing(
                    binding_document, folder_path, child_subpath)
            except listing_service.WorkspaceListingError:
                child["expand_refused"] = True
                continue
            if child_listing["truncated"]:
                state["truncated"] = True
            fill(child, child_listing, child_subpath, level + 1)

    fill(root, root_listing, subpath, 1)
    document["node_count"] = state["count"]
    document["truncated"] = state["truncated"]
    return document


async def resolve_chat_tree(session, store, user_id: str, chat_id: str,
                            subpath: str = "",
                            max_depth: int = DEFAULT_DEPTH):
    """The folder tree for one chat, or None.

    None exactly when P-170's resolve_chat_listing is
    None (the chat is missing or foreign - existence
    never leaks - or the chat is unbound); the road
    keeps the two 404 details apart by checking the
    chat first, the P-169 router pattern. Otherwise the
    tree document; a refused root subpath raises
    P-170's own WorkspaceListingError unchanged and a
    refused max_depth raises WorkspaceTreeError.
    """
    root_listing = await listing_service.resolve_chat_listing(
        session, store, user_id, chat_id, subpath)
    if root_listing is None:
        return None
    return build_tree(root_listing, max_depth)


__all__ = [
    "DEFAULT_DEPTH", "MAX_DEPTH", "MAX_NODES", "TREE_NOTES",
    "TREE_SCHEMA", "WorkspaceTreeError", "build_tree",
    "resolve_chat_tree",
]
