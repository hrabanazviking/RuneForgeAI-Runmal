"""P-186 acceptance: the Part XI gate record.

The gate record (docs/PART_XI_GATE_2026-11-09.md)
closes Part XI: every P-169..P-185 workspace surface
present and working together, the gate standing on the
P-185 reconciliation battery in its base (never
duplicating it silently), the custody and fence laws
whole, the carried items K1-K6 named, and the measured
counts recorded against the banked baseline. These
tests pin those operative claims so a future slice
cannot silently drop a carried item or upgrade a
carried number into a measured one.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).parent.parent
GATE = REPO / "docs" / "PART_XI_GATE_2026-11-09.md"


def _gate() -> str:
    return " ".join(GATE.read_text(encoding="utf-8").split())


def test_gate_doc_exists_and_states_the_verdict() -> None:
    assert GATE.exists()
    text = _gate()
    assert "Part XI is COMPLETE and the gate PASSES" in text
    assert "named carried items and two findings" in text
    assert "claims only what the battery proves" in text
    assert "Census PASS" in text
    assert "Together PASS" in text
    assert "Custody PASS" in text
    assert "Accounting PASS" in text


def test_part_line_derived_scope_and_p185_relation() -> None:
    text = _gate()
    assert "XI | Workspaces - the Companion That Works | P-169 - P-186" in text
    assert "every Part XI slice scope is DERIVED" in text
    assert "no mirror source consulted (clean-room)" in text
    assert "the gate stands on it, never duplicates it silently" in text
    assert "its 24 tests run beside this gate's battery as neighbours" in text
    assert "ZqxGate186, query \"copper\"" in text


def test_gate_checklist_and_coverage_map() -> None:
    text = _gate()
    assert "P-169->A/B/C" in text
    assert "P-179->D" in text
    assert "P-185->A (stood on, run as neighbour)" in text
    assert "P-186->this gate" in text
    assert "No roadmap text was edited" in text
    assert "Part XI spans P-169..P-186, eighteen slices continuous" in text


def test_verdict_rows_cover_every_slice() -> None:
    text = _gate()
    for row in ("Workspace binding foundation",
                "Workspace folder listing",
                "Workspace census",
                "Workspace file content read",
                "Workspace binding history",
                "Workspace folder census",
                "Workspace history deletion",
                "Workspace folder tree",
                "Workspace history census",
                "Workspace filename search",
                "Workspace tree truncated fix",
                "Workspace content search",
                "Workspace tree census",
                "Workspace unified search",
                "Workspace content census",
                "Workspace unified search census",
                "Workspace reconciliation battery"):
        assert row in text, row


def test_passes_means_together() -> None:
    text = _gate()
    assert "the estate census reconciles with P-169's owner list" in text
    assert "the unified search is exactly the union of the filename" in text
    assert "the deleted binding gone from the live estate" in text


def test_passes_means_custody() -> None:
    text = _gate()
    assert "every resolve is a pure read" in text
    assert "a secret string readable through P-172 is absent from all five" in text
    assert "writes inside bound folders stay fenced behind the VX-57 guard" in text
    assert "execution is declined ABSOLUTELY (VX-55/56, P-027" in text
    assert "watching stays declined (P-169" in text


def test_carried_items_are_named() -> None:
    text = _gate()
    assert "K1 - A binding label update stays named open" in text
    assert "unbind-then-bind, never a silent in-place update" in text
    assert "K2 - Automatic retention / bulk clear of history awaits Volmarr's ruling" in text
    assert "K3 - A unified-search history stays named open" in text
    assert "presupposes a recording write and a store" in text
    assert "K4 - Writes inside bound folders stay fenced" in text
    assert "K5 - Execution is declined ABSOLUTELY" in text
    assert "K6 - Watching stays declined" in text


def test_findings_are_named() -> None:
    text = _gate()
    assert "F1 - No new engine defect was found by this gate" in text
    assert "Nothing was left unfixed in this slice's own files" in text
    assert "9 sync + 15 async" in text
    assert "F2 - One contention flake in the first full-suite" in text
    assert "24 passed" in text


def test_migration_note_and_head_0041() -> None:
    text = _gate()
    assert "Migration note: none" in text
    assert "migration head remains 0041" in text
    assert "no migration was added by this slice" in text
    assert ("committed on yrsa/runmal-team-03 for the keeper "
            "to bank in roadmap order") in text
    from runmal.db.migrations import MIGRATIONS
    assert MIGRATIONS[-1][0] == "0041"


def test_measured_counts_are_recorded() -> None:
    text = _gate()
    assert "Gate battery: 25 passed, 0 skipped" in text
    assert "tests/test_p186_part_xi_gate.py (25 tests)" in text
    assert "8 + 7 + 5 + 3 + 2 = 25" in text
    assert "tests/test_p186_gate_record.py" in text
    assert "R = 10" in text
    assert "Neighbours batch as run by the tester: 272 passed" in text
    assert "Full suite: 5614 passed, 5 skipped, 0 failed in" in text
    assert "5579 + 25 + 10 = 5614" in text
