"""P-034 acceptance: inclusion groups for lorebook entries.

Roadmap line: *Inclusion groups: mutually exclusive entries
resolved by weight/priority, deterministically.*

Contract under test:
- ``runmal.lorebooks.groups`` is a pure module owning the group
  label + weight vocabulary and ``resolve_inclusion_groups``:
  among activated candidates sharing a non-empty group exactly
  one wins -- highest ``group_weight``, then highest
  ``priority``, then lowest ``entry_id`` -- with no randomness
  and no wall-clock, so the same candidate set always resolves
  identically, in any input order. Losers carry provenance
  (group, winner id, both weight/priority pairs).
- ``activate()`` filters direct activations through the resolver
  before ``{{lore:...}}`` reference expansion; every via kind
  competes (constant included); reference-pulled entries are not
  group-resolved; a loser's timing state has already advanced.
- The stored entry carries ``inclusion_group`` + ``group_weight``
  (migration 0026, PROVISIONAL -- 0025 is reserved for P-033;
  defaults '' / 100 = exactly pre-P-034 behaviour); the service
  validates strictly, the API surfaces bad values as 422, and
  ``entry_to_dict`` reports both fields.
- Import/export carry them: world-info ``group`` / ``groupWeight``
  map tolerantly, native files carry ``inclusion_group`` /
  ``group_weight``, and world-info export writes the spellings
  under the no-fabrication rule (the Gale-Bell entry: 'weather'
  / 75 in, modelled, back out; the corpus fixed point holds).
- Preview reports losers as ``group_excluded`` (never the budget
  pass's ``discarded``), with ``group_winner_id`` set,
  ``discard_reason`` None, and the fired ``via`` preserved.
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
from runmal.lorebooks.activation import ActivatableEntry, EntryState, activate
from runmal.lorebooks.groups import (
    DEFAULT_GROUP_WEIGHT,
    GroupCandidate,
    check_group_weight,
    check_inclusion_group,
    normalise_group_weight,
    normalise_inclusion_group,
    resolve_inclusion_groups,
)
from runmal.lorebooks.interop import (
    export_worldinfo,
    parse_lorebook_file,
    worldinfo_from_native,
)
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.service import entry_to_dict

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


def cand(eid, group="", weight=100, priority=100):
    return GroupCandidate(
        entry_id=eid, inclusion_group=group, group_weight=weight, priority=priority
    )


def ae(eid, **kw):
    base = dict(name=eid, content=f"content of {eid}")
    base.update(kw)
    return ActivatableEntry(id=eid, **base)


# ------------------------------------------------------- vocabulary checks


def test_check_inclusion_group_strips_and_allows_empty():
    assert check_inclusion_group("  weather ") == "weather"
    assert check_inclusion_group("") == ""
    assert check_inclusion_group("   ") == ""


@pytest.mark.parametrize("bad", [None, 7, 1.5, True, ["weather"], {"g": 1}])
def test_check_inclusion_group_rejects_non_strings(bad):
    with pytest.raises(ValueError):
        check_inclusion_group(bad)


def test_check_inclusion_group_rejects_over_long():
    with pytest.raises(ValueError):
        check_inclusion_group("x" * 201)
    assert check_inclusion_group("x" * 200) == "x" * 200


def test_normalise_inclusion_group_tolerant():
    assert normalise_inclusion_group("  weather ") == "weather"
    assert normalise_inclusion_group(None) == ""
    assert normalise_inclusion_group(7) == ""
    assert normalise_inclusion_group(True) == ""
    assert normalise_inclusion_group("x" * 500) == "x" * 200


def test_check_group_weight_strict():
    assert check_group_weight(0) == 0
    assert check_group_weight(75) == 75
    for bad in (-1, True, False, 1.5, "75", None):
        with pytest.raises(ValueError):
            check_group_weight(bad)


def test_normalise_group_weight_tolerant():
    assert normalise_group_weight(None) == DEFAULT_GROUP_WEIGHT
    assert normalise_group_weight(True) == DEFAULT_GROUP_WEIGHT
    assert normalise_group_weight(75) == 75
    assert normalise_group_weight(75.9) == 75
    assert normalise_group_weight("75") == 75
    assert normalise_group_weight("75.5") == 75
    assert normalise_group_weight("junk") == DEFAULT_GROUP_WEIGHT
    assert normalise_group_weight(-3) == DEFAULT_GROUP_WEIGHT
    assert normalise_group_weight(0) == 0


def test_candidate_validation():
    with pytest.raises(ValueError):
        cand("a", weight=-1)
    with pytest.raises(ValueError):
        cand("a", weight=True)
    with pytest.raises(ValueError):
        cand("a", priority=1.5)
    assert cand("a", group=" weather ").inclusion_group == "weather"


# ------------------------------------------------------------- the resolver


def test_ungrouped_candidates_always_pass():
    r = resolve_inclusion_groups([cand("a"), cand("b", weight=0, priority=0)])
    assert [w.entry_id for w in r.winners] == ["a", "b"]
    assert r.losers == () and r.winner_by_group == {}


def test_empty_and_whitespace_groups_are_ungrouped():
    r = resolve_inclusion_groups([cand("a", group=""), cand("b", group="   ")])
    assert len(r.winners) == 2 and r.losers == ()


def test_single_member_group_is_uncontested():
    r = resolve_inclusion_groups([cand("a", group="weather")])
    assert [w.entry_id for w in r.winners] == ["a"]
    assert r.losers == () and r.winner_by_group == {}


def test_highest_weight_wins_over_priority():
    r = resolve_inclusion_groups(
        [cand("low", "g", weight=10, priority=999), cand("high", "g", weight=20, priority=1)]
    )
    assert [w.entry_id for w in r.winners] == ["high"]
    assert r.winner_by_group == {"g": "high"}
    loser = r.losers[0]
    assert (loser.entry_id, loser.winner_id, loser.reason) == ("low", "high", "inclusion_group")
    assert (loser.group_weight, loser.priority) == (10, 999)
    assert (loser.winner_group_weight, loser.winner_priority) == (20, 1)
    assert loser.inclusion_group == "g"


def test_priority_breaks_weight_tie():
    r = resolve_inclusion_groups(
        [cand("a", "g", weight=50, priority=100), cand("b", "g", weight=50, priority=300)]
    )
    assert [w.entry_id for w in r.winners] == ["b"]


def test_entry_id_breaks_weight_and_priority_tie():
    r = resolve_inclusion_groups(
        [cand("zeta", "g"), cand("alpha", "g"), cand("mid", "g")]
    )
    assert [w.entry_id for w in r.winners] == ["alpha"]
    assert [l.entry_id for l in r.losers] == ["mid", "zeta"]


def test_negative_priority_is_a_valid_tiebreak_value():
    r = resolve_inclusion_groups(
        [cand("a", "g", priority=-5), cand("b", "g", priority=0)]
    )
    assert [w.entry_id for w in r.winners] == ["b"]


def test_weight_zero_competes_and_can_win_on_priority():
    r = resolve_inclusion_groups(
        [cand("a", "g", weight=0, priority=10), cand("b", "g", weight=0, priority=20)]
    )
    assert [w.entry_id for w in r.winners] == ["b"]


def test_groups_are_independent_and_case_sensitive():
    r = resolve_inclusion_groups(
        [
            cand("a", "Weather", weight=10),
            cand("b", "weather", weight=10),
            cand("c", "weather", weight=20),
            cand("d", "tide", weight=1),
        ]
    )
    assert [w.entry_id for w in r.winners] == ["a", "c", "d"]
    assert r.winner_by_group == {"weather": "c"}


def test_winners_keep_input_order():
    r = resolve_inclusion_groups(
        [cand("z", "g2", weight=5), cand("y"), cand("x", "g1", weight=5), cand("w", "g1", weight=9)]
    )
    assert [w.entry_id for w in r.winners] == ["z", "y", "w"]


def test_losers_have_deterministic_order_across_groups():
    r = resolve_inclusion_groups(
        [
            cand("b2", "beta", weight=1),
            cand("a2", "alpha", weight=1),
            cand("b1", "beta", weight=9),
            cand("a1", "alpha", weight=9),
            cand("a3", "alpha", weight=5),
        ]
    )
    assert [(l.inclusion_group, l.entry_id) for l in r.losers] == [
        ("alpha", "a3"),
        ("alpha", "a2"),
        ("beta", "b2"),
    ]


def test_duplicate_entry_id_first_row_is_the_candidate():
    r = resolve_inclusion_groups(
        [cand("a", "g", weight=10), cand("a", "g", weight=999), cand("b", "g", weight=50)]
    )
    # the second 'a' row (weight 999) is ignored: b wins on 50 > 10
    assert [w.entry_id for w in r.winners] == ["b"]
    assert [l.entry_id for l in r.losers] == ["a"]
    assert r.losers[0].group_weight == 10


def test_resolver_accepts_a_generator():
    r = resolve_inclusion_groups(iter([cand("a", "g"), cand("b", "g", weight=1)]))
    assert [w.entry_id for w in r.winners] == ["a"]


# ---------------------------------------------------- determinism (the proof)


def _mixed_candidates():
    return [
        cand("e1", "weather", weight=75, priority=300),
        cand("e2", "weather", weight=75, priority=300),
        cand("e3", "weather", weight=10, priority=999),
        cand("e4", "tide", weight=0, priority=0),
        cand("e5", "tide", weight=0, priority=0),
        cand("e6"),
    ]


def test_repeated_resolution_is_identical_50_times():
    first = resolve_inclusion_groups(_mixed_candidates())
    for _ in range(50):
        again = resolve_inclusion_groups(_mixed_candidates())
        assert again.winners == first.winners
        assert again.losers == first.losers
        assert again.winner_by_group == first.winner_by_group


def test_winner_set_is_input_order_independent_all_permutations():
    base = _mixed_candidates()
    expected_winners = {"e1", "e4", "e6"}
    expected_losers = {"e2", "e3", "e5"}
    for perm in itertools.permutations(base):
        r = resolve_inclusion_groups(list(perm))
        assert {w.entry_id for w in r.winners} == expected_winners
        assert {l.entry_id for l in r.losers} == expected_losers
        assert r.winner_by_group == {"weather": "e1", "tide": "e4"}
        # losers are fully deterministic too: same tuple every order
        assert r.losers == resolve_inclusion_groups(base).losers


# ---------------------------------------------------------------- activation


def test_activation_grouped_key_hits_resolve_to_one():
    entries = [
        ae("a", inclusion_group="weather", group_weight=75, priority=300),
        ae("b", inclusion_group="weather", group_weight=100, priority=100),
    ]
    r = activate(entries, {"a", "b"})
    assert [a.entry_id for a in r.activations] == ["b"]
    assert [(l.entry_id, l.winner_id) for l in r.group_losers] == [("a", "b")]
    assert [(a.entry_id, a.via) for a in r.group_suppressed] == [("a", "key")]


def test_activation_constant_and_key_compete_in_one_group():
    entries = [
        ae("c", constant=True, inclusion_group="g", group_weight=10),
        ae("k", inclusion_group="g", group_weight=20),
    ]
    r = activate(entries, {"k"})
    assert [(a.entry_id, a.via) for a in r.activations] == [("k", "key")]
    assert [(a.entry_id, a.via) for a in r.group_suppressed] == [("c", "constant")]


def test_activation_ungrouped_behaviour_unchanged():
    entries = [ae("a"), ae("b", constant=True)]
    r = activate(entries, {"a"})
    assert [a.entry_id for a in r.activations] == ["a", "b"]
    assert r.group_losers == () and r.group_suppressed == ()


def test_activation_uncontested_group_behaves_unchanged():
    entries = [ae("a", inclusion_group="solo", group_weight=1)]
    r = activate(entries, {"a"})
    assert [a.entry_id for a in r.activations] == ["a"]
    assert r.group_losers == () and r.group_suppressed == ()


def test_activation_loser_timing_state_already_advanced():
    # The loser fired this tick, so its sticky was armed even though
    # the group excluded it; next tick, uncontested, it fires via
    # sticky. Group exclusion is inclusion, not un-firing.
    entries = [
        ae("win", inclusion_group="g", group_weight=100),
        ae("lose", inclusion_group="g", group_weight=1, sticky_prompts=2),
    ]
    states: dict = {}
    r1 = activate(entries, {"win", "lose"}, states)
    assert [a.entry_id for a in r1.activations] == ["win"]
    assert states["lose"].sticky_remaining == 2
    r2 = activate(entries, set(), states)
    assert [(a.entry_id, a.via) for a in r2.activations] == [("lose", "sticky")]


def test_activation_reference_expansion_is_not_group_resolved():
    entries = [
        ae("win", inclusion_group="g", group_weight=100, content="see {{lore:lose}}"),
        ae("lose", name="lose", inclusion_group="g", group_weight=1),
    ]
    r = activate(entries, {"win", "lose"})
    vias = {(a.entry_id, a.via) for a in r.activations}
    assert ("win", "key") in vias
    assert ("lose", "reference") in vias  # explicit reference wins over the group
    assert [l.entry_id for l in r.group_losers] == ["lose"]


def test_activation_winner_references_still_expand():
    entries = [
        ae("win", inclusion_group="g", group_weight=100, content="base {{lore:other}}"),
        ae("lose", inclusion_group="g", group_weight=1),
        ae("other", name="other"),
    ]
    r = activate(entries, {"win", "lose"})
    assert [(a.entry_id, a.via) for a in r.activations] == [
        ("win", "key"),
        ("other", "reference"),
    ]
    assert r.activations[0].content == "base content of other"


def test_activatable_entry_validation_and_defaults():
    e = ae("a")
    assert e.inclusion_group == "" and e.group_weight == DEFAULT_GROUP_WEIGHT
    assert e.priority == 100
    with pytest.raises(ValueError):
        ae("a", group_weight=-1)
    with pytest.raises(ValueError):
        ae("a", inclusion_group=7)
    assert ae("a", inclusion_group="  weather ").inclusion_group == "weather"


def test_activatable_from_orm_tolerates_missing_group_fields():
    class Bare:
        id = "x"
        name = "x"
        content = "c"
        enabled = True
        constant = False
        sticky_prompts = 0
        cooldown_prompts = 0
        delay_prompts = 0

    e = ActivatableEntry.from_orm(Bare())
    assert e.inclusion_group == "" and e.group_weight == DEFAULT_GROUP_WEIGHT
    assert e.priority == 100


def test_repeated_activation_scans_resolve_identically():
    # Determinism proof at the pipeline seam: the same book + the
    # same hits, run 25 times from fresh state, produce identical
    # activations, losers and suppressed rows every time.
    def run():
        entries = [
            ae("a", inclusion_group="weather", group_weight=75, priority=300),
            ae("b", inclusion_group="weather", group_weight=75, priority=300),
            ae("c", inclusion_group="weather", group_weight=10, priority=999),
            ae("d", constant=True),
        ]
        r = activate(entries, {"a", "b", "c"}, {})
        return (
            [(a.entry_id, a.via, a.content) for a in r.activations],
            list(r.group_losers),
            [(a.entry_id, a.via) for a in r.group_suppressed],
        )

    first = run()
    assert [a[0] for a in first[0]] == ["a", "d"]  # id tie-break: a beats b
    for _ in range(25):
        assert run() == first


# ------------------------------------------------------------------- preview


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


def grouped_rows():
    return [
        FakeRow("a", "gale", "gale lore", inclusion_group="weather", group_weight=75, priority=300),
        FakeRow("b", "gale", "storm lore", inclusion_group="weather", group_weight=100, priority=100),
        FakeRow("c", "calm", "calm lore"),
    ]


def test_preview_group_loser_is_group_excluded_not_discarded():
    out = preview_activation(grouped_rows(), ["a gale and calm"], 1, None)
    rows = {r["entry_id"]: r for r in out["entries"]}
    assert rows["b"]["status"] == "included"
    assert rows["c"]["status"] == "included"
    loser = rows["a"]
    assert loser["status"] == "group_excluded"
    assert loser["discard_reason"] is None
    assert loser["group_winner_id"] == "b"
    assert loser["via"] == "key"
    assert loser["inclusion_group"] == "weather" and loser["group_weight"] == 75
    assert loser["content"] is None and loser["tokens"] is None
    assert out["inclusion_group_winners"] == {"weather": "b"}
    # the excluded entry's content never reaches the budget totals
    assert out["tokens_used"] == sum(
        r["tokens"] for r in out["entries"] if r["status"] == "included"
    )


def test_preview_without_groups_has_no_winners_key_and_rows_carry_defaults():
    rows = [FakeRow("a", "gale", "gale lore")]
    out = preview_activation(rows, ["gale"], 1, None)
    assert "inclusion_group_winners" not in out
    row = out["entries"][0]
    assert row["status"] == "included"
    assert row["inclusion_group"] == "" and row["group_weight"] == 100
    assert row["group_winner_id"] is None


def test_preview_repeated_scans_over_same_book_and_chat_are_identical():
    # The determinism proof the roadmap line demands, at the full
    # scan -> activation -> group -> budget pipeline: 25 repeats
    # over the same book + chat produce byte-identical previews.
    first = preview_activation(grouped_rows(), ["a gale and calm"], 1, None)
    for _ in range(25):
        again = preview_activation(grouped_rows(), ["a gale and calm"], 1, None)
        assert again == first
        assert json.dumps(again, sort_keys=True) == json.dumps(first, sort_keys=True)


def test_preview_group_resolution_composes_with_recursive_scan():
    rows = [
        FakeRow("a", "alpha", "alpha lore names beta", inclusion_group="g", group_weight=10),
        FakeRow("b", "beta", "beta lore", inclusion_group="g", group_weight=20),
    ]
    out = preview_activation(rows, ["alpha rises"], 1, None, recursive_scan=True)
    by_id = {r["entry_id"]: r for r in out["entries"]}
    assert by_id["b"]["status"] == "included" and by_id["b"]["via"] == "recursive"
    assert by_id["a"]["status"] == "group_excluded" and by_id["a"]["group_winner_id"] == "b"


# --------------------------------------------------------- service + the API


async def _book_with_entries(factory, user_id):
    async with factory() as session:
        book = await service.create_lorebook(session, user_id, "Groups")
        return book.id


async def test_service_create_update_round_trip(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await _book_with_entries(factory, user_id)
    async with factory() as session:
        entry = await service.create_entry(
            session, user_id, book_id, name="Gale", keys=["gale"],
            inclusion_group="  weather ", group_weight=75, priority=300,
        )
        assert entry.inclusion_group == "weather" and entry.group_weight == 75
        d = entry_to_dict(entry)
        assert d["inclusion_group"] == "weather" and d["group_weight"] == 75
        updated = await service.update_entry(
            session, user_id, book_id, entry.id, group_weight=0, inclusion_group=""
        )
        assert updated.group_weight == 0 and updated.inclusion_group == ""


async def test_service_defaults_are_pre_p034_behaviour(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await _book_with_entries(factory, user_id)
    async with factory() as session:
        entry = await service.create_entry(session, user_id, book_id, name="Plain")
        assert entry.inclusion_group == "" and entry.group_weight == 100


async def test_service_rejects_bad_group_values(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id = await _book_with_entries(factory, user_id)
    async with factory() as session:
        with pytest.raises(ValueError):
            await service.create_entry(session, user_id, book_id, group_weight=-1)
        with pytest.raises(ValueError):
            await service.create_entry(session, user_id, book_id, inclusion_group=7)
        entry = await service.create_entry(session, user_id, book_id, name="E")
        with pytest.raises(ValueError):
            await service.update_entry(session, user_id, book_id, entry.id, group_weight=True)


def test_api_create_entry_with_group_and_bad_weight_422(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book = client.post("/api/v1/lorebooks", json={"name": "B"}).json()
    ok = client.post(
        f"/api/v1/lorebooks/{book['id']}/entries",
        json={"name": "Gale", "keys": ["gale"], "inclusion_group": "weather", "group_weight": 75},
    )
    assert ok.status_code == 201
    body = ok.json()
    assert body["inclusion_group"] == "weather" and body["group_weight"] == 75
    bad = client.post(
        f"/api/v1/lorebooks/{book['id']}/entries", json={"name": "Bad", "group_weight": -5}
    )
    assert bad.status_code == 422
    bad2 = client.patch(
        f"/api/v1/lorebooks/{book['id']}/entries/{body['id']}", json={"group_weight": -1}
    )
    assert bad2.status_code == 422
    patched = client.patch(
        f"/api/v1/lorebooks/{book['id']}/entries/{body['id']}", json={"inclusion_group": "tide"}
    )
    assert patched.status_code == 200 and patched.json()["inclusion_group"] == "tide"


def test_api_preview_reports_group_exclusion(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book = client.post("/api/v1/lorebooks", json={"name": "B"}).json()
    for name, weight in (("Weak", 10), ("Strong", 90)):
        r = client.post(
            f"/api/v1/lorebooks/{book['id']}/entries",
            json={"name": name, "keys": ["gale"], "content": f"{name} lore",
                  "inclusion_group": "weather", "group_weight": weight},
        )
        assert r.status_code == 201
    out = client.post(
        f"/api/v1/lorebooks/{book['id']}/preview", json={"messages": ["the gale rises"]}
    ).json()
    rows = {r["name"]: r for r in out["entries"]}
    assert rows["Strong"]["status"] == "included"
    assert rows["Weak"]["status"] == "group_excluded"
    assert rows["Weak"]["group_winner_id"] == rows["Strong"]["entry_id"]
    assert out["inclusion_group_winners"] == {"weather": rows["Strong"]["entry_id"]}


# ----------------------------------------------------------------- migration


def test_migration_head_is_0029_p037():
    # 0025 was reserved for P-033 and P-033 took it, banking first;
    # head moved 0026 -> 0028 by P-036 (0027 is P-035's reserved
    # number, banked first), then -> 0029 by P-037. 0026 stands.
    assert MIGRATIONS[-1][0] == "0036"  # head moved by P-065 (PROVISIONAL 0036)
    assert MIGRATIONS[-7][0] == "0030"  # position moved by P-065 (PROVISIONAL 0036)
    assert MIGRATIONS[-8][0] == "0029"  # position moved by P-065 (PROVISIONAL 0036)
    assert MIGRATIONS[-9][0] == "0028"  # position moved by P-065 (PROVISIONAL 0036)
    assert MIGRATIONS[-10][0] == "0027"  # position moved by P-065 (PROVISIONAL 0036)
    assert MIGRATIONS[-11][0] == "0026"  # position moved by P-065 (PROVISIONAL 0036)
def test_migration_head_is_0030_provisional_p038():
    # number, banked first), then -> 0030 by P-038 (0029 is
    # P-037's reserved number, banking first). 0026 stands.
    assert MIGRATIONS[-1][0] == "0036"  # head moved by P-065 (PROVISIONAL 0036)
    assert MIGRATIONS[-12][0] == "0025"  # position moved by P-065 (PROVISIONAL 0036)


def test_migration_0026_columns_exist_and_default(tmp_path):
    import sqlite3

    db_path = tmp_path / "m.db"
    migrate_to_head(db_path)
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1]: row for row in conn.execute("PRAGMA table_info(lore_entries)")}
        assert "inclusion_group" in cols and "group_weight" in cols
        conn.execute(
            "INSERT INTO lore_entries (id, lorebook_id, user_id, name, created_at) VALUES ('e1', 'b', 'u', 'Raw', '2026-01-01T00:00:00')"
        )
        row = conn.execute(
            "SELECT inclusion_group, group_weight FROM lore_entries WHERE id = 'e1'"
        ).fetchone()
        assert row == ("", 100)  # raw rows default to pre-P-034 behaviour
    finally:
        conn.close()


def test_old_database_upgrades_in_place_preserving_entries(tmp_path):
    # A pre-P-034 database (migrated only to 0024) keeps its entries
    # through the 0026 upgrade: they read back ungrouped, weight 100.
    import sqlite3

    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE schema_migrations (revision TEXT PRIMARY KEY, applied_at TEXT NOT NULL)"
        )
        for revision, _desc, module in MIGRATIONS:
            if revision > "0024":
                continue
            module.upgrade(conn)
            conn.execute(
                "INSERT INTO schema_migrations (revision, applied_at) VALUES (?, '2026-01-01T00:00:00')",
                (revision,),
            )
        conn.commit()
    finally:
        conn.close()
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO lore_entries (id, lorebook_id, user_id, name, priority, created_at) VALUES ('old1', 'b', 'u', 'Old', 42, '2026-01-01T00:00:00')"
        )
        conn.commit()
    finally:
        conn.close()
    applied = migrate_to_head(db_path)
    assert applied == ["0025", "0026", "0027", "0028", "0029", "0030", "0031", "0032", "0033", "0034", "0035", "0036"]  # PROVISIONAL 0036 appended by P-065
    conn = sqlite3.connect(db_path)
    try:
        row = conn.execute(
            "SELECT inclusion_group, group_weight, priority FROM lore_entries WHERE id = 'old1'"
        ).fetchone()
        assert row == ("", 100, 42)
    finally:
        conn.close()


# ------------------------------------------------------------ interop + files


def test_worldinfo_fixture_group_fields_are_first_class():
    book = parse_lorebook_file((CORPUS / "lorebook_worldinfo_full.json").read_bytes())
    gale = book.entries[0]
    assert gale.inclusion_group == "weather" and gale.group_weight == 75
    assert "group" not in gale.extra and "groupWeight" not in gale.extra
    # neighbours stay preserved-as-data, uninterpreted
    assert gale.extra["groupOverride"] is False
    assert gale.extra["useGroupScoring"] is True
    other = book.entries[1]
    assert other.inclusion_group == "" and other.group_weight == 100


def test_worldinfo_export_fixed_point_still_holds():
    raw = json.loads((CORPUS / "lorebook_worldinfo_full.json").read_text(encoding="utf-8"))
    book = parse_lorebook_file((CORPUS / "lorebook_worldinfo_full.json").read_bytes())
    assert export_worldinfo(book) == raw


def test_worldinfo_group_weight_tolerant_coercions():
    data = {
        "name": "Tolerant",
        "entries": {
            "0": {"comment": "A", "content": "a", "key": ["a"], "group": " g ", "groupWeight": "75"},
            "1": {"comment": "B", "content": "b", "key": ["b"], "groupWeight": None},
            "2": {"comment": "C", "content": "c", "key": ["c"], "groupWeight": -9},
            "3": {"comment": "D", "content": "d", "key": ["d"], "group": 7},
        },
    }
    book = parse_lorebook_file(data)
    a, b, c, d = book.entries
    assert (a.inclusion_group, a.group_weight) == ("g", 75)
    assert b.group_weight == 100
    assert c.group_weight == 100  # negative falls back, never crashes
    assert d.inclusion_group == ""  # non-string group means ungrouped


def test_worldinfo_export_no_fabrication_from_native_dicts():
    book = {"name": "N", "description": "", "scan_depth": 4, "token_budget": None}
    plain = {
        "name": "Plain", "content": "p", "keys": ["p"], "secondary_keys": [],
        "priority": 100, "position": "before_char", "enabled": True,
        "constant": False, "case_sensitive": False, "whole_word": True,
        "sticky_prompts": 0, "cooldown_prompts": 0, "delay_prompts": 0,
    }
    out = worldinfo_from_native(book, [plain])
    entry = out["entries"]["0"]
    assert "group" not in entry and "groupWeight" not in entry
    grouped = dict(plain, inclusion_group="weather", group_weight=75)
    out = worldinfo_from_native(book, [grouped])
    entry = out["entries"]["0"]
    assert entry["group"] == "weather" and entry["groupWeight"] == 75
    default_weight = dict(plain, inclusion_group="weather")
    out = worldinfo_from_native(book, [default_weight])
    entry = out["entries"]["0"]
    assert entry["group"] == "weather" and "groupWeight" not in entry


def test_native_file_round_trip_carries_group_fields():
    data = {
        "format": "runmal-lorebook", "version": 1, "name": "Native",
        "description": "", "scan_depth": 4, "token_budget": None,
        "entries": [
            {"name": "Gale", "content": "g", "keys": ["gale"], "secondary_keys": [],
             "inclusion_group": "weather", "group_weight": 75, "priority": 300,
             "position": "before_char", "enabled": True, "constant": False,
             "case_sensitive": False, "whole_word": True, "sticky_prompts": 0,
             "cooldown_prompts": 0, "delay_prompts": 0},
        ],
    }
    book = parse_lorebook_file(data)
    entry = book.entries[0]
    assert entry.inclusion_group == "weather" and entry.group_weight == 75
    assert entry.native_fields()["inclusion_group"] == "weather"
    from runmal.lorebooks.interop import export_native

    again = export_native(book)
    assert again["entries"][0]["inclusion_group"] == "weather"
    assert again["entries"][0]["group_weight"] == 75


def test_transfer_parse_import_maps_group_fields_both_shapes():
    wi = {
        "name": "WI",
        "entries": {"0": {"comment": "Gale", "content": "g", "key": ["gale"],
                          "group": "weather", "groupWeight": 75, "order": 300}},
    }
    _book, entries = transfer.parse_import(wi)
    assert entries[0]["inclusion_group"] == "weather"
    assert entries[0]["group_weight"] == 75
    native = {
        "name": "N",
        "entries": [{"name": "Gale", "content": "g", "keys": ["gale"],
                     "inclusion_group": "weather", "group_weight": 75}],
    }
    _book, entries = transfer.parse_import(native)
    assert entries[0]["inclusion_group"] == "weather"
    assert entries[0]["group_weight"] == 75


def test_transfer_export_book_emits_group_fields():
    book = {"name": "B", "description": "", "scan_depth": 4, "token_budget": None}
    entry = {
        "name": "Gale", "content": "g", "keys": ["gale"], "secondary_keys": [],
        "selective_logic": "and_any", "inclusion_group": "weather", "group_weight": 75,
        "priority": 300, "position": "before_char", "enabled": True, "constant": False,
        "case_sensitive": False, "whole_word": True, "sticky_prompts": 0,
        "cooldown_prompts": 0, "delay_prompts": 0,
    }
    out = transfer.export_book(book, [entry])
    assert out["entries"][0]["inclusion_group"] == "weather"
    assert out["entries"][0]["group_weight"] == 75


async def test_import_book_transactional_stores_group_fields(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    data = {
        "name": "WI",
        "entries": {"0": {"comment": "Gale", "content": "g", "key": ["gale"],
                          "group": "weather", "groupWeight": 75, "order": 300}},
    }
    async with factory() as session:
        book = await transfer.import_book_transactional(session, user_id, data)
        entries = await service.list_entries(session, user_id, book.id)
    assert entries is not None and len(entries) == 1
    assert entries[0].inclusion_group == "weather" and entries[0].group_weight == 75
    assert entry_to_dict(entries[0])["group_weight"] == 75
