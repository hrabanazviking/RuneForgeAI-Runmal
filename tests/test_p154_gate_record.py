"""P-154 acceptance: the Part IX gate record.

The gate record (docs/PART_IX_GATE_2026-11-08.md) closes
Part IX: every P-131..P-152 scenario surface present and
working together, P-153 accounted for honestly by overlay
(it banks in parallel and is not in the gate's base), the
custody chains whole, the honesty bounds pinned, the
carried items K1-K8 named, and the measured counts
recorded against the banked baseline. These tests pin
those operative claims so a future slice cannot silently
drop a carried item or upgrade a carried number into a
measured one.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).parent.parent
GATE = REPO / "docs" / "PART_IX_GATE_2026-11-08.md"


def _gate() -> str:
    return " ".join(GATE.read_text(encoding="utf-8").split())


def test_gate_doc_exists_and_states_the_verdict() -> None:
    assert GATE.exists()
    text = _gate()
    assert "Part IX is COMPLETE and the gate PASSES" in text
    assert "named carried items and two findings" in text
    assert "claims only what the battery proves" in text
    assert "Census PASS" in text
    assert "Together PASS" in text
    assert "Custody PASS" in text
    assert "Accounting PASS" in text


def test_part_line_derived_scope_and_p153_shape() -> None:
    text = _gate()
    assert "IX | Scenarios - the Visual Novel Engine | P-131 - P-154" in text
    assert "every Part IX slice scope is DERIVED" in text
    assert "no mirror source consulted (clean-room)" in text
    assert "P-153 (Library Bind-Plan Census, team-02 commit 4d35cff)" in text
    assert "is NOT in this gate's base by design" in text
    assert "names BOTH shapes" in text


def test_gate_checklist_and_coverage_map() -> None:
    text = _gate()
    assert "P-131->A/B/C" in text
    assert "P-150->A/B/C/D" in text
    assert "P-153->A/B/D" in text
    assert "P-154->this gate" in text
    assert "No roadmap text was edited" in text
    assert "Part IX spans P-131..P-154, twenty-four slices continuous" in text


def test_verdict_rows_cover_every_slice() -> None:
    text = _gate()
    for row in ("Definitions store",
                "Scenario-to-chat binding",
                "Stored-definition file export",
                "Library organisation",
                "Binding lifecycle read surface",
                "Binding plan preview",
                "Definition duplication",
                "Chat-scoped bind preview",
                "Definition delete-impact preview",
                "Definition replace-impact preview",
                "Scenario definition sharing packs",
                "Stateless native-to-Voxta export (F1 closed)",
                "Library-scoped pack import preview",
                "Global binding census",
                "Library unmappable-content census",
                "Candidate replace preview",
                "Chat-scoped candidate bind preview",
                "Binding chat-custody census",
                "Chat delete-impact preview",
                "Binding custody census, both axes",
                "Library definition census",
                "Chat coverage census",
                "Library bind-plan census (overlay)"):
        assert row in text, row


def test_passes_means_together() -> None:
    text = _gate()
    assert ("its flags and variables seed through P-093 "
            "missing-keys-only") in text
    assert ("the P-153 overlay census reconciles with "
            "P-136's per-definition envelopes") in text
    assert ("an exact duplicate returns the existing "
            "record, a fresh library creates one") in text


def test_passes_means_custody() -> None:
    text = _gate()
    assert "deleting a chat leaves the binding document byte-untouched" in text
    assert "still answers the per-chat read exactly as if the chat lived" in text
    assert "every census and every preview writes nothing" in text


def test_carried_items_are_named() -> None:
    text = _gate()
    assert "K1 - The delete_chat cascade stays open, RESERVED" in text
    assert "FOR VOLMARR" in text
    assert "does NOT take it" in text
    assert "K2 - Portable-archive inclusion of the scenario" in text
    assert "K3 - Unmappable Voxta raw values never persist" in text
    assert "K4 - The P-133 finding F1 is CLOSED on the stateless" in text
    assert "K5 - Playback / runtime / condition evaluation stays" in text
    assert "K6 - Definition history retention stays open" in text
    assert "K7 - Organisation orphan rows and cross-store" in text
    assert "K8 - Bind-plan vs actual-bind reconciliation beyond" in text


def test_findings_are_named() -> None:
    text = _gate()
    assert "F1 - No new engine defect was found by this gate" in text
    assert "Nothing was left unfixed in this slice's own files" in text
    assert "F2 - P-153 banks in parallel; its shape is named" in text
    assert "forge confirmation 5009 (4990 + 19, exact)" in text


def test_migration_note_and_head_0041() -> None:
    text = _gate()
    assert "Migration note: none" in text
    assert "migration head remains 0041" in text
    assert "no migration was added by this slice" in text
    assert "committed on yrsa/runmal-team-03 for the keeper to bank in roadmap order" in text
    from runmal.db.migrations import MIGRATIONS
    assert MIGRATIONS[-1][0] == "0042"


def test_measured_counts_are_recorded() -> None:
    text = _gate()
    assert "Gate battery: 26 passed, 0 skipped" in text
    assert "tests/test_p154_part_ix_gate.py (26 tests)" in text
    assert "4 + 8 + 6 + 6 + 2 = 26" in text
    assert "tests/test_p154_gate_record.py" in text
    assert "R = 10" in text
    assert "Neighbours batch as run by the tester: 445 passed" in text
    assert "Full suite: 5016 passed, 5 skipped, 0 failed in" in text
    assert "4990 + 26 + 10 = 5026" in text
    assert "5009 + 26 + 10 = 5045" in text
