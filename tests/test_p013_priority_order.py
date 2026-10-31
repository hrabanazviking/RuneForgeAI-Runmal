"""P-013 acceptance: the priority order ratified.

The record (docs/PRIORITY_ORDER_2026-10-30.md) judges Part I's
census evidence against the roadmap's §3 order: the order
stands, the Evaluation Sitting keeps its P-006 first place
with its interrupt rule, the NO-HOME adapter family is ranked
first for the P-014 gate, and Parts VII/IX get definition
priority in the title-only back block. These tests pin the
record's operative claims and the roadmap's unchanged §3
table, so a future re-sequencing must update the record
deliberately instead of the order silently drifting.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).parent.parent
RECORD = REPO / "docs" / "PRIORITY_ORDER_2026-10-30.md"
ROADMAP = REPO / "docs" / "RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md"
LOG = REPO / "docs" / "CLEAN_ROOM_LOG_2026-10-30.md"

# The §3 table's parts, in the order the roadmap files them.
PARTS = (
    ("I", "The Delta Census — prove what is actually missing", "P-001 – P-014"),
    ("II", "Cards & Content Interop", "P-015 – P-030"),
    ("III", "Lorebook Depth", "P-031 – P-048"),
    ("IV", "Prompt & Sampler Depth", "P-049 – P-064"),
    ("V", "Chat Surgery", "P-065 – P-080"),
    ("VI", "The Extensions Row", "P-081 – P-100"),
    ("VII", "Voice, the Voxta Way", "P-101 – P-116"),
    ("VIII", "Vision Services", "P-117 – P-130"),
    ("IX", "Scenarios — the Visual Novel Engine", "P-131 – P-154"),
    ("X", "Faces That Speak", "P-155 – P-168"),
    ("XI", "Workspaces — the Companion That Works", "P-169 – P-186"),
    ("XII", "The Hub, Sovereign Shape", "P-187 – P-202"),
    ("XIII", "Assistant View, Inspector & Bots", "P-203 – P-218"),
    ("XIV", "The Proof Spine — the parity matrix, published", "P-219 – P-232"),
)


def _record() -> str:
    return RECORD.read_text(encoding="utf-8")


def test_roadmap_section3_order_is_unchanged() -> None:
    # The ratification's premise: §3 still files the fourteen
    # parts in this exact order, renumbered by nobody.
    text = ROADMAP.read_text(encoding="utf-8")
    positions = []
    for roman, name, rng in PARTS:
        row = f"| {roman} | {name} | {rng} |"
        assert row in text, row
        positions.append(text.index(row))
    assert positions == sorted(positions)
    assert len(PARTS) == 14


def test_record_ratifies_the_order_as_standing() -> None:
    text = _record()
    assert "the §3 order STANDS" in text
    assert "no part is renumbered" in text
    assert "no roadmap text was edited" in text
    # The rejected move is recorded with its rejection.
    assert "considered and rejected" in text
    assert "Rejected, for three recorded reasons" in text


def test_ratified_sequence_names_every_part_in_order() -> None:
    text = _record()
    # §3 point 0: the sitting is first and Volmarr-gated.
    assert "Evaluation Sitting — first" in text
    assert "Volmarr-gated" in text
    assert "take\n   priority over parity slices then in flight" in text or (
        "priority over parity slices" in text
    )
    # Points 1-4: gate, then II-VI, then VII-XIII, then XIV.
    assert "P-014, the Part I gate — next" in text
    assert "Parts II–VI, in numeric order" in text
    assert "Parts VII–XIII, in numeric order" in text
    assert "Part XIV, the Proof Spine — last" in text
    order = [
        text.index("Evaluation Sitting — first"),
        text.index("P-014, the Part I gate — next"),
        text.index("Parts II–VI, in numeric order"),
        text.index("Parts VII–XIII, in numeric order"),
        text.index("Part XIV, the Proof Spine — last"),
    ]
    assert order == sorted(order)


def test_daily_use_peaks_and_hub_late_are_named() -> None:
    text = _record()
    # VII and IX are the back block's priority; XII sits late.
    assert "VII and IX are the block's priority" in text
    assert "defined first" in text
    assert "XII (Hub) sits late in the block by design" in text
    # The census counts the reasoning rests on (P-004's own).
    assert "14 HAVE, 69 HAVE-THIN, 55 MISSING" in text
    assert "17 MISSING, 2 HAVE-THIN" in text
    assert "34 of the 55 MISSING rows carry a" in text


def test_priority_rulings_rank_the_no_home_families() -> None:
    text = _record()
    # Ruling A: the adapter family ranks first for the gate,
    # and homing remains the gate's act.
    assert "Priority ruling A" in text
    assert "generic\nOpenAI-compatible chat (+embeddings) adapter" in text or (
        "OpenAI-compatible chat (+embeddings) adapter" in text
    )
    assert "Aesir\nbinding repair" in text or "Aesir binding repair" in text
    assert "speech\nadapter" in text or "speech adapter" in text
    assert "Ranking is this slice's act; homing remains P-014's" in text
    # Ruling B: PWA + capture ride with Part VII (P-011 D5).
    assert "Priority ruling B" in text
    assert "ride\nwith Part VII" in text or "ride with Part VII" in text
    assert "secure-context" in text


def test_dependency_chain_and_limits_are_recorded() -> None:
    text = _record()
    # The chain that forbids re-sequencing: scenarios consume
    # P-093's store under P-082's law; X consumes P-087; the
    # Inspector consumes P-043/P-059.
    for marker in ("P-093", "P-082", "P-087", "P-023", "P-043", "P-059"):
        assert marker in text, marker
    # Honest limits: this record assigns nothing and validates
    # no slice list beyond Parts I-VI.
    assert "It assigns nothing" in text
    assert "awaiting definitions" in text
    assert "surveyed-but-not-yet-read" in text


def test_clean_room_log_carries_the_p013_entry() -> None:
    # P-012 §0(5): every slice appends its entry before banking.
    text = LOG.read_text(encoding="utf-8")
    assert "P-013 (2026-10-30, derived / own documents only)" in text
    assert "no mirror reading" in text or "No new mirror reading" in text or (
        "no\n  new external source" in text
    )
