"""Workspace census HTTP surface (P-171): one owner's
whole workspace estate - chats bound and unbound, the
bound folders' live states, and folder sharing - on
the /api/v1/workspaces road, bearer-gated like every
API and wired in app.py.

Owner scoping: the census subject is the caller
themselves - there is no id parameter, nothing foreign
can be named, and every census state (no_chats,
no_bindings, none_ready, some_ready, all_ready) is
DATA at 200, never an error: the client decides what
to show from the named states. The truth layer lives
in runmal.workspaces.census; this module is only the
HTTP shape. This road is disjoint from the folder
listing / files-browser roads: it lists no folder
and reads no file contents.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.workspaces import bindings as bindings_service
from runmal.workspaces import census as census_service

router = APIRouter(tags=["workspaces"])


def _store() -> bindings_service.WorkspaceStore:
    base = Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return bindings_service.WorkspaceStore(base)


@router.get("/workspaces/census")
async def workspace_census(
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    return await census_service.resolve_workspace_census(
        session, _store(), owner_id)
