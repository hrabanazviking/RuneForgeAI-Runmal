"""Bridge from imported chat files to the live service shape (P-020).

This module is glue only: it projects an `ImportedChat` (the
file contract in `.filemodels`) into the plain-dict shapes the
live chat service consumes, reports what that projection loses,
compares two imported chats field by field, and resolves a
chat's character by exact name. It imports ONLY `.filemodels`,
takes and returns plain values, and never imports
`chats.service`, so it can be used by importers, exporters and
tests without a cycle.

Clean-room basis: shapes from P-002's census of public
documentation, P-005's authored corpus fixture, and public
JSONL format documentation. No mirror source code was read.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .filemodels import ImportedChat, ImportedMessage

__all__ = [
    "field_diff",
    "loss_report",
    "project_messages",
    "resolve_character",
    "to_service_document",
]


def project_messages(chat: ImportedChat) -> list[dict]:
    """Project messages to the live shape: role/content/speaker_name.

    `content` is `message.content` (the line's `mes`) and is
    authoritative: on a MES_SWIPE_MISMATCH line the active
    swipe text differs, and the `mes` text wins here.
    """
    return [
        {
            "role": message.role,
            "content": message.content,
            "speaker_name": message.speaker_name,
        }
        for message in chat.messages
    ]


def to_service_document(chat: ImportedChat, *, exported_at: str) -> dict:
    """Build the S111 native export document for an imported chat.

    `exported_at` is a required caller-supplied ISO string;
    this module never calls a clock.
    """
    return {
        "format": "runmal-chat-export",
        "version": 1,
        "exported_at": exported_at,
        "chat": {
            "title": "",
            "character_id": None,
            "character_name": chat.character_name,
            "user_name": chat.user_name,
        },
        "messages": project_messages(chat),
    }


def loss_report(chat: ImportedChat) -> list[str]:
    """Human strings, one per datum the live projection cannot hold.

    Empty list when nothing is lost.
    """
    losses: list[str] = []
    for key in sorted(chat.chat_metadata):
        losses.append(
            f"chat_metadata key {key!r} has no live-projection column"
        )
    for key in sorted(chat.branch_link):
        losses.append(
            f"branch linkage key {key!r} has no live-projection column"
        )
    for index, message in enumerate(chat.messages):
        if len(message.swipes) > 1:
            alternates = len(message.swipes) - 1
            losses.append(
                f"messages[{index}]: {alternates} alternate swipe(s) "
                "beyond the active one cannot be held by the live projection"
            )
        if message.extra:
            keys = ", ".join(sorted(str(k) for k in message.extra))
            losses.append(
                f"messages[{index}]: extra provenance present "
                f"(keys: {keys}) cannot be held by the live projection"
            )
        if message.send_date_raw is not None or "send_date" in message.raw:
            losses.append(
                f"messages[{index}]: send_date present with no "
                "full-fidelity live column"
            )
        if message.content == "":
            losses.append(
                f"messages[{index}]: empty content would be refused "
                "by live append_message"
            )
    return losses


def _diff_into(a: Any, b: Any, path: str, out: list[str]) -> None:
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b), key=str):
            child = f"{path}.{key}" if path else str(key)
            if key not in a or key not in b:
                out.append(child)
            else:
                _diff_into(a[key], b[key], child, out)
        return
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            out.append(path)
        for index in range(min(len(a), len(b))):
            _diff_into(a[index], b[index], f"{path}[{index}]", out)
        return
    if a != b:
        out.append(path)


def _message_value(message: ImportedMessage) -> dict:
    return {
        "role": message.role,
        "content": message.content,
        "speaker_name": message.speaker_name,
        "is_system": message.is_system,
        "send_date_raw": message.send_date_raw,
        "send_date_parsed": message.send_date_parsed,
        "swipes": message.swipes,
        "swipe_id": message.swipe_id,
        "has_explicit_swipes": message.has_explicit_swipes,
        "swipe_info": message.swipe_info,
        "has_swipe_info": message.has_swipe_info,
        "extra": message.extra,
        "raw": message.raw,
    }


def field_diff(a: ImportedChat, b: ImportedChat) -> list[str]:
    """Dotted paths of every field that differs between two chats.

    Compares the typed fields AND `header_raw` / per-message
    `raw` recursively. An empty list means field-clean.
    """
    out: list[str] = []
    _diff_into(a.user_name, b.user_name, "user_name", out)
    _diff_into(a.character_name, b.character_name, "character_name", out)
    _diff_into(a.create_date_raw, b.create_date_raw, "create_date_raw", out)
    _diff_into(a.create_date_parsed, b.create_date_parsed, "create_date_parsed", out)
    _diff_into(a.chat_metadata, b.chat_metadata, "chat_metadata", out)
    _diff_into(a.header_raw, b.header_raw, "header", out)
    _diff_into(a.source_shape, b.source_shape, "source_shape", out)
    if len(a.messages) != len(b.messages):
        out.append("messages")
    for index in range(min(len(a.messages), len(b.messages))):
        _diff_into(
            _message_value(a.messages[index]),
            _message_value(b.messages[index]),
            f"messages[{index}]",
            out,
        )
    return out


def resolve_character(chat: ImportedChat, by_name: Mapping[str, str]) -> str | None:
    """Exact-name lookup of `chat.character_name`; None if absent.

    Never guesses and performs no I/O.
    """
    return by_name.get(chat.character_name)
