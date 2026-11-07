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


class MessageMoveIn(BaseModel):
    to_index: int


class MessageCopyIn(BaseModel):
    target_chat_id: str | None = None
    title: str | None = None


class SwipeSettingsIn(BaseModel):
    enabled: bool = True
    params: dict = {}


class ContinueIn(BaseModel):
    mode: str = "auto"
    instruction: str | None = None


class ImpersonateIn(BaseModel):
    instruction: str | None = None


class ImpersonateAcceptIn(BaseModel):
    content: str = Field(min_length=1)
    draft_id: str | None = None


class ImpersonateDiscardIn(BaseModel):
    draft_id: str | None = None
class BranchCreate(BaseModel):
    message_id: str | None = None
    name: str | None = None


class MergeBackIn(BaseModel):
    target_id: str | None = None
    name: str | None = None


class BranchNameIn(BaseModel):
    name: str


class CheckpointCreate(BaseModel):
    name: str | None = None


class CheckpointRestoreIn(BaseModel):
    name: str | None = None


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


@router.get("/chats/{chat_id}/messages/{message_id}/variants")
async def get_message_variants(
    chat_id: str,
    message_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """A message's variant history: replaced contents, edit order (P-068)."""
    variants = await service.get_message_variants(session, user_id, chat_id, message_id)
    if variants is None:
        raise HTTPException(status_code=404, detail="message not found")
    return {"message_id": message_id, "variants": variants,
            "variant_count": len(variants)}


@router.post("/chats/{chat_id}/messages/{message_id}/move")
async def move_message(
    chat_id: str,
    message_id: str,
    body: MessageMoveIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Move a message to a strict target index within its chat (P-068)."""
    try:
        message = await service.move_message(
            session, user_id, chat_id, message_id, body.to_index
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if message is None:
        raise HTTPException(status_code=404, detail="message not found")
    return message_to_dict(message)


@router.post("/chats/{chat_id}/messages/{message_id}/copy-to-branch",
             status_code=status.HTTP_201_CREATED)
async def copy_message_to_branch(
    chat_id: str,
    message_id: str,
    body: MessageCopyIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Copy a message to a branch chat (P-068): fork a new chat up to
    and including the message, or copy it into an existing owned chat."""
    try:
        result = await service.copy_message_to_branch(
            session, user_id, chat_id, message_id,
            target_chat_id=body.target_chat_id, title=body.title,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="target chat not found") from None
    if result is None:
        raise HTTPException(status_code=404, detail="message not found")
    return {
        "target_chat": chat_to_dict(result["target_chat"]),
        "copied_message": message_to_dict(result["copied_message"]),
        "copied_count": result["copied_count"],
        "mode": result["mode"],
    }


@router.post("/chats/{chat_id}/messages/{message_id}/pin",
             status_code=status.HTTP_201_CREATED)
async def pin_message(
    chat_id: str,
    message_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Pin a message to memory (P-068): a real pinned Memory record."""
    from runmal.memory.models import memory_to_dict

    memory = await service.pin_message_to_memory(session, user_id, chat_id, message_id)
    if memory is None:
        raise HTTPException(status_code=404, detail="message not found")
    return memory_to_dict(memory)


@router.delete("/chats/{chat_id}/messages/{message_id}/pin")
async def unpin_message(
    chat_id: str,
    message_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Unpin a message (P-068): removes its pin Memory record."""
    removed = await service.unpin_message_from_memory(session, user_id, chat_id, message_id)
    if removed is None:
        raise HTTPException(status_code=404, detail="message not found")
    return {"unpinned": removed, "id": message_id}


@router.get("/chats/{chat_id}/pinned-messages")
async def list_pinned_messages(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """A chat's pinned messages, in display order (P-068)."""
    pinned = await service.list_pinned_messages(session, user_id, chat_id)
    if pinned is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return [message_to_dict(m) for m in pinned]


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


@router.post("/chats/{chat_id}/checkpoints", status_code=status.HTTP_201_CREATED)
async def create_checkpoint(
    chat_id: str,
    body: CheckpointCreate,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Snapshot a chat as a named checkpoint (P-067). Never
    destructive: the source chat is copied, never mutated."""
    from runmal.chats import checkpoints

    try:
        checkpoint = await checkpoints.create_checkpoint(session, user_id, chat_id, body.name)
    except (checkpoints.CheckpointError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if checkpoint is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return checkpoint


@router.get("/chats/{chat_id}/checkpoints")
async def list_checkpoints(
    chat_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """List a chat's checkpoints (P-067), oldest first."""
    from runmal.chats import checkpoints

    try:
        result = await checkpoints.list_checkpoints(session, user_id, chat_id)
    except (checkpoints.CheckpointError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return result


@router.post("/chats/{chat_id}/continue", status_code=status.HTTP_201_CREATED)
async def continue_chat(
    chat_id: str,
    body: ContinueIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Continue a chat (P-069): the model nudges the conversation
    forward and the result LANDS -- extend grows the last
    assistant message in place; next appends a new assistant
    message."""
    from runmal.chats import continue_impersonate as ci

    try:
        result = await ci.continue_chat(
            session, user_id, chat_id, mode=body.mode, instruction=body.instruction
        )
    except ci.GenerationFailedError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return result


@router.get("/chats/{chat_id}/checkpoints/{checkpoint_id}")
async def get_checkpoint(
    chat_id: str,
    checkpoint_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """One checkpoint's metadata (P-067): a verified read, so a
    tampered file is a 422 here, not only at restore."""
    from runmal.chats import checkpoints

    try:
        checkpoint = await checkpoints.get_checkpoint(session, user_id, chat_id, checkpoint_id)
    except (checkpoints.CheckpointError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if checkpoint is None:
        raise HTTPException(status_code=404, detail="chat or checkpoint not found")
    return checkpoint


@router.post(
    "/chats/{chat_id}/checkpoints/{checkpoint_id}/restore",
    status_code=status.HTTP_201_CREATED,
)
async def restore_checkpoint(
    chat_id: str,
    checkpoint_id: str,
    body: CheckpointRestoreIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Restore a checkpoint as a NEW chat (P-067): the snapshot
    moment returns as a chat to continue in; the source chat and
    everything after the checkpoint are never discarded."""
    from runmal.chats import checkpoints

    try:
        restored = await checkpoints.restore_checkpoint(
            session, user_id, chat_id, checkpoint_id, body.name
        )
    except (checkpoints.CheckpointError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if restored is None:
        raise HTTPException(status_code=404, detail="chat or checkpoint not found")
    history = await service.get_history(session, user_id, restored.id) or []
    return chat_to_dict(restored, len(history))


@router.delete("/chats/{chat_id}/checkpoints/{checkpoint_id}")
async def delete_checkpoint(
    chat_id: str,
    checkpoint_id: str,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Delete one checkpoint file (P-067). Only that file is
    removed; the chat, its other checkpoints, and any chat already
    restored from this checkpoint are untouched."""
    from runmal.chats import checkpoints

    try:
        result = await checkpoints.delete_checkpoint(session, user_id, chat_id, checkpoint_id)
    except (checkpoints.CheckpointError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="chat not found")
    if not result:
        raise HTTPException(status_code=404, detail="checkpoint not found")
    return {"deleted": True, "id": checkpoint_id}


@router.post("/chats/{chat_id}/impersonate", status_code=status.HTTP_201_CREATED)
async def impersonate_draft(
    chat_id: str,
    body: ImpersonateIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Draft the next user turn (P-069). The result is a DRAFT
    document only: it is never stored as a message and history
    is untouched until the user accepts a final text."""
    from runmal.chats import continue_impersonate as ci

    try:
        draft = await ci.impersonate_draft(
            session, user_id, chat_id, instruction=body.instruction
        )
    except ci.GenerationFailedError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if draft is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return draft


@router.post(
    "/chats/{chat_id}/impersonate/accept", status_code=status.HTTP_201_CREATED
)
async def accept_impersonate(
    chat_id: str,
    body: ImpersonateAcceptIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Accept an impersonate draft (P-069): the final text the
    user supplies -- the draft verbatim or their edit of it --
    is appended as a real user message. This is the only road
    by which impersonated text becomes a message."""
    from runmal.chats import continue_impersonate as ci

    try:
        message = await ci.accept_impersonate(
            session, user_id, chat_id, body.content, draft_id=body.draft_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if message is None:
        raise HTTPException(status_code=404, detail="chat not found")
    return message_to_dict(message)


@router.post("/chats/{chat_id}/impersonate/discard")
async def discard_impersonate(
    chat_id: str,
    body: ImpersonateDiscardIn,
    user_id: str = Depends(get_owner_id),
    session: AsyncSession = Depends(get_session),
):
    """Discard an impersonate draft (P-069): records the
    discard and stores nothing -- a draft was never stored."""
    from runmal.chats import continue_impersonate as ci

    if not await ci.discard_impersonate(
        session, user_id, chat_id, draft_id=body.draft_id
    ):
        raise HTTPException(status_code=404, detail="chat not found")
    return {"discarded": True, "chat_id": chat_id}


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
