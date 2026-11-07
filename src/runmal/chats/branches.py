"""Chat branches (P-066): fork a chat at any message, list and name
branches, merge a branch back as a NEW branch.

The never-destructive law governs everything here: forking COPIES
messages into a new chat, merging CREATES a new chat, renaming
touches only the branch's own title. No operation in this module
mutates or deletes a source chat, branch, or message.

A branch is an ordinary chat row plus lineage (PROVISIONAL 0037):
``branch_parent_id`` (plain id, no FK, so a parent's deletion can
never cascade into a branch), ``branch_fork_message_id`` (the
message id in the parent where the fork was taken; NULL for a
whole-chat fork), ``branch_fork_index`` (how many messages were
copied), ``branch_kind`` ('root' | 'fork' | 'merge') and
``branch_merge_of_json`` (source ids for merge branches).

Copied messages get fresh ids and keep their original
``created_at``/``updated_at``, so the copy's history order -- the
service orders by ``created_at`` -- reproduces the source order.
One exception: a merge suffix that would interleave into the
target (its timestamps at or before the target's last message) is
shifted, as one block with internal gaps preserved, to start just
after the target's last message -- concatenation order wins over
wall-clock purity, and the shift is the honest price of an
order-by-timestamp history with no sequence column.
The event log is NOT copied: a branch's log starts with its own
``branch.created`` event stating exactly what was copied.

Merge-back semantics (message grain, no text merge): the result
is a new chat holding the TARGET's full history followed by the
BRANCH's divergent suffix -- the branch messages after its fork
index when the branch forked directly from the target, otherwise
the branch's whole history. Divergence inside one message is
never reconciled; the suffix is appended whole.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.chats.service import _get_owned_chat, _record_event
from runmal.chats import provenance as prov_mod
from runmal.db.models import Chat, Message

EVENT_BRANCH_CREATED = "branch.created"
EVENT_BRANCH_FORKED = "branch.forked"
EVENT_BRANCH_MERGED = "branch.merged"
EVENT_BRANCH_RENAMED = "branch.renamed"

KIND_ROOT = "root"
KIND_FORK = "fork"
KIND_MERGE = "merge"


def branch_info(chat: Chat) -> dict:
    """The branch sub-document for a chat (additive in chat_to_dict)."""
    try:
        merge_of = json.loads(getattr(chat, "branch_merge_of_json", None) or "[]")
        if not isinstance(merge_of, list):
            merge_of = []
    except (json.JSONDecodeError, TypeError):
        merge_of = []
    return {
        "kind": getattr(chat, "branch_kind", None) or KIND_ROOT,
        "parent_id": getattr(chat, "branch_parent_id", None),
        "fork_message_id": getattr(chat, "branch_fork_message_id", None),
        "fork_index": getattr(chat, "branch_fork_index", None),
        "merge_of": merge_of,
        "is_branch": (getattr(chat, "branch_kind", None) or KIND_ROOT) != KIND_ROOT,
    }


async def _history(session: AsyncSession, chat_id: str) -> list[Message]:
    result = await session.execute(
        select(Message).where(Message.chat_id == chat_id).order_by(Message.created_at)
    )
    return list(result.scalars().all())


def _aware(value):
    # Normalise a stored timestamp to aware UTC. Rows read back from
    # SQLite arrive naive; freshly created rows carry UTC. Copies must
    # serialise identically to originals, so naive reads as UTC.
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def _copy_message(source: Message, chat_id: str, created_at=None) -> Message:
    return Message(
        chat_id=chat_id,
        role=source.role,
        content=source.content,
        speaker_id=source.speaker_id,
        speaker_name=source.speaker_name,
        provenance_json=prov_mod.dump_document(
            prov_mod.document_for_copy(
                {"schema": prov_mod.PROVENANCE_SCHEMA, "recorded": True,
                 "recorded_at": None,
                 "swipes": {"0": prov_mod.active_record(source)}},
                source_chat_id=source.chat_id,
                source_message_id=source.id,
                source_content_sha256=hashlib.sha256(
                    source.content.encode("utf-8")).hexdigest())),
        created_at=created_at if created_at is not None else _aware(source.created_at),
        updated_at=_aware(source.updated_at),
    )


def _clean_name(name: str | None) -> str | None:
    if name is None:
        return None
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("branch name must not be empty")
    return cleaned


def _fork_title(source: Chat, name: str | None) -> str:
    if name is not None:
        return name
    if source.title:
        return f"{source.title} (branch)"
    return "Untitled branch"


def _merge_title(target: Chat, branch: Chat, name: str | None) -> str:
    if name is not None:
        return name
    if target.title or branch.title:
        return f"{target.title or 'Untitled chat'} + {branch.title or 'branch'} (merged)"
    return "Merged branch"


def _spawn_chat(source: Chat, user_id: str, title: str) -> Chat:
    """A new chat carrying the source's settings (never its group-room
    link: a branch is a standalone chat, not the group's room)."""
    return Chat(
        user_id=user_id,
        title=title,
        character_id=source.character_id,
        preset_id=source.preset_id,
        backend_profile_id=source.backend_profile_id,
        authors_note_json=source.authors_note_json,
        post_history_json=source.post_history_json,
    )


async def fork_chat(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    message_id: str | None = None,
    name: str | None = None,
) -> Chat | None:
    """Fork a chat at a message (P-066): a NEW chat holding a copy of
    the source history up to and including ``message_id`` (the whole
    history when ``message_id`` is None).

    Missing chat returns None; a message id that is not part of the
    chat raises ValueError; an explicitly blank name raises
    ValueError. The source is never mutated. Forking an empty chat
    is legal and yields an empty branch.
    """
    source = await _get_owned_chat(session, user_id, chat_id)
    if source is None:
        return None
    cleaned = _clean_name(name)
    history = await _history(session, chat_id)
    if message_id is None:
        prefix = history
        fork_message_id = None
    else:
        position = next((i for i, m in enumerate(history) if m.id == message_id), None)
        if position is None:
            raise ValueError(f"message {message_id!r} is not part of chat {chat_id!r}")
        prefix = history[: position + 1]
        fork_message_id = message_id
    branch = _spawn_chat(source, user_id, _fork_title(source, cleaned))
    branch.branch_parent_id = source.id
    branch.branch_fork_message_id = fork_message_id
    branch.branch_fork_index = len(prefix)
    branch.branch_kind = KIND_FORK
    branch.branch_merge_of_json = "[]"
    session.add(branch)
    await session.flush()
    for message in prefix:
        session.add(_copy_message(message, branch.id))
    await session.flush()
    await _record_event(
        session,
        branch.id,
        EVENT_BRANCH_CREATED,
        data={
            "parent_id": source.id,
            "fork_message_id": fork_message_id,
            "fork_index": len(prefix),
            "copied_messages": len(prefix),
            "kind": KIND_FORK,
        },
    )
    await _record_event(
        session,
        source.id,
        EVENT_BRANCH_FORKED,
        data={
            "branch_id": branch.id,
            "fork_message_id": fork_message_id,
            "fork_index": len(prefix),
        },
    )
    await session.commit()
    return branch


async def rename_branch(
    session: AsyncSession, user_id: str, chat_id: str, name: str
) -> Chat | None:
    """Name a branch (P-066): sets the chat's OWN title only and
    records branch.renamed. Missing chat returns None; a blank
    name raises ValueError. Works for any chat -- a name is a
    name -- but the branch surface uses it for branches.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    cleaned = _clean_name(name)
    assert cleaned is not None  # name is required here; None cleans to None
    from runmal.chats import undo as undo_mod

    await undo_mod.record_journal(session, user_id, chat, "branch.rename")
    chat.title = cleaned
    await _record_event(session, chat.id, EVENT_BRANCH_RENAMED, data={"title": cleaned})
    await session.commit()
    return chat


async def _all_owned_chats(session: AsyncSession, user_id: str) -> list[Chat]:
    result = await session.execute(
        select(Chat).where(Chat.user_id == user_id).order_by(Chat.created_at)
    )
    return list(result.scalars().all())


async def list_branch_family(
    session: AsyncSession, user_id: str, chat_id: str
) -> dict | None:
    """The branch family of a chat (P-066): root, ancestors, the chat
    itself, its children and all descendants -- every member named
    by its title. Missing chat returns None.

    The walk is visited-set guarded: even a corrupt lineage cycle
    (which the write paths cannot create) cannot loop the read.
    A parent id pointing at a deleted chat simply ends the chain:
    branches outlive their parents by design.
    """
    from runmal.chats.service import chat_to_dict

    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    chats = await _all_owned_chats(session, user_id)
    by_id = {c.id: c for c in chats}
    counts: dict[str, int] = {}
    for c in chats:
        counts[c.id] = 0
    rows = await session.execute(select(Message.chat_id))
    for (cid,) in rows.all():
        if cid in counts:
            counts[cid] += 1
    children_of: dict[str, list[Chat]] = {}
    for c in chats:
        parent = getattr(c, "branch_parent_id", None)
        if parent:
            children_of.setdefault(parent, []).append(c)
    # Ancestors: walk up from the chat to the root.
    ancestors: list[Chat] = []
    seen: set[str] = {chat.id}
    cursor = getattr(chat, "branch_parent_id", None)
    while cursor and cursor in by_id and cursor not in seen:
        seen.add(cursor)
        ancestors.append(by_id[cursor])
        cursor = getattr(by_id[cursor], "branch_parent_id", None)
    ancestors.reverse()
    root = ancestors[0] if ancestors else chat
    # Descendants: breadth-first from the chat, cycle-safe.
    descendants: list[Chat] = []
    queue = list(children_of.get(chat.id, []))
    seen_desc: set[str] = {chat.id}
    while queue:
        node = queue.pop(0)
        if node.id in seen_desc:
            continue
        seen_desc.add(node.id)
        descendants.append(node)
        queue.extend(children_of.get(node.id, []))
    family_ids = {root.id} | {c.id for c in ancestors} | {chat.id} | {c.id for c in descendants}
    # Siblings share the chat's parent; family = root line + descendants of root.
    root_desc: list[Chat] = []
    queue = list(children_of.get(root.id, []))
    seen_root: set[str] = {root.id}
    while queue:
        node = queue.pop(0)
        if node.id in seen_root:
            continue
        seen_root.add(node.id)
        root_desc.append(node)
        queue.extend(children_of.get(node.id, []))
    family_ids |= seen_root
    def entry(c: Chat) -> dict:
        payload = chat_to_dict(c, counts.get(c.id, 0))
        return payload
    return {
        "chat_id": chat.id,
        "root": entry(root),
        "ancestors": [entry(c) for c in ancestors],
        "self": entry(chat),
        "children": [entry(c) for c in children_of.get(chat.id, [])],
        "descendants": [entry(c) for c in descendants],
        "family": [entry(by_id[i]) for i in by_id if i in family_ids],
    }


async def merge_back(
    session: AsyncSession,
    user_id: str,
    branch_id: str,
    target_id: str | None = None,
    name: str | None = None,
) -> Chat | None:
    """Merge a branch back as a NEW branch (P-066): the result holds
    the target's full history plus the branch's divergent suffix.
    Neither source is mutated or deleted, ever.

    ``target_id`` defaults to the branch's parent. Missing branch
    or target returns None; merging a chat into itself, merging a
    root chat that was never forked (no parent and no explicit
    target), a blank name, and a branch with nothing divergent to
    contribute all raise ValueError.
    """
    branch = await _get_owned_chat(session, user_id, branch_id)
    if branch is None:
        return None
    cleaned = _clean_name(name)
    resolved_target = target_id or getattr(branch, "branch_parent_id", None)
    if resolved_target is None:
        raise ValueError("merge-back needs a target: this chat has no branch parent")
    if resolved_target == branch.id:
        raise ValueError("a chat cannot be merged into itself")
    target = await _get_owned_chat(session, user_id, resolved_target)
    if target is None:
        return None
    branch_history = await _history(session, branch.id)
    if getattr(branch, "branch_parent_id", None) == target.id and getattr(branch, "branch_fork_index", None) is not None:
        suffix = branch_history[int(branch.branch_fork_index):]
    else:
        suffix = branch_history
    if not suffix:
        raise ValueError("nothing to merge: the branch has no messages beyond the fork point")
    target_history = await _history(session, target.id)
    # History is ordered by created_at alone, and copies keep their
    # original timestamps -- so a suffix older than the target would
    # sort INTO the target instead of after it. Shift the suffix, in
    # one block with its internal gaps preserved, to start just
    # after the target's last message whenever it would interleave.
    suffix_shift = None
    if target_history and suffix:
        last_target = _aware(target_history[-1].created_at)
        first_suffix = _aware(suffix[0].created_at)
        if last_target is not None and first_suffix is not None and first_suffix <= last_target:
            suffix_shift = (last_target - first_suffix) + timedelta(microseconds=1)
    merged = _spawn_chat(target, user_id, _merge_title(target, branch, cleaned))
    merged.branch_parent_id = target.id
    merged.branch_fork_message_id = None
    merged.branch_fork_index = len(target_history)
    merged.branch_kind = KIND_MERGE
    merged.branch_merge_of_json = json.dumps([target.id, branch.id])
    session.add(merged)
    await session.flush()
    for message in target_history:
        session.add(_copy_message(message, merged.id))
    for message in suffix:
        if suffix_shift is not None:
            session.add(_copy_message(message, merged.id, created_at=_aware(message.created_at) + suffix_shift))
        else:
            session.add(_copy_message(message, merged.id))
    await session.flush()
    total = len(target_history) + len(suffix)
    await _record_event(
        session,
        merged.id,
        EVENT_BRANCH_CREATED,
        data={
            "parent_id": target.id,
            "fork_message_id": None,
            "fork_index": len(target_history),
            "copied_messages": total,
            "kind": KIND_MERGE,
            "merge_of": [target.id, branch.id],
        },
    )
    await _record_event(
        session,
        branch.id,
        EVENT_BRANCH_MERGED,
        data={"merged_into": merged.id, "target_id": target.id, "suffix_messages": len(suffix)},
    )
    await _record_event(
        session,
        target.id,
        EVENT_BRANCH_MERGED,
        data={"merged_into": merged.id, "branch_id": branch.id, "suffix_messages": len(suffix)},
    )
    await session.commit()
    return merged
