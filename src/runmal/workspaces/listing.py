"""Workspace folder listing (P-170, Part XI - DERIVED).

P-169 banked the binding and named this cell in its own
record: the binding had no consumer, and "the folder
listing / files browser is the named natural next cell".
This module is that consumer, and it is READ-ONLY: it
lists the bound folder's entries (names, kinds, honest
sizes) judged live at read time. It reads no file
contents, writes nothing anywhere, runs nothing and
watches nothing - writes wait for the VX-57 guard,
execution is VX-55/56 territory (P-027 absolute).

Composition law: the binding and the folder-state law
are P-169's, composed VERBATIM from
runmal.workspaces.bindings (the same store, the same
folder_state(), the same binding document) - there is
no second binding store and no second folder-state law
in this module. What is new here is only the entry law
and the path law for walking inside the bound folder:

- Every listed path stays inside the bound folder. A
  subpath is refused plainly (WorkspaceListingError)
  when it is absolute, carries a NUL or any ".."
  component, names nothing inside, names a
  non-directory, or resolves - through any symlink -
  outside the bound folder's real path.
- Entries are judged by lstat, never followed: a
  symlink is always kind "symlink", carries no size,
  and carries an honest escapes flag when its realpath
  leaves the bound folder. A directory carries no size
  rather than an invented one.
- Non-ready folder states (missing / not_a_directory /
  unreadable, P-169's closed law) are DATA in the
  document, never an error and never a scan.
"""

from __future__ import annotations

import os
import stat as stat_module
from pathlib import Path

from runmal.workspaces import bindings as bindings_service
from runmal.workspaces.bindings import (
    FOLDER_READY,
    WorkspaceBinding,
    folder_state,
)

LISTING_SCHEMA = "runmal-p170-workspace-listing-v1"

KIND_DIRECTORY = "directory"
KIND_FILE = "file"
KIND_SYMLINK = "symlink"
KIND_OTHER = "other"
ENTRY_KINDS = frozenset({
    KIND_DIRECTORY, KIND_FILE, KIND_SYMLINK, KIND_OTHER})
_KIND_RANK = {
    KIND_DIRECTORY: 0, KIND_FILE: 1, KIND_SYMLINK: 2, KIND_OTHER: 3}

MAX_ENTRIES = 500

LISTING_NOTES = (
    "Read-only consumer of the P-169 binding: this "
    "surface lists entry names, kinds and sizes only - "
    "it reads no file contents, writes, edits and "
    "deletes nothing, and runs nothing; workspace "
    "writes wait for the tool-calling guard (VX-57).",
    "Every listed path stays inside the bound folder: "
    "subpaths are refused on traversal or escape, and "
    "a symlink pointing out of the folder is flagged "
    "as escaping, never followed by the listing.",
    "Sizes are honest: a regular file carries its exact "
    "byte size, and directories, symlinks and other "
    "kinds carry no size rather than an invented one. "
    "The folder state and the entries are a "
    "point-in-time judgement at this read.",
    "Owner-scoped throughout: a listing exists only "
    "for the binding owner's own chat, resolved "
    "through the P-169 binding - there is no second "
    "binding store and no second folder-state law.",
)


class WorkspaceListingError(ValueError):
    """A listing the state of the world forbids."""


def _inside(path_real: str, root_real: str) -> bool:
    return path_real == root_real or Path(path_real).is_relative_to(root_real)


def _normalise_subpath(subpath: str) -> tuple[str, list[str]]:
    raw = subpath or ""
    if "\x00" in raw:
        raise WorkspaceListingError("the subpath is not a valid path")
    if os.path.isabs(raw):
        raise WorkspaceListingError(
            "the subpath must stay inside the workspace folder")
    raw_parts = raw.split("/")
    if ".." in raw_parts:
        raise WorkspaceListingError(
            "the subpath must stay inside the workspace folder")
    parts = [part for part in raw_parts if part not in ("", ".")]
    return "/".join(parts), parts


def _entry_document(entry, root_real: str) -> dict:
    name = entry.name
    base = {"name": name, "kind": KIND_OTHER, "size_bytes": None,
            "hidden": name.startswith("."), "escapes": False}
    try:
        info = entry.stat(follow_symlinks=False)
    except OSError:
        return base  # vanished mid-scan: named honestly, never a crash
    if entry.is_symlink():
        base["kind"] = KIND_SYMLINK
        target_real = os.path.realpath(entry.path)
        base["escapes"] = not _inside(target_real, root_real)
    elif stat_module.S_ISDIR(info.st_mode):
        base["kind"] = KIND_DIRECTORY
    elif stat_module.S_ISREG(info.st_mode):
        base["kind"] = KIND_FILE
        base["size_bytes"] = info.st_size
    return base


def build_listing(binding_document: dict, folder_path: str,
                  subpath: str = "") -> dict:
    """The listing document for one resolved binding.

    Judges the folder state LIVE through P-169's own
    folder_state(); a non-ready folder is never scanned
    and its state is the document's data. A ready folder
    is listed one level deep at the (normalised,
    contained) subpath. Raises WorkspaceListingError
    for a refused subpath on a ready folder.
    """
    state = folder_state(folder_path)
    normalised, parts = _normalise_subpath(subpath)
    document = {
        "schema": LISTING_SCHEMA,
        "binding_document": binding_document,
        "folder_state": state,
        "subpath": normalised,
        "entries": [],
        "entry_count": 0,
        "total_count": 0,
        "truncated": False,
        "notes": list(LISTING_NOTES),
    }
    if state != FOLDER_READY:
        return document
    root_real = os.path.realpath(folder_path)
    candidate = os.path.join(root_real, *parts) if parts else root_real
    if not os.path.exists(candidate):
        raise WorkspaceListingError(
            "the subpath does not exist inside the workspace folder")
    if not os.path.isdir(candidate):
        raise WorkspaceListingError(
            "the subpath is not a directory inside the workspace folder")
    candidate_real = os.path.realpath(candidate)
    if not _inside(candidate_real, root_real):
        raise WorkspaceListingError(
            "the subpath escapes the workspace folder")
    entries = []
    with os.scandir(candidate_real) as scan:
        for entry in scan:
            entries.append(_entry_document(entry, root_real))
    entries.sort(key=lambda row: (
        _KIND_RANK[row["kind"]], row["name"].casefold(), row["name"]))
    document["total_count"] = len(entries)
    document["entries"] = entries[:MAX_ENTRIES]
    document["entry_count"] = len(document["entries"])
    document["truncated"] = len(entries) > MAX_ENTRIES
    return document


async def resolve_chat_listing(session, store, user_id: str,
                               chat_id: str, subpath: str = ""):
    """The listing document for one chat, or None.

    None exactly when P-169's resolve_chat_workspace is
    None (the chat is missing or foreign - existence
    never leaks - or the chat is unbound); the road
    keeps the two 404 details apart by checking the
    chat first, the P-169 router pattern. Otherwise
    the listing document; a refused subpath raises
    WorkspaceListingError.
    """
    binding_document = await bindings_service.resolve_chat_workspace(
        session, store, user_id, chat_id)
    if binding_document is None:
        return None
    folder_path = binding_document["binding"]["folder_path"]
    return build_listing(binding_document, folder_path, subpath)


__all__ = [
    "ENTRY_KINDS", "KIND_DIRECTORY", "KIND_FILE", "KIND_OTHER",
    "KIND_SYMLINK", "LISTING_NOTES", "LISTING_SCHEMA", "MAX_ENTRIES",
    "WorkspaceBinding", "WorkspaceListingError", "build_listing",
    "resolve_chat_listing",
]
