"""P-037 acceptance: scan depth & context windows.

Roadmap line: *Scan depth & context windows: per-book scan
settings (messages-deep, whole-chat, external context) as
data.*

Contract under test:
- ``runmal.lorebooks.windows`` is the pure settings module: a
  book's scan window is stored data -- ``scan_depth``
  (messages-deep, unchanged from S201), ``scan_mode``
  (``depth`` = last scan_depth messages, the pre-P-037
  behaviour; ``whole_chat`` = every message) and
  ``scan_external_context`` (caller-supplied external context
  joins the window as its own segment, never counted against
  the depth). Strict ``check_*`` at the service/API layer,
  tolerant ``normalise_*`` at the stored/file layer, with the
  fallback always the narrow pre-P-037 window.
- ``scan_entries_windowed`` runs the SAME matching core as
  ``scan_entries`` over the resolved window: with depth
  settings and no external segment the hits are identical;
  chat matches report indices into the full message list and
  external matches report ``external_indices`` -- where a key
  fired is never ambiguous. Recursive round 0 honours the
  settings; later rounds are unchanged.
- The settings are carried end to end: migration 0029 +
  model, service (strict), API (422 on a bad mode), preview
  (book defaults, per-request overrides, window summary +
  per-row external indices), the prompt inspector, native
  transfer export/import, and the native file layer. The
  world-info file layer keeps its P-019 discipline: book
  settings ride in ``originalData`` verbatim and the
  per-entry ``scanDepth`` stays preserved-as-data (the
  dropped set is unchanged -- P-037 claims no per-entry
  semantics).
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Character, User
from runmal.library.service import _lorebook_hash
from runmal.lorebooks import service, transfer
from runmal.lorebooks.interop import (
    export_native,
    parse_lorebook_file,
    worldinfo_from_native,
)
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.scan import (
    ScanEntry,
    scan_entries,
    scan_entries_recursive,
    scan_entries_windowed,
)
from runmal.lorebooks.service import lorebook_to_dict
from runmal.lorebooks.windows import (
    SCAN_MODES,
    ScanSettings,
    build_scan_window,
    check_scan_depth,
    check_scan_external_context,
    check_scan_mode,
    normalise_scan_depth,
    normalise_scan_external_context,
    normalise_scan_mode,
)
from runmal.prompt.inspect import inspect_prompt

CORPUS = Path(__file__).parent / "fixtures" / "interop"


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


def entry(eid, keys, **kw):
    return ScanEntry(id=eid, keys=tuple(keys), **kw)


# ------------------------------------------------------- vocabulary checks


def test_check_scan_mode_strict():
    assert check_scan_mode("depth") == "depth"
    assert check_scan_mode("whole_chat") == "whole_chat"
    assert SCAN_MODES == frozenset({"depth", "whole_chat"})
    for bad in ("Depth", "DEPTH", "all", "", None, 4, True):
        with pytest.raises(ValueError):
            check_scan_mode(bad)


def test_normalise_scan_mode_tolerant_falls_back_to_depth():
    assert normalise_scan_mode("whole_chat") == "whole_chat"
    assert normalise_scan_mode("depth") == "depth"
    # The fallback is the NARROW pre-P-037 window, never wider.
    for bad in ("wide", "", None, 4, True):
        assert normalise_scan_mode(bad) == "depth"


def test_check_scan_depth_strict():
    assert check_scan_depth(1) == 1
    assert check_scan_depth(250) == 250
    for bad in (0, -1, True, False, "4", 4.0, None):
        with pytest.raises(ValueError):
            check_scan_depth(bad)


def test_normalise_scan_depth_tolerant():
    assert normalise_scan_depth(7) == 7
    for bad in (0, -3, True, "9", None):
        assert normalise_scan_depth(bad) == 4


def test_check_scan_external_context_strict():
    assert check_scan_external_context(True) is True
    assert check_scan_external_context(False) is False
    for bad in (1, 0, "yes", None):
        with pytest.raises(ValueError):
            check_scan_external_context(bad)


def test_normalise_scan_external_context_tolerant():
    assert normalise_scan_external_context(None) is False
    assert normalise_scan_external_context(True) is True
    assert normalise_scan_external_context(1) is True
    assert normalise_scan_external_context("") is False
    # A string is read as the flag it NAMES: "false" must never
    # widen the window by truthiness (the never-widen rule).
    assert normalise_scan_external_context("false") is False
    assert normalise_scan_external_context("0") is False
    assert normalise_scan_external_context("no") is False
    assert normalise_scan_external_context("off") is False
    assert normalise_scan_external_context("true") is True
    assert normalise_scan_external_context("True") is True
    assert normalise_scan_external_context("yes") is True


def test_settings_defaults_are_pre_p037_behaviour():
    s = ScanSettings()
    assert s.scan_depth == 4
    assert s.scan_mode == "depth"
    assert s.scan_external_context is False
    assert s.to_dict() == {
        "scan_depth": 4,
        "scan_mode": "depth",
        "scan_external_context": False,
    }


def test_settings_construction_is_strict():
    with pytest.raises(ValueError):
        ScanSettings(scan_mode="wide")
    with pytest.raises(ValueError):
        ScanSettings(scan_depth=0)
    with pytest.raises(ValueError):
        ScanSettings(scan_depth=True)
    with pytest.raises(ValueError):
        ScanSettings(scan_external_context=1)


def test_settings_normalised_falls_back():
    s = ScanSettings.normalised(scan_depth=-2, scan_mode="wide", scan_external_context=None)
    assert s == ScanSettings()
    s = ScanSettings.normalised(scan_depth=9, scan_mode="whole_chat", scan_external_context=1)
    assert (s.scan_depth, s.scan_mode, s.scan_external_context) == (9, "whole_chat", True)


def test_settings_from_book_mapping_namespace_and_legacy():
    by_map = ScanSettings.from_book(
        {"scan_depth": 3, "scan_mode": "whole_chat", "scan_external_context": True}
    )
    assert (by_map.scan_depth, by_map.scan_mode, by_map.scan_external_context) == (
        3,
        "whole_chat",
        True,
    )
    legacy = SimpleNamespace(scan_depth=6)  # a pre-P-037 row: no new fields
    from_legacy = ScanSettings.from_book(legacy)
    assert (from_legacy.scan_depth, from_legacy.scan_mode, from_legacy.scan_external_context) == (
        6,
        "depth",
        False,
    )
    bare = ScanSettings.from_book(SimpleNamespace())
    assert bare == ScanSettings()


def test_chat_window_size():
    depth = ScanSettings(scan_depth=3)
    assert depth.chat_window_size(10) == 3
    assert depth.chat_window_size(2) == 2
    assert depth.chat_window_size(0) == 0
    whole = ScanSettings(scan_depth=1, scan_mode="whole_chat")
    assert whole.chat_window_size(10) == 10
    assert whole.chat_window_size(0) == 0
    with pytest.raises(ValueError):
        depth.chat_window_size(-1)


# ------------------------------------------------------- window builder


def test_window_depth_segment_keeps_full_list_indices():
    w = build_scan_window(ScanSettings(scan_depth=2), ["m0", "m1", "m2", "m3"])
    assert w.texts == ("m2", "m3")
    assert w.sources == ("chat", "chat")
    assert w.message_indices == (2, 3)
    assert w.external_indices == (None, None)


def test_window_whole_chat_ignores_depth_for_size():
    w = build_scan_window(
        ScanSettings(scan_depth=1, scan_mode="whole_chat"), ["m0", "m1", "m2"]
    )
    assert w.texts == ("m0", "m1", "m2")
    assert w.message_indices == (0, 1, 2)


def test_window_external_segment_appended_and_not_counted():
    w = build_scan_window(
        ScanSettings(scan_depth=1, scan_external_context=True),
        ["old", "new"],
        ["persona text", "scenario text"],
    )
    assert w.texts == ("new", "persona text", "scenario text")
    assert w.sources == ("chat", "external", "external")
    assert w.message_indices == (1, None, None)
    assert w.external_indices == (None, 0, 1)
    assert w.summary() == {"texts": 3, "chat_messages": 1, "external_texts": 2}


def test_window_external_ignored_when_flag_off():
    w = build_scan_window(ScanSettings(scan_depth=4), ["m"], ["ext"])
    assert w.texts == ("m",)
    assert w.external_count == 0


def test_window_external_only_and_empty():
    w = build_scan_window(ScanSettings(scan_external_context=True), [], ["only"])
    assert w.texts == ("only",)
    assert w.chat_count == 0 and w.external_count == 1
    empty = build_scan_window(ScanSettings(scan_external_context=True), [], [])
    assert empty.texts == ()
    assert empty.summary() == {"texts": 0, "chat_messages": 0, "external_texts": 0}


# ------------------------------------------------------- scan engine


def test_windowed_depth_equals_plain_scan():
    entries = [
        entry("a", ["gale"]),
        entry("b", ["harbour"], secondary_keys=("bell",)),
        entry("c", ["storm"], whole_word=False),
        entry("d", ["off"], enabled=False),
    ]
    messages = [
        "harbour bell tolls",
        "a gale rises",
        "stormwatch",
        "calm seas",
        "the harbour bell again, gale fading",
    ]
    for depth in (1, 2, 3, 5, 9):
        plain = scan_entries(entries, messages, depth)
        windowed = scan_entries_windowed(entries, messages, ScanSettings(scan_depth=depth))
        assert windowed == plain
        assert all(h.external_indices == () for h in windowed)


def test_windowed_whole_chat_reaches_beyond_depth():
    entries = [entry("old", ["aurora"])]
    messages = ["aurora over the fjord", "filler", "filler", "filler", "filler"]
    depth_hits = scan_entries_windowed(entries, messages, ScanSettings(scan_depth=2))
    assert depth_hits == []
    whole_hits = scan_entries_windowed(
        entries, messages, ScanSettings(scan_depth=2, scan_mode="whole_chat")
    )
    assert [h.entry_id for h in whole_hits] == ["old"]
    assert whole_hits[0].message_indices == (0,)


def test_windowed_external_hit_reports_external_indices():
    entries = [entry("persona", ["blacksmith"])]
    settings = ScanSettings(scan_depth=2, scan_external_context=True)
    hits = scan_entries_windowed(
        entries, ["chat one", "chat two"], settings, ["a smith", "the blacksmith rests"]
    )
    assert len(hits) == 1
    assert hits[0].message_indices == ()
    assert hits[0].external_indices == (1,)
    assert hits[0].matched_primary == ("blacksmith",)


def test_windowed_external_off_means_no_external_hit():
    entries = [entry("persona", ["blacksmith"])]
    hits = scan_entries_windowed(
        entries, ["chat"], ScanSettings(scan_depth=2), ["the blacksmith rests"]
    )
    assert hits == []


def test_windowed_cross_segment_secondary_gate():
    entries = [entry("b", ["harbour"], secondary_keys=("gale",))]
    settings = ScanSettings(scan_depth=2, scan_external_context=True)
    # Primary in chat, secondary only in external: one window, fires.
    hits = scan_entries_windowed(entries, ["the harbour"], settings, ["gale warning"])
    assert len(hits) == 1
    assert hits[0].message_indices == (0,)
    assert hits[0].external_indices == (0,)
    assert hits[0].matched_secondary == ("gale",)
    # not_any: a secondary matched in the external segment gates OFF.
    entries_not = [
        ScanEntry(id="n", keys=("harbour",), secondary_keys=("gale",), selective_logic="not_any")
    ]
    assert scan_entries_windowed(entries_not, ["the harbour"], settings, ["gale warning"]) == []
    assert len(scan_entries_windowed(entries_not, ["the harbour"], settings, ["calm"])) == 1


def test_windowed_skips_constant_vectorised_disabled():
    entries = [
        entry("k", ["gale"]),
        entry("c", ["gale"], constant=True),
        entry("v", ["gale"], vectorised=True),
        entry("d", ["gale"], enabled=False),
    ]
    hits = scan_entries_windowed(entries, ["gale"], ScanSettings())
    assert [h.entry_id for h in hits] == ["k"]


def test_windowed_empty_and_external_only():
    entries = [entry("a", ["gale"])]
    assert scan_entries_windowed(entries, [], ScanSettings()) == []
    hits = scan_entries_windowed(
        entries, [], ScanSettings(scan_external_context=True), ["gale"]
    )
    assert len(hits) == 1 and hits[0].external_indices == (0,)


# ------------------------------------------------------- recursive round 0


def _chain_entries():
    return [
        ScanEntry(id="first", keys=("aurora",), content="the beacon wakes"),
        ScanEntry(id="second", keys=("beacon",), content="beacon lit"),
    ]


def test_recursive_round0_honours_whole_chat():
    messages = ["aurora", "filler", "filler", "filler"]
    shallow = scan_entries_recursive(
        _chain_entries(), messages, 1, settings=ScanSettings(scan_depth=1)
    )
    assert shallow.hits == ()
    deep = scan_entries_recursive(
        _chain_entries(),
        messages,
        1,
        settings=ScanSettings(scan_depth=1, scan_mode="whole_chat"),
    )
    assert [h.entry_id for h in deep.hits] == ["first", "second"]
    assert deep.hits[1].depth == 1 and deep.hits[1].triggered_by == "first"


def test_recursive_round0_external_trigger():
    result = scan_entries_recursive(
        _chain_entries(),
        ["nothing here"],
        1,
        settings=ScanSettings(scan_external_context=True),
        external_context=["aurora rising"],
    )
    assert [h.entry_id for h in result.hits] == ["first", "second"]
    assert result.hits[0].external_indices == (0,)


# ------------------------------------------------------- preview


async def _book_with_entries(factory, user_id, **book_kw):
    async with factory() as session:
        book = await service.create_lorebook(session, user_id, "Windows", **book_kw)
        await service.create_entry(
            session, user_id, book.id, name="Old", content="aurora lore",
            keys=["aurora"],
        )
        await service.create_entry(
            session, user_id, book.id, name="Persona", content="smith lore",
            keys=["blacksmith"],
        )
        entries = await service.list_entries(session, user_id, book.id)
        return book, entries


async def test_preview_reports_settings_and_window(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    _book, entries = await _book_with_entries(factory, user_id)
    result = preview_activation(entries, ["a", "b", "c", "d", "e", "f"], 4, None)
    assert result["scan_mode"] == "depth"
    assert result["scan_external_context"] is False
    assert result["scan_window"] == {"texts": 4, "chat_messages": 4, "external_texts": 0}
    assert all(row["external_indices"] == [] for row in result["entries"])


async def test_preview_whole_chat_vs_depth(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    _book, entries = await _book_with_entries(factory, user_id)
    messages = ["aurora", "f", "f", "f", "f"]
    depth = preview_activation(entries, messages, 1, None)
    by_name = {r["name"]: r for r in depth["entries"]}
    assert by_name["Old"]["status"] == "not_triggered"
    whole = preview_activation(entries, messages, 1, None, scan_mode="whole_chat")
    by_name = {r["name"]: r for r in whole["entries"]}
    assert by_name["Old"]["status"] == "included"
    assert whole["scan_window"]["chat_messages"] == 5


async def test_preview_external_hit_row(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    _book, entries = await _book_with_entries(factory, user_id)
    result = preview_activation(
        entries, ["chat"], 4, None,
        scan_external_context=True,
        external_context=["the blacksmith rests"],
    )
    by_name = {r["name"]: r for r in result["entries"]}
    assert by_name["Persona"]["status"] == "included"
    assert by_name["Persona"]["external_indices"] == [0]
    assert result["scan_window"] == {"texts": 2, "chat_messages": 1, "external_texts": 1}
    # Flag off: the same external text is not scanned at all.
    off = preview_activation(
        entries, ["chat"], 4, None, external_context=["the blacksmith rests"]
    )
    by_name = {r["name"]: r for r in off["entries"]}
    assert by_name["Persona"]["status"] == "not_triggered"
    assert off["scan_window"]["external_texts"] == 0


async def test_preview_recursive_round0_honours_settings(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    _book, entries = await _book_with_entries(factory, user_id)
    result = preview_activation(
        entries, ["nothing", "nothing"], 1, None,
        recursive_scan=True,
        scan_external_context=True,
        external_context=["aurora"],
    )
    by_name = {r["name"]: r for r in result["entries"]}
    assert by_name["Old"]["status"] == "included"
    assert result["recursive_scan"] is True


# ------------------------------------------------------- service + API


async def test_service_create_update_round_trip(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        book = await service.create_lorebook(
            session, user_id, "Deep", scan_mode="whole_chat", scan_external_context=True
        )
        assert book.scan_mode == "whole_chat" and book.scan_external_context is True
        as_dict = lorebook_to_dict(book)
        assert as_dict["scan_mode"] == "whole_chat"
        assert as_dict["scan_external_context"] is True
        updated = await service.update_lorebook(
            session, user_id, book.id, scan_mode="depth", scan_external_context=False
        )
        assert updated.scan_mode == "depth" and updated.scan_external_context is False


async def test_service_defaults_are_pre_p037(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        book = await service.create_lorebook(session, user_id, "Plain")
        assert lorebook_to_dict(book)["scan_mode"] == "depth"
        assert lorebook_to_dict(book)["scan_external_context"] is False


async def test_service_rejects_bad_settings(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        for bad in ("wide", "", None, 4):
            with pytest.raises(ValueError):
                await service.create_lorebook(session, user_id, "B", scan_mode=bad)
        for bad in (1, "yes", 0):
            with pytest.raises(ValueError):
                await service.create_lorebook(
                    session, user_id, "B", scan_external_context=bad
                )
        book = await service.create_lorebook(session, user_id, "B")
        with pytest.raises(ValueError):
            await service.update_lorebook(session, user_id, book.id, scan_mode="wide")
        with pytest.raises(ValueError):
            await service.update_lorebook(
                session, user_id, book.id, scan_external_context=1
            )


def test_api_book_scan_settings_and_422(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post(
        "/api/v1/lorebooks",
        json={"name": "B", "scan_mode": "whole_chat", "scan_external_context": True},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["scan_mode"] == "whole_chat" and body["scan_external_context"] is True
    bad = client.post("/api/v1/lorebooks", json={"name": "B", "scan_mode": "wide"})
    assert bad.status_code == 422
    patched = client.patch(
        f"/api/v1/lorebooks/{body['id']}", json={"scan_mode": "depth"}
    )
    assert patched.status_code == 200 and patched.json()["scan_mode"] == "depth"
    bad_patch = client.patch(
        f"/api/v1/lorebooks/{body['id']}", json={"scan_mode": "wide"}
    )
    assert bad_patch.status_code == 422


def test_api_preview_uses_book_settings_and_overrides(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book = client.post(
        "/api/v1/lorebooks",
        json={"name": "B", "scan_depth": 1, "scan_mode": "whole_chat"},
    ).json()
    client.post(
        f"/api/v1/lorebooks/{book['id']}/entries",
        json={"name": "Old", "content": "aurora lore", "keys": ["aurora"]},
    )
    messages = ["aurora", "f", "f", "f"]
    # Book default (whole_chat) reaches the old message.
    result = client.post(
        f"/api/v1/lorebooks/{book['id']}/preview", json={"messages": messages}
    ).json()
    assert result["scan_mode"] == "whole_chat"
    assert result["entries"][0]["status"] == "included"
    # Per-request override narrows it back to depth 1.
    narrowed = client.post(
        f"/api/v1/lorebooks/{book['id']}/preview",
        json={"messages": messages, "scan_mode": "depth"},
    ).json()
    assert narrowed["entries"][0]["status"] == "not_triggered"
    # A bad override mode is a 422, never a silent default.
    bad = client.post(
        f"/api/v1/lorebooks/{book['id']}/preview",
        json={"messages": messages, "scan_mode": "wide"},
    )
    assert bad.status_code == 422


def test_api_preview_external_context(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book = client.post(
        "/api/v1/lorebooks", json={"name": "B", "scan_external_context": True}
    ).json()
    client.post(
        f"/api/v1/lorebooks/{book['id']}/entries",
        json={"name": "Persona", "content": "smith lore", "keys": ["blacksmith"]},
    )
    hit = client.post(
        f"/api/v1/lorebooks/{book['id']}/preview",
        json={"messages": ["chat"], "external_context": ["the blacksmith rests"]},
    ).json()
    assert hit["entries"][0]["status"] == "included"
    assert hit["entries"][0]["external_indices"] == [0]
    miss = client.post(
        f"/api/v1/lorebooks/{book['id']}/preview", json={"messages": ["chat"]}
    ).json()
    assert miss["entries"][0]["status"] == "not_triggered"


# ------------------------------------------------------- migration 0029


def test_migration_head_is_0029_p037():
    assert MIGRATIONS[-1][0] == "0029"
    assert MIGRATIONS[-2][0] == "0028"
    assert MIGRATIONS[-3][0] == "0027"


def test_migration_0029_columns_exist_and_default(tmp_path):
    import sqlite3

    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1]: row for row in conn.execute("PRAGMA table_info(lorebooks)")}
        assert "scan_mode" in cols and "scan_external_context" in cols
        conn.execute(
            "INSERT INTO lorebooks (id, user_id, name, description, created_at) VALUES ('b1', 'u', 'Raw', '', '2026-01-01T00:00:00')"
        )
        row = conn.execute(
            "SELECT scan_mode, scan_external_context FROM lorebooks WHERE id = 'b1'"
        ).fetchone()
        assert row == ("depth", 0)  # raw rows default to pre-P-037 behaviour
    finally:
        conn.close()


def test_old_database_upgrades_in_place_preserving_books(tmp_path):
    import sqlite3

    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE schema_migrations (revision TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for revision, _desc, module in MIGRATIONS:
            if revision > "0028":
                continue
            module.upgrade(conn)
            conn.execute(
                "INSERT INTO schema_migrations (revision, applied_at) VALUES (?, '2026-01-01T00:00:00')",
                (revision,),
            )
        conn.commit()
        conn.execute(
            "INSERT INTO lorebooks (id, user_id, name, description, scan_depth, created_at) VALUES ('old', 'u', 'Old Book', '', 7, '2026-01-01T00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()
    applied = migrate_to_head(db_path)
    assert applied == ["0029"]
    assert current_revision(db_path) == "0029"
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT name, scan_depth, scan_mode, scan_external_context FROM lorebooks WHERE id = 'old'"
        ).fetchone()
        assert row == ("Old Book", 7, "depth", 0)
    finally:
        conn.close()


# ------------------------------------------------------- file layer


def test_transfer_export_carries_scan_settings():
    out = transfer.export_book(
        {
            "name": "B", "description": "", "scan_depth": 3, "token_budget": None,
            "scan_mode": "whole_chat", "scan_external_context": True,
        },
        [],
    )
    assert out["scan_mode"] == "whole_chat" and out["scan_external_context"] is True
    defaulted = transfer.export_book({"name": "B"}, [])
    assert defaulted["scan_mode"] == "depth"
    assert defaulted["scan_external_context"] is False


def test_transfer_parse_import_native_tolerant():
    book, _entries = transfer.parse_import(
        {
            "name": "B", "entries": [], "scan_depth": 5,
            "scan_mode": "whole_chat", "scan_external_context": True,
        }
    )
    assert book["scan_mode"] == "whole_chat" and book["scan_external_context"] is True
    # The file layer is tolerant: an unknown mode falls back to
    # the narrow default, never to a wider window.
    book2, _ = transfer.parse_import(
        {"name": "B", "entries": [], "scan_mode": "wide"}
    )
    assert book2["scan_mode"] == "depth"


async def test_transfer_import_book_stores_settings(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    data = {
        "format": "runmal-lorebook", "version": 1, "name": "Imported",
        "description": "", "scan_depth": 2, "token_budget": None,
        "scan_mode": "whole_chat", "scan_external_context": True,
        "entries": [],
    }
    async with factory() as session:
        book = await transfer.import_book(session, user_id, data)
        assert book.scan_mode == "whole_chat" and book.scan_external_context is True
        book2 = await transfer.import_book_transactional(session, user_id, data)
        assert book2.scan_mode == "whole_chat" and book2.scan_external_context is True


def test_interop_native_file_round_trip():
    raw = json.dumps(
        {
            "format": "runmal-lorebook", "version": 1, "name": "Native",
            "description": "d", "scan_depth": 3, "token_budget": 50,
            "scan_mode": "whole_chat", "scan_external_context": True,
            "entries": [],
        }
    )
    parsed = parse_lorebook_file(raw)
    assert parsed.scan_mode == "whole_chat" and parsed.scan_external_context is True
    assert parsed.native_book_fields()["scan_mode"] == "whole_chat"
    out = export_native(parsed)
    assert out["scan_mode"] == "whole_chat" and out["scan_external_context"] is True
    again = parse_lorebook_file(json.dumps(out))
    assert again.scan_mode == "whole_chat" and again.scan_external_context is True


def test_interop_worldinfo_corpus_preservation_unchanged():
    full = parse_lorebook_file((CORPUS / "lorebook_worldinfo_full.json").read_bytes())
    # Book settings ride in originalData, verbatim (P-019 discipline).
    assert full.original_data == {"scan_depth": 4}
    # The per-entry world-info scanDepth stays preserved-as-data;
    # P-037 claims no per-entry semantics for it.
    gale = full.entries[0]  # "The Gale-Bell", uid "0" (the P-019 corpus order)
    assert "scanDepth" in gale.extra and gale.extra["scanDepth"] is None


def test_worldinfo_from_native_with_settings():
    out = worldinfo_from_native(
        {
            "name": "B", "description": "", "scan_depth": 4, "token_budget": None,
            "scan_mode": "whole_chat", "scan_external_context": True,
        },
        [],
    )
    assert out["name"] == "B" and out["entries"] == {}


def test_library_hash_distinguishes_scan_settings():
    base = {"name": "B", "description": "", "scan_depth": 4, "token_budget": None}
    depth_hash = _lorebook_hash(base, [])
    whole_hash = _lorebook_hash({**base, "scan_mode": "whole_chat"}, [])
    ext_hash = _lorebook_hash({**base, "scan_external_context": True}, [])
    assert len({depth_hash, whole_hash, ext_hash}) == 3


# ------------------------------------------------------- prompt inspector


async def test_inspect_prompt_honours_book_scan_mode(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    messages = ["aurora", "f", "f", "f"]
    async with factory() as session:
        whole = await service.create_lorebook(
            session, user_id, "Whole", scan_depth=1, scan_mode="whole_chat"
        )
        entry = await service.create_entry(
            session, user_id, whole.id, name="Old", content="aurora lore", keys=["aurora"]
        )
        trace = await inspect_prompt(
            session, user_id, lorebook_ids=[whole.id], messages=messages
        )
        slots = {s["slot_id"]: s for s in trace["slots"]}
        assert slots[f"lore/{entry.id}"]["status"] != "discarded"
    async with factory() as session:
        depth_book = await service.create_lorebook(session, user_id, "Depth", scan_depth=1)
        entry2 = await service.create_entry(
            session, user_id, depth_book.id, name="Old", content="aurora lore", keys=["aurora"]
        )
        trace = await inspect_prompt(
            session, user_id, lorebook_ids=[depth_book.id], messages=messages
        )
        slots = {s["slot_id"]: s for s in trace["slots"]}
        assert slots[f"lore/{entry2.id}"]["status"] == "discarded"
        assert slots[f"lore/{entry2.id}"]["reason"] == "not_triggered"


async def test_inspect_supplies_persona_as_external_context(tmp_path):
    # The inspector holds the character's persona text: it is the
    # external context for the scan, admitted only by books whose
    # own scan_external_context setting is on.
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        character = Character(
            user_id=user_id,
            name="Sigrun",
            card_json=json.dumps(
                {"description": "A wandering blacksmith of the fjords"}
            ),
        )
        session.add(character)
        await session.commit()
        on = await service.create_lorebook(
            session, user_id, "On", scan_external_context=True
        )
        on_entry = await service.create_entry(
            session, user_id, on.id, name="Smith", content="smith lore",
            keys=["blacksmith"],
        )
        off = await service.create_lorebook(session, user_id, "Off")
        off_entry = await service.create_entry(
            session, user_id, off.id, name="Smith", content="smith lore",
            keys=["blacksmith"],
        )
        trace = await inspect_prompt(
            session,
            user_id,
            character_id=character.id,
            lorebook_ids=[on.id, off.id],
            messages=["a quiet evening"],
        )
        slots = {s["slot_id"]: s for s in trace["slots"]}
        assert slots[f"lore/{on_entry.id}"]["status"] != "discarded"
        assert slots[f"lore/{off_entry.id}"]["status"] == "discarded"
        assert slots[f"lore/{off_entry.id}"]["reason"] == "not_triggered"
