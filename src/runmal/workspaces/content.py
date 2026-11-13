"""Workspace file content read (P-172, Part XI - DERIVED).

P-170 banked the listing and named this cell in its own
record: limitation (4) - "still no file-content surface:
reads/viewing, writes and execution remain named-open
later Part XI cells, in that order of presupposition" -
and limitation (2) ordered any future consumer that
acts on paths to re-judge containment at use. This
module is that read cell: a READ-ONLY read of one text
file inside the bound folder, through the P-169 binding
and the P-170 path law, with containment re-judged at
the moment of use. It writes nothing anywhere, runs
nothing, watches nothing and renders no image bytes -
writes wait for the VX-57 guard and execution is
VX-55/56 territory (P-027 absolute).

Composition law: the binding and the folder-state law
are P-169's, composed VERBATIM from
runmal.workspaces.bindings (the same store, the same
folder_state(), the same binding document) - there is
no second binding store and no second folder-state law
in this module. The path law is P-170's shape
(normalise, refuse, realpath containment), re-expressed
for a file path and judged FRESH at this use: the
listing's two-moment race is answered here, not
inherited - folder state, containment, kind and size
are all judged at the read, the final component is
opened with O_NOFOLLOW, and the opened descriptor is
fstat-verified before any byte is read.

Honesty law: text means strict UTF-8 with no NUL byte,
under a stated cap (MAX_CONTENT_BYTES, carried in the
document as data). Binary, oversize and unreadable
files are named OUTCOMES in the document - their bytes
are never dumped as text, never decoded with
replacement characters, never silently truncated.
"""

from __future__ import annotations

import os
import stat as stat_module
from pathlib import Path

from runmal.workspaces import bindings as bindings_service
from runmal.workspaces.bindings import FOLDER_READY, folder_state

CONTENT_SCHEMA = "runmal-p172-workspace-content-v1"

OUTCOME_OK = "ok"
OUTCOME_FOLDER_NOT_READY = "folder_not_ready"
OUTCOME_BINARY = "binary"
OUTCOME_OVERSIZE = "oversize"
OUTCOME_UNREADABLE = "unreadable"
OUTCOMES = frozenset({
    OUTCOME_OK, OUTCOME_FOLDER_NOT_READY, OUTCOME_BINARY,
    OUTCOME_OVERSIZE, OUTCOME_UNREADABLE,
})

MAX_CONTENT_BYTES = 262144  # 256 KiB, a viewing cap stated as data

CONTENT_NOTES = (
    "Read-only consumer of the P-169 binding: this "
    "surface reads one named text file inside the "
    "bound folder - it writes, edits and deletes "
    "nothing, and runs nothing; workspace writes wait "
    "for the tool-calling guard (VX-57).",
    "Containment is re-judged at the moment of use, "
    "not inherited from any earlier listing: the "
    "folder state, the realpath containment, the "
    "file kind and the size are all judged at this "
    "read, and a symlink is never followed for "
    "content.",
    "Text means strict UTF-8 with no NUL byte, under "
    "the stated byte cap: a binary, oversize or "
    "unreadable file is a named outcome in this "
    "document - its bytes are never dumped as text "
    "and its content is never truncated or guessed.",
    "Owner-scoped throughout: a read exists only for "
    "the binding owner's own chat, resolved through "
    "the P-169 binding - there is no second binding "
    "store and no second folder-state law.",
)


class WorkspaceContentError(ValueError):
    """A content read the state of the world forbids."""


def _inside(path_real: str, root_real: str) -> bool:
    return path_real == root_real or Path(path_real).is_relative_to(root_real)


def _normalise_path(path: str) -> tuple[str, list[str]]:
    raw = path or ""
    if "\x00" in raw:
        raise WorkspaceContentError("the path is not a valid path")
    if os.path.isabs(raw):
        raise WorkspaceContentError(
            "the path must stay inside the workspace folder")
    raw_parts = raw.split("/")
    if ".." in raw_parts:
        raise WorkspaceContentError(
            "the path must stay inside the workspace folder")
    parts = [part for part in raw_parts if part not in ("", ".")]
    if not parts:
        raise WorkspaceContentError("a file path inside the "
                                    "workspace folder is required")
    return "/".join(parts), parts


def _read_bytes(candidate: str) -> tuple[str, bytes | None]:
    """Open + fstat-verify + bounded read. Returns (outcome, data).

    data is None unless the outcome is OUTCOME_OK's raw
    material (bytes still to be judged as text by the
    caller) - oversize and unreadable carry no bytes.
    """
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(candidate, flags)
    except OSError:
        return OUTCOME_UNREADABLE, None
    try:
        info = os.fstat(fd)
        if not stat_module.S_ISREG(info.st_mode):
            raise WorkspaceContentError(
                "the path is not a regular file inside the "
                "workspace folder")
        if info.st_size > MAX_CONTENT_BYTES:
            return OUTCOME_OVERSIZE, None
        chunks = []
        remaining = MAX_CONTENT_BYTES + 1
        while remaining > 0:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    except WorkspaceContentError:
        raise
    except OSError:
        return OUTCOME_UNREADABLE, None
    finally:
        os.close(fd)
    if len(data) > MAX_CONTENT_BYTES:
        return OUTCOME_OVERSIZE, None
    return OUTCOME_OK, data


def build_content_read(binding_document: dict, folder_path: str,
                       path: str = "") -> dict:
    """The content document for one resolved binding.

    Judges the folder state LIVE through P-169's own
    folder_state(); a non-ready folder is never opened
    and its state is the document's data. A ready folder
    answers one named file, with containment, kind and
    size re-judged at this use. Raises
    WorkspaceContentError for a refused path (empty,
    absolute, NUL, traversal, escaping, missing, a
    symlink, a directory or a non-regular kind).
    """
    state = folder_state(folder_path)
    normalised, parts = _normalise_path(path)
    document = {
        "schema": CONTENT_SCHEMA,
        "binding_document": binding_document,
        "folder_state": state,
        "path": normalised,
        "outcome": OUTCOME_FOLDER_NOT_READY,
        "size_bytes": None,
        "content": None,
        "max_bytes": MAX_CONTENT_BYTES,
        "notes": list(CONTENT_NOTES),
    }
    if state != FOLDER_READY:
        return document
    root_real = os.path.realpath(folder_path)
    candidate = os.path.join(root_real, *parts)
    candidate_real = os.path.realpath(candidate)
    if not _inside(candidate_real, root_real):
        raise WorkspaceContentError(
            "the path escapes the workspace folder")
    try:
        info = os.lstat(candidate)
    except FileNotFoundError:
        raise WorkspaceContentError(
            "the path does not exist inside the workspace "
            "folder") from None
    except OSError:
        document["outcome"] = OUTCOME_UNREADABLE
        return document
    if stat_module.S_ISLNK(info.st_mode):
        raise WorkspaceContentError(
            "the path is a symlink; symlinks are never "
            "followed for content")
    if stat_module.S_ISDIR(info.st_mode):
        raise WorkspaceContentError(
            "the path is a directory inside the workspace folder")
    if not stat_module.S_ISREG(info.st_mode):
        raise WorkspaceContentError(
            "the path is not a regular file inside the "
            "workspace folder")
    document["size_bytes"] = info.st_size
    if info.st_size > MAX_CONTENT_BYTES:
        document["outcome"] = OUTCOME_OVERSIZE
        return document  # the body is never read
    outcome, data = _read_bytes(candidate)
    document["outcome"] = outcome
    if outcome == OUTCOME_OK and data is not None:
        document["size_bytes"] = len(data)  # bytes actually read
    if outcome != OUTCOME_OK or data is None:
        return document
    if b"\x00" in data:
        document["outcome"] = OUTCOME_BINARY
        return document
    try:
        document["content"] = data.decode("utf-8")
    except UnicodeDecodeError:
        document["outcome"] = OUTCOME_BINARY
        document["content"] = None
        return document
    return document


async def resolve_chat_content(session, store, user_id: str,
                               chat_id: str, path: str = ""):
    """The content document for one chat, or None.

    None exactly when P-169's resolve_chat_workspace is
    None (the chat is missing or foreign - existence
    never leaks - or the chat is unbound); the road
    keeps the two 404 details apart by checking the
    chat first, the P-169 router pattern. Otherwise
    the content document; a refused path raises
    WorkspaceContentError.
    """
    binding_document = await bindings_service.resolve_chat_workspace(
        session, store, user_id, chat_id)
    if binding_document is None:
        return None
    folder_path = binding_document["binding"]["folder_path"]
    return build_content_read(binding_document, folder_path, path)


__all__ = [
    "CONTENT_NOTES", "CONTENT_SCHEMA", "MAX_CONTENT_BYTES",
    "OUTCOMES", "OUTCOME_BINARY", "OUTCOME_FOLDER_NOT_READY",
    "OUTCOME_OK", "OUTCOME_OVERSIZE", "OUTCOME_UNREADABLE",
    "WorkspaceContentError", "build_content_read",
    "resolve_chat_content",
]
