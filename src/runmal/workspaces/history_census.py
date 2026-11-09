"""Workspace binding-history census (P-177, Part XI - DERIVED).

The roadmap gives Part XI one line only ("Workspaces -
the Companion That Works", P-169..P-186); this slice
scope is derived from Runmal own in-tree record - see
docs/WORKSPACE_HISTORY_CENSUS_2026-11-09.md and
hidden_files/P177_SCOUT.md / P177_DESIGN.md.

What the derivation found: P-171 censused the owner
LIVE binding estate and P-174 one live folder, while
P-173 banked the binding HISTORY - every ended binding
kept as data - with only a list read (four counts
summed inline) and, since P-175, a single-entry delete.
No surface aggregates the history estate: how ended
bindings distribute by ending cause, by the folder
live state today, by whether their chats still exist,
by folder sharing across endings, or by label presence.
P-176 evidence named this cell the first post-P-175
candidate; P-175 is banked in this base. The house
pattern is the census (P-148 / P-164 / P-165 / P-171):
a pure read composing the owning surface verbatim,
classified under a closed law, counts summed from the
composed document own fields. P-165 (owner-wide face
history census) is the direct precedent. That is here:

- the history document is P-173 resolve_workspace_
  history composed VERBATIM with no chat filter,
  embedded whole; its entry / unbound / chat_deleted /
  chat counts are carried, never recomputed;
- the folder-state axis sums each entry document own
  folder_state under P-169 closed FOLDER_STATES law -
  no second folder-state law;
- the existence axis sums chat_exists (P-173 live
  read-time judgement): entries whose chat still lives
  vs entries whose chat is gone, and the distinct
  chats on each side;
- the sharing axis groups entry folder_path values:
  distinct folders, folders ended into by more than
  one entry, entries on shared folders;
- the label axis counts entries by their verbatim
  label: labelled vs unlabelled;
- the estate is classified under the closed
  HISTORY_CENSUS_STATES law: no_history /
  no_live_chats / all_live_chats / some_live_chats.

Honest boundaries: this census is a pure read - it
deletes no history (P-175 owns single-entry deletion),
ends no binding, writes nothing, reads no file
contents, lists no folder, runs and launches nothing,
watches nothing and grants nothing (P-169 law; P-027:
content is data, never code). Folder states and chat
existence are P-173 live read-time judgements at THIS
call, never claimed as the state at the ending. No
store, no migration: head stays 0041.
"""

from __future__ import annotations

from runmal.workspaces import bindings as bindings_service
from runmal.workspaces import history as history_service

HISTORY_CENSUS_SCHEMA = "runmal-p177-workspace-history-census-v1"

STATE_NO_HISTORY = "no_history"
STATE_NO_LIVE_CHATS = "no_live_chats"
STATE_ALL_LIVE_CHATS = "all_live_chats"
STATE_SOME_LIVE_CHATS = "some_live_chats"
HISTORY_CENSUS_STATES = frozenset({
    STATE_NO_HISTORY, STATE_NO_LIVE_CHATS,
    STATE_ALL_LIVE_CHATS, STATE_SOME_LIVE_CHATS,
})

HISTORY_CENSUS_NOTES = (
    "Pure read, owner scoped: only the caller own "
    "history entries appear; this census stores, "
    "archives, deletes, binds, unbinds, writes and "
    "runs nothing - single-entry history deletion "
    "is a separate road (P-175).",
    "The history document is P-173 binding-history "
    "read composed verbatim and embedded whole, "
    "with no chat filter: its counts are carried, "
    "and every other count here is summed from "
    "that document own entry fields only - no "
    "second history law is invented here.",
    "Folder states and chat existence are P-173 "
    "live read-time judgements under P-169 law, "
    "judged at THIS call: they are not claimed as "
    "the state the folder or chat had when the "
    "binding ended.",
    "Folder sharing across endings is named, never "
    "judged: the same folder may end into history "
    "more than once, so shared folders are counted "
    "as a fact of the history estate.",
    "Label counts describe the entries verbatim "
    "labels only (labelled vs unlabelled); this "
    "census edits no label and no binding.",
    "A census grants nothing: no tool, backend or "
    "process inherits any access from a binding - "
    "live or historical - existing, and workspace "
    "writes wait for the tool-calling guard "
    "(VX-57) while execution stays declined "
    "(P-027: content is data, never code).",
)


def build_history_census(history_document: dict) -> dict:
    """The history census for one P-173 document.

    Sums only the history document own fields; the
    document is embedded whole. An empty history is
    the honest no_history zero document - data,
    never an error.
    """
    documents = history_document["history"]
    entry_count = history_document["entry_count"]
    state_counts = {
        state: 0 for state in sorted(bindings_service.FOLDER_STATES)}
    live_entries = 0
    live_chats: set[str] = set()
    gone_chats: set[str] = set()
    folder_use: dict[str, int] = {}
    labelled = 0
    for doc in documents:
        state_counts[doc["folder_state"]] += 1
        entry = doc["entry"]
        if doc["chat_exists"]:
            live_entries += 1
            live_chats.add(entry["chat_id"])
        else:
            gone_chats.add(entry["chat_id"])
        path = entry["folder_path"]
        folder_use[path] = folder_use.get(path, 0) + 1
        if entry["label"]:
            labelled += 1
    shared = {p: n for p, n in folder_use.items() if n > 1}
    if entry_count == 0:
        census_state = STATE_NO_HISTORY
    elif live_entries == 0:
        census_state = STATE_NO_LIVE_CHATS
    elif live_entries == entry_count:
        census_state = STATE_ALL_LIVE_CHATS
    else:
        census_state = STATE_SOME_LIVE_CHATS
    return {
        "schema": HISTORY_CENSUS_SCHEMA,
        "census_state": census_state,
        "history_document": history_document,
        "entry_count": entry_count,
        "unbound_count": history_document["unbound_count"],
        "chat_deleted_count": history_document["chat_deleted_count"],
        "chat_count": history_document["chat_count"],
        "folder_state_counts": state_counts,
        "ready_count": state_counts[bindings_service.FOLDER_READY],
        "missing_count": state_counts[bindings_service.FOLDER_MISSING],
        "not_a_directory_count": state_counts[
            bindings_service.FOLDER_NOT_A_DIRECTORY],
        "unreadable_count": state_counts[
            bindings_service.FOLDER_UNREADABLE],
        "live_chat_entry_count": live_entries,
        "gone_chat_entry_count": entry_count - live_entries,
        "live_chat_count": len(live_chats),
        "gone_chat_count": len(gone_chats),
        "distinct_folder_count": len(folder_use),
        "shared_folder_count": len(shared),
        "entries_on_shared_folders": sum(shared.values()),
        "labelled_count": labelled,
        "unlabelled_count": entry_count - labelled,
        "notes": list(HISTORY_CENSUS_NOTES),
    }


async def resolve_workspace_history_census(session, store,
                                           user_id: str) -> dict:
    """The binding-history census for one owner.

    Always a document, never None: the subject is
    the caller themselves, so there is no foreign
    subject whose existence could leak, and an owner
    with no history gets the honest empty census
    (state no_history). Otherwise P-173 history
    document (no chat filter) composed verbatim and
    classified under HISTORY_CENSUS_STATES.
    """
    history_document = await history_service.resolve_workspace_history(
        session, store, user_id, None)
    return build_history_census(history_document)


__all__ = [
    "HISTORY_CENSUS_NOTES", "HISTORY_CENSUS_SCHEMA",
    "HISTORY_CENSUS_STATES", "STATE_ALL_LIVE_CHATS",
    "STATE_NO_HISTORY", "STATE_NO_LIVE_CHATS",
    "STATE_SOME_LIVE_CHATS", "build_history_census",
    "resolve_workspace_history_census",
]
