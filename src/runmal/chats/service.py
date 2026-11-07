"""Chat + message CRUD with stable IDs, mutation timestamps, and a durable
mutation event log (S107). Events feed future memory sync."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.characters.service import get_character as get_char
from runmal.chats import actions as action_mod
from runmal.chats import swipes as swipe_mod
from runmal.chats.swipes import (
    SwipeRegenSettings,
    settings_from_data,
    settings_to_data,
)
from runmal.db.models import Chat, ChatEvent, Memory, MemorySource, Message
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
EVENT_MESSAGE_MOVED = "message.moved"
EVENT_MESSAGE_COPIED_TO_BRANCH = "message.copied_to_branch"
EVENT_MESSAGE_PINNED = "message.pinned_to_memory"
EVENT_MESSAGE_UNPINNED = "message.unpinned_from_memory"


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


def _variants(message: Message) -> list[dict]:
    return action_mod.parse_history(getattr(message, "variant_history_json", None))


async def _ordered_messages(session: AsyncSession, chat_id: str) -> list[Message]:
    """A chat's messages in display order (P-068).

    Materialised rows (position set) come first by position;
    legacy rows (position NULL) follow by created_at -- in
    practice a chat is either fully legacy or fully materialised,
    because the first move/delete/append-after-materialisation
    renumbers the whole chat. created_at + id break ties so the
    order is always deterministic.
    """
    result = await session.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(
            Message.position.is_(None),
            Message.position,
            Message.created_at,
            Message.id,
        )
    )
    return list(result.scalars().all())


def _renumber(messages: list[Message]) -> None:
    for index, message in enumerate(messages):
        message.position = index


async def _pin_memory_for(
    session: AsyncSession, user_id: str, message_id: str
) -> Memory | None:
    """The pin Memory row for a message, via its MemorySource link."""
    result = await session.execute(
        select(Memory)
        .join(MemorySource, MemorySource.memory_id == Memory.id)
        .where(
            Memory.user_id == user_id,
            MemorySource.source_kind == "message",
            MemorySource.source_id == message_id,
        )
    )
    return result.scalar_one_or_none()


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
        "variant_history": _variants(message),
        "variant_count": len(_variants(message)),
        "pinned": bool(getattr(message, "pinned", False)),
        "position": getattr(message, "position", None),
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
    try:
        from runmal.chats.checkpoints import remove_chat_checkpoints

        remove_chat_checkpoints(user_id, chat_id)
    except Exception:
        pass
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
    existing = await _ordered_messages(session, chat_id)
    new_position: int | None = None
    if any(m.position is not None for m in existing):
        _renumber(existing)
        new_position = len(existing)
    message = Message(
        chat_id=chat_id,
        role=role,
        content=content,
        speaker_id=speaker_id,
        speaker_name=speaker_name,
        swipes_json=json.dumps([content]),
        swipe_id=0,
        position=new_position,
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
    return await _ordered_messages(session, chat_id)


async def edit_message(
    session: AsyncSession, user_id: str, chat_id: str, message_id: str, content: str
) -> Message | None:
    """Edit a message's ACTIVE alternate, keeping variant history (P-068).

    The replaced content is appended to the message's variant
    history BEFORE the deck is updated -- prior contents are
    retained and inspectable (get_message_variants), never silently
    overwritten. The deck invariant ``content == swipes[swipe_id]``
    is preserved: only the active alternate changes. Editing to
    the identical content is a no-op (no history entry, no event).
    When the message is pinned, its pin Memory content refreshes
    to the new active content so memory never silently diverges.
    The mutation event records only the variant count -- never text.
    """
    message = await _get_owned_message(session, user_id, chat_id, message_id)
    if message is None:
        return None
    if not content:
        raise ValueError("message content must not be empty")
    if content == message.content:
        return message
    deck, idx = _deck(message)
    history = action_mod.record_edit(
        _variants(message), message.content, _now().isoformat(), idx
    )
    message.variant_history_json = json.dumps(history)
    new_deck = list(deck)
    new_deck[idx] = content
    _store_deck(message, new_deck, idx)
    message.updated_at = _now()
    await _record_event(
        session, chat_id, EVENT_MESSAGE_EDITED,
        message_id=message.id, data={"variant_count": len(history)},
    )
    if getattr(message, "pinned", False):
        memory = await _pin_memory_for(session, user_id, message.id)
        if memory is not None and memory.content != content:
            memory.content = content
            from runmal.memory import service as memory_svc

            await memory_svc.index_fts(session, memory)
    await session.commit()
    return message


async def get_message_variants(
    session: AsyncSession, user_id: str, chat_id: str, message_id: str
) -> list[dict] | None:
    """A message's variant history (replaced contents, edit order).

    Returns None when the chat or message is missing/foreign.
    """
    message = await _get_owned_message(session, user_id, chat_id, message_id)
    if message is None:
        return None
    return _variants(message)


async def delete_message(
    session: AsyncSession, user_id: str, chat_id: str, message_id: str
) -> bool:
    """Delete a message (P-068 completes the pre-existing delete).

    A pinned message's pin Memory (and its source link) is removed
    first -- no orphaned memory may point at a dead message. When
    the chat's order is materialised, the survivors are renumbered
    so positions stay unique and contiguous.
    """
    message = await _get_owned_message(session, user_id, chat_id, message_id)
    if message is None:
        return False
    was_materialised = message.position is not None
    if getattr(message, "pinned", False):
        memory = await _pin_memory_for(session, user_id, message_id)
        if memory is not None:
            from runmal.memory import service as memory_svc

            await memory_svc.delete_memory(session, user_id, memory.id)
    await _record_event(session, chat_id, EVENT_MESSAGE_DELETED, message_id=message_id)
    await session.execute(delete(Message).where(Message.id == message_id))
    await session.flush()
    if was_materialised:
        _renumber(await _ordered_messages(session, chat_id))
    await session.commit()
    return True


async def move_message(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    message_id: str,
    to_index: int,
) -> Message | None:
    """Move a message to a strict target index within its chat (P-068).

    The target is validated strictly (no clamp, no wrap -- a bad
    target raises ValueError and changes nothing). The first move
    in a legacy chat materialises positions for the whole chat in
    current (created_at) order, then applies the move; positions
    are always unique and contiguous afterwards. Moving to the
    current index is a no-op (no event, no materialisation).
    Returns None when the chat or message is missing/foreign. The
    event records only indexes -- never text.
    """
    message = await _get_owned_message(session, user_id, chat_id, message_id)
    if message is None:
        return None
    ordered = await _ordered_messages(session, chat_id)
    target = action_mod.validate_move_target(len(ordered), to_index)
    from_index = [m.id for m in ordered].index(message_id)
    if from_index == target:
        return message
    _renumber(action_mod.move_index(ordered, from_index, target))
    message.updated_at = _now()
    await _record_event(
        session, chat_id, EVENT_MESSAGE_MOVED,
        message_id=message.id,
        data={"from_index": from_index, "to_index": target},
    )
    await session.commit()
    return message


async def copy_message_to_branch(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    message_id: str,
    *,
    target_chat_id: str | None = None,
    title: str | None = None,
) -> dict | None:
    """Copy a message to a branch (P-068).

    BANKING RE-TARGET (P-068 banking): this slice's base predated
    P-066's branch columns; at banking the fork mode was re-targeted
    onto them -- the forked chat now carries the P-066 lineage
    (branch_parent_id, branch_fork_message_id, branch_fork_index,
    branch_kind='fork') and the source's settings, mirroring
    branches.fork_chat, so branch-family listing sees it. With no
    ``target_chat_id``, a new chat
    is forked carrying every message up to and including the
    source message (the fork-at-message shape), titled ``title``
    or ``"<source title> (branch)"``. With ``target_chat_id``, a
    copy of just the source message is appended to that chat.
    Either way: both chats must belong to the user (a foreign or
    missing target raises KeyError; a missing/foreign source
    returns None); decks, variant history, speakers and roles are
    deep-copied (later edits never bleed across chats); copies
    are NEVER pinned and carry no pin Memory. Returns a dict with
    ``target_chat``, ``copied_message``, ``copied_count``, ``mode``.
    """
    source_chat = await _get_owned_chat(session, user_id, chat_id)
    if source_chat is None:
        return None
    source = await _get_owned_message(session, user_id, chat_id, message_id)
    if source is None:
        return None
    ordered = await _ordered_messages(session, chat_id)

    def _copy_of(m: Message, dest_chat_id: str, position: int | None) -> Message:
        return Message(
            chat_id=dest_chat_id,
            role=m.role,
            content=m.content,
            swipes_json=m.swipes_json,
            swipe_id=m.swipe_id,
            speaker_id=m.speaker_id,
            speaker_name=m.speaker_name,
            created_at=m.created_at,
            variant_history_json=getattr(m, "variant_history_json", "[]"),
            pinned=False,
            position=position,
        )

    if target_chat_id is None:
        branch_title = title if title is not None else (
            f"{source_chat.title} (branch)" if source_chat.title else "Branch"
        )
        branch = Chat(
            user_id=user_id, title=branch_title,
            character_id=source_chat.character_id,
            preset_id=getattr(source_chat, "preset_id", None),
            backend_profile_id=getattr(source_chat, "backend_profile_id", None),
            authors_note_json=getattr(source_chat, "authors_note_json", "{}"),
            post_history_json=getattr(source_chat, "post_history_json", "{}"),
        )
        session.add(branch)
        await session.flush()
        upto = ordered[: [m.id for m in ordered].index(message_id) + 1]
        copies = [_copy_of(m, branch.id, i) for i, m in enumerate(upto)]
        branch.branch_parent_id = chat_id
        branch.branch_fork_message_id = message_id
        branch.branch_fork_index = len(copies)
        branch.branch_kind = "fork"
        branch.branch_merge_of_json = "[]"
        session.add_all(copies)
        await session.flush()
        await _record_event(
            session, branch.id, EVENT_CHAT_CREATED,
            data={"title": branch_title,
                  "character_id": branch.character_id,
                  "branched_from_chat_id": chat_id,
                  "branched_from_message_id": message_id},
        )
        await _record_event(
            session, chat_id, EVENT_MESSAGE_COPIED_TO_BRANCH,
            message_id=message_id,
            data={"target_chat_id": branch.id,
                  "copied_count": len(copies), "mode": "fork"},
        )
        await session.commit()
        return {"target_chat": branch, "copied_message": copies[-1],
                "copied_count": len(copies), "mode": "fork"}
    target = await _get_owned_chat(session, user_id, target_chat_id)
    if target is None:
        raise KeyError(target_chat_id)
    target_ordered = await _ordered_messages(session, target_chat_id)
    position: int | None = None
    if any(m.position is not None for m in target_ordered):
        _renumber(target_ordered)
        position = len(target_ordered)
    copied = _copy_of(source, target_chat_id, position)
    copied.created_at = _now()
    session.add(copied)
    await session.flush()
    await _record_event(
        session, chat_id, EVENT_MESSAGE_COPIED_TO_BRANCH,
        message_id=message_id,
        data={"target_chat_id": target_chat_id,
              "copied_count": 1, "mode": "copy"},
    )
    await session.commit()
    return {"target_chat": target, "copied_message": copied,
            "copied_count": 1, "mode": "copy"}


async def pin_message_to_memory(
    session: AsyncSession, user_id: str, chat_id: str, message_id: str
) -> Memory | None:
    """Pin a message to memory (P-068).

    Creates a REAL Memory row through the memory service --
    pinned, state ``pinned``, kind ``episodic``, scope ``chat`` --
    with a MemorySource link back to the message, so the pinned
    content surfaces through the tree's existing memory retrieval
    (whose default states already include ``pinned``). The
    message's ``pinned`` flag is set in step. Idempotent: pinning
    an already-pinned message returns the existing Memory and
    creates nothing. Returns None when missing/foreign.
    """
    message = await _get_owned_message(session, user_id, chat_id, message_id)
    if message is None:
        return None
    existing = await _pin_memory_for(session, user_id, message_id)
    if existing is not None:
        if not getattr(message, "pinned", False):
            message.pinned = True
            await session.commit()
        return existing
    from runmal.memory import service as memory_svc

    memory = await memory_svc.create_memory(
        session,
        user_id,
        content=message.content,
        kind="episodic",
        state="pinned",
        pinned=True,
        salience=1.0,
        stability=1.0,
        scope="chat",
        chat_id=chat_id,
        character_id=None,
        extractor={"source": "p068_pin", "message_id": message_id,
                   "chat_id": chat_id},
        sources=(("message", message_id, chat_id),),
    )
    message.pinned = True
    await _record_event(
        session, chat_id, EVENT_MESSAGE_PINNED,
        message_id=message_id, data={"memory_id": memory.id},
    )
    await session.commit()
    return memory


async def unpin_message_from_memory(
    session: AsyncSession, user_id: str, chat_id: str, message_id: str
) -> bool | None:
    """Unpin a message (P-068): delete its pin Memory, clear the flag.

    Returns True when a pin was removed, False when the message
    exists but was not pinned, and None when the chat or message
    is missing/foreign.
    """
    message = await _get_owned_message(session, user_id, chat_id, message_id)
    if message is None:
        return None
    memory = await _pin_memory_for(session, user_id, message_id)
    if memory is None and not getattr(message, "pinned", False):
        return False
    if memory is not None:
        from runmal.memory import service as memory_svc

        await memory_svc.delete_memory(session, user_id, memory.id)
    message.pinned = False
    await _record_event(
        session, chat_id, EVENT_MESSAGE_UNPINNED, message_id=message_id,
    )
    await session.commit()
    return True


async def list_pinned_messages(
    session: AsyncSession, user_id: str, chat_id: str
) -> list[Message] | None:
    """A chat's pinned messages, in display order (P-068).

    Truth is the MemorySource link, so this stays correct even if
    a pin Memory was removed outside the pin/unpin functions.
    Returns None when the chat is missing/foreign.
    """
    if await _get_owned_chat(session, user_id, chat_id) is None:
        return None
    ordered = await _ordered_messages(session, chat_id)
    pinned_ids = set(
        await session.scalars(
            select(MemorySource.source_id)
            .join(Memory, Memory.id == MemorySource.memory_id)
            .where(
                Memory.user_id == user_id,
                MemorySource.source_kind == "message",
                MemorySource.chat_id == chat_id,
            )
        )
    )
    return [m for m in ordered if m.id in pinned_ids]


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
