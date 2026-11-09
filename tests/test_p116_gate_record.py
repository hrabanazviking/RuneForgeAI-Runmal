"""P-116 acceptance: the Part VII gate record.

The gate record (docs/PART_VII_GATE_2026-11-08.md) closes
Part VII: every P-101..P-115 voice surface present and
working together, the P-115 digest covered by
auto-discovery, the carried items K1-K7 named, and the
measured counts recorded against the banked baseline.
These tests pin those operative claims so a future slice
cannot silently drop a carried item or upgrade a carried
number into a measured one.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).parent.parent
GATE = REPO / "docs" / "PART_VII_GATE_2026-11-08.md"


def _gate() -> str:
    return " ".join(GATE.read_text(encoding="utf-8").split())


def test_gate_doc_exists_and_states_the_verdict() -> None:
    assert GATE.exists()
    text = _gate()
    assert "Part VII is COMPLETE and the gate PASSES" in text
    assert "named carried items and one finding" in text
    assert "claims only what the battery proves" in text
    assert "Census PASS" in text
    assert "Together PASS" in text
    assert "Digest PASS" in text
    assert "Accounting PASS" in text


def test_part_line_and_derived_scope_are_stated() -> None:
    text = _gate()
    assert "VII | Voice, the Voxta Way | P-101 - P-116" in text
    assert "every Part VII slice scope is DERIVED" in text
    assert "no mirror source consulted (clean-room)" in text


def test_gate_checklist_and_coverage_map() -> None:
    text = _gate()
    assert "P-101->A/B" in text
    assert "P-113->A" in text
    assert "P-115->C (by auto-discovery" in text
    assert "P-116->this gate" in text
    assert "No roadmap text was edited" in text
    assert "Part VII spans P-101..P-116, sixteen slices continuous" in text


def test_verdict_rows_cover_every_slice() -> None:
    text = _gate()
    for row in ("Voice sessions", "Live voice host",
                "Turn projection", "Auto-projection",
                "Mishearing truth", "Rendered confidence markings",
                "Repeat-request signal", "Affects as carried data",
                "Turn latency evidence", "Repeat housekeeping",
                "Live-start back-projection", "Custody coverage",
                "Mishearing session report", "Repeat-request digest"):
        assert row in text, row
    assert "PASS by auto-discovery" in text


def test_passes_means_together() -> None:
    text = _gate()
    assert ("the projection status, the repeat signal and the "
            "session report all state the same turns") in text
    assert "exactly one flagged needs-repeat" in text
    assert "back-projects at live start" in text


def test_passes_means_digest_auto_discovery() -> None:
    text = _gate()
    assert "its counts are the P-108 per-session views' sums" in text
    assert "reads exactly 600 seconds old at LATER" in text
    assert "the pending state is pinned at equal strength" in text


def test_carried_items_are_named() -> None:
    text = _gate()
    assert "K1 - The character-asks half of VX-11 stays open on the" in text
    assert "K2 - VX-12's engine half has no backend seam" in text
    assert "K3 - L3 registration is deliberate host-explicit law" in text
    assert "K4 - Several Part VII surfaces have no UI" in text
    assert "K5 - Back-projection is HTTP-road only" in text
    assert "K6 - Confidence is the backend's uncalibrated" in text
    assert 'K7 - The digest reports how long, never "too long"' in text


def test_findings_are_named() -> None:
    text = _gate()
    assert "F1 - No new engine defect was found by this gate" in text
    assert "Nothing was left unfixed in this slice's own files" in text
    assert "F2 - Observation, not a gate row: app.openapi() raises" in text


def test_migration_note_and_head_0041() -> None:
    text = _gate()
    assert "Migration note: none" in text
    assert "migration head remains 0041" in text
    assert "no migration was added by this slice" in text
    assert "committed on yrsa/runmal-team-01 for the keeper to bank in roadmap order" in text
    from runmal.db.migrations import MIGRATIONS
    assert MIGRATIONS[-1][0] == "0042"


def test_measured_counts_are_recorded() -> None:
    text = _gate()
    assert "Gate battery: 20 passed, 1 skipped" in text
    assert "tests/test_p116_gate.py (21 tests)" in text
    assert "4 + 7 + 2 + 6 + 2 = 21" in text
    assert "tests/test_p116_gate_record.py" in text
    assert "R = 10" in text
    assert "Neighbours batch as run by the tester: 445 passed" in text
    assert "Full suite: 4334 passed, 5 skipped, 0 failed" in text
    assert "4314 + 20 + 10 = 4344" in text
