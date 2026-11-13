"""Persistent group rooms (roadmap S210): room / members / transcript.

A Group is the room: it references member characters in roster order and
owns one transcript Chat (``chats.group_id``). Messages posted to the room
carry explicit per-message speaker identity -- the speaking character's id
plus a snapshot of its display name -- so later membership changes or
renames never rewrite who historically said what (DATA_MODEL.md).

The in-memory turn orchestration lives in ``runmal.groupchat.core``; this
module is the durable data layer beneath it. All operations are
ownership-scoped: a group resolves only through its owner.
"""

from __future__ import annotations

import json

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.chats import provenance as prov_mod
from runmal.chats import reasoning as reasoning_mod
from runmal.characters.service import get_character
from runmal.db.models import Character, Chat, ChatEvent, Group, GroupMember, Message
from runmal.groupchat.policies import get_policy

USER_SPEAKER = "user"


def member_to_dict(member: GroupMember, name: str) -> dict:
    return {
        "character_id": member.character_id,
        "name": name,
        "position": member.position,
        "talkativeness": member.talkativeness,
        "muted": bool(member.muted),
    }


def group_to_dict(
    group: Group,
    members: list[dict],
    chat_id: str | None,
    message_count: int = 0,
) -> dict:
    return {
        "id": group.id,
        "name": group.name,
        "chat_id": chat_id,
        "members": members,
        "member_count": len(members),
        "message_count": message_count,
        "speaker_policy": group.speaker_policy,
        "speaker_config": json.loads(group.speaker_config or "{}"),
        "created_at": group.created_at.isoformat(),
    }


def message_to_dict(message: Message) -> dict:
    return {
        "id": message.id,
        "chat_id": message.chat_id,
        "role": message.role,
        "content": message.content,
        "speaker_id": message.speaker_id,
        "speaker_name": message.speaker_name,
        "provenance": prov_mod.active_view(
            message, getattr(message, "swipe_id", 0) or 0),
        "reasoning": reasoning_mod.active_view(
            message, getattr(message, "swipe_id", 0) or 0),
        "created_at": message.created_at.isoformat(),
        "updated_at": message.updated_at.isoformat() if message.updated_at else None,
    }


async def _get_owned_group(session: AsyncSession, user_id: str, group_id: str) -> Group | None:
    result = await session.execute(
        select(Group).where(Group.id == group_id, Group.user_id == user_id)
    )
    return result.scalar_one_or_none()


async def _room_chat(session: AsyncSession, group_id: str) -> Chat | None:
    result = await session.execute(select(Chat).where(Chat.group_id == group_id))
    return result.scalar_one_or_none()


async def _member_rows(session: AsyncSession, group_id: str) -> list[tuple[GroupMember, str]]:
    """(membership, character name) pairs in roster order."""
    result = await session.execute(
        select(GroupMember, Character.name)
        .join(Character, Character.id == GroupMember.character_id)
        .where(GroupMember.group_id == group_id)
        .order_by(GroupMember.position)
    )
    return [(row[0], row[1]) for row in result.all()]


async def _describe(session: AsyncSession, group: Group, with_count: bool = False) -> dict:
    members = [member_to_dict(m, name) for m, name in await _member_rows(session, group.id)]
    chat = await _room_chat(session, group.id)
    count = 0
    if with_count and chat is not None:
        result = await session.execute(
            select(func.count(Message.id)).where(Message.chat_id == chat.id)
        )
        count = int(result.scalar_one())
    return group_to_dict(group, members, chat.id if chat else None, count)


async def create_group(
    session: AsyncSession,
    user_id: str,
    name: str,
    member_character_ids: list[str],
) -> Group:
    seen: set[str] = set()
    ordered_ids: list[str] = []
    for cid in member_character_ids:
        if cid not in seen:
            seen.add(cid)
            ordered_ids.append(cid)
    characters = []
    for cid in ordered_ids:
        character = await get_character(session, user_id, cid)
        if character is None:
            raise ValueError(f"unknown member character: {cid}")
        characters.append(character)

    group = Group(user_id=user_id, name=name)
    session.add(group)
    await session.flush()
    chat = Chat(user_id=user_id, character_id=None, group_id=group.id, title=name)
    session.add(chat)
    for position, character in enumerate(characters):
        session.add(GroupMember(group_id=group.id, character_id=character.id, position=position))
    await session.commit()
    await session.refresh(group)
    return group


async def describe_group(session: AsyncSession, user_id: str, group_id: str) -> dict | None:
    group = await _get_owned_group(session, user_id, group_id)
    if group is None:
        return None
    return await _describe(session, group, with_count=True)


async def list_groups(session: AsyncSession, user_id: str) -> list[dict]:
    result = await session.execute(
        select(Group).where(Group.user_id == user_id).order_by(Group.created_at)
    )
    return [await _describe(session, g, with_count=True) for g in result.scalars()]


async def update_group(
    session: AsyncSession,
    user_id: str,
    group_id: str,
    name: str | None = None,
    speaker_policy: str | None = None,
    speaker_config: dict | None = None,
) -> dict | None:
    """Update room name and/or speaker-policy configuration (S211).
    ValueError -> unknown speaker policy name."""
    group = await _get_owned_group(session, user_id, group_id)
    if group is None:
        return None
    if speaker_policy is not None:
        get_policy(speaker_policy)  # raises ValueError for unknown names
        group.speaker_policy = speaker_policy
    if speaker_config is not None:
        group.speaker_config = json.dumps(speaker_config)
    if name is not None:
        group.name = name
        chat = await _room_chat(session, group.id)
        if chat is not None:
            chat.title = name
    await session.commit()
    return await _describe(session, group, with_count=True)


async def delete_group(session: AsyncSession, user_id: str, group_id: str) -> bool:
    group = await _get_owned_group(session, user_id, group_id)
    if group is None:
        return False
    await session.execute(delete(Group).where(Group.id == group.id))
    await session.commit()
    return True


async def add_member(
    session: AsyncSession, user_id: str, group_id: str, character_id: str
) -> dict | None:
    """Append a character to the roster. None -> group not found;
    ValueError -> unknown character or already a member."""
    group = await _get_owned_group(session, user_id, group_id)
    if group is None:
        return None
    character = await get_character(session, user_id, character_id)
    if character is None:
        raise ValueError(f"unknown member character: {character_id}")
    rows = await _member_rows(session, group.id)
    if any(m.character_id == character_id for m, _ in rows):
        raise ValueError(f"already a member: {character_id}")
    member = GroupMember(group_id=group.id, character_id=character_id, position=len(rows))
    session.add(member)
    await session.commit()
    await session.refresh(member)
    return member_to_dict(member, character.name)


async def remove_member(
    session: AsyncSession, user_id: str, group_id: str, character_id: str
) -> bool:
    """Remove a roster member. Historical messages keep their speaker
    snapshot; only future speech is affected."""
    group = await _get_owned_group(session, user_id, group_id)
    if group is None:
        return False
    result = await session.execute(
        delete(GroupMember).where(
            GroupMember.group_id == group.id,
            GroupMember.character_id == character_id,
        )
    )
    await session.commit()
    return (result.rowcount or 0) > 0


async def update_member_settings(
    session: AsyncSession,
    user_id: str,
    group_id: str,
    character_id: str,
    talkativeness: float | None = None,
    muted: bool | None = None,
) -> dict | None:
    """Update a member's speaker-policy knobs (S211). None -> group or
    member not found; ValueError -> talkativeness outside [0.0, 1.0]."""
    if talkativeness is not None and not 0.0 <= talkativeness <= 1.0:
        raise ValueError("talkativeness must be in [0.0, 1.0]")
    group = await _get_owned_group(session, user_id, group_id)
    if group is None:
        return None
    result = await session.execute(
        select(GroupMember, Character.name)
        .join(Character, Character.id == GroupMember.character_id)
        .where(
            GroupMember.group_id == group.id,
            GroupMember.character_id == character_id,
        )
    )
    row = result.first()
    if row is None:
        return None
    member, name = row[0], row[1]
    if talkativeness is not None:
        member.talkativeness = talkativeness
    if muted is not None:
        member.muted = muted
    await session.commit()
    await session.refresh(member)
    return member_to_dict(member, name)


async def append_message(
    session: AsyncSession,
    user_id: str,
    group_id: str,
    speaker: str,
    content: str,
    *,
    provenance: dict | None = None,
    reasoning: dict | None = None,
) -> Message | None:
    """Append a transcript message with explicit speaker identity.

    ``speaker`` is ``"user"`` or a member character's id. None -> group not
    found; ValueError -> a character speaker who is not a current member.
    """
    group = await _get_owned_group(session, user_id, group_id)
    if group is None:
        return None
    chat = await _room_chat(session, group.id)
    if chat is None:  # pragma: no cover - group always creates its room chat
        raise ValueError("group has no room chat")

    if speaker == USER_SPEAKER:
        role, speaker_id, speaker_name = "user", None, None
    else:
        rows = await _member_rows(session, group.id)
        names = {m.character_id: name for m, name in rows}
        if speaker not in names:
            raise ValueError(f"speaker is not a group member: {speaker}")
        role, speaker_id, speaker_name = "assistant", speaker, names[speaker]

    if provenance is None:
        provenance = prov_mod.build_record(
            origin_kind="manual" if speaker == USER_SPEAKER
            else "group_declared",
            model=prov_mod.model_section(status="not_applicable"),
            preset=prov_mod.preset_section(status="not_applicable"),
            lore=prov_mod.lore_section(status="not_applicable"),
            speaker={"speaker_id": speaker_id,
                     "speaker_name": speaker_name})
    message = Message(
        chat_id=chat.id,
        role=role,
        content=content,
        speaker_id=speaker_id,
        speaker_name=speaker_name,
        provenance_json=prov_mod.dump_document(
            prov_mod.build_document(provenance)),
        reasoning_json=reasoning_mod.dump_document(
            reasoning_mod.build_document(
                reasoning if reasoning is not None
                else reasoning_mod.not_recorded_record())),
    )
    session.add(message)
    await session.flush()
    session.add(
        ChatEvent(
            chat_id=chat.id,
            message_id=message.id,
            kind="message.appended",
            data=json.dumps({"speaker_id": speaker_id, "group_id": group.id}),
        )
    )
    await session.commit()
    await session.refresh(message)
    return message


async def list_messages(session: AsyncSession, user_id: str, group_id: str) -> list[Message] | None:
    group = await _get_owned_group(session, user_id, group_id)
    if group is None:
        return None
    chat = await _room_chat(session, group.id)
    if chat is None:
        return []
    result = await session.execute(
        select(Message).where(Message.chat_id == chat.id).order_by(Message.created_at)
    )
    return list(result.scalars())


async def list_group_reasoning(
    session: AsyncSession, user_id: str, group_id: str
) -> dict | None:
    """A group's per-message reasoning views: every
    transcript message's ACTIVE view and FULL document
    (P-211), for the Inspector group reasoning census,
    plus the speaker identity the transcript itself
    carries. None when the group is missing or foreign.
    Pure read over the banked P-205 tolerant readers;
    persists nothing.

    The owned fence IS list_messages itself: it is
    called, its None (missing or foreign group)
    propagates as None, and no second fence is written,
    so existence never leaks. The room chat is resolved
    through the banked _room_chat, exactly as
    list_messages resolves it. Each message's active
    view is resolved exactly as message_to_dict resolves
    it (the message's active swipe)."""
    messages = await list_messages(session, user_id, group_id)
    if messages is None:
        return None
    chat = await _room_chat(session, group_id)
    entries = []
    for message in messages:
        entries.append({
            "message_id": message.id,
            "role": message.role,
            "speaker_id": message.speaker_id,
            "speaker_name": message.speaker_name,
            "active": reasoning_mod.active_view(
                message, getattr(message, "swipe_id", 0) or 0),
            "full": reasoning_mod.full_view(message),
        })
    return {
        "group_id": group_id,
        "room_chat_id": chat.id if chat is not None else None,
        "messages": entries,
    }
