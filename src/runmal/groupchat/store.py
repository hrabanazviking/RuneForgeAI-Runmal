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

from runmal.characters.service import get_character
from runmal.db.models import Character, Chat, ChatEvent, Group, GroupMember, Message

USER_SPEAKER = "user"


def member_to_dict(character_id: str, name: str, position: int) -> dict:
    return {"character_id": character_id, "name": name, "position": position}


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
    members = [
        member_to_dict(m.character_id, name, m.position)
        for m, name in await _member_rows(session, group.id)
    ]
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


async def rename_group(
    session: AsyncSession, user_id: str, group_id: str, name: str
) -> dict | None:
    group = await _get_owned_group(session, user_id, group_id)
    if group is None:
        return None
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
    return member_to_dict(character_id, character.name, len(rows))


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


async def append_message(
    session: AsyncSession,
    user_id: str,
    group_id: str,
    speaker: str,
    content: str,
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

    message = Message(
        chat_id=chat.id,
        role=role,
        content=content,
        speaker_id=speaker_id,
        speaker_name=speaker_name,
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
