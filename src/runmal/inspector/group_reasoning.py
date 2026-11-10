"""Inspector group reasoning document (P-211): one
read-only document per owned group answering "which
reasoning records exist for this group's transcript
messages, in what state, who produced them, and where
the thinking itself can be read" - composed from the
banked P-205 reasoning record as landed in the
groupchat store by P-208.

P-210 joined the record into the Inspector for
one-to-one chats and stated its own first carried
limitation plainly: chats-store coverage only -
groupchat transcripts live in the separate groupchat
store, so group reasoning was NOT in that census, and
a group join would be its own document if ever
commissioned. This service is that document. It joins
the record into ONE schema-versioned census by CALLING
the new groupchat-store read (runmal.groupchat.store
list_group_reasoning, mirroring the banked
list_chat_reasoning in shape) and the banked
summarise_reasoning from runmal.inspector.reasoning
UNCHANGED; it never re-implements either and never
opens a second query path (the P-059
one-source-of-truth rule, generalised a fourth time,
as P-203, P-204 and P-210 applied it). All parsing
stays in runmal.chats.reasoning's tolerant readers.

The group-native fact this census adds is speaker
identity: every per-message entry carries the
speaker_id / speaker_name the transcript itself
serves, and a per-speaker roll-up aggregates each
distinct speaker's active-view counts in
first-appearance transcript order. User and manual
turns carry whatever speaker identity the store itself
serves (null where the store serves null) - carried
verbatim, never invented.

No-text law (the P-204 no-payload discipline, as
P-210 applied it): the document carries NO thinking
text and NO message content anywhere - statuses,
counts, timestamps, speaker identity and pointers
only. The thinking itself stays on the banked group
transcript road (GET /groups/{group_id}/messages,
whose message_to_dict serves each message's active
reasoning view, text included when recorded), which
the document's single raw_road pointer names.
Deliberate divergence from P-210's per-message
raw_road, stated plainly: no per-message group
reasoning road exists, and fabricating per-message
pointers at a road that does not exist would be a
false pointer; the transcript road is the banked
surface that actually serves the text.

Honesty law (the P-210 idiom, transposed):

- the coverage section carries a status from the
  closed pair available / empty: empty when the
  transcript has no messages; a transcript whose
  messages all read not_recorded is AVAILABLE - the
  census is the fact, honestly reported;
- the summary is EXACTLY the P-210 summary shape,
  produced by the banked summarise_reasoning: two
  count families carried precisely so they are never
  confused - active counts per message over ACTIVE
  views (they move when an active swipe changes) and
  swipe counts over EVERY swipe record in every full
  document (stable);
- malformed stored reasoning censuses as unknown
  through the banked tolerant readers - joined, never
  re-implemented, never an exception on this road.

Read-only: nothing is persisted, cached or written;
the document is assembled fresh from the banked truth
on each call.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.groupchat import store as group_store
from runmal.inspector import GROUP_REASONING_SCHEMA
from runmal.inspector.reasoning import STATUSES, summarise_reasoning

__all__ = [
    "COVERAGE_STATUSES",
    "build_group_reasoning_document",
    "summarise_speakers",
]

#: The closed coverage-status vocabulary for this
#: document: a census over an existing group is either
#: available or honestly empty (the P-210 pair).
COVERAGE_STATUSES = frozenset({"available", "empty"})


def _empty_counts() -> dict:
    return {status: 0 for status in STATUSES}


def _recorded_indexes(full: dict) -> list[int]:
    """The swipe indexes whose stored record is recorded,
    in document order - mirroring the P-210 helper of
    the same name in runmal.inspector.reasoning."""
    return sorted(
        int(index)
        for index, record in full["swipes"].items()
        if record.get("status") == "recorded"
    )


def summarise_speakers(messages) -> list[dict]:
    """Aggregate the store read's per-message views into
    the per-speaker roll-up. Pure. One entry per
    distinct speaker, in first-appearance transcript
    order, keyed by the (speaker_id, speaker_name)
    pair the store itself serves - carried verbatim,
    never invented. Counts are over ACTIVE views only,
    in the P-210 census vocabulary: each speaker's
    messages_total, active_by_status (all four
    statuses, zero-filled) and messages_with_recorded
    (the full document's recorded bool). Counts and
    statuses only - no text, no content."""
    speakers: list[dict] = []
    by_key: dict = {}
    for entry in messages:
        key = (entry["speaker_id"], entry["speaker_name"])
        speaker = by_key.get(key)
        if speaker is None:
            speaker = {
                "speaker_id": entry["speaker_id"],
                "speaker_name": entry["speaker_name"],
                "messages_total": 0,
                "active_by_status": _empty_counts(),
                "messages_with_recorded": 0,
            }
            by_key[key] = speaker
            speakers.append(speaker)
        speaker["messages_total"] += 1
        speaker["active_by_status"][
            entry["active"]["reasoning_status"]] += 1
        if entry["full"]["recorded"]:
            speaker["messages_with_recorded"] += 1
    return speakers


def _message_entry(entry: dict) -> dict:
    """One transcript message's census row: the P-210
    entry shape (the active view's status, the full
    document's recorded bool and timestamp, the
    recorded swipe indexes) plus the two speaker
    fields the group store serves. No raw_road here:
    the document carries ONE document-level pointer
    (see the module docstring)."""
    active = entry["active"]
    full = entry["full"]
    return {
        "message_id": entry["message_id"],
        "role": entry["role"],
        "speaker_id": entry["speaker_id"],
        "speaker_name": entry["speaker_name"],
        "active_status": active["reasoning_status"],
        "recorded": full["recorded"],
        "recorded_at": full["recorded_at"],
        "swipes_recorded": _recorded_indexes(full),
    }


async def build_group_reasoning_document(
    session: AsyncSession,
    user_id: str,
    group_id: str,
) -> dict | None:
    """The Inspector group reasoning document for one
    owned group.

    Returns None when the group is missing or foreign
    (the router maps that to the house 404 idiom for
    groups; existence never leaks). Pure read: the
    census is composed by CALLING the banked-shape
    groupchat-store list_group_reasoning read and the
    banked summarise_reasoning aggregator, and
    persists nothing.
    """
    payload = await group_store.list_group_reasoning(
        session, user_id, group_id
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
                "the group transcript has no messages, so "
                "no reasoning records exist to census"
            ),
        }
    return {
        "schema": GROUP_REASONING_SCHEMA,
        "group_id": group_id,
        "room_chat_id": payload["room_chat_id"],
        "coverage": coverage,
        "summary": summarise_reasoning(messages),
        "speakers": summarise_speakers(messages),
        "messages": [_message_entry(entry) for entry in messages],
        "raw_road": f"/groups/{group_id}/messages",
    }
