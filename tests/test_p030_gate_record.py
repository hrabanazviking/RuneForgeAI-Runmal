"""P-030 acceptance: the Part II gate record.

The gate record (docs/PART_II_GATE_2026-11-06.md) closes
Part II: the P-005 corpus round-trips clean under a
per-type contract, a stranger's library imports whole
with a report that reconciles exactly, the pinned losses
are named (a)-(d), the carried limitations are numbered
F1-F5, and the measured counts are recorded against the
P-029 baseline. These tests pin those operative claims so
a future slice cannot silently upgrade a mapped-only leg
to full, drop a pinned loss, or lose a finding.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).parent.parent
GATE = REPO / "docs" / "PART_II_GATE_2026-11-06.md"
ROADMAP = REPO / "docs" / "RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md"


def _gate() -> str:
    return " ".join(GATE.read_text(encoding="utf-8").split())


def test_gate_doc_exists_and_states_the_verdict() -> None:
    assert GATE.exists()
    text = _gate()
    assert "Part II is COMPLETE and the gate PASSES" in text
    assert "named pinned losses and carried limitations" in text
    assert "claims no fidelity the tests do not prove" in text


def test_roadmap_line_and_part_ii_goal_are_quoted() -> None:
    text = _gate()
    assert "P-030 Part II gate: the P-005 corpus round-trips clean" in text
    assert "a stranger's real library imports whole with an honest report" in text
    assert "Whatever the mirrors can hold, Rúnmál can receive, keep whole, and hand back" in text


def test_corpus_tally_by_type() -> None:
    text = _gate()
    assert "12/12 fixtures" in text
    assert "12 fixtures" in text
    assert "5 cards, 3 lorebooks, 2 presets, 1 chat, 1 persona" in text
    assert "No scenario fixture exists in the corpus" in text
    assert "the scenario leg is supplementary, authored in-module" in text


def test_clean_means_per_type() -> None:
    text = _gate()
    # Cards: full file leg, store leg full bar the v2 collapse.
    assert "normalised fields + unknowns equal" in text
    assert "byte fixed point on second export" in text
    assert 'spec_version collapses to "2" by construction' in text
    # Lorebooks: full file leg, mapped-only store leg.
    assert "file leg FULL" in text
    assert "23 world-info fields P-005 pinned as dropped" in text
    assert "survive as data in extra/raw carriage" in text
    assert "store leg MAPPED-ONLY" in text
    assert "dropped set pinned by name" in text
    # Presets: exact params bag, raw carriage, seed sentinel.
    assert "canonical params bag exact" in text
    assert "mirror-only keys in raw carriage only" in text
    assert "seed -1 sentinel restored" in text
    # Chat: clean file leg, pinned live-projection losses.
    assert "field_diff == []" in text
    assert "pinned exactly via loss_report" in text
    assert "6 items for the corpus chat" in text
    # Persona: file-model only, no store claimed.
    assert "file-model only" in text
    assert "No persona store exists yet" in text
    # Scenario: supplementary fixed points, verbatim carriage.
    assert "parse->export fixed points" in text
    assert "unmappable elements re-emitted verbatim" in text


def test_stranger_library_reconciles_exactly() -> None:
    text = _gate()
    assert "19 files submitted" in text
    assert "totals == compute_totals" in text
    assert "accepted+repaired+refused+skipped == submitted" in text
    assert "every non-accept is reason-coded" in text
    assert "6 characters / 3 lorebooks matching the report" in text
    assert "honestly refused unsupported_kind" in text
    assert "P-021 for presets, P-020 for chats, P-018 for personas" in text
    assert "redeemed whole via its home importer" in text
    assert "Scenario has NO bulk home" in text
    assert "export -> validate -> restore" in text
    assert "re-export checksum-stable" in text
    assert "authored fresh in the test module" in text
    assert "no real user files" in text


def test_pinned_losses_a_to_d_are_named() -> None:
    text = _gate()
    # (a) lorebook store: 23 fields dropped, position 4 collapses.
    assert "(a) Lorebook store loss" in text
    assert "drops the 23 world-info fields" in text
    assert "collapses position 4 (at_depth) to before_char" in text
    assert "Part III debt" in text
    # (b) chat live projection: swipes, extra, metadata, dates.
    assert "(b) Chat live projection loss" in text
    assert "alternate swipes beyond the active one" in text
    assert "chat_metadata and send_date fidelity" in text
    # (c) PNG export: synthesised carrier, art via the DB path.
    assert "(c) PNG carrier loss" in text
    assert "synthesised 1x1 carrier" in text
    assert "Original art survives only via the P-023 DB asset path" in text
    # (d) stored card shape: always v2 export text.
    assert "(d) Stored card shape" in text
    assert "Stored card_json is always v2 export text" in text


def test_findings_f1_to_f5_are_named() -> None:
    text = _gate()
    # F1: at-depth lorebooks cannot enter the DB store at all.
    assert "F1" in text
    assert "import_book_transactional raises ValueError" in text
    assert "VALID_POSITIONS rejects at_depth" in text
    assert "at-depth DB carriage is P-038's road" in text
    # F2: bulk classifier swallows one scenario spelling, refuses the other.
    assert "F2" in text
    assert "swallows a Voxta scenario" in text
    assert "accepted under the scenario's name" in text
    assert "refused unrecognized_content" in text
    # F3: chat home slice in reason text only; preset is structured.
    assert "F3" in text
    assert "names its home slice (P-020) in reason text only" in text
    assert "detected_shape/home_slice" in text
    assert "cosmetic asymmetry" in text
    # F4: stale manifest prose, manifest left untouched.
    assert "F4" in text
    assert "P-005 manifest prose is stale" in text
    assert "predate P-018/P-021" in text
    assert "manifest is left untouched" in text
    # F5: provenance is character-only; API path records nulls.
    assert "F5" in text
    assert "provenance is character-only" in text
    assert "carry no provenance record" in text
    assert "original_sha256/original_byte_length as null by design" in text


def test_measured_counts_and_baseline() -> None:
    text = _gate()
    assert "Gate battery: 45 passed" in text
    assert "tests/test_p030_part2_gate.py (29 tests)" in text
    assert "tests/test_p030_stranger_library.py (16 tests)" in text
    assert "Part II neighbours: 412 passed" in text
    assert "1233 passed, 4 skipped, 0 failed" in text
    assert "P-029 baseline was 1188 passed, 4 skipped" in text
    assert "gate adds exactly 45" in text


def test_migration_note() -> None:
    text = _gate()
    assert "Migration note: none" in text
    assert "migration head remains 0023" in text
    assert "no migration was added" in text


def test_roadmap_part_ii_spans_p015_to_p030() -> None:
    roadmap = ROADMAP.read_text(encoding="utf-8")
    start = roadmap.index("## Part II")
    end = roadmap.index("## Part III")
    section = roadmap[start:end]
    ids = [int(m) for m in re.findall(r"\*\*P-(\d+)\*\*", section)]
    assert sorted(ids) == list(range(15, 31))  # P-015..P-030, no gaps/dupes
    assert len(ids) == 16
    text = _gate()
    assert "Part II spans P-015 – P-030" in text
    assert "No roadmap text was edited by this gate" in text
    assert "branch yrsa/runmal-team-03" in text
