"""P-047 acceptance: lorebook migration -- existing lorebooks
upgraded in place, behaviour-preserving, fixture-proven.

Roadmap line: *Migration: existing Runmal lorebooks upgraded in
place, behaviour-preserving, fixture-proven.*

Contract under test (``runmal.lorebooks.upgrade``, schema
``runmal-p047-lorebook-upgrade-v1``):

- File layer: ``inspect_lorebook`` reports exactly what an
  in-place upgrade would do (missing book/entry fields, unknown
  fields preserved, defect fixes) and changes nothing;
  ``upgrade_lorebook`` materialises every current native field
  in the SAME format the file arrived in, never mutates its
  input, and is idempotent. ``depth`` is materialised as None
  (undeclared), never as the compose-time default 4;
  ``token_budget`` is copied verbatim (null stays null).
- The behaviour invariant is stated over the interop layer:
  ``native_fields()`` + ``native_book_fields()`` of the parsed
  old file equal those of the parsed upgraded file. The one
  enumerated correction is the defect entry (an explicit
  ``use_probability=false`` with ``probability=30``): the file
  layer preserves {30, False} verbatim on both sides, while the
  store layer (``transfer.parse_import``, P-047 fold fix) folds
  the gate-off flag to the effective percent 100 on BOTH the
  legacy and the upgraded file -- snake spelling wins over the
  ``useProbability`` alias, an explicit None means the default.
- World-info files stay world-info: uid keys, ``originalData``
  and unknown position codes (e.g. 7) ride back verbatim, and
  preserved-as-data extras (``groupOverride`` and kin) survive.
- DB layer: ``upgrade_database`` on a database frozen at
  revision 0023 snapshots the lore tables raw, runs the ordinary
  migration chain (0024..0032, pure ADD COLUMN + new tables),
  and proves every pre-existing row/column byte-identical and
  every new column at its behaviour-preserving default. A
  database with no lore tables is left untouched. This slice
  takes NO new migration: the head stays 0032.
- Surfaces: ``POST /lorebooks/upgrade/inspect`` and
  ``POST /lorebooks/upgrade`` (registered after
  ``pack/inspect``, before the ``/lorebooks/{book_id}`` family);
  both write nothing to the database.

Fixtures are authored fresh here (P-005 discipline).
"""

from __future__ import annotations

import copy
import sqlite3
import types

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.lorebooks import service, transfer
from runmal.lorebooks.interop import LorebookParseError, parse_lorebook_file
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.upgrade import (
    NATIVE_BOOK_MATERIALISED,
    NATIVE_ENTRY_MATERIALISED,
    UPGRADE_SCHEMA,
    inspect_lorebook,
    upgrade_database,
    upgrade_lorebook,
)


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


# ------------------------------------------------------------------
# File fixtures (authored fresh, P-005 discipline)


def _s201_entry(**over):
    """An entry carrying only S201/S203-era fields."""
    entry = {
        "name": "",
        "content": "",
        "keys": [],
        "secondary_keys": [],
        "priority": 100,
        "position": "before_char",
        "enabled": True,
        "constant": False,
        "case_sensitive": False,
        "whole_word": True,
        "sticky_prompts": 0,
        "cooldown_prompts": 0,
        "delay_prompts": 0,
    }
    entry.update(over)
    return entry


def legacy_native():
    """(A) Pre-Part-III native book: no Part III book or entry
    fields, one defect entry, unknown keys at both levels."""
    return {
        "format": "runmal-lorebook",
        "version": 1,
        "name": "Legacy Fjord",
        "x_book_note": "kept by hand",
        "entries": [
            _s201_entry(
                name="Gale Warning",
                content="Gales lash the fjord.",
                keys=["gale"],
                priority=120,
                x_custom_note="do not drop",
            ),
            _s201_entry(
                name="Harbour Sticky",
                content="The harbour holds.",
                keys=["harbour"],
                priority=110,
                sticky_prompts=2,
            ),
            _s201_entry(
                name="Faded Gate",
                content="A gate that was turned off.",
                keys=["gate"],
                priority=100,
                probability=30,
                use_probability=False,
            ),
        ],
    }


def current_native():
    """(B) The fully explicit canonical book: every native book
    field and every native entry field, spelled canonically."""
    return {
        "format": "runmal-lorebook",
        "version": 1,
        "name": "Current Fjord",
        "description": "Fully explicit.",
        "scan_depth": 4,
        "token_budget": 500,
        "scan_mode": "depth",
        "scan_external_context": False,
        "entries": [
            {
                "name": "Gale",
                "content": "Gale lore.",
                "keys": ["gale"],
                "secondary_keys": [],
                "selective_logic": "and_any",
                "inclusion_group": "",
                "group_weight": 100,
                "probability": 100,
                "use_probability": True,
                "priority": 120,
                "position": "before_char",
                "depth": None,
                "role": "system",
                "enabled": True,
                "constant": False,
                "vectorised": False,
                "case_sensitive": False,
                "whole_word": True,
                "sticky_prompts": 0,
                "cooldown_prompts": 0,
                "delay_prompts": 0,
            },
            {
                "name": "Deep",
                "content": "Deep lore.",
                "keys": ["deep"],
                "secondary_keys": ["dark"],
                "selective_logic": "and_all",
                "inclusion_group": "arts",
                "group_weight": 80,
                "probability": 40,
                "use_probability": True,
                "priority": 90,
                "position": "at_depth",
                "depth": 2,
                "role": "user",
                "enabled": True,
                "constant": True,
                "vectorised": True,
                "case_sensitive": True,
                "whole_word": False,
                "sticky_prompts": 1,
                "cooldown_prompts": 3,
                "delay_prompts": 1,
            },
        ],
    }


def legacy_worldinfo():
    """(C) World-info book: uid-keyed entries, an unknown
    position code, preserved-as-data extras, a sparse entry."""
    return {
        "name": "Harbour World",
        "originalData": {"scan_depth": 4},
        "entries": {
            "0": {
                "key": ["storm"],
                "keysecondary": [],
                "content": "Storm lore.",
                "comment": "Storm",
                "constant": False,
                "disable": False,
                "order": 100,
                "position": 7,
                "caseSensitive": False,
                "matchWholeWords": True,
            },
            "1": {
                "key": ["harbour"],
                "keysecondary": [],
                "content": "Harbour lore.",
                "comment": "Harbour",
                "constant": False,
                "disable": False,
                "order": 90,
                "position": 0,
                "groupOverride": True,
                "useGroupScoring": False,
                "id": 42,
                "displayIndex": 3,
            },
            "2": {"key": ["calm"], "content": "Calm lore."},
        },
    }


# ------------------------------------------------------------------
# File layer: inspect + upgrade of the legacy native book


def test_inspect_legacy_native_report_exact():
    report = inspect_lorebook(legacy_native())
    assert set(report.keys()) == {
        "schema",
        "format",
        "generation",
        "entry_count",
        "book_missing_fields",
        "entry_missing_fields",
        "unknown_book_fields",
        "unknown_entry_fields",
        "preserved_unknown_count",
        "defect_fixes",
        "defect_fix_entries",
        "would_change",
        "behaviour_preserving",
        "behaviour_diffs",
    }
    assert report["schema"] == UPGRADE_SCHEMA
    assert report["schema"] == "runmal-p047-lorebook-upgrade-v1"
    assert report["format"] == "native"
    assert report["generation"] == "native-legacy"
    assert report["entry_count"] == 3
    # All five materialised book fields are missing, in order.
    assert report["book_missing_fields"] == list(NATIVE_BOOK_MATERIALISED)
    assert report["book_missing_fields"] == [
        "description",
        "scan_depth",
        "token_budget",
        "scan_mode",
        "scan_external_context",
    ]
    # Hand-computed: the two plain entries miss all 8 Part III
    # entry fields; the defect entry carries probability +
    # use_probability, so it misses only the other 6.
    assert report["entry_missing_fields"] == {
        "selective_logic": 3,
        "inclusion_group": 3,
        "group_weight": 3,
        "probability": 2,
        "use_probability": 2,
        "depth": 3,
        "role": 3,
        "vectorised": 3,
    }
    assert report["unknown_book_fields"] == ["x_book_note"]
    assert report["unknown_entry_fields"] == ["x_custom_note"]
    assert report["preserved_unknown_count"] == 2
    assert report["defect_fixes"] == 1
    assert report["defect_fix_entries"] == [2]
    assert report["would_change"] is True
    assert report["behaviour_preserving"] is True
    assert report["behaviour_diffs"] == []


def test_upgrade_legacy_native_preserves_and_materialises():
    book = legacy_native()
    snapshot = copy.deepcopy(book)
    upgraded, report = upgrade_lorebook(book)
    assert book == snapshot  # the input is never mutated
    assert report["fields_materialised"] == 27  # 5 book + 22 entry
    assert upgraded["format"] == "runmal-lorebook"
    assert upgraded["version"] == 1
    for entry in upgraded["entries"]:
        assert set(NATIVE_ENTRY_MATERIALISED) <= set(entry.keys())
        assert entry["depth"] is None  # undeclared, never default 4
    assert upgraded["token_budget"] is None  # null stays null
    # Unknown keys survive verbatim at both levels.
    assert upgraded["x_book_note"] == "kept by hand"
    assert upgraded["entries"][0]["x_custom_note"] == "do not drop"
    assert upgraded["entries"][1]["sticky_prompts"] == 2
    # File layer (interop): the parsed behaviour is identical,
    # and the defect entry's {30, False} is preserved verbatim.
    before = parse_lorebook_file(snapshot)
    after = parse_lorebook_file(upgraded)
    assert before.native_book_fields() == after.native_book_fields()
    assert [e.native_fields() for e in before.entries] == [
        e.native_fields() for e in after.entries
    ]
    for parsed in (before, after):
        defect = parsed.entries[2].native_fields()
        assert defect["probability"] == 30
        assert defect["use_probability"] is False
    # Store layer (transfer): the fold expresses the gate-off
    # flag as the effective percent 100 on BOTH files, so the
    # parsed imports are fully equal (builder-1 fold fix).
    book_before, entries_before = transfer.parse_import(snapshot)
    book_after, entries_after = transfer.parse_import(upgraded)
    assert book_before == book_after
    assert entries_before == entries_after
    assert entries_before[2]["probability"] == 100
    assert entries_after[2]["probability"] == 100


def test_upgrade_idempotent_and_current_book_untouched():
    upgraded, _report = upgrade_lorebook(legacy_native())
    again, _report2 = upgrade_lorebook(copy.deepcopy(upgraded))
    assert again == upgraded  # exactly idempotent
    report = inspect_lorebook(copy.deepcopy(upgraded))
    assert report["generation"] == "native-current"
    assert report["would_change"] is False
    current = current_native()
    report_b = inspect_lorebook(copy.deepcopy(current))
    assert report_b["generation"] == "native-current"
    assert report_b["would_change"] is False
    assert report_b["book_missing_fields"] == []
    assert report_b["entry_missing_fields"] == {}
    upgraded_b, report_ub = upgrade_lorebook(copy.deepcopy(current))
    assert upgraded_b == current
    assert report_ub["already_current"] is True


# ------------------------------------------------------------------
# File layer: the use_probability fold pins (transfer)


def _pin_probability(entry):
    _book, entries = transfer.parse_import(
        {"name": "Pin Book", "entries": [entry]}
    )
    return entries[0]["probability"]


def test_transfer_use_probability_fold_pins():
    base = {"name": "Pinned", "content": "Pinned lore."}
    # An explicit gate-off folds to the effective percent 100,
    # under either spelling.
    assert _pin_probability({**base, "probability": 30, "use_probability": False}) == 100
    assert _pin_probability({**base, "probability": 30, "useProbability": False}) == 100
    # Gate on (or undeclared, or explicitly None): the raw
    # percent is stored as-is.
    assert _pin_probability({**base, "probability": 30, "use_probability": True}) == 30
    assert _pin_probability({**base, "probability": 30}) == 30
    assert _pin_probability({**base, "probability": 30, "use_probability": None}) == 30
    # When both spellings disagree, the snake spelling wins.
    assert _pin_probability(
        {**base, "probability": 30, "use_probability": False, "useProbability": True}
    ) == 100
    assert _pin_probability(
        {**base, "probability": 30, "use_probability": True, "useProbability": False}
    ) == 30


# ------------------------------------------------------------------
# File layer: world-info stays world-info; malformed files refuse


def test_worldinfo_upgrade_preserves_foreign_shape():
    book = legacy_worldinfo()
    snapshot = copy.deepcopy(book)
    report = inspect_lorebook(copy.deepcopy(book))
    assert report["format"] == "worldinfo"
    assert report["generation"] == "worldinfo"
    upgraded, _report = upgrade_lorebook(book)
    assert book == snapshot  # the input is never mutated
    # Uid keys, originalData and the unknown position code ride
    # back verbatim; preserved-as-data extras survive.
    assert set(upgraded["entries"].keys()) == {"0", "1", "2"}
    assert upgraded["entries"]["0"]["position"] == 7
    assert upgraded["originalData"] == {"scan_depth": 4}
    extra = upgraded["entries"]["1"]
    assert extra["groupOverride"] is True
    assert extra["useGroupScoring"] is False
    assert extra["id"] == 42
    assert extra["displayIndex"] == 3
    # The parsed behaviour is identical across the refresh.
    before = parse_lorebook_file(snapshot)
    after = parse_lorebook_file(upgraded)
    assert before.native_book_fields() == after.native_book_fields()
    assert [e.native_fields() for e in before.entries] == [
        e.native_fields() for e in after.entries
    ]
    again, _report2 = upgrade_lorebook(copy.deepcopy(upgraded))
    assert again == upgraded  # exactly idempotent


def test_malformed_files_raise():
    for bad in ({}, {"name": "x"}):
        with pytest.raises(LorebookParseError):
            inspect_lorebook(copy.deepcopy(bad))
        with pytest.raises(LorebookParseError):
            upgrade_lorebook(copy.deepcopy(bad))
    bad_entry = {"name": "x", "entries": [42]}
    with pytest.raises(LorebookParseError):
        inspect_lorebook(copy.deepcopy(bad_entry))
    with pytest.raises(LorebookParseError):
        upgrade_lorebook(copy.deepcopy(bad_entry))
    # LorebookParseError is the ValueError the routers map to 422.
    assert issubclass(LorebookParseError, ValueError)


# ------------------------------------------------------------------
# DB layer: a database frozen at revision 0023

USER_ID = "u1"
BOOK_ID = "b1"
STAMP = "2026-01-01T00:00:00+00:00"

DB_ENTRIES = [
    dict(id="e-const", name="Always", content="The hall is always lit.",
         keys_json="[]", secondary_keys_json="[]", priority=130,
         position="before_char", enabled=1, constant=1,
         case_sensitive=0, whole_word=1, sticky_prompts=0,
         cooldown_prompts=0, delay_prompts=0,
         created_at="2026-01-01T00:00:00+00:00"),
    dict(id="e-gale", name="Gale", content="A gale tears the sails.",
         keys_json='["gale"]', secondary_keys_json="[]", priority=120,
         position="before_char", enabled=1, constant=0,
         case_sensitive=0, whole_word=1, sticky_prompts=0,
         cooldown_prompts=0, delay_prompts=0,
         created_at="2026-01-01T00:01:00+00:00"),
    dict(id="e-sticky", name="Harbour", content="The harbour holds fast.",
         keys_json='["harbour"]', secondary_keys_json="[]", priority=110,
         position="before_char", enabled=1, constant=0,
         case_sensitive=0, whole_word=1, sticky_prompts=2,
         cooldown_prompts=0, delay_prompts=0,
         created_at="2026-01-01T00:02:00+00:00"),
    dict(id="e-muted", name="Muted", content="Muted lore.",
         keys_json='["gale"]', secondary_keys_json="[]", priority=100,
         position="before_char", enabled=0, constant=0,
         case_sensitive=0, whole_word=1, sticky_prompts=0,
         cooldown_prompts=0, delay_prompts=0,
         created_at="2026-01-01T00:03:00+00:00"),
]


def build_legacy_db(tmp_path):
    """A database migrated only to 0023 (revisions 0001..0023,
    applied exactly as migrate_to_head applies them), holding one
    book with four entries in 0004+0005 columns only."""
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "revision TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for revision, _description, module in MIGRATIONS[:23]:
            module.upgrade(conn)
            conn.execute(
                "INSERT INTO schema_migrations (revision, applied_at)"
                " VALUES (?, ?)",
                (revision, STAMP),
            )
            conn.commit()
        conn.execute(
            "INSERT INTO users (id, name, created_at) VALUES (?, ?, ?)",
            (USER_ID, "volmarr", STAMP),
        )
        conn.execute(
            "INSERT INTO lorebooks (id, user_id, name, description,"
            " scan_depth, token_budget, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (BOOK_ID, USER_ID, "Legacy DB Book", "old", 4, None, STAMP),
        )
        for row in DB_ENTRIES:
            conn.execute(
                "INSERT INTO lore_entries (id, lorebook_id, user_id,"
                " name, content, keys_json, secondary_keys_json,"
                " priority, position, enabled, constant,"
                " case_sensitive, whole_word, sticky_prompts,"
                " cooldown_prompts, delay_prompts, created_at,"
                " updated_at) VALUES (:id, :lorebook_id, :user_id,"
                " :name, :content, :keys_json, :secondary_keys_json,"
                " :priority, :position, :enabled, :constant,"
                " :case_sensitive, :whole_word, :sticky_prompts,"
                " :cooldown_prompts, :delay_prompts, :created_at,"
                " :updated_at)",
                {**row, "lorebook_id": BOOK_ID, "user_id": USER_ID,
                 "updated_at": None},
            )
        conn.commit()
    finally:
        conn.close()
    return db_path


def _raw_rows(db_path, table, order=""):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(f"SELECT * FROM {table} {order}")]
    finally:
        conn.close()


PREVIEW_MESSAGES = ["the gale rises", "calm harbour"]


def _preview(entries):
    return preview_activation(
        entries,
        list(PREVIEW_MESSAGES),
        scan_depth=4,
        token_budget=None,
        seed=7,
        roll_context="p047-fixture",
        vector_hit_ids=set(),
    )


def _preview_before(db_path):
    """Behaviour BEFORE, from raw rows carrying only the
    pre-0024 columns, in service order (priority desc,
    created_at)."""
    rows = _raw_rows(
        db_path, "lore_entries", "ORDER BY priority DESC, created_at"
    )
    return _preview([types.SimpleNamespace(**row) for row in rows])


def test_db_fixture_starts_at_0023_and_preview_before(tmp_path):
    db_path = build_legacy_db(tmp_path)
    assert current_revision(db_path) == "0023"
    before = _preview_before(db_path)
    assert [row["status"] for row in before["entries"]] == [
        "included",
        "included",
        "included",
        "disabled",
    ]
    assert before["entries"][1]["matched_primary"] == ["gale"]
    assert before["entries"][2]["matched_primary"] == ["harbour"]
    assert before["tokens_used"] == 15


def test_upgrade_database_report(tmp_path):
    db_path = build_legacy_db(tmp_path)
    report = upgrade_database(db_path)
    assert report["schema"] == UPGRADE_SCHEMA
    assert report["status"] == "upgraded"
    assert report["before_revision"] == "0023"
    assert report["after_revision"] == "0038"
    assert report["applied_revisions"] == [
        "0024", "0025", "0026", "0027", "0028",
        "0029", "0030", "0031", "0032", "0033", "0034", "0035", "0036", "0037", "0038",  # PROVISIONAL 0038 appended by P-068; 0037 by P-066; 0036 by P-065
    ]
    assert report["books_before"] == 1
    assert report["books_after"] == 1
    assert report["entries_before"] == 4
    assert report["entries_after"] == 4
    assert report["rows_verified"] == 5  # 1 book + 4 entries
    assert report["defaults_verified"] is True
    assert report["mismatches"] == []
    assert report["behaviour_preserving"] is True
    assert report["new_tables_present"] == [
        "character_book_bindings",
        "chat_lore_entry_states",
        "lorebook_scopes",
    ]


def test_upgrade_database_raw_rows_and_defaults(tmp_path):
    db_path = build_legacy_db(tmp_path)
    books_snapshot = _raw_rows(db_path, "lorebooks")
    entries_snapshot = _raw_rows(
        db_path, "lore_entries", "ORDER BY priority DESC, created_at"
    )
    upgrade_database(db_path)
    books_after = {r["id"]: r for r in _raw_rows(db_path, "lorebooks")}
    entries_after = {r["id"]: r for r in _raw_rows(db_path, "lore_entries")}
    assert set(books_after) == {r["id"] for r in books_snapshot}
    assert set(entries_after) == {r["id"] for r in entries_snapshot}
    # Every pre-existing column value is identical to the
    # snapshot this test captured before the upgrade.
    for snapshot in books_snapshot:
        after_row = books_after[snapshot["id"]]
        for column, value in snapshot.items():
            assert after_row[column] == value, column
    for snapshot in entries_snapshot:
        after_row = entries_after[snapshot["id"]]
        for column, value in snapshot.items():
            assert after_row[column] == value, column
    # Every new column holds exactly its behaviour-preserving
    # default on the pre-existing rows.
    for row in books_after.values():
        assert row["scan_mode"] == "depth"
        assert row["scan_external_context"] == 0
    for row in entries_after.values():
        assert row["selective_logic"] == "and_any"
        assert row["inclusion_group"] == ""
        assert row["group_weight"] == 100
        assert row["vectorised"] == 0
        assert row["probability"] == 100
        assert row["depth"] is None
        assert row["role"] == "system"


async def test_db_preview_after_matches_before(tmp_path):
    db_path = build_legacy_db(tmp_path)
    before = _preview_before(db_path)
    upgrade_database(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    async with factory() as session:
        entries = await service.list_entries(session, USER_ID, BOOK_ID)
    assert [e.id for e in entries] == [
        "e-const", "e-gale", "e-sticky", "e-muted"
    ]
    after = _preview(entries)
    assert after == before  # full dict equality, same tick args


def test_upgrade_database_second_call_already_current(tmp_path):
    db_path = build_legacy_db(tmp_path)
    upgrade_database(db_path)
    report = upgrade_database(db_path)
    assert report["status"] == "already_current"
    assert report["applied_revisions"] == []
    assert report["behaviour_preserving"] is True


def test_upgrade_database_missing_path(tmp_path):
    report = upgrade_database(tmp_path / "nope.db")
    assert report["status"] == "missing"
    assert report["applied_revisions"] == []


def test_upgrade_database_no_lorebooks_left_untouched(tmp_path):
    db_path = tmp_path / "empty.db"
    db_path.write_bytes(b"")
    report = upgrade_database(db_path)
    assert report["status"] == "no_lorebooks"
    assert report["applied_revisions"] == []
    conn = sqlite3.connect(db_path)
    try:
        tables = {
            row[0]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
    finally:
        conn.close()
    assert "lorebooks" not in tables
    assert "lore_entries" not in tables
    # upgrade_database's own contract: a database with no lore
    # tables "is left untouched" -- migrate was not forced, and
    # no schema_migrations table was created by the call either.
    assert tables == set()


def test_no_new_migration_head_stays_0032():
    assert MIGRATIONS[-1][0] == "0038"  # head moved by P-065 (PROVISIONAL 0036)


# ------------------------------------------------------------------
# Router surface


def test_router_upgrade_inspect_and_upgrade_write_nothing(
    tmp_path, monkeypatch
):
    client = make_client(tmp_path, monkeypatch)
    book = legacy_native()
    inspected = client.post(
        "/api/v1/lorebooks/upgrade/inspect", json=book
    )
    assert inspected.status_code == 200, inspected.text
    report = inspected.json()
    # The upgrade report came back (not a book 404): the routes
    # are not shadowed by the /lorebooks/{book_id} family.
    assert report["schema"] == UPGRADE_SCHEMA
    assert report["generation"] == "native-legacy"
    assert report["defect_fixes"] == 1
    upgraded_resp = client.post("/api/v1/lorebooks/upgrade", json=book)
    assert upgraded_resp.status_code == 200, upgraded_resp.text
    body = upgraded_resp.json()
    assert set(body.keys()) == {"lorebook", "upgrade"}
    assert body["upgrade"]["generation"] == "native-legacy"
    for entry in body["lorebook"]["entries"]:
        assert "selective_logic" in entry
    bad = client.post("/api/v1/lorebooks/upgrade/inspect", json={})
    assert bad.status_code == 422, bad.text
    # Neither call wrote anything.
    assert client.get("/api/v1/lorebooks").json() == []
