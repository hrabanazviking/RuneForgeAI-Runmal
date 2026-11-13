"""Workspace content search HTTP surface (P-180): one
chat's bound folder searched by file content over
P-176's tree, every candidate read through P-172 - on
the /api/v1/workspaces road, bearer-gated like every
API and wired in app.py.

Owner scoping follows the banked router pattern: a chat
that is unknown - or owned by someone else - answers 404
("chat not found"); a known chat with no binding answers
404 "workspace binding not found" - a different fact,
stated differently, existence never leaking. A refused
subpath answers 422 with P-170's own refusal and a
refused query answers 422 with the content search's own
refusal. Every folder state (ready / missing /
not_a_directory / unreadable) is DATA at 200, never an
error. The truth layer lives in
runmal.workspaces.content_search; this module is only
the HTTP shape. This road is disjoint from P-178's
filename-search road: it opens files only through
P-172's read law and touches no history file and no
bindings file.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.chats import service as chat_service
from runmal.db.deps import get_owner_id, get_session
from runmal.workspaces import bindings as bindings_service
from runmal.workspaces import content_search as content_search_service
from runmal.workspaces import listing as listing_service

router = APIRouter(tags=["workspaces"])


def _store() -> bindings_service.WorkspaceStore:
    base = Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return bindings_service.WorkspaceStore(base)


@router.get("/workspaces/content-search")
async def search_workspace_content(
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
        document = await content_search_service.resolve_chat_content_search(
            session, _store(), owner_id, chat.id, q, subpath)
    except (listing_service.WorkspaceListingError,
            content_search_service.WorkspaceContentSearchError) as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace binding not found")
    return document
