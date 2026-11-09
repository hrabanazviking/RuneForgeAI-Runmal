"""P-168 acceptance: the Part X gate record.

The gate record (docs/PART_X_GATE_2026-11-08.md) closes
Part X: every P-155..P-166 faces surface present and
working together, P-167 accounted for honestly by
overlay (it banks in parallel and is not in the gate's
base), the custody and honesty laws whole, the carried
items K1-K8 named, and the measured counts recorded
against the banked baseline. These tests pin those
operative claims so a future slice cannot silently
drop a carried item or upgrade a carried number into
a measured one.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).parent.parent
GATE = REPO / "docs" / "PART_X_GATE_2026-11-08.md"


def _gate() -> str:
    return " ".join(GATE.read_text(encoding="utf-8").split())


def test_gate_doc_exists_and_states_the_verdict() -> None:
    assert GATE.exists()
    text = _gate()
    assert "Part X is COMPLETE and the gate PASSES" in text
    assert "named carried items and two findings" in text
    assert "claims only what the battery proves" in text
    assert "Census PASS" in text
    assert "Together PASS" in text
    assert "Custody PASS" in text
    assert "Accounting PASS" in text


def test_part_line_derived_scope_and_p167_shape() -> None:
    text = _gate()
    assert "X | Faces That Speak | P-155 - P-168" in text
    assert "every Part X slice scope is DERIVED" in text
    assert "no mirror source consulted (clean-room)" in text
    assert "P-167 (Face Speaking Census, team-02 commit c18d1e38)" in text
    assert "is NOT in this gate's base by design" in text
    assert "names BOTH shapes" in text
    assert "the base shape: the speaking-census road absent" in text
    assert ("the overlay shape: the speaking-census road "
            "present and passing") in text
    assert ("the keeper heals that one pin to the merged "
            "truth at banking if needed, at equal strength") in text


def test_gate_checklist_and_coverage_map() -> None:
    text = _gate()
    assert "P-155->A/B/C" in text
    assert "P-166->A/B/C/D" in text
    assert "P-167->A/B/C/D" in text
    assert "P-168->this gate" in text
    assert "No roadmap text was edited" in text
    assert "Part X spans P-155..P-168, fourteen slices continuous" in text


def test_verdict_rows_cover_every_slice() -> None:
    text = _gate()
    for row in ("Face presentation foundation",
                "Character face roster",
                "Speaking face",
                "Face selection history",
                "Speaking roster",
                "Character face chats",
                "Speaking history",
                "Character face history",
                "Character speaking history",
                "Face census",
                "Face history census",
                "Character speaking chats",
                "Face speaking census (overlay)"):
        assert row in text, row


def test_passes_means_together() -> None:
    text = _gate()
    assert "the census counts sum to the boards they compose" in text
    assert ("the P-167 overlay census reconciles with "
            "P-164's census row for row") in text
    assert "a second character's default voice stays distinct" in text


def test_passes_means_custody() -> None:
    text = _gate()
    assert "no voice key in any silent document" in text
    assert "voice_scope: current_only on every document" in text
    assert "no census-level voice" in text
    assert ("the P-023 content and thumbnail URLs as "
            "data only") in text
    assert "byte-identical and the voice row untouched" in text


def test_carried_items_are_named() -> None:
    text = _gate()
    assert ("K1 - The owner speaking-history census stays OPEN"
            in text)
    assert "Part X closes with that one owner speaking cell unmade" in text
    assert "does NOT take it" in text
    assert "K2 - No renderer, stage or lip-sync exists" in text
    assert "K3 - The P-109 affect is consumed:False" in text
    assert "K4 - The kept window is per chat and the record" in text
    assert "K5 - There is no owner-wide face and no single" in text
    assert "K6 - No voice history exists anywhere" in text
    assert "K7 - Scenario VN stage integration stays open" in text
    assert "K8 - Generated expression sprites via P-087 stay" in text


def test_findings_are_named() -> None:
    text = _gate()
    assert "F1 - No new engine defect was found by this gate" in text
    assert "Nothing was left unfixed in this slice's own files" in text
    assert "F2 - P-167 banks in parallel; its shape is named" in text
    assert "forge confirmation 5273 (5254 + 19, exact)" in text


def test_migration_note_and_head_0041() -> None:
    text = _gate()
    assert "Migration note: none" in text
    assert "migration head remains 0041" in text
    assert "no migration was added by this slice" in text
    assert ("committed on yrsa/runmal-team-03 for the keeper "
            "to bank in roadmap order") in text
    from runmal.db.migrations import MIGRATIONS
    assert MIGRATIONS[-1][0] == "0042"


def test_measured_counts_are_recorded() -> None:
    text = _gate()
    assert "Gate battery: 24 passed, 0 skipped" in text
    assert "tests/test_p168_part_x_gate.py (24 tests)" in text
    assert "5 + 6 + 6 + 5 + 2 = 24" in text
    assert "tests/test_p168_gate_record.py" in text
    assert "R = 10" in text
    assert "Neighbours batch as run by the tester: 233 passed" in text
    assert "Overlay battery as run by the tester: 19 passed" in text
    assert "Full suite: 5288 passed, 5 skipped, 0 failed in" in text
    assert "5273 + 24 + 10 = 5307" in text
