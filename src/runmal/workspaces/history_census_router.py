"""Workspace binding-history census HTTP surface
(P-177): one owner whole history estate - ended
bindings by cause, by the folders live states today,
by whether their chats still exist, by folder sharing
across endings and by label presence - on the
/api/v1/workspaces road, bearer-gated like every API
and wired in app.py.

Owner scoping: the census subject is the caller
themselves - there is no id or filter parameter,
nothing foreign can be named, and every census state
(no_history / no_live_chats / all_live_chats /
some_live_chats) is DATA at 200, never an error. The
truth layer lives in runmal.workspaces.history_census
(composing P-173 history verbatim); this module is
only the HTTP shape. This road is disjoint from the
P-173 history list / P-175 deletion roads: it deletes
nothing and ends no binding.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.deps import get_owner_id, get_session
from runmal.workspaces import bindings as bindings_service
from runmal.workspaces import history_census as census_service

router = APIRouter(tags=["workspaces"])


def _store() -> bindings_service.WorkspaceStore:
    base = Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return bindings_service.WorkspaceStore(base)


@router.get("/workspaces/history-census")
async def workspace_history_census(
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    return await census_service.resolve_workspace_history_census(
        session, _store(), owner_id)
