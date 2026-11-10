"""Inspector reasoning document (P-210): one read-only
document per owned chat answering "which reasoning
records exist for this chat's messages, in what state,
and where the thinking itself can be read" - composed
from the banked P-205 reasoning record.

The record itself is banked: every producing road was
wired by P-209, the per-message raw road
(GET /chats/{chat_id}/messages/{message_id}/reasoning)
already serves every swipe's record verbatim, and the
Assistant View (P-206) renders the active view. What
Part XIII lacked was the Inspector's read of it: the
P-203 overview joins provenance, prompts and lore, and
the P-204 events document joins the S107 log, but an
owner debugging "why does this reply have no thinking"
had to leave the Inspector and query message by
message. This service joins the record into ONE
schema-versioned census document by CALLING the banked
chats-service read (runmal.chats.service
list_chat_reasoning, the reasoning twin of
list_chat_provenance); it never re-implements that read
and never opens a second query path (the P-059
one-source-of-truth rule, generalised, as P-203 and
P-204 applied it). All parsing stays in
runmal.chats.reasoning's tolerant readers.

No-text law (the P-204 no-payload discipline, applied
to the one content-class record): the document carries
NO thinking text and NO message content anywhere -
statuses, counts, timestamps and pointers only. The
thinking itself stays on the banked raw road, which
every per-message entry points at (``raw_road``).

Honesty law (the P-075 idiom, transposed):

- the coverage section carries a status from the closed
  pair available / empty: empty when the chat has no
  messages; a chat whose messages all read not_recorded
  is AVAILABLE - the census is the fact, honestly
  reported;
- two count families are carried precisely so they are
  never confused: ``active_by_status`` counts each
  message's ACTIVE swipe view (a fact about the chat's
  current active swipes - it moves when the active
  swipe changes), while ``swipes_by_status`` counts
  EVERY swipe record in every message's full document
  (the stable all-documents census);
- ``swipes_total`` counts swipe records present in the
  stored documents; a swipe whose record was never
  written into the document (legacy rows predating
  0042 default ``"{}"``) surfaces through its message's
  active not_recorded / unknown status, not as a
  phantom swipe row;
- malformed stored reasoning censuses as ``unknown``
  through the banked tolerant readers - joined, never
  re-implemented, never an exception on this road.

Coverage is the chats store only: groupchat transcripts
live in the separate groupchat store (P-208 landed
their records there), so group reasoning is NOT in this
census; a group join would be its own document if ever
commissioned.

Read-only: nothing is persisted, cached or written; the
document is assembled fresh from the banked truth on
each call.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.chats import service as chats_service
from runmal.inspector import REASONING_SCHEMA

__all__ = [
    "COVERAGE_STATUSES",
    "STATUSES",
    "build_reasoning_document",
    "summarise_reasoning",
]

#: The closed reasoning-status vocabulary (P-205), in the
#: fixed order both count families are zero-filled in.
STATUSES = ("recorded", "not_present", "not_recorded", "unknown")

#: The closed coverage-status vocabulary for this
#: document: a census over an existing chat is either
#: available or honestly empty.
COVERAGE_STATUSES = frozenset({"available", "empty"})


def _empty_counts() -> dict:
    return {status: 0 for status in STATUSES}


def _recorded_indexes(full: dict) -> list[int]:
    """The swipe indexes whose stored record is recorded,
    in document order - the recorded swipe indexes known
    to the document."""
    return sorted(
        int(index)
        for index, record in full["swipes"].items()
        if record.get("status") == "recorded"
    )


def summarise_reasoning(messages) -> dict:
    """Aggregate the service read's per-message views into
    the chat-level census. Pure. Counts and statuses
    only - no text, no content.

    ``active_by_status`` counts each message's ACTIVE
    view; ``swipes_by_status`` counts every swipe record
    in every full document. Both families carry all four
    statuses, zero-filled."""
    active_by_status = _empty_counts()
    swipes_by_status = _empty_counts()
    messages_with_recorded = 0
    swipes_total = 0
    swipes_recorded = 0
    for entry in messages:
        active = entry["active"]
        full = entry["full"]
        active_by_status[active["reasoning_status"]] += 1
        if full["recorded"]:
            messages_with_recorded += 1
        swipes_total += len(full["swipes"])
        swipes_recorded += len(_recorded_indexes(full))
        for record in full["swipes"].values():
            swipes_by_status[record["status"]] += 1
    return {
        "messages_total": len(messages),
        "active_by_status": active_by_status,
        "messages_with_recorded": messages_with_recorded,
        "swipes_total": swipes_total,
        "swipes_recorded": swipes_recorded,
        "swipes_by_status": swipes_by_status,
    }


def _message_entry(chat_id: str, entry: dict) -> dict:
    """One message's census row: the active view's status,
    the full document's recorded bool and timestamp, the
    recorded swipe indexes, and the pointer at the banked
    raw road where the thinking itself lives."""
    active = entry["active"]
    full = entry["full"]
    message_id = entry["message_id"]
    return {
        "message_id": message_id,
        "role": entry["role"],
        "active_status": active["reasoning_status"],
        "recorded": full["recorded"],
        "recorded_at": full["recorded_at"],
        "swipes_recorded": _recorded_indexes(full),
        "raw_road": f"/chats/{chat_id}/messages/{message_id}/reasoning",
    }


async def build_reasoning_document(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
) -> dict | None:
    """The Inspector reasoning document for one owned chat.

    Returns None when the chat is missing or foreign (the
    router maps that to the house 404 idiom; existence
    never leaks). Pure read: the census is composed by
    CALLING the banked chats-service list_chat_reasoning
    read and persists nothing.
    """
    payload = await chats_service.list_chat_reasoning(
        session, user_id, chat_id
    )
    if payload is None:
        return None
    messages = payload["messages"]
    if messages:
        coverage = {"status": "available", "reason": None}
    else:
        coverage = {
            "status": "empty",
            "reason": (
                "the chat has no messages, so no reasoning "
                "records exist to census"
            ),
        }
    return {
        "schema": REASONING_SCHEMA,
        "chat_id": chat_id,
        "coverage": coverage,
        "summary": summarise_reasoning(messages),
        "messages": [
            _message_entry(chat_id, entry) for entry in messages
        ],
    }
