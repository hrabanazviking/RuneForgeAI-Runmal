"""Workspace census (P-171, Part XI - DERIVED scope).

The roadmap gives Part XI one line only ("Workspaces -
the Companion That Works", P-169..P-186); this slice's
scope is derived from Runmal's own in-tree record - see
docs/WORKSPACE_CENSUS_2026-11-09.md and
hidden_files/P171_SCOUT.md / P171_DESIGN.md.

What the derivation found: P-169 banked the binding
foundation - one binding per owned chat, folder state
judged live at read - and named its own limitation: the
binding had no consumer yet. P-170 (team-02, in flight,
not in this base) takes the folder-listing consumer.
The cell no surface takes is the OWNER's whole estate:
across all of one owner's chats, how many are bound,
how the bound folders distribute across P-169's folder
states, and whether several chats share one folder -
a fact P-169's law permits and no surface named. The
house pattern for exactly this is the census (P-164,
P-148): a pure read composing the owning surface
verbatim, classified under a closed law, counts summed
from the composed documents' own arithmetic. That is
what lives here:

- the rows are P-169's owner list document composed
  VERBATIM - list_owner_workspaces' rows whole, its
  orphan count carried, never recomputed under a
  second law, and no second store or folder-state
  law invented;
- the chat axis comes from chats.service.list_chats:
  the owner's chat count, the bound count (the rows),
  and the unbound remainder;
- the state axis sums the rows' own folder_state
  values under P-169's closed FOLDER_STATES law;
- the sharing axis groups the rows' own folder_path
  values: distinct folders, folders bound by more
  than one live binding, and how many bindings sit
  on shared folders;
- the estate is classified under a closed census
  law (CENSUS_STATES): no_chats / no_bindings /
  none_ready / some_ready / all_ready.

Honest boundaries: this census reads NO folder
contents and lists NO folder - the files browser is
P-170's road, in flight on another team. It writes
nothing, binds nothing, unbinds nothing, runs and
launches nothing, and grants nothing: a binding's
existence gives no tool, backend or process any
access (P-169's law, restated). Folder states are
P-169's live read-time judgements, point-in-time at
this call. No store, no migration: head stays 0041.
"""

from __future__ import annotations

from runmal.workspaces import bindings as bindings_service

CENSUS_SCHEMA = "runmal-p171-workspace-census-v1"

CENSUS_STATE_NO_CHATS = "no_chats"
CENSUS_STATE_NO_BINDINGS = "no_bindings"
CENSUS_STATE_NONE_READY = "none_ready"
CENSUS_STATE_SOME_READY = "some_ready"
CENSUS_STATE_ALL_READY = "all_ready"
CENSUS_STATES = frozenset({
    CENSUS_STATE_NO_CHATS, CENSUS_STATE_NO_BINDINGS,
    CENSUS_STATE_NONE_READY, CENSUS_STATE_SOME_READY,
    CENSUS_STATE_ALL_READY,
})

NOTES = (
    "Pure read, owner scoped: only the caller's own "
    "chats and bindings appear; this census stores, "
    "binds, unbinds, writes and deletes nothing.",
    "Every row is P-169's owner-list document composed "
    "verbatim, and every folder state is P-169's own "
    "live read-time judgement under its closed law "
    "(ready / missing / not_a_directory / unreadable) "
    "- no second folder-state law is invented here.",
    "This census reads no folder contents and lists "
    "no folder: the read-only files browser over a "
    "binding is a separate Part XI road, not claimed "
    "or restated here.",
    "A census grants nothing: no tool, backend or "
    "process inherits any access from a binding "
    "existing, and this surface runs and launches "
    "nothing (P-027: content is data, never code).",
    "Folder sharing is named, never judged: P-169 "
    "permits several chats to bind the same folder, "
    "so the census counts shared folders as a fact "
    "of the estate, not as an error.",
    "Orphaned bindings (their chat gone) are carried "
    "from P-169's own count, excluded from the rows, "
    "and never presented as live bindings.",
)


async def resolve_workspace_census(session, store, user_id: str) -> dict:
    """The workspace census for one owner.

    Always a document, never None: the subject is the
    caller themselves, so there is no foreign subject
    whose existence could leak, and an owner with no
    chats gets the honest empty census (state
    no_chats). Otherwise the envelope described in
    the module docstring: P-169's owner list composed
    verbatim as the rows, the chat / state / sharing
    counts summed from those rows and the owner's
    chat list, and the estate classified under
    CENSUS_STATES.
    """
    from runmal.chats import service as chat_service

    list_doc = await bindings_service.list_owner_workspaces(
        session, store, user_id)
    rows = list_doc["workspaces"]
    binding_count = list_doc["binding_count"]

    chats = await chat_service.list_chats(session, user_id)
    chat_count = len(chats)
    unbound_chat_count = max(chat_count - binding_count, 0)

    state_counts = {
        state: 0 for state in sorted(bindings_service.FOLDER_STATES)}
    for row in rows:
        state_counts[row["folder_state"]] += 1

    folder_use: dict[str, int] = {}
    for row in rows:
        path = row["binding"]["folder_path"]
        folder_use[path] = folder_use.get(path, 0) + 1
    shared = {p: n for p, n in folder_use.items() if n > 1}

    if chat_count == 0:
        census_state = CENSUS_STATE_NO_CHATS
    elif binding_count == 0:
        census_state = CENSUS_STATE_NO_BINDINGS
    elif state_counts[bindings_service.FOLDER_READY] == 0:
        census_state = CENSUS_STATE_NONE_READY
    elif state_counts[bindings_service.FOLDER_READY] == binding_count:
        census_state = CENSUS_STATE_ALL_READY
    else:
        census_state = CENSUS_STATE_SOME_READY

    return {
        "schema": CENSUS_SCHEMA,
        "census_state": census_state,
        "workspaces": rows,
        "chat_count": chat_count,
        "binding_count": binding_count,
        "bound_chat_count": binding_count,
        "unbound_chat_count": unbound_chat_count,
        "ready_count": state_counts[bindings_service.FOLDER_READY],
        "missing_count": state_counts[bindings_service.FOLDER_MISSING],
        "not_a_directory_count": state_counts[
            bindings_service.FOLDER_NOT_A_DIRECTORY],
        "unreadable_count": state_counts[
            bindings_service.FOLDER_UNREADABLE],
        "folder_state_counts": state_counts,
        "distinct_folder_count": len(folder_use),
        "shared_folder_count": len(shared),
        "bindings_on_shared_folders": sum(shared.values()),
        "orphan_count": list_doc["orphan_count"],
        "notes": list(NOTES),
    }


__all__ = [
    "CENSUS_SCHEMA", "CENSUS_STATE_ALL_READY",
    "CENSUS_STATE_NO_BINDINGS", "CENSUS_STATE_NO_CHATS",
    "CENSUS_STATE_NONE_READY", "CENSUS_STATE_SOME_READY",
    "CENSUS_STATES", "NOTES", "resolve_workspace_census",
]
