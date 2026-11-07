"""P-031 acceptance: recursive scanning.

Roadmap line: *Recursive scanning: entries triggering entries, with
depth limits and cycle safety, token budget enforced.*

One scenario per semantic, in the S202/S203 house style: the scan
layer (``scan_entries_recursive``), the activation relabel
(``via="recursive"``), and the opt-in preview path. All fixtures are
authored fresh in this module (P-005 discipline); no mirror source
was consulted.
"""

import json

import pytest

from runmal.lorebooks.activation import ActivatableEntry, EntryState, activate
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.scan import (
    MAX_RECURSIVE_SCAN_DEPTH,
    ScanEntry,
    scan_entries,
    scan_entries_recursive,
)
from runmal.tokens import estimate_tokens


def se(eid, keys=(), content="", **kw):
    return ScanEntry(id=eid, keys=tuple(keys), content=content, **kw)


def sig(result):
    return [(h.entry_id, h.depth, h.triggered_by) for h in result.hits]


def chain(n, prefix="k"):
    """Entries e0..e(n-1): e_i's content mentions key k(i+1)."""
    entries = []
    for i in range(n):
        content = f"lore {i} mentions {prefix}{i + 1}" if i + 1 < n else f"lore {i} end"
        entries.append(se(f"e{i}", keys=(f"{prefix}{i}",), content=content))
    return entries


# ---------------------------------------------------------------- scan layer


def test_round0_is_exactly_the_plain_scan():
    entries = chain(3)
    plain = scan_entries(entries, ["k0 rises"], 1)
    rec = scan_entries_recursive(entries, ["k0 rises"], 1, max_recursion_depth=0)
    assert [h.entry_id for h in rec.hits] == [h.entry_id for h in plain]
    assert rec.hits[0].matched_primary == plain[0].matched_primary
    assert rec.hits[0].message_indices == plain[0].message_indices
    assert sig(rec) == [("e0", 0, None)]
    assert rec.depth_reached == 0
    assert rec.budget_exhausted is False


def test_chain_recruits_entries_at_rising_depths():
    entries = [
        se("a", keys=("alpha",), content="alpha lore names beta"),
        se("b", keys=("beta",), content="beta lore names gamma"),
        se("c", keys=("gamma",), content="gamma lore"),
    ]
    r = scan_entries_recursive(entries, ["alpha rises"], 1)
    assert sig(r) == [("a", 0, None), ("b", 1, "a"), ("c", 2, "b")]
    assert r.depth_reached == 2
    assert r.budget_exhausted is False
    assert r.tokens_used == sum(estimate_tokens(e.content) for e in entries)


def test_mutual_cycle_terminates_and_each_fires_once():
    entries = [
        se("a", keys=("alpha",), content="alpha names beta"),
        se("b", keys=("beta",), content="beta names alpha"),
    ]
    r = scan_entries_recursive(entries, ["alpha"], 1)
    assert sig(r) == [("a", 0, None), ("b", 1, "a")]


def test_self_reference_fires_once():
    entries = [se("s", keys=("loop",), content="loop loop loop")]
    r = scan_entries_recursive(entries, ["loop begins"], 1)
    assert sig(r) == [("s", 0, None)]


def test_diamond_fires_once_with_first_parent_as_trigger():
    entries = [
        se("a", keys=("alpha",), content="alpha names beta and gamma"),
        se("b", keys=("beta",), content="beta names delta"),
        se("c", keys=("gamma",), content="gamma names delta"),
        se("d", keys=("delta",), content="delta lore"),
    ]
    r = scan_entries_recursive(entries, ["alpha"], 1)
    assert sig(r) == [
        ("a", 0, None),
        ("b", 1, "a"),
        ("c", 1, "a"),
        ("d", 2, "b"),
    ]


def test_default_depth_cap_is_five():
    entries = chain(9)
    r = scan_entries_recursive(entries, ["k0"], 1)
    assert [h.depth for h in r.hits] == [0, 1, 2, 3, 4, 5]
    assert r.depth_reached == MAX_RECURSIVE_SCAN_DEPTH == 5
    assert len(r.hits) == 6


@pytest.mark.parametrize("cap,expected", [(0, ["e0"]), (1, ["e0", "e1"]), (2, ["e0", "e1", "e2"])])
def test_explicit_depth_caps(cap, expected):
    r = scan_entries_recursive(chain(4), ["k0"], 1, max_recursion_depth=cap)
    assert [h.entry_id for h in r.hits] == expected


def test_disabled_entry_is_never_recruited():
    entries = [
        se("a", keys=("alpha",), content="alpha names beta"),
        se("b", keys=("beta",), content="beta lore", enabled=False),
    ]
    r = scan_entries_recursive(entries, ["alpha"], 1)
    assert sig(r) == [("a", 0, None)]


def test_constant_entry_is_never_recruited_and_never_a_parent():
    entries = [
        se("a", keys=("alpha",), content="alpha names beta"),
        se("b", keys=("beta",), content="beta names gamma", constant=True),
        se("c", keys=("gamma",), content="gamma lore"),
    ]
    r = scan_entries_recursive(entries, ["alpha"], 1)
    # b is constant: the scanner skips it in every round, so it is
    # never admitted and its content is never scanned for gamma.
    assert sig(r) == [("a", 0, None)]


def test_secondary_keys_gate_recursive_rounds():
    entries = [
        se("a", keys=("alpha",), content="alpha names beta only"),
        se(
            "b",
            keys=("beta",),
            secondary_keys=("sigil",),
            content="beta lore",
        ),
    ]
    # Parent content has the primary but not the secondary: no recruit.
    assert sig(scan_entries_recursive(entries, ["alpha"], 1)) == [("a", 0, None)]
    entries[0] = se("a", keys=("alpha",), content="alpha names beta and sigil")
    r = scan_entries_recursive(entries, ["alpha"], 1)
    assert sig(r) == [("a", 0, None), ("b", 1, "a")]
    assert r.hits[1].matched_secondary == ("sigil",)


def test_scan_depth_window_governs_round_zero():
    entries = chain(2)
    msgs = ["k0 is old news", "nothing here"]
    assert scan_entries_recursive(entries, msgs, 1).hits == ()
    assert sig(scan_entries_recursive(entries, msgs, 2)) == [("e0", 0, None), ("e1", 1, "e0")]


def test_matching_rules_are_inherited_in_recursive_rounds():
    entries = [
        se("a", keys=("alpha",), content="alpha text CONCATheNATE BETA"),
        se("b", keys=("beta",), content="beta lore"),
        se("c", keys=("cat",), content="cat lore"),
    ]
    r = scan_entries_recursive(entries, ["alpha"], 1)
    # beta matches case-insensitively as a whole word; "cat" inside
    # "concatenate" is not a whole-word match, so c stays silent.
    assert sig(r) == [("a", 0, None), ("b", 1, "a")]


def test_recursive_hits_carry_no_message_indices():
    r = scan_entries_recursive(chain(2), ["k0"], 1)
    assert r.hits[0].message_indices == (0,)
    assert r.hits[1].message_indices == ()


def test_deterministic_repeat_calls():
    entries = chain(4)
    first = scan_entries_recursive(entries, ["k0"], 1)
    second = scan_entries_recursive(entries, ["k0"], 1)
    assert first == second


def test_empty_inputs_recruit_nothing():
    assert scan_entries_recursive([], ["k0"], 1).hits == ()
    assert scan_entries_recursive(chain(2), [], 1).hits == ()
    assert scan_entries_recursive(chain(2), ["no keys here"], 1).hits == ()


# ------------------------------------------------------------- token budget


def test_budget_generous_admits_full_chain():
    entries = chain(3)
    total = sum(estimate_tokens(e.content) for e in entries)
    r = scan_entries_recursive(entries, ["k0"], 1, token_budget=total + 10)
    assert [h.entry_id for h in r.hits] == ["e0", "e1", "e2"]
    assert r.tokens_used == total
    assert r.budget_exhausted is False


def test_budget_fully_consumed_by_a_complete_chain_still_flags():
    entries = chain(3)
    total = sum(estimate_tokens(e.content) for e in entries)
    r = scan_entries_recursive(entries, ["k0"], 1, token_budget=total)
    # Nothing was lost -- the whole chain fits exactly -- but the
    # budget is fully consumed, so expansion is honestly reported
    # as exhausted (the leaf's content is never scanned onward).
    assert [h.entry_id for h in r.hits] == ["e0", "e1", "e2"]
    assert r.tokens_used == total
    assert r.budget_exhausted is True


def test_budget_blocks_recruit_and_its_whole_subtree():
    entries = chain(3)
    cost0 = estimate_tokens(entries[0].content)
    cost1 = estimate_tokens(entries[1].content)
    # Room for e0 + e1 exactly; e2 must be refused, and since e1 is
    # the only path to e2 the refusal is total.
    r = scan_entries_recursive(entries, ["k0"], 1, token_budget=cost0 + cost1)
    assert [h.entry_id for h in r.hits] == ["e0", "e1"]
    assert r.budget_exhausted is True
    assert r.tokens_used == cost0 + cost1


def test_budget_skipped_candidate_is_never_scanned_onward():
    entries = [
        se("a", keys=("alpha",), content="alpha names beta and delta"),
        se("b", keys=("beta",), content="beta names gamma " + "x" * 200),
        se("c", keys=("gamma",), content="gamma lore"),
        se("d", keys=("delta",), content="delta lore"),
    ]
    budget = estimate_tokens(entries[0].content) + estimate_tokens(entries[3].content)
    r = scan_entries_recursive(entries, ["alpha"], 1, token_budget=budget)
    # b does not fit and is skipped (never scanned, so gamma never
    # appears); the smaller later candidate d still fits (greedy).
    assert [h.entry_id for h in r.hits] == ["a", "d"]
    assert r.budget_exhausted is True


def test_budget_round0_over_budget_flags_exhausted_at_depth_zero():
    entries = chain(2)
    r = scan_entries_recursive(entries, ["k0"], 1, max_recursion_depth=0, token_budget=1)
    # Direct hits are always admitted; the flag honestly reports
    # that the budget is already met/exceeded by round 0 alone.
    assert [h.entry_id for h in r.hits] == ["e0"]
    assert r.tokens_used > 1
    assert r.budget_exhausted is True


def test_budget_round0_over_budget_blocks_expansion():
    entries = chain(3)
    r = scan_entries_recursive(entries, ["k0"], 1, token_budget=1)
    assert [h.entry_id for h in r.hits] == ["e0"]
    assert r.budget_exhausted is True
    assert r.depth_reached == 0


@pytest.mark.parametrize("bad", [-1, 1.5, True, "2"])
def test_invalid_max_recursion_depth_rejected(bad):
    with pytest.raises(ValueError):
        scan_entries_recursive(chain(1), ["k0"], 1, max_recursion_depth=bad)


@pytest.mark.parametrize("bad", [0, -3, 2.5, True])
def test_invalid_token_budget_rejected(bad):
    with pytest.raises(ValueError):
        scan_entries_recursive(chain(1), ["k0"], 1, token_budget=bad)


def test_depth_request_above_the_hard_cap_is_clamped():
    r = scan_entries_recursive(chain(9), ["k0"], 1, max_recursion_depth=99)
    assert [h.depth for h in r.hits] == [0, 1, 2, 3, 4, 5]
    assert r.depth_reached == MAX_RECURSIVE_SCAN_DEPTH


def test_duplicate_id_rows_fire_at_most_once():
    entries = [
        se("x", keys=("alpha",), content="alpha lore"),
        se("x", keys=("beta",), content="beta lore"),
    ]
    r = scan_entries_recursive(entries, ["alpha and beta"], 1)
    assert [h.entry_id for h in r.hits] == ["x"]


def test_entries_may_be_any_iterable():
    r = scan_entries_recursive(iter(chain(2)), ["k0"], 1)
    assert [h.entry_id for h in r.hits] == ["e0", "e1"]


def test_scan_entry_from_orm_carries_content():
    class Row:
        id = 7
        enabled = True
        constant = False
        keys_json = json.dumps(["alpha"])
        secondary_keys_json = json.dumps([])
        whole_word = True
        case_sensitive = False
        content = "alpha lore names beta"

    entry = ScanEntry.from_orm(Row())
    assert entry.id == "7"
    assert entry.content == "alpha lore names beta"


# --------------------------------------------------------------- activation


def ae(eid, **kw):
    base = dict(name=eid, content=f"content-{eid}")
    base.update(kw)
    return ActivatableEntry(id=eid, **base)


def test_recursive_hit_activates_via_recursive_at_its_depth():
    entries = [ae("a"), ae("b")]
    r = activate(entries, {"a", "b"}, {}, recursive_hit_ids={"b"}, hit_depths={"b": 2})
    by_id = {a.entry_id: a for a in r.activations}
    assert by_id["a"].via == "key" and by_id["a"].depth == 0
    assert by_id["b"].via == "recursive" and by_id["b"].depth == 2


def test_activation_without_recursive_params_is_unchanged():
    entries = [ae("a"), ae("b")]
    r = activate(entries, {"a", "b"}, {})
    assert [(a.entry_id, a.via, a.depth) for a in r.activations] == [
        ("a", "key", 0),
        ("b", "key", 0),
    ]


def test_recursive_hit_with_delay_arms_the_delay_instead():
    entries = [ae("b", delay_prompts=2)]
    states: dict = {}
    r = activate(entries, {"b"}, states, recursive_hit_ids={"b"}, hit_depths={"b": 1})
    assert r.activations == []
    assert states["b"].delay_armed is True
    assert states["b"].delay_remaining == 2


def test_recursive_hit_under_cooldown_is_suppressed():
    entries = [ae("b")]
    states = {"b": EntryState(cooldown_remaining=1)}
    r = activate(entries, {"b"}, states, recursive_hit_ids={"b"}, hit_depths={"b": 1})
    assert r.activations == []
    assert states["b"].cooldown_remaining == 0


def test_delayed_recursive_entry_later_fires_as_plain_delay():
    entries = [ae("b", delay_prompts=1)]
    states: dict = {}
    r = activate(entries, {"b"}, states, recursive_hit_ids={"b"}, hit_depths={"b": 3})
    assert r.activations == []
    # Next tick the caller passes no recursive arguments; the firing
    # is a delay firing, with recursive provenance honestly absent.
    r = activate(entries, set(), states)
    assert [(a.entry_id, a.via, a.depth) for a in r.activations] == [("b", "delay", 0)]


def test_depth_is_only_reported_for_recursive_firings():
    # An armed-delay firing whose id is (mis)listed as recursive in
    # the same call still reports depth 0: depth belongs to via.
    entries = [ae("b", delay_prompts=1)]
    states: dict = {}
    activate(entries, {"b"}, states)
    r = activate(entries, set(), states, recursive_hit_ids={"b"}, hit_depths={"b": 3})
    assert [(a.entry_id, a.via, a.depth) for a in r.activations] == [("b", "delay", 0)]


def test_empty_recursive_params_match_absent_params():
    entries = [ae("a", sticky_prompts=1), ae("b", constant=True)]
    plain = activate(entries, {"a"}, {})
    empty = activate(entries, {"a"}, {}, recursive_hit_ids=set(), hit_depths={})
    assert [(a.entry_id, a.via, a.depth) for a in plain.activations] == [
        (a.entry_id, a.via, a.depth) for a in empty.activations
    ]


def test_recursive_ids_without_depths_relabel_with_depth_zero():
    entries = [ae("b")]
    r = activate(entries, {"b"}, {}, recursive_hit_ids={"b"})
    assert [(a.entry_id, a.via, a.depth) for a in r.activations] == [("b", "recursive", 0)]


def test_sticky_armed_entry_hit_recursively_fires_as_recursive():
    entries = [ae("b", sticky_prompts=2)]
    states = {"b": EntryState(sticky_remaining=1)}
    r = activate(entries, {"b"}, states, recursive_hit_ids={"b"}, hit_depths={"b": 1})
    assert [(a.entry_id, a.via, a.depth) for a in r.activations] == [("b", "recursive", 1)]


# ------------------------------------------------------------------ preview


class FakeRow:
    def __init__(self, eid, key, content, **kw):
        self.id = eid
        self.name = eid
        self.content = content
        self.enabled = kw.get("enabled", True)
        self.constant = kw.get("constant", False)
        self.keys_json = json.dumps([key] if key else [])
        self.secondary_keys_json = json.dumps(kw.get("secondary", []))
        self.whole_word = True
        self.case_sensitive = False
        self.sticky_prompts = 0
        self.cooldown_prompts = 0
        self.delay_prompts = kw.get("delay_prompts", 0)
        self.priority = kw.get("priority", 100)


def preview_rows():
    return [
        FakeRow("a", "alpha", "alpha lore names beta"),
        FakeRow("b", "beta", "beta lore names gamma"),
        FakeRow("c", "gamma", "gamma lore"),
    ]


def test_preview_default_does_not_recruit_and_has_no_recursion_metadata():
    out = preview_activation(preview_rows(), ["alpha rises"], 1, None)
    assert "recursive_scan" not in out
    rows = {r["entry_id"]: r for r in out["entries"]}
    assert rows["a"]["status"] == "included"
    assert rows["b"]["status"] == "not_triggered"
    assert rows["c"]["status"] == "not_triggered"


def test_preview_recursive_recruits_with_metadata():
    out = preview_activation(preview_rows(), ["alpha rises"], 1, None, recursive_scan=True)
    assert out["recursive_scan"] is True
    assert out["max_recursion_depth"] == MAX_RECURSIVE_SCAN_DEPTH
    assert out["recursion_depth_reached"] == 2
    assert out["recursion_budget_exhausted"] is False
    rows = {r["entry_id"]: r for r in out["entries"]}
    assert rows["a"]["via"] == "key" and rows["a"]["depth"] == 0
    assert rows["b"]["via"] == "recursive" and rows["b"]["depth"] == 1
    assert rows["c"]["via"] == "recursive" and rows["c"]["depth"] == 2
    assert all(r["status"] == "included" for r in rows.values())


def test_preview_recursive_respects_max_depth():
    out = preview_activation(
        preview_rows(), ["alpha rises"], 1, None, recursive_scan=True, max_recursion_depth=1
    )
    assert out["recursion_depth_reached"] == 1
    rows = {r["entry_id"]: r for r in out["entries"]}
    assert rows["b"]["status"] == "included"
    assert rows["c"]["status"] == "not_triggered"


def test_preview_recursive_delayed_entry_is_not_triggered_but_explained():
    rows = preview_rows()
    rows[1] = FakeRow("b", "beta", "beta lore names gamma", delay_prompts=2)
    out = preview_activation(rows, ["alpha rises"], 1, None, recursive_scan=True)
    by_id = {r["entry_id"]: r for r in out["entries"]}
    # The scan discovered b (its matched keys are shown), but the
    # delay knob arms instead of firing in a one-tick preview.
    assert by_id["b"]["status"] == "not_triggered"
    assert by_id["b"]["matched_primary"] == ["beta"]
    assert by_id["b"]["via"] is None and by_id["b"]["depth"] is None


def test_preview_recursive_invalid_depth_raises():
    with pytest.raises(ValueError):
        preview_activation(
            preview_rows(), ["alpha rises"], 1, None, recursive_scan=True, max_recursion_depth=-1
        )


def test_preview_recursive_tight_budget_reports_exhaustion():
    out = preview_activation(preview_rows(), ["alpha rises"], 1, 1, recursive_scan=True)
    assert out["recursion_budget_exhausted"] is True
    rows = {r["entry_id"]: r for r in out["entries"]}
    # The direct hit is never silently untriggered: it is activated
    # and then honestly discarded by the budget/priority pass.
    assert rows["a"]["status"] == "discarded"
    assert rows["a"]["discard_reason"] == "over_budget"
    assert rows["b"]["status"] == "not_triggered"
