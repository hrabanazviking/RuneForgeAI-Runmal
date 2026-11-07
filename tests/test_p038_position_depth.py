"""P-038 acceptance: position & depth control.

Roadmap line: *entries inject at declared positions/depths in
the prompt (the composer contract honoured).* This battery pins:

- the placement vocabulary (positions, the role code table this
  slice defines, strict checkers, tolerant normalisers) in
  runmal.lorebooks.placement -- the single owner both layers
  import, closing the split gate finding F1 recorded;
- migration 0030 (PROVISIONAL: 0029 is reserved for P-037,
  building concurrently and banking first) adding the stored
  depth/role companions, with pre-0030 rows reading back
  depth None / role system;
- the DB store accepting at_depth entries whole (F1 closed):
  service CRUD, both transfer import paths, and the native
  at_depth book round-tripping through the store;
- both file legs carrying depth/role (transfer maps the
  world-info role code to the stored name; interop keeps its
  no-fabrication rule);
- preview rows reporting declared position + effective role /
  injection_depth, and the prompt inspector honouring placement
  end to end: the slot the inspector builds for an at_depth
  entry, composed with a history, splices at its depth with
  its role (the composer's S206 contract).

Entries are authored fresh in this module (P-005 discipline).
No mirror source was consulted.
"""

import dataclasses
import sqlite3

import pytest
from pydantic import ValidationError

from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.lorebooks import service as lore_service
from runmal.lorebooks.placement import (
    CODE_FROM_POSITION,
    CODE_FROM_ROLE,
    DEFAULT_AT_DEPTH_DEPTH,
    DEFAULT_ROLE,
    POSITION_FROM_CODE,
    POSITIONS,
    ROLE_FROM_CODE,
    VALID_POSITIONS,
    VALID_ROLES,
    Placement,
    check_depth,
    check_position,
    check_role,
    normalise_depth,
    normalise_position,
    normalise_role,
    placement_for,
)
from runmal.lorebooks.service import entry_to_dict


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory) -> str:
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        return user.id


async def make_book(factory, user_id, name="P-038 Book"):
    async with factory() as session:
        book = await lore_service.create_lorebook(session, user_id, name=name)
        return book.id


async def add_entry(factory, user_id, book_id, **kw):
    kw.setdefault("name", "entry")
    kw.setdefault("content", "lore content")
    async with factory() as session:
        return await lore_service.create_entry(session, user_id, book_id, **kw)


async def list_dicts(factory, user_id, book_id) -> list[dict]:
    async with factory() as session:
        entries = await lore_service.list_entries(session, user_id, book_id)
        return [entry_to_dict(e) for e in entries or []]


# --- 1. vocabulary + strict checkers -------------------------------------


def test_positions_vocabulary() -> None:
    assert POSITIONS == ("before_char", "after_char", "at_depth")
    assert VALID_POSITIONS == frozenset(POSITIONS)
    assert lore_service.VALID_POSITIONS == VALID_POSITIONS


def test_role_vocabulary_and_defaults() -> None:
    assert VALID_ROLES == ("system", "user", "assistant")
    assert DEFAULT_ROLE == "system"
    assert DEFAULT_AT_DEPTH_DEPTH == 4


def test_position_code_maps_are_inverses() -> None:
    assert POSITION_FROM_CODE == {0: "before_char", 1: "after_char", 4: "at_depth"}
    assert CODE_FROM_POSITION == {"before_char": 0, "after_char": 1, "at_depth": 4}


def test_role_code_maps_are_inverses() -> None:
    assert ROLE_FROM_CODE == {0: "system", 1: "user", 2: "assistant"}
    assert CODE_FROM_ROLE == {"system": 0, "user": 1, "assistant": 2}


@pytest.mark.parametrize("pos", ["before_char", "after_char", "at_depth"])
def test_check_position_accepts_the_three(pos) -> None:
    assert check_position(pos) == pos


@pytest.mark.parametrize("pos", ["before", "AT_DEPTH", "", None, 0, 4, True, "0"])
def test_check_position_rejects_everything_else(pos) -> None:
    with pytest.raises(ValueError):
        check_position(pos)


@pytest.mark.parametrize("d", [None, 0, 1, 4, 100])
def test_check_depth_accepts(d) -> None:
    assert check_depth(d) == d


@pytest.mark.parametrize("d", [True, False, -1, 1.0, 0.0, 2.5, "4", [], {}])
def test_check_depth_rejects(d) -> None:
    with pytest.raises(ValueError):
        check_depth(d)


@pytest.mark.parametrize("r", ["system", "user", "assistant"])
def test_check_role_accepts_names_only(r) -> None:
    assert check_role(r) == r


@pytest.mark.parametrize("r", ["System", "admin", "", None, 0, 1, True])
def test_check_role_rejects_codes_and_strangers(r) -> None:
    with pytest.raises(ValueError):
        check_role(r)


# --- 2. tolerant normalisers ----------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("before_char", "before_char"),
        ("after_char", "after_char"),
        ("at_depth", "at_depth"),
        (0, "before_char"),
        (1, "after_char"),
        (4, "at_depth"),
        (4.0, "at_depth"),
        ("0", "before_char"),
        ("4", "at_depth"),
        (2, "before_char"),  # authors-note codes: no lore semantics claimed
        (3, "before_char"),
        (7, "before_char"),
        (-1, "before_char"),
        (None, "before_char"),
        (True, "before_char"),
        ("unknown", "before_char"),
        ("", "before_char"),
    ],
)
def test_normalise_position(raw, expected) -> None:
    assert normalise_position(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, None),
        (True, None),  # bool is not 1: the bool-is-int trap stays shut
        (False, None),
        (0, 0),
        (4, 4),
        (100, 100),
        (-1, None),  # negative degrades to undeclared, never clamped to 0
        (-2, None),
        (4.0, 4),
        (0.0, 0),
        (-1.0, None),
        (2.5, None),
        ("4", 4),
        (" 4 ", 4),
        ("4.0", 4),
        ("-2", None),
        ("deep", None),
        ("", None),
        ([], None),
    ],
)
def test_normalise_depth(raw, expected) -> None:
    assert normalise_depth(raw) == expected


@pytest.mark.parametrize(
    "raw,expected",
    [
        (None, "system"),
        (True, "system"),  # bool must not become code 1 / user
        (False, "system"),
        (0, "system"),
        (1, "user"),
        (2, "assistant"),
        (3, "system"),
        (-1, "system"),
        (0.0, "system"),
        (1.0, "user"),
        (2.0, "assistant"),
        (1.5, "system"),
        ("0", "system"),
        ("1", "user"),
        ("2", "assistant"),
        ("system", "system"),
        ("SYSTEM", "system"),
        ("User", "user"),
        ("admin", "system"),
        ("", "system"),
        ([], "system"),
    ],
)
def test_normalise_role(raw, expected) -> None:
    assert normalise_role(raw) == expected


# --- 3. placement resolution -----------------------------------------------


@pytest.mark.parametrize(
    "position,depth,role,expected",
    [
        ("before_char", None, "system", ("lore_before", None, "system")),
        ("before_char", 2, "user", ("lore_before", None, "system")),
        ("after_char", None, "system", ("lore_after", None, "system")),
        ("after_char", 5, "assistant", ("lore_after", None, "system")),
        ("at_depth", 2, "user", ("lore_before", 2, "user")),
        ("at_depth", 0, "assistant", ("lore_before", 0, "assistant")),
        ("at_depth", None, "system", ("lore_before", 4, "system")),
        ("at_depth", None, None, ("lore_before", 4, "system")),
        ("at_depth", -1, "admin", ("lore_before", 4, "system")),
        ("at_depth", True, "user", ("lore_before", 4, "user")),
        ("at_depth", 7, "assistant", ("lore_before", 7, "assistant")),
        ("sideways", None, "user", ("lore_before", None, "system")),
        (None, None, None, ("lore_before", None, "system")),
    ],
)
def test_placement_for_table(position, depth, role, expected) -> None:
    placement = placement_for(position, depth, role)
    assert isinstance(placement, Placement)
    assert (placement.kind, placement.depth, placement.role) == expected


def test_placement_is_frozen() -> None:
    placement = placement_for("at_depth", 1, "user")
    with pytest.raises(dataclasses.FrozenInstanceError):
        placement.kind = "lore_after"  # type: ignore[misc]


# --- 4. migration 0030 (PROVISIONAL) ----------------------------------------


def test_migration_head_is_0030_provisional_p038() -> None:
    # 0029 is P-037's (scan depth & context windows), banked first;
    # 0030 stands as numbered. Merged sequence composed at banking.
    revisions = [m[0] for m in MIGRATIONS]
    assert revisions[-1] == "0038"
    assert revisions[-12:] == ["0027", "0028", "0029", "0030", "0031", "0032", "0033", "0034", "0035", "0036", "0037", "0038"]  # tail moved by P-065 (PROVISIONAL 0036)


def test_migration_0030_columns_on_fresh_db(tmp_path) -> None:
    db_path = tmp_path / "fresh.db"
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1]: row for row in conn.execute("PRAGMA table_info(lore_entries)")}
    finally:
        conn.close()
    assert "depth" in cols and "role" in cols
    assert cols["depth"][3] == 0  # nullable: undeclared is a stored state
    assert cols["role"][3] == 1  # NOT NULL
    assert "system" in str(cols["role"][4])  # DEFAULT 'system'


def test_pre_0030_db_upgrades_with_rows_intact(tmp_path) -> None:
    # Build a 0028-era database by hand (raw sqlite, the migrate
    # runner's own road), seed one entry, then migrate to head:
    # the row reads back depth None / role system -- exactly its
    # old behaviour.
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(revision TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for revision, _desc, module in MIGRATIONS:
            if revision == "0030":
                continue
            module.upgrade(conn)
            conn.execute(
                "INSERT INTO schema_migrations (revision, applied_at) VALUES (?, ?)",
                (revision, "2026-11-06T00:00:00+00:00"),
            )
            conn.commit()
        conn.execute(
            "INSERT INTO lorebooks (id, user_id, name, description, scan_depth,"
            " token_budget, created_at) VALUES ('b1', 'u1', 'Old Book', '', 4, NULL,"
            " '2026-11-06T00:00:00')"
        )
        conn.execute(
            "INSERT INTO lore_entries (id, lorebook_id, user_id, name, content,"
            " keys_json, secondary_keys_json, selective_logic, inclusion_group,"
            " group_weight, probability, priority, position, enabled, constant,"
            " vectorised, case_sensitive, whole_word, sticky_prompts,"
            " cooldown_prompts, delay_prompts, created_at, updated_at) VALUES"
            " ('e1', 'b1', 'u1', 'Legacy', 'old lore', '[]', '[]', 'and_any', '',"
            " 100, 100, 100, 'before_char', 1, 0, 0, 0, 1, 0, 0, 0,"
            " '2026-11-06T00:00:00', NULL)"
        )
        conn.commit()
    finally:
        conn.close()
    applied = migrate_to_head(db_path)
    assert applied == ["0030"]
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute("SELECT depth, role FROM lore_entries WHERE id = 'e1'").fetchone()
    finally:
        conn.close()
    assert row == (None, "system")


# --- 5. service CRUD ----------------------------------------------------------


async def test_service_create_at_depth_round_trips(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await make_book(factory, user_id)
    await add_entry(
        factory, user_id, book_id, name="deep", position="at_depth", depth=2, role="user"
    )
    (row,) = await list_dicts(factory, user_id, book_id)
    assert row["position"] == "at_depth" and row["depth"] == 2 and row["role"] == "user"


async def test_service_defaults_are_undeclared_and_system(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await make_book(factory, user_id)
    await add_entry(factory, user_id, book_id, name="plain")
    (row,) = await list_dicts(factory, user_id, book_id)
    assert row["position"] == "before_char" and row["depth"] is None and row["role"] == "system"


async def test_service_at_depth_accepted_f1_closed(tmp_path) -> None:
    # Gate finding F1: create_entry used to raise ValueError on
    # at_depth (VALID_POSITIONS held only before/after). It must
    # now store the entry.
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await make_book(factory, user_id)
    entry = await add_entry(factory, user_id, book_id, name="f1", position="at_depth")
    assert entry.position == "at_depth"


@pytest.mark.parametrize(
    "kw",
    [
        {"depth": -1},
        {"depth": "4"},
        {"depth": True},
        {"role": "admin"},
        {"role": "System"},
        {"role": 1},
        {"position": "sideways"},
    ],
)
async def test_service_create_invalid_placement_raises(tmp_path, kw) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await make_book(factory, user_id)
    kw.setdefault("position", "at_depth")
    with pytest.raises(ValueError):
        await add_entry(factory, user_id, book_id, name="bad", **kw)


async def test_service_update_changes_placement(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await make_book(factory, user_id)
    entry = await add_entry(factory, user_id, book_id, name="upd")
    async with factory() as session:
        updated = await lore_service.update_entry(
            session, user_id, book_id, entry.id,
            position="at_depth", depth=3, role="assistant",
        )
        assert updated is not None
        row = entry_to_dict(updated)
    assert row["position"] == "at_depth" and row["depth"] == 3 and row["role"] == "assistant"


async def test_service_update_can_clear_depth(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await make_book(factory, user_id)
    entry = await add_entry(factory, user_id, book_id, name="clr", position="at_depth", depth=2)
    async with factory() as session:
        updated = await lore_service.update_entry(session, user_id, book_id, entry.id, depth=None)
        assert updated is not None
        assert entry_to_dict(updated)["depth"] is None


async def test_service_before_char_stores_companions_but_placement_ignores(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await make_book(factory, user_id)
    await add_entry(
        factory, user_id, book_id, name="stored", position="before_char", depth=9, role="user"
    )
    (row,) = await list_dicts(factory, user_id, book_id)
    assert row["depth"] == 9 and row["role"] == "user"  # preserved on storage
    placement = placement_for(row["position"], row["depth"], row["role"])
    assert (placement.kind, placement.depth, placement.role) == ("lore_before", None, "system")


# --- 6. API schemas (thin) ------------------------------------------------------


def test_api_entry_create_defaults_and_validation() -> None:
    from runmal.lorebooks.router import EntryCreate, EntryUpdate

    body = EntryCreate(name="x", content="c")
    assert body.position == "before_char" and body.depth is None and body.role == "system"
    deep = EntryCreate(name="x", content="c", position="at_depth", depth=0, role="user")
    assert deep.depth == 0 and deep.role == "user"
    with pytest.raises(ValidationError):
        EntryCreate(name="x", content="c", depth=-1)
    with pytest.raises(ValidationError):
        EntryUpdate(depth=-1)
    assert EntryUpdate().depth is None and EntryUpdate().role is None


# --- 7. transfer (the DB file legs) ----------------------------------------------


def _gale_worldinfo() -> dict:
    return {
        "name": "Gale Book",
        "entries": {
            "0": {
                "comment": "The Gale-Bell",
                "content": "The gale-bell rings only when nobody is listening.",
                "key": ["gale-bell", "bell"],
                "keysecondary": ["weather"],
                "constant": False,
                "disable": False,
                "order": 300,
                "position": 4,
                "depth": 4,
                "role": 0,
            }
        },
    }


def _native_book() -> dict:
    return {
        "format": "runmal-lorebook",
        "version": 1,
        "name": "Native Book",
        "description": "",
        "scan_depth": 4,
        "token_budget": None,
        "entries": [
            {
                "name": "The Ferry",
                "content": "The ferry crosses at dawn.",
                "keys": ["ferry"],
                "secondary_keys": ["river"],
                "position": "at_depth",
                "enabled": True,
                "constant": False,
                "priority": 90,
            },
            {
                "name": "Night Bell",
                "content": "The bell speaks as a user.",
                "keys": ["bell"],
                "position": "at_depth",
                "depth": 2,
                "role": "user",
                "enabled": True,
                "constant": True,
            },
            {
                "name": "Coded Role",
                "content": "Role arrived as a code in a native file.",
                "keys": [],
                "position": "at_depth",
                "depth": 1,
                "role": 2,
                "enabled": True,
                "constant": True,
            },
        ],
    }


def test_parse_import_worldinfo_maps_at_depth_companions() -> None:
    from runmal.lorebooks.transfer import parse_import

    _book, entries = parse_import(_gale_worldinfo())
    (gale,) = entries
    assert gale["position"] == "at_depth"  # code 4 mapped, not collapsed (F1)
    assert gale["depth"] == 4 and gale["role"] == "system"  # code 0 -> name


@pytest.mark.parametrize(
    "code,expected", [(0, "before_char"), (1, "after_char"), (4, "at_depth"), (7, "before_char")]
)
def test_parse_import_worldinfo_position_codes(code, expected) -> None:
    from runmal.lorebooks.transfer import parse_import

    entry = {"comment": "E", "content": "x", "key": [], "position": code}
    data = {"name": "B", "entries": {"0": entry}}
    _book, entries = parse_import(data)
    assert entries[0]["position"] == expected


def test_parse_import_native_carries_depth_and_role() -> None:
    from runmal.lorebooks.transfer import parse_import

    _book, entries = parse_import(_native_book())
    ferry, bell, coded = entries
    assert ferry["position"] == "at_depth" and ferry["depth"] is None and ferry["role"] == "system"
    assert bell["depth"] == 2 and bell["role"] == "user"
    assert coded["depth"] == 1 and coded["role"] == "assistant"  # code tolerated on the native leg


def test_validate_parsed_book_prepares_placement() -> None:
    from runmal.lorebooks.transfer import parse_import, validate_parsed_book

    book_fields, entry_fields = parse_import(_native_book())
    prepared = validate_parsed_book(book_fields, entry_fields)
    assert prepared[0]["depth"] is None and prepared[0]["role"] == "system"
    assert prepared[1]["depth"] == 2 and prepared[1]["role"] == "user"
    assert prepared[2]["depth"] == 1 and prepared[2]["role"] == "assistant"


def test_export_book_emits_depth_and_role_for_every_entry() -> None:
    from runmal.lorebooks.transfer import export_book

    book = {"name": "B", "description": "", "scan_depth": 4, "token_budget": None}
    entries = [
        {
            "name": "deep", "content": "x", "keys": [], "secondary_keys": [],
            "priority": 100, "position": "at_depth", "depth": 2, "role": "user",
            "enabled": True, "constant": False, "case_sensitive": False,
            "whole_word": True, "sticky_prompts": 0, "cooldown_prompts": 0,
            "delay_prompts": 0,
        },
        {
            "name": "plain", "content": "y", "keys": [], "secondary_keys": [],
            "priority": 100, "position": "before_char",
            "enabled": True, "constant": False, "case_sensitive": False,
            "whole_word": True, "sticky_prompts": 0, "cooldown_prompts": 0,
            "delay_prompts": 0,
        },
    ]
    out = export_book(book, entries)
    deep, plain = out["entries"]
    assert deep["depth"] == 2 and deep["role"] == "user"
    # The native leg emits the modelled fields unconditionally
    # (the transfer pattern since P-032): a plain entry exports
    # depth None / role system rather than omitting the keys.
    assert plain["depth"] is None and plain["role"] == "system"


async def test_import_book_transactional_stores_at_depth_book_whole(tmp_path) -> None:
    # F1's other half: the transactional import used to refuse
    # this book whole (ValueError on at_depth) and leave nothing.
    from runmal.lorebooks.transfer import import_book_transactional

    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        book = await import_book_transactional(session, user_id, _native_book())
        book_id = book.id
    rows = await list_dicts(factory, user_id, book_id)
    assert len(rows) == 3
    by_name = {r["name"]: r for r in rows}
    assert by_name["The Ferry"]["position"] == "at_depth"
    assert by_name["The Ferry"]["depth"] is None and by_name["The Ferry"]["role"] == "system"
    assert by_name["Night Bell"]["depth"] == 2 and by_name["Night Bell"]["role"] == "user"


async def test_import_book_service_loop_stores_at_depth(tmp_path) -> None:
    from runmal.lorebooks.transfer import import_book

    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        book = await import_book(session, user_id, _gale_worldinfo())
        book_id = book.id
    (row,) = await list_dicts(factory, user_id, book_id)
    assert row["position"] == "at_depth" and row["depth"] == 4 and row["role"] == "system"


async def test_store_round_trip_native_book_is_fixed_point(tmp_path) -> None:
    from runmal.lorebooks.transfer import export_book, import_book_transactional, parse_import

    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        book = await import_book_transactional(session, user_id, _native_book())
        book_id = book.id
        stored = await lore_service.list_entries(session, user_id, book_id)
        exported = export_book(
            lore_service.lorebook_to_dict(book),
            [entry_to_dict(e) for e in stored or []],
        )
    _book_fields, parsed_entries = parse_import(_native_book())
    assert sorted(exported["entries"], key=lambda e: e["name"]) == sorted(
        parsed_entries, key=lambda e: e["name"]
    )


# --- 8. interop (the file layer) -------------------------------------------------


def test_interop_gale_role_is_a_name_and_exports_as_code() -> None:
    from runmal.lorebooks.interop import export_worldinfo, parse_lorebook_file

    book = parse_lorebook_file(_gale_worldinfo())
    (gale,) = book.entries
    assert gale.position == "at_depth" and gale.depth == 4
    assert gale.role == "system"  # P-038: the code table resolves 0 -> system
    out = export_worldinfo(book)
    assert out["entries"]["0"]["position"] == 4
    assert out["entries"]["0"]["depth"] == 4 and out["entries"]["0"]["role"] == 0


def test_interop_ferry_no_fabrication() -> None:
    from runmal.lorebooks.interop import export_native, export_worldinfo, parse_lorebook_file

    book = parse_lorebook_file(_native_book())
    ferry = book.entries[0]
    assert ferry.position == "at_depth" and ferry.depth is None and ferry.role == "system"
    world = export_worldinfo(book)
    # The Ferry declared neither depth nor role: the world-info
    # export must not invent them (no-fabrication), though its
    # position code is written.
    assert world["entries"]["0"]["position"] == 4
    assert "depth" not in world["entries"]["0"] and "role" not in world["entries"]["0"]
    # The Night Bell declared both as native data: depth rides,
    # role rides as its code.
    assert world["entries"]["1"]["depth"] == 2 and world["entries"]["1"]["role"] == 1
    native = export_native(book)
    assert native["entries"][0]["depth"] is None and native["entries"][0]["role"] == "system"
    assert native["entries"][1]["depth"] == 2 and native["entries"][1]["role"] == "user"


def test_interop_fixed_points_hold_with_placement() -> None:
    from runmal.lorebooks.interop import (
        export_native,
        export_worldinfo,
        parse_lorebook_file,
    )

    for source in (_gale_worldinfo(), _native_book()):
        book = parse_lorebook_file(source)
        world_once = export_worldinfo(book)
        assert export_worldinfo(parse_lorebook_file(world_once)) == world_once
        native_once = export_native(book)
        assert export_native(parse_lorebook_file(native_once)) == native_once


def test_interop_position_tables_are_placements() -> None:
    from runmal.lorebooks import interop

    assert interop.POSITION_FROM_CODE is POSITION_FROM_CODE
    assert interop.CODE_FROM_POSITION is CODE_FROM_POSITION


# --- 9. preview placement fields ---------------------------------------------------


async def _preview_rows(factory, user_id, book_id) -> list[dict]:
    from runmal.lorebooks.preview import preview_activation

    async with factory() as session:
        entries = await lore_service.list_entries(session, user_id, book_id)
        book = await lore_service.get_lorebook(session, user_id, book_id)
        assert entries is not None and book is not None
        preview = preview_activation(entries, [], book.scan_depth, book.token_budget)
    return preview["entries"]


async def test_preview_at_depth_declared(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await make_book(factory, user_id)
    entry = await add_entry(
        factory, user_id, book_id, name="deep", position="at_depth",
        depth=2, role="user", constant=True,
    )
    rows = await _preview_rows(factory, user_id, book_id)
    (row,) = [r for r in rows if r["entry_id"] == entry.id]
    assert row["position"] == "at_depth" and row["role"] == "user" and row["injection_depth"] == 2
    assert row["status"] == "included"
    # The row's plain "depth" key is still the recursion depth
    # (P-031), a different number from the injection depth.
    assert row["depth"] == 0


async def test_preview_at_depth_undeclared_materialises_default(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await make_book(factory, user_id)
    entry = await add_entry(
        factory, user_id, book_id, name="deep2", position="at_depth", constant=True
    )
    rows = await _preview_rows(factory, user_id, book_id)
    (row,) = [r for r in rows if r["entry_id"] == entry.id]
    assert row["injection_depth"] == DEFAULT_AT_DEPTH_DEPTH and row["role"] == "system"


async def test_preview_after_char_effective_role_is_system(tmp_path) -> None:
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await make_book(factory, user_id)
    entry = await add_entry(
        factory, user_id, book_id, name="after", position="after_char",
        depth=5, role="user", constant=True,
    )
    rows = await _preview_rows(factory, user_id, book_id)
    (row,) = [r for r in rows if r["entry_id"] == entry.id]
    # Stored companions survive (see the service test) but the
    # EFFECTIVE placement for after_char forces system / None.
    assert row["position"] == "after_char" and row["role"] == "system"
    assert row["injection_depth"] is None


# --- 10. inspector + composer contract ----------------------------------------------


async def test_inspector_trace_honours_placement(tmp_path) -> None:
    from runmal.prompt.inspect import inspect_prompt

    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await make_book(factory, user_id)
    before = await add_entry(
        factory, user_id, book_id, name="b", content="before lore", constant=True
    )
    after = await add_entry(
        factory, user_id, book_id, name="a", content="after lore",
        position="after_char", constant=True,
    )
    deep = await add_entry(
        factory, user_id, book_id, name="d", content="deep lore",
        position="at_depth", depth=1, role="user", constant=True,
    )
    messages = ["m0", "m1", "m2", "m3"]
    async with factory() as session:
        trace = await inspect_prompt(session, user_id, lorebook_ids=[book_id], messages=messages)
    assert trace is not None
    slots = {s["slot_id"]: s for s in trace["slots"]}
    assert slots[f"lore/{before.id}"]["kind"] == "lore_before"
    assert slots[f"lore/{before.id}"]["role"] == "system"
    assert slots[f"lore/{after.id}"]["kind"] == "lore_after"
    assert slots[f"lore/{deep.id}"]["kind"] == "lore_before"
    assert slots[f"lore/{deep.id}"]["role"] == "user"
    assert slots[f"lore/{deep.id}"]["status"] == "included"


def _row(**kw) -> dict:
    row = {
        "entry_id": "e1", "name": "deep", "status": "included", "via": "constant",
        "matched_primary": [], "content": "deep lore", "position": "at_depth",
        "role": "user", "injection_depth": 1,
    }
    row.update(kw)
    return row


def test_lore_slot_for_at_depth_row_carries_depth_role_and_order() -> None:
    from runmal.prompt.inspect import _lore_slot
    from runmal.prompt.slots import baseline_order

    slot = _lore_slot(_row(), "lore/e1", "lorebook:B")
    assert slot.kind == "lore_before" and slot.role == "user" and slot.depth == 1
    # Load-bearing: the slot must sort AFTER history or the
    # composer finds no history to splice into (S206 contract).
    assert slot.order > baseline_order("history")
    assert slot.order == baseline_order("authors_note")


def test_lore_slot_for_after_and_before_rows() -> None:
    from runmal.prompt.inspect import _lore_slot

    after = _lore_slot(
        _row(position="after_char", role="system", injection_depth=None), "lore/e1", "p"
    )
    assert after.kind == "lore_after" and after.role == "system" and after.depth is None
    before = _lore_slot(
        _row(position="before_char", role="system", injection_depth=None), "lore/e1", "p"
    )
    assert before.kind == "lore_before" and before.role == "system" and before.depth is None


def _history_slot(parts) -> object:
    from runmal.prompt.slots import Slot, baseline_order

    return Slot(
        id="history", kind="history", role="user",
        order=baseline_order("history"), splittable=True, parts=tuple(parts),
    )


def test_compose_splices_inspector_at_depth_slot_at_its_depth() -> None:
    from runmal.prompt.composer import compose
    from runmal.prompt.inspect import _lore_slot

    slot = _lore_slot(_row(), "lore/e1", "lorebook:B")
    result = compose(
        [_history_slot(["m0", "m1", "m2", "m3"]), slot],
        context_limit=4096, reserve_response=512,
    )
    assert [(m.slot_id, m.role) for m in result.messages] == [
        ("history", "user"),
        ("lore/e1", "user"),
        ("history", "user"),
    ]
    head, lore_msg, tail = result.messages
    assert "m0" in head.content and "m2" in head.content and "m3" not in head.content
    assert lore_msg.content == "deep lore"
    assert tail.content.strip() == "m3"


def test_compose_depth_zero_lands_after_history() -> None:
    from runmal.prompt.composer import compose
    from runmal.prompt.inspect import _lore_slot

    slot = _lore_slot(_row(injection_depth=0, role="assistant"), "lore/e1", "p")
    result = compose([_history_slot(["m0", "m1"]), slot], context_limit=4096, reserve_response=512)
    assert [m.slot_id for m in result.messages] == ["history", "lore/e1"]
    assert result.messages[1].role == "assistant"


def test_compose_no_history_depth_slot_emits_at_its_order() -> None:
    from runmal.prompt.composer import compose
    from runmal.prompt.inspect import _lore_slot
    from runmal.prompt.slots import make_slot

    slots = [
        make_slot("main_system", "system", "SYS", required=True, id="system/main"),
        make_slot("lore_before", "system", "before lore", id="lore/b"),
        _lore_slot(_row(), "lore/e1", "p"),
        make_slot("post_history", "system", "PH", id="post"),
    ]
    result = compose(slots, context_limit=4096, reserve_response=512)
    # No history to splice into: the depth slot falls through to
    # normal emission at its (depth-injection) order position --
    # after the plain lore, before post-history.
    assert [m.slot_id for m in result.messages] == ["system/main", "lore/b", "lore/e1", "post"]
