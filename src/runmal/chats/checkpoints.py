"""Chat checkpoints (P-067): named chat snapshots (bookmarks) with
one-click return -- restore-as-new.

The never-destructive law governs everything here (branches law,
P-066): no checkpoint operation mutates or deletes the source chat,
its messages, or its event log, except that CREATE and RESTORE
append their own audit events to the source, and DELETE removes
only the checkpoint file itself. Restoring NEVER writes into the
source chat: it creates a brand-new chat whose history is the
checkpoint's messages, exactly as forking and merge-back create
new chats rather than editing old ones.

A checkpoint is a self-contained JSON file on disk -- no DB rows,
no migration -- built over the portable archive machinery (S801):
the chat row and its message rows serialised with
``runmal.portable.archive.row_to_dict`` (original IDs preserved,
swipe decks included by construction), sealed by a SHA-256 checksum
over the canonical bytes of the ``{"chat": ..., "messages": ...}``
payload, mirroring the archive manifest's per-member discipline.
Files live at
``data_dir()/checkpoints/<user_id>/<chat_id>/<checkpoint_id>.json``
and are written atomically (tmp sibling, chmod 0o600, replace --
the auth credential pattern). Listing is a directory scan; there
is no index file to disagree with the directory.

The restored chat carries the SNAPSHOT's settings (character,
preset, backend profile, author's note, post-history instructions,
swipe settings) -- never its group-room link and never its branch
lineage: a restored chat is a standalone root chat whose lineage
lives in its ``checkpoint.restored`` event data. Its messages are
rebuilt with the ``portable.restore`` decode discipline: fresh
ids, the new chat's id, and every other field verbatim, original
``created_at``/``updated_at`` included, so the restored history
reproduces the snapshot order.

Every operation verifies the owned chat FIRST
(``service._get_owned_chat``) before any file is touched, and the
checkpoint id is validated before any path is built from it: a
missing or foreign chat, and an unknown checkpoint, read as
None/False; a malformed id raises ValueError; a corrupt, tampered,
or foreign payload raises CheckpointError. Unknown and corrupt
stay distinct, always.

Clean-room: built from Rúnmál's own archive / branch / restore
contracts only.
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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.auth import data_dir
from runmal.chats.service import _get_owned_chat, _record_event
from runmal.db.models import Chat, Message
from runmal.portable.archive import row_to_dict
from runmal.portable.restore import _row

FORMAT_NAME = "runmal-checkpoint"
FORMAT_VERSION = 1

EVENT_CHECKPOINT_CREATED = "checkpoint.created"
EVENT_CHECKPOINT_RESTORED = "checkpoint.restored"


class CheckpointError(Exception):
    """A checkpoint payload is corrupt, tampered, foreign, or of an
    unsupported format or version (mirrors ``ArchiveError``: a plain
    Exception, NOT a ValueError subclass, so the two map distinctly
    even though both land on 422 at the router)."""


#: A checkpoint id is a plain filename stem: uuids qualify; anything
#: with separators, traversal, a leading dot, or a NUL never does.
_CHECKPOINT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")


def _validate_checkpoint_id(checkpoint_id) -> None:
    """Raise ValueError unless ``checkpoint_id`` is a plain filename
    stem. Called before ANY path is constructed from the id."""
    if (
        not isinstance(checkpoint_id, str)
        or checkpoint_id in (".", "..")
        or "/" in checkpoint_id
        or "\\" in checkpoint_id
        or "\x00" in checkpoint_id
        or not _CHECKPOINT_ID_RE.fullmatch(checkpoint_id)
    ):
        raise ValueError(f"malformed checkpoint id: {checkpoint_id!r}")


def _root(base_dir: Path | None) -> Path:
    return base_dir if base_dir is not None else data_dir()


def _chat_checkpoint_dir(user_id: str, chat_id: str, base_dir: Path | None = None) -> Path:
    return _root(base_dir) / "checkpoints" / user_id / chat_id


def _checkpoint_path(
    user_id: str, chat_id: str, checkpoint_id: str, base_dir: Path | None = None
) -> Path:
    """The checkpoint's file path. Only ever called after id
    validation; defence in depth after the join: the resolved
    file's parent must be the resolved chat checkpoint directory."""
    directory = _chat_checkpoint_dir(user_id, chat_id, base_dir)
    path = directory / f"{checkpoint_id}.json"
    if path.resolve().parent != directory.resolve():
        raise ValueError(f"checkpoint path escapes its directory: {checkpoint_id!r}")
    return path


def _canonical_bytes(payload) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _checksum(payload: dict) -> str:
    """SHA-256 over the canonical bytes of exactly
    ``{"chat": ..., "messages": ...}`` -- the history is sealed;
    metadata (name, id) is not."""
    return hashlib.sha256(_canonical_bytes(payload)).hexdigest()


def checkpoint_to_dict(document: dict) -> dict:
    """Pure metadata projection of a checkpoint document: never
    message bodies, never the checksum. ``chat_title`` is the title
    AT SNAPSHOT TIME, read from the payload, not the live chat."""
    return {
        "id": document["id"],
        "chat_id": document["chat_id"],
        "name": document["name"],
        "created_at": document["created_at"],
        "message_count": document["message_count"],
        "chat_title": document["chat"]["title"],
    }


def _clean_name(name: str | None) -> str | None:
    if name is None:
        return None
    cleaned = name.strip()
    if not cleaned:
        raise ValueError("checkpoint name must not be empty")
    return cleaned


def _default_name(created_at: datetime) -> str:
    """Timestamp-based default name (design decision): a count-based
    ``Checkpoint <n>`` lies after deletions and needs a pre-write
    scan; a timestamp is truthful and needs no scan. Ids, not names,
    are identity, so a shared name within one second is legal."""
    return f"Checkpoint {created_at:%Y-%m-%d %H:%M:%S} UTC"


def _write_checkpoint_file(path: Path, document: dict) -> None:
    """Write a checkpoint document atomically (auth credential
    pattern): canonical bytes to the tmp sibling in the SAME
    directory, chmod 0o600 (checkpoints hold full chat content;
    owner-readable only), then replace. On any exception before
    the replace, the tmp file is unlinked best-effort and the
    error propagates -- a crashed create never leaves a
    half-written ``<checkpoint_id>.json``."""
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


def _load_verified_checkpoint(
    user_id: str, chat_id: str, checkpoint_id: str, *, base_dir: Path | None = None
) -> dict | None:
    """The full verified checkpoint document, or None only for "no
    such file". A malformed id raises ValueError (before any path
    is built); every other problem -- unreadable JSON, wrong
    format or version, missing or wrongly-typed envelope fields,
    identity mismatch, message_count mismatch, checksum mismatch --
    raises CheckpointError with a specific message."""
    _validate_checkpoint_id(checkpoint_id)
    path = _checkpoint_path(user_id, chat_id, checkpoint_id, base_dir)
    if not path.is_file():
        return None
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise CheckpointError(f"checkpoint {checkpoint_id!r} is unreadable: {exc}") from exc
    if not isinstance(document, dict):
        raise CheckpointError(f"checkpoint {checkpoint_id!r} is not a JSON object")
    if document.get("format") != FORMAT_NAME:
        raise CheckpointError(f"checkpoint {checkpoint_id!r} format is not {FORMAT_NAME}")
    if document.get("format_version") != FORMAT_VERSION:
        raise CheckpointError(
            f"checkpoint {checkpoint_id!r} has unsupported format_version "
            f"{document.get('format_version')!r}"
        )
    for key in ("id", "chat_id", "user_id", "name", "created_at"):
        if not isinstance(document.get(key), str):
            raise CheckpointError(f"checkpoint {checkpoint_id!r} has a missing or invalid {key!r}")
    message_count = document.get("message_count")
    if not isinstance(message_count, int) or isinstance(message_count, bool):
        raise CheckpointError(
            f"checkpoint {checkpoint_id!r} has a missing or invalid 'message_count'"
        )
    chat_doc = document.get("chat")
    messages = document.get("messages")
    if not isinstance(chat_doc, dict):
        raise CheckpointError(f"checkpoint {checkpoint_id!r} has a missing or invalid 'chat'")
    if not isinstance(messages, list):
        raise CheckpointError(f"checkpoint {checkpoint_id!r} has a missing or invalid 'messages'")
    if (
        document["id"] != checkpoint_id
        or document["chat_id"] != chat_id
        or document["user_id"] != user_id
    ):
        raise CheckpointError(
            f"checkpoint {checkpoint_id!r} identity mismatch: the document does not "
            "belong to this chat and owner"
        )
    for message in messages:
        if not isinstance(message, dict):
            raise CheckpointError(f"checkpoint {checkpoint_id!r} holds a non-object message")
        if "chat_id" in message and message["chat_id"] != chat_doc.get("id"):
            raise CheckpointError(f"checkpoint {checkpoint_id!r} holds a foreign message")
    if message_count != len(messages):
        raise CheckpointError(
            f"checkpoint {checkpoint_id!r} message_count {message_count} "
            f"!= {len(messages)} stored messages"
        )
    expected = _checksum({"chat": chat_doc, "messages": messages})
    if document.get("checksum") != expected:
        raise CheckpointError(f"checkpoint {checkpoint_id!r} checksum mismatch")
    return document


async def _history(session: AsyncSession, chat_id: str) -> list[Message]:
    """The chat's history in archive order (``created_at``, ``id``):
    deterministic even on timestamp ties, because payload
    determinism is what the checksum seals."""
    result = await session.execute(
        select(Message)
        .where(Message.chat_id == chat_id)
        .order_by(Message.created_at, Message.id)
    )
    return list(result.scalars().all())


async def create_checkpoint(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    name: str | None = None,
    *,
    base_dir: Path | None = None,
) -> dict | None:
    """Snapshot a chat as a named checkpoint (P-067).

    Returns the checkpoint metadata, or None when the chat is
    missing or foreign. An explicitly blank name raises ValueError;
    with no name, the checkpoint takes the timestamp default. An
    empty chat is legal (``message_count == 0``). The
    ``checkpoint.created`` event is recorded only after the file is
    durably in place -- the log must never claim a checkpoint the
    disk does not have.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    cleaned = _clean_name(name)
    history = await _history(session, chat_id)
    created_at = datetime.now(UTC)
    chat_doc = row_to_dict(chat)
    message_docs = [row_to_dict(message) for message in history]
    document = {
        "format": FORMAT_NAME,
        "format_version": FORMAT_VERSION,
        "id": str(uuid.uuid4()),
        "chat_id": chat_id,
        "user_id": user_id,
        "name": cleaned if cleaned is not None else _default_name(created_at),
        "created_at": created_at.isoformat(),
        "message_count": len(message_docs),
        "chat": chat_doc,
        "messages": message_docs,
        "checksum": _checksum({"chat": chat_doc, "messages": message_docs}),
    }
    _write_checkpoint_file(
        _checkpoint_path(user_id, chat_id, document["id"], base_dir), document
    )
    await _record_event(
        session,
        chat.id,
        EVENT_CHECKPOINT_CREATED,
        data={
            "checkpoint_id": document["id"],
            "name": document["name"],
            "message_count": len(message_docs),
        },
    )
    await session.commit()
    return checkpoint_to_dict(document)


async def list_checkpoints(
    session: AsyncSession, user_id: str, chat_id: str, *, base_dir: Path | None = None
) -> list[dict] | None:
    """All checkpoints of a chat, oldest first (``created_at``, then
    id). Returns None when the chat is missing or foreign; a chat
    with no checkpoint directory yet returns ``[]``.

    Listing reads metadata only and does NOT verify checksums (it
    is an index, not a restore), but it does validate the envelope
    enough to project: a file that does not parse as a checkpoint
    document raises CheckpointError -- a corrupt checkpoint is
    surfaced loudly, never silently dropped from the list.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    directory = _chat_checkpoint_dir(user_id, chat_id, base_dir)
    if not directory.is_dir():
        return []
    metas: list[dict] = []
    for path in sorted(directory.glob("*.json")):
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise CheckpointError(f"checkpoint file {path.name!r} is unreadable: {exc}") from exc
        if not isinstance(document, dict):
            raise CheckpointError(f"checkpoint file {path.name!r} is not a JSON object")
        try:
            metas.append(checkpoint_to_dict(document))
        except (KeyError, TypeError) as exc:
            raise CheckpointError(
                f"checkpoint file {path.name!r} does not match the checkpoint schema: {exc}"
            ) from exc
    metas.sort(key=lambda meta: (str(meta["created_at"]), str(meta["id"])))
    return metas


async def get_checkpoint(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    checkpoint_id: str,
    *,
    base_dir: Path | None = None,
) -> dict | None:
    """One checkpoint's metadata -- a VERIFIED read: the checksum
    and identity binding are checked, so a tampered file raises
    CheckpointError here, not only at restore. Returns None when
    the chat or the checkpoint is missing; a malformed checkpoint
    id raises ValueError."""
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    document = _load_verified_checkpoint(user_id, chat_id, checkpoint_id, base_dir=base_dir)
    if document is None:
        return None
    return checkpoint_to_dict(document)


def _restore_title(chat_doc: dict, checkpoint_name: str, name: str | None) -> str:
    if name is not None:
        return name
    source_title = chat_doc.get("title") or "Untitled chat"
    return f"{source_title} (checkpoint: {checkpoint_name})"


def _spawn_from_payload(chat_payload: dict, user_id: str, title: str) -> Chat:
    """A new standalone chat carrying the PAYLOAD chat's settings --
    the settings as they were when the checkpoint was taken, not
    the live chat's possibly-changed ones. Exactly six fields are
    carried (the ``branches._spawn_chat`` list PLUS
    ``swipe_settings_json``); ``group_id`` is NOT carried (a
    restored chat is not the group's room) and branch lineage is
    NOT carried (the new chat takes the root defaults). A missing
    ``*_json`` field defaults to ``"{}"`` -- forward tolerance for
    payloads written before a settings column existed."""
    return Chat(
        user_id=user_id,
        title=title,
        character_id=chat_payload.get("character_id"),
        preset_id=chat_payload.get("preset_id"),
        backend_profile_id=chat_payload.get("backend_profile_id"),
        authors_note_json=chat_payload.get("authors_note_json") or "{}",
        post_history_json=chat_payload.get("post_history_json") or "{}",
        swipe_settings_json=chat_payload.get("swipe_settings_json") or "{}",
    )


async def restore_checkpoint(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    checkpoint_id: str,
    name: str | None = None,
    *,
    base_dir: Path | None = None,
) -> Chat | None:
    """Return to a checkpoint (P-067): RESTORE-AS-NEW.

    Creates a NEW chat from the snapshot (see ``_spawn_from_payload``)
    holding fresh copies of the snapshot's messages -- fresh ids,
    original timestamps, full swipe decks -- and returns it,
    committed, with a ``checkpoint.restored`` event on BOTH chats.
    The source chat is never mutated. Returns None when the chat
    or checkpoint is missing; a blank explicit name raises
    ValueError; a corrupt, tampered, or foreign payload raises
    CheckpointError BEFORE any row is added, so no partial chat
    can survive a refused restore.
    """
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    cleaned = _clean_name(name)
    document = _load_verified_checkpoint(user_id, chat_id, checkpoint_id, base_dir=base_dir)
    if document is None:
        return None
    chat_doc = document["chat"]
    restored = _spawn_from_payload(
        chat_doc, user_id, _restore_title(chat_doc, document["name"], cleaned)
    )
    session.add(restored)
    await session.flush()
    for payload in document["messages"]:
        rebuilt = dict(payload)
        rebuilt["id"] = str(uuid.uuid4())
        rebuilt["chat_id"] = restored.id
        session.add(_row(Message, rebuilt))
    await session.flush()
    await _record_event(
        session,
        chat.id,
        EVENT_CHECKPOINT_RESTORED,
        data={
            "checkpoint_id": checkpoint_id,
            "name": document["name"],
            "restored_chat_id": restored.id,
        },
    )
    await _record_event(
        session,
        restored.id,
        EVENT_CHECKPOINT_RESTORED,
        data={
            "source_chat_id": chat.id,
            "checkpoint_id": checkpoint_id,
            "name": document["name"],
            "restored_messages": len(document["messages"]),
        },
    )
    await session.commit()
    return restored


async def delete_checkpoint(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    checkpoint_id: str,
    *,
    base_dir: Path | None = None,
) -> bool | None:
    """Delete one checkpoint file. Returns None when the chat is
    missing or foreign, False when the checkpoint file is absent,
    and True once deleted. A malformed id raises ValueError. Only
    that one file is removed; no event is recorded and no checksum
    is verified -- deletion must stay possible even for a corrupt
    file, and the chat's event log is not owed a note about a file
    it can no longer reach (a pinned decision)."""
    chat = await _get_owned_chat(session, user_id, chat_id)
    if chat is None:
        return None
    _validate_checkpoint_id(checkpoint_id)
    path = _checkpoint_path(user_id, chat_id, checkpoint_id, base_dir)
    if not path.is_file():
        return False
    path.unlink()
    return True


def remove_chat_checkpoints(user_id: str, chat_id: str, *, base_dir: Path | None = None) -> bool:
    """Remove a chat's whole checkpoint directory (best-effort,
    ``shutil.rmtree(..., ignore_errors=True)`` semantics): when a
    chat is deleted, its checkpoints die with it -- a checkpoint
    never outlives its chat as a restorable object, while chats
    RESTORED from those checkpoints are independent and untouched.
    Returns True when the directory is absent afterwards
    (including "never existed"), False if it survives. Synchronous
    and session-free; never raises for a missing directory. The
    ``service.delete_chat`` wiring is a separate change."""
    if not (
        _CHECKPOINT_ID_RE.fullmatch(user_id or "")
        and _CHECKPOINT_ID_RE.fullmatch(chat_id or "")
    ):
        return False
    directory = _chat_checkpoint_dir(user_id, chat_id, base_dir)
    if directory.exists():
        shutil.rmtree(directory, ignore_errors=True)
    return not directory.exists()
