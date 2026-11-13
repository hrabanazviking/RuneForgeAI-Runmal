"""Workspace tree census HTTP surface (P-181): the
aggregate of one chat's bound folder over P-176's whole
depth-limited tree - kind counts, total file bytes,
extension shape, hidden and escaping-symlink counts,
the largest file, expanded / unexpanded / refused
directory counts and counts by depth - on the
/api/v1/workspaces road, bearer-gated like every API
and wired in app.py.

Owner scoping follows the banked router pattern: a
chat that is unknown - or owned by someone else -
answers 404 ("chat not found"); a known chat with no
binding answers 404 "workspace binding not found" - a
different fact, stated differently, existence never
leaking. A refused subpath answers 422 with P-170's
own refusal. Every census state (folder_not_ready /
empty / no_files / has_files) is DATA at 200, never an
error. The truth layer lives in
runmal.workspaces.tree_census; this module is only the
HTTP shape. This road is disjoint from P-180's content-
search road: it touches no content_search file and
opens no file.
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
from runmal.workspaces import tree_census as tree_census_service

router = APIRouter(tags=["workspaces"])


def _store() -> bindings_service.WorkspaceStore:
    base = Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return bindings_service.WorkspaceStore(base)


@router.get("/workspaces/tree-census")
async def read_workspace_tree_census(
    chat_id: str,
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
        document = await tree_census_service.resolve_chat_tree_census(
            session, _store(), owner_id, chat.id, subpath)
    except listing_service.WorkspaceListingError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None
    if document is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace binding not found")
    return document
