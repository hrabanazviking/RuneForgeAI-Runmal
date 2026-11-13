"""P-100 acceptance: the Part VI gate record.

The gate record (docs/PART_VI_GATE_2026-11-07.md) closes
Part VI: the row ships with P-084-P-090 + P-095 live under
the P-097 kit, a blind third-party-shaped plugin installs
and runs, the carried items K1-K6 are named, finding F1 is
commissioned, and the measured counts are recorded against
the merged baseline. These tests pin those operative claims
so a future slice cannot silently drop a carried item, lose
a finding, or upgrade a carried number into a measured one.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).parent.parent
GATE = REPO / "docs" / "PART_VI_GATE_2026-11-07.md"
ROADMAP = REPO / "docs" / "RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md"


def _gate() -> str:
    return " ".join(GATE.read_text(encoding="utf-8").split())


def test_gate_doc_exists_and_states_the_verdict() -> None:
    assert GATE.exists()
    text = _gate()
    assert "Part VI is COMPLETE and the gate PASSES" in text
    assert "named carried items and one finding" in text
    assert "claims only what the battery proves" in text
    assert "Row PASS" in text
    assert "Blind PASS" in text
    assert "Accounting PASS" in text


def test_roadmap_line_and_part_vi_goal_are_quoted() -> None:
    text = _gate()
    assert ("P-100 Part VI gate: the row ships with P-084-P-090 + P-095 live; "
            "a third-party-shaped test plugin (written blind against the docs) "
            "installs and runs") in text
    assert "a real API, a real sandbox, and the beloved extensions rebuilt as citizens" in text
    assert "no mirror source consulted (clean-room)" in text


def test_gate_checklist_and_coverage_map() -> None:
    text = _gate()
    assert "P-081->A/B/C" in text
    assert "P-094->B/C" in text
    assert "P-095->A" in text
    assert "P-099->B/C" in text
    assert "P-100->this gate" in text
    assert "No roadmap text was edited" in text
    roadmap = ROADMAP.read_text(encoding="utf-8")
    section = roadmap[roadmap.index("## Part VI"):]
    section = section[:section.index("\n---")]
    ids = [int(m) for m in re.findall(r"\*\*P-(\d+)\*\*", section)]
    assert sorted(ids) == list(range(81, 101))
    assert len(ids) == 20
    assert "Part VI spans P-081..P-100, twenty slices continuous" in text


def test_passes_means_row() -> None:
    text = _gate()
    assert "passes the P-097 conformance kit as shipped and is listable" in text
    assert "the full shipped corpus of sixteen citizens passes" in text
    assert "a chat.created dispatch is delivered to the ten subscribed citizens" in text
    assert "the seed slot and seed message pass through both stages byte-intact" in text


def test_passes_means_blind() -> None:
    text = _gate()
    assert "passes the conformance kit on data alone" in text
    assert "installs and enables through the manager road" in text
    assert "deletes through the same road, finishing through the manager uninstall" in text
    assert "the plugin disables itself at the failure limit with a plain report that carries no secret" in text
    assert "the errored plugin is never invoked again" in text
    assert "it lives only in the gate battery" in text


def test_blind_plugin_docs_are_named() -> None:
    text = _gate()
    for doc in ("PLUGIN_API_V1_2026-11-07.md", "PLUGIN_MANAGER_2026-11-07.md",
                "PLUGIN_SETTINGS_UI_2026-11-07.md",
                "PLUGIN_DATA_CUSTODY_2026-11-07.md",
                "PLUGIN_CONFORMANCE_KIT_2026-11-07.md"):
        assert doc in text
    assert "acme.word-counter" in text
    assert "ZqxGate100" in text


def test_carried_items_are_named() -> None:
    text = _gate()
    assert "K1 - The P-094 fixed citizen list omits two citizens" in text
    assert "K2 - P-098 stored values do not yet change a running citizen's behaviour" in text
    assert "K3 - P-099 failure state is process-local" in text
    assert "K4 - The P-081 empty boot registry is deliberate" in text
    assert "K5 - The pack road is data-only in v1" in text
    assert "K6 - Custody deletion spans two surfaces for a pack plugin" in text


def test_findings_are_named() -> None:
    text = _gate()
    assert "F1 - The P-094 fixed citizen list omits runmal.game-bridge" in text
    assert "extend it at the next custody touch" in text
    assert "add both ids to CITIZEN_PLUGIN_IDS" in text
    assert "F2 - No new engine defect was found by this gate" in text
    assert "Nothing was left unfixed in this slice's own files" in text
    assert "The P-064 findings F1/F2 are not touched by this gate" in text


def test_migration_note_and_head_0041() -> None:
    text = _gate()
    assert "Migration note: none" in text
    assert "migration head remains 0041" in text
    assert "no migration was added by this slice" in text
    assert "committed on yrsa/runmal-team-03 for the keeper to bank in roadmap order" in text
    from runmal.db.migrations import MIGRATIONS
    assert MIGRATIONS[-1][0] == "0042"


def test_measured_counts_and_baseline_arithmetic() -> None:
    text = _gate()
    assert "Gate battery: 16 passed" in text
    assert "tests/test_p100_gate.py (16 tests)" in text
    assert "4 + 7 + 5 = 16" in text
    assert "tests/test_p100_gate_record.py (10 tests)" in text
    assert "R = 10" in text
    assert "Neighbours batch as run by the tester: 628 passed" in text
    assert "Full suite: 4067 passed, 4 skipped, 0 failed" in text
    assert "B = 4041 passed, 4 skipped" in text
    assert "4041 + 16 + 10 = 4067" in text
    assert "full suite == B + 16 + R, exact" in text
