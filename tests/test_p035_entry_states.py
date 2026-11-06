"""P-035 acceptance: entry states for lorebook entries.

Roadmap line: *Entry states: constant / selective / vectorised
activation kinds, one engine.*

Contract under test:
- ``runmal.lorebooks.states`` is a pure module owning the
  activation-kind vocabulary: exactly three kinds
  (``constant`` / ``selective`` / ``vectorised``), a strict
  checker, a tolerant normaliser (default ``selective``), a
  tolerant ``vectorised`` flag coercion, and the derivation
  ``activation_kind_for`` with precedence
  constant > vectorised > selective (a both-flags entry is
  constant, and its vectorised flag is still carried).
  ``vectorized`` (US spelling) is a *file* field, never a kind.
- Migration 0027 adds ``lore_entries.vectorised`` (default
  False = exactly pre-P-035 behaviour); the kind itself is
  derived, never stored.
- One engine: ``activate()`` dispatches on the derived kind.
  Constant fires via ``"constant"`` with no hits; selective
  fires via ``"key"`` on a keyword hit only; vectorised fires
  via ``"vector"`` on a caller-supplied vector hit only
  (``vector_hit_ids``; the embedding matcher itself is P-041).
  The two hit kinds never cross, disabled entries never fire,
  and the timing knobs (sticky / cooldown / delay) and the
  inclusion groups apply to the vector kind exactly as to keys.
- The keyword scanner never scans vectorised entries (plain or
  recursive); their hits arrive from vector matching only.
- Preview reports every row's ``vectorised`` flag and derived
  ``activation_kind``; a vector-fired row honestly reports
  ``matched_primary`` / ``matched_secondary`` empty with
  ``via="vector"``, and a vectorised entry whose key sits in
  the messages but which has no vector hit is not triggered.
- The service and the API carry ``vectorised`` on create and
  PATCH; ``entry_to_dict`` reports ``vectorised`` +
  ``activation_kind``.
- Files: world-info ``vectorized`` maps to native
  ``vectorised`` on both file legs (transfer + interop), the
  legacy native alias ``"vectorized"`` is accepted on import,
  native export emits ``vectorised``, and world-info export
  writes ``vectorized`` only under the no-fabrication rule
  (source carried it, or the entry is vectorised).
- Per chat, ``run_activation_tick(..., vector_hit_ids=...)``
  passes vector hits through the persistence seam so a stored
  vectorised entry fires from its stored row.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import service as chats_service
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.lorebooks import service, transfer
from runmal.lorebooks.activation import ActivatableEntry, activate
from runmal.lorebooks.interop import export_worldinfo, parse_lorebook_file
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.scan import ScanEntry, scan_entries, scan_entries_recursive
from runmal.lorebooks.service import entry_to_dict
from runmal.lorebooks.state import run_activation_tick
from runmal.lorebooks.states import (
    ACTIVATION_KINDS,
    activation_kind_for,
    check_activation_kind,
    normalise_activation_kind,
    normalise_vectorised,
)

CORPUS = Path(__file__).parent / "fixtures" / "interop"

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


async def make_chat(factory, user_id, title="chat") -> str:
    async with factory() as session:
        chat = await chats_service.create_chat(session, user_id, title)
        return str(chat.id)


async def make_book(factory, user_id, specs, name="B"):
    """Create a lorebook plus entries; returns (book_id, {label: entry_id})."""
    async with factory() as session:
        book = await service.create_lorebook(session, user_id, name)
        book_id = str(book.id)
        ids: dict[str, str] = {}
        for spec in specs:
            spec = dict(spec)
            label = spec.pop("label")
            entry = await service.create_entry(session, user_id, book_id, **spec)
            ids[label] = str(entry.id)
        return book_id, ids


def ae(eid, **kw):
    base = dict(name=eid, content=f"content of {eid}")
    base.update(kw)
    return ActivatableEntry(id=eid, **base)


def vias(result):
    return [(a.entry_id, a.via) for a in result.activations]


# ------------------------------------------------------------- vocabulary


def test_activation_kinds_vocabulary_is_exactly_the_three():
    assert ACTIVATION_KINDS == {"constant", "selective", "vectorised"}
    assert len(ACTIVATION_KINDS) == 3


@pytest.mark.parametrize("kind", ["constant", "selective", "vectorised"])
def test_check_activation_kind_accepts_the_three_kinds(kind):
    assert check_activation_kind(kind) == kind


@pytest.mark.parametrize("bad", ["CONSTANT", "vectorized", "", None, 1])
def test_check_activation_kind_rejects_non_kinds(bad):
    # "CONSTANT" is the wrong case; "vectorized" (US spelling) is
    # a file field, NOT a kind; "" / None / 1 are not kinds either.
    with pytest.raises(ValueError):
        check_activation_kind(bad)


def test_normalise_activation_kind_is_tolerant_with_selective_default():
    assert normalise_activation_kind("constant") == "constant"
    assert normalise_activation_kind("selective") == "selective"
    assert normalise_activation_kind("vectorised") == "vectorised"
    assert normalise_activation_kind("CONSTANT") == "selective"
    assert normalise_activation_kind("vectorized") == "selective"
    assert normalise_activation_kind("") == "selective"
    assert normalise_activation_kind(None) == "selective"
    assert normalise_activation_kind(1) == "selective"


@pytest.mark.parametrize(
    "raw, expected", [(None, False), (0, False), (1, True)]
)
def test_normalise_vectorised_coercion(raw, expected):
    assert normalise_vectorised(raw) is expected


@pytest.mark.parametrize(
    "constant, vectorised, expected",
    [
        (False, False, "selective"),
        (True, False, "constant"),
        (False, True, "vectorised"),
        (True, True, "constant"),  # constant dominates (precedence)
    ],
)
def test_activation_kind_for_truth_table(constant, vectorised, expected):
    assert activation_kind_for(constant, vectorised) == expected


# -------------------------------------------------------------- migration


def test_migration_head_is_0030_and_sequence_tail():
    assert MIGRATIONS[-1][0] == "0032"
    assert [m[0] for m in MIGRATIONS[-8:]] == ["0025", "0026", "0027", "0028", "0029", "0030", "0031", "0032"]
def test_migration_head_is_0028_and_sequence_tail():
    assert MIGRATIONS[-1][0] == "0032"
    assert [m[0] for m in MIGRATIONS[-8:]] == ["0025", "0026", "0027", "0028", "0029", "0030", "0031", "0032"]


def test_fresh_database_has_vectorised_column(tmp_path):
    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(lore_entries)")}
    finally:
        conn.close()
    assert "vectorised" in cols


def test_fresh_database_raw_row_defaults_vectorised_to_zero(tmp_path):
    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO lore_entries (id, lorebook_id, user_id, name, created_at)"
            " VALUES ('e1', 'b', 'u', 'Raw', '2026-01-01T00:00:00')"
        )
        row = conn.execute(
            "SELECT vectorised FROM lore_entries WHERE id = 'e1'"
        ).fetchone()
    finally:
        conn.close()
    assert row == (0,)  # raw rows default to pre-P-035 behaviour


async def test_existing_behaviour_default_is_false_via_service(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id, ids = await make_book(factory, user_id, [{"label": "plain", "name": "Plain"}])
    async with factory() as session:
        entries = await service.list_entries(session, user_id, book_id)
    assert entries is not None and len(entries) == 1
    assert entry_to_dict(entries[0])["vectorised"] is False
    assert entry_to_dict(entries[0])["activation_kind"] == "selective"
    assert ids["plain"] == str(entries[0].id)


# --------------------------------------------------------- one engine: activate


def test_constant_fires_via_constant_with_no_hits():
    r = activate([ae("c", constant=True)], set())
    assert vias(r) == [("c", "constant")]


def test_both_flags_entry_fires_via_constant_even_when_vector_hit():
    r = activate(
        [ae("both", constant=True, vectorised=True)],
        set(),
        vector_hit_ids={"both"},
    )
    assert vias(r) == [("both", "constant")]


def test_selective_fires_via_key_on_key_hit():
    r = activate([ae("s")], {"s"})
    assert vias(r) == [("s", "key")]


def test_selective_does_not_fire_on_vector_hit_alone():
    r = activate([ae("s")], set(), vector_hit_ids={"s"})
    assert r.activations == []


def test_vectorised_fires_via_vector_on_vector_hit():
    r = activate([ae("v", vectorised=True)], set(), vector_hit_ids={"v"})
    assert vias(r) == [("v", "vector")]


def test_vectorised_does_not_fire_on_key_hit_alone():
    r = activate([ae("v", vectorised=True)], {"v"})
    assert r.activations == []


def test_vectorised_does_not_fire_with_no_hits():
    r = activate([ae("v", vectorised=True)], set())
    assert r.activations == []


def test_disabled_vectorised_never_fires():
    r = activate(
        [ae("v", vectorised=True, enabled=False)], set(), vector_hit_ids={"v"}
    )
    assert r.activations == []


def test_mixed_book_of_three_kinds_fires_all_in_one_call():
    entries = [
        ae("c", constant=True),
        ae("s"),
        ae("v", vectorised=True),
    ]
    r = activate(entries, {"s"}, vector_hit_ids={"v"})
    assert vias(r) == [("c", "constant"), ("s", "key"), ("v", "vector")]


def test_activatable_entry_activation_kind_property():
    assert ae("s").activation_kind == "selective"
    assert ae("c", constant=True).activation_kind == "constant"
    assert ae("v", vectorised=True).activation_kind == "vectorised"
    assert ae("b", constant=True, vectorised=True).activation_kind == "constant"
    assert ae("v").vectorised is False


class _BareRow:
    id = "x"
    name = "x"
    content = "c"
    enabled = True
    constant = False
    sticky_prompts = 0
    cooldown_prompts = 0
    delay_prompts = 0


def test_activatable_from_orm_tolerates_missing_vectorised():
    e = ActivatableEntry.from_orm(_BareRow())
    assert e.vectorised is False
    assert e.activation_kind == "selective"


def test_activatable_from_orm_reads_vectorised_when_present():
    class Row(_BareRow):
        vectorised = 1

    e = ActivatableEntry.from_orm(Row())
    assert e.vectorised is True
    assert e.activation_kind == "vectorised"


# ------------------------------------------------- timing on the vector kind


def test_vectorised_cooldown_suppresses_next_tick_then_fires_again():
    entry = ae("v", vectorised=True, cooldown_prompts=1)
    states: dict = {}
    r1 = activate([entry], set(), states, vector_hit_ids={"v"})
    assert vias(r1) == [("v", "vector")]
    assert states["v"].cooldown_remaining == 1
    r2 = activate([entry], set(), states, vector_hit_ids={"v"})
    assert r2.activations == []  # suppressed despite the vector hit
    r3 = activate([entry], set(), states, vector_hit_ids={"v"})
    assert vias(r3) == [("v", "vector")]


def test_vectorised_delay_arms_on_vector_hit_and_fires_next_tick():
    entry = ae("v", vectorised=True, delay_prompts=1)
    states: dict = {}
    r1 = activate([entry], set(), states, vector_hit_ids={"v"})
    assert r1.activations == []  # the hit only arms the delay
    assert states["v"].delay_armed is True
    r2 = activate([entry], set(), states)  # no hit at all this tick
    assert vias(r2) == [("v", "delay")]


def test_vectorised_sticky_carries_to_next_tick_without_a_hit():
    entry = ae("v", vectorised=True, sticky_prompts=1)
    states: dict = {}
    r1 = activate([entry], set(), states, vector_hit_ids={"v"})
    assert vias(r1) == [("v", "vector")]
    r2 = activate([entry], set(), states)
    assert vias(r2) == [("v", "sticky")]
    r3 = activate([entry], set(), states)
    assert r3.activations == []


# ------------------------------------------------------------ groups interplay


def test_two_vectorised_entries_in_one_group_resolve_to_one_winner():
    entries = [
        ae("win", vectorised=True, inclusion_group="g", group_weight=100),
        ae("lose", vectorised=True, inclusion_group="g", group_weight=10),
    ]
    r = activate(entries, set(), vector_hit_ids={"win", "lose"})
    assert vias(r) == [("win", "vector")]
    assert [(l.entry_id, l.winner_id) for l in r.group_losers] == [("lose", "win")]
    assert [(a.entry_id, a.via) for a in r.group_suppressed] == [("lose", "vector")]


# ---------------------------------------------------------------------- scan


def test_scan_skips_vectorised_even_when_its_key_matches():
    entries = [
        ScanEntry(id="v", vectorised=True, keys=("gale-bell",), content="vec lore"),
        ScanEntry(id="s", keys=("gale-bell",), content="selective lore"),
    ]
    hits = scan_entries(entries, ["the gale-bell rings"], 4)
    assert [h.entry_id for h in hits] == ["s"]  # selective control still hits


def test_recursive_scan_also_skips_vectorised():
    entries = [
        ScanEntry(
            id="parent",
            keys=("alpha",),
            content="parent lore mentions vectorkey and childkey",
        ),
        ScanEntry(id="v", vectorised=True, keys=("vectorkey",), content="vec lore"),
        ScanEntry(id="child", keys=("childkey",), content="child lore"),
    ]
    result = scan_entries_recursive(entries, ["alpha rises"], 4)
    hit_ids = {h.entry_id for h in result.hits}
    assert hit_ids == {"parent", "child"}  # recursive control still pulled in
    assert "v" not in hit_ids


# ------------------------------------------------------------------- preview


class FakeRow:
    def __init__(self, eid, key, content, **kw):
        self.id = eid
        self.name = eid
        self.content = content
        self.enabled = kw.get("enabled", True)
        self.constant = kw.get("constant", False)
        self.vectorised = kw.get("vectorised", False)
        self.keys_json = json.dumps([key] if key else [])
        self.secondary_keys_json = json.dumps(kw.get("secondary", []))
        self.selective_logic = kw.get("selective_logic", "and_any")
        self.whole_word = True
        self.case_sensitive = False
        self.sticky_prompts = 0
        self.cooldown_prompts = 0
        self.delay_prompts = 0
        self.priority = kw.get("priority", 100)
        self.inclusion_group = kw.get("inclusion_group", "")
        self.group_weight = kw.get("group_weight", 100)


def three_kind_rows():
    return [
        FakeRow("c", None, "constant lore", constant=True),
        FakeRow("s", "gale", "selective lore"),
        FakeRow("v", "signal", "vector lore", vectorised=True),
    ]


def test_preview_rows_report_vectorised_and_activation_kind_for_three_kinds():
    out = preview_activation(three_kind_rows(), ["a gale blows"], 1, None)
    rows = {r["entry_id"]: r for r in out["entries"]}
    assert rows["c"]["vectorised"] is False
    assert rows["c"]["activation_kind"] == "constant"
    assert rows["c"]["status"] == "included" and rows["c"]["via"] == "constant"
    assert rows["s"]["vectorised"] is False
    assert rows["s"]["activation_kind"] == "selective"
    assert rows["s"]["status"] == "included" and rows["s"]["via"] == "key"
    assert rows["v"]["vectorised"] is True
    assert rows["v"]["activation_kind"] == "vectorised"
    assert rows["v"]["status"] == "not_triggered"


def test_preview_vector_hit_includes_vectorised_with_honest_empty_matches():
    out = preview_activation(
        three_kind_rows(), ["unrelated chatter"], 1, None, vector_hit_ids={"v"}
    )
    rows = {r["entry_id"]: r for r in out["entries"]}
    row = rows["v"]
    assert row["status"] == "included"
    assert row["via"] == "vector"
    assert row["matched_primary"] == []  # honest: no keyword matched
    assert row["matched_secondary"] == []


def test_preview_vectorised_not_triggered_by_its_key_in_messages():
    out = preview_activation(three_kind_rows(), ["the signal is loud"], 1, None)
    rows = {r["entry_id"]: r for r in out["entries"]}
    assert rows["v"]["status"] == "not_triggered"
    assert rows["v"]["via"] is None


def test_api_preview_accepts_vector_hit_ids_in_request_body(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book = client.post("/api/v1/lorebooks", json={"name": "B"}).json()
    created = client.post(
        f"/api/v1/lorebooks/{book['id']}/entries",
        json={
            "name": "Vec",
            "keys": ["signal"],
            "content": "vector lore",
            "vectorised": True,
        },
    )
    assert created.status_code == 201
    entry_id = created.json()["id"]
    out = client.post(
        f"/api/v1/lorebooks/{book['id']}/preview",
        json={"messages": ["unrelated chatter"], "vector_hit_ids": [entry_id]},
    )
    assert out.status_code == 200
    rows = {r["entry_id"]: r for r in out.json()["entries"]}
    assert rows[entry_id]["status"] == "included"
    assert rows[entry_id]["via"] == "vector"
    assert rows[entry_id]["vectorised"] is True
    assert rows[entry_id]["activation_kind"] == "vectorised"
    assert rows[entry_id]["matched_primary"] == []
    assert rows[entry_id]["matched_secondary"] == []


# ------------------------------------------------------------ service + API


async def test_service_create_entry_defaults_to_selective(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id, _ids = await make_book(factory, user_id, [{"label": "e", "name": "Plain"}])
    async with factory() as session:
        entries = await service.list_entries(session, user_id, book_id)
    d = entry_to_dict(entries[0])
    assert d["vectorised"] is False
    assert d["activation_kind"] == "selective"


async def test_service_create_vectorised_entry(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id, _ids = await make_book(
        factory, user_id, [{"label": "e", "name": "Vec", "vectorised": True}]
    )
    async with factory() as session:
        entries = await service.list_entries(session, user_id, book_id)
    d = entry_to_dict(entries[0])
    assert d["vectorised"] is True
    assert d["activation_kind"] == "vectorised"


async def test_service_constant_plus_vectorised_is_constant_but_flag_kept(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id, _ids = await make_book(
        factory,
        user_id,
        [{"label": "e", "name": "Both", "constant": True, "vectorised": True}],
    )
    async with factory() as session:
        entries = await service.list_entries(session, user_id, book_id)
    d = entry_to_dict(entries[0])
    assert d["constant"] is True
    assert d["vectorised"] is True  # the flag is carried, never dropped
    assert d["activation_kind"] == "constant"


def test_api_create_entry_with_vectorised_true(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book = client.post("/api/v1/lorebooks", json={"name": "B"}).json()
    r = client.post(
        f"/api/v1/lorebooks/{book['id']}/entries",
        json={"name": "Vec", "keys": ["signal"], "content": "v", "vectorised": True},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["vectorised"] is True
    assert body["activation_kind"] == "vectorised"


def test_api_patch_entry_toggles_vectorised(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book = client.post("/api/v1/lorebooks", json={"name": "B"}).json()
    created = client.post(
        f"/api/v1/lorebooks/{book['id']}/entries",
        json={"name": "Plain", "keys": ["gale"], "content": "p"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["vectorised"] is False and body["activation_kind"] == "selective"
    patched = client.patch(
        f"/api/v1/lorebooks/{book['id']}/entries/{body['id']}",
        json={"vectorised": True},
    )
    assert patched.status_code == 200
    assert patched.json()["vectorised"] is True
    assert patched.json()["activation_kind"] == "vectorised"
    back = client.patch(
        f"/api/v1/lorebooks/{book['id']}/entries/{body['id']}",
        json={"vectorised": False},
    )
    assert back.status_code == 200
    assert back.json()["vectorised"] is False
    assert back.json()["activation_kind"] == "selective"


# ------------------------------------------------------------ files: transfer


def test_transfer_parse_import_worldinfo_fixture_vectorised_flags():
    data = json.loads((CORPUS / "lorebook_worldinfo_full.json").read_text("utf-8"))
    _book, entries = transfer.parse_import(data)
    gale, harbour = entries[0], entries[1]
    assert gale["name"] == "The Gale-Bell"
    assert gale["vectorised"] is False
    assert harbour["name"] == "Harbour Law"
    assert harbour["vectorised"] is True
    assert harbour["constant"] is True


def test_transfer_parse_import_native_legacy_vectorized_alias():
    native = {
        "name": "Native Legacy",
        "entries": [
            {
                "name": "Vec",
                "content": "v",
                "keys": ["signal"],
                "vectorized": True,  # legacy native alias (US spelling)
            }
        ],
    }
    _book, entries = transfer.parse_import(native)
    assert entries[0]["vectorised"] is True


def test_transfer_export_book_emits_vectorised():
    book = {"name": "B", "description": "", "scan_depth": 4, "token_budget": None}
    entry = {
        "name": "Vec",
        "content": "v",
        "keys": ["signal"],
        "secondary_keys": [],
        "selective_logic": "and_any",
        "inclusion_group": "",
        "group_weight": 100,
        "priority": 100,
        "position": "before_char",
        "enabled": True,
        "constant": False,
        "vectorised": True,
        "case_sensitive": False,
        "whole_word": True,
        "sticky_prompts": 0,
        "cooldown_prompts": 0,
        "delay_prompts": 0,
    }
    out = transfer.export_book(book, [entry])
    assert out["entries"][0]["vectorised"] is True


def test_validate_parsed_book_prepared_row_carries_vectorised():
    data = {
        "name": "WI",
        "entries": {
            "0": {"comment": "Vec", "content": "v", "key": ["signal"], "vectorized": True}
        },
    }
    book_fields, entry_fields = transfer.parse_import(data)
    prepared = transfer.validate_parsed_book(book_fields, entry_fields)
    assert prepared[0]["vectorised"] is True


def test_interop_parse_lorebook_file_corpus_harbour_is_vectorised():
    book = parse_lorebook_file((CORPUS / "lorebook_worldinfo_full.json").read_bytes())
    harbour = book.entries[1]
    assert harbour.name == "Harbour Law"
    assert harbour.vectorised is True
    assert book.entries[0].vectorised is False


def test_interop_export_worldinfo_vectorized_no_fabrication_rules():
    book = parse_lorebook_file((CORPUS / "lorebook_worldinfo_full.json").read_bytes())
    out = export_worldinfo(book)
    # entry 1 carried vectorized=True in the source: True back out
    assert out["entries"]["1"]["vectorized"] is True
    # entry 0 carried vectorized=False in the source: False back out
    assert out["entries"]["0"]["vectorized"] is False
    # entry 2 never carried the field: none is fabricated for it
    assert "vectorized" not in out["entries"]["2"]


async def test_import_book_transactional_lands_vectorized_worldinfo_entry(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    data = {
        "name": "WI",
        "entries": {
            "0": {"comment": "Vec", "content": "v", "key": ["signal"], "vectorized": True}
        },
    }
    async with factory() as session:
        book = await transfer.import_book_transactional(session, user_id, data)
        entries = await service.list_entries(session, user_id, book.id)
    assert entries is not None and len(entries) == 1
    d = entry_to_dict(entries[0])
    assert d["vectorised"] is True
    assert d["activation_kind"] == "vectorised"


# ------------------------------------------------------------- per-chat tick


async def tick(factory, user_id, chat_id, book_id, hit_ids, **kw):
    """One activation tick in a FRESH session (the restart boundary)."""
    async with factory() as session:
        return await run_activation_tick(
            session, user_id, chat_id, book_id, set(hit_ids), **kw
        )


async def test_tick_vector_hit_fires_stored_vectorised_entry(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    book_id, ids = await make_book(
        factory,
        user_id,
        [{"label": "v", "name": "Vec", "keys": ["signal"], "vectorised": True}],
    )
    result = await tick(
        factory, user_id, chat_id, book_id, set(), vector_hit_ids={ids["v"]}
    )
    assert result is not None
    assert vias(result) == [(ids["v"], "vector")]


async def test_tick_without_vector_hit_leaves_vectorised_entry_quiet(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    chat_id = await make_chat(factory, user_id)
    book_id, ids = await make_book(
        factory,
        user_id,
        [{"label": "v", "name": "Vec", "keys": ["signal"], "vectorised": True}],
    )
    # a keyword hit alone never fires a stored vectorised entry
    result = await tick(factory, user_id, chat_id, book_id, {ids["v"]})
    assert result is not None
    assert result.activations == []

# ------------------------------------------------------- archive carriage


async def test_archive_export_carries_vectorised(tmp_path):
    # The .runmal archive serialises lore entries by table columns
    # (portable/archive.row_to_dict), so the 0027 column rides with
    # no archive change; pin that it actually does.
    import zipfile

    from runmal.portable.archive import export_archive

    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id, ids = await make_book(
        factory,
        user_id,
        [{"label": "v", "name": "Vec", "keys": ["signal"], "vectorised": True}],
    )
    dest = tmp_path / "world.runmal"
    async with factory() as session:
        await export_archive(session, user_id, dest, base_dir=tmp_path)
    with zipfile.ZipFile(dest) as zf:
        member = [n for n in zf.namelist() if n.startswith("lorebooks/")][0]
        payload = json.loads(zf.read(member))
    (entry,) = payload["entries"]
    assert entry["id"] == ids["v"]
    assert entry["vectorised"] in (True, 1)


async def test_archive_restore_preserves_vectorised(tmp_path):
    from runmal.portable.archive import export_archive
    from runmal.portable.restore import import_archive

    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id, ids = await make_book(
        factory,
        user_id,
        [{"label": "v", "name": "Vec", "keys": ["signal"], "vectorised": True}],
    )
    dest = tmp_path / "world.runmal"
    async with factory() as session:
        await export_archive(session, user_id, dest, base_dir=tmp_path)
    report = await import_archive(dest, tmp_path / "restored")
    assert report.ok
    restored_factory = create_session_factory(create_db_engine(Path(report.staged_db)))
    async with restored_factory() as session:
        entries = await service.list_entries(session, user_id, book_id)
    assert entries is not None and len(entries) == 1
    restored = entry_to_dict(entries[0])
    assert restored["vectorised"] is True
    assert restored["activation_kind"] == "vectorised"
