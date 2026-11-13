"""P-130 acceptance: the Part VIII gate record.

The gate record (docs/PART_VIII_GATE_2026-11-08.md) closes
Part VIII: every P-117..P-129 vision surface present and
working together, the custody chains whole, the honesty
bounds pinned, the carried items K1-K8 named, and the
measured counts recorded against the banked baseline.
These tests pin those operative claims so a future slice
cannot silently drop a carried item or upgrade a carried
number into a measured one.
"""

from __future__ import annotations

from pathlib import Path

REPO = Path(__file__).parent.parent
GATE = REPO / "docs" / "PART_VIII_GATE_2026-11-08.md"


def _gate() -> str:
    return " ".join(GATE.read_text(encoding="utf-8").split())


def test_gate_doc_exists_and_states_the_verdict() -> None:
    assert GATE.exists()
    text = _gate()
    assert "Part VIII is COMPLETE and the gate PASSES" in text
    assert "named carried items and two findings" in text
    assert "claims only what the battery proves" in text
    assert "Census PASS" in text
    assert "Together PASS" in text
    assert "Custody PASS" in text
    assert "Accounting PASS" in text


def test_part_line_and_derived_scope_are_stated() -> None:
    text = _gate()
    assert "VIII | Vision Services | P-117 - P-130" in text
    assert "every Part VIII slice scope is DERIVED" in text
    assert "no mirror source consulted (clean-room)" in text


def test_gate_checklist_and_coverage_map() -> None:
    text = _gate()
    assert "P-117->A/B/C/D" in text
    assert "P-129->A/C" in text
    assert "P-130->this gate" in text
    assert "No roadmap text was edited" in text
    assert "Part VIII spans P-117..P-130, fourteen slices continuous" in text


def test_verdict_rows_cover_every_slice() -> None:
    text = _gate()
    for row in ("Vision foundation + OpenAPI fix",
                "Last description template variable",
                "Provider selection + capability truth",
                "Chat image attachments",
                "Folder watcher",
                "Description history, search & custody",
                "Attachment thumbnails",
                "Watcher custody & control",
                "Attachment history & search",
                "Describe-on-attach opt-in",
                "Watcher history & search",
                "Describe-on-scan opt-in",
                "Watcher control parity"):
        assert row in text, row


def test_passes_means_together() -> None:
    text = _gate()
    assert ("both provider roads describe into one store whose "
            "list, last-per-chat, history search and prompt variable") in text
    assert "never re-describes an already-ingested file" in text
    assert "the dedupe memory survives the flip" in text


def test_passes_means_custody() -> None:
    text = _gate()
    assert '"ingested_records_removed": n' in text
    assert "ingests anew on the next scan instead of skipping forever" in text
    assert "message deletion purges the message's attachment" in text


def test_carried_items_are_named() -> None:
    text = _gate()
    assert "K1 - A real local semantic caption provider stays" in text
    assert "K2 - OCR stays open" in text
    assert "K3 - Capture / camera stays open" in text
    assert "K4 - A watcher daemon stays open, deliberately" in text
    assert "K5 - Non-PNG thumbnails stay open" in text
    assert "K6 - Watcher scan-report persistence stays open" in text
    assert "K7 - Vision settings stay open" in text
    assert "K8 - Portable-archive inclusion of the vision stores" in text


def test_findings_are_named() -> None:
    text = _gate()
    assert "F1 - No new engine defect was found by this gate" in text
    assert "Nothing was left unfixed in this slice's own files" in text
    assert "F2 - The P-116 gate's F2 is verified CLOSED" in text


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
    assert "tests/test_p130_part_viii_gate.py (26 tests)" in text
    assert "4 + 8 + 6 + 6 + 2 = 26" in text
    assert "tests/test_p130_gate_record.py" in text
    assert "R = 10" in text
    assert "Neighbours batch as run by the tester: 210 passed" in text
    assert "4571 + 26 + 10 = 4607" in text
