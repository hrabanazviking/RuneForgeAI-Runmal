"""Chat + message CRUD with stable IDs, mutation timestamps, and a durable
mutation event log (S107). Events feed future memory sync."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.cards import import_card
from runmal.characters.service import get_character as get_char
from runmal.chats import actions as action_mod
from runmal.chats import greetings as greeting_mod
from runmal.chats.greetings import GreetingChoice
from runmal.chats import provenance as prov_mod
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


async def _dispatch_plugin(name, *, chat_id=None, message_id=None, data=None):
    """Fire-and-observe plugin dispatch (P-081): lazy import (the
    delete_chat cleanup pattern; no import cycle), never raises --
    plugins.service.dispatch_event already never raises, and the
    import itself is guarded here too."""
    try:
        from runmal.plugins.service import dispatch_event

        await dispatch_event(name, chat_id=chat_id, message_id=message_id, data=data)
    except Exception:
        pass


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


def _metadata_provenance(chat: Chat) -> dict:
    from runmal.chats.metadata import provenance_from_chat

    return provenance_from_chat(chat)


async def _preset_snapshot(
    session: AsyncSession, user_id: str, chat: Chat
) -> dict:
    """The chat's applied preset AS OF NOW (P-075): a snapshot
    section for a provenance record being written at production
    time. No preset applied -> not_applicable; an applied id
    whose row has since vanished records the id alone."""
    preset_id = getattr(chat, "preset_id", None)
    if not preset_id:
        return prov_mod.preset_section(status="not_applicable")
    from runmal.presets import service as presets

    preset = await presets.get_preset(session, user_id, preset_id)
    if preset is None:
        return prov_mod.preset_section(preset_id=preset_id)
    data = presets.preset_to_dict(preset)
    return prov_mod.preset_section(
        preset_id=preset_id, name=data.get("name"),
        params=data.get("params"))


async def _profile_snapshot(
    session: AsyncSession, user_id: str, chat: Chat
) -> tuple[str | None, str | None]:
    """(backend_profile_id, backend_profile_name) pinned on the
    chat as of now, for a provenance record's model section."""
    profile_id = getattr(chat, "backend_profile_id", None)
    if not profile_id:
        return None, None
    from runmal.backends import profiles as backend_profiles

    profile = await backend_profiles.get_profile(session, user_id, profile_id)
    return profile_id, (profile.name if profile is not None else None)


async def _default_record(
    session: AsyncSession, user_id: str, chat: Chat, role: str,
    speaker_id: str | None, speaker_name: str | None,
) -> dict:
    """The record for a bare append (P-075): origin manual; the
    model section is a gap — unknown for an assistant line (the
    append road cannot know a model produced it), not_applicable
    for user/system lines — over a snapshot of the chat's
    current preset/profile configuration."""
    profile_id, profile_name = await _profile_snapshot(session, user_id, chat)
    return prov_mod.build_record(
        origin_kind="manual",
        model=prov_mod.model_section(
            status="unknown" if role == "assistant" else "not_applicable",
            backend_profile_id=profile_id,
            backend_profile_name=profile_name),
        preset=await _preset_snapshot(session, user_id, chat),
        lore=prov_mod.lore_section(status="not_applicable"),
        speaker={"speaker_id": speaker_id, "speaker_name": speaker_name},
    )


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
        "summary": getattr(chat, "summary", "") or "",
        "metadata": _metadata_provenance(chat),
    }


def message_to_dict(message: Message) -> dict:
    deck, swipe_id = _deck(message)
    variants = _variants(message)
    return {
        "id": message.id,
        "chat_id": message.chat_id,
        "role": message.role,
        "content": message.content,
        "swipes": deck,
        "swipe_id": swipe_id,
        "swipe_count": len(deck),
        "variant_history": variants,
        "variant_count": len(variants),
        "pinned": bool(getattr(message, "pinned", False)),
        "position": getattr(message, "position", None),
        "speaker_id": message.speaker_id,
        "speaker_name": message.speaker_name,
        "provenance": prov_mod.active_view(message, swipe_id),
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


async def _journal(
    session: AsyncSession, user_id: str, chat_id: str, operation: str, detail: dict | None = None
) -> None:
    """Journal the chat's before-image for undo (P-076).

    Lazy import (undo imports this module) and a fresh owned-chat
    read, so the snapshot is exactly the state the operation is
    about to change. Called AFTER validation and no-op checks,
    BEFORE any mutation, by every covered operation below.
    """
    from runmal.chats import undo as undo_mod

    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is not None:
        await undo_mod.record_journal(session, user_id, chat, operation, detail)


async def _get_owned_chat(session: AsyncSession, user_id: str, chat_id: str) -> Chat | None:
    result = await session.execute(select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id))
    return result.scalar_one_or_none()


def _greeting_record(character, entry: dict, preset: dict) -> dict:
    """The P-075 provenance record for one greeting alternate.

    The text is card-authored, placed by the append road: origin
    ``manual`` with the card-greeting facts recorded plainly (the
    entry's kind and its card-side index); no model produced it
    and no lore ran, so both sections say not_applicable.
    """
    return prov_mod.build_record(
        origin_kind="manual",
        origin={
            "source": "card_greeting",
            "greeting_kind": entry["kind"],
            "greeting_index": entry["source_index"],
        },
        model=prov_mod.model_section(status="not_applicable"),
        preset=preset,
        lore=prov_mod.lore_section(status="not_applicable"),
        speaker={"speaker_id": character.id, "speaker_name": character.name},
    )


async def _seed_greeting_message(
    session: AsyncSession,
    user_id: str,
    chat: Chat,
    character,
    choice: GreetingChoice,
) -> Message | None:
    """Seed a chat's greeting as its first message (P-079).

    The card's greeting deck becomes the message's swipe deck and
    the choice picks the active alternate, so the opening line is
    swiped exactly like any other message (P-065), with one
    provenance record per alternate (P-075). Returns None when
    the choice resolves to no greeting (quiet mode, or a card
    with no usable greeting). Event data carries metadata only,
    never greeting text. The caller owns the commit.
    """
    card = import_card(character.card_json.encode(), "card.json")
    entries = greeting_mod.greeting_entries(card.first_mes, card.alternate_greetings)
    deck = [entry["text"] for entry in entries]
    index = choice.resolve(deck)
    if index is None:
        return None
    preset = await _preset_snapshot(session, user_id, chat)
    document = prov_mod.build_document(
        _greeting_record(character, entries[index], preset), swipe_index=index
    )
    for other, entry in enumerate(entries):
        if other != index:
            document = prov_mod.with_record_for_swipe(
                document, other, _greeting_record(character, entry, preset)
            )
    message = Message(
        chat_id=chat.id,
        role="assistant",
        content=deck[index],
        speaker_id=character.id,
        speaker_name=character.name,
        swipes_json=json.dumps(deck),
        swipe_id=index,
        position=0,
        provenance_json=prov_mod.dump_document(document),
    )
    session.add(message)
    await session.flush()
    await _record_event(
        session,
        chat.id,
        EVENT_MESSAGE_APPENDED,
        message_id=message.id,
        data={
            "role": "assistant",
            "greeting": True,
            "greeting_mode": choice.mode,
            "greeting_kind": entries[index]["kind"],
            "greeting_index": entries[index]["source_index"],
            "swipe_id": index,
            "swipe_count": len(deck),
        },
    )
    return message


async def create_chat(
    session: AsyncSession,
    user_id: str,
    title: str = "",
    character_id: str | None = None,
    *,
    greeting: GreetingChoice | None = None,
) -> Chat:
    character = None
    if character_id is not None:
        character = await get_char(session, user_id, character_id)
        if character is None:
            raise KeyError(character_id)
    chat = Chat(user_id=user_id, title=title, character_id=character_id)
    session.add(chat)
    await session.flush()
    choice = greeting if greeting is not None else GreetingChoice()
    await _record_event(
        session,
        chat.id,
        EVENT_CHAT_CREATED,
        data={
            "title": title,
            "character_id": character_id,
            "greeting_mode": choice.mode,
        },
    )
    if character is not None:
        await _seed_greeting_message(session, user_id, chat, character, choice)
    await session.commit()
    await _dispatch_plugin(
        "chat.created",
        chat_id=chat.id,
        data={"chat_id": chat.id, "character_id": chat.character_id, "title": chat.title},
    )
    return chat


async def seed_greeting(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    choice: GreetingChoice | None = None,
) -> Message | None:
    """Seed the greeting into an existing EMPTY chat (P-079).

    For chats created quiet, or before their character was bound
    (set_chat_persona). Raises KeyError for a missing/foreign
    chat and ValueError when the chat is a group room, has no
    character, the
    character is gone, the deck choice is invalid for the card,
    or the chat already has messages -- a greeting is an opening
    line, never an insertion. Returns None when the choice
    resolves to no greeting (quiet mode / greetingless card).
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        raise KeyError(chat_id)
    if chat.group_id is not None:
        raise ValueError("group rooms have no single greeter; a greeting seeds only a one-to-one chat")
    if chat.character_id is None:
        raise ValueError("chat has no character to greet with")
    character = await get_char(session, user_id, chat.character_id)
    if character is None:
        raise ValueError("the chat's character no longer exists")
    if await _ordered_messages(session, chat_id):
        raise ValueError("chat already has messages; a greeting opens an empty chat")
    resolved = choice if choice is not None else GreetingChoice()
    card = import_card(character.card_json.encode(), "card.json")
    deck = greeting_mod.greeting_deck(card.first_mes, card.alternate_greetings)
    resolved.resolve(deck)  # strict: a bad explicit index fails BEFORE the journal
    await _journal(
        session, user_id, chat_id, "message.append", {"role": "assistant", "greeting": True}
    )
    message = await _seed_greeting_message(session, user_id, chat, character, resolved)
    await session.commit()
    return message


async def get_character_greetings(
    session: AsyncSession, user_id: str, character_id: str
) -> dict | None:
    """A card's greeting deck as the API presents it (P-079).

    Ordered usable greetings with their deck index, kind and
    card-side source index; None when the character is missing
    or foreign. The deck a new chat would seed from, exactly.
    """
    character = await get_char(session, user_id, character_id)
    if character is None:
        return None
    card = import_card(character.card_json.encode(), "card.json")
    entries = greeting_mod.greeting_entries(card.first_mes, card.alternate_greetings)
    return {
        "character_id": character.id,
        "character_name": character.name,
        "greetings": [
            {
                "index": index,
                "kind": entry["kind"],
                "source_index": entry["source_index"],
                "text": entry["text"],
            }
            for index, entry in enumerate(entries)
        ],
        "count": len(entries),
    }


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
    await _journal(session, user_id, chat_id, "chat.preset", {"preset_id": preset_id})
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
    await _journal(session, user_id, chat_id, "chat.authors_note")
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
    await _journal(session, user_id, chat_id, "chat.post_history")
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
    await _journal(session, user_id, chat_id, "chat.swipe_settings")
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
    await _journal(
        session, user_id, chat_id, "chat.persona", {"from": previous, "to": character_id}
    )
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
    await _journal(session, user_id, chat_id, "chat.backend_profile", {"profile_id": profile_id})
    chat.backend_profile_id = profile_id
    await session.commit()
    return chat


async def rename_chat(session: AsyncSession, user_id: str, chat_id: str, title: str) -> Chat | None:
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    await _journal(session, user_id, chat_id, "chat.rename")
    chat.title = title
    await _record_event(session, chat.id, EVENT_CHAT_RENAMED, data={"title": title})
    await session.commit()
    await _dispatch_plugin(
        "chat.renamed", chat_id=chat_id, data={"chat_id": chat_id, "title": title}
    )
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
    try:
        from runmal.chats.databank import remove_chat_databank

        remove_chat_databank(user_id, chat_id)
    except Exception:
        pass
    try:
        from runmal.chats.undo import remove_chat_undo

        remove_chat_undo(user_id, chat_id)
    except Exception:
        pass
    try:
        from runmal.prompt.vision_link import purge_chat

        purge_chat(chat_id)
    except Exception:
        pass
    try:
        # P-120 custody: the chat's image attachments (index
        # rows + byte files) die with the chat, like its vision
        # descriptions above.
        import os as _os
        from pathlib import Path as _Path

        from runmal.vision.attachments import AttachmentStore

        AttachmentStore(
            _Path(_os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
        ).purge_chat(chat_id)
    except Exception:
        pass
    try:
        # P-121 custody (wired at banking): the chat's folder-
        # watch registrations and their ingested records die
        # with the chat, like its attachments above.
        import os as _os_w
        from pathlib import Path as _Path_w

        from runmal.vision.watcher import WatchStore

        WatchStore(
            _Path_w(_os_w.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
        ).purge_chat(chat_id)
    except Exception:
        pass
    await _dispatch_plugin("chat.deleted", chat_id=chat_id, data={"chat_id": chat_id})
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
    provenance: dict | None = None,
) -> Message:
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        raise KeyError(chat_id)
    if role not in VALID_ROLES:
        raise ValueError(f"invalid role: {role!r}")
    if not content:
        raise ValueError("message content must not be empty")
    await _journal(session, user_id, chat_id, "message.append", {"role": role})
    agg = await session.execute(
        select(
            func.count(),
            func.count(Message.position),
            func.min(Message.position),
            func.max(Message.position),
            func.count(Message.position.distinct()),
        ).where(Message.chat_id == chat_id)
    )
    total_count, position_count, min_position, max_position, distinct_count = agg.one()
    new_position: int | None = None
    if (
        total_count > 0
        and position_count == total_count
        and distinct_count == total_count
        and min_position == 0
        and max_position == total_count - 1
    ):
        new_position = total_count
    elif position_count == 0:
        new_position = None
    else:
        existing = await _ordered_messages(session, chat_id)
        if any(m.position is not None for m in existing):
            _renumber(existing)
            new_position = len(existing)
    if provenance is None:
        provenance = await _default_record(
            session, user_id, chat, role, speaker_id, speaker_name)
    message = Message(
        chat_id=chat_id,
        role=role,
        content=content,
        speaker_id=speaker_id,
        speaker_name=speaker_name,
        swipes_json=json.dumps([content]),
        swipe_id=0,
        position=new_position,
        provenance_json=prov_mod.dump_document(
            prov_mod.build_document(provenance)),
    )
    session.add(message)
    await session.flush()
    data = {"role": role}
    if event_data:
        data.update(event_data)
    await _record_event(session, chat_id, EVENT_MESSAGE_APPENDED, message_id=message.id, data=data)
    await session.commit()
    await _dispatch_plugin(
        "message.created",
        chat_id=chat_id,
        message_id=message.id,
        data={
            "chat_id": chat_id,
            "message_id": message.id,
            "role": message.role,
            "content": message.content,
            "content_chars": len(message.content),
        },
    )
    return message


async def get_history(session: AsyncSession, user_id: str, chat_id: str) -> list[Message] | None:
    if await _get_owned_chat(session, user_id, chat_id) is None:
        return None
    return await _ordered_messages(session, chat_id)


async def get_history_page(session, user_id, chat_id, *, limit=100, offset=0, tail=False):
    """One page of a chat's history in display order + total count.
    Returns (messages, total, effective_offset, effective_limit) or None when the chat is not owned.
    Same ORDER BY as _ordered_messages; SQL LIMIT/OFFSET does the
    paging so a page never materialises the whole chat."""
    if await _get_owned_chat(session, user_id, chat_id) is None:
        return None
    limit = max(1, min(500, int(limit)))
    offset = max(0, int(offset))
    total_result = await session.execute(
        select(func.count()).select_from(Message).where(Message.chat_id == chat_id)
    )
    total = int(total_result.scalar_one())
    if tail:
        offset = max(0, total - limit)
    result = await session.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(
            Message.position.is_(None),
            Message.position,
            Message.created_at,
            Message.id,
        )
        .offset(offset)
        .limit(limit)
    )
    return list(result.scalars().all()), total, offset, limit


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
    await _journal(session, user_id, chat_id, "message.edit", {"message_id": message_id})
    deck, idx = _deck(message)
    history = action_mod.record_edit(
        _variants(message), message.content, _now().isoformat(), idx
    )
    message.variant_history_json = json.dumps(history)
    message.provenance_json = prov_mod.dump_document(
        prov_mod.with_amendment(
            getattr(message, "provenance_json", None), idx,
            {"kind": "edit", "variant_count": len(history)}))
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
    await _dispatch_plugin(
        "message.edited",
        chat_id=chat_id,
        message_id=message.id,
        data={
            "chat_id": chat_id,
            "message_id": message.id,
            "role": message.role,
            "content": message.content,
            "content_chars": len(message.content),
        },
    )
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
    await _journal(session, user_id, chat_id, "message.delete", {"message_id": message_id})
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
    try:
        # P-120 custody: a deleted message's image attachments
        # (index rows + byte files) are purged with it.
        # P-122 source custody: descriptions derived from those
        # attachments are purged with them, so derived text
        # never outlives the deleted bytes.
        # P-124 watcher custody: watcher ingested records
        # naming those attachments are forgotten with them,
        # so the scan dedupe memory never tombstones a file
        # whose attachment died with this message.
        import os as _os
        from pathlib import Path as _Path

        from runmal.vision.attachments import AttachmentStore

        _att_store = AttachmentStore(
            _Path(_os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
        )
        _att_ids = [
            row.id for row in _att_store.list_for_message(message_id)
        ]
        _att_store.purge_message(message_id)
        if _att_ids:
            from runmal.vision.service import (
                SOURCE_ATTACHMENT,
                VisionStore,
                descriptions_path,
            )

            _vis_store = VisionStore(descriptions_path(_att_store.data_dir))
            for _att_id in _att_ids:
                _vis_store.purge_source(SOURCE_ATTACHMENT, _att_id)
            from runmal.vision.watcher import WatchStore as _WatchStore

            _watch_store = _WatchStore(_att_store.data_dir)
            for _att_id in _att_ids:
                _watch_store.forget_attachment(_att_id)
    except Exception:
        pass
    await _dispatch_plugin(
        "message.deleted",
        chat_id=chat_id,
        message_id=message_id,
        data={"chat_id": chat_id, "message_id": message_id},
    )
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
    await _journal(
        session, user_id, chat_id, "message.move",
        {"message_id": message_id, "from_index": from_index, "to_index": target},
    )
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
            provenance_json=prov_mod.dump_document(
                prov_mod.document_for_copy(
                    m, source_chat_id=chat_id, source_message_id=m.id,
                    source_content_sha256=hashlib.sha256(
                        m.content.encode("utf-8")).hexdigest())),
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
            await _journal(session, user_id, chat_id, "message.pin", {"message_id": message_id})
            message.pinned = True
            await session.commit()
        return existing
    await _journal(session, user_id, chat_id, "message.pin", {"message_id": message_id})
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
    await _journal(session, user_id, chat_id, "message.unpin", {"message_id": message_id})
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
    await _journal(session, user_id, chat_id, "message.swipe_add", {"message_id": message_id})
    deck, _idx = _deck(message)
    new_deck = list(deck)
    new_deck.append(content)
    new_id = len(new_deck) - 1
    _store_deck(message, new_deck, new_id)
    chat = await _get_owned_chat(session, user_id, chat_id)
    swipe_record = prov_mod.build_record(
        origin_kind="swipe_manual",
        model=prov_mod.model_section(status="not_applicable"),
        preset=(await _preset_snapshot(session, user_id, chat)
                if chat is not None else prov_mod.preset_section()),
        lore=prov_mod.lore_section(status="not_applicable"),
        speaker={"speaker_id": message.speaker_id,
                 "speaker_name": message.speaker_name})
    message.provenance_json = prov_mod.dump_document(
        prov_mod.with_record_for_swipe(
            prov_mod.parse_provenance(message), new_id, swipe_record))
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
    await _journal(session, user_id, chat_id, "message.swipe_select", {"message_id": message_id})
    _store_deck(message, list(deck), new_id)
    await _record_event(
        session,
        chat_id,
        EVENT_MESSAGE_SWIPE_SELECTED,
        message_id=message.id,
        data={"swipe_id": new_id, "swipe_count": len(deck)},
    )
    await session.commit()
    await _dispatch_plugin(
        "message.swipe_selected",
        chat_id=chat_id,
        message_id=message.id,
        data={"chat_id": chat_id, "message_id": message.id, "swipe_id": new_id},
    )
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
    await _journal(session, user_id, chat_id, "message.swipe_delete", {"message_id": message_id})
    new_deck = list(deck)
    del new_deck[index]
    message.provenance_json = prov_mod.dump_document(
        prov_mod.without_swipe(
            getattr(message, "provenance_json", None), index))
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
    await _journal(session, user_id, chat_id, "message.swipe_import", {"message_id": message_id})
    _store_deck(message, list(swipes_list), idx)
    mode_value = getattr(session_obj, "mode", None)
    generation = {
        "fingerprint": getattr(session_obj, "fingerprint", None),
        "mode": getattr(mode_value, "value", mode_value),
    }
    document = None
    for position in range(len(swipes_list)):
        session_record = prov_mod.build_record(
            origin_kind="generation_session",
            generation=generation,
            speaker={"speaker_id": message.speaker_id,
                     "speaker_name": message.speaker_name})
        if document is None:
            document = prov_mod.build_document(
                session_record, swipe_index=position)
        else:
            document = prov_mod.with_record_for_swipe(
                document, position, session_record)
    if document is not None:
        message.provenance_json = prov_mod.dump_document(document)
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

# -- Message provenance reads (P-075) --------------------------------------


async def get_message_provenance(
    session: AsyncSession, user_id: str, chat_id: str, message_id: str
) -> dict | None:
    """One message's FULL provenance document (every recorded
    swipe), for the Inspector. None when missing/foreign."""
    message = await _get_owned_message(session, user_id, chat_id, message_id)
    if message is None:
        return None
    view = prov_mod.full_view(message)
    view["message_id"] = message.id
    view["chat_id"] = chat_id
    view["active_swipe_id"] = _deck(message)[1]
    return view


async def list_chat_provenance(
    session: AsyncSession, user_id: str, chat_id: str
) -> dict | None:
    """A chat's per-message ACTIVE provenance records plus the
    aggregate summary (P-075). None when the chat is missing
    or foreign."""
    if await _get_owned_chat(session, user_id, chat_id) is None:
        return None
    history = await _ordered_messages(session, chat_id)
    messages = []
    views = []
    for message in history:
        view = prov_mod.active_view(message, _deck(message)[1])
        views.append(view)
        messages.append({
            "message_id": message.id, "role": message.role,
            "provenance": view,
        })
    return {
        "chat_id": chat_id,
        "messages": messages,
        "summary": prov_mod.summarise_provenance(views),
    }
