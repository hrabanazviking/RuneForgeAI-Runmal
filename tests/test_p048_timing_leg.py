"""P-048 Part III gate, Area C -- TIMING (P-033).

Roadmap line: *P-048 Part III gate: the ST-shaped lore test pack
(logic, recursion, timing) passes on Runmal's engine; inspector
explains every firing.*

Timing contract under test (P-033, as implemented by
``lorebooks.activation`` tick order and surfaced by
``lorebooks.preview`` / persisted by ``lorebooks.state``):

- One turn is one tick. Tick order per entry: cooldown first
  (decrement + suppress), then an armed delay (decrement; fire
  via ``"delay"`` on reaching zero), then a key hit (arm the
  delay instead when ``delay_prompts > 0``; otherwise fire via
  ``"key"`` and arm sticky/cooldown), then sticky carryover
  (decrement + fire via ``"sticky"``).
- Pure leg: ``preview_activation(..., entry_states=...)`` ticks
  a COPY of the supplied states -- the caller's mapping and its
  ``EntryState`` objects are never mutated, nothing persists --
  and each row's ``timed`` block reports ``state_before`` /
  ``state_after`` plus the derived ``effect``: ``"fired"``,
  ``"sticky_carryover"``, ``"cooldown_suppressed"``,
  ``"delay_armed"``, ``"delay_pending"``, ``"delay_fired"``
  or None. A key scan is a scan fact: ``matched_primary``
  records the key even on a tick where timing suppresses or
  defers the firing.
- Persistence leg: ``run_activation_tick`` in a FRESH session
  per tick (the restart boundary) reproduces the pure columns
  exactly when S+K+D live in one book on one chat, with no
  cross-leak. Absence of a state row IS the default state
  (``is_default_state``); deleting the chat cascades its rows.

Chat-life script (turn = one tick):
- Sticky S (sticky_prompts=2): T1 key hit fires via "key" and
  arms sticky 2; T2/T3 fire via "sticky" (2->1, 1->0); T4 quiet.
- Cooldown K (cooldown_prompts=2): T1 fires via "key", arms
  cooldown 2; T2/T3 hits are suppressed (2->1, 1->0); T4 hit
  fires via "key" again and re-arms.
- Delay D (delay_prompts=2): T1 hit only arms (delay_remaining
  2); T2 pending (2->1); T3 fires via "delay" with no key.
"""

from __future__ import annotations

import json
import sqlite3
from types import SimpleNamespace

from runmal.chats import service as chats_service
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.models import User
from runmal.lorebooks import service as lore_service
from runmal.lorebooks.activation import EntryState
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.state import (
    is_default_state,
    load_entry_states,
    run_activation_tick,
)

# ------------------------------------------------------------- pure helpers


def orm_entry(eid, name, content, keys=(), **kw):
    base = dict(
        id=eid, name=name, content=content, enabled=True, constant=False,
        vectorised=False, keys_json=json.dumps(list(keys)),
        secondary_keys_json="[]", whole_word=True, case_sensitive=False,
        selective_logic="and_any", sticky_prompts=0, cooldown_prompts=0,
        delay_prompts=0, inclusion_group="", group_weight=100, priority=100,
        probability=100, position="before_char", depth=None, role="system",
    )
    base.update(kw)
    return SimpleNamespace(**base)


def st(sticky=0, cooldown=0, delay=0, armed=False):
    return {
        "sticky_remaining": sticky,
        "cooldown_remaining": cooldown,
        "delay_remaining": delay,
        "delay_armed": armed,
    }


def _fields(state):
    return (
        state.sticky_remaining,
        state.cooldown_remaining,
        state.delay_remaining,
        state.delay_armed,
    )


def preview_turn(entries, message, states):
    """One pure tick; asserts the caller's states are unmutated."""
    snapshot = {eid: _fields(s) for eid, s in states.items()}
    result = preview_activation(
        entries, [message], 4, None, entry_states=states
    )
    assert set(states) == set(snapshot)
    for eid, before_fields in snapshot.items():
        assert _fields(states[eid]) == before_fields
    rows = {row["entry_id"]: row for row in result["entries"]}
    next_states = {
        eid: EntryState(**row["timed"]["state_after"])
        for eid, row in rows.items()
    }
    return result, rows, next_states


# ------------------------------------------------------- C-TIM-1: sticky


def test_c_tim_1_sticky_carryover_pure_leg():
    sid = "s1"
    entries = [
        orm_entry(sid, "S", "Sticky lore.", keys=("pinekey",),
                  sticky_prompts=2)
    ]
    states = {sid: EntryState()}
    original = states[sid]

    # T1: key hit fires via "key", arms sticky 2.
    _, rows, states = preview_turn(entries, "a pinekey appears", states)
    row = rows[sid]
    assert row["status"] == "included"
    assert row["via"] == "key"
    assert row["matched_primary"] == ["pinekey"]
    assert row["timed"]["config"] == {
        "sticky_prompts": 2, "cooldown_prompts": 0, "delay_prompts": 0,
    }
    assert row["timed"]["state_before"] == st()
    assert row["timed"]["state_after"] == st(sticky=2)
    assert row["timed"]["effect"] == "fired"
    assert original == EntryState()

    # T2: no hit, sticky carries it (2 -> 1).
    _, rows, states = preview_turn(entries, "quiet meadow", states)
    row = rows[sid]
    assert row["status"] == "included"
    assert row["via"] == "sticky"
    assert row["matched_primary"] == []
    assert row["timed"]["state_before"] == st(sticky=2)
    assert row["timed"]["state_after"] == st(sticky=1)
    assert row["timed"]["effect"] == "sticky_carryover"

    # T3: last sticky prompt (1 -> 0).
    _, rows, states = preview_turn(entries, "quiet meadow", states)
    row = rows[sid]
    assert row["status"] == "included"
    assert row["via"] == "sticky"
    assert row["timed"]["state_before"] == st(sticky=1)
    assert row["timed"]["state_after"] == st()
    assert row["timed"]["effect"] == "sticky_carryover"

    # T4: the effect is over.
    _, rows, states = preview_turn(entries, "quiet meadow", states)
    row = rows[sid]
    assert row["status"] == "not_triggered"
    assert row["via"] is None
    assert row["timed"]["state_before"] == st()
    assert row["timed"]["state_after"] == st()
    assert row["timed"]["effect"] is None
    assert states[sid] == EntryState()
    assert original == EntryState()


# ----------------------------------------------------- C-TIM-2: cooldown


def test_c_tim_2_cooldown_suppression_pure_leg():
    kid = "k1"
    entries = [
        orm_entry(kid, "K", "Cooldown lore.", keys=("kelpkey",),
                  cooldown_prompts=2)
    ]
    states = {kid: EntryState()}

    # T1: key hit fires via "key", arms cooldown 2.
    _, rows, states = preview_turn(entries, "kelpkey soup", states)
    row = rows[kid]
    assert row["status"] == "included"
    assert row["via"] == "key"
    assert row["timed"]["state_before"] == st()
    assert row["timed"]["state_after"] == st(cooldown=2)
    assert row["timed"]["effect"] == "fired"

    # T2: hit is suppressed; the scan still records the key.
    _, rows, states = preview_turn(entries, "kelpkey soup", states)
    row = rows[kid]
    assert row["status"] == "not_triggered"
    assert row["via"] is None
    assert row["matched_primary"] == ["kelpkey"]
    assert row["timed"]["state_before"] == st(cooldown=2)
    assert row["timed"]["state_after"] == st(cooldown=1)
    assert row["timed"]["effect"] == "cooldown_suppressed"

    # T3: suppressed again, counter burns its last prompt.
    _, rows, states = preview_turn(entries, "kelpkey soup", states)
    row = rows[kid]
    assert row["status"] == "not_triggered"
    assert row["via"] is None
    assert row["matched_primary"] == ["kelpkey"]
    assert row["timed"]["state_before"] == st(cooldown=1)
    assert row["timed"]["state_after"] == st()
    assert row["timed"]["effect"] == "cooldown_suppressed"

    # T4: cooldown spent; the hit fires via "key" and re-arms.
    _, rows, states = preview_turn(entries, "kelpkey soup", states)
    row = rows[kid]
    assert row["status"] == "included"
    assert row["via"] == "key"
    assert row["matched_primary"] == ["kelpkey"]
    assert row["timed"]["state_before"] == st()
    assert row["timed"]["state_after"] == st(cooldown=2)
    assert row["timed"]["effect"] == "fired"

    # Variant: the key ABSENT still decrements exactly once
    # per tick -- cooldown is per-tick, not per-hit -- and no
    # suppression effect is claimed without a trigger.
    states = {kid: EntryState(cooldown_remaining=2)}
    _, rows, states = preview_turn(entries, "quiet meadow", states)
    row = rows[kid]
    assert row["status"] == "not_triggered"
    assert row["matched_primary"] == []
    assert row["timed"]["state_before"] == st(cooldown=2)
    assert row["timed"]["state_after"] == st(cooldown=1)
    assert row["timed"]["effect"] is None
    _, rows, states = preview_turn(entries, "quiet meadow", states)
    row = rows[kid]
    assert row["timed"]["state_before"] == st(cooldown=1)
    assert row["timed"]["state_after"] == st()
    assert row["timed"]["effect"] is None


# --------------------------------------------------------- C-TIM-3: delay


def test_c_tim_3_delay_pure_leg():
    did = "d1"
    entries = [
        orm_entry(did, "D", "Delay lore.", keys=("thornkey",),
                  delay_prompts=2)
    ]
    states = {did: EntryState()}

    # T1: the hit only ARMS the delay; nothing fires.
    _, rows, states = preview_turn(entries, "thornkey hedge", states)
    row = rows[did]
    assert row["status"] == "not_triggered"
    assert row["via"] is None
    assert row["matched_primary"] == ["thornkey"]
    assert row["timed"]["state_before"] == st()
    assert row["timed"]["state_after"] == st(delay=2, armed=True)
    assert row["timed"]["state_after"]["delay_armed"] is True
    assert row["timed"]["state_after"]["delay_remaining"] == 2
    assert row["timed"]["effect"] == "delay_armed"

    # T2: no hit, still counting down (2 -> 1).
    _, rows, states = preview_turn(entries, "quiet meadow", states)
    row = rows[did]
    assert row["status"] == "not_triggered"
    assert row["via"] is None
    assert row["matched_primary"] == []
    assert row["timed"]["state_before"] == st(delay=2, armed=True)
    assert row["timed"]["state_after"] == st(delay=1, armed=True)
    assert row["timed"]["effect"] == "delay_pending"

    # T3: fires via "delay" with no key in the messages.
    _, rows, states = preview_turn(entries, "quiet meadow", states)
    row = rows[did]
    assert row["status"] == "included"
    assert row["via"] == "delay"
    assert row["matched_primary"] == []
    assert row["timed"]["state_before"] == st(delay=1, armed=True)
    assert row["timed"]["state_after"] == st()
    assert row["timed"]["effect"] == "delay_fired"

    # Variant: a re-hit at T2 while armed does NOT reset the
    # countdown -- the armed branch runs before trigger
    # dispatch, so it still fires at T3, not T4.
    states = {did: EntryState()}
    _, rows, states = preview_turn(entries, "thornkey hedge", states)
    assert rows[did]["timed"]["state_after"] == st(delay=2, armed=True)
    _, rows, states = preview_turn(entries, "thornkey again", states)
    row = rows[did]
    assert row["status"] == "not_triggered"
    assert row["matched_primary"] == ["thornkey"]
    assert row["timed"]["state_before"] == st(delay=2, armed=True)
    assert row["timed"]["state_after"] == st(delay=1, armed=True)
    assert row["timed"]["effect"] == "delay_pending"
    _, rows, states = preview_turn(entries, "quiet meadow", states)
    row = rows[did]
    assert row["status"] == "included"
    assert row["via"] == "delay"
    assert row["timed"]["effect"] == "delay_fired"
    _, rows, states = preview_turn(entries, "quiet meadow", states)
    assert rows[did]["status"] == "not_triggered"
    assert rows[did]["via"] is None


# ------------------------------------------------------- DB-leg helpers


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory, name="volmarr") -> str:
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


async def make_chat(factory, user_id, title="chat") -> str:
    async with factory() as session:
        chat = await chats_service.create_chat(session, user_id, title)
        return str(chat.id)


async def make_book(factory, user_id, specs, name="B"):
    async with factory() as session:
        book = await lore_service.create_lorebook(session, user_id, name)
        book_id = str(book.id)
        ids: dict[str, str] = {}
        for spec in specs:
            spec = dict(spec)
            label = spec.pop("label")
            entry = await lore_service.create_entry(
                session, user_id, book_id, **spec
            )
            ids[label] = str(entry.id)
        return book_id, ids


async def tick(factory, user_id, chat_id, book_id, hit_ids):
    """One activation tick in a FRESH session (restart boundary)."""
    async with factory() as session:
        return await run_activation_tick(
            session, user_id, chat_id, book_id, set(hit_ids)
        )


async def load(factory, user_id, chat_id, entry_ids=None):
    async with factory() as session:
        return await load_entry_states(session, user_id, chat_id, entry_ids)


def via_map(result) -> dict[str, str]:
    return {a.entry_id: a.via for a in result.activations}


def raw_count(tmp_path, chat_id=None) -> int:
    conn = sqlite3.connect(tmp_path / "test.db")
    try:
        sql = "SELECT COUNT(*) FROM chat_lore_entry_states WHERE 1 = 1"
        args: list = []
        if chat_id is not None:
            sql += " AND chat_id = ?"
            args.append(chat_id)
        return conn.execute(sql, args).fetchone()[0]
    finally:
        conn.close()


# ------------------------------------------- C-TIM-4: whole life persists


async def test_c_tim_4_whole_life_persists_db_leg(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    book_id, ids = await make_book(
        factory,
        user_id,
        [
            {"label": "s", "name": "S", "content": "Sticky lore.",
             "keys": ["pinekey"], "sticky_prompts": 2},
            {"label": "k", "name": "K", "content": "Cooldown lore.",
             "keys": ["kelpkey"], "cooldown_prompts": 2},
            {"label": "d", "name": "D", "content": "Delay lore.",
             "keys": ["thornkey"], "delay_prompts": 2},
        ],
    )
    s, k, d = ids["s"], ids["k"], ids["d"]

    # T1: all three keys hit. S and K fire via "key"; D only arms.
    result = await tick(factory, user_id, chat_id, book_id, {s, k, d})
    assert via_map(result) == {s: "key", k: "key"}
    assert await load(factory, user_id, chat_id) == {
        s: EntryState(sticky_remaining=2),
        k: EntryState(cooldown_remaining=2),
        d: EntryState(delay_remaining=2, delay_armed=True),
    }

    # T2: only K's key hits again. S carries on sticky, K is
    # suppressed, D counts down -- no column leaks into another.
    result = await tick(factory, user_id, chat_id, book_id, {k})
    assert via_map(result) == {s: "sticky"}
    assert await load(factory, user_id, chat_id) == {
        s: EntryState(sticky_remaining=1),
        k: EntryState(cooldown_remaining=1),
        d: EntryState(delay_remaining=1, delay_armed=True),
    }

    # T3: K's key hits again. S spends its last sticky prompt,
    # K is suppressed for its last cooldown prompt, D fires.
    result = await tick(factory, user_id, chat_id, book_id, {k})
    assert via_map(result) == {s: "sticky", d: "delay"}
    assert await load(factory, user_id, chat_id) == {}
    assert raw_count(tmp_path, chat_id) == 0

    # T4: only K's key hits. S and D stay quiet; K fires via
    # "key" again and re-arms its cooldown.
    result = await tick(factory, user_id, chat_id, book_id, {k})
    assert via_map(result) == {k: "key"}

    # Final residuals: K's re-armed cooldown is the only live
    # row. S and D are all-default, so their rows are ABSENT --
    # absence IS the default state.
    loaded = await load(factory, user_id, chat_id)
    assert loaded == {k: EntryState(cooldown_remaining=2)}
    assert s not in loaded and d not in loaded
    assert is_default_state(EntryState()) is True
    assert is_default_state(loaded[k]) is False
    assert raw_count(tmp_path, chat_id) == 1

    # Deleting the chat cascades its state rows away.
    async with factory() as session:
        assert await chats_service.delete_chat(
            session, user_id, chat_id
        ) is True
    assert raw_count(tmp_path, chat_id) == 0
    assert await load(factory, user_id, chat_id) is None
