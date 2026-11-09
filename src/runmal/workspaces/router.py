"""Workspace binding HTTP surface (P-169): bind an owned
chat to a real folder, read the binding back with the
folder's state judged live, list the owner's bindings,
and unbind - on the /api/v1/workspaces road,
bearer-gated like every API and wired in app.py.

Owner scoping: a chat that is unknown - or owned by
someone else - answers 404 ("chat not found") on the
bind and per-chat roads; a binding that is unknown or
foreign answers 404 on the delete road. Existence
never leaks. A known chat with no binding answers 404
"workspace binding not found" on the per-chat road -
a different fact from a missing chat, and stated
differently. Every folder state (ready / missing /
not_a_directory / unreadable) is DATA at 200 on a
read, never an error: the client decides what to show
from the named states. The truth layer lives in
runmal.workspaces.bindings; this module is only the
HTTP shape.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.chats import service as chat_service
from runmal.db.deps import get_owner_id, get_session
from runmal.workspaces import bindings as bindings_service

router = APIRouter(tags=["workspaces"])


def _store() -> bindings_service.WorkspaceStore:
    base = Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return bindings_service.WorkspaceStore(base)


async def _chat_or_404(session: AsyncSession, owner_id: str, chat_id: str):
    chat = await chat_service.get_chat(session, owner_id, chat_id)
    if chat is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="chat not found")
    return chat


class BindRequest(BaseModel):
    chat_id: str
    folder_path: str
    label: str = ""


@router.post("/workspaces/bindings", status_code=status.HTTP_201_CREATED)
async def bind_workspace(
    body: BindRequest,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    chat = await _chat_or_404(session, owner_id, body.chat_id)
    try:
        binding = bindings_service.register_binding(
            _store(), owner_id=owner_id, chat_id=chat.id,
            folder_path=body.folder_path, label=body.label)
    except bindings_service.WorkspaceError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc)) from None
    return bindings_service.binding_document(binding, chat)


@router.get("/workspaces/bindings")
async def read_chat_workspace(
    chat_id: str,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    chat = await _chat_or_404(session, owner_id, chat_id)
    binding = _store().get_for_chat(chat.id)
    if binding is None or binding.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace binding not found")
    return bindings_service.binding_document(binding, chat)


@router.get("/workspaces")
async def list_workspaces(
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
):
    return await bindings_service.list_owner_workspaces(
        session, _store(), owner_id)


@router.delete("/workspaces/bindings/{binding_id}")
async def unbind_workspace(
    binding_id: str,
    owner_id: str = Depends(get_owner_id),
):
    store = _store()
    binding = store.get_binding(binding_id)
    if binding is None or binding.owner_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="workspace binding not found")
    store.remove_binding(binding_id)
    return {"deleted": True, "id": binding_id}
