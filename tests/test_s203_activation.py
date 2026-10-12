"""S203 acceptance: activation semantics.

One scenario per semantic: constant, selective (key-gated), sticky,
cooldown, delay, recursion with cycle detection and the hard depth cap.
Cyclic lore must terminate deterministically.
"""

import pytest

from runmal.lorebooks.activation import (
    MAX_RECURSION_DEPTH,
    ActivatableEntry,
    EntryState,
    activate,
)


def ae(eid, **kw):
    base = dict(name=eid, content=f"content-{eid}")
    base.update(kw)
    return ActivatableEntry(id=eid, **base)


def ids(result):
    return [a.entry_id for a in result.activations]


def via(result, eid):
    return next(a.via for a in result.activations if a.entry_id == eid)


def test_constant_always_active_without_hits():
    entries = [ae("a", constant=True)]
    r = activate(entries, set(), {})
    assert ids(r) == ["a"]
    assert via(r, "a") == "constant"
    # still active three ticks later, no hits ever
    states = r.states
    for _ in range(3):
        r = activate(entries, set(), states)
        assert ids(r) == ["a"]


def test_selective_needs_key_hit():
    entries = [ae("a")]
    assert ids(activate(entries, set(), {})) == []
    r = activate(entries, {"a"}, {})
    assert ids(r) == ["a"]
    assert via(r, "a") == "key"


def test_disabled_never_activates():
    entries = [ae("a", enabled=False, constant=True)]
    assert ids(activate(entries, {"a"}, {})) == []


def test_sticky_carries_over():
    entries = [ae("a", sticky_prompts=2)]
    states: dict = {}
    assert ids(activate(entries, {"a"}, states)) == ["a"]  # tick 0: key
    assert ids(activate(entries, set(), states)) == ["a"]  # tick 1: sticky
    assert via(activate(entries, set(), states), "a") == "sticky"  # tick 2
    assert ids(activate(entries, set(), states)) == []  # tick 3: expired


def test_sticky_zero_is_off():
    entries = [ae("a", sticky_prompts=0)]
    states: dict = {}
    activate(entries, {"a"}, states)
    assert ids(activate(entries, set(), states)) == []


def test_cooldown_suppresses_retrigger():
    entries = [ae("a", cooldown_prompts=2)]
    states: dict = {}
    assert ids(activate(entries, {"a"}, states)) == ["a"]  # tick 0: fires
    assert ids(activate(entries, {"a"}, states)) == []  # tick 1: suppressed
    assert ids(activate(entries, {"a"}, states)) == []  # tick 2: suppressed
    r = activate(entries, {"a"}, states)  # tick 3: cooldown spent
    assert ids(r) == ["a"]


def test_delay_fires_later():
    entries = [ae("a", delay_prompts=2)]
    states: dict = {}
    assert ids(activate(entries, {"a"}, states)) == []  # tick 0: armed
    assert ids(activate(entries, set(), states)) == []  # tick 1: counting
    r = activate(entries, set(), states)  # tick 2: fires
    assert ids(r) == ["a"]
    assert via(r, "a") == "delay"


def test_delay_then_sticky_chain():
    entries = [ae("a", delay_prompts=1, sticky_prompts=1)]
    states: dict = {}
    assert ids(activate(entries, {"a"}, states)) == []  # tick 0: armed
    assert ids(activate(entries, set(), states)) == ["a"]  # tick 1: delay fires
    assert ids(activate(entries, set(), states)) == ["a"]  # tick 2: sticky
    assert ids(activate(entries, set(), states)) == []  # tick 3: done


def test_recursion_expands_references():
    entries = [
        ae("a", content="A sees {{lore:B}}"),
        ae("b", name="B", content="B sees {{lore:C}}"),
        ae("c", name="C", content="C alone"),
    ]
    r = activate(entries, {"a"}, {})
    assert ids(r) == ["a", "b", "c"]
    a = next(x for x in r.activations if x.entry_id == "a")
    b = next(x for x in r.activations if x.entry_id == "b")
    assert a.depth == 0 and b.depth == 1
    assert a.content == "A sees B sees C alone"
    assert b.via == "reference"


def test_cycle_terminates_deterministically():
    entries = [
        ae("a", name="A", content="A -> {{lore:B}}"),
        ae("b", name="B", content="B -> {{lore:A}}"),
    ]
    r1 = activate(entries, {"a"}, {})
    r2 = activate(entries, {"a"}, {})
    assert ids(r1) == ["a", "b"]
    # B's reference back to A is left literal instead of recursing forever
    b = next(x for x in r1.activations if x.entry_id == "b")
    assert "{{lore:A}}" in b.content
    # deterministic across runs
    assert [ (x.entry_id, x.content) for x in r1.activations ] == [
        (x.entry_id, x.content) for x in r2.activations
    ]


def test_hard_recursion_depth_cap():
    entries = [ae(f"e{i}", name=f"E{i}",
                  content=f"E{i} {{{{lore:E{i+1}}}}}" if i < 7 else "E7 end")
               for i in range(8)]
    r = activate(entries, {"e0"}, {})
    depths = {x.entry_id: x.depth for x in r.activations}
    assert max(depths.values()) <= MAX_RECURSION_DEPTH
    # the entry beyond the cap keeps its reference literal
    deepest = max(r.activations, key=lambda x: x.depth)
    assert "{{lore:" in deepest.content


def test_unknown_reference_left_literal():
    entries = [ae("a", content="hello {{lore:Nobody}}")]
    r = activate(entries, {"a"}, {})
    assert r.activations[0].content == "hello {{lore:Nobody}}"
    assert ids(r) == ["a"]


def test_disabled_reference_target_left_literal():
    entries = [
        ae("a", content="see {{lore:B}}"),
        ae("b", name="B", enabled=False, content="hidden"),
    ]
    r = activate(entries, {"a"}, {})
    assert ids(r) == ["a"]
    assert "{{lore:B}}" in r.activations[0].content


def test_reference_lookup_case_insensitive_fallback():
    entries = [
        ae("a", content="see {{lore:bravo}}"),
        ae("b", name="Bravo", content="here"),
    ]
    r = activate(entries, {"a"}, {})
    assert ids(r) == ["a", "b"]


def test_negative_config_rejected():
    with pytest.raises(ValueError):
        ae("a", sticky_prompts=-1)
    with pytest.raises(ValueError):
        ae("a", cooldown_prompts=-2)
    with pytest.raises(ValueError):
        ae("a", delay_prompts=-3)


def test_order_is_deterministic_input_order():
    entries = [ae("b"), ae("a")]
    r = activate(entries, {"a", "b"}, {})
    assert ids(r) == ["b", "a"]


def test_from_orm_adapter():
    from runmal.lorebooks.activation import ActivatableEntry as AE

    class Fake:
        id = "orm-1"
        name = "Orm"
        content = "c"
        enabled = 1
        constant = 0
        sticky_prompts = 2
        cooldown_prompts = 0
        delay_prompts = 0

    e = AE.from_orm(Fake())
    assert (e.id, e.name, e.sticky_prompts) == ("orm-1", "Orm", 2)
