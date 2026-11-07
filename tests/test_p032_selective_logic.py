"""P-032 acceptance: selective key logic for lorebook entries.

Roadmap line: *Selective logic: the four secondary-key modes
(and_any / and_all / not_any / not_all) for lorebook entries.*

Contract under test:
- ``runmal.lorebooks.logic`` is a pure module owning the four mode
  names, their public world-info codes (and_any=0, not_all=1,
  not_any=2, and_all=3 -- file-format order, not prose order), a
  strict checker, tolerant name/code normalisers, and the
  ``secondary_gate`` truth table. With no usable secondary keys the
  gate always passes: the primary match alone decides.
- The S202 scanner applies the gate: an entry fires only when a
  primary key matched AND the gate passes for its usable secondary
  keys. Primary-unmatched entries never fire, in any mode.
- The stored entry carries ``selective_logic`` (migration 0024,
  default ``and_any``); the service validates it strictly, the API
  surfaces a bad mode as 422, and ``entry_to_dict`` reports it.
- Import/export carry it: world-info ``selectiveLogic`` codes map
  to names tolerantly, native files carry the name, native export
  emits the name, and world-info export from native dicts emits
  the code -- except ``and_any``, which is never fabricated.

Helper patterns mirror tests/test_p029_provenance_on_import.py and
tests/test_s201_lorebooks.py; the scan helper mirrors
tests/test_s202_scan.py, extended with a selective_logic kwarg.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.lorebooks import service, transfer
from runmal.lorebooks.interop import (
    export_worldinfo,
    parse_lorebook_file,
    worldinfo_from_native,
)
from runmal.lorebooks.logic import (
    DEFAULT_SELECTIVE_LOGIC,
    LOGIC_BY_WORLDINFO_CODE,
    SELECTIVE_LOGICS,
    WORLDINFO_CODE_BY_LOGIC,
    check_selective_logic,
    normalise_selective_logic,
    secondary_gate,
    selective_logic_from_code,
    worldinfo_code,
)
from runmal.lorebooks.scan import ScanEntry, scan_entries
from runmal.lorebooks.service import entry_to_dict

CORPUS = Path(__file__).parent / "fixtures" / "interop"

ALL_MODES = ("and_any", "and_all", "not_any", "not_all")

# ---------------------------------------------------------------- helpers


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


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


def e(eid, **kw):
    """ScanEntry helper in test_s202_scan.py's style, extended so a
    selective_logic kwarg passes straight through; without it the
    dataclass default applies (the legacy-behaviour case)."""
    base = dict(
        enabled=True,
        constant=False,
        keys=(),
        secondary_keys=(),
        whole_word=True,
        case_sensitive=False,
    )
    base.update(kw)
    return ScanEntry(id=eid, **base)


def service_entry_dict(mode, **over):
    """A service-shaped (entry_to_dict-shaped) entry dict."""
    entry = {
        "name": "E",
        "content": "c",
        "keys": ["dragon"],
        "secondary_keys": ["fire"],
        "priority": 100,
        "position": "before_char",
        "enabled": True,
        "constant": False,
        "case_sensitive": False,
        "whole_word": True,
        "sticky_prompts": 0,
        "cooldown_prompts": 0,
        "delay_prompts": 0,
        "selective_logic": mode,
    }
    entry.update(over)
    return entry


BOOK_DICT = {
    "name": "B",
    "description": "",
    "scan_depth": 4,
    "token_budget": None,
}


def worldinfo_payload(**entry_over):
    entry = {
        "comment": "E",
        "content": "c",
        "key": ["dragon"],
        "keysecondary": ["fire"],
        "order": 100,
        "position": 0,
    }
    entry.update(entry_over)
    return {"name": "W", "entries": {"0": entry}}


def native_payload(mode_marker, *, include=True):
    entry = service_entry_dict("and_any")
    if include:
        entry["selective_logic"] = mode_marker
    else:
        entry.pop("selective_logic")
    return {
        "name": "N",
        "description": "",
        "scan_depth": 4,
        "token_budget": None,
        "entries": [entry],
    }


# ------------------------------------------------------- (a) pure gate

# (mode, secondary_count, matched_count, expected): the full truth
# table over the pinned situations, including the (0, 0) row where
# the empty-secondary rule makes every mode pass.
TRUTH_TABLE = [
    # secondary_count == 0: logic not applied, primary alone decides
    ("and_any", 0, 0, True),
    ("and_all", 0, 0, True),
    ("not_any", 0, 0, True),
    ("not_all", 0, 0, True),
    # one secondary, matched
    ("and_any", 1, 1, True),
    ("and_all", 1, 1, True),
    ("not_any", 1, 1, False),
    ("not_all", 1, 1, False),
    # one secondary, unmatched
    ("and_any", 1, 0, False),
    ("and_all", 1, 0, False),
    ("not_any", 1, 0, True),
    ("not_all", 1, 0, True),
    # two secondaries, none matched
    ("and_any", 2, 0, False),
    ("and_all", 2, 0, False),
    ("not_any", 2, 0, True),
    ("not_all", 2, 0, True),
    # two secondaries, one matched
    ("and_any", 2, 1, True),
    ("and_all", 2, 1, False),
    ("not_any", 2, 1, False),
    ("not_all", 2, 1, True),
    # two secondaries, all matched
    ("and_any", 2, 2, True),
    ("and_all", 2, 2, True),
    ("not_any", 2, 2, False),
    ("not_all", 2, 2, False),
    # three secondaries, one matched
    ("and_any", 3, 1, True),
    ("and_all", 3, 1, False),
    ("not_any", 3, 1, False),
    ("not_all", 3, 1, True),
    # three secondaries, two matched
    ("and_any", 3, 2, True),
    ("and_all", 3, 2, False),
    ("not_any", 3, 2, False),
    ("not_all", 3, 2, True),
]


@pytest.mark.parametrize(
    "mode,secondary_count,matched_count,expected", TRUTH_TABLE
)
def test_secondary_gate_truth_table(mode, secondary_count, matched_count, expected):
    assert (
        secondary_gate(
            mode,
            secondary_count=secondary_count,
            matched_count=matched_count,
        )
        is expected
    )


@pytest.mark.parametrize("bad_mode", ["bogus", "AND_ANY", "and-any", "", None, 0, 2])
def test_secondary_gate_rejects_bad_mode(bad_mode):
    with pytest.raises(ValueError):
        secondary_gate(bad_mode, secondary_count=1, matched_count=0)


@pytest.mark.parametrize(
    "secondary_count,matched_count",
    [
        (1, 2),  # matched > count
        (0, 1),  # matched > count at zero
        (-1, 0),  # negative secondary_count
        (1, -1),  # negative matched_count
        (-2, -3),  # both negative
    ],
)
def test_secondary_gate_rejects_bad_counts(secondary_count, matched_count):
    with pytest.raises(ValueError):
        secondary_gate(
            "and_any",
            secondary_count=secondary_count,
            matched_count=matched_count,
        )


@pytest.mark.parametrize(
    "secondary_count,matched_count",
    [(True, 0), (1, True), (False, 0), (1, False), (1.0, 0), (1, 0.0), ("1", 0)],
)
def test_secondary_gate_rejects_non_int_counts(secondary_count, matched_count):
    with pytest.raises(ValueError):
        secondary_gate(
            "and_any",
            secondary_count=secondary_count,
            matched_count=matched_count,
        )


# ------------------------------------------------- (b) representation


def test_constants_and_code_table():
    assert SELECTIVE_LOGICS == frozenset(ALL_MODES)
    assert DEFAULT_SELECTIVE_LOGIC == "and_any"
    # Public file-format codes; NOT prose order (pins 1 and 2 too).
    assert WORLDINFO_CODE_BY_LOGIC == {
        "and_any": 0,
        "not_all": 1,
        "not_any": 2,
        "and_all": 3,
    }
    assert LOGIC_BY_WORLDINFO_CODE == {
        0: "and_any",
        1: "not_all",
        2: "not_any",
        3: "and_all",
    }


@pytest.mark.parametrize(
    "code,expected",
    [
        (0, "and_any"),
        (1, "not_all"),
        (2, "not_any"),  # pinned: code 2 is not_any
        (3, "and_all"),  # pinned: code 3 is and_all
    ],
)
def test_selective_logic_from_code_exact(code, expected):
    assert selective_logic_from_code(code) == expected


@pytest.mark.parametrize(
    "value,expected",
    [
        (None, "and_any"),
        (True, "and_any"),
        (False, "and_any"),
        ("2", "not_any"),
        (2.0, "not_any"),
        ("3", "and_all"),
        (7, "and_any"),
        (-1, "and_any"),
        (99, "and_any"),
        ("junk", "and_any"),
        ("", "and_any"),
    ],
)
def test_selective_logic_from_code_tolerant(value, expected):
    assert selective_logic_from_code(value) == expected


@pytest.mark.parametrize("mode", ALL_MODES)
def test_check_selective_logic_accepts_canonical(mode):
    assert check_selective_logic(mode) == mode


@pytest.mark.parametrize(
    "bad", ["AND_ANY", "and-any", "And_Any", "and any", "", "bogus", 0, 1, None, True]
)
def test_check_selective_logic_rejects_non_canonical(bad):
    with pytest.raises(ValueError):
        check_selective_logic(bad)


@pytest.mark.parametrize("mode", ALL_MODES)
def test_normalise_selective_logic_canonical_passthrough(mode):
    assert normalise_selective_logic(mode) == mode


@pytest.mark.parametrize(
    "garbage", ["bogus", "AND_ANY", "and-any", "", None, 0, 2, True, ["and_any"]]
)
def test_normalise_selective_logic_garbage_defaults(garbage):
    assert normalise_selective_logic(garbage) == "and_any"


@pytest.mark.parametrize(
    "mode,code",
    [("and_any", 0), ("not_all", 1), ("not_any", 2), ("and_all", 3)],
)
def test_worldinfo_code_round_trips(mode, code):
    assert worldinfo_code(mode) == code
    assert selective_logic_from_code(worldinfo_code(mode)) == mode


@pytest.mark.parametrize("bad", ["bogus", "AND_ANY", None, 0])
def test_worldinfo_code_rejects_bad_mode(bad):
    with pytest.raises(ValueError):
        worldinfo_code(bad)


# -------------------------------------------------------- (c) scanning

# situation -> (secondary_keys, messages, {mode: fires?})
SCAN_SITUATIONS = {
    "no_secondaries": (
        (),
        ["a dragon appears"],
        {"and_any": True, "and_all": True, "not_any": True, "not_all": True},
    ),
    "one_matched": (
        ("fire",),
        ["a dragon breathes fire"],
        {"and_any": True, "and_all": True, "not_any": False, "not_all": False},
    ),
    "one_unmatched": (
        ("fire",),
        ["a dragon appears"],
        {"and_any": False, "and_all": False, "not_any": True, "not_all": True},
    ),
    "two_none": (
        ("fire", "ash"),
        ["a dragon appears"],
        {"and_any": False, "and_all": False, "not_any": True, "not_all": True},
    ),
    "two_some": (
        ("fire", "ash"),
        ["a dragon breathes fire"],
        {"and_any": True, "and_all": False, "not_any": False, "not_all": True},
    ),
    "two_all": (
        ("fire", "ash"),
        ["a dragon breathes fire and ash"],
        {"and_any": True, "and_all": True, "not_any": False, "not_all": False},
    ),
}


@pytest.mark.parametrize("mode", ALL_MODES)
@pytest.mark.parametrize("situation", list(SCAN_SITUATIONS))
def test_scan_selective_modes(mode, situation):
    secondary_keys, messages, expected = SCAN_SITUATIONS[situation]
    entries = [
        e(
            "a",
            keys=("dragon",),
            secondary_keys=secondary_keys,
            selective_logic=mode,
        )
    ]
    hits = scan_entries(entries, messages, 2)
    assert [h.entry_id for h in hits] == (["a"] if expected[mode] else [])


@pytest.mark.parametrize("mode", ALL_MODES)
def test_scan_primary_unmatched_never_fires(mode):
    # Especially the NOT modes: secondaries matching (or not) can
    # never substitute for a primary hit.
    entries = [
        e("a", keys=("dragon",), secondary_keys=("fire",), selective_logic=mode)
    ]
    assert scan_entries(entries, ["fire everywhere"], 1) == []
    assert scan_entries(entries, ["nothing relevant"], 1) == []


@pytest.mark.parametrize("mode", ALL_MODES)
def test_scan_whitespace_only_secondaries_fire(mode):
    # Whitespace-only keys are not usable secondaries, so the
    # empty-secondary rule applies: the primary alone decides.
    entries = [
        e(
            "a",
            keys=("dragon",),
            secondary_keys=("   ", ""),
            selective_logic=mode,
        )
    ]
    hits = scan_entries(entries, ["a dragon appears"], 1)
    assert [h.entry_id for h in hits] == ["a"]
    assert hits[0].matched_secondary == ()


def test_scan_default_mode_is_and_any_and_legacy_unchanged():
    entry = e("a", keys=("dragon",), secondary_keys=("fire",))
    assert entry.selective_logic == "and_any"
    # Legacy behaviour: primary alone is not enough, primary +
    # one secondary fires.
    assert scan_entries([entry], ["a dragon"], 1) == []
    hits = scan_entries([entry], ["a dragon breathes fire"], 1)
    assert [h.entry_id for h in hits] == ["a"]
    assert hits[0].matched_secondary == ("fire",)


def test_scan_not_any_hit_reports_no_secondaries_and_primary_indices():
    entries = [
        e("a", keys=("dragon",), secondary_keys=("fire",), selective_logic="not_any")
    ]
    hits = scan_entries(entries, ["hello", "a dragon appears"], 2)
    assert [h.entry_id for h in hits] == ["a"]
    assert hits[0].matched_primary == ("dragon",)
    assert hits[0].matched_secondary == ()
    assert hits[0].message_indices == (1,)


def test_scan_not_all_partial_hit_reports_matched_subset():
    entries = [
        e(
            "a",
            keys=("dragon",),
            secondary_keys=("fire", "ash"),
            selective_logic="not_all",
        )
    ]
    hits = scan_entries(entries, ["a dragon breathes fire"], 1)
    assert [h.entry_id for h in hits] == ["a"]
    assert hits[0].matched_secondary == ("fire",)


# A firing situation per mode, for the ScanHit echo check.
_FIRING_MESSAGES = {
    "and_any": (("fire", "ash"), ["a dragon breathes fire"]),
    "and_all": (("fire", "ash"), ["a dragon breathes fire and ash"]),
    "not_any": (("fire",), ["a dragon appears"]),
    "not_all": (("fire", "ash"), ["a dragon breathes fire"]),
}


@pytest.mark.parametrize("mode", ALL_MODES)
def test_scan_hit_echoes_selective_logic(mode):
    secondary_keys, messages = _FIRING_MESSAGES[mode]
    entries = [
        e(
            "a",
            keys=("dragon",),
            secondary_keys=secondary_keys,
            selective_logic=mode,
        )
    ]
    hits = scan_entries(entries, messages, 1)
    assert [h.entry_id for h in hits] == ["a"]
    assert hits[0].selective_logic == mode


class _OrmStubWithoutLogic:
    id = "orm-legacy"
    enabled = 1
    constant = 0
    keys_json = '["dragon"]'
    secondary_keys_json = '["fire"]'
    whole_word = 1
    case_sensitive = 0


class _OrmStubWithLogic(_OrmStubWithoutLogic):
    id = "orm-and-all"
    selective_logic = "and_all"


def test_scan_from_orm_without_selective_logic_defaults_and_any():
    se = ScanEntry.from_orm(_OrmStubWithoutLogic())
    assert se.selective_logic == "and_any"


def test_scan_from_orm_with_selective_logic_passthrough():
    se = ScanEntry.from_orm(_OrmStubWithLogic())
    assert se.selective_logic == "and_all"
    # and_all with only one of one secondary matched still fires,
    # and the hit carries the mode through.
    hits = scan_entries([se], ["dragon breathes fire"], 1)
    assert [h.entry_id for h in hits] == ["orm-and-all"]
    assert hits[0].selective_logic == "and_all"


# --------------------------------------------------- (d) service / API


def test_migration_head_is_0029_p037():
    # Head pin moved by P-037's 0029 (P-036's provisional 0028
    # before it); 0024 remains the selective-logic migration.
    assert MIGRATIONS[-1][0] == "0033"
def test_migration_head_is_0030_p038():
    # Head pin moved by P-038's provisional 0030 (0029 reserved
    # for P-037); 0024 remains the selective-logic migration.
    assert MIGRATIONS[-1][0] == "0033"
def test_migration_head_is_0028_p036():
    # Head pin moved by P-036's provisional 0028 (0027 reserved
    # for P-035); 0024 remains the selective-logic migration.
    assert MIGRATIONS[-1][0] == "0033"


def test_migration_0024_column_exists(tmp_path):
    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(lore_entries)")}
        assert "selective_logic" in columns
    finally:
        conn.close()


def test_migration_0024_raw_row_defaults_to_and_any(tmp_path):
    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO users (id, name, created_at) VALUES (?, ?, ?)",
            ("u1", "U", "2026-01-01T00:00:00"),
        )
        conn.execute(
            "INSERT INTO lorebooks (id, user_id, name, created_at) VALUES (?, ?, ?, ?)",
            ("b1", "u1", "B", "2026-01-01T00:00:00"),
        )
        # Raw row inserted WITHOUT naming selective_logic: the
        # column default must supply 'and_any'.
        conn.execute(
            "INSERT INTO lore_entries (id, lorebook_id, user_id, created_at)"
            " VALUES (?, ?, ?, ?)",
            ("e1", "b1", "u1", "2026-01-01T00:00:00"),
        )
        conn.commit()
        row = conn.execute(
            "SELECT selective_logic FROM lore_entries WHERE id = ?", ("e1",)
        ).fetchone()
        assert row is not None
        assert row[0] == "and_any"
    finally:
        conn.close()


async def test_service_create_entry_default_selective_logic(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        book = await service.create_lorebook(session, user_id, "B")
        entry = await service.create_entry(
            session, user_id, book.id, name="E", keys=["x"]
        )
        assert entry_to_dict(entry)["selective_logic"] == "and_any"


@pytest.mark.parametrize("mode", ALL_MODES)
async def test_service_modes_round_trip_create_and_update(tmp_path, mode):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        book = await service.create_lorebook(session, user_id, "B")
        created = await service.create_entry(
            session, user_id, book.id, name="C", keys=["x"], selective_logic=mode
        )
        assert entry_to_dict(created)["selective_logic"] == mode
        plain = await service.create_entry(
            session, user_id, book.id, name="U", keys=["y"]
        )
        assert entry_to_dict(plain)["selective_logic"] == "and_any"
        updated = await service.update_entry(
            session, user_id, book.id, plain.id, selective_logic=mode
        )
        assert updated is not None
        assert entry_to_dict(updated)["selective_logic"] == mode


async def test_service_create_entry_bogus_mode_raises(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        book = await service.create_lorebook(session, user_id, "B")
        with pytest.raises(ValueError):
            await service.create_entry(
                session, user_id, book.id, name="Bad", selective_logic="bogus"
            )


def test_api_create_entry_default_and_modes(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book_id = client.post("/api/v1/lorebooks", json={"name": "B"}).json()["id"]
    created = client.post(
        f"/api/v1/lorebooks/{book_id}/entries",
        json={"name": "D", "keys": ["x"]},
    )
    assert created.status_code == 201
    assert created.json()["selective_logic"] == "and_any"
    for mode in ALL_MODES:
        resp = client.post(
            f"/api/v1/lorebooks/{book_id}/entries",
            json={"name": mode, "keys": ["x"], "selective_logic": mode},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["selective_logic"] == mode


def test_api_patch_entry_selective_logic_round_trip(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book_id = client.post("/api/v1/lorebooks", json={"name": "B"}).json()["id"]
    entry_id = client.post(
        f"/api/v1/lorebooks/{book_id}/entries", json={"name": "E", "keys": ["x"]}
    ).json()["id"]
    for mode in ALL_MODES:
        resp = client.patch(
            f"/api/v1/lorebooks/{book_id}/entries/{entry_id}",
            json={"selective_logic": mode},
        )
        assert resp.status_code == 200, resp.text
        assert resp.json()["selective_logic"] == mode


def test_api_patch_bogus_mode_is_422(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book_id = client.post("/api/v1/lorebooks", json={"name": "B"}).json()["id"]
    entry_id = client.post(
        f"/api/v1/lorebooks/{book_id}/entries", json={"name": "E", "keys": ["x"]}
    ).json()["id"]
    resp = client.patch(
        f"/api/v1/lorebooks/{book_id}/entries/{entry_id}",
        json={"selective_logic": "bogus"},
    )
    # router._service_error maps the service ValueError to 422.
    assert resp.status_code == 422


# ------------------------------------------------- (e) transfer / interop


@pytest.mark.parametrize(
    "code,expected",
    [(0, "and_any"), (1, "not_all"), (2, "not_any"), (3, "and_all")],
)
def test_parse_import_worldinfo_codes(code, expected):
    _, entries = transfer.parse_import(worldinfo_payload(selectiveLogic=code))
    assert entries[0]["selective_logic"] == expected


@pytest.mark.parametrize(
    "marker,expected",
    [
        (None, "and_any"),  # explicit null
        (99, "and_any"),  # unknown code
        (-1, "and_any"),  # unknown code
        ("3", "and_all"),  # numeric string coerced
        ("junk", "and_any"),  # unparsable
    ],
)
def test_parse_import_worldinfo_tolerant(marker, expected):
    _, entries = transfer.parse_import(worldinfo_payload(selectiveLogic=marker))
    assert entries[0]["selective_logic"] == expected


def test_parse_import_worldinfo_absent_defaults():
    _, entries = transfer.parse_import(worldinfo_payload())
    assert entries[0]["selective_logic"] == "and_any"


@pytest.mark.parametrize("mode", ALL_MODES)
def test_parse_import_native_name_passthrough(mode):
    _, entries = transfer.parse_import(native_payload(mode))
    assert entries[0]["selective_logic"] == mode


@pytest.mark.parametrize("garbage", ["bogus", "AND_ANY", None, 2])
def test_parse_import_native_garbage_defaults(garbage):
    _, entries = transfer.parse_import(native_payload(garbage))
    assert entries[0]["selective_logic"] == "and_any"


def test_parse_import_native_absent_defaults():
    _, entries = transfer.parse_import(native_payload(None, include=False))
    assert entries[0]["selective_logic"] == "and_any"


@pytest.mark.parametrize("mode", ALL_MODES)
def test_export_book_emits_selective_logic(mode):
    exported = transfer.export_book(BOOK_DICT, [service_entry_dict(mode)])
    assert exported["entries"][0]["selective_logic"] == mode


@pytest.mark.parametrize("mode", ALL_MODES)
def test_native_round_trip_identity(mode):
    book_fields, parsed = transfer.parse_import(native_payload(mode))
    assert parsed[0]["selective_logic"] == mode
    entry_dicts = [service_entry_dict(parsed[0]["selective_logic"])]
    # Carry the other parsed fields through, service-shaped.
    for key in (
        "name",
        "content",
        "keys",
        "secondary_keys",
        "priority",
        "position",
        "enabled",
        "constant",
        "case_sensitive",
        "whole_word",
        "sticky_prompts",
        "cooldown_prompts",
        "delay_prompts",
    ):
        entry_dicts[0][key] = parsed[0][key]
    exported = transfer.export_book(book_fields, entry_dicts)
    assert exported["entries"][0]["selective_logic"] == mode
    _, reparsed = transfer.parse_import(exported)
    assert reparsed[0]["selective_logic"] == mode


@pytest.mark.parametrize(
    "mode,code",
    [
        ("not_all", 1),
        ("not_any", 2),
        ("and_all", 3),
    ],
)
def test_worldinfo_from_native_emits_codes(mode, code):
    out = worldinfo_from_native(BOOK_DICT, [service_entry_dict(mode)])
    assert out["entries"]["0"]["selectiveLogic"] == code


def test_worldinfo_from_native_and_any_not_fabricated():
    out = worldinfo_from_native(BOOK_DICT, [service_entry_dict("and_any")])
    assert "selectiveLogic" not in out["entries"]["0"]


def test_interop_corpus_gale_bell_selective_logic():
    data = json.loads(
        (CORPUS / "lorebook_worldinfo_full.json").read_text(encoding="utf-8")
    )
    book = parse_lorebook_file(data)
    gale = book.entries[0]
    assert gale.name == "The Gale-Bell"
    # selectiveLogic 1 in the file is now a first-class field,
    # no longer carried verbatim in extra.
    assert gale.selective_logic == "not_all"
    assert "selectiveLogic" not in gale.extra
    out = export_worldinfo(book)
    assert out["entries"]["0"]["selectiveLogic"] == 1
