"""Chat + message CRUD with stable IDs, mutation timestamps, and a durable
mutation event log (S107). Events feed future memory sync."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.characters.service import get_character as get_char
from runmal.chats import swipes as swipe_mod
from runmal.chats.swipes import (
    SwipeRegenSettings,
    settings_from_data,
    settings_to_data,
)
from runmal.db.models import Chat, ChatEvent, Message
from runmal.prompt.authors_note import AuthorsNote, note_from_data, note_to_data
from runmal.prompt.post_history import (
    PostHistoryInstructions,
    instructions_from_data,
    instructions_to_data,
)

VALID_ROLES = frozenset({"user", "assistant", "system"})

EVENT_CHAT_CREATED = "chat.created"
EVENT_CHAT_RENAMED = "chat.renamed"
EVENT_PERSONA_CHANGED = "persona.changed"
EVENT_MESSAGE_APPENDED = "message.appended"
EVENT_MESSAGE_EDITED = "message.edited"
EVENT_MESSAGE_DELETED = "message.deleted"
EVENT_AUTHORS_NOTE_CHANGED = "authors_note.changed"
EVENT_POST_HISTORY_CHANGED = "post_history.changed"
EVENT_MESSAGE_SWIPE_ADDED = "message.swipe_added"
EVENT_MESSAGE_SWIPE_SELECTED = "message.swipe_selected"
EVENT_MESSAGE_SWIPE_DELETED = "message.swipe_deleted"
EVENT_SWIPE_SETTINGS_CHANGED = "swipe_settings.changed"
EVENT_BRANCH_CREATED = "branch.created"
EVENT_BRANCH_FORKED = "branch.forked"
EVENT_BRANCH_MERGED = "branch.merged"
EVENT_BRANCH_RENAMED = "branch.renamed"


def _now() -> datetime:
    return datetime.now(UTC)


def _post_history_from_chat(chat: Chat) -> PostHistoryInstructions:
    try:
        raw = getattr(chat, "post_history_json", None)
        parsed = json.loads(raw) if raw else None
        return instructions_from_data(parsed)
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return PostHistoryInstructions()


def _swipe_settings_from_chat(chat: Chat) -> SwipeRegenSettings:
    try:
        raw = getattr(chat, "swipe_settings_json", None)
        parsed = json.loads(raw) if raw else None
        return settings_from_data(parsed)
    except (json.JSONDecodeError, ValueError, TypeError, AttributeError):
        return SwipeRegenSettings()


def _deck(message: Message) -> tuple[list[str], int]:
    return swipe_mod.deck_for(
        message.content,
        getattr(message, "swipes_json", None),
        getattr(message, "swipe_id", 0),
    )


def _store_deck(message: Message, swipes_list: list[str], swipe_id: int) -> None:
    message.swipes_json = json.dumps(swipes_list)
    message.swipe_id = swipe_id
    message.content = swipes_list[swipe_id]


async def _get_owned_message(
    session: AsyncSession, user_id: str, chat_id: str, message_id: str
) -> Message | None:
    if await _get_owned_chat(session, user_id, chat_id) is None:
        return None
    result = await session.execute(
        select(Message).where(Message.id == message_id, Message.chat_id == chat_id)
    )
    return result.scalar_one_or_none()


def chat_to_dict(chat: Chat, message_count: int = 0) -> dict:
    try:
        note = note_from_data(json.loads(chat.authors_note_json or "{}"))
    except (json.JSONDecodeError, ValueError, TypeError):
        note = AuthorsNote()
    ph = _post_history_from_chat(chat)
    from runmal.chats.branches import branch_info

    return {
        "id": chat.id,
        "title": chat.title,
        "character_id": chat.character_id,
        "preset_id": chat.preset_id,
        "backend_profile_id": chat.backend_profile_id,
        "created_at": chat.created_at.isoformat(),
        "message_count": message_count,
        "authors_note": note_to_data(note),
        "post_history": instructions_to_data(ph),
        "swipe_settings": settings_to_data(_swipe_settings_from_chat(chat)),
        "branch": branch_info(chat),
    }


def message_to_dict(message: Message) -> dict:
    deck, swipe_id = _deck(message)
    return {
        "id": message.id,
        "chat_id": message.chat_id,
        "role": message.role,
        "content": message.content,
        "swipes": deck,
        "swipe_id": swipe_id,
        "swipe_count": len(deck),
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


async def get_chat_authors_note(
    session: AsyncSession, user_id: str, chat_id: str
) -> AuthorsNote | None:
    """The chat's author's note (P-056), or None when the chat is missing.

    A corrupt stored document reads as the default (empty) note rather
    than failing the read.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    try:
        return note_from_data(json.loads(chat.authors_note_json or "{}"))
    except (json.JSONDecodeError, ValueError, TypeError):
        return AuthorsNote()


async def set_chat_authors_note(
    session: AsyncSession, user_id: str, chat_id: str, data: dict
) -> Chat | None:
    """Set a chat's author's note (P-056).

    The chat must belong to the user; a missing chat returns None.
    Invalid note data raises ValueError and stores nothing. The
    mutation event records only depth/frequency/enabled -- never the
    note text.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    note = note_from_data(data)
    chat.authors_note_json = json.dumps(note_to_data(note))
    await _record_event(
        session,
        chat.id,
        EVENT_AUTHORS_NOTE_CHANGED,
        data={"depth": note.depth, "frequency": note.frequency, "enabled": note.enabled},
    )
    await session.commit()
    return chat


async def get_chat_post_history(
    session: AsyncSession, user_id: str, chat_id: str
) -> PostHistoryInstructions | None:
    """The chat's post-history instructions (P-057), or None when missing.

    A corrupt stored document reads as the default (empty)
    instructions rather than failing the read.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    return _post_history_from_chat(chat)


async def set_chat_post_history(
    session: AsyncSession, user_id: str, chat_id: str, data: dict
) -> Chat | None:
    """Set a chat's post-history instructions (P-057).

    The chat must belong to the user; a missing chat returns None.
    Invalid data raises ValueError and stores nothing. The mutation
    event records only enabled/role -- never the instruction text.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    ph = instructions_from_data(data)
    chat.post_history_json = json.dumps(instructions_to_data(ph))
    await _record_event(
        session,
        chat.id,
        EVENT_POST_HISTORY_CHANGED,
        data={"enabled": ph.enabled, "role": ph.role},
    )
    await session.commit()
    return chat


async def get_chat_swipe_settings(
    session: AsyncSession, user_id: str, chat_id: str
) -> SwipeRegenSettings | None:
    """The chat's swipe-regeneration settings (P-065), or None when missing.

    A corrupt stored document reads as the default settings rather
    than failing the read.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    return _swipe_settings_from_chat(chat)


async def set_chat_swipe_settings(
    session: AsyncSession, user_id: str, chat_id: str, data: dict
) -> Chat | None:
    """Set a chat's swipe-regeneration settings (P-065).

    The chat must belong to the user; a missing chat returns None.
    Invalid data raises ValueError and stores nothing. The mutation
    event records only enabled and the sorted parameter keys --
    never the parameter values.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    settings = settings_from_data(data)
    chat.swipe_settings_json = json.dumps(settings_to_data(settings))
    await _record_event(
        session,
        chat.id,
        EVENT_SWIPE_SETTINGS_CHANGED,
        data={"enabled": settings.enabled, "param_keys": sorted(settings.params)},
    )
    await session.commit()
    return chat

async def set_chat_persona(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    character_id: str | None,
    *,
    event_data: dict | None = None,
) -> Chat | None:
    """Switch a chat's active persona (S603, BRIDGE_PROTOCOL §8).

    An explicit state change affecting FUTURE turns only: stored
    messages keep their original speaker snapshots, and a
    `persona.changed` mutation event records the switch. Both the chat
    and the character must belong to the user; a foreign or missing
    character raises KeyError, a missing chat returns None. Passing the
    already-active persona is a no-op (no duplicate event).
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    if character_id is not None and await get_char(session, user_id, character_id) is None:
        raise KeyError(character_id)
    if chat.character_id == character_id:
        return chat
    previous = chat.character_id
    chat.character_id = character_id
    data = {"from": previous, "to": character_id}
    if event_data:
        data.update(event_data)
    await _record_event(session, chat.id, EVENT_PERSONA_CHANGED, data=data)
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
        swipes_json=json.dumps([content]),
        swipe_id=0,
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
    deck, idx = _deck(message)
    new_deck = list(deck)
    new_deck[idx] = content
    _store_deck(message, new_deck, idx)
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


async def add_swipe(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    message_id: str,
    content: str,
) -> Message | None:
    """Append a new alternate to a message's swipe deck (P-065).

    The new alternate becomes the active one. Returns None when the
    chat or message is missing/foreign. Invalid content raises
    ValueError. The mutation event records only counts -- never
    the alternate text.
    """
    message = await _get_owned_message(session, user_id, chat_id, message_id)
    if message is None:
        return None
    swipe_mod.validate_new_alternate(content)
    deck, _idx = _deck(message)
    new_deck = list(deck)
    new_deck.append(content)
    new_id = len(new_deck) - 1
    _store_deck(message, new_deck, new_id)
    await _record_event(
        session,
        chat_id,
        EVENT_MESSAGE_SWIPE_ADDED,
        message_id=message.id,
        data={"swipe_count": len(new_deck), "swipe_id": new_id},
    )
    await session.commit()
    return message


async def select_swipe(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    message_id: str,
    *,
    action: str | None = None,
    index: int | None = None,
) -> Message | None:
    """Select the active alternate in a message's swipe deck (P-065).

    Exactly one of ``action`` (one of next/prev/first/last, clamped
    navigation) or ``index`` (strict selection) must be given.
    Returns None when the chat or message is missing/foreign. When
    the selection does not change, the message is returned with no
    event recorded and no commit needed.
    """
    message = await _get_owned_message(session, user_id, chat_id, message_id)
    if message is None:
        return None
    if (action is None) == (index is None):
        raise ValueError("exactly one of action or index is required")
    deck, current = _deck(message)
    if index is not None:
        new_id = swipe_mod.select_index(deck, index)
    else:
        if action not in {"next", "prev", "first", "last"}:
            raise ValueError(f"unknown swipe navigation action: {action!r}")
        new_id = swipe_mod.navigate(deck, current, action)
    if new_id == current:
        return message
    _store_deck(message, list(deck), new_id)
    await _record_event(
        session,
        chat_id,
        EVENT_MESSAGE_SWIPE_SELECTED,
        message_id=message.id,
        data={"swipe_id": new_id, "swipe_count": len(deck)},
    )
    await session.commit()
    return message


async def delete_swipe(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    message_id: str,
    index: int,
) -> Message | None:
    """Delete one alternate from a message's swipe deck (P-065).

    The index is strict (out of range raises ValueError), and the
    last remaining alternate cannot be deleted. The active index
    shifts to keep pointing at the same alternate where possible;
    deleting the active alternate activates the next one, or the
    previous one when the deleted alternate was last.
    """
    message = await _get_owned_message(session, user_id, chat_id, message_id)
    if message is None:
        return None
    deck, active = _deck(message)
    swipe_mod.select_index(deck, index)
    if len(deck) == 1:
        raise ValueError("cannot delete the only swipe")
    new_deck = list(deck)
    del new_deck[index]
    if index < active:
        new_active = active - 1
    elif index == active:
        new_active = min(index, len(new_deck) - 1)
    else:
        new_active = active
    _store_deck(message, new_deck, new_active)
    await _record_event(
        session,
        chat_id,
        EVENT_MESSAGE_SWIPE_DELETED,
        message_id=message.id,
        data={"index": index, "swipe_count": len(new_deck)},
    )
    await session.commit()
    return message


async def resolve_swipe_params(
    session: AsyncSession, user_id: str, chat_id: str
) -> dict | None:
    """Resolve effective swipe-regeneration params for a chat (P-065).

    The base is the chat's applied preset params ({} when there is
    no preset or the preset is missing/deleted); the chat's swipe
    settings override per-key when enabled. Returns None when the
    chat is missing/foreign.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    base: dict = {}
    if chat.preset_id:
        from runmal.presets import service as presets

        preset = await presets.get_preset(session, user_id, chat.preset_id)
        if preset is not None:
            params = presets.preset_to_dict(preset).get("params")
            if isinstance(params, dict):
                base = params
    return swipe_mod.resolve_params(base, _swipe_settings_from_chat(chat))


async def import_session_swipes(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    message_id: str,
    session_obj: object,
) -> Message | None:
    """Import a generation session's candidates as a swipe deck (P-065).

    Bridges a GenerationSession (or voice turn) into the stored
    deck: the session's candidates replace the message's deck and
    its active index becomes the message's swipe_id. An empty
    candidate list raises ValueError. Returns None when the chat
    or message is missing/foreign.
    """
    swipes_list, idx = swipe_mod.swipes_from_session(session_obj)
    if not swipes_list:
        raise ValueError("session has no candidates")
    message = await _get_owned_message(session, user_id, chat_id, message_id)
    if message is None:
        return None
    _store_deck(message, list(swipes_list), idx)
    await _record_event(
        session,
        chat_id,
        EVENT_MESSAGE_SWIPE_ADDED,
        message_id=message.id,
        data={
            "swipe_count": len(swipes_list),
            "swipe_id": idx,
            "source": "generation_session",
        },
    )
    await session.commit()
    return message

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
