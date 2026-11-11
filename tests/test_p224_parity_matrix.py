"""P-224 - Parity matrix tranche 6: the Part VII rows, re-judged.

Pins for docs/PARITY_MATRIX_2026-11-10.md after the P-224
tranche-6 update: the tranche-6 rows (road home = Part VII,
plus VX-11 included as HAVE-THIN under the keeper's Q1 and
Q2 rulings - the P-014 definition queue homed VX-11 to
Part VII and Part VII built its substance, the
character-asks half staying open as the P-116 gate's item
K1) carry closing verdicts with evidence citations
resolving inside this repo, every other unjudged row keeps
the explicit NOT-YET-REJUDGED marker, the tranche-1,
tranche-2, tranche-3, tranche-4 and tranche-5 judgements
are identical to the P-223 banking record, and the
section-3 counts (tranche 6, cumulative, remainder) equal
a mechanical recount.
"""
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MATRIX = REPO / "docs" / "PARITY_MATRIX_2026-11-10.md"
DELTA = REPO / "docs" / "DELTA_TABLE_2026-10-30.md"
CLEAN_ROOM_LOG = REPO / "docs" / "CLEAN_ROOM_LOG_2026-10-30.md"
BASE = "d940375c7dcf3f2786b994e3a31de6073acc0e55"
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
TRANCHE10 = {
    "VX-54", "VX-55", "VX-56", "VX-57", "VX-58",
}
TRANCHE10_HAVE_THIN = {"VX-54"}
TRANCHE10_MISSING = TRANCHE10 - TRANCHE10_HAVE_THIN
TRANCHE11 = {
    "VX-59", "VX-61",
}
TRANCHE12 = {
    "ST-55", "VX-07", "VX-65", "VX-67",
}
TRANCHE11_HAVE_THIN = {"VX-61"}
TRANCHE11_SHIPPED_SOVEREIGN = {"VX-59"}
JUDGED8 = TRANCHE1 | TRANCHE2 | TRANCHE3 | TRANCHE4 | TRANCHE5 | TRANCHE6 | TRANCHE7 | TRANCHE8
JUDGED9 = JUDGED8 | TRANCHE9
JUDGED10 = JUDGED9 | TRANCHE10
JUDGED11 = JUDGED10 | TRANCHE11
# P-231 heal: JUDGED extended with TRANCHE13 (complete at 141).
JUDGED12 = JUDGED11 | TRANCHE12
TRANCHE13 = {
    "ST-01", "ST-11", "ST-12", "ST-19", "ST-21", "ST-24",
    "ST-37", "ST-40", "ST-41", "ST-42", "ST-43", "ST-44",
    "ST-45", "ST-52", "ST-59", "ST-69", "ST-70", "ST-71",
    "ST-72", "ST-73", "VX-01", "VX-09", "VX-15", "VX-19",
    "VX-21", "VX-23", "VX-24", "VX-62", "VX-63", "VX-64",
}
JUDGED = JUDGED12 | TRANCHE13
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


def test_05_tranche6_rows_carry_ruled_closing_verdicts():
    rows = _rows(MATRIX)
    for rid in TRANCHE6:
        token = _closing_token(rows[rid])
        assert token in CLOSING_TOKENS, rid
        # Branch B as ruled: every tranche-6 row closes
        # HAVE-THIN (VX-11 under the keeper's Q2 ruling).
        assert token == "HAVE-THIN", rid


def test_06_rows_outside_tranches_exactly_not_yet_rejudged():
    rows = _rows(MATRIX)
    for rid, cells in rows.items():
        if rid in JUDGED:
            continue
        assert cells[4] == "NOT-YET-REJUDGED", rid


def test_07_tranche1_2_3_4_and_5_rows_identical_to_p223_record():
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
    for rid in TRANCHE1 | TRANCHE2 | TRANCHE3 | TRANCHE4 | TRANCHE5:
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
    got6 = _count_line(flat, "Tranche 6 closing counts")
    assert got6 == _as_tuple(_counts(rows, TRANCHE6), len(TRANCHE6))
    label = "Cumulative judged counts [(]tranches 1, 2, 3, 4, 5 and 6[)]"
    gotc = _count_line(flat, label)
    judged6 = TRANCHE1 | TRANCHE2 | TRANCHE3 | TRANCHE4 | TRANCHE5 | TRANCHE6
    assert gotc == _as_tuple(_counts(rows, judged6), len(judged6))
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
    assert gotc9 == _as_tuple(_counts(rows, JUDGED9), len(JUDGED9))
    # P-228 heal: restated to the cumulative tranches 1-10 truth.
    got10 = _count_line(flat, "Tranche 10 closing counts")
    assert got10 == _as_tuple(_counts(rows, TRANCHE10), len(TRANCHE10))
    label10 = "Cumulative judged counts [(]tranches 1, 2, 3, 4, 5, 6, 7, 8, 9 and 10[)]"
    gotc10 = _count_line(flat, label10)
    assert gotc10 == _as_tuple(_counts(rows, JUDGED10), len(JUDGED10))
    # P-229 heal: restated to the cumulative tranches 1-11 truth.
    got11 = _count_line(flat, "Tranche 11 closing counts")
    assert got11 == _as_tuple(_counts(rows, TRANCHE11), len(TRANCHE11))
    label11 = "Cumulative judged counts [(]tranches 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 and 11[)]"
    gotc11 = _count_line(flat, label11)
    assert gotc11 == _as_tuple(_counts(rows, JUDGED11), len(JUDGED11))
    # P-230 heal: restated to the cumulative tranches 1-12 truth.
    got12 = _count_line(flat, "Tranche 12 closing counts")
    assert got12 == _as_tuple(_counts(rows, TRANCHE12), len(TRANCHE12))
    label12 = "Cumulative judged counts [(]tranches 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 and 12[)]"
    gotc12 = _count_line(flat, label12)
    # P-231 heal: the tranches 1-12 line is re-pinned against
    # the JUDGED12 subset recount, at equal strength.
    assert gotc12 == _as_tuple(_counts(rows, JUDGED12), len(JUDGED12))
    # P-231 heal: restated to the cumulative tranches 1-13 truth.
    got13 = _count_line(flat, "Tranche 13 closing counts")
    assert got13 == _as_tuple(_counts(rows, TRANCHE13), len(TRANCHE13))
    label13 = "Cumulative judged counts [(]tranches 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12 and 13[)]"
    gotc13 = _count_line(flat, label13)
    assert gotc13 == _as_tuple(_counts(rows, JUDGED), len(JUDGED))
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
    # P-229 heal class 5 (keeper class-5 grant, the P-223
    # precedent): VX-59 restated per-row at greater strength
    # to its exact Q2 SHIPPED-SOVEREIGN closing; VX-01 still
    # NOT-YET-REJUDGED; VX-42 pin untouched below.
    # P-231 heal class 5 (keeper class-5 grants Q1/Q2/Q5 plus
    # the Q6 audit restatement): VX-01 restated per-row at
    # greater strength to its exact Q1 SHIPPED-SOVEREIGN
    # closing; the granted gate-DD rows ST-44 / ST-71 / VX-64
    # pinned to their SHIPPED-SOVEREIGN closings; section 4
    # restated (VX-59 corrected to its judged cell).
    assert rows["VX-01"][2] == "DELIBERATELY-DIFFERENT"
    assert _closing_token(rows["VX-01"]) == "SHIPPED-SOVEREIGN"
    assert _closing_token(rows["ST-44"]) == "SHIPPED-SOVEREIGN"
    assert _closing_token(rows["ST-71"]) == "SHIPPED-SOVEREIGN"
    assert _closing_token(rows["VX-64"]) == "SHIPPED-SOVEREIGN"
    s4flat231 = " ".join(s4.split())
    assert "local owner-scoped registry over sealed local packs" in s4flat231
    assert "signed local packs" not in s4flat231
    assert "VX-01" in s4
    assert rows["VX-59"][2] == "DELIBERATELY-DIFFERENT"
    assert _closing_token(rows["VX-59"]) == "SHIPPED-SOVEREIGN"
    assert "VX-59" in s4
    assert rows["VX-42"][2] == "DELIBERATELY-DIFFERENT"
    assert _closing_token(rows["VX-42"]) == "SHIPPED-SOVEREIGN"
    assert "VX-42" in s4
    assert "P-231's end-to-end audit" in flat
    assert "sovereign shape" in s4


def test_11_no_citation_points_outside_the_repo():
    text = MATRIX.read_text(encoding="utf-8")
    assert "http://" not in text
    assert "https://" not in text


def test_12_clean_room_log_p224_p223_p222_p221_p220_p219_entries_exactly_once():
    log = CLEAN_ROOM_LOG.read_text(encoding="utf-8")
    assert len(re.findall("(?m)^- [*][*]P-224 [(]", log)) == 1
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


def test_14_s0_disclaimer_principle4_and_p224_base_truth():
    text = MATRIX.read_text(encoding="utf-8")
    s0 = _section(text, "## " + S + "0")
    assert "DERIVED" in s0
    assert "says plainly which shape shipped" in s0
    assert "P-224" in s0
    assert "0042" in s0
    assert "356/439" in s0
    assert "6311" in s0
    assert "d940375" in s0


def test_15_s2_tranche_map_names_all_and_p224_judged():
    text = MATRIX.read_text(encoding="utf-8")
    s2 = _section(text, "## " + S + "2")
    for n in range(219, 233):
        assert "P-%d" % n in s2, n
    assert "P-224 judged" in s2
    assert "Part VII" in s2


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


def test_17_tranche6_rows_name_the_gap_or_the_sovereign_shape():
    rows = _rows(MATRIX)
    for rid in TRANCHE6:
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
    m = re.search("rows judged in tranche 6 are ([^.]+)[.]", flat)
    assert m, flat
    listed = set(re.findall("(?:ST|VX)-[0-9]{2}", m.group(1)))
    assert listed == TRANCHE6, listed
    assert "VX-11 is judged in tranche 6 under the keeper's Q1 ruling" in flat
    assert "verdict HAVE-THIN under the keeper's Q2 ruling" in flat
    assert "VX-09 is not judged in tranche 6" in flat
    assert "P-231 reconciliation" in flat
    assert "VX-58 is left to the Part XI tranche (P-228)" in flat
    assert "keeper's Q3 ruling" in flat
    assert "judged here once on their Part VII homes" in flat
