"""P-014 acceptance: the Part I gate.

The gate record (docs/PART_I_GATE_2026-10-30.md) closes
Part I: its checklist ties the delta table, continuation
audit and fresh baseline to their banking commits, Parts
II-VI are re-validated by mechanical count against the
filed roadmap, every flagged NO-HOME / kin-only row is
homed, queued, or explicitly dropped, Parts VII-XIV are
recorded as awaiting definitions, and the S806 licence
re-check is reported with its measured counts. These tests
pin those operative claims so a future slice cannot
silently un-home a row or claim a validation the gate
never made.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).parent.parent
GATE = REPO / "docs" / "PART_I_GATE_2026-10-30.md"
ROADMAP = REPO / "docs" / "RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md"
LOG = REPO / "docs" / "CLEAN_ROOM_LOG_2026-10-30.md"


def _gate() -> str:
    return " ".join(GATE.read_text(encoding="utf-8").split())


def test_gate_verdict_and_checklist() -> None:
    text = _gate()
    assert "Part I is COMPLETE and the gate PASSES" in text
    # The three roadmap-named gate inputs, with their commits.
    assert "0f2ad64" in text  # P-004 delta table
    assert "2c73cf7" in text  # P-006 continuation audit
    assert "72692e1" in text  # P-007 fresh baseline
    assert "14 HAVE, 69 HAVE-THIN, 55 MISSING, 3 DELIBERATELY-DIFFERENT" in text
    assert "685 passed, 6 skipped, 0 failed" in text
    assert "735 passed, 6 skipped, 0 failed" in text


def test_every_part1_slice_commit_is_named() -> None:
    text = _gate()
    for commit in (
        "9ee6402", "a8f6dc8", "24f0433", "0f2ad64", "d08fc58",
        "2c73cf7", "72692e1", "c1b0572", "d13a092", "268ec36",
        "d316f69", "4589d32", "819cdd8",
    ):
        assert commit in text, commit


def test_parts_ii_to_vi_counts_are_mechanical_and_stand() -> None:
    roadmap = ROADMAP.read_text(encoding="utf-8")
    ids = [int(m) for m in re.findall(r"^- \*\*P-(\d+)\*\*", roadmap, flags=re.M)]
    assert sorted(ids) == list(range(1, 101))  # continuous, no gaps/dupes
    assert len([n for n in ids if 15 <= n <= 100]) == 86
    text = _gate()
    for part in (
        "II Cards & Content Interop", "III Lorebook Depth",
        "IV Prompt & Sampler Depth", "V Chat Surgery",
        "VI The Extensions Row",
    ):
        assert part in text, part
    assert text.count("STANDS") >= 5
    assert "no roadmap text was edited" in text


def test_follow_on_block_homes_the_adapter_family_first() -> None:
    text = _gate()
    assert "F-01 — generic OpenAI-compatible chat adapter" in text
    assert "F-02 — Aesir binding repair" in text
    assert "F-03 — generic OpenAI-compatible speech adapter" in text
    assert "F-04 — clean-up tool" in text
    order = [text.index(f"F-0{i}") for i in (1, 2, 3, 4)]
    assert order == sorted(order)
    assert "before P-015" in text
    assert "stop sending `stream_options`" in text
    assert "Aesir embeddings bind to Ollama, never to Aesir" in text


def test_every_flagged_row_has_a_gate_verdict() -> None:
    text = _gate()
    for row in (
        "ST-26", "ST-27", "ST-30", "ST-39", "ST-40", "ST-44",
        "ST-50", "ST-55", "ST-69", "ST-70", "ST-71", "ST-73",
        "VX-07", "VX-08", "VX-11", "VX-17", "VX-18", "VX-19",
        "VX-23", "VX-26", "VX-52", "VX-53", "VX-58", "VX-64",
    ):
        assert row in text, row
    # The explicit drops are stated as drops, with re-open terms.
    assert "DROPPED from the defined road, explicitly" in text  # ST-40
    assert "ST-69 user theme editing" in text and "DROPPED, explicitly" in text
    assert "ST-70 localised UI" in text
    assert "DELIBERATELY-DIFFERENT, closed" in text  # ST-44
    assert "none is silently dropped" in text


def test_parts_vii_to_xiv_are_awaiting_definitions_not_validated() -> None:
    text = _gate()
    assert "awaiting definitions, not validated" in text
    assert "VII (Voice) and IX (Scenarios) are first in the definition queue" in text
    assert "XII (Hub) sits late in the block by sovereign design" in text
    assert "Assistant view and full Inspector surface" in text


def test_s806_recheck_counts_and_names() -> None:
    text = _gate()
    assert "33 distributions" in text
    assert "28 permissive, 5 unknown, 0 forbidden" in text
    for name in ("certifi", "greenlet", "packaging", "sqlite-vec", "typing_extensions"):
        assert name in text, name
    assert "does not silently clear them" in text
    assert "zero forbidden licences in both measured sets" in text


def test_named_debts_stay_open() -> None:
    text = _gate()
    assert "The Evaluation Sitting — Volmarr-gated, still first" in text
    assert "purplelongship baseline confirmation leg — still owed" in text
    assert "Aesir live smoke — still owed" in text
    assert "NOT PROVEN LIVE" in text
    assert "CosyVoice CPU performance fact — still open" in text
    assert "HTTPS-for-LAN decision — Volmarr's" in text


def test_clean_room_log_carries_the_p014_entry() -> None:
    text = " ".join(LOG.read_text(encoding="utf-8").split())
    assert "P-014 (2026-10-30, derived / own documents and own-tree measurement only)" in text
    assert "no mirror reading" in text
