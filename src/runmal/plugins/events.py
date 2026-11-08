"""Chat and generation events, plugin side (P-081, design section 3).

Fire-and-observe: a :class:`PluginEvent` is dispatched to ENABLED
plugins only AFTER the host operation has committed, handler
failures are recorded by the registry and never raised through the
host path (PLG-01), and generation events carry metadata only,
never prompt or message text (PLG-05).

The event-name constants below DUPLICATE the string values of the
S107 ``chats/service.py`` ``EVENT_*`` constants on purpose: this
module must not import ``chats.service`` (the pinning test asserts
the overlap equals those values, voice-adapter pinning style, and
importing here would invite a cycle). One name is deliberately NOT
a duplicate: the plugin name ``message.created`` corresponds to
the S107 log's ``EVENT_MESSAGE_APPENDED`` (``"message.appended"``)
-- the mapping is stated here, in :data:`PLUGIN_EVENT_S107_VALUES`,
and pinned by test. ``chat.deleted`` and the ``generation.*``
names have no S107 value at all: a deleted chat leaves no row in
the S107 log, and generation events come from the generation
service, not the chat event log.

The content rule is a payload-construction property, never a
handler promise: message text rides in a payload ONLY for a
receiving plugin whose manifest declares the ``chat.read``
permission; every other receiver gets ``content_chars`` (the
length) and no text. :func:`message_payload` builds a payload
under the rule directly; :func:`payload_for_receiver` applies the
rule to an already-built payload, per receiver, which is how the
dispatcher personalises one event for plugins with different
grants.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime

from runmal.plugins.api import PLUGIN_API_VERSION, PLUGIN_EVENTS

# Event names (section 3 catalogue). Values duplicate the S107
# chats/service.py EVENT_* values where those exist -- see the
# module docstring for the one stated exception.
EVENT_CHAT_CREATED = "chat.created"  # EVENT_CHAT_CREATED
EVENT_CHAT_RENAMED = "chat.renamed"  # EVENT_CHAT_RENAMED
EVENT_CHAT_DELETED = "chat.deleted"  # new dispatch point; no S107 row
EVENT_MESSAGE_CREATED = "message.created"  # S107: EVENT_MESSAGE_APPENDED
EVENT_MESSAGE_EDITED = "message.edited"  # EVENT_MESSAGE_EDITED
EVENT_MESSAGE_DELETED = "message.deleted"  # EVENT_MESSAGE_DELETED
EVENT_MESSAGE_SWIPE_SELECTED = "message.swipe_selected"  # EVENT_MESSAGE_SWIPE_SELECTED
EVENT_GENERATION_BEFORE = "generation.before"  # generation/service seam
EVENT_GENERATION_AFTER = "generation.after"  # generation/service seam
EVENT_GENERATION_FAILED = "generation.failed"  # generation/service seam

#: Plugin event name -> the S107 ``EVENT_*`` string value it
#: corresponds to, or None where the S107 chat log has no such
#: value (chat.deleted, generation.*). Stated here so the mapping
#: -- above all message.created -> "message.appended" -- is data
#: the pinning test can assert, not folklore.
PLUGIN_EVENT_S107_VALUES: dict[str, str | None] = {
    EVENT_CHAT_CREATED: "chat.created",
    EVENT_CHAT_RENAMED: "chat.renamed",
    EVENT_CHAT_DELETED: None,
    EVENT_MESSAGE_CREATED: "message.appended",
    EVENT_MESSAGE_EDITED: "message.edited",
    EVENT_MESSAGE_DELETED: "message.deleted",
    EVENT_MESSAGE_SWIPE_SELECTED: "message.swipe_selected",
    EVENT_GENERATION_BEFORE: None,
    EVENT_GENERATION_AFTER: None,
    EVENT_GENERATION_FAILED: None,
}

#: The permission that lets message text ride in a payload.
CHAT_READ_PERMISSION = "chat.read"


@dataclass(frozen=True)
class PluginEvent:
    """One dispatched event, as a receiving handler sees it.

    ``occurred_at`` is an aware UTC datetime; ``api_version`` is
    :data:`PLUGIN_API_VERSION` at dispatch. ``data`` is the
    per-receiver payload, already redacted for that receiver by
    the payload builders below.
    """

    name: str
    api_version: int = PLUGIN_API_VERSION
    occurred_at: datetime = field(
        default_factory=lambda: datetime.now(UTC)
    )
    chat_id: str | None = None
    message_id: str | None = None
    data: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.name not in PLUGIN_EVENTS:
            raise ValueError(f"unknown plugin event: {self.name!r}")
        if self.occurred_at.tzinfo is None:
            raise ValueError("plugin event occurred_at must be timezone-aware")

    def to_dict(self) -> dict:
        """Plain JSON shapes; the timestamp renders ISO 8601."""
        return {
            "name": self.name,
            "api_version": self.api_version,
            "occurred_at": self.occurred_at.isoformat(),
            "chat_id": self.chat_id,
            "message_id": self.message_id,
            "data": dict(self.data),
        }


def make_event(
    name: str,
    *,
    chat_id: str | None = None,
    message_id: str | None = None,
    data: Mapping | None = None,
    occurred_at: datetime | None = None,
) -> PluginEvent:
    """Build a :class:`PluginEvent` stamped with the current API version."""
    return PluginEvent(
        name=name,
        api_version=PLUGIN_API_VERSION,
        occurred_at=(
            occurred_at
            if occurred_at is not None
            else datetime.now(UTC)
        ),
        chat_id=chat_id,
        message_id=message_id,
        data=dict(data) if data is not None else {},
    )


def message_payload(
    *,
    chat_id: str,
    message_id: str,
    role: str,
    content: str,
    permissions: Iterable[str],
) -> dict:
    """The ``message.created`` / ``message.edited`` payload for ONE receiver.

    ``content_chars`` is always present. ``content`` (the message
    text itself) is present only when the receiving plugin's
    manifest declares the ``chat.read`` permission -- the section 3
    redaction rule, applied here at construction time.
    """
    payload: dict = {
        "chat_id": chat_id,
        "message_id": message_id,
        "role": role,
        "content_chars": len(content),
    }
    if CHAT_READ_PERMISSION in permissions:
        payload["content"] = content
    return payload


def payload_for_receiver(
    data: Mapping, *, permissions: Iterable[str]
) -> dict:
    """A per-receiver copy of a built payload, redaction applied.

    If the payload carries message text under ``content``, the
    copy keeps ``content_chars`` (filling it from the text when
    absent) and drops the text itself unless the receiver declares
    ``chat.read``. Payloads without text pass through unchanged
    (as a fresh dict, so handlers can never mutate shared state).
    """
    out = dict(data)
    content = out.get("content")
    if isinstance(content, str):
        out.setdefault("content_chars", len(content))
        if CHAT_READ_PERMISSION not in permissions:
            del out["content"]
    return out


def chat_created_payload(
    *, chat_id: str, character_id: str | None, title: str
) -> dict:
    return {"chat_id": chat_id, "character_id": character_id, "title": title}


def chat_renamed_payload(*, chat_id: str, title: str) -> dict:
    return {"chat_id": chat_id, "title": title}


def chat_deleted_payload(*, chat_id: str) -> dict:
    return {"chat_id": chat_id}


def message_deleted_payload(*, chat_id: str, message_id: str) -> dict:
    return {"chat_id": chat_id, "message_id": message_id}


def swipe_selected_payload(
    *, chat_id: str, message_id: str, swipe_id: str
) -> dict:
    return {"chat_id": chat_id, "message_id": message_id, "swipe_id": swipe_id}


def generation_before_payload(
    *,
    request_id: str,
    backend_key: str,
    model_id: str | None,
    chat_id: str | None,
    message_count: int,
) -> dict:
    """Metadata only (PLG-05): counts and ids, never message text."""
    return {
        "request_id": request_id,
        "backend_key": backend_key,
        "model_id": model_id,
        "chat_id": chat_id,
        "message_count": message_count,
    }


def generation_after_payload(
    *,
    request_id: str,
    backend_key: str,
    finish_reason: str,
    usage: dict | None,
) -> dict:
    return {
        "request_id": request_id,
        "backend_key": backend_key,
        "finish_reason": finish_reason,
        "usage": usage,
    }


def generation_failed_payload(
    *,
    request_id: str,
    backend_key: str,
    error_code: str,
    retryable: bool,
) -> dict:
    return {
        "request_id": request_id,
        "backend_key": backend_key,
        "error_code": error_code,
        "retryable": retryable,
    }
