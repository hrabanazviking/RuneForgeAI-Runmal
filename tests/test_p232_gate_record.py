"""P-232 acceptance: the Part XIV gate record (R = 10).

The gate record closes Part XIV: the whole parity
matrix re-measured whole (141 rows judged, remainder
0), the thirteen tranche records standing in
CAMPAIGN_STATE exactly once each with tally lines
agreeing with the battery data, the banking hash chain
unbroken from the P-218 record to the build base, the
carried items named with their gate dispositions, and
the measured counts recorded against the P-231 banking
baseline. These tests pin those operative claims so a
future slice cannot silently drop a carried item, fill
a record gap on paper, or upgrade a carried number
into a measured one.

R6 carries one marked restatement (P-232 heal, design
section 3): WAVE_PLAN.md is a forge-side untracked
banking file and exists in no worktree, so the
one-line-per-tranche record fact is pinned where the
tree itself carries it - the gate doc's citizen table,
one row per tranche, in the P-218 record form - while
R1..R5 pin the tracked record (CAMPAIGN_STATE + git)
directly.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

REPO = Path(__file__).parent.parent
GATE = REPO / "docs" / "PART_XIV_GATE_2026-11-10.md"
CAMPAIGN_STATE = REPO / "CAMPAIGN_STATE.md"
CLEAN_ROOM_LOG = REPO / "docs" / "CLEAN_ROOM_LOG_2026-10-30.md"

P218_RECORD = "c8a054dda09682e584d479d74bae3f149ac41d8e"
BUILD_BASE = "09750a9b02205de582d490c55d2ba8dd8853a303"

EXPECTED_SPLITS = (
    (2, 10, 0, 0), (2, 7, 1, 0), (2, 10, 2, 0), (5, 6, 1, 0),
    (2, 15, 1, 1), (0, 5, 0, 0), (0, 1, 0, 0), (1, 7, 15, 0),
    (0, 0, 4, 0), (0, 1, 4, 0), (0, 1, 0, 1), (0, 2, 2, 0),
    (13, 11, 2, 4),
)
EXPECTED_CUMULATIVE = (
    (12, 2, 10, 0, 0), (22, 4, 17, 1, 0), (36, 6, 27, 3, 0),
    (48, 11, 33, 4, 0), (67, 13, 48, 5, 1), (72, 13, 53, 5, 1),
    (73, 13, 54, 5, 1), (96, 14, 61, 20, 1),
    (100, 14, 61, 24, 1), (105, 14, 62, 28, 1),
    (107, 14, 63, 28, 2), (111, 14, 65, 30, 2),
    (141, 27, 76, 32, 6),
)


def _gate() -> str:
    return " ".join(GATE.read_text(encoding="utf-8").split())


def _sections():
    text = CAMPAIGN_STATE.read_text(encoding="utf-8")
    heads = list(re.finditer(
        r"(?m)^\s+P-(\d{3}) BANKED -", text))
    sections = {}
    for i, head in enumerate(heads):
        end = (heads[i + 1].start()
               if i + 1 < len(heads) else len(text))
        sections[int(head.group(1))] = text[head.start():end]
    return sections


def _tally_flat(section):
    return " ".join(section.split()).replace("- ", "-")


def _cumulative(section):
    match = re.search(
        r"Cumulative judged (\d+) rows: HAVE (\d+) / "
        r"HAVE-THIN (\d+) / MISSING (\d+) / "
        r"SHIPPED-SOVEREIGN (\d+)", _tally_flat(section))
    assert match, "record carries no cumulative tally line"
    return tuple(int(g) for g in match.groups())


def _split(section):
    match = re.search(
        r"HAVE (\d+) / HAVE-THIN (\d+) / MISSING (\d+) / "
        r"SHIPPED-SOVEREIGN (\d+)", _tally_flat(section))
    assert match, "record carries no tally line"
    return tuple(int(g) for g in match.groups())


def test_r1_records_exist_tranches_1_to_5():
    sections = _sections()
    for n in range(219, 224):
        assert n in sections, n
        assert sections[n].count("BANKED") >= 1
    text = CAMPAIGN_STATE.read_text(encoding="utf-8")
    for n in range(219, 224):
        heads = re.findall(
            rf"(?m)^\s+P-{n} BANKED -", text)
        assert len(heads) == 1, n


def test_r2_records_exist_tranches_6_to_9():
    sections = _sections()
    text = CAMPAIGN_STATE.read_text(encoding="utf-8")
    for n in range(224, 228):
        assert n in sections, n
        heads = re.findall(
            rf"(?m)^\s+P-{n} BANKED -", text)
        assert len(heads) == 1, n


def test_r3_records_exist_tranches_10_to_13():
    sections = _sections()
    text = CAMPAIGN_STATE.read_text(encoding="utf-8")
    for n in range(228, 232):
        assert n in sections, n
        heads = re.findall(
            rf"(?m)^\s+P-{n} BANKED -", text)
        assert len(heads) == 1, n
    # The gate's own record lands at banking, not before:
    # no P-232 record stands in the file at build time.
    assert 232 not in sections


def test_r4_record_tallies_agree_with_battery_data():
    sections = _sections()
    # The founding record carries its tranche split in
    # its own form (no cumulative line stands before it).
    assert _split(sections[219]) == EXPECTED_SPLITS[0]
    for i, n in enumerate(range(220, 232), start=1):
        assert _cumulative(sections[n]) == (
            EXPECTED_CUMULATIVE[i]), (n, _cumulative(sections[n]))
    # Successive cumulative differences reproduce every
    # tranche split the batteries carry.
    previous = (0, 0, 0, 0, 0)
    for i, cumulative in enumerate(EXPECTED_CUMULATIVE):
        diff = tuple(
            cumulative[k] - previous[k] for k in range(1, 5))
        assert diff == EXPECTED_SPLITS[i], (i, diff)
        previous = cumulative


def test_r5_hash_chain_unbroken():
    out = subprocess.run(
        ["git", "log", "--reverse", "--pretty=%s",
         f"{P218_RECORD}..{BUILD_BASE}"],
        cwd=REPO, capture_output=True, text=True,
        check=True).stdout
    subjects = [line for line in out.splitlines() if line]
    positions = []
    for n in range(219, 232):
        found = [i for i, s in enumerate(subjects)
                 if s.startswith(f"P-{n} banking record")]
        assert len(found) == 1, (n, found)
        positions.append(found[0])
    assert positions == sorted(positions)
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor",
         P218_RECORD, BUILD_BASE],
        cwd=REPO, capture_output=True)
    assert ancestor.returncode == 0
    ancestor = subprocess.run(
        ["git", "merge-base", "--is-ancestor",
         BUILD_BASE, "HEAD"],
        cwd=REPO, capture_output=True)
    assert ancestor.returncode == 0


def test_r6_gate_doc_citizen_table_one_row_per_tranche():
    raw = GATE.read_text(encoding="utf-8")
    rows = re.findall(r"(?m)^\| (P-2\d{2}) \|", raw)
    assert rows == [f"P-{n}" for n in range(219, 232)], rows


def test_r7_p231_record_names_reconciliation_remainder_0():
    sections = _sections()
    flat = _tally_flat(sections[231])
    assert "RECONCILIATION" in flat
    assert "remaining 0 rows" in flat
    assert "FULLY JUDGED" in flat
    assert _cumulative(sections[231]) == (141, 27, 76, 32, 6)


def test_r8_no_record_claims_migration_or_census_change():
    sections = _sections()
    for n in range(219, 232):
        flat = _tally_flat(sections[n])
        assert "0043" not in flat, n
        assert "head stays 0042" in flat, n


def test_r9_clean_room_entries_match_records_one_for_one():
    log = CLEAN_ROOM_LOG.read_text(encoding="utf-8")
    total = 0
    for n in range(219, 232):
        pat = f"(?m)^- [*][*]P-{n} [(]"
        found = len(re.findall(pat, log))
        assert found == 1, n
        total += found
    assert total == 13


def test_r10_gate_record_lands_in_p218_form():
    assert GATE.exists()
    text = _gate()
    assert "P-219..P-232" in text
    assert "Part XIV is COMPLETE and the gate PASSES" in text
    assert "Census PASS" in text
    assert "Together PASS" in text
    assert "Scenario PASS" in text
    assert "Accounting PASS" in text
    assert "G = 35 as 10 + 8 + 7 + 8 + 2 = 35" in text
    assert "R = 10" in text
    assert "the P-231 banking total + 35 + 10" in text
    assert "6455 + 35 + 10 = 6500" in text
