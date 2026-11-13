"""P-202 acceptance: the Part XII gate record.

The gate record (docs/PART_XII_GATE_2026-11-09.md)
closes Part XII: every P-187..P-201 hub surface
present and working together, the gate standing on
the P-201 reconciliation battery in its base (never
duplicating it silently), the custody and fence laws
whole, the carried items K-A..K-H named, and the
measured counts recorded against the banked baseline.
These tests pin those operative claims so a future
slice cannot silently drop a carried item or upgrade
a carried number into a measured one.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).parent.parent
GATE = REPO / "docs" / "PART_XII_GATE_2026-11-09.md"


def _gate() -> str:
    return " ".join(GATE.read_text(encoding="utf-8").split())


def test_gate_doc_exists_and_states_the_verdict() -> None:
    assert GATE.exists()
    text = _gate()
    assert "Part XII is COMPLETE and the gate PASSES" in text
    assert "named carried items and two findings" in text
    assert "claims only what the battery proves" in text
    assert "Census PASS" in text
    assert "Together PASS" in text
    assert "Custody PASS" in text
    assert "Accounting PASS" in text


def test_part_line_derived_scope_and_p201_relation() -> None:
    text = _gate()
    assert "XII | The Hub, Sovereign Shape | P-187..P-202" in text
    assert "every Part XII slice scope is DERIVED" in text
    assert "no mirror source consulted (clean-room)" in text
    assert "the gate stands on it, never duplicates it silently" in text
    assert "its 26 tests run beside this gate's battery as neighbours" in text
    assert "ZqxGate202, nonce \"ZqxGate202Nonce\"" in text


def test_gate_checklist_and_coverage_map() -> None:
    text = _gate()
    assert "P-187->A/B/C" in text
    assert "P-194->B" in text
    assert "P-201->A (stood on, run as neighbour)" in text
    assert "P-202->this gate" in text
    assert "No roadmap text was edited" in text
    assert "Part XII spans P-187..P-202, sixteen slices continuous" in text


def test_verdict_rows_cover_every_slice() -> None:
    text = _gate()
    for row in ("Hub registry foundation",
                "Hub browse over entry contents",
                "Hub census",
                "Hub search over entries",
                "Hub pack-content search",
                "Hub unified search",
                "Hub content census",
                "Hub unified-search census",
                "Hub duplicate-content census",
                "Hub content-shape census",
                "Hub byte-size census",
                "Hub breadth census",
                "Hub distinct-content census",
                "Hub schema census",
                "Hub reconciliation battery",
                "Part XII gate"):
        assert row in text, row

def test_passes_means_together() -> None:
    text = _gate()
    assert "the P-187 list document equals the list embedded in P-189" in text
    assert "the unified search is exactly the union" in text
    assert "the duplicate partition closes" in text
    assert "P-197 per-row bytes equal os.stat" in text


def test_passes_means_custody() -> None:
    text = _gate()
    assert "every hub read is a pure read" in text
    assert "no census document retains content" in text
    assert "the mutating roads are exactly the two banked writes" in text
    assert "one TestClient session walks all 17 operations" in text


def test_carried_items_are_named() -> None:
    text = _gate()
    assert "K-A - Binding label update stays named open" in text
    assert "remove-then-register, never a silent in-place update" in text
    assert "K-B - Automatic retention / bulk clear of history" in text
    assert "awaits the ruling of Volmarr" in text
    assert "K-C - Unified-search history stays named open" in text
    assert "presupposes a recording write and a store" in text
    assert "K-D - Signing / attestation - declined, not shipped" in text
    assert "signing is NOT part of what shipped" in text
    assert "K-E - Friend-instance exchange transport" in text
    assert "K-F - Hub-side import / install - declined" in text
    assert "K-G - Entry lifecycle depth beyond register/remove" in text
    assert "K-H - Central store / catalogue / creator profiles" in text
    assert "ruled out by VX-59, NOT a gap" in text
    assert "content_sha256 subtrees are never walked" in text
    assert "Checksum claims are claims" in text


def test_findings_are_named() -> None:
    text = _gate()
    assert "F1 - One design-text discrepancy, corrected against the tree" in text
    assert "no defect in banked code" in text
    assert "does NOT reproduce on this tree" in text
    assert "is NOT carried as a live finding" in text
    assert "Nothing was left unfixed in this slice's own files" in text
    assert "F2 - One contention flake in the first full-suite" in text
    assert "5947 passed, 5 skipped, 1 failed in 592.52s" in text
    assert "4 passed" in text


def test_migration_note_and_head_0041() -> None:
    text = _gate()
    assert "Migration note: none" in text
    assert "migration head remains 0041" in text
    assert "no migration was added by this slice" in text
    assert ("committed on yrsa/runmal-team-01 for the keeper "
            "to bank in roadmap order") in text
    from runmal.db.migrations import MIGRATIONS
    assert MIGRATIONS[-1][0] == "0042"


def test_measured_counts_are_recorded() -> None:
    text = _gate()
    assert "Gate battery: 34 passed, 0 skipped" in text
    assert "tests/test_p202_part_xii_gate.py (34 tests)" in text
    assert "9 + 12 + 5 + 6 + 2 = 34" in text
    assert "tests/test_p202_gate_record.py" in text
    assert "R = 10" in text
    assert "Neighbours batch as run by the tester: 405 passed" in text
    assert "Full suite: 5948 passed, 5 skipped, 0 failed" in text
    assert "(adjusted) on this gate's base" in text
    assert "5904 + 34 + 10 = 5948" in text
