"""P-219 - The parity matrix, founded (Part XIV opening slice).

Pins for docs/PARITY_MATRIX_2026-11-10.md: the full 141-row
universe of the P-004 Delta Table carried verbatim (opening
verdicts and road homes), closing judgements for tranche 1
only (road home = Part II), every other row printed
NOT-YET-REJUDGED, evidence citations resolving inside this
repo, and the section-3 counts equal to a mechanical recount.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MATRIX = REPO / "docs" / "PARITY_MATRIX_2026-11-10.md"
DELTA = REPO / "docs" / "DELTA_TABLE_2026-10-30.md"
CLEAN_ROOM_LOG = REPO / "docs" / "CLEAN_ROOM_LOG_2026-10-30.md"

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
TRANCHE10 = {
    "VX-54", "VX-55", "VX-56", "VX-57", "VX-58",
}
TRANCHE10_HAVE_THIN = {"VX-54"}
TRANCHE10_MISSING = TRANCHE10 - TRANCHE10_HAVE_THIN
JUDGED8 = TRANCHE1 | TRANCHE2 | TRANCHE3 | TRANCHE4 | TRANCHE5 | TRANCHE6 | TRANCHE7 | TRANCHE8
JUDGED9 = JUDGED8 | TRANCHE9
JUDGED = JUDGED9 | TRANCHE10
DD_ROWS = ("VX-01", "VX-42", "VX-59")
CLOSING_TOKENS = {
    "HAVE", "HAVE-THIN", "MISSING", "SHIPPED-SOVEREIGN",
    "NOT-YET-REJUDGED",
}
ALL_TOKENS = CLOSING_TOKENS | {"DELIBERATELY-DIFFERENT"}


def _rows(path):
    rows = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\| ((?:ST|VX)-\d{2}) \|", line)
        if not m:
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        assert m.group(1) not in rows, m.group(1)
        rows[m.group(1)] = cells
    return rows


def _section(text, heading):
    start = text.index(heading)
    rest = text[start + len(heading):]
    nxt = rest.find("\n## ")
    return rest if nxt == -1 else rest[:nxt]


def _closing_token(cells):
    return cells[4].split(" - ")[0]


def test_01_schema_sections_present():
    text = MATRIX.read_text(encoding="utf-8")
    for heading in ("## \u00a70 Method", "## \u00a71 Verdict vocabulary",
                    "## \u00a72 The tranche map", "## \u00a73 Summary counts",
                    "## Table A", "## Table B", "## \u00a74 Carried items"):
        assert heading in text, heading


def test_02_st_row_ids_exactly_once():
    rows = _rows(MATRIX)
    st = sorted(r for r in rows if r.startswith("ST-"))
    assert st == [f"ST-{n:02d}" for n in range(1, 75)]


def test_03_vx_row_ids_exactly_once():
    rows = _rows(MATRIX)
    vx = sorted(r for r in rows if r.startswith("VX-"))
    assert vx == [f"VX-{n:02d}" for n in range(1, 68)]


def test_04_opening_verdicts_and_homes_match_delta():
    matrix = _rows(MATRIX)
    delta = _rows(DELTA)
    assert set(matrix) == set(delta)
    for rid, dcells in delta.items():
        mcells = matrix[rid]
        assert mcells[1] == dcells[1], rid  # feature, verbatim
        assert mcells[2] == dcells[2], rid  # opening verdict
        assert mcells[3] == dcells[4], rid  # road home, verbatim


def test_05_tranche1_rows_carry_closing_verdicts():
    rows = _rows(MATRIX)
    for rid in JUDGED:
        token = _closing_token(rows[rid])
        assert token in CLOSING_TOKENS, rid
        assert token != "NOT-YET-REJUDGED", rid


def test_06_non_tranche_rows_exactly_not_yet_rejudged():
    rows = _rows(MATRIX)
    for rid, cells in rows.items():
        if rid in JUDGED:
            continue
        assert cells[4] == "NOT-YET-REJUDGED", rid


def test_07_closing_evidence_citations_resolve():
    rows = _rows(MATRIX)
    for rid in TRANCHE1:
        cites = re.findall(r"`([^`]+)`", rows[rid][5])
        assert cites, rid
        for cite in cites:
            assert (REPO / cite).is_file(), (rid, cite)


def test_08_section3_counts_equal_recount():
    rows = _rows(MATRIX)
    counts = {t: 0 for t in CLOSING_TOKENS}
    for rid in JUDGED:
        counts[_closing_token(rows[rid])] += 1
    remainder = sum(
        1 for rid, cells in rows.items()
        if rid not in JUDGED and cells[4] == "NOT-YET-REJUDGED")
    text = MATRIX.read_text(encoding="utf-8")
    flat = " ".join(_section(text, "## \u00a73").split())
    # P-224 heal: the tranches 1-5 line is pinned against the
    # tranche 1-5 subset recount; the cumulative tranches 1-6
    # line is pinned against the full JUDGED recount below,
    # at equal strength.
    judged5 = TRANCHE1 | TRANCHE2 | TRANCHE3 | TRANCHE4 | TRANCHE5
    counts5 = {t: 0 for t in CLOSING_TOKENS}
    for rid in judged5:
        counts5[_closing_token(rows[rid])] += 1
    m = re.search(
        r"Cumulative judged counts \(tranches 1, 2, 3, 4 and 5\): HAVE (\d+), "
        r"HAVE-THIN (\d+), MISSING (\d+), SHIPPED-SOVEREIGN (\d+), "
        r"NOT-YET-REJUDGED (\d+), of (\d+) rows\.", flat)
    assert m, flat
    got = tuple(int(g) for g in m.groups())
    assert got == (counts5["HAVE"], counts5["HAVE-THIN"],
                   counts5["MISSING"], counts5["SHIPPED-SOVEREIGN"],
                   counts5["NOT-YET-REJUDGED"], len(judged5))
    m6 = re.search(
        r"Cumulative judged counts \(tranches 1, 2, 3, 4, 5 and 6\): HAVE (\d+), "
        r"HAVE-THIN (\d+), MISSING (\d+), SHIPPED-SOVEREIGN (\d+), "
        r"NOT-YET-REJUDGED (\d+), of (\d+) rows\.", flat)
    assert m6, flat
    got6 = tuple(int(g) for g in m6.groups())
    judged6 = TRANCHE1 | TRANCHE2 | TRANCHE3 | TRANCHE4 | TRANCHE5 | TRANCHE6
    counts6 = {t: 0 for t in CLOSING_TOKENS}
    for rid in judged6:
        counts6[_closing_token(rows[rid])] += 1
    assert got6 == (counts6["HAVE"], counts6["HAVE-THIN"],
                    counts6["MISSING"], counts6["SHIPPED-SOVEREIGN"],
                    counts6["NOT-YET-REJUDGED"], len(judged6))
    # P-225 heal: the cumulative tranches 1-7 line is pinned
    # against the full JUDGED recount, at equal strength.
    m7 = re.search(
        r"Cumulative judged counts \(tranches 1, 2, 3, 4, 5, 6 and 7\): HAVE (\d+), "
        r"HAVE-THIN (\d+), MISSING (\d+), SHIPPED-SOVEREIGN (\d+), "
        r"NOT-YET-REJUDGED (\d+), of (\d+) rows\.", flat)
    assert m7, flat
    got7 = tuple(int(g) for g in m7.groups())
    # P-226 heal: the tranches 1-7 line is re-pinned against
    # the judged7 subset recount, at equal strength.
    judged7 = TRANCHE1 | TRANCHE2 | TRANCHE3 | TRANCHE4 | TRANCHE5 | TRANCHE6 | TRANCHE7
    counts7 = {t: 0 for t in CLOSING_TOKENS}
    for rid in judged7:
        counts7[_closing_token(rows[rid])] += 1
    assert got7 == (counts7["HAVE"], counts7["HAVE-THIN"],
                    counts7["MISSING"], counts7["SHIPPED-SOVEREIGN"],
                    counts7["NOT-YET-REJUDGED"], len(judged7))
    # P-226 heal: the cumulative tranches 1-8 line is pinned
    # against the full JUDGED recount, at equal strength.
    m8 = re.search(
        r"Cumulative judged counts \(tranches 1, 2, 3, 4, 5, 6, 7 and 8\): HAVE (\d+), "
        r"HAVE-THIN (\d+), MISSING (\d+), SHIPPED-SOVEREIGN (\d+), "
        r"NOT-YET-REJUDGED (\d+), of (\d+) rows\.", flat)
    assert m8, flat
    got8 = tuple(int(g) for g in m8.groups())
    # P-227 heal: the tranches 1-8 line is re-pinned against
    # the judged8 subset recount, at equal strength.
    counts8 = {t: 0 for t in CLOSING_TOKENS}
    for rid in JUDGED8:
        counts8[_closing_token(rows[rid])] += 1
    assert got8 == (counts8["HAVE"], counts8["HAVE-THIN"],
                    counts8["MISSING"], counts8["SHIPPED-SOVEREIGN"],
                    counts8["NOT-YET-REJUDGED"], len(JUDGED8))
    # P-227 heal: the cumulative tranches 1-9 line is pinned
    # against the full JUDGED recount, at equal strength.
    m9 = re.search(
        r"Cumulative judged counts \(tranches 1, 2, 3, 4, 5, 6, 7, 8 and 9\): HAVE (\d+), "
        r"HAVE-THIN (\d+), MISSING (\d+), SHIPPED-SOVEREIGN (\d+), "
        r"NOT-YET-REJUDGED (\d+), of (\d+) rows\.", flat)
    assert m9, flat
    got9 = tuple(int(g) for g in m9.groups())
    # P-228 heal: the tranches 1-9 line is re-pinned against
    # the judged9 subset recount, at equal strength.
    counts9 = {t: 0 for t in CLOSING_TOKENS}
    for rid in JUDGED9:
        counts9[_closing_token(rows[rid])] += 1
    assert got9 == (counts9["HAVE"], counts9["HAVE-THIN"],
                    counts9["MISSING"], counts9["SHIPPED-SOVEREIGN"],
                    counts9["NOT-YET-REJUDGED"], len(JUDGED9))
    # P-228 heal: the cumulative tranches 1-10 line is pinned
    # against the full JUDGED recount, at equal strength.
    m10 = re.search(
        r"Cumulative judged counts \(tranches 1, 2, 3, 4, 5, 6, 7, 8, 9 and 10\): HAVE (\d+), "
        r"HAVE-THIN (\d+), MISSING (\d+), SHIPPED-SOVEREIGN (\d+), "
        r"NOT-YET-REJUDGED (\d+), of (\d+) rows\.", flat)
    assert m10, flat
    got10 = tuple(int(g) for g in m10.groups())
    assert got10 == (counts["HAVE"], counts["HAVE-THIN"],
                    counts["MISSING"], counts["SHIPPED-SOVEREIGN"],
                    counts["NOT-YET-REJUDGED"], len(JUDGED))
    m2 = re.search(r"Unjudged remainder: (\d+) rows NOT-YET-REJUDGED\.", flat)
    assert m2 and int(m2.group(1)) == remainder


def test_09_deliberately_different_rows_carry_disposition():
    text = MATRIX.read_text(encoding="utf-8")
    rows = _rows(MATRIX)
    s4 = _section(text, "## \u00a74")
    for rid in ("VX-01", "VX-59"):
        assert rows[rid][2] == "DELIBERATELY-DIFFERENT", rid
        assert rows[rid][4] == "NOT-YET-REJUDGED", rid
        assert rid in s4, rid
    # Heal class 5 (keeper ruling, 2026-11-10): VX-42 closed
    # SHIPPED-SOVEREIGN at P-223 under ruling Q3, superseding
    # the pre-ruling blanket pin. Pin its exact closing
    # verdict - strictly stronger than the pin it replaces -
    # with P-231's end-to-end audit of the DD rows preserved.
    assert rows["VX-42"][2] == "DELIBERATELY-DIFFERENT"
    assert _closing_token(rows["VX-42"]) == "SHIPPED-SOVEREIGN"
    assert "VX-42" in s4
    flat_dd = " ".join(_section(text, "## " + chr(167) + "3").split())
    assert "P-231's end-to-end audit" in flat_dd
    assert "sovereign shape" in s4


def test_10_no_citation_points_outside_the_repo():
    text = MATRIX.read_text(encoding="utf-8")
    assert "http://" not in text
    assert "https://" not in text


def test_11_clean_room_log_p219_entry_exactly_once():
    log = CLEAN_ROOM_LOG.read_text(encoding="utf-8")
    assert len(re.findall(r"(?m)^- \*\*P-219 \(", log)) == 1


def test_12_every_verdict_token_used_is_defined_in_s1():
    text = MATRIX.read_text(encoding="utf-8")
    s1 = _section(text, "## \u00a71")
    rows = _rows(MATRIX)
    used = set()
    for cells in rows.values():
        used.add(cells[2])
        used.add(_closing_token(cells))
    assert used <= ALL_TOKENS, used
    for token in ALL_TOKENS:
        assert token in s1, token


def test_13_s0_derived_disclaimer_and_principle4():
    text = MATRIX.read_text(encoding="utf-8")
    s0 = _section(text, "## \u00a70")
    assert "DERIVED" in s0
    assert "says plainly which shape shipped" in s0


def test_14_s0_base_truth_line():
    text = MATRIX.read_text(encoding="utf-8")
    s0 = _section(text, "## \u00a70")
    assert "0042" in s0
    assert "356/439" in s0
    assert "6223" in s0


def test_15_s2_tranche_map_names_all_part_xiv_slices():
    text = MATRIX.read_text(encoding="utf-8")
    s2 = _section(text, "## \u00a72")
    for n in range(219, 233):
        assert f"P-{n}" in s2, n


def test_16_s4_carried_items_named_with_dispositions():
    text = MATRIX.read_text(encoding="utf-8")
    s4 = _section(text, "## \u00a74")
    low = s4.lower()
    assert "D1" in s4 and "FENCED" in s4
    assert "per-swipe" in low and "DECLINED-PENDING-WORD" in s4
    for item in ("K-A", "K-B", "K-C"):
        assert item in s4, item
    assert "NAMED OPEN" in s4
    assert "bot runtime" in low and "substrateless" in low
    assert "None is claimed resolved" in s4
