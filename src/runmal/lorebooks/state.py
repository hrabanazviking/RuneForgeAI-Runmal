"""Per-chat lore entry timed-effect state persistence (P-033).

``lorebooks.activation.activate()`` is pure: callers pass the runtime
state dict (entry id -> ``EntryState``) in and get it back mutated.
This module is the persistence layer for that dict. Counters live in
``chat_lore_entry_states`` (migration 0025), modelled separately from
the canonical ``LoreEntry`` definition per DATA_MODEL.md: the entry
row holds the sticky/cooldown/delay CONFIG, these rows hold the live
counters, keyed by (chat, entry) -- the book is only the enumeration
source for a tick, never part of the key.

Absence of a row means the default (all-zero, unarmed) state, so a
row exists only while a timed effect is actually in flight. Preview
and prompt inspection stay clean-state forever and never touch this
module; the seam for a live pipeline is :func:`run_activation_tick`.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.chats.service import get_chat
from runmal.db.models import ChatLoreEntryState, LoreEntry
from runmal.lorebooks.activation import (
    ActivatableEntry,
    ActivationResult,
    EntryState,
    activate,
)
from runmal.lorebooks.service import list_entries

_COUNTER_FIELDS = ("sticky_remaining", "cooldown_remaining", "delay_remaining")


def _now() -> datetime:
    return datetime.now(UTC)


# --- Pure serialisation (sync, no DB) --------------------------------------


def is_default_state(state: EntryState) -> bool:
    """True when ``state`` carries no live effect (all counters 0, unarmed).

    The armed flag alone makes a state non-default, even with every
    counter at 0.
    """
    return (
        state.sticky_remaining == 0
        and state.cooldown_remaining == 0
        and state.delay_remaining == 0
        and not state.delay_armed
    )


def state_to_dict(state: EntryState) -> dict:
    """Convert one ``EntryState`` to its dict form (dataclass field names)."""
    return {
        "sticky_remaining": int(state.sticky_remaining),
        "cooldown_remaining": int(state.cooldown_remaining),
        "delay_remaining": int(state.delay_remaining),
        "delay_armed": bool(state.delay_armed),
    }


def state_from_dict(data: dict) -> EntryState:
    """Build an ``EntryState`` from its dict form.

    Missing keys fall back to the dataclass defaults; unknown keys are
    ignored (forward compatibility). Counter values must be ints --
    bool is rejected, mirroring ``activation._check_non_negative`` --
    and non-negative; violations raise ``ValueError``, as does a
    non-dict argument. ``delay_armed`` is coerced with ``bool()``.
    """
    if not isinstance(data, dict):
        raise ValueError("entry state must be a dict")
    fields: dict = {}
    for name in _COUNTER_FIELDS:
        if name not in data:
            continue
        value = data[name]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"{name} must be an integer")
        if value < 0:
            raise ValueError(f"{name} must be >= 0")
        fields[name] = value
    if "delay_armed" in data:
        fields["delay_armed"] = bool(data["delay_armed"])
    return EntryState(**fields)


def states_to_dict(states: dict[str, EntryState]) -> dict[str, dict]:
    """Convert a states dict to dict form, OMITTING default states."""
    return {
        entry_id: state_to_dict(state)
        for entry_id, state in states.items()
        if not is_default_state(state)
    }


def states_from_dict(data: dict[str, dict]) -> dict[str, EntryState]:
    """Build a states dict from dict form (see :func:`state_from_dict`)."""
    if not isinstance(data, dict):
        raise ValueError("entry states must be a dict")
    return {entry_id: state_from_dict(state) for entry_id, state in data.items()}


def _state_from_row(row: ChatLoreEntryState) -> EntryState:
    """Convert a stored row to an ``EntryState`` (fail loud on corruption)."""
    fields: dict = {}
    for name in _COUNTER_FIELDS:
        value = int(getattr(row, name))
        if value < 0:
            raise ValueError(f"stored {name} must be >= 0")
        fields[name] = value
    return EntryState(**fields, delay_armed=bool(row.delay_armed))


# --- Persistence (async, ownership-scoped via the chat) --------------------


async def load_entry_states(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    entry_ids: Iterable[str] | None = None,
) -> dict[str, EntryState] | None:
    """Load the live timed-effect states for one chat.

    Returns ``None`` when the chat is missing or not owned by
    ``user_id``; ``{}`` when the chat is owned but no effect is in
    flight. ``entry_ids`` optionally restricts the returned ids. Rows
    whose entry no longer exists are filtered out (stale state is
    never resurrected). Read-only: never commits, never writes.
    """
    if await get_chat(session, user_id, chat_id) is None:
        return None
    query = (
        select(ChatLoreEntryState)
        .join(LoreEntry, LoreEntry.id == ChatLoreEntryState.entry_id)
        .where(ChatLoreEntryState.chat_id == chat_id)
    )
    if entry_ids is not None:
        query = query.where(ChatLoreEntryState.entry_id.in_(list(entry_ids)))
    result = await session.execute(query)
    return {row.entry_id: _state_from_row(row) for row in result.scalars().all()}


async def save_entry_states(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    states: dict[str, EntryState],
    *,
    entry_ids: Iterable[str] | None = None,
) -> bool:
    """Sync the stored states for one chat to ``states`` within a scope.

    ``entry_ids`` is the COMPLETE scope of the save (default: the keys
    of ``states``): within (chat, scope) rows are made to match the
    given states exactly -- non-default states are upserted, default
    or absent states have their row deleted. Rows outside the scope
    (other books ticked earlier in the same chat) are untouched,
    except that rows whose entry no longer exists are swept away as
    part of the same commit (self-healing). Returns ``False`` --
    writing nothing -- when the chat is missing or not owned.
    ``updated_at`` is refreshed on every written row. Commits.
    """
    if await get_chat(session, user_id, chat_id) is None:
        return False
    scope = list(dict.fromkeys(entry_ids)) if entry_ids is not None else list(states)
    result = await session.execute(
        select(ChatLoreEntryState).where(
            ChatLoreEntryState.chat_id == chat_id,
            ChatLoreEntryState.entry_id.in_(scope),
        )
    )
    existing = {row.entry_id: row for row in result.scalars().all()}
    now = _now()
    for entry_id in scope:
        state = states.get(entry_id)
        row = existing.get(entry_id)
        if state is None or is_default_state(state):
            if row is not None:
                await session.delete(row)
            continue
        if row is None:
            session.add(
                ChatLoreEntryState(
                    chat_id=chat_id,
                    entry_id=entry_id,
                    sticky_remaining=int(state.sticky_remaining),
                    cooldown_remaining=int(state.cooldown_remaining),
                    delay_remaining=int(state.delay_remaining),
                    delay_armed=bool(state.delay_armed),
                    updated_at=now,
                )
            )
        else:
            row.sticky_remaining = int(state.sticky_remaining)
            row.cooldown_remaining = int(state.cooldown_remaining)
            row.delay_remaining = int(state.delay_remaining)
            row.delay_armed = bool(state.delay_armed)
            row.updated_at = now
    # Self-healing sweep: drop rows whose entry is gone (possible only
    # via a pragma-less raw connection or a pre-0025 restore; the FK
    # cascade handles every engine-mediated delete).
    await session.execute(
        delete(ChatLoreEntryState).where(
            ChatLoreEntryState.chat_id == chat_id,
            ~ChatLoreEntryState.entry_id.in_(select(LoreEntry.id)),
        )
    )
    await session.commit()
    return True


async def clear_entry_states(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    entry_ids: Iterable[str] | None = None,
) -> bool:
    """Delete stored timed-effect states for one chat. Commits.

    ``entry_ids=None`` clears ALL state for the chat; otherwise only
    the listed entries. Returns ``False`` when the chat is missing or
    not owned; deleting nothing is still ``True``.
    """
    if await get_chat(session, user_id, chat_id) is None:
        return False
    query = delete(ChatLoreEntryState).where(ChatLoreEntryState.chat_id == chat_id)
    if entry_ids is not None:
        query = query.where(ChatLoreEntryState.entry_id.in_(list(entry_ids)))
    await session.execute(query)
    await session.commit()
    return True


async def run_activation_tick(
    session: AsyncSession,
    user_id: str,
    chat_id: str,
    book_id: str,
    hit_ids: set[str],
    *,
    recursive_hit_ids: set[str] | None = None,
    hit_depths: dict[str, int] | None = None,
) -> ActivationResult | None:
    """Run one activation tick for a real chat, persisting the counters.

    The seam a future pipeline slice calls once per generated prompt:
    load the chat's persisted states for the book's entries, run the
    (pure, frozen) ``activate()``, then save the resulting states --
    strictly after ``activate()`` returns, in a single commit. If
    ``activate()`` raises, nothing is saved: a tick is atomic. Hit
    computation stays outside; ``hit_ids`` (plus the P-031 recursive
    passthroughs) are given. Returns ``None`` -- persisting nothing --
    when the chat or the book is missing or not owned.
    """
    if await get_chat(session, user_id, chat_id) is None:
        return None
    entries = await list_entries(session, user_id, book_id)
    if entries is None:
        return None
    entry_ids = [str(entry.id) for entry in entries]
    states = await load_entry_states(session, user_id, chat_id, entry_ids)
    if states is None:
        return None
    view = [ActivatableEntry.from_orm(entry) for entry in entries]
    result = activate(
        view,
        hit_ids,
        states,
        recursive_hit_ids=recursive_hit_ids,
        hit_depths=hit_depths,
    )
    await save_entry_states(session, user_id, chat_id, result.states, entry_ids=entry_ids)
    return result
