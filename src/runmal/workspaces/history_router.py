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
the HTTP shape. This road is disjoint from the live
binding, listing, content and census roads: it ends
no binding and deletes no history.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends
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
