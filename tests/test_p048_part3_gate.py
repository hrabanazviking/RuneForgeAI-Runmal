"""P-048 Part III gate: the ST-shaped lore test pack (logic, recursion, timing) passes on Runmal's engine; inspector explains every firing.

Roadmap line: *P-048 Part III gate: the ST-shaped lore test pack
(logic, recursion, timing) passes on Runmal's engine; inspector
explains every firing.*

This module covers Areas A (logic) and B (recursion) of the gate.
The world below is fresh-authored for this test pack; no real user
files are read. Clean-room note: the scenarios are shaped from the
public selective-logic / inclusion-group / recursive-scan concepts
only; no SillyTavern or Voxta source was inspected.

Per-area "passes means" contracts:

- Area A (logic) passes means: the P-032 selective-logic gate's
  truth table holds at the pure-function level AND through the
  S202 scanner (hit sets row-for-row, mode echoed, matched
  secondary keys exact); P-034 inclusion groups resolve
  deterministically by (-group_weight, -priority, entry_id) at the
  resolver level AND in preview (winner included, losers
  ``group_excluded`` with the winner recorded); and P-035
  activation kinds dispatch honestly in preview -- constant fires
  with no keys, selective only on a key hit, vectorised only on a
  vector hit, the two hit kinds never cross, disabled entries stay
  ``disabled``.
- Area B (recursion) passes means: recursive scanning follows
  keyword links in fired entries' content breadth-first with
  honest depth / triggered_by attribution, respects
  ``max_recursion_depth`` (clamped to ``MAX_RECURSIVE_SCAN_DEPTH``
  == 5), terminates on cycles and self-reference with each entry
  firing at most once, and honours the token budget as an
  *expansion* bound -- round-0 (direct) hits are admitted
  unconditionally by design, so ``tokens_used`` may exceed a
  budget smaller than the round-0 cost alone; and the preview /
  activation legs surface recursion (``via="recursive"`` with
  scan depths) and ``{{lore:...}}`` reference expansion
  (``via="reference"``, cycles left literal).

Plain pytest functions, no test classes. Fixed seed 48048 wherever
a seed is needed.
"""

from __future__ import annotations

import json
import random
from types import SimpleNamespace

from runmal.lorebooks.activation import ActivatableEntry, activate
from runmal.lorebooks.groups import GroupCandidate, resolve_inclusion_groups
from runmal.lorebooks.logic import (
    secondary_gate,
    selective_logic_from_code,
    worldinfo_code,
)
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.scan import (
    MAX_RECURSIVE_SCAN_DEPTH,
    ScanEntry,
    scan_entries,
    scan_entries_recursive,
)
from runmal.lorebooks.states import activation_kind_for
from runmal.tokens import estimate_tokens

SEED = 48048
ALL_MODES = ("and_any", "and_all", "not_any", "not_all")

# ---------------------------------------------------------------- helpers


def e(eid, **kw):
    """ScanEntry helper in test_p032's style (defaults mirror the
    legacy scanner behaviour; kwargs pass straight through)."""
    base = dict(
        enabled=True,
        constant=False,
        keys=(),
        secondary_keys=(),
        whole_word=True,
        case_sensitive=False,
        content="",
    )
    base.update(kw)
    return ScanEntry(id=eid, **base)


def orm_entry(eid, name, content, keys=(), **kw):
    """ORM-shaped entry in test_p043's orm_entry style."""
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


def rows_by_id(preview):
    return {row["entry_id"]: row for row in preview["entries"]}


# ------------------------------------------------------- Area A: logic

# A-LOG-1: secondary_gate truth table + degenerate case + code round-trip.
# Rows are matched_count 0, 1, 2 at secondary_count=2.
GATE_TRUTH = {
    "and_any": (False, True, True),
    "and_all": (False, False, True),
    "not_any": (True, False, False),
    "not_all": (True, True, False),
}


def test_a_log_1_secondary_gate_truth_table():
    for mode in ALL_MODES:
        for matched, want in zip((0, 1, 2), GATE_TRUTH[mode]):
            got = secondary_gate(mode, secondary_count=2, matched_count=matched)
            assert got is want, (mode, matched, got, want)


def test_a_log_1_secondary_gate_degenerate_and_codes():
    # No usable secondary keys: the gate passes in every mode; the
    # primary match alone decides (the empty-secondary rule).
    for mode in ALL_MODES:
        assert secondary_gate(mode, secondary_count=0, matched_count=0) is True
    # World-info codes are file-format order, not prose order.
    assert worldinfo_code("and_any") == 0
    assert worldinfo_code("not_all") == 1
    assert worldinfo_code("not_any") == 2
    assert worldinfo_code("and_all") == 3
    for mode in ALL_MODES:
        assert selective_logic_from_code(worldinfo_code(mode)) == mode


# A-LOG-2: the same truth table through the scanner.
def _gate_entries():
    return [
        e(mode, keys=("gate",), secondary_keys=("iron", "oak"),
          selective_logic=mode)
        for mode in ALL_MODES
    ]


def test_a_log_2_scan_truth_table():
    entries = _gate_entries()
    # (messages, expected hit ids, expected matched_secondary per hit)
    cases = [
        (["the gate"], {"not_any", "not_all"},
         {"not_any": (), "not_all": ()}),
        (["gate iron"], {"and_any", "not_all"},
         {"and_any": ("iron",), "not_all": ("iron",)}),
        (["gate iron oak"], {"and_any", "and_all"},
         {"and_any": ("iron", "oak"), "and_all": ("iron", "oak")}),
        # No primary key anywhere: nothing fires, in any mode.
        (["iron oak"], set(), {}),
    ]
    for messages, want_ids, want_secondary in cases:
        hits = scan_entries(entries, messages, max(1, len(messages)))
        assert {h.entry_id for h in hits} == want_ids, messages
        for hit in hits:
            # The hit echoes its mode and the exact secondary matches.
            assert hit.selective_logic == hit.entry_id
            assert hit.matched_primary == ("gate",)
            assert tuple(hit.matched_secondary) == want_secondary[hit.entry_id]


# A-LOG-3: inclusion groups at the resolver level.
def _omen_candidates():
    return [
        GroupCandidate(entry_id="omens-low", inclusion_group="omens",
                       group_weight=100, priority=100),
        GroupCandidate(entry_id="omens-mid", inclusion_group="omens",
                       group_weight=200, priority=50),
        GroupCandidate(entry_id="omens-high", inclusion_group="omens",
                       group_weight=200, priority=100),
    ]


def test_a_log_3_resolve_inclusion_groups():
    res = resolve_inclusion_groups(_omen_candidates())
    # Rank rule -group_weight, -priority, entry_id: (200, 100) wins.
    assert res.winner_by_group == {"omens": "omens-high"}
    assert [c.entry_id for c in res.winners] == ["omens-high"]
    assert {row.entry_id for row in res.losers} == {"omens-low", "omens-mid"}
    own = {"omens-low": (100, 100), "omens-mid": (200, 50)}
    for loser in res.losers:
        assert loser.inclusion_group == "omens"
        assert loser.winner_id == "omens-high"
        assert loser.winner_group_weight == 200
        assert loser.winner_priority == 100
        assert loser.reason == "inclusion_group"
        assert (loser.group_weight, loser.priority) == own[loser.entry_id]
    # Shuffled candidate order resolves to the identical winner.
    rng = random.Random(SEED)
    for _ in range(6):
        shuffled = _omen_candidates()
        rng.shuffle(shuffled)
        again = resolve_inclusion_groups(shuffled)
        assert again.winner_by_group == {"omens": "omens-high"}
        assert {c.entry_id for c in again.winners} == {"omens-high"}
    # Ungrouped and single-member-group candidates are untouched,
    # and no winner is recorded for an uncontested group.
    mixed = resolve_inclusion_groups(
        _omen_candidates()
        + [GroupCandidate(entry_id="free-1"),
           GroupCandidate(entry_id="solo-1", inclusion_group="solo")]
    )
    assert {c.entry_id for c in mixed.winners} == {
        "omens-high", "free-1", "solo-1"}
    assert mixed.winner_by_group == {"omens": "omens-high"}


def _omen_orm_entries():
    return [
        orm_entry("omens-low", "Low Omen", "Low omen lore.", keys=("omen",),
                  inclusion_group="omens", group_weight=100, priority=100),
        orm_entry("omens-mid", "Mid Omen", "Mid omen lore.", keys=("omen",),
                  inclusion_group="omens", group_weight=200, priority=50),
        orm_entry("omens-high", "High Omen", "High omen lore.", keys=("omen",),
                  inclusion_group="omens", group_weight=200, priority=100),
        orm_entry("free-1", "Free", "Free lore.", keys=("omen",)),
        orm_entry("solo-1", "Solo", "Solo lore.", keys=("omen",),
                  inclusion_group="solo"),
    ]


def test_a_log_3_preview_inclusion_groups():
    preview = preview_activation(
        _omen_orm_entries(), ["an omen appears"], 4, None, seed=SEED)
    rows = rows_by_id(preview)
    assert rows["omens-high"]["status"] == "included"
    for loser_id in ("omens-low", "omens-mid"):
        row = rows[loser_id]
        assert row["status"] == "group_excluded"
        assert row["group_winner_id"] == "omens-high"
        assert row["discard_reason"] is None
    assert rows["free-1"]["status"] == "included"
    assert rows["solo-1"]["status"] == "included"
    assert preview["inclusion_group_winners"] == {"omens": "omens-high"}
    # A repeated identical preview call gives the identical winner.
    again = preview_activation(
        _omen_orm_entries(), ["an omen appears"], 4, None, seed=SEED)
    assert again["inclusion_group_winners"] == {"omens": "omens-high"}
    assert rows_by_id(again)["omens-high"]["status"] == "included"
    # Shuffled entry order gives the identical winner too.
    shuffled = _omen_orm_entries()
    random.Random(SEED).shuffle(shuffled)
    mixed = preview_activation(shuffled, ["an omen appears"], 4, None, seed=SEED)
    assert mixed["inclusion_group_winners"] == {"omens": "omens-high"}
    assert rows_by_id(mixed)["omens-high"]["status"] == "included"


# A-LOG-4: activation kinds dispatch honestly, hit kinds never cross.
def _state_world():
    return [
        orm_entry("C", "Constant", "Constant lore.", constant=True),
        orm_entry("C-off", "Constant Off", "Disabled lore.",
                  enabled=False, constant=True),
        orm_entry("S", "Selective", "Selective lore.", keys=("sigil",)),
        orm_entry("V", "Vector", "Vector lore.", keys=("beacon",),
                  vectorised=True),
    ]


def test_a_log_4_activation_kinds():
    # The pure derivation, including constant > vectorised precedence.
    assert activation_kind_for(constant=True, vectorised=False) == "constant"
    assert activation_kind_for(constant=True, vectorised=True) == "constant"
    assert activation_kind_for(constant=False, vectorised=True) == "vectorised"
    assert activation_kind_for(constant=False, vectorised=False) == "selective"

    # Tick 1: messages match nothing.
    tick1 = preview_activation(
        _state_world(), ["a quiet road"], 4, None, seed=SEED)
    rows = rows_by_id(tick1)
    assert rows["C"]["status"] == "included"
    assert rows["C"]["via"] == "constant"
    assert rows["C"]["activation_kind"] == "constant"
    assert rows["S"]["status"] == "not_triggered"
    assert rows["S"]["activation_kind"] == "selective"
    assert rows["V"]["status"] == "not_triggered"
    assert rows["V"]["activation_kind"] == "vectorised"
    assert rows["C-off"]["status"] == "disabled"

    # Tick 2: S's key present; V supplied as a vector hit.
    tick2 = preview_activation(
        _state_world(), ["the sigil glows"], 4, None, seed=SEED,
        vector_hit_ids={"V"})
    rows = rows_by_id(tick2)
    assert rows["S"]["status"] == "included"
    assert rows["S"]["via"] == "key"
    assert rows["V"]["status"] == "included"
    assert rows["V"]["via"] == "vector"
    # A vector-fired row honestly reports no keyword matches.
    assert rows["V"]["matched_primary"] == []
    assert rows["C-off"]["status"] == "disabled"

    # Tick 3: S given only a claimed vector hit, V only a keyword
    # hit (not in vector_hit_ids, no embedder): neither fires --
    # hit kinds never cross (vector_fallback is tested elsewhere).
    tick3 = preview_activation(
        _state_world(), ["a beacon shines"], 4, None, seed=SEED,
        vector_hit_ids={"S"})
    rows = rows_by_id(tick3)
    assert rows["S"]["status"] == "not_triggered"
    assert rows["V"]["status"] == "not_triggered"
    assert rows["C"]["status"] == "included"
    assert rows["C-off"]["status"] == "disabled"


# ---------------------------------------------------- Area B: recursion

def _chain():
    return [
        e("A", keys=("ember",), content="the ash rises"),
        e("B", keys=("ash",), content="a phoenix returns"),
        e("C", keys=("phoenix",), content="quiet leaf lore"),
    ]


def test_b_rec_1_chain_depths_and_attribution():
    res = scan_entries_recursive(_chain(), ["an ember glows"], 4)
    by_id = {h.entry_id: h for h in res.hits}
    assert set(by_id) == {"A", "B", "C"}
    assert len(res.hits) == 3  # each id exactly once
    assert by_id["A"].depth == 0 and by_id["A"].triggered_by is None
    assert by_id["B"].depth == 1 and by_id["B"].triggered_by == "A"
    assert by_id["C"].depth == 2 and by_id["C"].triggered_by == "B"
    assert res.depth_reached == 2
    assert res.budget_exhausted is False


def test_b_rec_2_max_recursion_depth_and_clamp():
    chain = _chain()
    res1 = scan_entries_recursive(chain, ["an ember glows"], 4,
                                  max_recursion_depth=1)
    assert {h.entry_id for h in res1.hits} == {"A", "B"}
    assert res1.depth_reached == 1
    res0 = scan_entries_recursive(chain, ["an ember glows"], 4,
                                  max_recursion_depth=0)
    assert {h.entry_id for h in res0.hits} == {"A"}
    assert res0.depth_reached == 0
    # 99 clamps to the hard cap: a 7-link chain stops at depth 5.
    assert MAX_RECURSIVE_SCAN_DEPTH == 5
    links = [
        e(f"L{i}", keys=(f"link{i}",),
          content=(f"link{i + 1} follows" if i < 6 else "the end"))
        for i in range(7)
    ]
    res99 = scan_entries_recursive(links, ["link0 begins"], 4,
                                   max_recursion_depth=99)
    assert {h.entry_id for h in res99.hits} == {f"L{i}" for i in range(6)}
    assert res99.depth_reached == 5


def test_b_rec_3_cycle_safety():
    entries = [
        e("cyc-a", keys=("alpha",), content="beta wakes"),
        e("cyc-b", keys=("beta",), content="alpha sleeps"),
        e("self-d", keys=("solo",), content="solo again solo"),
    ]
    res = scan_entries_recursive(entries, ["alpha and solo"], 4)
    by_id = {h.entry_id: h for h in res.hits}
    assert set(by_id) == {"cyc-a", "cyc-b", "self-d"}
    assert len(res.hits) == 3  # cycles/self-reference fire at most once
    assert by_id["cyc-a"].depth == 0
    assert by_id["cyc-b"].depth == 1
    assert by_id["cyc-b"].triggered_by == "cyc-a"
    assert by_id["self-d"].depth == 0


def test_b_rec_4_token_budget_bounds_expansion():
    entries = _chain()
    by_entry = {entry.id: entry for entry in entries}
    cost_a = estimate_tokens(by_entry["A"].content)
    cost_b = estimate_tokens(by_entry["B"].content)
    assert cost_a > 1  # the sub-budget case below needs this
    # Budget exactly A's cost: A admitted, expansion stopped.
    exact = scan_entries_recursive(entries, ["an ember glows"], 4,
                                   token_budget=cost_a)
    assert {h.entry_id for h in exact.hits} == {"A"}
    assert exact.budget_exhausted is True
    assert exact.tokens_used == cost_a
    # Budget admitting A + B but not C.
    two = scan_entries_recursive(entries, ["an ember glows"], 4,
                                 token_budget=cost_a + cost_b)
    assert {h.entry_id for h in two.hits} == {"A", "B"}
    assert two.budget_exhausted is True
    assert two.tokens_used == cost_a + cost_b
    # Honest pin: round-0 admission is unconditional by design, so
    # a budget smaller than A's own cost still admits A and
    # tokens_used exceeds the budget (never assert the reverse).
    tiny = scan_entries_recursive(entries, ["an ember glows"], 4,
                                  token_budget=1)
    assert {h.entry_id for h in tiny.hits} == {"A"}
    assert tiny.budget_exhausted is True
    assert tiny.tokens_used == cost_a > 1


def test_b_rec_5_preview_recursive_leg():
    entries = [
        orm_entry("A", "Ember", "the ash rises", keys=("ember",)),
        orm_entry("B", "Ash", "a phoenix returns", keys=("ash",)),
        orm_entry("C", "Phoenix", "quiet leaf lore", keys=("phoenix",)),
    ]
    preview = preview_activation(
        entries, ["an ember glows"], 4, None, seed=SEED, recursive_scan=True)
    rows = rows_by_id(preview)
    assert rows["A"]["status"] == "included"
    assert rows["A"]["via"] == "key"
    assert rows["B"]["status"] == "included"
    assert rows["B"]["via"] == "recursive"
    assert rows["B"]["depth"] == 1
    assert rows["C"]["status"] == "included"
    assert rows["C"]["via"] == "recursive"
    assert rows["C"]["depth"] == 2
    assert preview["recursive_scan"] is True
    assert preview["recursion_depth_reached"] == 2


def test_b_rec_5_reference_expansion_and_cycle():
    x = ActivatableEntry(id="X", name="X", content="Before {{lore:Y}} after")
    y = ActivatableEntry(id="Y", name="Y", content="inner lore")
    result = activate([x, y], {"X"})
    acts = {a.entry_id: a for a in result.activations}
    # Y's content is spliced into X's resolved content.
    assert acts["X"].content == "Before inner lore after"
    assert acts["Y"].via == "reference"
    assert acts["Y"].depth == 1
    # A cyclic reference pair terminates with the unexpandable
    # reference left as literal text.
    lx = ActivatableEntry(id="LX", name="LoopX",
                          content="start {{lore:LoopY}} end")
    ly = ActivatableEntry(id="LY", name="LoopY",
                          content="loop {{lore:LoopX}} back")
    cyclic = activate([lx, ly], {"LX"})
    cacts = {a.entry_id: a for a in cyclic.activations}
    assert "{{lore:" in cacts["LX"].content
    assert cacts["LY"].via == "reference"
