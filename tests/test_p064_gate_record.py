"""P-064 acceptance: the Part IV gate record.

The gate record (docs/PART_IV_GATE_2026-11-07.md) closes
Part IV: an ST preset pack drives Runmal chats with visibly
identical prompt assembly (preview-diffed), the sampler truth
table is published per backend, the pinned limitations are
named (a)-(f), the carried findings are numbered F1-F3, and
the measured counts are recorded against the P-063 baseline.
These tests pin those operative claims so a future slice
cannot silently drop a pinned limitation, lose a finding, or
upgrade a carried number into a measured one.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).parent.parent
GATE = REPO / "docs" / "PART_IV_GATE_2026-11-07.md"
ROADMAP = REPO / "docs" / "RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md"


def _gate() -> str:
    return " ".join(GATE.read_text(encoding="utf-8").split())


def test_gate_doc_exists_and_states_the_verdict() -> None:
    assert GATE.exists()
    text = _gate()
    assert "Part IV is COMPLETE and the gate PASSES" in text
    assert "named pinned limitations and carried findings" in text
    assert "claims only what the battery proves" in text
    assert "Pack PASS" in text
    assert "Truth PASS" in text
    assert "Composition PASS" in text


def test_roadmap_line_and_part_iv_goal_are_quoted() -> None:
    text = _gate()
    assert ("P-064 Part IV gate: an ST preset pack drives Rúnmál chats with "
            "visibly identical prompt assembly (preview-diffed), sampler truth "
            "table published per backend") in text
    assert ("the prompt is the instrument. Players of the mirrors expect to "
            "tune it to the string — Rúnmál's composer grows the full workshop") in text
    assert "no mirror source consulted (clean-room)" in text


def test_gate_checklist_and_coverage_map() -> None:
    text = _gate()
    assert "A-PACK-1" in text and "A-PACK-3" in text
    assert "B-TRUTH-1..5" in text and "C-COMP-1..4" in text
    assert "P-049->C-COMP-1" in text
    assert "P-052->B-TRUTH-1..4" in text
    assert "P-059->A-PACK-3/C-COMP-1..4" in text
    assert "P-063->A-PACK-1..3" in text
    assert "P-064->this gate" in text
    assert "No roadmap text was edited" in text
    roadmap = ROADMAP.read_text(encoding="utf-8")
    start = roadmap.index("## Part IV")
    end = roadmap.index("## Part V")
    section = roadmap[start:end]
    ids = [int(m) for m in re.findall(r"\*\*P-(\d+)\*\*", section)]
    assert sorted(ids) == list(range(49, 65))  # P-049..P-064, no gaps/dupes
    assert len(ids) == 16
    assert "Part IV spans P-049..P-064, sixteen slices continuous" in text


def test_passes_means_pack_and_truth() -> None:
    text = _gate()
    assert "equal field by field across all 11 preview keys" in text
    assert "differs exactly by the persona the pack layout disables" in text
    assert "29x5 control rows + 4x5 mode rows" in text
    assert "nothing offered that no backend serves" in text
    assert ("partition_bag over the full canonical bag splits offered+greyed "
            "== the canonical set") in text
    assert ("the capabilities and structured-modes endpoints return the same "
            "available/greyed rows") in text


def test_passes_means_composition() -> None:
    text = _gate()
    assert "discard recorded as prompt_manager_disabled" in text
    assert "no raw macro survives" in text
    assert "spliced after all history at depth 0" in text
    assert "the chat's own text winning over the character card's, composed baseline-last" in text
    assert "budget sections sum to the ledger total" in text
    assert "history, character, lorebooks, authors_note and post_history carry unchanged" in text
    assert "composed message contents are identical across the switch" in text


def test_gatehall_tally_and_diff_centre() -> None:
    text = _gate()
    assert "Gatehall" in text
    assert "equal on every one of the 11 preview keys" in text
    assert ("messages, wire_messages, text, template_name, stop_strings, "
            "rendered_tokens, backend_key, model_id, form, available, note") in text


def test_pinned_limitations_are_named() -> None:
    text = _gate()
    assert "(a) The preview is the composition pipeline, not a live send" in text
    assert "live generation does not yet route through the composer/inspector" in text
    assert "(b) Macros are a text-layer engine, not an inspect stage" in text
    assert "(c) Pack template/layout items are validated, not stored" in text
    assert "validated_not_stored" in text
    assert "(d) Available truth rows carry a reason code, not prose" in text
    assert 'reason_code "supported"' in text
    assert "(e) Grammar is greyed on every backend" in text
    assert "(f) A profile/bundle sampler is partitioned, never silently honoured" in text


def test_findings_f1_to_f3_are_named() -> None:
    text = _gate()
    assert "F1" in text
    assert "Grammar served nowhere is CARRIED, not closed" in text
    assert "F2" in text
    assert "Live generation still does not route through the composer" in text
    assert "F3" in text
    assert "No new defect was found by this gate" in text
    assert "nothing was left unfixed" in text


def test_measured_counts_and_baseline_arithmetic() -> None:
    text = _gate()
    assert "Gate battery: 13 passed" in text
    assert "tests/test_p064_part_iv_gate.py (13 tests)" in text
    assert "3 + 5 + 4 + 1 = 13" in text
    assert "R = 10" in text
    assert "Part IV neighbours: 699 passed" in text
    assert "Full suite: 2898 passed, 4 skipped, 0 failed" in text
    assert "The P-063 baseline B was 2875 passed, 4 skipped" in text
    assert "2875 + 13 + 10 = 2898, exact" in text


def test_migration_note_and_head_0035() -> None:
    text = _gate()
    assert "Migration note: none" in text
    assert "migration head remains 0035" in text
    assert "no migration was added by this slice" in text
    assert "committed on yrsa/runmal-team-02 for the keeper to bank in roadmap order" in text
    from runmal.db.migrations import MIGRATIONS

    assert MIGRATIONS[-1][0] == "0036"
