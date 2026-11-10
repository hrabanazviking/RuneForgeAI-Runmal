"""P-223 - Parity matrix tranche 5: the Part VI rows, re-judged.

Pins for docs/PARITY_MATRIX_2026-11-10.md after the P-223
tranche-5 update: the tranche-5 rows (road home = Part VI,
plus ST-27 included as MISSING under the keeper's Q1 ruling,
VX-26 included as HAVE-THIN under the keeper's Q2 ruling and
VX-42 included as SHIPPED-SOVEREIGN under the keeper's Q3
ruling - the banked P-014 gate homed ST-27 as kin scope under
P-081/P-093 and VX-26 as explicit scope of P-085, and VX-42's
dedicated home names P-082 under the first-home rule) carry
closing verdicts with evidence citations resolving inside
this repo, every other unjudged row keeps the explicit
NOT-YET-REJUDGED marker, the tranche-1, tranche-2, tranche-3
and tranche-4 judgements are identical to the P-222 banking
record, and the section-3 counts (tranche 5, cumulative,
remainder) equal a mechanical recount.
"""
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MATRIX = REPO / "docs" / "PARITY_MATRIX_2026-11-10.md"
DELTA = REPO / "docs" / "DELTA_TABLE_2026-10-30.md"
CLEAN_ROOM_LOG = REPO / "docs" / "CLEAN_ROOM_LOG_2026-10-30.md"
BASE = "2566117d4e05f7fb2dfb7e1da3c9b218e439935f"
S = chr(167)

TRANCHE1 = {
    "ST-02", "ST-03", "ST-04", "ST-05", "ST-08", "ST-09",
    "ST-10", "ST-34", "ST-54", "VX-03", "VX-27", "VX-60",
}
TRANCHE2 = {
    "ST-15", "ST-16", "ST-17", "ST-18", "ST-20", "ST-22",
    "ST-23", "ST-25", "ST-26", "VX-22",
}
TRANCHE3 = {
    "ST-06", "ST-28", "ST-29", "ST-30", "ST-31", "ST-32",
    "ST-33", "ST-35", "ST-36", "ST-38", "ST-39", "ST-74",
    "VX-16", "VX-18",
}
TRANCHE4 = {
    "ST-07", "ST-13", "ST-14", "ST-46", "ST-47", "ST-48",
    "ST-49", "ST-50", "ST-51", "ST-53", "ST-60", "VX-06",
}
TRANCHE5 = {
    "ST-27", "ST-56", "ST-57", "ST-58", "ST-61", "ST-62",
    "ST-63", "ST-64", "ST-65", "ST-66", "ST-67", "ST-68",
    "VX-20", "VX-25", "VX-26", "VX-34", "VX-42", "VX-51",
    "VX-66",
}
TRANCHE6 = {
    "VX-04", "VX-10", "VX-11", "VX-12", "VX-14",
}
TRANCHE7 = {
    "VX-50",
}
TRANCHE8 = {
    "VX-02", "VX-05", "VX-08", "VX-13", "VX-17", "VX-28",
    "VX-29", "VX-30", "VX-31", "VX-32", "VX-33", "VX-35",
    "VX-36", "VX-37", "VX-38", "VX-39", "VX-40", "VX-41",
    "VX-43", "VX-44", "VX-45", "VX-46", "VX-47",
}
TRANCHE9 = {
    "VX-48", "VX-49", "VX-52", "VX-53",
}
JUDGED8 = TRANCHE1 | TRANCHE2 | TRANCHE3 | TRANCHE4 | TRANCHE5 | TRANCHE6 | TRANCHE7 | TRANCHE8
JUDGED = JUDGED8 | TRANCHE9
DD_ROWS = ("VX-01", "VX-42", "VX-59")
CLOSING_TOKENS = {
    "HAVE", "HAVE-THIN", "MISSING", "SHIPPED-SOVEREIGN",
    "NOT-YET-REJUDGED",
}
ALL_TOKENS = CLOSING_TOKENS | {"DELIBERATELY-DIFFERENT"}


def _rows(path):
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("| "):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        rid = cells[0]
        if not (rid.startswith("ST-") or rid.startswith("VX-")):
            continue
        assert rid not in rows, rid
        rows[rid] = cells
    return rows


def _section(text, heading):
    start = text.index(heading)
    rest = text[start + len(heading):]
    nxt = rest.find("\n## ")
    return rest if nxt == -1 else rest[:nxt]


def _closing_token(cells):
    return cells[4].split(" - ")[0]


def _counts(rows, ids):
    counts = {t: 0 for t in CLOSING_TOKENS}
    for rid in ids:
        counts[_closing_token(rows[rid])] += 1
    return counts


def _count_line(flat, label):
    pat = (label + ": HAVE ([0-9]+), HAVE-THIN ([0-9]+), "
           "MISSING ([0-9]+), SHIPPED-SOVEREIGN ([0-9]+), "
           "NOT-YET-REJUDGED ([0-9]+), of ([0-9]+) rows.")
    m = re.search(pat, flat)
    assert m, label
    return tuple(int(g) for g in m.groups())


def _as_tuple(counts, total):
    return (counts["HAVE"], counts["HAVE-THIN"], counts["MISSING"],
            counts["SHIPPED-SOVEREIGN"], counts["NOT-YET-REJUDGED"],
            total)


def test_01_schema_sections_present():
    text = MATRIX.read_text(encoding="utf-8")
    for heading in ("## " + S + "0 Method", "## " + S + "1 Verdict vocabulary",
                    "## " + S + "2 The tranche map", "## " + S + "3 Summary counts",
                    "## Table A", "## Table B", "## " + S + "4 Carried items"):
        assert heading in text, heading


def test_02_st_row_ids_exactly_once():
    rows = _rows(MATRIX)
    st = sorted(r for r in rows if r.startswith("ST-"))
    assert st == ["ST-%02d" % n for n in range(1, 75)]


def test_03_vx_row_ids_exactly_once():
    rows = _rows(MATRIX)
    vx = sorted(r for r in rows if r.startswith("VX-"))
    assert vx == ["VX-%02d" % n for n in range(1, 68)]


def test_04_opening_verdicts_and_homes_match_delta():
    matrix = _rows(MATRIX)
    delta = _rows(DELTA)
    assert set(matrix) == set(delta)
    for rid, dcells in delta.items():
        mcells = matrix[rid]
        assert mcells[1] == dcells[1], rid
        assert mcells[2] == dcells[2], rid
        assert mcells[3] == dcells[4], rid


def test_05_tranche5_rows_carry_closing_verdicts():
    rows = _rows(MATRIX)
    for rid in TRANCHE5:
        token = _closing_token(rows[rid])
        assert token in CLOSING_TOKENS, rid
        assert token != "NOT-YET-REJUDGED", rid


def test_06_rows_outside_tranches_exactly_not_yet_rejudged():
    rows = _rows(MATRIX)
    for rid, cells in rows.items():
        if rid in JUDGED:
            continue
        assert cells[4] == "NOT-YET-REJUDGED", rid


def test_07_tranche1_2_3_and_4_rows_identical_to_p222_record():
    founded = subprocess.run(
        ["git", "show", BASE + ":docs/PARITY_MATRIX_2026-11-10.md"],
        cwd=REPO, capture_output=True, text=True, check=True).stdout
    import tempfile
    with tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False, encoding="utf-8") as fh:
        fh.write(founded)
        founded_path = Path(fh.name)
    try:
        founding_rows = _rows(founded_path)
    finally:
        founded_path.unlink()
    rows = _rows(MATRIX)
    for rid in TRANCHE1 | TRANCHE2 | TRANCHE3 | TRANCHE4:
        assert rows[rid][4] == founding_rows[rid][4], rid
        assert rows[rid][5] == founding_rows[rid][5], rid


def test_08_closing_evidence_citations_resolve():
    rows = _rows(MATRIX)
    for rid in JUDGED:
        cites = re.findall("`([^`]+)`", rows[rid][5])
        assert cites, rid
        for cite in cites:
            assert (REPO / cite).is_file(), (rid, cite)


def test_09_section3_counts_equal_recount():
    rows = _rows(MATRIX)
    text = MATRIX.read_text(encoding="utf-8")
    flat = " ".join(_section(text, "## " + S + "3").split())
    got5 = _count_line(flat, "Tranche 5 closing counts")
    assert got5 == _as_tuple(_counts(rows, TRANCHE5), len(TRANCHE5))
    label = "Cumulative judged counts [(]tranches 1, 2, 3, 4 and 5[)]"
    gotc = _count_line(flat, label)
    judged5 = TRANCHE1 | TRANCHE2 | TRANCHE3 | TRANCHE4 | TRANCHE5
    assert gotc == _as_tuple(_counts(rows, judged5), len(judged5))
    # P-224 heal: restated to the cumulative tranches 1-6 truth.
    got6 = _count_line(flat, "Tranche 6 closing counts")
    assert got6 == _as_tuple(_counts(rows, TRANCHE6), len(TRANCHE6))
    label6 = "Cumulative judged counts [(]tranches 1, 2, 3, 4, 5 and 6[)]"
    gotc6 = _count_line(flat, label6)
    judged6 = TRANCHE1 | TRANCHE2 | TRANCHE3 | TRANCHE4 | TRANCHE5 | TRANCHE6
    assert gotc6 == _as_tuple(_counts(rows, judged6), len(judged6))
    # P-225 heal: restated to the cumulative tranches 1-7 truth.
    got7 = _count_line(flat, "Tranche 7 closing counts")
    assert got7 == _as_tuple(_counts(rows, TRANCHE7), len(TRANCHE7))
    label7 = "Cumulative judged counts [(]tranches 1, 2, 3, 4, 5, 6 and 7[)]"
    gotc7 = _count_line(flat, label7)
    judged7 = TRANCHE1 | TRANCHE2 | TRANCHE3 | TRANCHE4 | TRANCHE5 | TRANCHE6 | TRANCHE7
    assert gotc7 == _as_tuple(_counts(rows, judged7), len(judged7))
    # P-226 heal: restated to the cumulative tranches 1-8 truth.
    got8 = _count_line(flat, "Tranche 8 closing counts")
    assert got8 == _as_tuple(_counts(rows, TRANCHE8), len(TRANCHE8))
    label8 = "Cumulative judged counts [(]tranches 1, 2, 3, 4, 5, 6, 7 and 8[)]"
    gotc8 = _count_line(flat, label8)
    assert gotc8 == _as_tuple(_counts(rows, JUDGED8), len(JUDGED8))
    # P-227 heal: restated to the cumulative tranches 1-9 truth.
    got9 = _count_line(flat, "Tranche 9 closing counts")
    assert got9 == _as_tuple(_counts(rows, TRANCHE9), len(TRANCHE9))
    label9 = "Cumulative judged counts [(]tranches 1, 2, 3, 4, 5, 6, 7, 8 and 9[)]"
    gotc9 = _count_line(flat, label9)
    assert gotc9 == _as_tuple(_counts(rows, JUDGED), len(JUDGED))
    remainder = sum(1 for rid, cells in rows.items()
                    if rid not in JUDGED
                    and cells[4] == "NOT-YET-REJUDGED")
    m = re.search("Unjudged remainder: ([0-9]+) rows NOT-YET-REJUDGED.", flat)
    assert m and int(m.group(1)) == remainder
    assert remainder == 141 - len(JUDGED)


def test_10_deliberately_different_rows_carry_disposition():
    text = MATRIX.read_text(encoding="utf-8")
    rows = _rows(MATRIX)
    s4 = _section(text, "## " + S + "4")
    flat = " ".join(_section(text, "## " + S + "3").split())
    for rid in ("VX-01", "VX-59"):
        assert rows[rid][2] == "DELIBERATELY-DIFFERENT", rid
        assert rows[rid][4] == "NOT-YET-REJUDGED", rid
        assert rid in s4, rid
    assert rows["VX-42"][2] == "DELIBERATELY-DIFFERENT"
    assert _closing_token(rows["VX-42"]) == "SHIPPED-SOVEREIGN"
    assert "VX-42" in s4
    assert "P-231's end-to-end audit" in flat
    assert "sovereign shape" in s4


def test_11_no_citation_points_outside_the_repo():
    text = MATRIX.read_text(encoding="utf-8")
    assert "http://" not in text
    assert "https://" not in text


def test_12_clean_room_log_p223_p222_p221_p220_p219_entries_exactly_once():
    log = CLEAN_ROOM_LOG.read_text(encoding="utf-8")
    assert len(re.findall("(?m)^- [*][*]P-223 [(]", log)) == 1
    assert len(re.findall("(?m)^- [*][*]P-222 [(]", log)) == 1
    assert len(re.findall("(?m)^- [*][*]P-221 [(]", log)) == 1
    assert len(re.findall("(?m)^- [*][*]P-220 [(]", log)) == 1
    assert len(re.findall("(?m)^- [*][*]P-219 [(]", log)) == 1


def test_13_every_verdict_token_used_is_defined_in_s1():
    text = MATRIX.read_text(encoding="utf-8")
    s1 = _section(text, "## " + S + "1")
    rows = _rows(MATRIX)
    used = set()
    for cells in rows.values():
        used.add(cells[2])
        used.add(_closing_token(cells))
    assert used <= ALL_TOKENS, used
    for token in ALL_TOKENS:
        assert token in s1, token


def test_14_s0_disclaimer_principle4_and_p223_base_truth():
    text = MATRIX.read_text(encoding="utf-8")
    s0 = _section(text, "## " + S + "0")
    assert "DERIVED" in s0
    assert "says plainly which shape shipped" in s0
    assert "P-223" in s0
    assert "0042" in s0
    assert "356/439" in s0
    assert "6293" in s0
    assert "2566117" in s0


def test_15_s2_tranche_map_names_all_and_p223_judged():
    text = MATRIX.read_text(encoding="utf-8")
    s2 = _section(text, "## " + S + "2")
    for n in range(219, 233):
        assert "P-%d" % n in s2, n
    assert "P-223 judged" in s2
    assert "Part VI" in s2


def test_16_s4_carried_items_named_with_dispositions():
    text = MATRIX.read_text(encoding="utf-8")
    s4 = _section(text, "## " + S + "4")
    low = s4.lower()
    assert "D1" in s4 and "FENCED" in s4
    assert "per-swipe" in low and "DECLINED-PENDING-WORD" in s4
    for item in ("K-A", "K-B", "K-C"):
        assert item in s4, item
    assert "NAMED OPEN" in s4
    assert "bot runtime" in low and "substrateless" in low
    assert "None is claimed resolved" in s4


def test_17_tranche5_rows_name_the_gap_or_the_sovereign_shape():
    rows = _rows(MATRIX)
    for rid in TRANCHE5:
        cells = rows[rid]
        token = _closing_token(cells)
        depth = cells[4].split(" - ", 1)[1] if " - " in cells[4] else ""
        if token == "HAVE-THIN":
            assert depth.strip(), rid
            assert "still missing" in cells[4], rid
        if token == "MISSING":
            assert depth.strip(), rid
        if token == "SHIPPED-SOVEREIGN":
            assert depth.strip(), rid
            assert "sovereign shape" in cells[4], rid


def test_18_section3_tranche_note_lists_rows_and_borderlines():
    text = MATRIX.read_text(encoding="utf-8")
    flat = " ".join(_section(text, "## " + S + "3").split())
    m = re.search("rows judged in tranche 5 are ([^.]+)[.]", flat)
    assert m, flat
    listed = set(re.findall("(?:ST|VX)-[0-9]{2}", m.group(1)))
    assert listed == TRANCHE5, listed
    assert "ST-27 is judged in tranche 5 under the keeper's Q1 ruling" in flat
    assert "VX-26 is judged in tranche 5 under the keeper's Q2 ruling" in flat
    assert "VX-42 is judged in tranche 5 under the keeper's Q3" in flat
    assert "SHIPPED-SOVEREIGN" in flat and "P-231" in flat
    assert "ST-59 is not judged in tranche 5" in flat
    assert "P-231 reconciliation" in flat
    assert "judged here once on their Part VI slice homes" in flat
    for rid in ("ST-65", "VX-34", "VX-51", "VX-66"):
        assert rid in flat, rid
