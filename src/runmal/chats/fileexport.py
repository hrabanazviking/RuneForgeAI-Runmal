"""Chat file export (P-020): ST-shaped chat JSONL out.

Clean-room basis: the exchanged shape is as recorded in P-002's
census from SillyTavern's official public documentation and as
carried by P-005's authored corpus fixture
(`tests/fixtures/interop/chat_st.jsonl`). No mirror source code
was read.

Export is a raw overlay: each emitted line starts from a deep copy
of the line's `raw` mapping (INV-009 — unknown-but-valid fields
survive verbatim, in their original key position) and overlays the
normalized known fields under the write rules below. Nothing is
fabricated: a field the source line did not carry, and the typed
record does not carry either, is not invented on export. The one
deliberate exception to verbatim raw is a repaired `swipes` array:
non-string members dropped at import stay dropped, so the typed
array overlays raw's — and the second export is the fixed point.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime

from .filemodels import ImportedChat, ImportedMessage


def _format_st_datetime_ms(value: datetime) -> str:
    """ST date spelling with milliseconds: `2026-10-01 @20h 00m 00s 000ms`."""
    return (
        f"{value.year:04d}-{value.month:02d}-{value.day:02d} "
        f"@{value.hour:02d}h {value.minute:02d}m {value.second:02d}s "
        f"{value.microsecond // 1000:03d}ms"
    )


def _header_create_date(chat: ImportedChat, raw_value: object) -> object:
    """The `create_date` value to write for a header that carried one.

    A string date rides back verbatim through `create_date_raw`. A
    numeric epoch is the one sanctioned reformatting: the parsed
    datetime is written in ST-with-ms form. Anything else keeps
    raw's original value.
    """
    if isinstance(raw_value, bool):
        return copy.deepcopy(raw_value)
    if isinstance(raw_value, (int, float)) and chat.create_date_parsed is not None:
        return _format_st_datetime_ms(chat.create_date_parsed)
    if chat.create_date_raw is not None:
        return chat.create_date_raw
    return copy.deepcopy(raw_value)


def _header_object(chat: ImportedChat) -> dict | None:
    """The header line object, or None when the chat has no header.

    Overlays run in the order user_name, character_name,
    create_date, chat_metadata so keys the raw header did not carry
    append in that fixed order; keys it did carry keep position.
    """
    raw = chat.header_raw
    if raw:
        obj: dict = copy.deepcopy(raw)
        if "user_name" in raw or chat.user_name != "":
            obj["user_name"] = chat.user_name
        if "character_name" in raw or chat.character_name != "":
            obj["character_name"] = chat.character_name
        if "create_date" in raw:
            obj["create_date"] = _header_create_date(chat, raw["create_date"])
        if "chat_metadata" in raw or chat.chat_metadata:
            obj["chat_metadata"] = copy.deepcopy(chat.chat_metadata)
        return obj
    # No raw header (a natively built chat): synthesize a header
    # only from fields the chat actually carries — a chat that
    # carries nothing gets no header line, and `create_date` is
    # included only when `create_date_raw` is set, never fabricated.
    if not (
        chat.user_name
        or chat.character_name
        or chat.chat_metadata
        or chat.create_date_raw is not None
    ):
        return None
    obj = {}
    if chat.user_name != "":
        obj["user_name"] = chat.user_name
    if chat.character_name != "":
        obj["character_name"] = chat.character_name
    if chat.create_date_raw is not None:
        obj["create_date"] = chat.create_date_raw
    if chat.chat_metadata:
        obj["chat_metadata"] = copy.deepcopy(chat.chat_metadata)
    return obj


def _message_object(message: ImportedMessage) -> dict:
    """One message line: raw overlaid with the normalized fields.

    Overlays run in the fixed order name, is_user, is_system,
    send_date, mes, extra, swipes, swipe_id, swipe_info so keys the
    raw line did not carry append deterministically; keys it did
    carry keep their raw position.
    """
    raw = message.raw
    obj: dict = copy.deepcopy(raw)
    if "name" in raw or message.speaker_name != "":
        obj["name"] = message.speaker_name
    obj["is_user"] = message.role == "user"
    if "is_system" in raw or message.is_system:
        obj["is_system"] = message.is_system
    if message.send_date_raw is not None:
        # A numeric raw `send_date` leaves `send_date_raw` None at
        # import, so raw's numeric value rides through untouched.
        obj["send_date"] = message.send_date_raw
    obj["mes"] = message.content
    if "extra" in raw:
        if isinstance(raw["extra"], dict):
            obj["extra"] = copy.deepcopy(message.extra)
        # A non-dict `extra` cannot be represented in the typed
        # record; raw's value is the only faithful copy and the
        # deepcopy above already carries it — leave it untouched.
    elif message.extra:
        obj["extra"] = copy.deepcopy(message.extra)
    if message.has_explicit_swipes or len(message.swipes) > 1 or message.swipe_id != 0:
        obj["swipes"] = copy.deepcopy(message.swipes)
        obj["swipe_id"] = message.swipe_id
    if message.has_swipe_info:
        obj["swipe_info"] = copy.deepcopy(message.swipe_info)
    return obj


def export_chat_jsonl(chat: ImportedChat) -> bytes:
    """Export an ImportedChat as ST-shaped chat JSONL bytes.

    Header line first when the chat has one, then one JSON object
    per message, `json.dumps(..., ensure_ascii=False)` with default
    separators, "\\n" line endings and exactly one trailing "\\n".
    Exporting the re-import of an export reproduces the export
    byte-for-byte.
    """
    lines: list[str] = []
    header = _header_object(chat)
    if header is not None:
        lines.append(json.dumps(header, ensure_ascii=False))
    for message in chat.messages:
        lines.append(json.dumps(_message_object(message), ensure_ascii=False))
    return "".join(f"{line}\n" for line in lines).encode("utf-8")
