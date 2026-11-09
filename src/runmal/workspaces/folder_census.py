"""Workspace folder census (P-174, Part XI - DERIVED).

The roadmap gives Part XI one line only ("Workspaces -
the Companion That Works", P-169..P-186); this slice's
scope is derived from Runmal's own in-tree record - see
docs/WORKSPACE_FOLDER_CENSUS_2026-11-09.md and
hidden_files/P174_SCOUT.md / P174_DESIGN.md.

What the derivation found: P-169 banked the binding,
P-170 the read-only folder listing, P-171 the census of
the owner's whole BINDING estate (which lists no folder
and reads no contents), and P-172 the read of one named
file. The cell no surface took is the aggregate of ONE
chat's bound folder at ONE level: how many entries of
each kind, how many file bytes in total, the shape of
the file extensions, how many entries are hidden, how
many symlinks escape the folder, and the largest file.
The house pattern for exactly this is the census
(P-148 / P-164 / P-171): a pure read composing the
owning surface verbatim, classified under a closed law,
counts summed from the composed document's own fields.
That is what lives here:

- the listing is P-170's, composed VERBATIM -
  resolve_chat_listing / build_listing unchanged, its
  document embedded whole in this one, its entry fields
  the only numbers summed; there is no second listing
  law, no second folder-state law and no second scan;
- the kind axis sums the entries' own kind values under
  P-170's closed ENTRY_KINDS law;
- the byte axis sums the file entries' own size_bytes
  (P-170 gives directories, symlinks and other kinds no
  size rather than an invented one, so only files carry
  bytes here too);
- the extension axis counts file NAMES only (the suffix
  after the final dot, lowercased; no suffix is the
  honest key "(none)") - no file is opened, so an
  extension never claims what the content is;
- the folder is classified under the closed
  FOLDER_CENSUS_STATES law: folder_not_ready / empty /
  no_files / has_files. A non-ready folder is DATA,
  never an error and never a scan: P-170's listing of a
  missing / not_a_directory / unreadable folder already
  carries empty entries, and the census of it is the
  honest zero document.

Truncation honesty: P-170 caps a listing at MAX_ENTRIES
returned entries while carrying total_count and
truncated. Both ride in this document VERBATIM, and
when truncated is true every count here describes the
returned entries only - stated in the notes, never
hidden.

Honest boundaries: this census reads no file contents
(that is P-172's per-file read), writes, edits and
deletes nothing, runs and launches nothing, watches
nothing and grants nothing - no tool, backend or
process inherits any access from a binding existing
(P-169's law, restated). Writes wait for the VX-57
guard; execution is VX-55/56 territory (P-027
absolute). Counts are a point-in-time judgement
composed from one listing read. No store, no
migration: head stays 0041.
"""

from __future__ import annotations

from runmal.workspaces import listing as listing_service
from runmal.workspaces.bindings import FOLDER_READY
from runmal.workspaces.listing import (
    KIND_DIRECTORY,
    KIND_FILE,
    KIND_OTHER,
    KIND_SYMLINK,
)

FOLDER_CENSUS_SCHEMA = "runmal-p174-workspace-folder-census-v1"

STATE_FOLDER_NOT_READY = "folder_not_ready"
STATE_EMPTY = "empty"
STATE_NO_FILES = "no_files"
STATE_HAS_FILES = "has_files"
FOLDER_CENSUS_STATES = frozenset({
    STATE_FOLDER_NOT_READY, STATE_EMPTY, STATE_NO_FILES,
    STATE_HAS_FILES,
})

NO_EXTENSION = "(none)"

FOLDER_CENSUS_NOTES = (
    "Pure read over one chat's bound folder at one "
    "level: this census stores, binds, unbinds, writes, "
    "edits, deletes, runs and watches nothing, and "
    "reads no file contents - the per-file text read "
    "is a separate Part XI road (P-172).",
    "Every count is summed from P-170's listing "
    "document, composed verbatim and embedded whole: "
    "its folder state, path law, kind law and honest "
    "sizes are P-170's own - no second listing law, "
    "folder-state law or scan exists here.",
    "When the listing is truncated (over the listing "
    "cap at one level), total_count and truncated are "
    "carried verbatim and every count describes the "
    "returned entries only - never the whole folder "
    "dressed as counted.",
    "Extension counts describe file names, not "
    "contents: no file is opened by this census, so a "
    "name never claims what the bytes are.",
    "A census grants nothing: no tool, backend or "
    "process inherits any access from a binding "
    "existing, and workspace writes wait for the "
    "tool-calling guard (VX-57) while execution stays "
    "declined (P-027: content is data, never code).",
    "Counts are a point-in-time judgement composed "
    "from one listing read; the folder can change "
    "between this census and any later consumer.",
)


def _extension_of(name: str) -> str:
    if "." not in name:
        return NO_EXTENSION
    suffix = name.rsplit(".", 1)[1]
    if not suffix:
        return NO_EXTENSION
    return suffix.lower()


def build_folder_census(listing_document: dict) -> dict:
    """The folder census document for one listing.

    Sums only the listing document's own entry fields;
    the listing document is embedded whole. A non-ready
    folder (P-169's law, carried by the listing) is the
    folder_not_ready zero document - data, never an
    error.
    """
    folder_state = listing_document["folder_state"]
    entries = listing_document["entries"]
    kind_counts = {
        KIND_DIRECTORY: 0, KIND_FILE: 0,
        KIND_SYMLINK: 0, KIND_OTHER: 0}
    total_file_bytes = 0
    hidden_count = 0
    escaping_symlink_count = 0
    extension_counts: dict[str, int] = {}
    largest_file = None
    for entry in entries:
        kind = entry["kind"]
        if kind in kind_counts:
            kind_counts[kind] += 1
        if entry["hidden"]:
            hidden_count += 1
        if kind == KIND_SYMLINK and entry["escapes"]:
            escaping_symlink_count += 1
        if kind == KIND_FILE:
            size = entry["size_bytes"] or 0
            total_file_bytes += size
            ext = _extension_of(entry["name"])
            extension_counts[ext] = extension_counts.get(ext, 0) + 1
            if largest_file is None or size > largest_file["size_bytes"]:
                largest_file = {
                    "name": entry["name"], "size_bytes": size}
    if folder_state != FOLDER_READY:
        census_state = STATE_FOLDER_NOT_READY
    elif not entries:
        census_state = STATE_EMPTY
    elif kind_counts[KIND_FILE] == 0:
        census_state = STATE_NO_FILES
    else:
        census_state = STATE_HAS_FILES
    return {
        "schema": FOLDER_CENSUS_SCHEMA,
        "census_state": census_state,
        "listing_document": listing_document,
        "folder_state": folder_state,
        "subpath": listing_document["subpath"],
        "entry_count": listing_document["entry_count"],
        "total_count": listing_document["total_count"],
        "truncated": listing_document["truncated"],
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
        "notes": list(FOLDER_CENSUS_NOTES),
    }


async def resolve_chat_folder_census(session, store, user_id: str,
                                     chat_id: str,
                                     subpath: str = ""):
    """The folder census for one chat, or None.

    None exactly when P-170's resolve_chat_listing is
    None (the chat is missing or foreign - existence
    never leaks - or the chat is unbound); the road
    keeps the two 404 details apart by checking the
    chat first, the P-169 router pattern. Otherwise the
    census document; a refused subpath raises P-170's
    own WorkspaceListingError unchanged.
    """
    listing_document = await listing_service.resolve_chat_listing(
        session, store, user_id, chat_id, subpath)
    if listing_document is None:
        return None
    return build_folder_census(listing_document)


__all__ = [
    "FOLDER_CENSUS_NOTES", "FOLDER_CENSUS_SCHEMA",
    "FOLDER_CENSUS_STATES", "NO_EXTENSION",
    "STATE_EMPTY", "STATE_FOLDER_NOT_READY",
    "STATE_HAS_FILES", "STATE_NO_FILES",
    "build_folder_census",
    "resolve_chat_folder_census",
]
