"""P-230 - Parity matrix tranche 12: the Part XIII rows, re-judged.

Pins for docs/PARITY_MATRIX_2026-11-10.md after the P-230
tranche-12 update: the tranche-12 rows (road home = Part XIII,
4 rows - ST-55, VX-07, VX-65, VX-67; ST-55 MISSING under the
keeper Q1 ruling (all three named acts absent - no welcome
surface, welcome zero-hit tree-wide and / redirects straight
to /chat; no temporary unsaved quick uncarded chat surface;
no default Assistant character - Part XIII's Assistant View
is a reasoning rendering, not that character; the general
chat UI + recent-sorted chat list is other rows' substance,
not this row's acts, VX-48 form) and VX-65 HAVE-THIN under
the keeper Q2 ruling (the per-chat Inspector itself shipped
and was gate-proven in its home part as 4 pure-read documents:
overview, events/actions census, reasoning joins - the row's
core act, VX-54 form; missing depth named: no script log as
log lines, no snippet browser, no Flags/Contexts views (flags
read not_applicable), hidden calls expressly in the
not_recorded family), VX-07 MISSING and VX-67 HAVE-THIN
unbranched) carry their ruled closing verdicts with evidence
citations resolving inside this repo, every other unjudged
row keeps the explicit NOT-YET-REJUDGED marker, the
tranche-1 through tranche-11 judgements are identical to
the P-229 banking record, and the section-3 counts (tranche
12, cumulative, remainder) equal a mechanical recount.
"""
import re
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MATRIX = REPO / "docs" / "PARITY_MATRIX_2026-11-10.md"
DELTA = REPO / "docs" / "DELTA_TABLE_2026-10-30.md"
CLEAN_ROOM_LOG = REPO / "docs" / "CLEAN_ROOM_LOG_2026-10-30.md"
BASE = "dbc6a3141baaaf6a1fd635064d5591c56bc4b303"
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
TRANCHE8_HAVE = {"VX-32"}
TRANCHE8_HAVE_THIN = {
    "VX-02", "VX-05", "VX-08", "VX-28", "VX-29", "VX-31",
    "VX-41",
}
TRANCHE8_MISSING = TRANCHE8 - TRANCHE8_HAVE - TRANCHE8_HAVE_THIN
TRANCHE9 = {
    "VX-48", "VX-49", "VX-52", "VX-53",
}
TRANCHE9_MISSING = TRANCHE9
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
TRANCHE12_HAVE_THIN = {"VX-65", "VX-67"}
TRANCHE12_MISSING = {"ST-55", "VX-07"}
TRANCHE11_HAVE_THIN = {"VX-61"}
TRANCHE11_SHIPPED_SOVEREIGN = {"VX-59"}
JUDGED7 = TRANCHE1 | TRANCHE2 | TRANCHE3 | TRANCHE4 | TRANCHE5 | TRANCHE6 | TRANCHE7
JUDGED8 = JUDGED7 | TRANCHE8
JUDGED9 = JUDGED8 | TRANCHE9
JUDGED10 = JUDGED9 | TRANCHE10
JUDGED11 = JUDGED10 | TRANCHE11
JUDGED = JUDGED11 | TRANCHE12
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


def test_05_tranche12_rows_carry_ruled_closing_verdicts():
    rows = _rows(MATRIX)
    for rid in TRANCHE12:
        token = _closing_token(rows[rid])
        assert token in CLOSING_TOKENS, rid
        if rid in TRANCHE12_HAVE_THIN:
            assert token == "HAVE-THIN", rid
        else:
            assert rid in TRANCHE12_MISSING, rid
            assert token == "MISSING", rid


def test_06_rows_outside_tranches_exactly_not_yet_rejudged():
    rows = _rows(MATRIX)
    for rid, cells in rows.items():
        if rid in JUDGED:
            continue
        assert cells[4] == "NOT-YET-REJUDGED", rid


def test_07_tranche1_to_11_rows_identical_to_p229_record():
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
    for rid in JUDGED11:
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
    got9 = _count_line(flat, "Tranche 9 closing counts")
    assert got9 == _as_tuple(_counts(rows, TRANCHE9), len(TRANCHE9))
    label8 = "Cumulative judged counts [(]tranches 1, 2, 3, 4, 5, 6, 7 and 8[)]"
    got8 = _count_line(flat, label8)
    assert got8 == _as_tuple(_counts(rows, JUDGED8), len(JUDGED8))
    label = "Cumulative judged counts [(]tranches 1, 2, 3, 4, 5, 6, 7, 8 and 9[)]"
    gotc = _count_line(flat, label)
    assert gotc == _as_tuple(_counts(rows, JUDGED9), len(JUDGED9))
    got10 = _count_line(flat, "Tranche 10 closing counts")
    assert got10 == _as_tuple(_counts(rows, TRANCHE10), len(TRANCHE10))
    label10 = "Cumulative judged counts [(]tranches 1, 2, 3, 4, 5, 6, 7, 8, 9 and 10[)]"
    gotc10 = _count_line(flat, label10)
    assert gotc10 == _as_tuple(_counts(rows, JUDGED10), len(JUDGED10))
    got11 = _count_line(flat, "Tranche 11 closing counts")
    assert got11 == _as_tuple(_counts(rows, TRANCHE11), len(TRANCHE11))
    label11 = "Cumulative judged counts [(]tranches 1, 2, 3, 4, 5, 6, 7, 8, 9, 10 and 11[)]"
    gotc11 = _count_line(flat, label11)
    assert gotc11 == _as_tuple(_counts(rows, JUDGED11), len(JUDGED11))
    got12 = _count_line(flat, "Tranche 12 closing counts")
    assert got12 == _as_tuple(_counts(rows, TRANCHE12), len(TRANCHE12))
    label12 = "Cumulative judged counts [(]tranches 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 and 12[)]"
    gotc12 = _count_line(flat, label12)
    assert gotc12 == _as_tuple(_counts(rows, JUDGED), len(JUDGED))
    remainder = sum(1 for rid, cells in rows.items()
                    if rid not in JUDGED
                    and cells[4] == "NOT-YET-REJUDGED")
    m = re.search("Unjudged remainder: ([0-9]+) rows NOT-YET-REJUDGED.", flat)
    assert m and int(m.group(1)) == remainder
    assert remainder == 141 - len(JUDGED)
    assert remainder == 30


def test_10_deliberately_different_rows_carry_disposition():
    text = MATRIX.read_text(encoding="utf-8")
    rows = _rows(MATRIX)
    s4 = _section(text, "## " + S + "4")
    flat = " ".join(_section(text, "## " + S + "3").split())
    # P-230: NO class-5 event (no tranche-12 row is opening
    # DELIBERATELY-DIFFERENT; no class-5 grant given - keeper
    # rulings): the P-229 pin 10 form carried VERBATIM -
    # VX-59 pinned to its exact SHIPPED-SOVEREIGN closing
    # token, VX-01 still NOT-YET-REJUDGED, VX-42 pin
    # untouched below.
    assert rows["VX-01"][2] == "DELIBERATELY-DIFFERENT"
    assert rows["VX-01"][4] == "NOT-YET-REJUDGED"
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


def test_12_clean_room_log_p230_down_to_p219_entries_exactly_once():
    log = CLEAN_ROOM_LOG.read_text(encoding="utf-8")
    for n in range(219, 231):
        pat = "(?m)^- [*][*]P-%d [(]" % n
        assert len(re.findall(pat, log)) == 1, n


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


def test_14_s0_disclaimer_principle4_and_p230_base_truth():
    text = MATRIX.read_text(encoding="utf-8")
    s0 = _section(text, "## " + S + "0")
    assert "DERIVED" in s0
    assert "says plainly which shape shipped" in s0
    assert "P-230" in s0
    assert "0042" in s0
    assert "356/439" in s0
    assert "6419" in s0
    assert "dbc6a31" in s0


def test_15_s2_tranche_map_names_all_and_p230_judged():
    text = MATRIX.read_text(encoding="utf-8")
    s2 = _section(text, "## " + S + "2")
    for n in range(219, 233):
        assert "P-%d" % n in s2, n
    assert "P-230 judged" in s2
    assert "Part XIII" in s2


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


def test_17_tranche12_rows_name_the_gap():
    rows = _rows(MATRIX)
    for rid in TRANCHE12:
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
    m = re.search("rows judged in tranche 12 are ([^.]+)[.]", flat)
    assert m, flat
    listed = set(re.findall("(?:ST|VX)-[0-9]{2}", m.group(1)))
    assert listed == TRANCHE12, listed
    assert "ST-55 is judged in tranche 12" in flat
    assert "keeper's Q1 ruling" in flat
    assert "VX-65 is judged in tranche 12" in flat
    assert "keeper's Q2 ruling" in flat
    assert "VX-66 was already judged in tranche 5" in flat
    assert "VX-17 was already judged in tranche 8" in flat
    assert "VX-56 was already judged in tranche 10" in flat
    assert "not left to P-230" in flat
    assert "not re-judged here" in flat
    assert "judged here once on their Part XIII homes" in flat
