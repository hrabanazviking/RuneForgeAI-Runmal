"""P-033 acceptance: timed effects persist across a chat's life.

Roadmap line: *Timed effects: sticky/cooldown/delay entries across
a chat's life.*

Contract under test:
- ``runmal.lorebooks.state`` owns the pure serialisation of the
  frozen ``activation.EntryState`` (default states are omitted from
  the dict form; unknown dict keys are ignored, missing keys
  default, bool/non-int/negative counters raise ``ValueError``).
- Migration 0025 creates ``chat_lore_entry_states`` keyed by
  (chat_id, entry_id) with CASCADE foreign keys to both parents;
  absence of a row IS the default state (no backfill).
- The async service (load/save/clear) is ownership-scoped through
  the chat: a missing or foreign chat yields None/False and writes
  nothing. Saves are scope-synced: rows outside the save scope (a
  different book ticked earlier in the same chat) are untouched.
- ``run_activation_tick`` is the persistence seam: load state, run
  the frozen ``activate()``, save the result -- so sticky, cooldown
  and delay counters survive a restart (a FRESH session from the
  same factory; no in-memory dict is ever carried between ticks).
- Deleting an entry, a chat, or a book cascades the state rows
  away; preview stays clean-state and never reads or writes rows.

Helper patterns mirror tests/test_p032_selective_logic.py
(``make_factory`` / ``make_user``), extended with ``make_chat`` /
``make_book`` built on the chats and lorebooks services.
"""

from __future__ import annotations

import sqlite3

import pytest

from runmal.chats import service as chats_service
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.lorebooks import service as lore_service
from runmal.lorebooks.activation import EntryState
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.state import (
    clear_entry_states,
    is_default_state,
    load_entry_states,
    run_activation_tick,
    save_entry_states,
    state_from_dict,
    state_to_dict,
    states_from_dict,
    states_to_dict,
)

# ---------------------------------------------------------------- helpers


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
    """Create a lorebook plus entries; returns (book_id, {label: entry_id}).

    Each spec is a ``create_entry`` kwargs dict plus a ``label`` key
    naming the entry for the test.
    """
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


async def tick(factory, user_id, chat_id, book_id, hit_ids, **kw):
    """One activation tick in a FRESH session (the restart boundary)."""
    async with factory() as session:
        return await run_activation_tick(
            session, user_id, chat_id, book_id, set(hit_ids), **kw
        )


async def load(factory, user_id, chat_id, entry_ids=None):
    async with factory() as session:
        return await load_entry_states(session, user_id, chat_id, entry_ids)


async def save(factory, user_id, chat_id, states, entry_ids=None):
    async with factory() as session:
        return await save_entry_states(
            session, user_id, chat_id, states, entry_ids=entry_ids
        )


async def clear(factory, user_id, chat_id, entry_ids=None):
    async with factory() as session:
        return await clear_entry_states(session, user_id, chat_id, entry_ids)


def via_map(result) -> dict[str, str]:
    return {a.entry_id: a.via for a in result.activations}


def raw_rows(tmp_path, chat_id=None):
    conn = sqlite3.connect(tmp_path / "test.db")
    try:
        sql = (
            "SELECT chat_id, entry_id, sticky_remaining, cooldown_remaining,"
            " delay_remaining, delay_armed, updated_at"
            " FROM chat_lore_entry_states"
        )
        if chat_id is None:
            return conn.execute(sql + " ORDER BY entry_id").fetchall()
        return conn.execute(
            sql + " WHERE chat_id = ? ORDER BY entry_id", (chat_id,)
        ).fetchall()
    finally:
        conn.close()


def raw_count(tmp_path, chat_id=None, entry_id=None) -> int:
    conn = sqlite3.connect(tmp_path / "test.db")
    try:
        sql = "SELECT COUNT(*) FROM chat_lore_entry_states WHERE 1 = 1"
        args: list = []
        if chat_id is not None:
            sql += " AND chat_id = ?"
            args.append(chat_id)
        if entry_id is not None:
            sql += " AND entry_id = ?"
            args.append(entry_id)
        return conn.execute(sql, args).fetchone()[0]
    finally:
        conn.close()

# ------------------------------------------- (a) pure serialisation

ROUND_TRIP_STATES = [
    EntryState(),
    EntryState(sticky_remaining=3),
    EntryState(cooldown_remaining=2),
    EntryState(delay_remaining=4),
    EntryState(delay_armed=True),
    EntryState(
        sticky_remaining=1, cooldown_remaining=2, delay_remaining=3,
        delay_armed=True,
    ),
]


@pytest.mark.parametrize("state", ROUND_TRIP_STATES)
def test_state_dict_round_trip(state):
    assert state_from_dict(state_to_dict(state)) == state


def test_state_to_dict_exact_shape_and_order():
    d = state_to_dict(
        EntryState(
            sticky_remaining=1, cooldown_remaining=2, delay_remaining=3,
            delay_armed=True,
        )
    )
    assert d == {
        "sticky_remaining": 1,
        "cooldown_remaining": 2,
        "delay_remaining": 3,
        "delay_armed": True,
    }
    assert list(d) == [
        "sticky_remaining", "cooldown_remaining", "delay_remaining",
        "delay_armed",
    ]


def test_states_to_dict_omits_defaults_keeps_live():
    live = EntryState(sticky_remaining=2)
    armed_only = EntryState(delay_armed=True)
    counter_only = EntryState(cooldown_remaining=1)
    d = states_to_dict(
        {"a": EntryState(), "b": live, "c": armed_only, "e": counter_only}
    )
    assert set(d) == {"b", "c", "e"}
    assert states_from_dict(d) == {"b": live, "c": armed_only, "e": counter_only}


def test_states_round_trip_law():
    original = {
        "a": EntryState(),
        "b": EntryState(cooldown_remaining=5),
        "c": EntryState(delay_remaining=1, delay_armed=True),
    }
    expected = {
        k: v for k, v in original.items() if not is_default_state(v)
    }
    assert states_from_dict(states_to_dict(original)) == expected


def test_state_from_dict_missing_keys_default():
    assert state_from_dict({}) == EntryState()
    assert state_from_dict({"sticky_remaining": 7}) == EntryState(
        sticky_remaining=7
    )


def test_state_from_dict_unknown_keys_ignored():
    assert state_from_dict(
        {"sticky_remaining": 2, "future_field": 99, "other": "x"}
    ) == EntryState(sticky_remaining=2)


@pytest.mark.parametrize(
    "field", ["sticky_remaining", "cooldown_remaining", "delay_remaining"]
)
def test_state_from_dict_negative_counter_raises(field):
    with pytest.raises(ValueError):
        state_from_dict({field: -1})


@pytest.mark.parametrize(
    "field", ["sticky_remaining", "cooldown_remaining", "delay_remaining"]
)
@pytest.mark.parametrize("bad", [True, False])
def test_state_from_dict_bool_counter_raises(field, bad):
    with pytest.raises(ValueError):
        state_from_dict({field: bad})


@pytest.mark.parametrize("bad", [1.5, "2", None, [1], {"x": 1}])
def test_state_from_dict_non_int_counter_raises(bad):
    with pytest.raises(ValueError):
        state_from_dict({"sticky_remaining": bad})


@pytest.mark.parametrize("bad", ["nope", None, 42, [("sticky_remaining", 1)]])
def test_state_from_dict_non_dict_raises(bad):
    with pytest.raises(ValueError):
        state_from_dict(bad)


def test_states_from_dict_non_dict_raises():
    with pytest.raises(ValueError):
        states_from_dict("nope")
    with pytest.raises(ValueError):
        states_from_dict({"a": "nope"})


@pytest.mark.parametrize(
    "raw,expected", [(1, True), (0, False), ("", False), ("x", True)]
)
def test_state_from_dict_delay_armed_coerced(raw, expected):
    assert state_from_dict({"delay_armed": raw}).delay_armed is expected


@pytest.mark.parametrize(
    "state,expected",
    [
        (EntryState(), True),
        (EntryState(sticky_remaining=1), False),
        (EntryState(cooldown_remaining=1), False),
        (EntryState(delay_remaining=1), False),
        # The armed flag alone is a live effect, even at zero counters.
        (EntryState(delay_armed=True), False),
    ],
)
def test_is_default_state_truth_table(state, expected):
    assert is_default_state(state) is expected

# ------------------------------------------------- (b) migration 0025


def test_migration_head_is_0025():
    # 0025 stands as numbered; head moved to 0028 when P-036
    # landed after this slice (0027 reserved for P-035).
    assert MIGRATIONS[-3][0] == "0025"
    assert MIGRATIONS[-1][0] == "0028"


def test_migration_0025_reaches_head_and_idempotent(tmp_path):
    db_path = tmp_path / "m.db"
    applied = migrate_to_head(db_path)
    assert applied[-3:] == ["0025", "0026", "0028"]
    assert current_revision(db_path) == "0028"
    # Forward-only runner: a second pass applies nothing new.
    assert migrate_to_head(db_path) == []
    assert current_revision(db_path) == "0028"


def test_migration_0025_table_shape(tmp_path):
    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        info = list(conn.execute("PRAGMA table_info(chat_lore_entry_states)"))
        # (name, type) in DDL order, exactly the seven designed columns.
        assert [(row[1], row[2]) for row in info] == [
            ("chat_id", "TEXT"),
            ("entry_id", "TEXT"),
            ("sticky_remaining", "INTEGER"),
            ("cooldown_remaining", "INTEGER"),
            ("delay_remaining", "INTEGER"),
            ("delay_armed", "INTEGER"),
            ("updated_at", "TEXT"),
        ]
        by_name = {row[1]: row for row in info}
        # Composite primary key: chat_id is part 1, entry_id part 2.
        assert by_name["chat_id"][5] == 1
        assert by_name["entry_id"][5] == 2
        for counter in (
            "sticky_remaining", "cooldown_remaining", "delay_remaining",
            "delay_armed",
        ):
            assert by_name[counter][3] == 1  # NOT NULL
            assert by_name[counter][5] == 0  # not part of the PK
        fks = {
            (row[2], row[3], row[4], row[6])
            for row in conn.execute(
                "PRAGMA foreign_key_list(chat_lore_entry_states)"
            )
        }
        assert fks == {
            ("chats", "chat_id", "id", "CASCADE"),
            ("lore_entries", "entry_id", "id", "CASCADE"),
        }
        index_names = {
            row[1]
            for row in conn.execute(
                "PRAGMA index_list(chat_lore_entry_states)"
            )
        }
        assert "idx_chat_lore_entry_states_entry" in index_names
    finally:
        conn.close()


def test_migration_0025_raw_row_defaults(tmp_path):
    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO users (id, name, created_at) VALUES (?, ?, ?)",
            ("u1", "U", "2026-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO chats (id, user_id, title, created_at)"
            " VALUES (?, ?, ?, ?)",
            ("c1", "u1", "", "2026-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO lorebooks (id, user_id, name, created_at)"
            " VALUES (?, ?, ?, ?)",
            ("b1", "u1", "B", "2026-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO lore_entries (id, lorebook_id, user_id, created_at)"
            " VALUES (?, ?, ?, ?)",
            ("e1", "b1", "u1", "2026-01-01T00:00:00"),
        )
        # Raw row naming only the key + updated_at: the DDL defaults
        # must supply all-zero counters (P-032 raw-row style).
        conn.execute(
            "INSERT INTO chat_lore_entry_states (chat_id, entry_id, updated_at)"
            " VALUES (?, ?, ?)",
            ("c1", "e1", "2026-01-01T00:00:00"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT sticky_remaining, cooldown_remaining, delay_remaining,"
            " delay_armed FROM chat_lore_entry_states"
            " WHERE chat_id = ? AND entry_id = ?",
            ("c1", "e1"),
        ).fetchone()
        assert row == (0, 0, 0, 0)
    finally:
        conn.close()


async def test_migration_0025_no_backfill_and_data_intact(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    await make_book(
        factory, user_id, [{"label": "e", "name": "E", "keys": ["x"]}]
    )
    # Pre-existing content is intact and NO state rows were backfilled:
    # every chat simply starts with no rows, i.e. all effects clean.
    conn = sqlite3.connect(tmp_path / "test.db")
    try:
        assert conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0] == 1
        assert (
            conn.execute("SELECT COUNT(*) FROM lore_entries").fetchone()[0]
            == 1
        )
        assert (
            conn.execute(
                "SELECT COUNT(*) FROM chat_lore_entry_states"
            ).fetchone()[0]
            == 0
        )
    finally:
        conn.close()
    assert await load(factory, user_id, chat_id) == {}
    # Re-running the migrator changes nothing.
    assert migrate_to_head(tmp_path / "test.db") == []
    assert await load(factory, user_id, chat_id) == {}

# ------------------------------------------- (c) service load/save/clear


async def test_load_fresh_missing_and_foreign(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    other_id = await make_user(factory, name="other")
    chat_id = await make_chat(factory, user_id)
    assert await load(factory, user_id, chat_id) == {}
    assert await load(factory, user_id, "no-such-chat") is None
    # Foreign chat is indistinguishable from a missing one.
    assert await load(factory, other_id, chat_id) is None


async def test_save_restart_load_round_trip(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    _, ids = await make_book(
        factory,
        user_id,
        [
            {"label": "a", "name": "A", "keys": ["a"]},
            {"label": "b", "name": "B", "keys": ["b"]},
        ],
    )
    states = {
        ids["a"]: EntryState(sticky_remaining=2, cooldown_remaining=1),
        ids["b"]: EntryState(delay_remaining=3, delay_armed=True),
    }
    assert await save(factory, user_id, chat_id, states) is True
    # Restart: a fresh session reads back exactly what was saved.
    assert await load(factory, user_id, chat_id) == states
    rows = {row[1]: row for row in raw_rows(tmp_path, chat_id)}
    assert rows[ids["a"]][2:6] == (2, 1, 0, 0)
    assert rows[ids["b"]][2:6] == (0, 0, 3, 1)


async def test_save_missing_and_foreign_write_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    other_id = await make_user(factory, name="other")
    chat_id = await make_chat(factory, user_id)
    _, ids = await make_book(
        factory, user_id, [{"label": "a", "name": "A", "keys": ["a"]}]
    )
    live = {ids["a"]: EntryState(sticky_remaining=1)}
    assert await save(factory, user_id, "no-such-chat", live) is False
    assert await save(factory, other_id, chat_id, live) is False
    assert raw_count(tmp_path) == 0
    # The owner's own save still works and is unaffected by the refusals.
    assert await save(factory, user_id, chat_id, live) is True
    assert await save(factory, other_id, chat_id, live) is False
    assert await load(factory, user_id, chat_id) == live


async def test_save_skips_default_states(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    _, ids = await make_book(
        factory,
        user_id,
        [
            {"label": "live", "name": "L", "keys": ["l"]},
            {"label": "idle", "name": "I", "keys": ["i"]},
        ],
    )
    states = {
        ids["live"]: EntryState(sticky_remaining=2),
        ids["idle"]: EntryState(),
    }
    scope = [ids["live"], ids["idle"]]
    assert await save(factory, user_id, chat_id, states, entry_ids=scope) is True
    # Only the live row exists on disk; load returns the live subset only.
    assert raw_count(tmp_path, chat_id) == 1
    assert await load(factory, user_id, chat_id) == {
        ids["live"]: EntryState(sticky_remaining=2)
    }


async def test_save_scope_isolation_between_books(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    _, ids_a = await make_book(
        factory, user_id, [{"label": "a", "name": "A", "keys": ["a"]}], name="BA"
    )
    _, ids_b = await make_book(
        factory, user_id, [{"label": "b", "name": "B", "keys": ["b"]}], name="BB"
    )
    ea, eb = ids_a["a"], ids_b["b"]
    assert await save(
        factory, user_id, chat_id, {ea: EntryState(sticky_remaining=1)},
        entry_ids=[ea],
    ) is True
    # Saving book B's states must never touch book A's rows.
    assert await save(
        factory, user_id, chat_id, {eb: EntryState(cooldown_remaining=3)},
        entry_ids=[eb],
    ) is True
    assert await load(factory, user_id, chat_id) == {
        ea: EntryState(sticky_remaining=1),
        eb: EntryState(cooldown_remaining=3),
    }
    # Saving a default state for a previously-live entry deletes its row,
    # still leaving the other book's row intact.
    assert await save(
        factory, user_id, chat_id, {ea: EntryState()}, entry_ids=[ea]
    ) is True
    assert await load(factory, user_id, chat_id) == {
        eb: EntryState(cooldown_remaining=3)
    }
    assert raw_count(tmp_path, chat_id, entry_id=ea) == 0
    assert raw_count(tmp_path, chat_id, entry_id=eb) == 1


async def test_save_absent_in_scope_deletes_row(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    _, ids = await make_book(
        factory,
        user_id,
        [
            {"label": "a", "name": "A", "keys": ["a"]},
            {"label": "b", "name": "B", "keys": ["b"]},
        ],
    )
    ea, eb = ids["a"], ids["b"]
    both = {ea: EntryState(sticky_remaining=1), eb: EntryState(sticky_remaining=1)}
    assert await save(factory, user_id, chat_id, both, entry_ids=[ea, eb]) is True
    # An in-scope entry ABSENT from the states dict loses its row;
    # the out-of-scope entry keeps its own.
    assert await save(factory, user_id, chat_id, {}, entry_ids=[ea]) is True
    assert await load(factory, user_id, chat_id) == {
        eb: EntryState(sticky_remaining=1)
    }


async def test_clear_all_listed_empty_and_foreign(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    other_id = await make_user(factory, name="other")
    chat_id = await make_chat(factory, user_id)
    _, ids = await make_book(
        factory,
        user_id,
        [
            {"label": "a", "name": "A", "keys": ["a"]},
            {"label": "b", "name": "B", "keys": ["b"]},
        ],
    )
    ea, eb = ids["a"], ids["b"]
    both = {ea: EntryState(sticky_remaining=1), eb: EntryState(cooldown_remaining=2)}
    assert await save(factory, user_id, chat_id, both) is True
    # Foreign / missing chats refuse and delete nothing.
    assert await clear(factory, other_id, chat_id) is False
    assert await clear(factory, user_id, "no-such-chat") is False
    assert raw_count(tmp_path, chat_id) == 2
    # Listed entries only.
    assert await clear(factory, user_id, chat_id, entry_ids=[ea]) is True
    assert await load(factory, user_id, chat_id) == {
        eb: EntryState(cooldown_remaining=2)
    }
    # entry_ids=None clears everything; clearing an empty chat is True.
    assert await clear(factory, user_id, chat_id) is True
    assert await load(factory, user_id, chat_id) == {}
    assert await clear(factory, user_id, chat_id) is True


async def test_load_entry_ids_restricts_result(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    _, ids = await make_book(
        factory,
        user_id,
        [
            {"label": "a", "name": "A", "keys": ["a"]},
            {"label": "b", "name": "B", "keys": ["b"]},
        ],
    )
    ea, eb = ids["a"], ids["b"]
    both = {ea: EntryState(sticky_remaining=1), eb: EntryState(sticky_remaining=2)}
    assert await save(factory, user_id, chat_id, both) is True
    assert await load(factory, user_id, chat_id, [ea]) == {
        ea: EntryState(sticky_remaining=1)
    }
    assert await load(factory, user_id, chat_id, [eb]) == {
        eb: EntryState(sticky_remaining=2)
    }


async def test_load_filters_orphan_row_and_save_sweeps_it(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    _, ids = await make_book(
        factory,
        user_id,
        [
            {"label": "gone", "name": "G", "keys": ["g"]},
            {"label": "kept", "name": "K", "keys": ["k"]},
        ],
    )
    gone, kept = ids["gone"], ids["kept"]
    assert await save(
        factory, user_id, chat_id, {gone: EntryState(sticky_remaining=2)}
    ) is True
    # Delete the entry behind the service's back on a pragma-less raw
    # connection: no FK cascade runs, so the state row is orphaned.
    conn = sqlite3.connect(tmp_path / "test.db")
    try:
        conn.execute("DELETE FROM lore_entries WHERE id = ?", (gone,))
        conn.commit()
    finally:
        conn.close()
    assert raw_count(tmp_path, chat_id, entry_id=gone) == 1  # orphan on disk
    # Load filters it out: stale state is never resurrected.
    assert await load(factory, user_id, chat_id) == {}
    # The next save sweeps the orphan away in the same commit.
    assert await save(
        factory, user_id, chat_id, {kept: EntryState(sticky_remaining=1)}
    ) is True
    assert raw_count(tmp_path, chat_id, entry_id=gone) == 0
    assert await load(factory, user_id, chat_id) == {
        kept: EntryState(sticky_remaining=1)
    }


async def test_updated_at_set_and_refreshed_on_resave(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    _, ids = await make_book(
        factory, user_id, [{"label": "a", "name": "A", "keys": ["a"]}]
    )
    ea = ids["a"]
    assert await save(
        factory, user_id, chat_id, {ea: EntryState(sticky_remaining=1)}
    ) is True
    rows = raw_rows(tmp_path, chat_id)
    assert len(rows) == 1 and rows[0][6]  # updated_at written, non-empty
    # Age the row artificially, then re-save: updated_at must refresh.
    conn = sqlite3.connect(tmp_path / "test.db")
    try:
        conn.execute(
            "UPDATE chat_lore_entry_states SET updated_at = ?"
            " WHERE chat_id = ? AND entry_id = ?",
            ("2000-01-01T00:00:00", chat_id, ea),
        )
        conn.commit()
    finally:
        conn.close()
    assert await save(
        factory, user_id, chat_id, {ea: EntryState(sticky_remaining=2)}
    ) is True
    rows = raw_rows(tmp_path, chat_id)
    assert rows[0][2] == 2
    assert rows[0][6] != "2000-01-01T00:00:00"

# ------------------------------ (d) multi-tick chat-life simulation
# Every tick() and load() below runs in a FRESH session: the counters
# can only survive via the database. That restart discipline is the
# whole point of the slice.


async def test_tick_sticky_lifecycle_across_restarts(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    book_id, ids = await make_book(
        factory,
        user_id,
        [{"label": "s", "name": "S", "keys": ["s"], "sticky_prompts": 2}],
    )
    s = ids["s"]
    # Tick 1: key hit fires via "key" and arms sticky for 2 prompts.
    result = await tick(factory, user_id, chat_id, book_id, {s})
    assert via_map(result) == {s: "key"}
    assert await load(factory, user_id, chat_id) == {
        s: EntryState(sticky_remaining=2)
    }
    # Tick 2 (after restart): no hit, fires via "sticky", one left.
    result = await tick(factory, user_id, chat_id, book_id, set())
    assert via_map(result) == {s: "sticky"}
    assert await load(factory, user_id, chat_id) == {
        s: EntryState(sticky_remaining=1)
    }
    # Tick 3: last sticky prompt; the state returns to default and
    # the row deletes itself on save.
    result = await tick(factory, user_id, chat_id, book_id, set())
    assert via_map(result) == {s: "sticky"}
    assert await load(factory, user_id, chat_id) == {}
    assert raw_count(tmp_path, chat_id) == 0
    # Tick 4: the effect is over.
    result = await tick(factory, user_id, chat_id, book_id, set())
    assert result.activations == []
    assert await load(factory, user_id, chat_id) == {}


async def test_tick_cooldown_suppresses_and_rearms(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    book_id, ids = await make_book(
        factory,
        user_id,
        [{"label": "c", "name": "C", "keys": ["c"], "cooldown_prompts": 2}],
    )
    c = ids["c"]
    result = await tick(factory, user_id, chat_id, book_id, {c})
    assert via_map(result) == {c: "key"}
    assert await load(factory, user_id, chat_id) == {
        c: EntryState(cooldown_remaining=2)
    }
    # Re-hits during cooldown are suppressed while the counter burns.
    result = await tick(factory, user_id, chat_id, book_id, {c})
    assert result.activations == []
    assert await load(factory, user_id, chat_id) == {
        c: EntryState(cooldown_remaining=1)
    }
    result = await tick(factory, user_id, chat_id, book_id, {c})
    assert result.activations == []
    assert await load(factory, user_id, chat_id) == {}
    assert raw_count(tmp_path, chat_id) == 0
    # Cooldown spent: the next hit fires via "key" and re-arms it.
    result = await tick(factory, user_id, chat_id, book_id, {c})
    assert via_map(result) == {c: "key"}
    assert await load(factory, user_id, chat_id) == {
        c: EntryState(cooldown_remaining=2)
    }


async def test_tick_cooldown_decrements_on_no_hit_ticks(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    book_id, ids = await make_book(
        factory,
        user_id,
        [{"label": "c", "name": "C", "keys": ["c"], "cooldown_prompts": 2}],
    )
    c = ids["c"]
    result = await tick(factory, user_id, chat_id, book_id, {c})
    assert via_map(result) == {c: "key"}
    # Cooldown is per-TICK, not per-hit: quiet ticks burn it down too.
    result = await tick(factory, user_id, chat_id, book_id, set())
    assert result.activations == []
    assert await load(factory, user_id, chat_id) == {
        c: EntryState(cooldown_remaining=1)
    }
    result = await tick(factory, user_id, chat_id, book_id, set())
    assert result.activations == []
    assert await load(factory, user_id, chat_id) == {}


async def test_tick_delay_arms_survives_restart_and_fires(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    book_id, ids = await make_book(
        factory,
        user_id,
        [{"label": "d", "name": "D", "keys": ["d"], "delay_prompts": 2}],
    )
    d = ids["d"]
    # Tick 1: the hit only ARMS the delay; nothing fires yet.
    result = await tick(factory, user_id, chat_id, book_id, {d})
    assert result.activations == []
    # The armed delay must survive the restart -- the slice's
    # sharpest case. This load is a fresh session reading the DB.
    assert await load(factory, user_id, chat_id) == {
        d: EntryState(delay_remaining=2, delay_armed=True)
    }
    # Tick 2: still counting down.
    result = await tick(factory, user_id, chat_id, book_id, set())
    assert result.activations == []
    assert await load(factory, user_id, chat_id) == {
        d: EntryState(delay_remaining=1, delay_armed=True)
    }
    # Tick 3: the delay fires via "delay" and the row is gone.
    result = await tick(factory, user_id, chat_id, book_id, set())
    assert via_map(result) == {d: "delay"}
    assert await load(factory, user_id, chat_id) == {}
    assert raw_count(tmp_path, chat_id) == 0
    # Tick 4: quiet again.
    result = await tick(factory, user_id, chat_id, book_id, set())
    assert result.activations == []


async def test_tick_sticky_cooldown_interaction_order(tmp_path):
    # Pins the FROZEN activation tick order: the cooldown branch runs
    # before the sticky branch, so a cooling-down entry does not
    # consume its sticky prompts.
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    book_id, ids = await make_book(
        factory,
        user_id,
        [
            {
                "label": "x", "name": "X", "keys": ["x"],
                "sticky_prompts": 1, "cooldown_prompts": 1,
            }
        ],
    )
    x = ids["x"]
    result = await tick(factory, user_id, chat_id, book_id, {x})
    assert via_map(result) == {x: "key"}
    assert await load(factory, user_id, chat_id) == {
        x: EntryState(sticky_remaining=1, cooldown_remaining=1)
    }
    # Tick 2: suppressed by cooldown; sticky is NOT consumed.
    result = await tick(factory, user_id, chat_id, book_id, set())
    assert result.activations == []
    assert await load(factory, user_id, chat_id) == {
        x: EntryState(sticky_remaining=1, cooldown_remaining=0)
    }
    # Tick 3: cooldown spent, the preserved sticky prompt fires.
    result = await tick(factory, user_id, chat_id, book_id, set())
    assert via_map(result) == {x: "sticky"}
    assert await load(factory, user_id, chat_id) == {}
    assert raw_count(tmp_path, chat_id) == 0


async def test_tick_recursive_passthrough_persists(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    book_id, ids = await make_book(
        factory,
        user_id,
        [{"label": "r", "name": "R", "keys": ["r"], "sticky_prompts": 1}],
    )
    r = ids["r"]
    result = await tick(
        factory, user_id, chat_id, book_id, {r},
        recursive_hit_ids={r}, hit_depths={r: 2},
    )
    assert via_map(result) == {r: "recursive"}
    assert result.activations[0].depth == 2
    # Counters armed by a recursive firing persist identically.
    assert await load(factory, user_id, chat_id) == {
        r: EntryState(sticky_remaining=1)
    }
    result = await tick(factory, user_id, chat_id, book_id, set())
    assert via_map(result) == {r: "sticky"}
    assert await load(factory, user_id, chat_id) == {}


async def test_tick_missing_or_foreign_returns_none_persists_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    other_id = await make_user(factory, name="other")
    chat_id = await make_chat(factory, user_id)
    book_id, ids = await make_book(
        factory,
        user_id,
        [{"label": "s", "name": "S", "keys": ["s"], "sticky_prompts": 2}],
    )
    _, other_ids = await make_book(
        factory,
        other_id,
        [{"label": "s", "name": "S", "keys": ["s"], "sticky_prompts": 2}],
        name="Foreign",
    )
    s = ids["s"]
    foreign_book, _ = await make_book(
        factory,
        other_id,
        [{"label": "f", "name": "F", "keys": ["f"]}],
        name="ForeignBook",
    )
    assert other_ids  # (the foreign user's own book exists and is valid)
    # Missing chat, foreign chat, missing book, foreign book: all None.
    assert await tick(factory, user_id, "no-such-chat", book_id, {s}) is None
    assert await tick(factory, other_id, chat_id, book_id, {s}) is None
    assert await tick(factory, user_id, chat_id, "no-such-book", {s}) is None
    assert await tick(factory, user_id, chat_id, foreign_book, {s}) is None
    # Nothing was persisted by any refused tick.
    assert raw_count(tmp_path) == 0
    assert await load(factory, user_id, chat_id) == {}


async def test_tick_constant_and_disabled_never_persist(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    book_id, ids = await make_book(
        factory,
        user_id,
        [
            {"label": "k", "name": "K", "keys": ["k"], "constant": True},
            {
                "label": "z", "name": "Z", "keys": ["z"],
                "enabled": False, "sticky_prompts": 3,
            },
        ],
    )
    k, z = ids["k"], ids["z"]
    # Even a direct hit cannot fire the disabled entry; the constant
    # entry fires every tick and never accumulates a state row.
    result = await tick(factory, user_id, chat_id, book_id, {z})
    assert via_map(result) == {k: "constant"}
    result = await tick(factory, user_id, chat_id, book_id, set())
    assert via_map(result) == {k: "constant"}
    assert await load(factory, user_id, chat_id) == {}
    assert raw_count(tmp_path, chat_id) == 0

# ---------------------------------------------------- (e) isolation


async def test_chat_isolation_same_entry(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_one = await make_chat(factory, user_id, "one")
    chat_two = await make_chat(factory, user_id, "two")
    book_id, ids = await make_book(
        factory,
        user_id,
        [{"label": "s", "name": "S", "keys": ["s"], "sticky_prompts": 2}],
    )
    s = ids["s"]
    result = await tick(factory, user_id, chat_one, book_id, {s})
    assert via_map(result) == {s: "key"}
    assert await load(factory, user_id, chat_one) == {
        s: EntryState(sticky_remaining=2)
    }
    # The same entry in the other chat has no state at all: its first
    # ticks behave as a first tick (no sticky leak across chats).
    assert await load(factory, user_id, chat_two) == {}
    result = await tick(factory, user_id, chat_two, book_id, set())
    assert result.activations == []
    result = await tick(factory, user_id, chat_two, book_id, {s})
    assert via_map(result) == {s: "key"}
    # And chat one's countdown is untouched by chat two's life.
    assert await load(factory, user_id, chat_one) == {
        s: EntryState(sticky_remaining=2)
    }


async def test_cross_user_isolation(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    other_id = await make_user(factory, name="other")
    chat_id = await make_chat(factory, user_id)
    book_id, ids = await make_book(
        factory,
        user_id,
        [{"label": "s", "name": "S", "keys": ["s"], "sticky_prompts": 2}],
    )
    s = ids["s"]
    result = await tick(factory, user_id, chat_id, book_id, {s})
    assert via_map(result) == {s: "key"}
    before = await load(factory, user_id, chat_id)
    assert before == {s: EntryState(sticky_remaining=2)}
    # Every operation by the other user against this chat refuses.
    assert await load(factory, other_id, chat_id) is None
    assert await save(
        factory, other_id, chat_id, {s: EntryState(sticky_remaining=9)}
    ) is False
    assert await clear(factory, other_id, chat_id) is False
    assert await tick(factory, other_id, chat_id, book_id, {s}) is None
    # The owner's persisted state is exactly as it was.
    assert await load(factory, user_id, chat_id) == before
    assert raw_count(tmp_path, chat_id) == 1

# ------------------------------------------------- (f) deletion behaviour


async def test_delete_entry_cascades_state_in_all_chats(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_one = await make_chat(factory, user_id, "one")
    chat_two = await make_chat(factory, user_id, "two")
    book_id, ids = await make_book(
        factory,
        user_id,
        [
            {"label": "gone", "name": "G", "keys": ["g"]},
            {"label": "kept", "name": "K", "keys": ["k"]},
        ],
    )
    gone, kept = ids["gone"], ids["kept"]
    live = EntryState(sticky_remaining=2)
    assert await save(factory, user_id, chat_one, {gone: live, kept: live})
    assert await save(factory, user_id, chat_two, {gone: live})
    assert raw_count(tmp_path, entry_id=gone) == 2
    async with factory() as session:
        assert (
            await lore_service.delete_entry(session, user_id, book_id, gone)
            is True
        )
    # The deleted entry's rows are gone in EVERY chat; the surviving
    # entry's row in the same chat is intact.
    assert raw_count(tmp_path, entry_id=gone) == 0
    assert raw_count(tmp_path, chat_one, entry_id=kept) == 1
    assert await load(factory, user_id, chat_one) == {kept: live}


async def test_tick_after_entry_delete_does_not_resurrect(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    book_id, ids = await make_book(
        factory,
        user_id,
        [{"label": "s", "name": "S", "keys": ["s"], "sticky_prompts": 2}],
    )
    s = ids["s"]
    result = await tick(factory, user_id, chat_id, book_id, {s})
    assert via_map(result) == {s: "key"}
    assert raw_count(tmp_path, chat_id) == 1
    async with factory() as session:
        assert (
            await lore_service.delete_entry(session, user_id, book_id, s)
            is True
        )
    assert raw_count(tmp_path, chat_id) == 0
    # A later tick (whose hit set still names the dead id, as a stale
    # caller might) saves only the book's CURRENT entries: no row
    # for the deleted entry is resurrected.
    result = await tick(factory, user_id, chat_id, book_id, {s})
    assert result is not None
    assert result.activations == []
    assert raw_count(tmp_path, chat_id) == 0
    assert await load(factory, user_id, chat_id) == {}


async def test_delete_chat_cascades_only_its_rows(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_one = await make_chat(factory, user_id, "one")
    chat_two = await make_chat(factory, user_id, "two")
    _, ids = await make_book(
        factory, user_id, [{"label": "s", "name": "S", "keys": ["s"]}]
    )
    s = ids["s"]
    live = EntryState(sticky_remaining=2)
    assert await save(factory, user_id, chat_one, {s: live})
    assert await save(factory, user_id, chat_two, {s: live})
    async with factory() as session:
        assert await chats_service.delete_chat(session, user_id, chat_one) is True
    assert raw_count(tmp_path, chat_one) == 0
    # The other chat's rows for the same entry survive.
    assert raw_count(tmp_path, chat_two, entry_id=s) == 1
    assert await load(factory, user_id, chat_two) == {s: live}


async def test_delete_lorebook_cascades_chain(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    book_id, ids = await make_book(
        factory,
        user_id,
        [
            {"label": "a", "name": "A", "keys": ["a"]},
            {"label": "b", "name": "B", "keys": ["b"]},
        ],
    )
    live = EntryState(sticky_remaining=2)
    assert await save(
        factory, user_id, chat_id, {ids["a"]: live, ids["b"]: live}
    )
    assert raw_count(tmp_path, chat_id) == 2
    async with factory() as session:
        assert await lore_service.delete_lorebook(session, user_id, book_id) is True
    # Book -> entries -> state rows: the whole chain cascades away.
    assert raw_count(tmp_path, chat_id) == 0
    assert await load(factory, user_id, chat_id) == {}

# --------------------------------- (g) preview stays clean-state


async def _preview_rows(factory, user_id, book_id, messages):
    async with factory() as session:
        entries = await lore_service.list_entries(session, user_id, book_id)
        assert entries is not None
        preview = preview_activation(entries, messages, 4, None)
    return {row["entry_id"]: row for row in preview["entries"]}, preview


async def test_preview_unaffected_by_persisted_states(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    book_id, ids = await make_book(
        factory,
        user_id,
        [
            {
                "label": "s", "name": "S", "content": "dragon lore",
                "keys": ["dragon"], "sticky_prompts": 2,
            }
        ],
    )
    s = ids["s"]
    # Clean-state baseline BEFORE any tick persists anything.
    rows_before, _ = await _preview_rows(factory, user_id, book_id, ["quiet"])
    assert rows_before[s]["status"] == "not_triggered"
    assert rows_before[s]["via"] is None
    # Persist a live sticky effect for this chat/book via real ticks.
    result = await tick(factory, user_id, chat_id, book_id, {s})
    assert via_map(result) == {s: "key"}
    assert await load(factory, user_id, chat_id) == {
        s: EntryState(sticky_remaining=2)
    }
    rows_on_disk = raw_count(tmp_path, chat_id)
    assert rows_on_disk == 1
    # Preview with NO key hit: the persisted sticky must NOT leak in --
    # the row is exactly the clean-state baseline row.
    rows_after, _ = await _preview_rows(factory, user_id, book_id, ["quiet"])
    assert rows_after[s] == rows_before[s]
    assert rows_after[s]["status"] == "not_triggered"
    # Preview WITH a key hit is a single clean tick: fires via "key".
    hit_rows, first = await _preview_rows(
        factory, user_id, book_id, ["a dragon appears"]
    )
    assert hit_rows[s]["status"] == "included"
    assert hit_rows[s]["via"] == "key"
    # Two consecutive previews are identical.
    _, second = await _preview_rows(
        factory, user_id, book_id, ["a dragon appears"]
    )
    assert second == first
    # Preview wrote nothing and consumed nothing: the persisted
    # sticky state is exactly where the ticks left it.
    assert raw_count(tmp_path, chat_id) == rows_on_disk
    assert await load(factory, user_id, chat_id) == {
        s: EntryState(sticky_remaining=2)
    }
