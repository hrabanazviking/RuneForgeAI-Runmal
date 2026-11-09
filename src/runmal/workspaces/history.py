"""Workspace binding history (P-173, Part XI - DERIVED).

P-171's banked record declined this cell by name:
"rebind history (a foundation amendment to P-169's
store shape) stays named open". This slice is that
amendment's read surface. The amendment itself lives
in runmal.workspaces.bindings, where the store now
archives every ended binding - explicit unbind and
chat-deletion custody purge alike - as a history entry
in the SAME workspaces.json index (no second store
file). What lives here is only the document law for
reading that history back:

- Owner scoped throughout: the subject is the caller;
  only the caller's own entries ever appear. An
  optional chat filter names only the caller's own
  entries for that chat - a foreign or unknown chat id
  yields an honest empty document, never an error and
  never a leak.
- NO chat-existence gate, deliberately unlike the
  live-binding roads: a deleted chat's entries are the
  history's most important rows (the chat_deleted
  entries exist only for gone chats), so they are
  returned with chat_exists judged live and stated
  plainly, never hidden behind a 404.
- Each entry rides verbatim from the store, plus two
  read-time judgements, both labelled as such: the
  folder's state judged LIVE at this read under
  P-169's folder_state() (never claimed as the state
  at the ending), and whether the entry's chat still
  exists (with its title when it does).
- Counts are summed from the returned entries
  themselves: entry_count, unbound_count,
  chat_deleted_count, chat_count (distinct chats).

Honest boundaries: this surface is a pure read - it
archives nothing itself, deletes no history, writes
nothing anywhere, reads no file contents, lists no
folder, runs and launches nothing, and grants nothing
(P-169's law; P-027: content is data, never code).
History entries are retained when their chat is
deleted (see bindings.WorkspaceStore.purge_chat for
the judged custody call); no history-retention or
history-deletion road exists yet - named open.
"""

from __future__ import annotations

from runmal.workspaces.bindings import (
    EVENT_CHAT_DELETED,
    EVENT_UNBOUND,
    HISTORY_SCHEMA,
    WorkspaceHistoryEntry,
    folder_state,
)

HISTORY_NOTES = (
    "History is kept data, not a live surface: every "
    "entry is a binding that has ENDED - unbound by "
    "its owner, or purged when its chat was deleted - "
    "with the binding's own fields carried verbatim "
    "and the ending's moment and cause named under a "
    "closed law (unbound / chat_deleted).",
    "Owner scoped throughout: only the caller's own "
    "entries appear, and a chat filter names only the "
    "caller's own entries for that chat; a foreign or "
    "unknown chat id reads as an empty history, never "
    "as another owner's record.",
    "A deleted chat's entries are returned on purpose: "
    "history outlives the binding, so there is no "
    "chat-existence gate here - each entry carries "
    "chat_exists judged live at this read, and a gone "
    "chat is a named fact, not a hidden row.",
    "The folder state on each entry was judged live "
    "from the filesystem at THIS read under P-169's "
    "law; it is not claimed as the state the folder "
    "had when the binding ended.",
    "This surface is a pure read: it stores, archives, "
    "deletes, writes and runs nothing, reads no file "
    "contents and lists no folder, and a binding - "
    "live or historical - grants nothing.",
)


def history_entry_document(entry: WorkspaceHistoryEntry,
                           chat) -> dict:
    """One history entry document: the entry verbatim,
    the folder state judged LIVE at this call, and the
    entry's chat facts - its title and existence when
    the chat is still there, a plain absence when the
    chat is gone. ``chat`` is a Chat row or None."""
    return {
        "entry": entry.to_dict(),
        "folder_state": folder_state(entry.folder_path),
        "chat_exists": chat is not None,
        "chat_title": chat.title if chat is not None else None,
    }


async def resolve_workspace_history(session, store, user_id: str,
                                    chat_id: str | None = None) -> dict:
    """The binding-history document for one owner.

    Always a document, never None: the subject is the
    caller themselves, so there is no foreign subject
    whose existence could leak. Entries are the
    owner's own, in store (chronological append)
    order, optionally narrowed to one chat. Each
    entry's chat is resolved through
    chats.service.get_chat under the caller's ownership
    - a chat that is gone (or was never the caller's)
    judges chat_exists False, and its entries still
    appear: history has no existence gate.
    """
    from runmal.chats import service as chat_service

    entries = store.list_history_for_owner(user_id)
    if chat_id is not None:
        entries = [row for row in entries if row.chat_id == chat_id]
    documents: list[dict] = []
    for entry in entries:
        chat = await chat_service.get_chat(session, user_id, entry.chat_id)
        documents.append(history_entry_document(entry, chat))
    return {
        "schema": HISTORY_SCHEMA,
        "history": documents,
        "entry_count": len(documents),
        "unbound_count": sum(
            1 for doc in documents
            if doc["entry"]["event"] == EVENT_UNBOUND),
        "chat_deleted_count": sum(
            1 for doc in documents
            if doc["entry"]["event"] == EVENT_CHAT_DELETED),
        "chat_count": len({doc["entry"]["chat_id"] for doc in documents}),
        "chat_id": chat_id,
        "notes": list(HISTORY_NOTES),
    }


__all__ = [
    "HISTORY_NOTES", "HISTORY_SCHEMA", "history_entry_document",
    "resolve_workspace_history",
]
