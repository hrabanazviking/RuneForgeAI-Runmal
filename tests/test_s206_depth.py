"""S206 acceptance: Author's Note depth injection.

Prompt tests verify exact position/depth behavior and boundary cases:
N messages from end, N=0, N beyond length, trimmed history, missing
history, budget exhaustion, and invalid depth.
"""

import pytest

from runmal.prompt import baseline_order, compose, make_slot
from runmal.prompt.slots import Slot


def history_slot(n=4, prefix="m"):
    return Slot(
        id="history",
        kind="history",
        role="user",
        order=baseline_order("history"),
        splittable=True,
        parts=tuple(f"{prefix}{i}-" + "x" * 34 for i in range(n)),
    )


def note_slot(depth, content="NOTE-" + "y" * 35):
    return make_slot("authors_note", "system", content, id="note", depth=depth)


def test_depth_one_injects_before_last_message():
    slots = [history_slot(4), note_slot(1)]
    result = compose(slots, context_limit=1000, reserve_response=0)
    bodies = [m.content for m in result.messages]
    assert len(bodies) == 3
    assert "m0" in bodies[0] and "m2" in bodies[0] and "m3" not in bodies[0]
    assert "NOTE" in bodies[1]
    assert bodies[2].strip().startswith("m3-")
    assert [m.slot_id for m in result.messages] == ["history", "note", "history"]


def test_depth_zero_appends_after_history():
    slots = [history_slot(3), note_slot(0)]
    result = compose(slots, context_limit=1000, reserve_response=0)
    assert [m.slot_id for m in result.messages] == ["history", "note"]
    assert "m2" in result.messages[0].content


def test_depth_beyond_length_injects_before_all():
    slots = [history_slot(3), note_slot(99)]
    result = compose(slots, context_limit=1000, reserve_response=0)
    assert [m.slot_id for m in result.messages] == ["note", "history"]
    assert "m0" in result.messages[1].content


def test_depth_counts_from_surviving_parts_after_trim():
    # 4 large parts, budget trims the oldest; depth=1 then splits survivors.
    # Each part ~19 tokens; history ~79. Budget 70 trims one part; note fits.
    big_history = Slot(
        id="history",
        kind="history",
        role="user",
        order=baseline_order("history"),
        splittable=True,
        parts=tuple(f"m{i}-" + "x" * 76 for i in range(4)),
    )
    slots = [big_history, note_slot(1)]
    result = compose(slots, context_limit=70, reserve_response=0)
    bodies = [m.content for m in result.messages]
    assert len(bodies) == 3
    assert "m0" not in bodies[0]  # trimmed oldest
    assert "m1" in bodies[0] and "m2" in bodies[0]
    assert "NOTE" in bodies[1]
    assert "m3" in bodies[2]


def test_no_history_note_emits_in_order_position():
    slots = [
        make_slot("persona", "system", "P" * 40, id="persona"),
        note_slot(2),
    ]
    result = compose(slots, context_limit=1000, reserve_response=0)
    assert [m.slot_id for m in result.messages] == ["persona", "note"]


def test_note_over_budget_discarded_with_reason():
    slots = [history_slot(2), note_slot(1, content="N" * 4000)]
    result = compose(slots, context_limit=100, reserve_response=0)
    assert [(d.slot_id, d.reason) for d in result.manifest.discarded] == [
        ("note", "over_input_budget")
    ]
    # history itself survived untouched
    assert [m.slot_id for m in result.messages] == ["history"]


def test_manifest_stays_within_allowance_with_injection():
    slots = [history_slot(6), note_slot(2),
             make_slot("persona", "system", "P" * 400, id="persona")]
    result = compose(slots, context_limit=500, reserve_response=100)
    m = result.manifest
    assert m.total_input_tokens <= m.input_budget
    assert "note" in [u.slot_id for u in m.included]


def test_negative_depth_rejected():
    with pytest.raises(ValueError):
        make_slot("authors_note", "system", "x", id="note", depth=-1)
