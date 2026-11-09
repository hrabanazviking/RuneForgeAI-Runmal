"""Workspace bindings (P-169, Part XI opener - DERIVED).

The roadmap gives Part XI one line only ("Workspaces -
the Companion That Works", P-169..P-186); this slice's
scope is derived from Runmal's own in-tree record - see
docs/WORKSPACE_BINDING_2026-11-09.md and
hidden_files/P169_SCOUT.md / P169_DESIGN.md.

What the derivation found: the census (P-003) names the
part's ground VX-54..VX-58 and the delta table (P-004)
judges every row MISSING. VX-54's first clause - a chat
bound to a real folder - presupposes every other row:
no file tool, coding-agent backend, path rule or
done-signal exists without a binding that says WHICH
folder a chat works in. No binding record existed
anywhere in the tree. This module is that record:

- ONE binding per owned chat: the chat, the operator's
  folder path stored verbatim as data, and an optional
  label. Rebinding is unbind-then-bind, never a silent
  overwrite. The same folder may be bound by several
  chats - no record forbids it, and none is invented.
- The binding LAW is P-121's (the vision watch
  registration, the one chat-bound folder record the
  tree already kept): the path is the operator's own
  path, stored as data; binding never claims the
  folder exists - existence is a READ-TIME fact,
  judged live from the filesystem on every document
  this module builds, under the closed FOLDER_STATES
  law, and a missing / not-a-directory / unreadable
  folder is a named state, never an error and never
  dressed as ready.
- Persistence rides the P-117 house pattern: a
  versioned JSON index (``workspaces.json``) in the
  data dir, tolerant load - a corrupt store reads as
  empty and never bricks the surface. NO migration:
  head stays 0041.
- Custody: a chat's binding dies with the chat -
  ``purge_chat`` is wired into the delete_chat chain
  in runmal.chats.service beside the P-121 watcher
  purge. A binding whose chat is gone anyway (a
  missed purge) is an ORPHAN: the owner list counts
  orphans plainly and never presents one as live.

P-173 amendment (binding history): when a binding ends
- by explicit unbind or by the chat-deletion custody
purge - the superseded binding no longer vanishes: the
store archives it as a history entry (the binding's own
fields verbatim, the ending moment, and the ending
cause under the closed HISTORY_EVENTS law) in the SAME
index, under a top-level ``history`` key beside
``bindings``. Live-binding semantics are unchanged;
runmal.workspaces.history serves the owner-scoped read.

Honest boundaries: a binding is DATA ONLY. This slice
reads no file contents, lists no folder, writes
nothing into any folder, runs nothing and launches
nothing - file tools, agent backends and the VX-57
path guard are later Part XI slices, named open in
the slice doc. A binding GRANTS nothing: no tool,
backend or process inherits any access from a binding
existing. Content stays data, never code (P-027).
"""

from __future__ import annotations

import json
import os
import stat as stat_module
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

BINDINGS_VERSION = 1
BINDINGS_FILENAME = "workspaces.json"

BINDING_SCHEMA = "runmal-p169-workspace-binding-v1"
LIST_SCHEMA = "runmal-p169-workspace-list-v1"
HISTORY_SCHEMA = "runmal-p173-workspace-history-v1"

EVENT_UNBOUND = "unbound"
EVENT_CHAT_DELETED = "chat_deleted"
HISTORY_EVENTS = frozenset({EVENT_UNBOUND, EVENT_CHAT_DELETED})

FOLDER_READY = "ready"
FOLDER_MISSING = "missing"
FOLDER_NOT_A_DIRECTORY = "not_a_directory"
FOLDER_UNREADABLE = "unreadable"
FOLDER_STATES = frozenset({
    FOLDER_READY, FOLDER_MISSING,
    FOLDER_NOT_A_DIRECTORY, FOLDER_UNREADABLE,
})

NOTES = (
    "A binding is data only: this surface reads no "
    "file contents, lists no folder, writes nothing "
    "into any folder, runs nothing and launches "
    "nothing - file tools, coding-agent backends and "
    "the tool-calling guard are later Part XI work, "
    "named open, not silently present.",
    "The folder path is the operator's own path, "
    "stored as data and never claimed to exist; the "
    "folder state in this document was judged live "
    "from the filesystem at read time, and a missing, "
    "not-a-directory or unreadable folder is a named "
    "state, never an error dressed as success.",
    "One binding per chat: rebinding a chat is "
    "unbind-then-bind, never a silent overwrite; the "
    "same folder may be bound by several chats.",
    "A binding grants nothing: no tool, backend or "
    "process inherits any access from a binding "
    "existing - the path rules and scopes that will "
    "govern workspace tools are a later slice.",
    "Owner scoped throughout: a binding is visible "
    "only to its owner, a chat's binding dies with "
    "the chat, and an orphaned binding (its chat "
    "gone) is counted in the owner list, never "
    "presented as a live binding.",
)


class WorkspaceError(ValueError):
    """A workspace operation the state of the world forbids."""


def bindings_path(data_dir: Path | None = None) -> Path:
    base = data_dir or Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return base / BINDINGS_FILENAME


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ------------------------------------------------------------ record


@dataclass(frozen=True)
class WorkspaceBinding:
    """One binding: a chat bound to a real folder path."""

    id: str
    owner_id: str
    chat_id: str
    folder_path: str  # operator-supplied folder path, stored as data
    label: str
    created_at: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "owner_id": self.owner_id,
            "chat_id": self.chat_id,
            "folder_path": self.folder_path,
            "label": self.label,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorkspaceBinding:
        return cls(
            id=str(data.get("id", "")),
            owner_id=str(data.get("owner_id", "")),
            chat_id=str(data.get("chat_id", "")),
            folder_path=str(data.get("folder_path", "")),
            label=str(data.get("label", "")),
            created_at=str(data.get("created_at", "")),
        )


@dataclass(frozen=True)
class WorkspaceHistoryEntry:
    """One ended binding, kept as history data (P-173).

    Every field except ``id``, ``ended_at`` and ``event``
    is the superseded binding's own field, verbatim;
    ``bound_at`` is the binding's ``created_at``. The
    store records no actor beyond ``owner_id``, so no
    actor is invented here.
    """

    id: str
    binding_id: str
    owner_id: str
    chat_id: str
    folder_path: str
    label: str
    bound_at: str
    ended_at: str
    event: str

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "binding_id": self.binding_id,
            "owner_id": self.owner_id,
            "chat_id": self.chat_id,
            "folder_path": self.folder_path,
            "label": self.label,
            "bound_at": self.bound_at,
            "ended_at": self.ended_at,
            "event": self.event,
        }

    @classmethod
    def from_dict(cls, data: dict) -> WorkspaceHistoryEntry:
        return cls(
            id=str(data.get("id", "")),
            binding_id=str(data.get("binding_id", "")),
            owner_id=str(data.get("owner_id", "")),
            chat_id=str(data.get("chat_id", "")),
            folder_path=str(data.get("folder_path", "")),
            label=str(data.get("label", "")),
            bound_at=str(data.get("bound_at", "")),
            ended_at=str(data.get("ended_at", "")),
            event=str(data.get("event", "")),
        )

    @classmethod
    def from_binding(cls, binding: WorkspaceBinding, *,
                     event: str, ended_at: str) -> WorkspaceHistoryEntry:
        return cls(
            id=str(uuid.uuid4()),
            binding_id=binding.id,
            owner_id=binding.owner_id,
            chat_id=binding.chat_id,
            folder_path=binding.folder_path,
            label=binding.label,
            bound_at=binding.created_at,
            ended_at=ended_at,
            event=event,
        )


# ------------------------------------------------------------- store


class WorkspaceStore:
    """Durable binding store: one JSON index in the data dir.

    Holds the workspace bindings. A corrupt index reads
    as empty and never bricks the surface (the P-117
    tolerant-load stance). Since P-173 the same index
    also holds the binding history (a top-level
    ``history`` list beside ``bindings``): every save
    preserves it, and a file without the key - every
    pre-P-173 store - reads as empty history.
    """

    def __init__(self, data_dir: Path):
        self.data_dir = Path(data_dir)
        self.index_path = self.data_dir / BINDINGS_FILENAME

    def _load_doc(self) -> tuple[list[WorkspaceBinding],
                                 list[WorkspaceHistoryEntry]]:
        try:
            doc = json.loads(self.index_path.read_text())
        except (OSError, ValueError):
            return [], []
        if not isinstance(doc, dict):
            return [], []
        rows: list[WorkspaceBinding] = []
        raw = doc.get("bindings")
        if isinstance(raw, list):
            for row in raw:
                if isinstance(row, dict):
                    rows.append(WorkspaceBinding.from_dict(row))
        history: list[WorkspaceHistoryEntry] = []
        raw_history = doc.get("history")
        if isinstance(raw_history, list):
            for row in raw_history:
                if isinstance(row, dict):
                    history.append(WorkspaceHistoryEntry.from_dict(row))
        return rows, history

    def _load(self) -> list[WorkspaceBinding]:
        return self._load_doc()[0]

    def _load_history(self) -> list[WorkspaceHistoryEntry]:
        return self._load_doc()[1]

    def _save_all(self, bindings: list[WorkspaceBinding],
                  history: list[WorkspaceHistoryEntry]) -> None:
        doc = {
            "version": BINDINGS_VERSION,
            "bindings": [row.to_dict() for row in bindings],
            "history": [row.to_dict() for row in history],
        }
        self.index_path.parent.mkdir(parents=True, exist_ok=True)
        self.index_path.write_text(json.dumps(doc, indent=2, sort_keys=True))

    def _save(self, bindings: list[WorkspaceBinding]) -> None:
        # A bindings-only save must never erase history
        # archived by the ending verbs (P-173): re-read
        # the on-disk history and write it back whole.
        self._save_all(bindings, self._load_history())

    def add_binding(self, binding: WorkspaceBinding) -> WorkspaceBinding:
        rows = self._load()
        self._save(rows + [binding])
        return binding

    def get_binding(self, binding_id: str) -> WorkspaceBinding | None:
        for row in self._load():
            if row.id == binding_id:
                return row
        return None

    def get_for_chat(self, chat_id: str) -> WorkspaceBinding | None:
        for row in self._load():
            if row.chat_id == chat_id:
                return row
        return None

    def list_for_owner(self, owner_id: str) -> list[WorkspaceBinding]:
        return [row for row in self._load() if row.owner_id == owner_id]

    def remove_binding(self, binding_id: str,
                       *, now: str | None = None,
                       ) -> WorkspaceBinding | None:
        """Remove a live binding, archiving it (P-173).

        On a hit the superseded binding is appended to
        the history (event ``unbound``) in the same save
        that removes it; a miss removes nothing and
        writes no history. The return contract is
        P-169's: the removed binding, or None.
        """
        rows, history = self._load_doc()
        removed = [row for row in rows if row.id == binding_id]
        if not removed:
            return None
        entry = WorkspaceHistoryEntry.from_binding(
            removed[0], event=EVENT_UNBOUND,
            ended_at=now or _now_iso())
        self._save_all(
            [row for row in rows if row.id != binding_id],
            history + [entry])
        return removed[0]

    def purge_chat(self, chat_id: str,
                   *, now: str | None = None) -> int:
        """Custody: drop a chat's binding. Returns rows removed.

        Each dropped binding is archived as history
        (event ``chat_deleted``, P-173) in the same save.
        History entries themselves are RETAINED at chat
        deletion: custody governs live bindings, and
        history is the owner's audit record - purging it
        here would destroy the chat_deleted entry in the
        moment it is created. The return contract is
        P-169's: the count of live bindings removed.
        """
        rows, history = self._load_doc()
        kept = [row for row in rows if row.chat_id != chat_id]
        dropped = [row for row in rows if row.chat_id == chat_id]
        if not dropped:
            return 0
        ended = now or _now_iso()
        entries = [
            WorkspaceHistoryEntry.from_binding(
                row, event=EVENT_CHAT_DELETED, ended_at=ended)
            for row in dropped]
        self._save_all(kept, history + entries)
        return len(dropped)

    def list_history_for_owner(
            self, owner_id: str) -> list[WorkspaceHistoryEntry]:
        """The owner's history entries, in store order."""
        return [row for row in self._load_history()
                if row.owner_id == owner_id]


# ----------------------------------------------------------- service


def register_binding(
    store: WorkspaceStore,
    *,
    owner_id: str,
    chat_id: str,
    folder_path: str,
    label: str = "",
    now: str | None = None,
) -> WorkspaceBinding:
    """Bind a chat to a folder path (the path stored as data).

    Refusals are plain and total - nothing is stored: an
    empty path, an empty chat id, and a chat that is
    already bound (one binding per chat; unbind first)
    each raise ``WorkspaceError``. The folder is NOT
    required to exist and is never inspected here:
    existence is a read-time fact, never faked at bind
    time (the P-121 registration law). Chat existence
    and ownership are the caller's law - the HTTP road
    verifies the owned chat before calling.
    """
    cleaned = (folder_path or "").strip()
    if not cleaned:
        raise WorkspaceError("a workspace folder path is required")
    if not (chat_id or "").strip():
        raise WorkspaceError("a chat is required")
    if store.get_for_chat(chat_id) is not None:
        raise WorkspaceError(
            "this chat is already bound to a workspace folder; "
            "unbind it first")
    binding = WorkspaceBinding(
        id=str(uuid.uuid4()),
        owner_id=owner_id,
        chat_id=chat_id,
        folder_path=cleaned,
        label=(label or "").strip(),
        created_at=now or _now_iso(),
    )
    return store.add_binding(binding)


def folder_state(folder_path: str) -> str:
    """Judge one folder path LIVE, under FOLDER_STATES.

    Follows symlinks as the filesystem does; never
    raises for a bad path. A path that cannot be
    stat'ed because it does not exist is ``missing``;
    a stat failure for any other reason (a parent the
    process cannot search, a loop) is ``unreadable`` -
    the folder may well exist, and this judgement does
    not claim otherwise.
    """
    try:
        info = os.stat(folder_path)
    except FileNotFoundError:
        return FOLDER_MISSING
    except OSError:
        return FOLDER_UNREADABLE
    if not stat_module.S_ISDIR(info.st_mode):
        return FOLDER_NOT_A_DIRECTORY
    if not os.access(folder_path, os.R_OK | os.X_OK):
        return FOLDER_UNREADABLE
    return FOLDER_READY


def binding_document(binding: WorkspaceBinding, chat) -> dict:
    """The single-binding document: the binding verbatim,
    the chat's own facts (id / title / character_id, from
    the Chat row itself), and the folder state judged
    live at this call."""
    return {
        "schema": BINDING_SCHEMA,
        "binding": binding.to_dict(),
        "chat": {
            "id": chat.id,
            "title": chat.title,
            "character_id": chat.character_id,
        },
        "folder_state": folder_state(binding.folder_path),
        "notes": list(NOTES),
    }


async def resolve_chat_workspace(session, store: WorkspaceStore,
                                 user_id: str, chat_id: str) -> dict | None:
    """The workspace document for one chat.

    None when the chat is missing or foreign (existence
    never leaks, the house law) and None when the chat
    exists but is unbound - at the service layer both
    are simply "no workspace document"; the HTTP road
    keeps the two 404 details apart by checking the
    chat first. Otherwise the binding document, with
    the folder state judged live.
    """
    from runmal.chats import service as chat_service

    chat = await chat_service.get_chat(session, user_id, chat_id)
    if chat is None:
        return None
    binding = store.get_for_chat(chat_id)
    if binding is None or binding.owner_id != user_id:
        return None
    return binding_document(binding, chat)


async def list_owner_workspaces(session, store: WorkspaceStore,
                                user_id: str) -> dict:
    """The owner list document: one binding document per
    owned binding whose chat still exists, in store
    append order, with the counts carried from the
    documents' own states. Bindings whose chat is gone
    are orphans: excluded from the rows and counted as
    ``orphan_count``, stated plainly - never silently
    dropped, never presented as live."""
    from runmal.chats import service as chat_service

    documents: list[dict] = []
    orphans = 0
    for binding in store.list_for_owner(user_id):
        chat = await chat_service.get_chat(session, user_id, binding.chat_id)
        if chat is None:
            orphans += 1
            continue
        documents.append(binding_document(binding, chat))
    return {
        "schema": LIST_SCHEMA,
        "workspaces": documents,
        "binding_count": len(documents),
        "ready_count": sum(
            1 for doc in documents if doc["folder_state"] == FOLDER_READY),
        "orphan_count": orphans,
        "notes": list(NOTES),
    }


__all__ = [
    "BINDINGS_FILENAME", "BINDINGS_VERSION", "BINDING_SCHEMA",
    "FOLDER_MISSING", "FOLDER_NOT_A_DIRECTORY", "FOLDER_READY",
    "FOLDER_STATES", "FOLDER_UNREADABLE", "LIST_SCHEMA", "NOTES",
    "EVENT_CHAT_DELETED", "EVENT_UNBOUND", "HISTORY_EVENTS",
    "HISTORY_SCHEMA", "WorkspaceBinding", "WorkspaceError",
    "WorkspaceHistoryEntry", "WorkspaceStore",
    "binding_document", "bindings_path", "folder_state",
    "list_owner_workspaces", "register_binding",
    "resolve_chat_workspace",
]
