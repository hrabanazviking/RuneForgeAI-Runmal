"""P-048 acceptance: the Part III gate record.

The gate record (docs/PART_III_GATE_2026-11-06.md) closes
Part III: the ST-shaped lore test pack (logic, recursion,
timing) passes on Rúnmál's engine, the inspector explains
every firing, the pinned limitations are named (a)-(f),
the carried findings are numbered F1-F4, and the measured
counts are recorded against the P-047 baseline. These
tests pin those operative claims so a future slice cannot
silently drop a pinned limitation, lose a finding, or
upgrade a carried number into a measured one.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).parent.parent
GATE = REPO / "docs" / "PART_III_GATE_2026-11-06.md"
ROADMAP = REPO / "docs" / "RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md"


def _gate() -> str:
    return " ".join(GATE.read_text(encoding="utf-8").split())


def test_gate_doc_exists_and_states_the_verdict() -> None:
    assert GATE.exists()
    text = _gate()
    assert "Part III is COMPLETE and the gate PASSES" in text
    assert "named pinned limitations and carried findings" in text
    assert "claims only what the battery proves" in text
    assert "Logic PASS" in text
    assert "Recursion PASS" in text
    assert "Timing PASS" in text
    assert "Inspector PASS" in text


def test_roadmap_line_and_part_iii_goal_are_quoted() -> None:
    text = _gate()
    assert "P-048 Part III gate: the ST-shaped lore test pack (logic, recursion, timing) passes on Rúnmál's engine; inspector explains every firing" in text
    assert "world info at the mirrors' full strength — the quiet engine that makes long worlds stay true" in text
    assert "no mirror source consulted (clean-room)" in text


def test_gate_checklist_and_coverage_map() -> None:
    text = _gate()
    assert "A-LOG-1" in text and "B-REC-1" in text
    assert "C-TIM-1" in text and "X-INS-1" in text
    assert "P-031→B-REC-1..5" in text
    assert "P-032→A-LOG-1/2" in text
    assert "P-033→C-TIM-1..4" in text
    assert "P-046→X-PERF-1 + carried bench evidence" in text
    assert "P-047→X-MIG-1" in text
    assert "P-048→this gate" in text
    assert "No roadmap text was edited" in text
    roadmap = ROADMAP.read_text(encoding="utf-8")
    start = roadmap.index("## Part III")
    end = roadmap.index("## Part IV")
    section = roadmap[start:end]
    ids = [int(m) for m in re.findall(r"\*\*P-(\d+)\*\*", section)]
    assert sorted(ids) == list(range(31, 49))  # P-031..P-048, no gaps/dupes
    assert len(ids) == 18
    assert "Part III spans P-031..P-048, eighteen slices continuous" in text


def test_passes_means_logic_recursion_timing() -> None:
    text = _gate()
    assert "truth table is exact at the core AND at the scanner" in text
    assert "-group_weight,-priority,entry_id" in text
    assert "hit kinds never cross except the labelled vector_fallback" in text
    assert "Chains carry depth + triggered_by" in text
    assert "MAX_RECURSIVE_SCAN_DEPTH=5" in text
    assert "Cycles terminate via the seen-set" in text
    assert "4-turn sticky/cooldown/delay life table" in text
    assert "Preview ticks copies, caller state unmutated" in text
    assert "absence of a row IS the default state" in text


def test_passes_means_inspector_and_cross_cutting() -> None:
    text = _gate()
    assert "Every firing is explained with a concrete reason code" in text
    assert "facts_not_recorded is carried verbatim" in text
    assert "Placement is asserted in the composed prompt" in text
    assert "Scopes are FOUR layers (global, character, persona, chat)" in text
    assert "persona between character and chat" in text
    assert "with an explicit counter the account recounts exactly while preview rows keep budget-pass estimates" in text
    assert "Seeded rolls are reproducible and context-bound" in text
    assert "seeded: False" in text


def test_gateworld_tally_reconciles() -> None:
    text = _gate()
    assert "Gateworld tally: 18 entries in the inspector sweep: 8 included / 7 not_triggered / 2 group_excluded / 1 disabled" in text
    assert "included+discarded+not_triggered+group_excluded+disabled == entries" in text
    assert "8 included + 0 discarded + 7 not_triggered + 2 group_excluded + 1 disabled == 18 entries" in text
    assert "firings explained == firings" in text


def test_pinned_limitations_are_named() -> None:
    text = _gate()
    assert "(a) Inspector FACTS_NOT_RECORDED, carried verbatim" in text
    assert "probability rolls exist only for gated entries (probability < 100); ungated entries make no roll by design (P-036)" in text
    assert "scope_over_budget outcomes are produced by the P-040 layered pass" in text
    assert "(b) Round-0 recursion admission is unconditional" in text
    assert "Budget flags, never blocks, the first round" in text
    assert "(c) Unseeded probability rolls are system-entropy" in text
    assert "(d) P-046's performance numbers are laptop measurements" in text
    assert "x4.0 Pi derating, never Pi measurements" in text
    assert "(e) X-PLC-1 composer ordering as built" in text
    assert "Persona precedes lore_before in the baseline order" in text
    assert "at_depth distance is measured from the end of the chat history" in text
    assert "(f) Timing effect vocabulary as built" in text
    assert '"sticky_carryover"' in text
    assert '"fired"' in text
    assert "decrements with effect None" in text


def test_findings_f1_to_f4_are_named() -> None:
    text = _gate()
    assert "F1" in text
    assert "vector cache is in-process only" in text
    assert "Pi 4" in text
    assert "direct Pi 4 run of the 10,000-entry bench is still owed" in text
    assert "F2" in text
    assert "binding.normalise_book_entry drops depth/role" in text
    assert "normalise_book_entry" in text
    assert "NOT fixed here, NOT part of this gate" in text
    assert "F3" in text
    assert "P-019's interop preservation is file-layer only" in text
    assert "F4" in text
    assert "P-030 finding F1 (at_depth placement) is CLOSED here" in text
    assert "composed-prompt + DB round-trip proof" in text


def test_measured_counts_and_baseline_arithmetic() -> None:
    text = _gate()
    assert "Gate battery: 32 passed" in text
    assert "tests/test_p048_part3_gate.py (12 tests)" in text
    assert "tests/test_p048_timing_leg.py (4 tests)" in text
    assert "tests/test_p048_inspector_leg.py (16 tests)" in text
    assert "12 + 4 + 16 = 32" in text
    assert "R = 10" in text
    assert "Part III neighbours: 906 passed" in text
    assert "Full suite: 2199 passed, 4 skipped, 0 failed" in text
    assert "P-047 baseline B was 2157 passed, 4 skipped" in text
    assert "2157 + 32 + 10 = 2199, exact" in text
    assert "BUDGET-P046" in text
    assert "310.1 ms laptop, 1241 ms Pi-equivalent" in text
    assert "keyword scan 14.3 ms laptop, 57 ms Pi-equivalent" in text
    assert "labelled carried, not re-measured" in text


def test_migration_note_and_head_0032() -> None:
    text = _gate()
    assert "Migration note: none" in text
    assert "migration head remains 0032" in text
    assert "no migration was added by this slice" in text
    assert "committed on yrsa/runmal-team-03 for the keeper to bank in roadmap order" in text
    from runmal.db.migrations import MIGRATIONS

    assert MIGRATIONS[-1][0] == "0039"  # head moved by P-065 (PROVISIONAL 0036)
