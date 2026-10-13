"""Durable bridge event outbox (S609, BRIDGE_PROTOCOL §5).

One append-only stream per chat. Producers (turn writes, generation,
persona switches, TTS lifecycle) record events; consumers poll with
`after=<event-id>` and acknowledge with a per-credential checkpoint.
A reconnecting bridge resumes from its checkpoint: acknowledged
events are never re-delivered to it, unacknowledged ones are never
lost — up to the retention bound (the newest `DEFAULT_KEEP_LAST`
events per chat are kept; a consumer that falls behind the window
resyncs from the conversation-state read, the protocol's recovery
source of truth alongside this log).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.db.models import BridgeCheckpoint, BridgeEvent

DEFAULT_KEEP_LAST = 1000
MAX_PAGE = 500

# Event kinds (BRIDGE_PROTOCOL §5, plus turn_appended for multi-bridge
# sync — every bridge on a chat can see turns land in near-real-time).
KIND_TURN_APPENDED = "turn_appended"
KIND_COMPANION_TURN_READY = "companion_turn_ready"
KIND_GENERATION_CANCELLED = "generation_cancelled"
KIND_PERSONA_CHANGED = "persona_changed"
KIND_TTS_READY = "tts_ready"
KIND_PLAYBACK_COMPLETE = "playback_complete"


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


def event_to_dict(event: BridgeEvent) -> dict:
    return {
        "id": event.id,
        "chat_id": event.chat_id,
        "kind": event.kind,
        "data": json.loads(event.data_json),
        "created_at": event.created_at,
    }


async def record_event(
    session: AsyncSession,
    chat_id: str,
    kind: str,
    data: dict | None = None,
    *,
    keep_last: int = DEFAULT_KEEP_LAST,
) -> BridgeEvent:
    event = BridgeEvent(
        chat_id=chat_id,
        kind=kind,
        data_json=json.dumps(data or {}),
        created_at=_now_iso(),
    )
    session.add(event)
    await session.flush()
    await session.commit()
    await prune(session, chat_id, keep_last=keep_last)
    return event


async def prune(session: AsyncSession, chat_id: str, *, keep_last: int = DEFAULT_KEEP_LAST) -> int:
    """Bounded retention: keep only the newest `keep_last` events of a chat."""
    max_id = (
        await session.execute(
            select(func.max(BridgeEvent.id)).where(BridgeEvent.chat_id == chat_id)
        )
    ).scalar_one_or_none()
    if max_id is None:
        return 0
    cutoff = max_id - keep_last
    if cutoff <= 0:
        return 0
    result = await session.execute(
        delete(BridgeEvent).where(BridgeEvent.chat_id == chat_id, BridgeEvent.id <= cutoff)
    )
    await session.commit()
    return int(result.rowcount or 0)


async def list_events(
    session: AsyncSession, chat_id: str, *, after_id: int = 0, limit: int = 100
) -> list[BridgeEvent]:
    limit = max(1, min(limit, MAX_PAGE))
    result = await session.execute(
        select(BridgeEvent)
        .where(BridgeEvent.chat_id == chat_id, BridgeEvent.id > after_id)
        .order_by(BridgeEvent.id)
        .limit(limit)
    )
    return list(result.scalars().all())


async def latest_event_id(session: AsyncSession, chat_id: str) -> int:
    value = (
        await session.execute(
            select(func.max(BridgeEvent.id)).where(BridgeEvent.chat_id == chat_id)
        )
    ).scalar_one_or_none()
    return int(value or 0)


async def get_checkpoint(session: AsyncSession, credential_id: str, chat_id: str) -> int:
    row = await session.get(BridgeCheckpoint, (credential_id, chat_id))
    return int(row.last_event_id) if row is not None else 0


async def acknowledge(
    session: AsyncSession, credential_id: str, chat_id: str, event_id: int
) -> int:
    """Move this credential's checkpoint forward (never backward, and
    never past the newest event that exists). Returns the checkpoint."""
    latest = await latest_event_id(session, chat_id)
    target = min(event_id, latest)
    row = await session.get(BridgeCheckpoint, (credential_id, chat_id))
    if row is None:
        row = BridgeCheckpoint(
            credential_id=credential_id,
            chat_id=chat_id,
            last_event_id=target,
            updated_at=_now_iso(),
        )
        session.add(row)
    elif target > row.last_event_id:
        row.last_event_id = target
        row.updated_at = _now_iso()
    await session.commit()
    return int(row.last_event_id)
