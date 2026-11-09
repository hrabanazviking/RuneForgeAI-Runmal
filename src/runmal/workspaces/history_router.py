"""Workspace binding-history HTTP surface (P-173): one
owner's ended bindings - unbound and chat-deleted -
kept as data in P-169's own store, on the
/api/v1/workspaces road, bearer-gated like every API
and wired in app.py.

Owner scoping: the history subject is the caller
themselves - the only selector is an optional chat_id
filter over the caller's OWN entries, so nothing
foreign can be named and nothing can leak. Every
outcome is DATA at 200, never an error: an owner with
no history gets the honest empty document, and a
filter naming a foreign, unknown or deleted chat gets
that chat's (empty or kept) history - a deleted chat's
entries are the surface's reason to exist, so this
road deliberately has no chat-existence 404, unlike
the live-binding roads. The truth layer lives in
runmal.workspaces.history (over the store amendment
in runmal.workspaces.bindings); this module is only
the HTTP shape. These roads are disjoint from the
live binding, listing, content and census roads:
they end no binding. Since P-175 this router also
carries the owner-scoped history-deletion road:
DELETE /workspaces/history/{entry_id} deletes ONE
of the caller's own entries permanently - an
unknown or foreign entry answers 404 ("workspace
history entry not found"), existence never leaks,
and the success shape is the P-169 unbind shape,
{"deleted": True, "id"}. That road is the P-173
named-open retention cell in its smallest
owner-hand form; no automatic retention policy
is claimed.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.workspaces import bindings as bindings_service
from runmal.workspaces import history as history_service

router = APIRouter(tags=["workspaces"])


def _store() -> bindings_service.WorkspaceStore:
    base = Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return bindings_service.WorkspaceStore(base)


@router.get("/workspaces/history")
async def workspace_history(
    chat_id: str | None = None,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    return await history_service.resolve_workspace_history(
        session, _store(), owner_id, chat_id)


@router.delete("/workspaces/history/{entry_id}")
async def delete_workspace_history(
    entry_id: str,
    owner_id: str = Depends(get_owner_id),
):
    removed = history_service.delete_workspace_history_entry(
        _store(), owner_id, entry_id)
    if removed is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace history entry not found")
    return {"deleted": True, "id": entry_id}
