"""P-036 acceptance: probability & RNG honesty.

Roadmap line: *Probability & RNG honesty: probabilistic entries
use a seeded, inspectable roll (the Sagnaskemma dice discipline's
kin).*

Contract under test:
- ``runmal.lorebooks.rng`` is the pure roll module: a gated
  entry's roll derives from (seed, context, entry_id) alone via
  SHA-256 (algorithm ``runmal-p036-roll-v1``), so the same seed +
  same inputs reproduce the same outcome -- per entry, in
  isolation, in any candidate order, with any neighbours. The
  roll does not depend on the probability itself: re-judging the
  same recorded roll against a raised/lowered threshold flips
  the outcome predictably. ``seed=None`` rolls are recorded with
  ``seeded=False`` -- inspectable, honestly not reproducible.
- ``resolve_budget`` records every gated candidate's roll on
  ``BudgetResult.rolls`` (pass or fail); ungated candidates
  (probability 1.0) make and record no roll; a failed roll still
  discards with S204's ``probability_skip``.
- The stored entry carries ``probability`` as an integer percent
  (migration 0028, PROVISIONAL -- 0027 is reserved for P-035;
  default 100 = gate off = exactly pre-P-036 behaviour); the
  service validates strictly, the API surfaces bad values as
  422, and ``entry_to_dict`` reports it.
- Preview finally gates: candidates carry the stored percent,
  rows report ``probability`` + the inspectable
  ``probability_roll`` record, and the result reports the seed,
  the roll context and every roll made.
- Import/export carry the field: world-info ``probability`` /
  ``useProbability`` are first-class (promoted out of ``extra``);
  an explicit ``useProbability=false`` folds to the effective
  percent 100 on the DB path; native files carry ``probability``
  (and the file model carries ``use_probability``).
"""

from __future__ import annotations

import itertools
import json
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
from runmal.lorebooks.budget import BudgetCandidate, resolve_budget
from runmal.lorebooks.interop import (
    export_native,
    export_worldinfo,
    parse_lorebook_file,
)
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.rng import (
    DEFAULT_PROBABILITY,
    ROLL_ALGORITHM,
    check_probability,
    derive_roll,
    explain_roll,
    normalise_probability,
    probability_fraction,
    roll_probability,
)
from runmal.lorebooks.service import entry_to_dict

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


def cand(eid, probability=1.0, priority=100, content="x" * 100):
    return BudgetCandidate(
        entry_id=eid, content=content, priority=priority, probability=probability
    )


# ------------------------------------------------------- vocabulary checks


def test_check_probability_strict():
    assert check_probability(0) == 0
    assert check_probability(80) == 80
    assert check_probability(100) == 100
    for bad in (-1, 101, True, False, 1.5, 80.0, "80", None):
        with pytest.raises(ValueError):
            check_probability(bad)


def test_normalise_probability_tolerant():
    assert normalise_probability(None) == DEFAULT_PROBABILITY
    assert normalise_probability(True) == DEFAULT_PROBABILITY
    assert normalise_probability(80) == 80
    assert normalise_probability(0) == 0
    assert normalise_probability(80.9) == 80
    assert normalise_probability("80") == 80
    assert normalise_probability("80.5") == 80
    assert normalise_probability("junk") == DEFAULT_PROBABILITY
    # out-of-range falls back to the default, never a clamped gate
    assert normalise_probability(-3) == DEFAULT_PROBABILITY
    assert normalise_probability(140) == DEFAULT_PROBABILITY


def test_probability_fraction():
    assert probability_fraction(100) == 1.0
    assert probability_fraction(80) == 0.8
    assert probability_fraction(0) == 0.0
    with pytest.raises(ValueError):
        probability_fraction(101)


# ------------------------------------------------------------- the roll


def test_roll_reproduces_same_seed_same_inputs():
    # THE core proof: same seed + same inputs -> same outcome.
    first = roll_probability("gale", 0.5, seed=42, context="chat-1")
    for _ in range(25):
        again = roll_probability("gale", 0.5, seed=42, context="chat-1")
        assert again == first
    assert first.seeded is True and first.seed == 42
    assert first.algorithm == ROLL_ALGORITHM
    assert 0.0 <= first.roll < 1.0
    assert first.passed == (first.roll < 0.5)


def test_roll_matches_derive_roll_and_explain():
    r = roll_probability("gale", 0.25, seed=7, context="tick-9")
    assert r.roll == derive_roll("gale", 7, "tick-9")
    assert explain_roll("gale", 0.25, seed=7, context="tick-9") == r.to_dict()
    d = r.to_dict()
    assert set(d) == {
        "entry_id", "probability", "roll", "passed",
        "seed", "seeded", "context", "algorithm",
    }


def test_roll_depends_on_seed_context_and_entry():
    base = derive_roll("gale", 42, "ctx")
    assert derive_roll("gale", 43, "ctx") != base
    assert derive_roll("gale", 42, "other") != base
    assert derive_roll("harbour", 42, "ctx") != base
    assert derive_roll("gale", 42, "ctx") == base


def test_roll_does_not_depend_on_probability_threshold_rejudged():
    # The same recorded roll, re-judged: lowering the threshold
    # below the roll flips pass->fail; raising it above flips back.
    r = roll_probability("gale", 0.5, seed=42)
    below = roll_probability("gale", r.roll / 2 if r.roll else 0.0, seed=42)
    assert below.roll == r.roll and below.passed is False
    above_p = min(1.0, r.roll + (1.0 - r.roll) / 2) if r.roll < 1.0 else 1.0
    above = roll_probability("gale", above_p, seed=42)
    assert above.roll == r.roll and above.passed is True


def test_unseeded_roll_is_labelled_not_reproducible():
    r = roll_probability("gale", 0.5)  # seed=None
    assert r.seed is None and r.seeded is False
    assert 0.0 <= r.roll < 1.0 and r.passed == (r.roll < 0.5)


def test_roll_rejects_bad_inputs():
    with pytest.raises(ValueError):
        roll_probability("gale", 1.5, seed=1)
    with pytest.raises(ValueError):
        roll_probability("gale", -0.1, seed=1)
    with pytest.raises(ValueError):
        roll_probability("gale", True, seed=1)
    with pytest.raises(ValueError):
        derive_roll("", 1)
    with pytest.raises(ValueError):
        derive_roll("gale", True)
    with pytest.raises(ValueError):
        derive_roll("gale", 1, context=7)


def test_roll_distribution_is_not_degenerate():
    rolls = [derive_roll(f"e{i}", 2026) for i in range(200)]
    assert len(set(rolls)) == 200
    frac = sum(1 for v in rolls if v < 0.5) / len(rolls)
    assert 0.35 < frac < 0.65

# ------------------------------------------------------------- the budget


def test_budget_records_roll_for_every_gated_candidate():
    cands = [cand("a", 0.5), cand("b", 1.0), cand("c", 0.25)]
    r = resolve_budget(cands, 10000, seed=99)
    assert [roll.entry_id for roll in r.rolls] == ["a", "c"]  # b ungated: no roll
    for roll in r.rolls:
        assert roll.seed == 99 and roll.seeded is True
        decided = {e.entry_id for e in r.included} | {d.entry_id for d in r.discarded}
        assert roll.entry_id in decided
        if roll.passed:
            assert roll.entry_id in {e.entry_id for e in r.included}
        else:
            d = next(d for d in r.discarded if d.entry_id == roll.entry_id)
            assert d.reason == "probability_skip"


def test_budget_same_seed_same_inputs_reproduce_outcome():
    cands = [cand(f"e{i}", 0.5) for i in range(20)]
    r1 = resolve_budget(cands, 10000, seed=1234)
    r2 = resolve_budget(cands, 10000, seed=1234)
    assert r1 == r2
    assert 0 < len(r1.included) < 20  # the seed actually gates


def test_budget_roll_independent_of_order_and_neighbours():
    # Each entry's roll is its own: permuting the candidate list,
    # or removing/adding neighbours, never changes it. (Pre-P-036
    # sequential draws failed exactly this.)
    base = [cand(f"e{i}", 0.5, priority=100 - i) for i in range(6)]
    reference = {roll.entry_id: roll for roll in resolve_budget(base, 10000, seed=5).rolls}
    for perm in itertools.permutations(base):
        got = {roll.entry_id: roll for roll in resolve_budget(list(perm), 10000, seed=5).rolls}
        assert got == reference
    solo = resolve_budget([base[3]], 10000, seed=5)
    assert solo.rolls[0] == reference[base[3].entry_id]
    assert (base[3].entry_id in {e.entry_id for e in solo.included}) == reference[
        base[3].entry_id
    ].passed


def test_budget_probability_zero_records_roll_and_skips():
    r = resolve_budget([cand("a", 0.0), cand("b", 1.0)], 10000, seed=42)
    assert [e.entry_id for e in r.included] == ["b"]
    assert r.discarded[0].reason == "probability_skip"
    assert len(r.rolls) == 1 and r.rolls[0].passed is False


def test_budget_context_changes_rolls_reproducibly():
    cands = [cand(f"e{i}", 0.5) for i in range(10)]
    a = resolve_budget(cands, 10000, seed=3, context="chat-1")
    b = resolve_budget(cands, 10000, seed=3, context="chat-1")
    c = resolve_budget(cands, 10000, seed=3, context="chat-2")
    assert a == b
    assert {r.entry_id: r.roll for r in a.rolls} != {r.entry_id: r.roll for r in c.rolls}


def test_budget_unseeded_rolls_are_labelled():
    r = resolve_budget([cand("a", 0.5)], 10000)  # seed=None
    assert len(r.rolls) == 1
    assert r.rolls[0].seed is None and r.rolls[0].seeded is False


# ------------------------------------------------------------- preview


class FakeRow:
    def __init__(self, eid, key, content, **kw):
        self.id = eid
        self.name = eid
        self.content = content
        self.enabled = kw.get("enabled", True)
        self.constant = kw.get("constant", False)
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
        self.probability = kw.get("probability", 100)


def test_preview_gates_on_stored_probability_and_shows_roll():
    rows = [
        FakeRow("never", "gale", "never lore", probability=0),
        FakeRow("always", "gale", "always lore", probability=100),
        FakeRow("coin", "gale", "coin lore", probability=50),
    ]
    out = preview_activation(rows, ["the gale rises"], 1, None, seed=11, roll_context="t1")
    by_id = {r["entry_id"]: r for r in out["entries"]}
    assert by_id["never"]["status"] == "discarded"
    assert by_id["never"]["discard_reason"] == "probability_skip"
    assert by_id["never"]["probability"] == 0
    assert by_id["never"]["probability_roll"]["passed"] is False
    assert by_id["always"]["status"] == "included"
    assert by_id["always"]["probability_roll"] is None  # ungated: no roll
    coin = by_id["coin"]
    assert coin["probability"] == 50 and coin["probability_roll"] is not None
    assert coin["probability_roll"]["seed"] == 11
    assert coin["probability_roll"]["context"] == "t1"
    assert coin["status"] == ("included" if coin["probability_roll"]["passed"] else "discarded")
    assert out["seed"] == 11 and out["roll_context"] == "t1"
    assert {r["entry_id"] for r in out["probability_rolls"]} == {"never", "coin"}


def test_preview_reproduces_roll_for_roll():
    rows = [FakeRow(f"e{i}", "gale", f"lore {i}", probability=50) for i in range(8)]
    first = preview_activation(rows, ["gale"], 1, None, seed=77, roll_context="abc")
    for _ in range(10):
        again = preview_activation(rows, ["gale"], 1, None, seed=77, roll_context="abc")
        assert again == first


def test_preview_without_gated_entries_has_no_rolls_key():
    rows = [FakeRow("a", "gale", "gale lore")]  # FakeRow has no probability attr default path
    out = preview_activation(rows, ["gale"], 1, None, seed=1)
    assert "probability_rolls" not in out
    assert out["entries"][0]["probability"] == 100
    assert out["entries"][0]["probability_roll"] is None


# ------------------------------------------------- service / API / store


async def _book(factory, user_id):
    async with factory() as session:
        book = await service.create_lorebook(session, user_id, "Prob")
        return book.id


async def test_service_create_update_round_trip(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await _book(factory, user_id)
    async with factory() as session:
        entry = await service.create_entry(
            session, user_id, book_id, name="Gale", keys=["gale"], probability=80
        )
        assert entry.probability == 80
        assert entry_to_dict(entry)["probability"] == 80
        updated = await service.update_entry(
            session, user_id, book_id, entry.id, probability=0
        )
        assert updated.probability == 0


async def test_service_defaults_are_pre_p036_behaviour(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await _book(factory, user_id)
    async with factory() as session:
        entry = await service.create_entry(session, user_id, book_id, name="Plain")
        assert entry.probability == 100
        assert entry_to_dict(entry)["probability"] == 100


async def test_service_rejects_bad_probability(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await _book(factory, user_id)
    async with factory() as session:
        for bad in (-1, 101, True, 50.5, "50"):
            with pytest.raises(ValueError):
                await service.create_entry(session, user_id, book_id, probability=bad)
        entry = await service.create_entry(session, user_id, book_id, name="E")
        with pytest.raises(ValueError):
            await service.update_entry(session, user_id, book_id, entry.id, probability=101)


def test_api_entry_probability_and_422(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book = client.post("/api/v1/lorebooks", json={"name": "B"}).json()
    ok = client.post(
        f"/api/v1/lorebooks/{book['id']}/entries",
        json={"name": "Gale", "keys": ["gale"], "probability": 80},
    )
    assert ok.status_code == 201 and ok.json()["probability"] == 80
    plain = client.post(f"/api/v1/lorebooks/{book['id']}/entries", json={"name": "Plain"})
    assert plain.json()["probability"] == 100
    for payload in ({"probability": 101}, {"probability": -1}):
        bad = client.post(f"/api/v1/lorebooks/{book['id']}/entries", json=payload)
        assert bad.status_code == 422
        bad_patch = client.patch(
            f"/api/v1/lorebooks/{book['id']}/entries/{ok.json()['id']}", json=payload
        )
        assert bad_patch.status_code == 422
    patched = client.patch(
        f"/api/v1/lorebooks/{book['id']}/entries/{ok.json()['id']}", json={"probability": 25}
    )
    assert patched.status_code == 200 and patched.json()["probability"] == 25


def test_api_preview_seed_and_context_reproduce(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book = client.post("/api/v1/lorebooks", json={"name": "B"}).json()
    for i in range(4):
        r = client.post(
            f"/api/v1/lorebooks/{book['id']}/entries",
            json={"name": f"E{i}", "keys": ["gale"], "content": f"lore {i}", "probability": 50},
        )
        assert r.status_code == 201
    body = {"messages": ["the gale rises"], "seed": 5, "roll_context": "chat-9"}
    first = client.post(f"/api/v1/lorebooks/{book['id']}/preview", json=body).json()
    again = client.post(f"/api/v1/lorebooks/{book['id']}/preview", json=body).json()
    assert first == again
    assert first["seed"] == 5 and first["roll_context"] == "chat-9"
    assert len(first["probability_rolls"]) == 4


# ---------------------------------------------------------------- migration


def test_migration_head_is_0028_provisional():
    # 0027 is reserved for P-035 (entry states, concurrent, banks
    # first); the merged sequence runs 0026 -> 0027 -> 0028.
    assert MIGRATIONS[-1][0] == "0028"
    assert MIGRATIONS[-2][0] == "0027"
    assert MIGRATIONS[-3][0] == "0026"


def test_migration_0028_column_exists_and_defaults(tmp_path):
    import sqlite3

    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1]: row for row in conn.execute("PRAGMA table_info(lore_entries)")}
        assert "probability" in cols
        conn.execute(
            "INSERT INTO lore_entries (id, lorebook_id, user_id, name, created_at) VALUES ('e1', 'b', 'u', 'Raw', '2026-01-01T00:00:00')"
        )
        row = conn.execute("SELECT probability FROM lore_entries WHERE id = 'e1'").fetchone()
        assert row == (100,)  # raw rows default to gate-off
    finally:
        conn.close()


def test_old_database_upgrades_in_place_preserving_entries(tmp_path):
    import sqlite3

    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE schema_migrations (revision TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for revision, _desc, module in MIGRATIONS:
            if revision > "0026":
                continue
            module.upgrade(conn)
            conn.execute(
                "INSERT INTO schema_migrations (revision, applied_at) VALUES (?, '2026-01-01T00:00:00')",
                (revision,),
            )
        conn.commit()
        conn.execute(
            "INSERT INTO lore_entries (id, lorebook_id, user_id, name, priority, created_at) VALUES ('old1', 'b', 'u', 'Old', 42, '2026-01-01T00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()
    applied = migrate_to_head(db_path)
    assert applied == ["0027", "0028"]
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT probability, priority FROM lore_entries WHERE id = 'old1'"
        ).fetchone()
        assert row == (100, 42)  # pre-P-036 entries read back gate-off
    finally:
        conn.close()


# ------------------------------------------------------- transfer + interop


def test_transfer_worldinfo_probability_and_use_probability_fold():
    _book, entries = transfer.parse_import(
        json.loads((CORPUS / "lorebook_worldinfo_full.json").read_text(encoding="utf-8"))
    )
    gale, harbour, tithe = entries
    assert gale["probability"] == 80  # useProbability=true: percent carried
    assert harbour["probability"] == 100  # useProbability=false folds to gate-off
    assert tithe["probability"] == 100  # absent: default


def test_transfer_native_probability_round_trip():
    data = {
        "name": "Native Prob",
        "entries": [{"name": "Coin", "content": "c", "keys": ["coin"], "probability": 30}],
    }
    _book, entries = transfer.parse_import(data)
    assert entries[0]["probability"] == 30
    out = transfer.export_book(
        {"name": "Native Prob"}, [dict(entries[0], keys=["coin"], secondary_keys=[])]
    )
    assert out["entries"][0]["probability"] == 30


def test_interop_probability_first_class_and_fixed_point():
    book = parse_lorebook_file((CORPUS / "lorebook_worldinfo_full.json").read_bytes())
    gale, harbour, _tithe = book.entries
    assert gale.probability == 80 and gale.use_probability is True
    assert harbour.probability == 100 and harbour.use_probability is False
    assert "probability" not in gale.extra and "useProbability" not in gale.extra
    assert gale.native_fields()["probability"] == 80
    assert gale.native_fields()["use_probability"] is True
    once = export_worldinfo(book)
    assert once["entries"]["0"]["probability"] == 80
    assert once["entries"]["0"]["useProbability"] is True
    assert once["entries"]["1"]["useProbability"] is False
    twice = export_worldinfo(parse_lorebook_file(json.dumps(once)))
    assert twice == once
    native = export_native(book)
    assert native["entries"][0]["probability"] == 80
    assert export_native(parse_lorebook_file(json.dumps(native))) == native
