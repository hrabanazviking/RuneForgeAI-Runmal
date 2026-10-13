"""Bridge conversation-state API (S602, BRIDGE_PROTOCOL §3/§6/§7).

The bridge surface over the existing chat domain — no parallel store:

- **Read** returns the chat's state: metadata, the active persona, and
  the ordered messages with their speaker snapshots.
- **Turn writes** declare a speaker kind (`user` / `companion` /
  `environment`) mapped onto stored roles, with the bridge's provenance
  (bridge id, bridge-supplied timestamp, environment metadata) recorded
  in the chat's mutation event log. The server owns final IDs and
  ordering (protocol §6).
- **Generation** composes the prompt server-side from conversation
  state (persona system prompt from the active character's card slots,
  then history) and streams the generation service's normalized events;
  a cleanly finished turn is appended as the active persona. A
  cancelled or errored generation stores nothing.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from runmal.backends import profiles as backend_profiles
from runmal.backends.base import ChatBackend
from runmal.backends.messages import ChatMessage
from runmal.cards import CardParseError, parse_json_card
from runmal.characters.service import get_character
from runmal.chats import service as chats
from runmal.chats.service import chat_to_dict, message_to_dict
from runmal.db.models import Chat, Message
from runmal.generation import service as generation_service
from runmal.persona import build_slot_manifest, render_system_prompt

PROTOCOL_VERSION = "1"

SPEAKER_KIND_ROLES = {
    "user": "user",
    "companion": "assistant",
    "environment": "system",
}


async def get_state(session: AsyncSession, user_id: str, chat_id: str) -> dict | None:
    chat = await chats.get_chat(session, user_id, chat_id)
    if chat is None:
        return None
    history = await chats.get_history(session, user_id, chat_id) or []
    persona = None
    if chat.character_id:
        character = await get_character(session, user_id, chat.character_id)
        if character is not None:
            persona = {"character_id": character.id, "name": character.name}
    payload = chat_to_dict(chat, len(history))
    return {
        "protocol_version": PROTOCOL_VERSION,
        "chat": payload,
        "persona": persona,
        "messages": [message_to_dict(m) for m in history],
    }


async def append_turn(
    session: AsyncSession,
    user_id: str,
    bridge_id: str,
    chat_id: str,
    *,
    speaker_kind: str,
    content: str,
    speaker_id: str | None = None,
    speaker_name: str | None = None,
    bridge_timestamp: str | None = None,
    metadata: dict | None = None,
) -> Message:
    """Append one bridge-declared turn. KeyError: chat; ValueError: bad turn."""
    if speaker_kind not in SPEAKER_KIND_ROLES:
        raise ValueError(f"unknown speaker_kind: {speaker_kind!r}")
    chat = await chats.get_chat(session, user_id, chat_id)
    if chat is None:
        raise KeyError(chat_id)
    resolved_id, resolved_name = await _resolve_speaker(
        session, user_id, chat, speaker_kind, speaker_id, speaker_name
    )
    event_data = {
        "source": "bridge",
        "bridge_id": bridge_id,
        "speaker_kind": speaker_kind,
    }
    if bridge_timestamp is not None:
        event_data["bridge_timestamp"] = bridge_timestamp
    if metadata:
        event_data["metadata"] = metadata
    return await chats.append_message(
        session,
        user_id,
        chat_id,
        SPEAKER_KIND_ROLES[speaker_kind],
        content,
        speaker_id=resolved_id,
        speaker_name=resolved_name,
        event_data=event_data,
    )


async def _resolve_speaker(
    session: AsyncSession,
    user_id: str,
    chat: Chat,
    speaker_kind: str,
    speaker_id: str | None,
    speaker_name: str | None,
) -> tuple[str | None, str | None]:
    if speaker_kind == "companion":
        target_id = speaker_id or chat.character_id
        if target_id is None:
            return None, speaker_name
        character = await get_character(session, user_id, target_id)
        if character is None:
            raise ValueError(f"unknown companion speaker: {target_id!r}")
        return character.id, speaker_name or character.name
    if speaker_id is not None:
        raise ValueError(f"speaker_id is only valid for companion turns, not {speaker_kind!r}")
    if speaker_kind == "environment":
        return None, speaker_name or "environment"
    return None, speaker_name


def persona_system_prompt(character) -> str:
    """The persona's system prompt from its card slots (S110 manifest)."""
    try:
        card = parse_json_card(character.card_json.encode("utf-8"))
    except CardParseError:
        return ""
    return render_system_prompt(build_slot_manifest(card))


async def compose_messages(session: AsyncSession, user_id: str, chat: Chat) -> list[ChatMessage]:
    """Server-side prompt composition from conversation state (§7):
    persona system prompt first, then the stored history in order."""
    messages: list[ChatMessage] = []
    if chat.character_id:
        character = await get_character(session, user_id, chat.character_id)
        if character is not None:
            system_prompt = persona_system_prompt(character)
            if system_prompt:
                messages.append(ChatMessage(role="system", content=system_prompt))
    history = await chats.get_history(session, user_id, chat.id) or []
    messages.extend(ChatMessage(role=m.role, content=m.content) for m in history)
    return messages


async def resolve_chat_backend(session: AsyncSession, user_id: str, chat: Chat) -> ChatBackend:
    """Same resolution as the local /generate route: the chat's pinned
    backend profile when set, else the offline fake default."""
    if chat.backend_profile_id:
        profile = await backend_profiles.get_profile(session, user_id, chat.backend_profile_id)
        if profile is not None:
            return await backend_profiles.build_chat_backend(session, profile)
    return generation_service.default_backend()


async def stream_generation(
    session_factory: async_sessionmaker[AsyncSession],
    user_id: str,
    bridge_id: str,
    chat_id: str,
    request_id: str,
) -> AsyncIterator[dict]:
    """Stream one bridge generation turn (protocol §7).

    Yields `turn_started`, the generation service's normalized events,
    and — only after a clean finish with text — `turn_stored` once the
    assistant message is persisted as the active persona.
    """
    async with session_factory() as session:
        chat = await chats.get_chat(session, user_id, chat_id)
        if chat is None:
            yield {
                "type": "error",
                "code": "chat_not_found",
                "message": "chat not found",
                "retryable": False,
            }
            return
        backend = await resolve_chat_backend(session, user_id, chat)
        messages = await compose_messages(session, user_id, chat)
        persona_id = chat.character_id
        persona_name = None
        if persona_id:
            character = await get_character(session, user_id, persona_id)
            persona_name = character.name if character is not None else None

    yield {
        "type": "turn_started",
        "request_id": request_id,
        "chat_id": chat_id,
        "backend": backend.backend_key,
    }
    parts: list[str] = []
    finish: str | None = None
    saw_error = False
    async for event in generation_service.generate_events(
        request_id, messages=messages, backend=backend
    ):
        if event["type"] == "token":
            parts.append(event["text"])
        elif event["type"] == "error":
            saw_error = True
        elif event["type"] == "done":
            finish = event.get("finish_reason")
        yield event
    text = "".join(parts)
    if saw_error or finish in (None, "cancelled", "error") or not text:
        return
    async with session_factory() as session:
        message = await chats.append_message(
            session,
            user_id,
            chat_id,
            "assistant",
            text,
            speaker_id=persona_id,
            speaker_name=persona_name,
            event_data={
                "source": "bridge-generate",
                "bridge_id": bridge_id,
                "request_id": request_id,
            },
        )
    yield {"type": "turn_stored", "request_id": request_id, "message_id": message.id}


def encode_sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"
