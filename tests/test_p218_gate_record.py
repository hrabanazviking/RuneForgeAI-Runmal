"""P-218 acceptance: the Part XIII gate record.

The gate record (docs/PART_XIII_GATE_2026-11-10.md)
closes Part XIII: the whole part re-measured on one
fresh gate world, the citizen batteries stood on as
neighbours (never duplicated silently), every carried
item named with its gate disposition, the two record
gaps stated verbatim, the Bots verdict in plain
words, and the measured counts recorded against the
P-217 banking baseline. These tests pin those
operative claims so a future slice cannot silently
drop a carried item, fill a record gap on paper, or
upgrade a carried number into a measured one.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).parent.parent
GATE = REPO / "docs" / "PART_XIII_GATE_2026-11-10.md"


def _gate() -> str:
    return " ".join(GATE.read_text(encoding="utf-8").split())


def test_r1_record_exists_and_names_the_span() -> None:
    assert GATE.exists()
    text = _gate()
    assert "P-203..P-218" in text
    assert "sixteen slices continuous" in text
    assert "gate P-218" in text
    assert "Part XIII is COMPLETE and the gate PASSES" in text


def test_r2_verdict_line_names_all_four_areas() -> None:
    text = _gate()
    assert "Census PASS" in text
    assert "Together PASS" in text
    assert "Custody PASS" in text
    assert "Accounting PASS" in text


def test_r3_per_row_verdict_table_covers_every_slice() -> None:
    raw = GATE.read_text(encoding="utf-8")
    rows = re.findall(r"(?m)^\| .+ \| (P-2\d{2}) \|", raw)
    assert rows == [f"P-{n}" for n in range(203, 219)], rows
    text = _gate()
    for row in ("Inspector overview", "Inspector events",
                "Reasoning record", "Assistant View (stored rendering)",
                "Continue / impersonate reasoning wiring",
                "Groupchat reasoning wiring",
                "Swipe and web reasoning wiring",
                "Inspector reasoning join",
                "Inspector group reasoning join",
                "Group Assistant View", "Group transcript loader",
                "Persistent-group composer wiring", "Group mode toggle",
                "Saved-group creation", "Persistent-mode refinements",
                "Part XIII gate"):
        assert row in text, row


def test_r4_measured_counts_state_g_and_r() -> None:
    text = _gate()
    assert "G = 35 as 10 + 8 + 7 + 8 + 2 = 35" in text
    assert "R = 10" in text
    assert "tests/test_p218_part_xiii_gate.py (35 tests)" in text


def test_r5_expected_total_formula_stated_with_figures() -> None:
    text = _gate()
    assert "the P-217 banking total + 35 + 10" in text
    assert "6178 + 35 + 10 = 6223" in text
    assert "6223 passed, 5 skipped, 0 failed" in text


def test_r6_record_gaps_stated_verbatim() -> None:
    text = _gate()
    assert "P-209 shipped no slice doc and no headed clean-room entry" in text
    assert "P-208 shipped a slice doc but no headed clean-room entry" in text
    assert "may not claim a complete doc / clean-room census" in text


def test_r7_carried_items_table_complete() -> None:
    text = _gate()
    for item in (
        "D1 stateless SSE error-swallowing",
        "Per-swipe thinking browsing",
        "Bot runtime / bots package",
        "K-A binding label update",
        "K-B retention / bulk clear",
        "K-C unified-search history",
        "P-206 stored-only position",
        "Census 356/439, head 0042",
        "Cross-subject Inspector roll-up",
        "/run + raw-append group-page wiring",
        "manual_speaker_id pick for /next",
        "Group management web surfaces",
        "Live rendering on stored roads",
        "Extend onto legacy / manual / imported swipes",
        "Impersonate reasoning draft-only",
        "P-209 record gap (no doc, no headed entry)",
        "P-208 record gap (doc, no headed entry)",
    ):
        assert item in text, item
    for disposition in ("FENCED, ruling outstanding",
                        "DECLINED-PENDING-WORD (P-206)",
                        "ABSENT, substrateless",
                        "NAMED OPEN (remove-then-register)",
                        "NAMED OPEN, Volmarr's ruling",
                        "NAMED OPEN, no recording write",
                        "RECORD FACT, stated verbatim"):
        assert disposition in text, disposition


def test_r8_migration_census_note() -> None:
    text = _gate()
    assert "head 0042" in text
    assert "census 356 / 439" in text
    assert "no movement by this slice" in text
    from runmal.db.migrations import MIGRATIONS
    assert MIGRATIONS[-1][0] == "0042"


def test_r9_area_c_honesty_line_present() -> None:
    text = _gate()
    assert "Area C is a composed scenario, not a browser run" in text
    assert "substrate legs run over real HTTP" in text
    assert "segmented source-contract pins" in text
    assert "The record claims no browser execution" in text


def test_r10_bots_verdict_in_plain_words() -> None:
    text = _gate()
    assert "Bots founded nothing in Part XIII" in text
    assert "substrateless" in text
    assert "carried named, not concealed" in text
    assert "does not present Part XIII as three founded nouns" in text
