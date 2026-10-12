"""S205 acceptance: prompt template engine.

Golden prompt manifests must never exceed the effective context allowance
after response reservation. Fixed fixtures assert exact manifest math.
"""

import pytest

from runmal.prompt import (
    BASELINE_ORDER,
    ImpossiblePromptError,
    baseline_order,
    compose,
    make_slot,
)
from runmal.prompt.slots import Slot
from runmal.tokens import TokenQuality


def golden_slots():
    return [
        make_slot("main_system", "system", "S" * 400, id="sys", required=True),
        make_slot("persona", "system", "P" * 400, id="persona"),
        make_slot("lore_before", "system", "L" * 1200, id="lore", priority=50),
        Slot(
            id="history",
            kind="history",
            role="user",
            order=baseline_order("history"),
            splittable=True,
            parts=tuple("H" * 200 for _ in range(10)),  # 10 x 50 tokens
        ),
        make_slot("authors_note", "system", "N" * 80, id="note"),
    ]


def test_golden_manifest_never_exceeds_allowance():
    # context 900 - reserve 200 - overhead 50 = 650 input budget.
    # (History parts join with newlines: n parts -> 200n + (n-1) chars.)
    result = compose(golden_slots(), context_limit=900,
                     reserve_response=200, overhead=50)
    m = result.manifest
    assert m.input_budget == 650
    assert m.total_input_tokens <= m.input_budget
    assert m.total_input_tokens == 650  # exactly packed
    assert m.count_quality == TokenQuality.ESTIMATED
    # sys(100) + persona(100) + lore(300) + history trimmed to 3 parts (150)
    assert [u.slot_id for u in m.included] == ["sys", "persona", "lore", "history"]
    hist = next(u for u in m.included if u.slot_id == "history")
    assert hist.tokens == 150 and hist.trimmed_parts == 7
    # note (20 tokens) found no room: recorded, not silent
    assert [(d.slot_id, d.reason) for d in m.discarded] == [
        ("note", "over_input_budget")
    ]
    # messages follow slot order
    assert [msg.slot_id for msg in result.messages] == [
        "sys", "persona", "lore", "history",
    ]
    assert [msg.role for msg in result.messages] == [
        "system", "system", "system", "user",
    ]


def test_response_reservation_comes_first():
    # A huge reservation starves optional slots but required ones stay.
    slots = [
        make_slot("main_system", "system", "S" * 40, id="sys", required=True),
        make_slot("persona", "system", "P" * 400, id="persona"),
    ]
    result = compose(slots, context_limit=500, reserve_response=450, overhead=0)
    assert result.manifest.input_budget == 50
    assert [u.slot_id for u in result.manifest.included] == ["sys"]
    assert result.manifest.discarded[0].slot_id == "persona"


def test_impossible_when_required_slots_overflow():
    slots = [make_slot("main_system", "system", "S" * 4000, id="sys",
                       required=True)]
    with pytest.raises(ImpossiblePromptError):
        compose(slots, context_limit=500, reserve_response=100)


def test_impossible_when_reservation_eats_everything():
    slots = [make_slot("main_system", "system", "S", id="sys")]
    with pytest.raises(ImpossiblePromptError):
        compose(slots, context_limit=100, reserve_response=100)


def test_slot_hard_budget_discards():
    slots = [
        make_slot("lore_before", "system", "L" * 400, id="lore", slot_budget=50),
        make_slot("persona", "system", "P" * 40, id="persona"),
    ]
    result = compose(slots, context_limit=1000, reserve_response=0)
    assert [(d.slot_id, d.reason) for d in result.manifest.discarded] == [
        ("lore", "over_slot_budget")
    ]
    assert [u.slot_id for u in result.manifest.included] == ["persona"]


def test_history_trims_oldest_first():
    parts = tuple(f"msg{i}-" + "x" * 36 for i in range(4))  # ~10 tokens each
    slot = Slot(id="h", kind="history", role="user", order=0,
                splittable=True, parts=parts)
    result = compose([slot], context_limit=35, reserve_response=0)
    usage = result.manifest.included[0]
    assert usage.trimmed_parts == 1  # oldest part dropped
    assert "msg0" not in result.messages[0].content
    assert "msg3" in result.messages[0].content


def test_priority_orders_equal_order_slots():
    slots = [
        make_slot("lore_before", "system", "A" * 400, id="lo", priority=10),
        make_slot("lore_before", "system", "B" * 400, id="hi", priority=90),
    ]
    result = compose(slots, context_limit=150, reserve_response=0)
    assert [u.slot_id for u in result.manifest.included] == ["hi"]
    assert result.manifest.discarded[0].slot_id == "lo"


def test_invalid_inputs_rejected():
    with pytest.raises(ValueError):
        Slot(id="x", kind="k", role="emperor", order=0)
    with pytest.raises(ValueError):
        compose([], context_limit=0, reserve_response=0)
    with pytest.raises(ValueError):
        compose([], context_limit=100, reserve_response=-1)
    with pytest.raises(ValueError):
        Slot(id="x", kind="history", role="user", order=0,
             splittable=True, parts=())


def test_baseline_order_helper():
    assert baseline_order("main_system") < baseline_order("persona")
    assert baseline_order("history") < baseline_order("authors_note")
    assert baseline_order("unknown_kind") >= len(BASELINE_ORDER)
