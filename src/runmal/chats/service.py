"""Chat + message CRUD with stable IDs, mutation timestamps, and a durable
mutation event log (S107). Events feed future memory sync."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.characters.service import get_character as get_char
from runmal.db.models import Chat, ChatEvent, Message

VALID_ROLES = frozenset({"user", "assistant", "system"})

EVENT_CHAT_CREATED = "chat.created"
EVENT_CHAT_RENAMED = "chat.renamed"
EVENT_MESSAGE_APPENDED = "message.appended"
EVENT_MESSAGE_EDITED = "message.edited"
EVENT_MESSAGE_DELETED = "message.deleted"


def _now() -> datetime:
    return datetime.now(UTC)


def chat_to_dict(chat: Chat, message_count: int = 0) -> dict:
    return {
        "id": chat.id,
        "title": chat.title,
        "character_id": chat.character_id,
        "preset_id": chat.preset_id,
        "backend_profile_id": chat.backend_profile_id,
        "created_at": chat.created_at.isoformat(),
        "message_count": message_count,
    }


def message_to_dict(message: Message) -> dict:
    return {
        "id": message.id,
        "chat_id": message.chat_id,
        "role": message.role,
        "content": message.content,
        "speaker_id": message.speaker_id,
        "speaker_name": message.speaker_name,
        "created_at": message.created_at.isoformat(),
        "updated_at": message.updated_at.isoformat() if message.updated_at else None,
    }


def event_to_dict(event: ChatEvent) -> dict:
    return {
        "id": event.id,
        "chat_id": event.chat_id,
        "message_id": event.message_id,
        "kind": event.kind,
        "data": json.loads(event.data),
        "created_at": event.created_at.isoformat(),
    }


async def _record_event(
    session: AsyncSession,
    chat_id: str,
    kind: str,
    message_id: str | None = None,
    data: dict | None = None,
) -> ChatEvent:
    event = ChatEvent(
        chat_id=chat_id,
        message_id=message_id,
        kind=kind,
        data=json.dumps(data or {}),
    )
    session.add(event)
    await session.flush()
    return event


async def _get_owned_chat(session: AsyncSession, user_id: str, chat_id: str) -> Chat | None:
    result = await session.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id))
    return result.scalar_one_or_none()


async def create_chat(
    session: AsyncSession,
    user_id: str,
    title: str = "",
    character_id: str | None = None,
) -> Chat:
    if character_id is not None and await get_char(session, user_id, character_id) is None:
        raise KeyError(character_id)
    chat = Chat(user_id=user_id, title=title, character_id=character_id)
    session.add(chat)
    await session.flush()
    await _record_event(
        session, chat.id, EVENT_CHAT_CREATED, data={"title": title, "character_id": character_id}
    )
    await session.commit()
    return chat


async def list_chats(session: AsyncSession, user_id: str) -> list[tuple[Chat, int]]:
    result = await session.execute(
        select(Chat, func.count(Message.id))
        .outerjoin(Message, Message.chat_id == Chat.id)
        .where(Chat.user_id == user_id)
        .group_by(Chat.id)
        .order_by(Chat.created_at)
    )
    return [(chat, count) for chat, count in result.all()]


async def get_chat(session: AsyncSession, user_id: str, chat_id: str) -> Chat | None:
    return await _get_owned_chat(session, user_id, chat_id)


async def set_chat_preset(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    preset_id: str | None,
) -> Chat | None:
    """Apply (or clear, with None) a sampling preset on a chat (S306).

    Both the chat and the preset must belong to the user; a foreign or
    missing preset raises KeyError, a missing chat returns None.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    if preset_id is not None:
        from runmal.presets import service as presets

        if await presets.get_preset(session, user_id, preset_id) is None:
            raise KeyError(preset_id)
    chat.preset_id = preset_id
    await session.commit()
    return chat


async def set_chat_backend_profile(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    profile_id: str | None,
) -> Chat | None:
    """Pin (or clear, with None) a chat's backend profile (S306/S307).

    Both the chat and the profile must belong to the user; a foreign or
    missing profile raises KeyError, a missing chat returns None.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    if profile_id is not None:
        from runmal.backends import profiles as backend_profiles

        if await backend_profiles.get_profile(session, user_id, profile_id) is None:
            raise KeyError(profile_id)
    chat.backend_profile_id = profile_id
    await session.commit()
    return chat


async def rename_chat(session: AsyncSession, user_id: str, chat_id: str, title: str) -> Chat | None:
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    chat.title = title
    await _record_event(session, chat.id, EVENT_CHAT_RENAMED, data={"title": title})
    await session.commit()
    return chat


async def delete_chat(session: AsyncSession, user_id: str, chat_id: str) -> bool:
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return False
    # No chat.deleted event: the FK cascade wipes this chat's event log anyway.
    await session.execute(delete(Chat).where(Chat.id == chat_id))
    await session.commit()
    return True


async def append_message(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    role: str,
    content: str,
    *,
    speaker_id: str | None = None,
    speaker_name: str | None = None,
    event_data: dict | None = None,
) -> Message:
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        raise KeyError(chat_id)
    if role not in VALID_ROLES:
        raise ValueError(f"invalid role: {role!r}")
    if not content:
        raise ValueError("message content must not be empty")
    message = Message(
        chat_id=chat_id,
        role=role,
        content=content,
        speaker_id=speaker_id,
        speaker_name=speaker_name,
    )
    session.add(message)
    await session.flush()
    data = {"role": role}
    if event_data:
        data.update(event_data)
    await _record_event(session, chat_id, EVENT_MESSAGE_APPENDED, message_id=message.id, data=data)
    await session.commit()
    return message


async def get_history(session: AsyncSession, user_id: str, chat_id: str) -> list[Message] | None:
    if await _get_owned_chat(session, user_id, chat_id) is None:
        return None
    result = await session.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at)
    )
    return list(result.scalars().all())


async def edit_message(
    session: AsyncSession, user_id: str, chat_id: str, message_id: str, content: str
) -> Message | None:
    if await _get_owned_chat(session, user_id, chat_id) is None:
        return None
    result = await session.execute(
        select(Message).where(Message.id == message_id, Message.chat_id == chat_id)
    )
    message = result.scalar_one_or_none()
    if message is None:
        return None
    if not content:
        raise ValueError("message content must not be empty")
    message.content = content
    message.updated_at = _now()
    await _record_event(session, chat_id, EVENT_MESSAGE_EDITED, message_id=message.id)
    await session.commit()
    return message


async def delete_message(
    session: AsyncSession, user_id: str, chat_id: str, message_id: str
) -> bool:
    if await _get_owned_chat(session, user_id, chat_id) is None:
        return False
    result = await session.execute(
        select(Message).where(Message.id == message_id, Message.chat_id == chat_id)
    )
    if result.scalar_one_or_none() is None:
        return False
    await _record_event(session, chat_id, EVENT_MESSAGE_DELETED, message_id=message_id)
    await session.execute(delete(Message).where(Message.id == message_id))
    await session.commit()
    return True


EXPORT_FORMAT = "runmal-chat-export"
EXPORT_VERSION = 1


async def export_chat(session: AsyncSession, user_id: str, chat_id: str) -> dict | None:
    """Build a self-contained portable export document for a chat (S111)."""
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    history = await get_history(session, user_id, chat_id) or []
    return {
        "format": EXPORT_FORMAT,
        "version": EXPORT_VERSION,
        "exported_at": _now().isoformat(),
        "chat": {
            "id": chat.id,
            "title": chat.title,
            "character_id": chat.character_id,
            "created_at": chat.created_at.isoformat(),
        },
        "messages": [message_to_dict(m) for m in history],
    }


async def list_events(session: AsyncSession, user_id: str, chat_id: str) -> list[ChatEvent] | None:
    if await _get_owned_chat(session, user_id, chat_id) is None:
        return None
    result = await session.execute(
        select(ChatEvent).where(ChatEvent.chat_id == chat_id).order_by(ChatEvent.created_at)
    )
    return list(result.scalars().all())
