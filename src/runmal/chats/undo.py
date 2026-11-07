"""Chat undo journal (P-076): undo for chat operations -- the
coder's journal pattern at chat scale.

The journal pattern, write-ahead style: BEFORE a covered chat
operation mutates anything, the chat's complete prior state is
written down durably as one sealed journal entry. Undo replays
the journal backwards: it pops the newest entry and restores
its snapshot IN PLACE, consuming the entry. Undo is the rewind
verb the checkpoint slice (P-067) deliberately is not -- a
checkpoint restores as a NEW chat and discards nothing; an
undo rewinds THIS chat by exactly one operation and discards
exactly what that operation added, because the journal entry
proves what was there before it.

Storage rides the P-067 / P-074 file idiom -- no DB rows, no
migration (head stays 0039): one self-contained JSON file per
entry at ``data_dir()/undo/<user_id>/<chat_id>/<entry_id>.json``,
sealed by a SHA-256 checksum over the canonical bytes of the
snapshot payload, written atomically (tmp sibling, chmod
0o600, replace). Listing is a directory scan; there is no
index file to disagree with the directory. The stack is
bounded: ``MAX_ENTRIES`` per chat, pruned oldest-first after
each write -- a pruned entry is gone, and the bound is part
of the contract.

A snapshot is the chat's whole restorable state, built with
the archive's ``row_to_dict`` (never a hand-rolled serialiser):
the chat row, every message row in display order, the chat's
tag rows and organisation row (P-073), and the pin memories
of the chat's messages -- Memory rows linked by MemorySource,
all their source rows, and their chunks -- so undoing the
delete or edit of a pinned message restores the pin exactly,
original ids included, with its FTS row rebuilt.

Covered operations (journaled in chats/service.py,
chats/metadata.py and chats/branches.py, always AFTER
validation and no-op checks, BEFORE any mutation): message
append / edit / delete / move, swipe add / select / delete /
import, pin / unpin, chat rename, author's note, post-history,
swipe settings, preset, persona, backend profile, metadata
update / regenerate, favourite, and branch rename. NOT
covered, by law: chat creation and deletion (deletion is
terminal -- the journal dies with the chat), fork / merge /
copy-to-branch (they create OTHER chats; undo never deletes
another chat), checkpoints and the data bank (their own file
systems, their own delete verbs), and redo (undo consumes
its entry; there is no redo stack).

Every operation verifies the owned chat FIRST
(``service._get_owned_chat``) before any file is touched, and
an entry id is validated before any path is built from it: a
missing or foreign chat, and an unknown entry, read as
None/False; a malformed id raises ValueError; a corrupt,
tampered, or foreign payload raises UndoError. Unknown and
corrupt stay distinct, always. A corrupt TOP entry blocks
the stack loudly (undo raises, restores nothing, consumes
nothing) until the journal is cleared -- stepping silently
past it would falsify the stack.

Clean-room: built from Runmal's own archive / checkpoint /
restore contracts only.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import uuid
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.auth import data_dir
from runmal.chats.service import _get_owned_chat, _ordered_messages, _record_event
from runmal.db.models import (
    Chat,
    ChatOrganisation,
    ChatTag,
    Memory,
    MemoryChunk,
    MemorySource,
    Message,
)
from runmal.portable.archive import row_to_dict
from runmal.portable.restore import _row

FORMAT_NAME = "runmal-undo-journal"
FORMAT_VERSION = 1

EVENT_UNDO_PERFORMED = "undo.performed"

MAX_ENTRIES = 50

_PAYLOAD_KEYS = (
    "chat",
    "messages",
    "chat_tags",
    "chat_organisation",
    "pin_memories",
    "pin_sources",
    "pin_chunks",
)


class UndoError(Exception):
    """A journal payload is corrupt, tampered, foreign, or of
    an unsupported format or version (mirrors CheckpointError:
    a plain Exception, NOT a ValueError subclass, so the two
    map distinctly even though both land on 422 at the router)."""


_ENTRY_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def _validate_entry_id(entry_id) -> None:
    """Raise ValueError unless ``entry_id`` is a plain filename
    stem. Called before ANY path is constructed from the id."""
    if (
        not isinstance(entry_id, str)
        or entry_id in (".", "..")
        or "/" in entry_id
        or "\\" in entry_id
        or "\x00" in entry_id
        or not _ENTRY_ID_RE.fullmatch(entry_id)
    ):
        raise ValueError(f"malformed undo entry id: {entry_id!r}")


def _root(base_dir: Path | None) -> Path:
    return base_dir if base_dir is not None else data_dir()


def _chat_undo_dir(user_id: str, chat_id: str, base_dir: Path | None = None) -> Path:
    return _root(base_dir) / "undo" / user_id / chat_id


def _entry_path(
    user_id: str, chat_id: str, entry_id: str, base_dir: Path | None = None
) -> Path:
    directory = _chat_undo_dir(user_id, chat_id, base_dir)
    path = directory / f"{entry_id}.json"
    if path.resolve().parent != directory.resolve():
        raise ValueError(f"undo entry path escapes its directory: {entry_id!r}")
    return path


def _canonical_bytes(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _checksum(payload: dict) -> str:
    """SHA-256 over the canonical bytes of the snapshot payload
    alone -- the state is sealed; entry metadata is not."""
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def journal_to_dict(document: dict) -> dict:
    """Pure metadata projection of a journal entry: never
    message bodies, never pin contents, never the checksum."""
    return {
        "id": document["id"],
        "chat_id": document["chat_id"],
        "seq": document["seq"],
        "operation": document["operation"],
        "detail": document["detail"],
        "created_at": document["created_at"],
        "message_count": document["message_count"],
    }


def _write_entry_file(path: Path, document: dict) -> None:
    """Write an entry document atomically (auth credential
    pattern): canonical bytes to the tmp sibling in the SAME
    directory, chmod 0o600 (entries hold full chat content;
    owner-readable only), then replace. On any exception
    before the replace the tmp file is unlinked best-effort
    and the error propagates."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    try:
        tmp.write_bytes(_canonical_bytes(document))
        os.chmod(tmp, 0o600)
        tmp.replace(path)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def _load_verified_entry(
    user_id: str, chat_id: str, entry_id: str, *, base_dir: Path | None = None
) -> dict | None:
    """The full verified entry document, or None only for "no
    such file". A malformed id raises ValueError (before any
    path is built); every other problem -- unreadable JSON,
    wrong format or version, missing or wrongly-typed envelope
    or payload fields, identity mismatch, message_count
    mismatch, checksum mismatch -- raises UndoError."""
    _validate_entry_id(entry_id)
    path = _entry_path(user_id, chat_id, entry_id, base_dir)
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UndoError(f"undo entry {entry_id!r} is unreadable: {exc}") from exc
    if not isinstance(document, dict):
        raise UndoError(f"undo entry {entry_id!r} is not a JSON object")
    if document.get("format") != FORMAT_NAME:
        raise UndoError(f"undo entry {entry_id!r} format is not {FORMAT_NAME}")
    if document.get("format_version") != FORMAT_VERSION:
        raise UndoError(
            f"undo entry {entry_id!r} has unsupported format_version "
            f"{document.get('format_version')!r}"
        )
    for key in ("id", "chat_id", "user_id", "operation", "created_at"):
        if not isinstance(document.get(key), str):
            raise UndoError(f"undo entry {entry_id!r} has a missing or invalid {key!r}")
    seq = document.get("seq")
    if not isinstance(seq, int) or isinstance(seq, bool) or seq < 1:
        raise UndoError(f"undo entry {entry_id!r} has a missing or invalid 'seq'")
    if not isinstance(document.get("detail"), dict):
        raise UndoError(f"undo entry {entry_id!r} has a missing or invalid 'detail'")
    message_count = document.get("message_count")
    if not isinstance(message_count, int) or isinstance(message_count, bool):
        raise UndoError(
            f"undo entry {entry_id!r} has a missing or invalid 'message_count'"
        )
    if (
        document["id"] != entry_id
        or document["chat_id"] != chat_id
        or document["user_id"] != user_id
    ):
        raise UndoError(
            f"undo entry {entry_id!r} identity mismatch: the document does not "
            "belong to this chat and owner"
        )
    payload = document.get("payload")
    if not isinstance(payload, dict):
        raise UndoError(f"undo entry {entry_id!r} has a missing or invalid 'payload'")
    for key in _PAYLOAD_KEYS:
        if key not in payload:
            raise UndoError(f"undo entry {entry_id!r} payload is missing {key!r}")
    if not isinstance(payload["chat"], dict):
        raise UndoError(f"undo entry {entry_id!r} payload 'chat' is not an object")
    for key in ("messages", "chat_tags", "pin_memories", "pin_sources", "pin_chunks"):
        if not isinstance(payload[key], list):
            raise UndoError(f"undo entry {entry_id!r} payload {key!r} is not a list")
    if payload["chat_organisation"] is not None and not isinstance(
        payload["chat_organisation"], dict
    ):
        raise UndoError(
            f"undo entry {entry_id!r} payload 'chat_organisation' is invalid"
        )
    if payload["chat"].get("id") != chat_id:
        raise UndoError(f"undo entry {entry_id!r} payload chat is foreign")
    for message in payload["messages"]:
        if not isinstance(message, dict):
            raise UndoError(f"undo entry {entry_id!r} holds a non-object message")
        if "chat_id" in message and message["chat_id"] != chat_id:
            raise UndoError(f"undo entry {entry_id!r} holds a foreign message")
    if message_count != len(payload["messages"]):
        raise UndoError(
            f"undo entry {entry_id!r} message_count {message_count} "
            f"!= {len(payload['messages'])} stored messages"
        )
    if document.get("checksum") != _checksum(payload):
        raise UndoError(f"undo entry {entry_id!r} checksum mismatch")
    return document


def _scan_entry_docs(
    user_id: str, chat_id: str, base_dir: Path | None = None
) -> list[dict]:
    """Every entry document in the chat's journal directory,
    parsed at envelope level (id / seq / created_at), sorted
    by seq ascending. A file that does not parse raises
    UndoError -- a corrupt entry is surfaced loudly, never
    silently dropped from the stack."""
    directory = _chat_undo_dir(user_id, chat_id, base_dir)
    if not directory.is_dir():
        return []
    docs: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise UndoError(f"undo entry file {path.name!r} is unreadable: {exc}") from exc
        if not isinstance(document, dict):
            raise UndoError(f"undo entry file {path.name!r} is not a JSON object")
        seq = document.get("seq")
        if not isinstance(seq, int) or isinstance(seq, bool):
            raise UndoError(f"undo entry file {path.name!r} has an invalid 'seq'")
        docs.append(document)
    docs.sort(key=lambda d: (d["seq"], str(d.get("id"))))
    return docs


async def _pin_rows(
    session: AsyncSession, user_id: str, chat_id: str
) -> tuple[list[Memory], list[MemorySource], list[MemoryChunk]]:
    """The pin memories of a chat's messages: Memory rows
    linked by a MemorySource (source_kind 'message' scoped to
    this chat), ALL source rows of those memories, and their
    chunks. Ordered deterministically for the seal."""
    memory_ids = list(
        await session.scalars(
            select(MemorySource.memory_id)
            .where(
                MemorySource.source_kind == "message",
                MemorySource.chat_id == chat_id,
            )
            .distinct()
        )
    )
    if not memory_ids:
        return [], [], []
    memories = list(
        (
            await session.execute(
                select(Memory)
                .where(Memory.id.in_(memory_ids), Memory.user_id == user_id)
                .order_by(Memory.id)
            )
        )
        .scalars()
        .all()
    )
    kept_ids = [m.id for m in memories]
    if not kept_ids:
        return [], [], []
    sources = list(
        (
            await session.execute(
                select(MemorySource)
                .where(MemorySource.memory_id.in_(kept_ids))
                .order_by(MemorySource.memory_id, MemorySource.source_kind, MemorySource.source_id)
            )
        )
        .scalars()
        .all()
    )
    chunks = list(
        (
            await session.execute(
                select(MemoryChunk)
                .where(MemoryChunk.memory_id.in_(kept_ids))
                .order_by(MemoryChunk.memory_id, MemoryChunk.chunk_index, MemoryChunk.id)
            )
        )
        .scalars()
        .all()
    )
    return memories, sources, chunks


async def _capture_payload(session: AsyncSession, chat: Chat) -> dict:
    """The chat's whole restorable state as row_to_dict rows."""
    messages = await _ordered_messages(session, chat.id)
    tags = list(
        (
            await session.execute(
                select(ChatTag)
                .where(ChatTag.chat_id == chat.id)
                .order_by(ChatTag.tag_key)
            )
        )
        .scalars()
        .all()
    )
    org = (
        await session.execute(
            select(ChatOrganisation).where(ChatOrganisation.chat_id == chat.id)
        )
    ).scalar_one_or_none()
    memories, sources, chunks = await _pin_rows(session, chat.user_id, chat.id)
    return {
        "chat": row_to_dict(chat),
        "messages": [row_to_dict(m) for m in messages],
        "chat_tags": [row_to_dict(t) for t in tags],
        "chat_organisation": row_to_dict(org) if org is not None else None,
        "pin_memories": [row_to_dict(m) for m in memories],
        "pin_sources": [row_to_dict(s) for s in sources],
        "pin_chunks": [row_to_dict(c) for c in chunks],
    }


def _prune(user_id: str, chat_id: str, base_dir: Path | None = None) -> None:
    """Bound the stack: beyond MAX_ENTRIES, the oldest entry
    files are deleted. A pruned entry is gone for good."""
    docs = _scan_entry_docs(user_id, chat_id, base_dir)
    excess = len(docs) - MAX_ENTRIES
    if excess <= 0:
        return
    for document in docs[:excess]:
        try:
            _entry_path(user_id, chat_id, str(document.get("id")), base_dir).unlink()
        except (OSError, ValueError):
            pass


async def record_journal(
    session: AsyncSession,
    user_id: str,
    chat: Chat,
    operation: str,
    detail: dict | None = None,
    *,
    base_dir: Path | None = None,
) -> dict:
    """Journal the chat's CURRENT state as the before-image of
    ``operation`` (P-076). Called by the mutating services
    AFTER validation and no-op checks, BEFORE any mutation:
    journal-first means journal-first -- if the write fails,
    the error propagates and the operation changes nothing.
    ``detail`` carries ids / indexes / flags only, never
    content. Returns the new entry's metadata projection."""
    payload = await _capture_payload(session, chat)
    existing = _scan_entry_docs(user_id, chat.id, base_dir)
    seq = (existing[-1]["seq"] + 1) if existing else 1
    created_at = datetime.now(UTC)
    document = {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "id": str(uuid.uuid4()),
        "chat_id": chat.id,
        "user_id": user_id,
        "seq": seq,
        "operation": operation,
        "detail": detail or {},
        "created_at": created_at.isoformat(),
        "message_count": len(payload["messages"]),
        "payload": payload,
        "checksum": _checksum(payload),
    }
    _write_entry_file(_entry_path(user_id, chat.id, document["id"], base_dir), document)
    _prune(user_id, chat.id, base_dir)
    return journal_to_dict(document)


async def list_journal(
    session: AsyncSession, user_id: str, chat_id: str, *, base_dir: Path | None = None
) -> list[dict] | None:
    """A chat's journal metadata, TOP of stack first (seq
    descending). Metadata only; checksums are NOT verified
    here (this is an index, not a restore), but a file that
    does not parse raises UndoError. Returns None when the
    chat is missing or foreign."""
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    docs = _scan_entry_docs(user_id, chat_id, base_dir)
    metas: list[dict] = []
    for document in reversed(docs):
        try:
            metas.append(journal_to_dict(document))
        except (KeyError, TypeError) as exc:
            raise UndoError(
                f"undo entry in chat {chat_id!r} does not match the journal schema: {exc}"
            ) from exc
    return metas


async def get_entry(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    entry_id: str,
    *,
    base_dir: Path | None = None,
) -> dict | None:
    """One entry's metadata -- a VERIFIED read: checksum and
    identity binding are checked, so a tampered file raises
    UndoError here, not only at undo. Returns None when the
    chat or the entry is missing; a malformed entry id raises
    ValueError."""
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    document = _load_verified_entry(user_id, chat_id, entry_id, base_dir=base_dir)
    if document is None:
        return None
    return journal_to_dict(document)


async def clear_journal(
    session: AsyncSession, user_id: str, chat_id: str, *, base_dir: Path | None = None
) -> int | None:
    """Delete every journal entry of a chat; returns how many
    files were removed. Returns None when the chat is missing
    or foreign. No checksum is verified and no event is
    recorded -- clearing must stay possible even with a
    corrupt entry on the stack (checkpoint-delete precedent);
    this is the escape hatch for a blocked stack."""
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    directory = _chat_undo_dir(user_id, chat_id, base_dir)
    if not directory.is_dir():
        return 0
    removed = 0
    for path in sorted(directory.glob("*.json")):
        path.unlink()
        removed += 1
    return removed


def remove_chat_undo(user_id: str, chat_id: str, *, base_dir: Path | None = None) -> bool:
    """Remove a chat's whole undo directory (best-effort,
    ``shutil.rmtree(..., ignore_errors=True)`` semantics):
    when a chat is deleted, its journal dies with it -- undo
    cannot resurrect a chat, and an orphaned journal of a
    dead chat would be unreachable anyway. Returns True when
    the directory is absent afterwards. Synchronous and
    session-free; never raises for a missing directory."""
    if not (
        _ENTRY_ID_RE.fullmatch(user_id or "")
        and _ENTRY_ID_RE.fullmatch(chat_id or "")
    ):
        return False
    directory = _chat_undo_dir(user_id, chat_id, base_dir)
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=True)
    return not directory.exists()


async def _delete_pin_memories(session: AsyncSession, memory_ids: list[str]) -> None:
    """Remove pin memories completely: FTS rows first (the
    memory service's delete order), then chunks and source
    rows, then the Memory rows themselves."""
    if not memory_ids:
        return
    for memory_id in memory_ids:
        await session.execute(
            text("DELETE FROM memory_fts WHERE memory_id = :mid"), {"mid": memory_id}
        )
    await session.execute(delete(MemoryChunk).where(MemoryChunk.memory_id.in_(memory_ids)))
    await session.execute(delete(MemorySource).where(MemorySource.memory_id.in_(memory_ids)))
    await session.execute(delete(Memory).where(Memory.id.in_(memory_ids)))
    await session.flush()


async def _apply_restore(session: AsyncSession, chat: Chat, payload: dict) -> None:
    """Rewind the LIVE chat row to the snapshot payload, in
    place: the chat keeps its identity (same id, same owner)
    while every other field, every message, the tag and
    organisation rows, and the pin memories return to the
    snapshot state, original ids included."""
    user_id = chat.user_id
    chat_id = chat.id
    current_memories, _s, _c = await _pin_rows(session, user_id, chat_id)
    snapshot_memory_ids = [row["id"] for row in payload["pin_memories"]]
    doomed = sorted({m.id for m in current_memories} | set(snapshot_memory_ids))
    await _delete_pin_memories(session, doomed)
    await session.execute(delete(ChatTag).where(ChatTag.chat_id == chat_id))
    await session.execute(
        delete(ChatOrganisation).where(ChatOrganisation.chat_id == chat_id)
    )
    await session.execute(delete(Message).where(Message.chat_id == chat_id))
    await session.flush()
    snapshot_chat = _row(Chat, payload["chat"])
    for col in Chat.__table__.columns:
        if col.name in ("id", "user_id"):
            continue
        setattr(chat, col.name, getattr(snapshot_chat, col.name))
    await session.flush()
    for row in payload["messages"]:
        session.add(_row(Message, row))
    for row in payload["chat_tags"]:
        session.add(_row(ChatTag, row))
    if payload["chat_organisation"] is not None:
        session.add(_row(ChatOrganisation, payload["chat_organisation"]))
    restored_memories: list[Memory] = []
    for row in payload["pin_memories"]:
        memory = _row(Memory, row)
        session.add(memory)
        restored_memories.append(memory)
    for row in payload["pin_sources"]:
        session.add(_row(MemorySource, row))
    for row in payload["pin_chunks"]:
        session.add(_row(MemoryChunk, row))
    await session.flush()
    if restored_memories:
        from runmal.memory import service as memory_svc

        for memory in restored_memories:
            await memory_svc.index_fts(session, memory)


async def undo_last(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    entry_id: str | None = None,
    *,
    base_dir: Path | None = None,
) -> dict | None:
    """Undo the most recent journaled operation on a chat
    (P-076): restore its before-image IN PLACE and consume
    the entry. Stack discipline is strict LIFO: with an
    explicit ``entry_id`` it must be the top entry, else
    ValueError (out-of-order undo refused, nothing changes).
    Returns None when the chat is missing/foreign or the
    journal is empty. A corrupt top entry raises UndoError
    BEFORE any row changes and is NOT consumed. The undo
    itself is never journaled -- there is no redo."""
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    docs = _scan_entry_docs(user_id, chat_id, base_dir)
    if not docs:
        return None
    top = docs[-1]
    top_id = top.get("id")
    if entry_id is not None:
        _validate_entry_id(entry_id)
        if entry_id != top_id:
            raise ValueError(
                "out-of-order undo refused: only the most recent journal "
                "entry can be undone"
            )
    if not isinstance(top_id, str):
        raise UndoError("top undo entry has no valid id")
    document = _load_verified_entry(user_id, chat_id, top_id, base_dir=base_dir)
    if document is None:  # pragma: no cover - scanned a moment ago
        return None
    payload = document["payload"]
    await _apply_restore(session, chat, payload)
    await _record_event(
        session,
        chat.id,
        EVENT_UNDO_PERFORMED,
        data={
            "entry_id": document["id"],
            "operation": document["operation"],
            "seq": document["seq"],
        },
    )
    await session.commit()
    try:
        _entry_path(user_id, chat_id, document["id"], base_dir).unlink()
    except OSError:
        pass
    return {
        "undone": document["operation"],
        "entry_id": document["id"],
        "seq": document["seq"],
        "chat_id": chat.id,
        "restored_message_count": len(payload["messages"]),
    }
