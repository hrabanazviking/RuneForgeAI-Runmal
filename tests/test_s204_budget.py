"""S204 acceptance: budget + priority resolution.

Over-budget fixtures must resolve identically under fixed state/seed:
priority order wins, equal priorities tie-break deterministically,
probability gates are seed-reproducible.
"""

import pytest

from runmal.lorebooks.budget import (
    BudgetCandidate,
    estimate_tokens,
    resolve_budget,
)


def c(eid, content="x" * 100, priority=100, probability=1.0):
    return BudgetCandidate(entry_id=eid, content=content,
                           priority=priority, probability=probability)


def ids(result):
    return [e.entry_id for e in result.included]


def test_priority_order_wins_when_tight():
    # "x"*100 -> 25 tokens each; budget 30 fits only the top priority.
    cands = [c("low", priority=10), c("high", priority=200)]
    r = resolve_budget(cands, 30, seed=1)
    assert ids(r) == ["high"]
    assert r.tokens_used == 25
    assert r.discarded[0].reason == "over_budget"


def test_greedy_packs_smaller_later_candidates():
    cands = [
        c("big", content="x" * 400, priority=300),   # 100 tokens
        c("small1", content="x" * 40, priority=200),  # 10 tokens
        c("small2", content="x" * 40, priority=100),  # 10 tokens
    ]
    r = resolve_budget(cands, 99, seed=1)
    assert ids(r) == ["small1", "small2"]
    assert r.tokens_used == 20
    assert r.discarded[0].entry_id == "big"


def test_equal_priority_tie_break_is_deterministic():
    cands = [c("b"), c("a"), c("c")]
    r1 = resolve_budget(cands, 25, seed=7)
    r2 = resolve_budget(cands, 25, seed=7)
    assert ids(r1) == ids(r2) == ["a"]  # id-ascending wins the tie
    # full-budget run keeps input-independent stable order too
    r3 = resolve_budget(cands, 1000, seed=7)
    assert ids(r3) == ["a", "b", "c"]


def test_probability_zero_always_skipped():
    cands = [c("a", probability=0.0), c("b", probability=1.0)]
    r = resolve_budget(cands, 1000, seed=42)
    assert ids(r) == ["b"]
    assert r.discarded[0].reason == "probability_skip"


def test_seeded_probability_reproducible():
    cands = [c(f"e{i}", probability=0.5) for i in range(20)]
    r1 = resolve_budget(cands, 10000, seed=1234)
    r2 = resolve_budget(cands, 10000, seed=1234)
    assert ids(r1) == ids(r2)
    # and the seed actually gates something (not all in, not all out)
    assert 0 < len(r1.included) < 20


def test_unseeded_probability_still_runs():
    cands = [c("a", probability=0.5)]
    r = resolve_budget(cands, 1000)  # seed=None: caller's choice
    assert len(r.included) + len(r.discarded) == 1


def test_unlimited_budget_includes_all():
    cands = [c("a"), c("b", priority=1)]
    r = resolve_budget(cands, None, seed=1)
    assert ids(r) == ["a", "b"]
    assert r.tokens_used == 50


def test_invalid_budget_rejected():
    with pytest.raises(ValueError):
        resolve_budget([c("a")], 0)
    with pytest.raises(ValueError):
        resolve_budget([c("a")], -5)


def test_invalid_probability_rejected():
    with pytest.raises(ValueError):
        c("a", probability=1.5)
    with pytest.raises(ValueError):
        c("a", probability=-0.1)


def test_estimate_tokens_sanity():
    assert estimate_tokens("") == 1
    assert estimate_tokens("x" * 4) == 1
    assert estimate_tokens("x" * 100) == 25
    assert estimate_tokens("hello world") == 2  # 11 chars // 4


def test_empty_candidates():
    r = resolve_budget([], 100, seed=1)
    assert r.included == () and r.discarded == () and r.tokens_used == 0
