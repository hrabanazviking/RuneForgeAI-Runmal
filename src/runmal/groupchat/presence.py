"""Absent-character presence + history digest (P-071).

Presence is derived from metadata-only chat_events
(``presence.left`` / ``presence.returned``) recorded on the group's
room chat: the latest such event per character decides whether that
character is present or absent. No new tables are involved.

The digest is extractive and deterministic: it is built on demand
from the real stored transcript, lists who spoke and excerpted what
they said in canonical transcript order, and is never stored. It is
not a summary and never calls a backend.

No migration is taken by this slice; the migration head stays 0038.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import ChatEvent, Message
from runmal.groupchat import store

DIGEST_VERSION = "extractive-1"
KIND_LEFT = "presence.left"
KIND_RETURNED = "presence.returned"
DEFAULT_MAX_ENTRIES = 50
DEFAULT_EXCERPT_CHARS = 200
MAX_ENTRIES_LIMIT = 500
EXCERPT_CHARS_MIN = 20
EXCERPT_CHARS_MAX = 5000
USER_LABEL = "user"
UNKNOWN_LABEL = "unknown speaker"


def excerpt_text(content: str, limit: int) -> tuple[str, bool]:
    """Return ``(content[:limit], truncated)``. No ellipsis is added."""
    return (content[:limit], len(content) > limit)


def _speaker_label(message) -> tuple[str | None, str]:
    """Resolve a message to ``(speaker_id, label)``; label is never None."""
    if message.speaker_id is not None:
        return (message.speaker_id, message.speaker_name or UNKNOWN_LABEL)
    if message.role == "user":
        return (None, USER_LABEL)
    return (None, UNKNOWN_LABEL)


def _canonical_order(messages):
    """Sorted copy in canonical transcript order.

    Mirrors ``chats/service._ordered_messages``: position-materialised
    rows first (by position), then ``created_at``, then ``id``.
    """
    return sorted(
        messages,
        key=lambda m: (
            m.position is None,
            m.position if m.position is not None else 0,
            m.created_at,
            m.id,
        ),
    )


def build_digest(
    messages,
    *,
    group_id,
    group_name,
    chat_id,
    character_id,
    character_name,
    absent_since,
    anchor_message_id,
    anchor_message_count,
    resolution,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    excerpt_chars: int = DEFAULT_EXCERPT_CHARS,
    delivered: bool = False,
) -> dict:
    """Build the extractive digest over an absence window.

    Pure function. ``messages`` are the absence-window messages in
    canonical order, INCLUDING any spoken by the returning character;
    the returning character's own messages are counted separately and
    never appear in entries or by_speaker.
    """
    missed = [m for m in messages if m.speaker_id != character_id]
    own_count = len(messages) - len(missed)

    entries = []
    for message in missed[:max_entries]:
        speaker_id, label = _speaker_label(message)
        excerpt, truncated = excerpt_text(message.content, excerpt_chars)
        entries.append(
            {
                "message_id": message.id,
                "speaker_id": speaker_id,
                "speaker_name": label,
                "role": message.role,
                "excerpt": excerpt,
                "truncated": truncated,
                "created_at": message.created_at.isoformat(),
            }
        )
    omitted_count = len(missed) - len(entries)

    by_speaker: list[dict] = []
    by_key: dict[tuple[str | None, str], dict] = {}
    for message in missed:
        key = _speaker_label(message)
        row = by_key.get(key)
        if row is None:
            row = {"speaker_id": key[0], "speaker_name": key[1], "count": 0}
            by_key[key] = row
            by_speaker.append(row)
        row["count"] += 1

    window = {
        "anchor_message_id": anchor_message_id,
        "anchor_message_count": anchor_message_count,
        "resolution": resolution,
        "first_missed_message_id": missed[0].id if missed else None,
        "last_missed_message_id": missed[-1].id if missed else None,
        "missed_count": len(missed),
    }

    place = group_name or "the group"
    if not missed:
        text = f"While {character_name} was away, nothing was posted in {place}."
    else:
        if len(missed) == 1:
            header = f"While {character_name} was away, 1 message was posted in {place}:"
        else:
            header = (
                f"While {character_name} was away, {len(missed)} messages "
                f"were posted in {place}:"
            )
        lines = [header]
        for entry in entries:
            lines.append(f"[{entry['speaker_name']}] {entry['excerpt']}")
        if omitted_count:
            noun = "message" if omitted_count == 1 else "messages"
            lines.append(
                f"(+{omitted_count} more {noun} not shown "
                f"— raise max_entries to see them.)"
            )
        text = "\n".join(lines)

    return {
        "kind": "extractive_digest",
        "digest_version": DIGEST_VERSION,
        "group_id": group_id,
        "group_name": group_name,
        "chat_id": chat_id,
        "character_id": character_id,
        "character_name": character_name,
        "absent_since": absent_since,
        "built_at": datetime.now(UTC).isoformat(),
        "delivered": delivered,
        "window": window,
        "missed_count": len(missed),
        "own_messages_in_window": own_count,
        "by_speaker": by_speaker,
        "entries": entries,
        "omitted_count": omitted_count,
        "empty": len(missed) == 0,
        "text": text,
    }


def digest_prompt_message(digest: dict) -> dict:
    """One system prompt dict carrying the digest, honestly labelled."""
    place = digest.get("group_name") or "the group"
    content = (
        f"History digest for {digest['character_name']} — what was said "
        f"in {place} while they were away. This is an extractive digest "
        f"of the real history, not a summary:\n{digest['text']}"
    )
    return {"role": "system", "content": content}


def _validate_caps(max_entries: int, excerpt_chars: int) -> None:
    """Raise ValueError when a digest cap is outside its allowed range."""
    if not 1 <= max_entries <= MAX_ENTRIES_LIMIT:
        raise ValueError(
            f"max_entries must be in 1..{MAX_ENTRIES_LIMIT}: {max_entries}"
        )
    if not EXCERPT_CHARS_MIN <= excerpt_chars <= EXCERPT_CHARS_MAX:
        raise ValueError(
            f"excerpt_chars must be in "
            f"{EXCERPT_CHARS_MIN}..{EXCERPT_CHARS_MAX}: {excerpt_chars}"
        )


async def _events(session: AsyncSession, chat_id: str) -> list[ChatEvent]:
    """Presence events for the room chat, ordered (created_at, id)."""
    result = await session.execute(
        select(ChatEvent)
        .where(
            ChatEvent.chat_id == chat_id,
            ChatEvent.kind.in_([KIND_LEFT, KIND_RETURNED]),
        )
        .order_by(ChatEvent.created_at, ChatEvent.id)
    )
    return list(result.scalars())


def _open_leave(events: list[ChatEvent], character_id: str) -> ChatEvent | None:
    """The open leave event for a character, or None when present.

    The latest presence event (in scan order) for the character
    decides: it is an open leave iff its kind is ``presence.left``.
    """
    latest: ChatEvent | None = None
    for event in events:
        try:
            data = json.loads(event.data or "{}")
        except (TypeError, ValueError):
            continue
        if data.get("character_id") == character_id:
            latest = event
    if latest is not None and latest.kind == KIND_LEFT:
        return latest
    return None


def _member(group_dict: dict, character_id: str) -> dict:
    """Find a roster member dict. ValueError when not a member."""
    for member in group_dict["members"]:
        if member["character_id"] == character_id:
            return member
    raise ValueError(f"not a group member: {character_id}")


async def _transcript(
    session: AsyncSession, user_id: str, group_id: str
) -> list[Message]:
    """The room transcript in canonical order, via store's public seam."""
    rows = await store.list_messages(session, user_id, group_id)
    return _canonical_order(rows or [])


def _slice_window(messages, data: dict):
    """Slice the absence window out of an ordered transcript.

    Returns ``(window_messages, resolution)`` where resolution is
    ``"by_id"`` when the leave anchor message still exists,
    ``"from_start"`` when there was no anchor, and
    ``"by_count_fallback"`` when the anchor is gone (deleted while
    away) and the recorded message-count-at-leave slices instead.
    The fallback starts at ``anchor_count - 1``: exact when the
    anchor itself is the only pre-window deletion; with D pre-window
    deletions it misses the earliest D-1 missed messages -- a
    documented approximation.
    """
    anchor = data.get("last_seen_message_id")
    count = int(data.get("message_count_at_leave") or 0)
    if anchor is None:
        return (list(messages), "from_start")
    ids = [m.id for m in messages]
    if anchor in ids:
        return (list(messages[ids.index(anchor) + 1:]), "by_id")
    start = max(0, count - 1) if count >= 1 else 0
    return (list(messages[start:]), "by_count_fallback")


async def _window_for(session: AsyncSession, user_id: str, group_dict: dict, character_id: str):
    """Resolve ``(leave_event, window_messages, resolution)``.

    Raises ValueError when the character is not absent, or when the
    group has no room chat. None is never returned here: group-missing
    is handled by the caller before this is invoked.
    """
    chat_id = group_dict["chat_id"]
    if not chat_id:
        raise ValueError("group has no room chat")
    events = await _events(session, chat_id)
    leave = _open_leave(events, character_id)
    if leave is None:
        raise ValueError("character is not absent")
    data = json.loads(leave.data or "{}")
    messages = await _transcript(session, user_id, group_dict["id"])
    window, resolution = _slice_window(messages, data)
    return leave, window, resolution


async def mark_absent(
    session: AsyncSession, user_id: str, group_id: str, character_id: str
) -> dict | None:
    """Record a character leaving the group room.

    None means the group is missing (or foreign) ONLY; every
    member/state failure raises ValueError. Records a metadata-only
    ``presence.left`` event and returns the presence record.
    """
    group = await store.describe_group(session, user_id, group_id)
    if group is None:
        return None
    member = _member(group, character_id)
    chat_id = group["chat_id"]
    if not chat_id:
        raise ValueError("group has no room chat")
    events = await _events(session, chat_id)
    if _open_leave(events, character_id) is not None:
        raise ValueError("character is already absent")
    messages = await _transcript(session, user_id, group_id)
    last = messages[-1] if messages else None
    data = {
        "group_id": group_id,
        "character_id": character_id,
        "character_name": member["name"],
        "last_seen_message_id": last.id if last else None,
        "message_count_at_leave": len(messages),
    }
    event = ChatEvent(chat_id=chat_id, kind=KIND_LEFT, data=json.dumps(data))
    session.add(event)
    await session.commit()
    await session.refresh(event)
    return {
        "group_id": group_id,
        "chat_id": chat_id,
        "character_id": character_id,
        "character_name": member["name"],
        "present": False,
        "absent_since": event.created_at.isoformat(),
        "last_seen_message_id": data["last_seen_message_id"],
        "message_count_at_leave": len(messages),
        "missed_count": 0,
    }


async def missed_digest(
    session: AsyncSession,
    user_id: str,
    group_id: str,
    character_id: str,
    *,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    excerpt_chars: int = DEFAULT_EXCERPT_CHARS,
) -> dict | None:
    """Preview the digest for an absent character, changing nothing.

    None means the group is missing (or foreign) ONLY; every
    member/state failure (including not being absent) raises
    ValueError, as do out-of-range caps.
    """
    _validate_caps(max_entries, excerpt_chars)
    group = await store.describe_group(session, user_id, group_id)
    if group is None:
        return None
    member = _member(group, character_id)
    leave, window, resolution = await _window_for(
        session, user_id, group, character_id
    )
    data = json.loads(leave.data or "{}")
    return build_digest(
        window,
        group_id=group_id,
        group_name=group["name"],
        chat_id=group["chat_id"],
        character_id=character_id,
        character_name=data.get("character_name") or member["name"],
        absent_since=leave.created_at.isoformat(),
        anchor_message_id=data.get("last_seen_message_id"),
        anchor_message_count=int(data.get("message_count_at_leave") or 0),
        resolution=resolution,
        max_entries=max_entries,
        excerpt_chars=excerpt_chars,
        delivered=False,
    )


async def mark_returned(
    session: AsyncSession,
    user_id: str,
    group_id: str,
    character_id: str,
    *,
    max_entries: int = DEFAULT_MAX_ENTRIES,
    excerpt_chars: int = DEFAULT_EXCERPT_CHARS,
) -> dict | None:
    """Return an absent character, delivering its digest.

    None means the group is missing (or foreign) ONLY; every
    member/state failure raises ValueError. The digest is built
    FIRST (delivered=True); only after the build succeeds is a
    metadata-only ``presence.returned`` event written, so a failed
    build writes no event and closes nothing. Returns the digest.
    """
    _validate_caps(max_entries, excerpt_chars)
    group = await store.describe_group(session, user_id, group_id)
    if group is None:
        return None
    member = _member(group, character_id)
    leave, window, resolution = await _window_for(
        session, user_id, group, character_id
    )
    data = json.loads(leave.data or "{}")
    digest = build_digest(
        window,
        group_id=group_id,
        group_name=group["name"],
        chat_id=group["chat_id"],
        character_id=character_id,
        character_name=data.get("character_name") or member["name"],
        absent_since=leave.created_at.isoformat(),
        anchor_message_id=data.get("last_seen_message_id"),
        anchor_message_count=int(data.get("message_count_at_leave") or 0),
        resolution=resolution,
        max_entries=max_entries,
        excerpt_chars=excerpt_chars,
        delivered=True,
    )
    returned_data = {
        "group_id": group_id,
        "character_id": character_id,
        "character_name": digest["character_name"],
        "missed_count": digest["missed_count"],
        "own_messages_in_window": digest["own_messages_in_window"],
        "first_missed_message_id": digest["window"]["first_missed_message_id"],
        "last_missed_message_id": digest["window"]["last_missed_message_id"],
        "resolution": digest["window"]["resolution"],
    }
    event = ChatEvent(
        chat_id=group["chat_id"], kind=KIND_RETURNED, data=json.dumps(returned_data)
    )
    session.add(event)
    await session.commit()
    return digest


async def list_presence(
    session: AsyncSession, user_id: str, group_id: str
) -> list[dict] | None:
    """One presence record per current member, in roster order.

    None means the group is missing (or foreign) ONLY. Events and
    the transcript are each fetched once for the whole call.
    """
    group = await store.describe_group(session, user_id, group_id)
    if group is None:
        return None
    chat_id = group["chat_id"]
    if chat_id:
        events = await _events(session, chat_id)
        messages = await _transcript(session, user_id, group_id)
    else:
        events = []
        messages = []
    records: list[dict] = []
    for member in group["members"]:
        cid = member["character_id"]
        leave = _open_leave(events, cid)
        if leave is None:
            records.append(
                {
                    "character_id": cid,
                    "character_name": member["name"],
                    "present": True,
                    "absent_since": None,
                    "last_seen_message_id": None,
                    "missed_count": 0,
                }
            )
            continue
        data = json.loads(leave.data or "{}")
        window, _resolution = _slice_window(messages, data)
        missed = sum(1 for m in window if m.speaker_id != cid)
        records.append(
            {
                "character_id": cid,
                "character_name": member["name"],
                "present": False,
                "absent_since": leave.created_at.isoformat(),
                "last_seen_message_id": data.get("last_seen_message_id"),
                "missed_count": missed,
            }
        )
    return records
