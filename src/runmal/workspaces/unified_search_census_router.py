"""Workspace unified search census HTTP surface (P-184):
the aggregate of one chat's unified search for one query -
the matched_by, kind, extension, depth, byte and
occurrence shape of P-182's returned union and the
outcome shape of its skipped files, the source counts
and partiality verdicts carried verbatim - on the
/api/v1/workspaces road, bearer-gated like every API
and wired in app.py.

Owner scoping follows the banked router pattern: a
chat that is unknown - or owned by someone else -
answers 404 ("chat not found"); a known chat with no
binding answers 404 "workspace binding not found" - a
different fact, stated differently, existence never
leaking. A refused subpath answers 422 with P-170's
own refusal and a refused query answers 422 with
P-182's own refusal. Every census state
(folder_not_ready / no_matches / name_only /
content_only / mixed) is DATA at 200, never an error.
The truth layer lives in
runmal.workspaces.unified_search_census; this module
is only the HTTP shape. This road is disjoint from
P-182's unified-search road: it composes it, touches
no unified_search, history or bindings file.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.chats import service as chat_service
from runmal.db.deps import get_owner_id, get_session
from runmal.workspaces import bindings as bindings_service
from runmal.workspaces import listing as listing_service
from runmal.workspaces import unified_search as unified_search_service
from runmal.workspaces import (
    unified_search_census as unified_search_census_service)

router = APIRouter(tags=["workspaces"])


def _store() -> bindings_service.WorkspaceStore:
    base = Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return bindings_service.WorkspaceStore(base)


@router.get("/workspaces/unified-search-census")
async def read_workspace_unified_search_census(
    chat_id: str,
    q: str = "",
    subpath: str = "",
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    chat = await chat_service.get_chat(session, owner_id, chat_id)
    if chat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="chat not found")
    binding = _store().get_for_chat(chat.id)
    if binding is None or binding.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace binding not found")
    try:
        document = await \
            unified_search_census_service.resolve_chat_unified_search_census(
                session, _store(), owner_id, chat.id, q, subpath)
    except (listing_service.WorkspaceListingError,
            unified_search_service.WorkspaceUnifiedSearchError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace binding not found")
    return document
