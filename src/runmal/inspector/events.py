"""Inspector events document (P-204): one read-only
document per owned chat answering the mirror census's
triad question - "what happened in this chat, of what
recorded kinds, and what was never recorded at all" -
composed from the banked S107 durable chat event log.

The log itself is banked: the ChatEvent table (the S107
durable mutation event log per chat, in
src/runmal/db/models.py) has existed since the
pre-campaign base, is written by every chat mutation
path, and already has a raw read road
(GET /chats/{chat_id}/events) carrying every row's data
payload verbatim. What Part XIII lacked was the
Inspector's read of it. This service joins the log into
ONE schema-versioned document in the P-203 idiom -
counts, kind names and timestamps only - by CALLING the
banked chats-service read
(runmal.chats.service.list_events); it never
re-implements that read and never opens a second query
path (the P-059 one-source-of-truth rule, generalised,
as P-203 applied it to provenance).

No-payload law: the document carries NO event data
payloads and NO message content anywhere. Payload
drill-down stays on the banked raw road, which the
events section points at.

Honesty law (the P-075 idiom, transposed):

- every section carries a status from the closed set
  available / empty / not_applicable / unavailable, plus
  a plain ``reason`` string whenever it is not available;
- the census counts what is stored under its own kind
  string - legacy kinds are counted verbatim, never
  renamed, validated or dropped against the 20-kind
  S107 catalogue;
- a chat with zero recorded rows reads events status
  empty, total 0, by_kind {} - never a faked census and
  never an error;
- an upstream read failure reads unavailable + reason,
  never a faked empty;
- the triad's other legs are stated as they are: actions
  are occurrences of five kinds over the same log, plus
  per-message state the banked message reads already
  carry (m0038, P-068); flags are bind-time bool seeds
  with no runtime mutation, so there is no flag stream
  to census (not_applicable + pointers);
- what the tree never persisted - generation events,
  plugin dispatch outcomes, chat.deleted - is named in
  the not_recorded section instead of silently absent.

Read-only: nothing is persisted, cached or written; the
document is assembled fresh from the banked truth on
each call. Retention / bulk clear of the log is carried
item K-B - Volmarr's ruling, NOT this slice.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from runmal.chats import service as chats_service
from runmal.inspector import EVENTS_SCHEMA

__all__ = [
    "ACTION_KINDS",
    "GENERATED_FROM",
    "NOT_RECORDED_FAMILIES",
    "SECTION_STATUSES",
    "build_events_document",
]

#: The banked source this document is composed from, in
#: the fixed form the document declares.
GENERATED_FROM = ["S107 chat event log"]

#: The closed section-status vocabulary (P-075 idiom).
SECTION_STATUSES = frozenset(
    {"available", "empty", "not_applicable", "unavailable"}
)

#: The five S107 kinds that record a message ACTION's
#: occurrence. Per-message action STATE (variant history,
#: pin, position - m0038, P-068) rides the banked message
#: reads; this census counts occurrences only.
ACTION_KINDS = (
    "message.edited",
    "message.pinned_to_memory",
    "message.unpinned_from_memory",
    "message.moved",
    "message.copied_to_branch",
)

#: The families the tree never persisted into the S107
#: log, as (name, reason) pairs in fixed order. Each is
#: stated not_applicable in the document - an honest
#: coverage limit, never a silent gap.
NOT_RECORDED_FAMILIES = (
    (
        "generation events",
        "generation.before / generation.after / generation.failed are "
        "dispatched fire-and-observe from the generation seam and the "
        "P-081 plugin seam; the generation and plugin packages write "
        "no ChatEvent rows, so no generation event was ever recorded "
        "in the chat log",
    ),
    (
        "plugin dispatches",
        "P-081 dispatch outcomes and handler failures live in the "
        "plugin registry's own records, never in chat_events",
    ),
    (
        "chat.deleted",
        "deleting a chat cascades to its event log, so no "
        "chat.deleted row survives to be read",
    ),
)

#: Why the flags leg is not a stream (see _flags_section).
FLAGS_REASON = (
    "scenario flags are bind-time bool seeds in the binding record "
    "(scenarios/binding.py: flags hold bool only, seeded through "
    "P-093); nothing mutates a flag after binding, so no flag event "
    "stream exists to census"
)


def _section(status: str, *, reason: str | None = None, **fields) -> dict:
    """One events-document section: a closed-vocabulary
    status, a plain reason when not available, then the
    section's own fields."""
    doc = {"status": status, "reason": reason}
    doc.update(fields)
    return doc


def _raw_road(chat_id: str) -> dict:
    """Pointer at the banked raw events road, where the
    rows' data payloads already live verbatim."""
    return {"method": "GET", "path": f"/api/v1/chats/{chat_id}/events"}


def _actions_pointer(chat_id: str) -> dict:
    """Pointer at the banked message reads, where
    per-message action STATE already rides."""
    return {
        "method": "GET",
        "path": f"/api/v1/chats/{chat_id}/messages",
        "note": (
            "per-message action state (variant history, pin and "
            "position, m0038 / P-068) rides the banked message "
            "reads; this section counts occurrences only"
        ),
    }


def _events_section(events, chat_id: str) -> dict:
    """The by-kind census over the banked log rows: total,
    per-kind counts of the stored kind strings verbatim,
    the first / last timestamps and the newest row's kind
    only. No data payloads, no per-event rows."""
    if not events:
        return _section(
            "empty",
            reason=(
                "no events have been recorded for this chat (it "
                "predates the S107 event log or was created off "
                "the service path)"
            ),
            total=0,
            by_kind={},
            first_at=None,
            last_at=None,
            latest=None,
            raw_road=_raw_road(chat_id),
        )
    by_kind: dict[str, int] = {}
    for event in events:
        by_kind[event.kind] = by_kind.get(event.kind, 0) + 1
    newest = events[-1]
    return _section(
        "available",
        total=len(events),
        by_kind=by_kind,
        first_at=events[0].created_at.isoformat(),
        last_at=newest.created_at.isoformat(),
        latest={
            "kind": newest.kind,
            "created_at": newest.created_at.isoformat(),
        },
        raw_road=_raw_road(chat_id),
    )


def _unavailable_events_section(reason: str, chat_id: str) -> dict:
    return _section(
        "unavailable",
        reason=reason,
        total=None,
        by_kind={},
        first_at=None,
        last_at=None,
        latest=None,
        raw_road=_raw_road(chat_id),
    )


def _actions_section(events_section: dict, chat_id: str) -> dict:
    """The actions leg: occurrences of the five action
    kinds, counted FROM THE SAME census as the events
    section - never a second count over the log."""
    status = events_section["status"]
    if status == "unavailable":
        return _section(
            "unavailable",
            reason=events_section["reason"],
            counts={},
            total=None,
            kinds=list(ACTION_KINDS),
            pointer=_actions_pointer(chat_id),
        )
    by_kind = events_section["by_kind"]
    counts = {kind: by_kind.get(kind, 0) for kind in ACTION_KINDS}
    if status == "empty":
        return _section(
            "empty",
            reason="no events have been recorded for this chat, so no action occurrences exist",
            counts=counts,
            total=0,
            kinds=list(ACTION_KINDS),
            pointer=_actions_pointer(chat_id),
        )
    return _section(
        "available",
        counts=counts,
        total=sum(counts.values()),
        kinds=list(ACTION_KINDS),
        pointer=_actions_pointer(chat_id),
    )


def _flags_section(chat_id: str) -> dict:
    """The flags leg, stated honestly: flags are bind-time
    bool seeds, so there is no flag event stream to census.
    The section says so and points at the surfaces where
    binding state already reads."""
    return _section(
        "not_applicable",
        reason=FLAGS_REASON,
        pointers={
            "overview_scenario": {
                "method": "GET",
                "path": f"/api/v1/inspector/chats/{chat_id}",
            },
            "note": (
                "binding state already reads on the P-203 overview's "
                "scenario section and the banked scenario censuses"
            ),
        },
    )


def _not_recorded_section() -> dict:
    """The honest coverage statement as data: the families
    never persisted into the S107 log, each named with its
    reason, instead of silently absent. A fixed statement,
    not a probe - a later slice that starts recording one
    of these families must revise this section."""
    return _section(
        "not_applicable",
        reason=(
            "these families were never persisted into the S107 chat "
            "event log; they are named here so their absence is a "
            "stated coverage limit, not a silent gap"
        ),
        entries=[
            {"name": name, "status": "not_applicable", "reason": reason}
            for name, reason in NOT_RECORDED_FAMILIES
        ],
    )


async def build_events_document(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
) -> dict | None:
    """The Inspector events document for one owned chat.

    Returns None when the chat is missing or foreign (the
    router maps that to the house 404 idiom; existence
    never leaks). Pure read: the census is composed by
    CALLING the banked chats-service list_events read and
    persists nothing.
    """
    chat = await chats_service.get_chat(session, user_id, chat_id)
    if chat is None:
        return None
    try:
        events = await chats_service.list_events(session, user_id, chat_id)
    except Exception as exc:  # upstream read failed: say so
        events_section = _unavailable_events_section(
            f"chat event log read failed: {exc}", chat_id
        )
    else:
        if events is None:
            events_section = _unavailable_events_section(
                "chat event log read found no owned chat", chat_id
            )
        else:
            events_section = _events_section(events, chat_id)
    return {
        "schema": EVENTS_SCHEMA,
        "chat_id": chat_id,
        "generated_from": list(GENERATED_FROM),
        "sections": {
            "events": events_section,
            "actions": _actions_section(events_section, chat_id),
            "flags": _flags_section(chat_id),
            "not_recorded": _not_recorded_section(),
        },
    }
