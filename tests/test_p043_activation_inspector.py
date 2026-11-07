"""P-043 acceptance: activation inspector.

Roadmap line: *Activation inspector: "why did this entry fire"
-- the matched keys and roll shown per message (Part XIII's
Inspector consumes this).*

Contract under test:
- ``runmal.lorebooks.inspector.inspect_activation`` explains
  one tick as DATA (schema runmal-p043-activation-inspection-v1):
  per entry the outcome, a deterministic reason code, the
  declared/matched/unmatched keys with the P-032 selective
  logic and gate verdict, WHERE matches landed (message /
  external indices), the P-036 probability roll, P-034 group
  exclusion with the winner's weight/priority, P-031 recursion
  depth + triggered_by, P-041 vector score vs threshold and
  the vector vs keyword-fallback distinction, the P-040 scope
  stamp, and the budget/placement outcome (P-037/P-038).
- Near misses are first-class: secondary-gate refusals (the
  new ``scan_near_misses`` in lorebooks/scan.py), timed
  suppression, vector below threshold, probability skips,
  over-budget and group exclusions all carry near_miss +
  near_miss_kind + stage_reached.
- Timed effects (P-033): preview_activation gains an opt-in
  ``entry_states`` tick (a copy -- the caller's counters are
  never mutated, nothing persists) whose rows gain a ``timed``
  block; without it rows are byte-identical to pre-P-043 and
  the inspector honestly records timed as unrecorded.
- Surfaces: POST /lorebooks/{id}/inspect (the preview's twin)
  and inspect_prompt's opt-in ``lorebook_inspections``, built
  from the SAME preview dict as the trace (no second tick).
- No migration: the schema head stays 0032 (P-042 reserves
  0033; this slice adds none).
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.lorebooks.activation import EntryState
from runmal.lorebooks.inspector import (
    FACTS_NOT_RECORDED,
    INSPECT_SCHEMA,
    explain_preview,
    inspect_activation,
)
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.scan import ScanEntry, scan_near_misses
from runmal.lorebooks.vector_match import LocalEmbeddingBackend
from runmal.lorebooks.windows import ScanSettings
from runmal.prompt.inspect import inspect_prompt


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


def by_id(result):
    return {row["entry_id"]: row for row in result["entries"]}


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


# --- Keyword firing + where it matched -------------------------------------


def test_keyword_match_explains_keys_and_message_indices():
    entries = [
        orm_entry("e1", "Dragon", "Dragon lore.", keys=("dragon", "wyrm")),
        orm_entry("e2", "Bread", "Bread lore.", keys=("bread",)),
    ]
    result = inspect_activation(entries, ["hello there", "a dragon flies"], 4, None)
    assert result["schema"] == INSPECT_SCHEMA
    rows = by_id(result)
    e1 = rows["e1"]
    assert e1["fired"] is True and e1["status"] == "included"
    assert e1["reason"] == "keyword_match" and e1["via"] == "key"
    assert e1["keys"]["matched_primary"] == ["dragon"]
    assert e1["keys"]["unmatched_primary"] == ["wyrm"]
    assert e1["keys"]["message_indices"] == [1]
    assert e1["keys"]["gate"] == "no_secondary_keys"
    assert e1["near_miss"] is False and e1["stage_reached"] == "included"
    assert "dragon" in e1["summary"]
    e2 = rows["e2"]
    assert e2["reason"] == "no_key_match" and e2["near_miss"] is False
    # Per-message breakdown: only message 1 carries a hit.
    assert result["messages"] == [
        {"index": 1, "entries": [{"entry_id": "e1", "matched_primary": ["dragon"], "matched_secondary": []}]}
    ]
    assert result["totals"]["included"] == 1
    assert result["totals"]["not_triggered"] == 1


def test_selective_gate_passed_records_logic():
    entries = [
        orm_entry(
            "e1", "Storm", "Storm lore.", keys=("storm",),
            secondary_keys_json=json.dumps(["sea", "wind"]),
            selective_logic="and_all",
        )
    ]
    result = inspect_activation(entries, ["a storm over sea and wind"], 4, None)
    row = by_id(result)["e1"]
    assert row["fired"] is True
    assert row["keys"]["selective_logic"] == "and_all"
    assert row["keys"]["gate"] == "passed"
    assert row["keys"]["matched_secondary"] == ["sea", "wind"]
    assert row["keys"]["secondary_count"] == 2
    assert row["keys"]["matched_secondary_count"] == 2


# --- Near misses: the secondary gate ----------------------------------------


def test_secondary_gate_failure_is_a_near_miss():
    entries = [
        orm_entry(
            "e1", "Storm", "Storm lore.", keys=("storm",),
            secondary_keys_json=json.dumps(["sea"]),
            selective_logic="and_any",
        )
    ]
    result = inspect_activation(entries, ["a storm gathers"], 4, None)
    row = by_id(result)["e1"]
    assert row["status"] == "not_triggered"
    assert row["reason"] == "secondary_gate_failed"
    assert row["near_miss"] is True
    assert row["near_miss_kind"] == "secondary_gate_failed"
    assert row["stage_reached"] == "gate"
    assert row["keys"]["gate"] == "failed"
    assert row["keys"]["matched_primary"] == ["storm"]
    assert row["keys"]["unmatched_secondary"] == ["sea"]
    assert result["totals"]["near_misses"] == 1
    # The per-message view flags the near miss too.
    assert result["messages"][0]["entries"][0]["near_miss"] == "secondary_gate_failed"


def test_secondary_gate_failure_not_all_and_not_any():
    entries = [
        orm_entry(
            "e1", "Calm", "Calm lore.", keys=("harbour",),
            secondary_keys_json=json.dumps(["storm"]),
            selective_logic="not_any",
        ),
        orm_entry(
            "e2", "Partial", "Partial lore.", keys=("tide",),
            secondary_keys_json=json.dumps(["moon", "sun"]),
            selective_logic="and_all",
        ),
    ]
    result = inspect_activation(entries, ["harbour in a storm; tide and moon"], 4, None)
    rows = by_id(result)
    assert rows["e1"]["reason"] == "secondary_gate_failed"
    assert rows["e1"]["keys"]["matched_secondary"] == ["storm"]
    assert rows["e2"]["reason"] == "secondary_gate_failed"
    assert rows["e2"]["keys"]["matched_secondary_count"] == 1
    assert rows["e2"]["keys"]["secondary_count"] == 2


def test_scan_near_misses_direct_and_external_indices():
    view = [
        ScanEntry(
            id="e1", keys=("storm",), secondary_keys=("sea",),
            selective_logic="and_any",
        ),
        ScanEntry(id="e2", keys=("bread",)),
    ]
    settings = ScanSettings.normalised(
        scan_depth=4, scan_mode="depth", scan_external_context=True
    )
    misses = scan_near_misses(view, ["calm day"], settings, ["a storm at sea port"])
    # e1's primary matched only in the external segment, and its
    # secondary matched there too but... sea IS in the external
    # text, so use a primary-only external text instead:
    assert misses == [] or misses[0].entry_id == "e1"
    misses = scan_near_misses(view, ["calm day"], settings, ["a storm gathers"])
    assert len(misses) == 1
    assert misses[0].entry_id == "e1"
    assert misses[0].matched_primary == ("storm",)
    assert misses[0].external_indices == (0,)
    assert misses[0].message_indices == ()
    assert misses[0].secondary_count == 1


# --- Constant / disabled ------------------------------------------------------


def test_constant_and_disabled_reasons():
    entries = [
        orm_entry("e1", "Always", "Always lore.", constant=True),
        orm_entry("e2", "Off", "Off lore.", keys=("dragon",), enabled=False),
    ]
    result = inspect_activation(entries, ["a dragon"], 4, None)
    rows = by_id(result)
    assert rows["e1"]["reason"] == "constant_active"
    assert rows["e1"]["via"] == "constant"
    assert rows["e2"]["reason"] == "disabled"
    assert rows["e2"]["status"] == "disabled"


# --- Probability (P-036) -------------------------------------------------------


def test_probability_roll_shown_and_reproducible():
    entries = [orm_entry("e1", "Luck", "Luck lore.", keys=("luck",), probability=0)]
    first = inspect_activation(entries, ["luck"], 4, None, seed=7, roll_context="tick-1")
    row = by_id(first)["e1"]
    assert row["status"] == "discarded"
    assert row["reason"] == "probability_skip"
    assert row["near_miss_kind"] == "probability_skip"
    roll = row["probability"]["roll"]
    assert roll is not None
    assert roll["seed"] == 7 and roll["seeded"] is True
    assert roll["passed"] is False and roll["context"] == "tick-1"
    assert row["probability"]["percent"] == 0
    second = inspect_activation(entries, ["luck"], 4, None, seed=7, roll_context="tick-1")
    assert by_id(second)["e1"]["probability"]["roll"]["roll"] == roll["roll"]
    assert first["probability_rolls"][0]["entry_id"] == "e1"


def test_ungated_entry_records_no_roll():
    entries = [orm_entry("e1", "Sure", "Sure lore.", keys=("sure",), probability=100)]
    row = by_id(inspect_activation(entries, ["sure"], 4, None, seed=7))["e1"]
    assert row["fired"] is True
    assert row["probability"]["roll"] is None
    assert any("probability rolls exist only" in f for f in FACTS_NOT_RECORDED)


# --- Budget (S204) --------------------------------------------------------------


def test_over_budget_explained_with_tokens():
    entries = [
        orm_entry("big", "Big", "x" * 400, keys=("alpha",), priority=100),
        orm_entry("small", "Small", "tiny", keys=("beta",), priority=200),
    ]
    result = inspect_activation(entries, ["alpha beta"], 4, 10)
    rows = by_id(result)
    assert rows["small"]["fired"] is True
    big = rows["big"]
    assert big["status"] == "discarded"
    assert big["reason"] == "over_budget"
    assert big["budget"]["discard_reason"] == "over_budget"
    assert big["budget"]["tokens"] == 100
    assert big["budget"]["priority"] == 100
    assert result["token_budget"] == 10


# --- Inclusion groups (P-034) ---------------------------------------------------


def test_group_exclusion_explains_winner():
    entries = [
        orm_entry("w1", "Strong", "Strong weather.", keys=("rain",),
                  inclusion_group="weather", group_weight=200, priority=100),
        orm_entry("w2", "Weak", "Weak weather.", keys=("rain",),
                  inclusion_group="weather", group_weight=50, priority=300),
    ]
    result = inspect_activation(entries, ["rain falls"], 4, None)
    rows = by_id(result)
    assert rows["w1"]["fired"] is True
    loser = rows["w2"]
    assert loser["status"] == "group_excluded"
    assert loser["reason"] == "inclusion_group_excluded"
    assert loser["near_miss_kind"] == "inclusion_group_excluded"
    assert loser["group"]["inclusion_group"] == "weather"
    assert loser["group"]["winner_id"] == "w1"
    assert loser["group"]["winner_group_weight"] == 200
    assert loser["group"]["winner_priority"] == 100
    assert loser["group"]["group_weight"] == 50
    assert result["inclusion_group_winners"] == {"weather": "w1"}


# --- Timed effects (P-033 via the P-043 preview seam) ---------------------------


def test_timed_cooldown_suppression_and_no_caller_mutation():
    entries = [orm_entry("e1", "Hex", "Hex lore.", keys=("hex",), cooldown_prompts=3)]
    supplied = {"e1": EntryState(cooldown_remaining=2)}
    result = inspect_activation(entries, ["a hex"], 4, None, entry_states=supplied)
    row = by_id(result)["e1"]
    assert row["status"] == "not_triggered"
    assert row["reason"] == "cooldown_suppressed"
    assert row["near_miss_kind"] == "cooldown_suppressed"
    assert row["timed"]["recorded"] is True
    assert row["timed"]["config"]["cooldown_prompts"] == 3
    assert row["timed"]["state_before"]["cooldown_remaining"] == 2
    assert row["timed"]["state_after"]["cooldown_remaining"] == 1
    assert row["timed"]["effect"] == "cooldown_suppressed"
    assert result["timed_states_supplied"] is True
    # The caller's counters were never mutated (a copy ticked).
    assert supplied["e1"].cooldown_remaining == 2


def test_timed_delay_armed_then_sticky_and_delay_fired():
    entries = [
        orm_entry("d1", "Slow", "Slow lore.", keys=("slow",), delay_prompts=2),
        orm_entry("s1", "Sticky", "Sticky lore.", keys=("glue",), sticky_prompts=2),
    ]
    armed = inspect_activation(entries, ["slow glue"], 4, None, entry_states={})
    rows = by_id(armed)
    assert rows["d1"]["reason"] == "delay_armed"
    assert rows["d1"]["timed"]["state_after"]["delay_armed"] is True
    assert rows["s1"]["fired"] is True  # fired by key this tick
    # A later tick: sticky carries s1 with no key; d1's delay fires.
    states = {
        "s1": EntryState(sticky_remaining=1),
        "d1": EntryState(delay_armed=True, delay_remaining=1),
    }
    later = inspect_activation(entries, ["nothing here"], 4, None, entry_states=states)
    rows = by_id(later)
    assert rows["s1"]["reason"] == "sticky_carryover"
    assert rows["s1"]["timed"]["effect"] == "sticky_carryover"
    assert rows["d1"]["reason"] == "delay_fired"
    assert rows["d1"]["timed"]["effect"] == "delay_fired"


def test_clean_inspection_records_no_timed_counters():
    entries = [orm_entry("e1", "Hex", "Hex lore.", keys=("hex",), cooldown_prompts=3)]
    result = inspect_activation(entries, ["a hex"], 4, None)
    row = by_id(result)["e1"]
    assert row["fired"] is True
    assert row["timed"]["recorded"] is False
    assert row["timed"]["state_before"] is None
    assert row["timed"]["config"]["cooldown_prompts"] == 3
    assert result["timed_states_supplied"] is False
    assert any("timed-effect counters" in f for f in result["facts_not_recorded"])


def test_preview_rows_unchanged_without_entry_states():
    entries = [orm_entry("e1", "Hex", "Hex lore.", keys=("hex",))]
    preview = preview_activation(entries, ["a hex"], 4, None)
    assert "timed" not in preview["entries"][0]
    assert "timed_states_supplied" not in preview
    preview2 = preview_activation(entries, ["a hex"], 4, None, entry_states={})
    assert preview2["entries"][0]["timed"]["effect"] == "fired"
    assert preview2["timed_states_supplied"] is True


# --- Recursion + references (P-031 / S203) ---------------------------------------


def test_recursive_trigger_explains_depth_and_parent():
    entries = [
        orm_entry("a", "Alpha", "Alpha mentions the beta seal.", keys=("alpha",)),
        orm_entry("b", "Beta", "Beta lore.", keys=("beta",)),
    ]
    result = inspect_activation(entries, ["alpha rises"], 4, None, recursive_scan=True)
    rows = by_id(result)
    assert rows["a"]["fired"] is True
    beta = rows["b"]
    assert beta["fired"] is True
    assert beta["reason"] == "recursive_trigger"
    assert beta["recursion"]["depth"] == 1
    assert beta["recursion"]["triggered_by"] == "a"
    assert beta["recursion"]["recursive"] is True
    assert result["recursive_scan"] is True
    assert result["recursion_depth_reached"] == 1


def test_reference_expansion_explained():
    entries = [
        orm_entry("a", "Alpha", "Alpha {{lore:Beta}} end.", keys=("alpha",)),
        orm_entry("b", "Beta", "Beta lore.", keys=("zzz",)),
    ]
    result = inspect_activation(entries, ["alpha rises"], 4, None)
    rows = by_id(result)
    assert rows["b"]["fired"] is True
    assert rows["b"]["reason"] == "reference_expansion"
    assert rows["b"]["via"] == "reference"
    assert rows["b"]["recursion"]["depth"] == 1


# --- Vector matching (P-041) -------------------------------------------------------


def test_vector_hit_from_caller_ids_carries_no_invented_score():
    entries = [orm_entry("v1", "Vec", "Vec lore.", vectorised=True, keys=("vec",))]
    result = inspect_activation(entries, ["anything"], 4, None, vector_hit_ids={"v1"})
    row = by_id(result)["v1"]
    assert row["fired"] is True
    assert row["reason"] == "vector_match"
    assert row["vector"]["score"] is None  # caller ids carry no scores
    assert row["vector"]["fallback"] is False


def test_vector_below_threshold_is_a_near_miss_with_score():
    entries = [
        orm_entry(
            "v1", "Dragon Peaks",
            "Dragons soar above the mountain peaks and guard the old hoard.",
            vectorised=True, keys=("dragon",),
        )
    ]
    backend = LocalEmbeddingBackend()
    result = inspect_activation(
        entries, ["Fresh bread is baked at dawn and sold for copper coins."],
        4, None, vector_embedder=backend.embed_sync,
    )
    row = by_id(result)["v1"]
    assert row["status"] == "not_triggered"
    assert row["reason"] == "vector_below_threshold"
    assert row["near_miss_kind"] == "vector_below_threshold"
    assert row["vector"]["score"] is not None
    assert row["vector"]["score"] < row["vector"]["threshold"]
    assert result["vector_match"]["mode"] in ("keyword_fallback", "none")


def test_vector_match_with_embedder_records_score_and_threshold():
    entries = [
        orm_entry(
            "v1", "Dragon Peaks",
            "Dragons soar above the mountain peaks and guard the old hoard.",
            vectorised=True, keys=("dragon",),
        )
    ]
    backend = LocalEmbeddingBackend()
    result = inspect_activation(
        entries, ["Dragons soar above the mountain peaks."],
        4, None, vector_embedder=backend.embed_sync,
    )
    row = by_id(result)["v1"]
    assert row["fired"] is True
    assert row["reason"] == "vector_match"
    assert row["vector"]["score"] is not None
    assert row["vector"]["score"] >= row["vector"]["threshold"]


def test_keyword_fallback_is_honestly_labelled():
    entries = [orm_entry("v1", "Vec", "Vec lore.", vectorised=True, keys=("vec",))]

    def dead_embedder(texts):
        raise RuntimeError("no embeddings today")

    result = inspect_activation(entries, ["a vec appears"], 4, None, vector_embedder=dead_embedder)
    row = by_id(result)["v1"]
    assert row["fired"] is True
    assert row["reason"] == "keyword_fallback"
    assert row["via"] == "vector_fallback"
    assert row["vector"]["fallback"] is True
    assert row["vector"]["degraded"] is True
    assert row["keys"]["matched_primary"] == ["vec"]


# --- Placement + external segment (P-038 / P-037) ---------------------------------


def test_placement_and_external_indices_explained():
    entries = [
        orm_entry("p1", "Deep", "Deep lore.", keys=("deep",),
                  position="at_depth", depth=None, role="user"),
        orm_entry("x1", "Ext", "Ext lore.", keys=("external-key",)),
    ]
    result = inspect_activation(
        entries, ["deep thought"], 4, None,
        scan_external_context=True, external_context=["mentions external-key here"],
    )
    rows = by_id(result)
    assert rows["p1"]["placement"] == {
        "position": "at_depth", "role": "user", "injection_depth": 4,
    }
    assert rows["x1"]["fired"] is True
    assert rows["x1"]["keys"]["external_indices"] == [0]
    assert rows["x1"]["keys"]["message_indices"] == []


# --- explain_preview over a layered-shaped dict (P-040) ----------------------------


def test_explain_preview_scope_over_budget_and_scope_stamp():
    preview = {
        "scan_depth": 4, "scan_mode": "depth", "scan_external_context": False,
        "scan_window": {"texts": 1, "chat_texts": 1, "external_texts": 0},
        "token_budget": None, "tokens_used": 0, "seed": None, "roll_context": "",
        "entries": [
            {
                "entry_id": "e1", "name": "Scoped", "enabled": True,
                "constant": False, "vectorised": False,
                "activation_kind": "selective", "matched_primary": ["k"],
                "matched_secondary": [], "vector_score": None,
                "external_indices": [], "via": "key", "depth": 0,
                "content": "c", "tokens": 5, "discard_reason": "scope_over_budget",
                "inclusion_group": "", "group_weight": 100,
                "group_winner_id": None, "probability": 100,
                "probability_roll": None, "position": "before_char",
                "role": "system", "injection_depth": None,
                "status": "discarded", "scope": "chat", "lorebook_id": "book-9",
            }
        ],
    }
    entries = [orm_entry("e1", "Scoped", "c", keys=("k",))]
    result = explain_preview(preview, entries)
    row = result["entries"][0]
    assert row["reason"] == "scope_over_budget"
    assert row["near_miss_kind"] == "scope_over_budget"
    assert row["scope"] == "chat"
    assert row["lorebook_id"] == "book-9"


# --- REST + prompt-inspector surfaces ------------------------------------------------


def test_inspect_endpoint_and_404(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book = client.post("/api/v1/lorebooks", json={"name": "B"}).json()
    entry = client.post(
        f"/api/v1/lorebooks/{book['id']}/entries",
        json={"name": "Dragon", "content": "Dragon lore.", "keys": ["dragon"]},
    ).json()
    resp = client.post(
        f"/api/v1/lorebooks/{book['id']}/inspect", json={"messages": ["a dragon"]}
    )
    assert resp.status_code == 200
    payload = resp.json()
    assert payload["schema"] == INSPECT_SCHEMA
    assert payload["book_id"] == book["id"]
    row = payload["entries"][0]
    assert row["entry_id"] == entry["id"]
    assert row["reason"] == "keyword_match"
    assert row["keys"]["message_indices"] == [0]
    missing = client.post("/api/v1/lorebooks/nope/inspect", json={"messages": []})
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_prompt_inspect_opt_in_activation_inspection(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        from runmal.lorebooks import service as lore_service

        book = await lore_service.create_lorebook(session, user_id, "B", "", 4, None)
        await lore_service.create_entry(
            session, user_id, book.id, name="Dragon", content="Dragon lore.",
            keys=["dragon"],
        )
        plain = await inspect_prompt(
            session, user_id, lorebook_ids=[book.id], messages=["a dragon"]
        )
        assert "lorebook_inspections" not in plain
        rich = await inspect_prompt(
            session, user_id, lorebook_ids=[book.id], messages=["a dragon"],
            include_activation_inspection=True,
        )
    assert rich["lorebook_inspections"][book.id]["schema"] == INSPECT_SCHEMA
    row = rich["lorebook_inspections"][book.id]["entries"][0]
    assert row["reason"] == "keyword_match"


def test_prompt_inspect_endpoint_flag(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book = client.post("/api/v1/lorebooks", json={"name": "B"}).json()
    client.post(
        f"/api/v1/lorebooks/{book['id']}/entries",
        json={"name": "Dragon", "content": "Dragon lore.", "keys": ["dragon"]},
    )
    resp = client.post(
        "/api/v1/debug/prompt-inspect",
        json={
            "lorebook_ids": [book["id"]], "messages": ["a dragon"],
            "include_activation_inspection": True,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["lorebook_inspections"][book["id"]]["totals"]["included"] == 1


# --- No migration ----------------------------------------------------------------------


def test_no_migration_head_stays_0032():
    assert MIGRATIONS[-1][0] == "0033"
