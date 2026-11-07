"""P-058 token budget governor battery.

Pure governor tests (section mapping, whole-prompt budget,
trace reconciliation, strict policy validation, deterministic
trimming) plus inspect-API tests (budget always present, an
explicit policy trims history, bad policy -> 422, the default
policy endpoint, and P-044 lore_account reconciliation intact).
No content ever enters a budget/governor payload (S214).
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.prompt.governor import (
    DEFAULT_TRIM_ORDER,
    SECTIONS,
    apply_policy,
    budget_from_slots,
    budget_from_trace,
    default_policy,
    policy_from_data,
    policy_to_data,
    section_for_kind,
)
from runmal.prompt.slots import BASELINE_ORDER, make_slot
from runmal.tokens import TokenQuality, estimate_tokens

SECRET = "ZqxBudgetSecret058"


def mk(sid, kind, content, **kw):
    role = kw.pop("role", "user" if kind == "history" else "system")
    return make_slot(kind, role, content, id=sid, **kw)


def hist_slot(parts, sid="history"):
    return make_slot("history", "user", "", id=sid, splittable=True, parts=tuple(parts))

# ---------------- 1. section_for_kind ----------------

EXPECTED_SECTION = {
    "main_system": "context", "persona": "context",
    "memory_nucleus": "memory", "lore_before": "lore",
    "memory_retrieved": "memory", "examples": "context",
    "history": "history", "lore_after": "lore",
    "authors_note": "context", "post_history": "context",
}


def test_section_for_kind_baseline_and_fallback():
    assert set(EXPECTED_SECTION) == set(BASELINE_ORDER)
    for kind in BASELINE_ORDER:
        assert section_for_kind(kind) == EXPECTED_SECTION[kind], kind
    assert section_for_kind("totally_unknown_kind") == "context"
    assert section_for_kind("") == "context"
    assert section_for_kind("future_kind_xyz") == "context"

# ---------------- 2. budget_from_slots ----------------


def _mixed_slots():
    return [
        mk("sys", "main_system", "a" * 40),          # 10 context
        mk("per", "persona", "b" * 20),               # 5 context
        mk("lb", "lore_before", "c" * 40),            # 10 lore
        mk("la", "lore_after", "d" * 8),              # 2 lore
        mk("mn", "memory_nucleus", "e" * 16),         # 4 memory
        mk("hist", "history", "f" * 24),              # 6 history
    ]


def test_budget_from_slots_hand_computed():
    slots = _mixed_slots()
    hand = {s.id: estimate_tokens(s.content) for s in slots}
    assert hand == {"sys": 10, "per": 5, "lb": 10, "la": 2, "mn": 4, "hist": 6}
    b = budget_from_slots(slots, input_budget=100)
    assert b.sections["context"].tokens == hand["sys"] + hand["per"] == 15
    assert b.sections["lore"].tokens == hand["lb"] + hand["la"] == 12
    assert b.sections["memory"].tokens == hand["mn"] == 4
    assert b.sections["history"].tokens == hand["hist"] == 6
    assert tuple(b.sections) == SECTIONS
    assert b.total_tokens == sum(hand.values()) == 37
    assert b.total_tokens == sum(r.tokens for r in b.sections.values())
    assert b.remaining == 63 and b.over_budget is False
    assert b.count_quality == TokenQuality.ESTIMATED
    d = b.to_dict()
    assert d["total_tokens"] == 37 and d["count_quality"] == "estimated"
    assert d["sections"]["lore"]["slot_ids"] == ["lb", "la"]
    assert d["sections"]["context"]["slots"] == 2


def test_budget_from_slots_remaining_unclamped_when_over():
    b = budget_from_slots(_mixed_slots(), input_budget=10)
    assert b.total_tokens == 37
    assert b.remaining == -27  # negative, never clamped to 0
    assert b.over_budget is True


def test_budget_from_slots_exact_with_supplied_counter():
    slots = [mk("x", "main_system", "abcd"), mk("y", "persona", "abcdefgh")]
    b = budget_from_slots(slots, input_budget=100, counter=lambda t: len(t))
    assert b.total_tokens == 4 + 8 == 12  # len-based, not estimate (1 + 2)
    assert b.count_quality == TokenQuality.EXACT
    assert b.to_dict()["count_quality"] == "exact"
    b7 = budget_from_slots(slots, input_budget=100, counter=lambda t: 7)
    assert b7.total_tokens == 14 and b7.sections["context"].tokens == 14


def test_budget_from_slots_negative_budget_raises():
    with pytest.raises(ValueError):
        budget_from_slots(_mixed_slots(), input_budget=-1)

# ---------------- 3. budget_from_trace ----------------


def _hand_trace():
    return {
        "ledger": {"total_input_tokens": 30, "input_budget": 100,
                   "remaining_input_tokens": 70, "count_quality": "estimated"},
        "slots": [
            {"slot_id": "lb", "kind": "lore_before", "status": "included", "tokens": 10},
            {"slot_id": "la", "kind": "lore_after", "status": "discarded", "tokens": 5},
            {"slot_id": "mn", "kind": "memory_nucleus", "status": "included", "tokens": 4},
            {"slot_id": "h", "kind": "history", "status": "included", "tokens": 6},
            {"slot_id": "sys", "kind": "main_system", "status": "included", "tokens": 10},
            {"slot_id": "per", "kind": "persona", "status": "discarded", "tokens": 3},
        ],
    }


def test_budget_from_trace_reconciles_with_ledger():
    trace = _hand_trace()
    b = budget_from_trace(trace)
    assert b["total_input_tokens"] == trace["ledger"]["total_input_tokens"] == 30
    assert b["input_budget"] == 100 and b["remaining_input_tokens"] == 70
    assert b["count_quality"] == "estimated"
    assert b["sections"]["lore"] == {"included_tokens": 10, "discarded_tokens": 5, "slots": 2}
    assert b["sections"]["memory"] == {"included_tokens": 4, "discarded_tokens": 0, "slots": 1}
    assert b["sections"]["history"] == {"included_tokens": 6, "discarded_tokens": 0, "slots": 1}
    assert b["sections"]["context"] == {"included_tokens": 10, "discarded_tokens": 3, "slots": 2}
    included_sum = sum(s["included_tokens"] for s in b["sections"].values())
    assert included_sum == trace["ledger"]["total_input_tokens"]

# ---------------- 4. policy validation ----------------


def test_policy_none_and_empty_give_defaults():
    assert policy_from_data(None) == default_policy()
    p = policy_from_data({})
    assert p.section_caps == {s: None for s in SECTIONS}
    assert p.trim_order == DEFAULT_TRIM_ORDER == ("lore", "memory", "history", "context")
    assert default_policy().section_caps == {s: None for s in SECTIONS}


@pytest.mark.parametrize("bad", [
    {"bogus_key": 1},
    {"section_caps": {"bogus": 5}},
    {"section_caps": {"lore": 0}},
    {"section_caps": {"lore": True}},
    {"section_caps": {"lore": "x"}},
    {"section_caps": {"lore": -3}},
    {"trim_order": ["bogus"]},
    {"trim_order": ["lore", "lore"]},
])
def test_policy_from_data_rejects(bad):
    with pytest.raises(ValueError):
        policy_from_data(bad)


def test_policy_partial_trim_order_fills_missing_in_default_order():
    p = policy_from_data({"trim_order": ["history"]})
    assert p.trim_order == ("history", "lore", "memory", "context")
    p2 = policy_from_data({"trim_order": ["context", "lore"]})
    assert p2.trim_order == ("context", "lore", "memory", "history")


def test_policy_round_trip():
    data = {"section_caps": {"lore": 50}, "trim_order": ["history", "lore"]}
    expected = {
        "section_caps": {"context": None, "lore": 50, "memory": None, "history": None},
        "trim_order": ["history", "lore", "memory", "context"],
    }
    assert policy_to_data(policy_from_data(data)) == expected
    assert policy_to_data(policy_from_data(expected)) == expected
    assert policy_to_data(default_policy()) == {
        "section_caps": {s: None for s in SECTIONS},
        "trim_order": list(DEFAULT_TRIM_ORDER),
    }

# ---------------- 5. section cap: lore ----------------


def test_section_cap_drops_lowest_priority_lore_first():
    low = mk("lore/low", "lore_before", "c" * 40, priority=10)
    high = mk("lore/high", "lore_before", "d" * 40, priority=90)
    sys_slot = mk("sys", "main_system", "a" * 40, required=True)
    policy = policy_from_data({"section_caps": {"lore": 10}})
    gov = apply_policy([sys_slot, low, high], policy, input_budget=10000)
    assert [s.id for s in gov.kept] == ["sys", "lore/high"]
    assert len(gov.actions) == 1
    a = gov.actions[0]
    assert (a.slot_id, a.section, a.action, a.reason) == (
        "lore/low", "lore", "dropped", "governor_section_cap")
    assert a.tokens_before == 10 and a.tokens_after == 0 and a.trimmed_parts == 0

# ---------------- 6. section cap: history parts ----------------

PARTS = ["a" * 40, "b" * 40, "c" * 40]  # 10 tok each; joined 30, pairs 20


def test_history_cap_trims_oldest_parts_first():
    hist = hist_slot(PARTS)
    policy = policy_from_data({"section_caps": {"history": 20}})
    gov = apply_policy([hist], policy, input_budget=10000)
    assert len(gov.kept) == 1
    assert gov.kept[0].parts == tuple(PARTS[1:])  # newest parts survive
    assert len(gov.actions) == 1
    a = gov.actions[0]
    assert (a.slot_id, a.action, a.reason) == ("history", "trimmed", "governor_section_cap")
    assert a.trimmed_parts == 1
    assert a.tokens_before == 30 and a.tokens_after == 20


def test_history_cap_too_small_for_any_part_drops_slot():
    hist = hist_slot(PARTS)
    policy = policy_from_data({"section_caps": {"history": 5}})
    gov = apply_policy([hist], policy, input_budget=10000)
    assert gov.kept == ()
    assert len(gov.actions) == 1
    a = gov.actions[0]
    assert a.action == "dropped" and a.reason == "governor_section_cap"
    assert a.tokens_after == 0 and a.trimmed_parts == 3

# ---------------- 7. total budget ----------------


def _total_slots():
    return [
        mk("sys", "main_system", "a" * 40, required=True),   # 10, protected
        mk("lore1", "lore_before", "c" * 40),                # 10
        mk("mem1", "memory_nucleus", "e" * 40),              # 10
        mk("hist1", "history", "f" * 40),                    # 10
        mk("ctx1", "examples", "g" * 40),                    # 10 context
    ]


def test_total_budget_default_trim_order():
    gov = apply_policy(_total_slots(), default_policy(), input_budget=30)
    assert [s.id for s in gov.kept] == ["sys", "hist1", "ctx1"]
    assert [a.slot_id for a in gov.actions] == ["lore1", "mem1"]
    assert all(a.reason == "governor_total_budget" and a.action == "dropped"
               and a.tokens_after == 0 for a in gov.actions)


def test_total_budget_custom_trim_order_history_first():
    policy = policy_from_data({"trim_order": ["history", "context", "memory", "lore"]})
    gov = apply_policy(_total_slots(), policy, input_budget=30)
    assert [s.id for s in gov.kept] == ["sys", "lore1", "mem1"]
    assert [a.slot_id for a in gov.actions] == ["hist1", "ctx1"]


def test_total_budget_required_slots_never_dropped():
    slots = [mk("sys", "main_system", "a" * 80, required=True),  # 20 tok
             mk("lore1", "lore_before", "c" * 40)]               # 10 tok
    gov = apply_policy(slots, default_policy(), input_budget=5)
    assert [s.id for s in gov.kept] == ["sys"]  # still over, but untouched
    assert [a.slot_id for a in gov.actions] == ["lore1"]


def test_apply_policy_deterministic_and_input_not_mutated():
    slots = _total_slots() + [hist_slot(PARTS, sid="hist2")]
    snapshot = [(s.id, s.content, s.parts) for s in slots]
    policy = policy_from_data({"section_caps": {"history": 20}})
    g1 = apply_policy(slots, policy, input_budget=40)
    g2 = apply_policy(slots, policy, input_budget=40)
    assert [s.id for s in g1.kept] == [s.id for s in g2.kept]
    assert [a.to_dict() for a in g1.actions] == [a.to_dict() for a in g2.actions]
    assert [(s.id, s.content, s.parts) for s in slots] == snapshot
    assert len(slots) == len(snapshot)
    kept_hist = [s for s in g1.kept if s.id == "hist2"][0]
    assert kept_hist.parts == tuple(PARTS[2:])  # cap also counts hist1
    assert slots[-1].parts == tuple(PARTS)  # original slot untouched


def test_no_caps_generous_budget_no_actions():
    slots = _total_slots()
    gov = apply_policy(slots, default_policy(), input_budget=10000)
    assert gov.actions == ()
    assert [s.id for s in gov.kept] == [s.id for s in slots]

# ---------------- 8. sacrifice order within a section ----------------


def _cap_one_of_two(a, b):
    policy = policy_from_data({"section_caps": {"lore": 10}})
    return apply_policy([a, b], policy, input_budget=10000)


def test_sacrifice_lower_priority_first():
    gov = _cap_one_of_two(mk("lore/lowp", "lore_before", "c" * 40, priority=5),
                          mk("lore/highp", "lore_before", "d" * 40, priority=95))
    assert [a.slot_id for a in gov.actions] == ["lore/lowp"]
    assert [s.id for s in gov.kept] == ["lore/highp"]


def test_sacrifice_tie_higher_order_first():
    gov = _cap_one_of_two(mk("lore/ord1", "lore_before", "c" * 40, priority=50, order=1),
                          mk("lore/ord9", "lore_before", "d" * 40, priority=50, order=9))
    assert [a.slot_id for a in gov.actions] == ["lore/ord9"]
    assert [s.id for s in gov.kept] == ["lore/ord1"]


def test_sacrifice_tie_same_order_id_descending():
    gov = _cap_one_of_two(mk("lore/aaa", "lore_before", "c" * 40, priority=50, order=7),
                          mk("lore/zzz", "lore_before", "d" * 40, priority=50, order=7))
    assert [a.slot_id for a in gov.actions] == ["lore/zzz"]
    assert [s.id for s in gov.kept] == ["lore/aaa"]

# ---------------- inspect API ----------------


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _inspect(client, **kw):
    body = {"messages": kw.pop("messages")}
    body.update(kw)
    r = client.post("/api/v1/debug/prompt-inspect", json=body)
    assert r.status_code == 200, r.text
    return r.json()

MSGS = ["a" * 40, "b" * 40, "c" * 40, "d" * 40]  # history: 40 tok joined


def test_inspect_no_policy_budget_present_and_reconciled(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    result = _inspect(client, messages=MSGS)
    assert "budget" in result and "budget_governor" in result
    budget = result["budget"]
    assert set(budget["sections"]) == set(SECTIONS)
    included = sum(s["included_tokens"] for s in budget["sections"].values())
    assert included == result["ledger"]["total_input_tokens"]
    assert budget["total_input_tokens"] == result["ledger"]["total_input_tokens"]
    gov = result["budget_governor"]
    assert gov["applied"] is False and gov["source"] == "default"
    assert gov["actions"] == []
    assert gov["policy"]["section_caps"] == {s: None for s in SECTIONS}


def test_inspect_history_cap_trims_and_carries_no_content(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    secret_msg = SECRET + "x" * (40 - len(SECRET))
    msgs = ["a" * 40, "b" * 40, "c" * 40, secret_msg]
    base = _inspect(client, messages=msgs)
    governed = _inspect(client, messages=msgs,
                        budget_policy={"section_caps": {"history": 20}})
    assert governed["ledger"]["total_input_tokens"] < base["ledger"]["total_input_tokens"]
    assert governed["ledger"]["total_input_tokens"] == base["ledger"]["total_input_tokens"] - 20
    gov = governed["budget_governor"]
    assert gov["applied"] is True and gov["source"] == "explicit"
    assert gov["policy"]["section_caps"]["history"] == 20
    trimmed = [a for a in gov["actions"] if a["action"] == "trimmed" and a["slot_id"] == "history"]
    assert trimmed and trimmed[0]["reason"] == "governor_section_cap"
    assert trimmed[0]["trimmed_parts"] == 2
    hist_row = [s for s in governed["slots"] if s["slot_id"] == "history"][0]
    base_hist = [s for s in base["slots"] if s["slot_id"] == "history"][0]
    assert hist_row["tokens"] < base_hist["tokens"]
    assert SECRET not in json.dumps(governed)
    assert SECRET not in json.dumps(base)


def test_inspect_unknown_section_policy_422(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    r = client.post("/api/v1/debug/prompt-inspect", json={
        "messages": MSGS, "budget_policy": {"section_caps": {"bogus": 5}}})
    assert r.status_code == 422, r.text


def test_default_budget_policy_endpoint(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    r = client.get("/api/v1/debug/budget-policy/default")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["source"] == "default"
    assert set(data["policy"]["section_caps"]) == set(SECTIONS)
    assert data["policy"]["section_caps"] == {s: None for s in SECTIONS}
    assert data["policy"]["trim_order"] == list(DEFAULT_TRIM_ORDER)


def test_inspect_reconciliation_and_lore_account_intact(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    result = _inspect(client, messages=MSGS)
    assert result["budget"]["total_input_tokens"] == result["ledger"]["total_input_tokens"]
    assert "lore_account" in result  # P-044 neighbour intact
    assert result["budget"]["input_budget"] == result["ledger"]["input_budget"]
    assert result["budget"]["remaining_input_tokens"] == result["ledger"]["remaining_input_tokens"]
