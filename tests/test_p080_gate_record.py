"""P-080 acceptance: the Part V gate record.

The gate record (docs/PART_V_GATE_2026-11-07.md) closes
Part V: a surgery drill script (branch, checkpoint,
swipe-storm, group scene) runs green, no operation loses
data under the account discipline, the pinned limitations
are named (a)-(g), the carried findings are numbered
F1-F2, and the measured counts are recorded against the
merged baseline. These tests pin those operative claims
so a future slice cannot silently drop a pinned
limitation, lose a finding, or upgrade a carried number
into a measured one.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).parent.parent
GATE = REPO / "docs" / "PART_V_GATE_2026-11-07.md"
ROADMAP = REPO / "docs" / "RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md"


def _gate() -> str:
    return " ".join(GATE.read_text(encoding="utf-8").split())


def test_gate_doc_exists_and_states_the_verdict() -> None:
    assert GATE.exists()
    text = _gate()
    assert "Part V is COMPLETE and the gate PASSES" in text
    assert "named pinned limitations and carried findings" in text
    assert "claims only what the battery proves" in text
    assert "Drill PASS" in text
    assert "Accounting PASS" in text
    assert "Citizens PASS" in text


def test_roadmap_line_and_part_v_goal_are_quoted() -> None:
    text = _gate()
    assert ("P-080 Part V gate: a surgery drill script (branch, checkpoint, "
            "swipe-storm, group scene) runs green; no operation loses data") in text
    assert "the conversation as a malleable document" in text
    assert "no mirror source consulted (clean-room)" in text


def test_gate_checklist_and_coverage_map() -> None:
    text = _gate()
    assert "scripts/drill_p080_surgery.py (10 steps, exit 0)" in text
    assert "P-065->A/J" in text
    assert "P-070->E" in text
    assert "P-076->F" in text
    assert "P-079->I" in text
    assert "P-080->this gate" in text
    assert "No roadmap text was edited" in text
    roadmap = ROADMAP.read_text(encoding="utf-8")
    section = roadmap[roadmap.index("## Part V"):roadmap.index("## Part VI")]
    ids = [int(m) for m in re.findall(r"\*\*P-(\d+)\*\*", section)]
    assert sorted(ids) == list(range(65, 81))
    assert len(ids) == 16
    assert "Part V spans P-065..P-080, sixteen slices continuous" in text


def test_passes_means_drill_and_accounting() -> None:
    text = _gate()
    assert "content == deck[swipe_id] at every stop" in text
    assert "the replaced text stays as a variant" in text
    assert "a fork's prefix decks equal the source decks exactly" in text
    assert "merge-back holds the target's full history plus the branch's divergent suffix" in text
    assert "reproduces the checkpoint-time account exactly in a NEW chat" in text
    assert "undo after delete (and after edit, and after append) restores the prior account exactly" in text
    assert "a quiet chat starts empty, and undoing a seed-into-empty returns the chat to empty" in text


def test_passes_means_citizens() -> None:
    text = _gate()
    assert "persisted cursor A,B,A" in text
    assert "equal canonical hash" in text
    assert "single named exception of finding F1" in text


def test_surgeryhall_and_union_centre() -> None:
    text = _gate()
    assert "Surgeryhall" in text
    assert "every seed string still exists somewhere" in text
    assert "{source, branch, merged, restored}" in text


def test_pinned_limitations_are_named() -> None:
    text = _gate()
    assert "(a) Fork and merge copies carry the FULL deck" in text
    assert "(b) Delete is intentional loss, exactly scoped" in text
    assert "(c) The undo journal is bounded: MAX_ENTRIES = 50 per chat" in text
    assert "(d) Undo covers a named operation set, not everything" in text
    assert "(e) Checkpoints live outside the database" in text
    assert "(f) The group scene is a transcript + activation claim" in text
    assert "(g) Gate scales are drill scales" in text


def test_findings_f1_and_f2_are_named() -> None:
    text = _gate()
    assert "F1 - P-079's fork pin contradicts the banked P-078 contract; heal at P-079 banking" in text
    assert "49 passed / 1 failed" in text
    assert "The governing contract is P-078's" in text
    assert "F2 - No new engine defect was found by this gate" in text
    assert "Nothing was left unfixed in this slice's own files" in text


def test_measured_counts_and_baseline_arithmetic() -> None:
    text = _gate()
    assert "Gate battery: 15 passed" in text
    assert "tests/test_p080_part_v_gate.py (15 tests)" in text
    assert "2 + 2 + 1 + 1 + 2 + 1 + 1 + 3 + 1 + 1 = 15" in text
    assert "R = 10" in text
    assert "Neighbours batch as run by the tester: 567 passed, 1 failed" in text
    assert "Full suite: 3401 passed, 1 failed (F1 only), 4 skipped" in text
    assert "3386 passed, 1 failed (F1), 4 skipped" in text
    assert "B = 3387 passed, 4 skipped" in text
    assert "3388 passed / 4 skipped / 0 failed" in text
    assert "3388 + 25 = 3413 passed, 4 skipped, 0 failed" in text
    assert "F1 was healed at P-079 banking" in text
    assert "full suite == B + 15 + R, exact" in text


def test_migration_note_and_head_0041() -> None:
    text = _gate()
    assert "Migration note: none" in text
    assert "migration head remains 0041" in text
    assert "no migration was added by this slice" in text
    assert "committed on yrsa/runmal-team-03 for the keeper to bank in roadmap order" in text
    from runmal.db.migrations import MIGRATIONS

    assert MIGRATIONS[-1][0] == "0041"
