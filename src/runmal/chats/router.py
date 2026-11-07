"""Chat + message REST API (S107). All routes require the local bearer credential."""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.chats import service
from runmal.chats.service import chat_to_dict, event_to_dict, message_to_dict
from runmal.chats.swipes import settings_to_data
from runmal.db.deps import get_owner_id, get_session
from runmal.prompt.authors_note import note_to_data
from runmal.prompt.post_history import instructions_to_data

router = APIRouter(tags=["chats"])


class ChatCreate(BaseModel):
    title: str = ""
    character_id: str | None = None


class ChatUpdate(BaseModel):
    title: str


class MessageCreate(BaseModel):
    role: Literal["user", "assistant", "system"]
    content: str = Field(min_length=1)


class MessageUpdate(BaseModel):
    content: str = Field(min_length=1)


class ChatPresetIn(BaseModel):
    preset_id: str | None = None


class ChatAuthorsNoteIn(BaseModel):
    text: str = ""
    depth: int = 4
    frequency: int = 1
    enabled: bool = True
    role: str = "system"


class ChatPostHistoryIn(BaseModel):
    text: str = ""
    enabled: bool = True
    role: str = "system"


class ChatBackendProfileIn(BaseModel):
    profile_id: str | None = None


class SwipeCreate(BaseModel):
    content: str = Field(min_length=1)


class SwipeSelectIn(BaseModel):
    action: str | None = None
    index: int | None = None


class SwipeSettingsIn(BaseModel):
    enabled: bool = True
    params: dict = {}
class BranchCreate(BaseModel):
    message_id: str | None = None
    name: str | None = None


class MergeBackIn(BaseModel):
    target_id: str | None = None
    name: str | None = None


class BranchNameIn(BaseModel):
    name: str


@router.post("/chats", status_code=status.HTTP_201_CREATED)
async def create_chat(
    body: ChatCreate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        chat = await service.create_chat(session, user_id, body.title, body.character_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="character not found") from None
    return chat_to_dict(chat)


@router.get("/chats")
async def list_chats(
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    return [chat_to_dict(chat, count) for chat, count in await service.list_chats(session, user_id)]


@router.get("/chats/{chat_id}")
async def get_chat(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    chat = await service.get_chat(session, user_id, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    history = await service.get_history(session, user_id, chat_id) or []
    payload = chat_to_dict(chat, len(history))
    payload["messages"] = [message_to_dict(m) for m in history]
    return payload


@router.patch("/chats/{chat_id}")
async def rename_chat(
    chat_id: str,
    body: ChatUpdate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    chat = await service.rename_chat(session, user_id, chat_id, body.title)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return chat_to_dict(chat)


@router.delete("/chats/{chat_id}")
async def delete_chat(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    if not await service.delete_chat(session, user_id, chat_id):
        raise HTTPException(status_code=404, detail="chat not found")
    return {"deleted": True, "id": chat_id}


@router.post("/chats/{chat_id}/messages", status_code=status.HTTP_201_CREATED)
async def append_message(
    chat_id: str,
    body: MessageCreate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        message = await service.append_message(session, user_id, chat_id, body.role, body.content)
    except KeyError:
        raise HTTPException(status_code=404, detail="chat not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return message_to_dict(message)


@router.get("/chats/{chat_id}/messages")
async def get_history(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    history = await service.get_history(session, user_id, chat_id)
    if history is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return [message_to_dict(m) for m in history]


@router.patch("/chats/{chat_id}/messages/{message_id}")
async def edit_message(
    chat_id: str,
    message_id: str,
    body: MessageUpdate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    try:
        message = await service.edit_message(session, user_id, chat_id, message_id, body.content)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if message is None:
        raise HTTPException(status_code=404, detail="message not found")
    return message_to_dict(message)


@router.delete("/chats/{chat_id}/messages/{message_id}")
async def delete_message(
    chat_id: str,
    message_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    if not await service.delete_message(session, user_id, chat_id, message_id):
        raise HTTPException(status_code=404, detail="message not found")
    return {"deleted": True, "id": message_id}


@router.post(
    "/chats/{chat_id}/messages/{message_id}/swipes",
    status_code=status.HTTP_201_CREATED,
)
async def add_swipe(
    chat_id: str,
    message_id: str,
    body: SwipeCreate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Append an alternate to a message's swipe deck (P-065)."""
    try:
        message = await service.add_swipe(
            session, user_id, chat_id, message_id, body.content
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if message is None:
        raise HTTPException(status_code=404, detail="message not found")
    return message_to_dict(message)


@router.post("/chats/{chat_id}/messages/{message_id}/swipes/select")
async def select_swipe(
    chat_id: str,
    message_id: str,
    body: SwipeSelectIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Select the active alternate in a message's swipe deck (P-065)."""
    try:
        message = await service.select_swipe(
            session, user_id, chat_id, message_id,
            action=body.action, index=body.index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if message is None:
        raise HTTPException(status_code=404, detail="message not found")
    return message_to_dict(message)


@router.delete("/chats/{chat_id}/messages/{message_id}/swipes/{index}")
async def delete_swipe(
    chat_id: str,
    message_id: str,
    index: int,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Delete one alternate from a message's swipe deck (P-065)."""
    try:
        message = await service.delete_swipe(
            session, user_id, chat_id, message_id, index
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if message is None:
        raise HTTPException(status_code=404, detail="message not found")
    return message_to_dict(message)


@router.post("/chats/{chat_id}/preset")
async def set_chat_preset(
    chat_id: str,
    body: ChatPresetIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Apply (or clear) a sampling preset on a chat (S306)."""
    try:
        chat = await service.set_chat_preset(
            session, user_id, chat_id, body.preset_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="preset not found") from exc
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return chat_to_dict(chat)


@router.post("/chats/{chat_id}/authors-note")
async def set_chat_authors_note(
    chat_id: str,
    body: ChatAuthorsNoteIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Set a chat's author's note (P-056)."""
    try:
        chat = await service.set_chat_authors_note(
            session, user_id, chat_id, body.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return chat_to_dict(chat)


@router.get("/chats/{chat_id}/authors-note")
async def get_chat_authors_note(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """A chat's author's note (P-056)."""
    note = await service.get_chat_authors_note(session, user_id, chat_id)
    if note is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return note_to_data(note)


@router.post("/chats/{chat_id}/post-history")
async def set_chat_post_history(
    chat_id: str,
    body: ChatPostHistoryIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Set a chat's post-history instructions (P-057)."""
    try:
        chat = await service.set_chat_post_history(
            session, user_id, chat_id, body.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return chat_to_dict(chat)


@router.get("/chats/{chat_id}/post-history")
async def get_chat_post_history(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """A chat's post-history instructions (P-057)."""
    ph = await service.get_chat_post_history(session, user_id, chat_id)
    if ph is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return instructions_to_data(ph)


@router.get("/chats/{chat_id}/swipe-settings")
async def get_chat_swipe_settings(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """A chat's swipe-regeneration settings (P-065)."""
    settings = await service.get_chat_swipe_settings(session, user_id, chat_id)
    if settings is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return settings_to_data(settings)


@router.post("/chats/{chat_id}/swipe-settings")
async def set_chat_swipe_settings(
    chat_id: str,
    body: SwipeSettingsIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Set a chat's swipe-regeneration settings (P-065)."""
    try:
        chat = await service.set_chat_swipe_settings(
            session, user_id, chat_id, body.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return chat_to_dict(chat)


@router.get("/chats/{chat_id}/swipe-regen-params")
async def get_swipe_regen_params(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Effective swipe-regeneration params for a chat (P-065)."""
    resolved = await service.resolve_swipe_params(session, user_id, chat_id)
    if resolved is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return {"chat_id": chat_id, "params": resolved}


@router.post("/chats/{chat_id}/backend-profile")
async def set_chat_backend_profile(
    chat_id: str,
    body: ChatBackendProfileIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Pin (or clear) a chat's backend profile (S307)."""
    try:
        chat = await service.set_chat_backend_profile(
            session, user_id, chat_id, body.profile_id
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="profile not found") from exc
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return chat_to_dict(chat)


@router.get("/chats/{chat_id}/generation-manifest")
async def generation_manifest(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """The generation request manifest for a chat (S306): the applied
    preset's canonical params, compat-filtered (S208) for the active
    connection's backend, with mapped/dropped lists explicit."""
    from runmal.connections import service as connections
    from runmal.generation.compat import filter_for_backend
    from runmal.presets import service as presets

    chat = await service.get_chat(session, user_id, chat_id)
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    active = await connections.get_active(session, user_id)
    backend = active.backend if active else "fake"
    empty = {"chat_id": chat.id, "preset": None, "backend": backend,
             "params": {}, "mapped": [], "dropped": []}
    if not chat.preset_id:
        return empty
    preset = await presets.get_preset(session, user_id, chat.preset_id)
    if preset is None:  # preset deleted after being applied
        return {**empty, "note": "applied preset no longer exists"}
    preset_dict = presets.preset_to_dict(preset)
    if backend in ("openai", "ollama"):
        filtered = filter_for_backend(preset_dict["params"], backend)
        return {
            "chat_id": chat.id,
            "preset": preset_dict,
            "backend": backend,
            "params": filtered.params,
            "mapped": [vars(m) for m in filtered.mapped],
            "dropped": [vars(d) for d in filtered.dropped],
        }
    # the fake backend takes the canonical bag as-is
    return {"chat_id": chat.id, "preset": preset_dict, "backend": backend,
            "params": preset_dict["params"], "mapped": [], "dropped": []}


@router.post("/chats/{chat_id}/branches", status_code=status.HTTP_201_CREATED)
async def fork_chat(
    chat_id: str,
    body: BranchCreate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Fork a chat at a message (P-066). Never destructive: the
    source is copied, never mutated. No message_id = whole chat."""
    from runmal.chats import branches

    try:
        branch = await branches.fork_chat(session, user_id, chat_id, body.message_id, body.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if branch is None:
        raise HTTPException(status_code=404, detail="chat not found")
    history = await service.get_history(session, user_id, branch.id) or []
    return chat_to_dict(branch, len(history))


@router.get("/chats/{chat_id}/branches")
async def list_branches(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """A chat's branch family (P-066): root, ancestors, self,
    children, descendants, family -- every member named."""
    from runmal.chats import branches

    family = await branches.list_branch_family(session, user_id, chat_id)
    if family is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return family


@router.post("/chats/{chat_id}/merge-back", status_code=status.HTTP_201_CREATED)
async def merge_back(
    chat_id: str,
    body: MergeBackIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Merge a branch back as a NEW branch (P-066): target history
    plus the branch's divergent suffix. Sources are never mutated.
    target_id defaults to the branch's parent."""
    from runmal.chats import branches

    try:
        merged = await branches.merge_back(session, user_id, chat_id, body.target_id, body.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if merged is None:
        raise HTTPException(status_code=404, detail="chat or target not found")
    history = await service.get_history(session, user_id, merged.id) or []
    return chat_to_dict(merged, len(history))


@router.post("/chats/{chat_id}/branch-name")
async def rename_branch(
    chat_id: str,
    body: BranchNameIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Name a branch (P-066): sets the branch's own title only."""
    from runmal.chats import branches

    try:
        chat = await branches.rename_branch(session, user_id, chat_id, body.name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if chat is None:
        raise HTTPException(status_code=404, detail="chat not found")
    history = await service.get_history(session, user_id, chat_id) or []
    return chat_to_dict(chat, len(history))


@router.get("/chats/{chat_id}/export")
async def export_chat(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Download a portable JSON export of the chat (S111). Non-destructive."""
    document = await service.export_chat(session, user_id, chat_id)
    if document is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return document


@router.get("/chats/{chat_id}/events")
async def list_events(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    events = await service.list_events(session, user_id, chat_id)
    if events is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return [event_to_dict(e) for e in events]
