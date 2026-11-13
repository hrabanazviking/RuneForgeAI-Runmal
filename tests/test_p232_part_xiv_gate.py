"""P-232 acceptance: the Part XIV gate battery (G = 35).

Part XIV (The Proof Spine - the parity matrix, published,
DERIVED) closes the way P-218 closed Part XIII: ONE fresh
gate world (ZqxGate232) on which the part's load-bearing
agreements are re-measured, every carried item pinned BY
NAME at full strength, and the thirteen tranche citizen
batteries stood on as neighbours (never duplicated
silently).

Areas: A Census x10, B Together x8, C composed matrix
walk x7, D Accounting x8, hygiene x2.

Honesty lines (design sections 1/5):
- the census the gate pins is derived, not trusted:
  141 rows judged, remainder 0 - HAVE 27 / HAVE-THIN 76 /
  MISSING 32 / SHIPPED-SOVEREIGN 6. A recount disagreeing
  with the banked sources is a STOP, never a heal target.
- Area C is a COMPOSED reader-programme over the
  published matrix as data, not a browser run.
- The S311 goldens are expected UNMOVED at this gate;
  the golden watch runs as a neighbour (H2 + fence).
- The record gaps stand as census facts: P-208 shipped
  a slice doc but no headed clean-room entry; P-209
  shipped neither. The gate pins the record AS IT IS.

Fresh-authored for this gate (P-005 discipline); the
tranche data is imported from the banked tranche
batteries themselves (the cumulative battery
test_p231_parity_matrix carries TRANCHE1..13, the
JUDGED chain and the explicit verdict sets; every
tranche battery restates the same TRANCHE sets, and
A4 proves the restatements agree).
"""

from __future__ import annotations

import hashlib
import importlib.util
import re
import subprocess
from pathlib import Path

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import service as svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.groupchat import store as group_store
from runmal.inspector import OVERVIEW_SCHEMA

REPO = Path(__file__).parent.parent
SRC = REPO / "src" / "runmal"
TESTS = REPO / "tests"
MATRIX = REPO / "docs" / "PARITY_MATRIX_2026-11-10.md"
GATE_DOC = REPO / "docs" / "PART_XIV_GATE_2026-11-10.md"
CAMPAIGN_STATE = REPO / "CAMPAIGN_STATE.md"
CLEAN_ROOM_LOG = REPO / "docs" / "CLEAN_ROOM_LOG_2026-10-30.md"
GROUP_JS = SRC / "web" / "static" / "group.js"
GROUP_HTML = SRC / "web" / "templates" / "group.html"
APP_JS = SRC / "web" / "static" / "app.js"
RENDERER_JS = SRC / "web" / "static" / "renderer.js"
S = chr(167)

P218_RECORD = "c8a054dda09682e584d479d74bae3f149ac41d8e"
BUILD_BASE = "09750a9b02205de582d490c55d2ba8dd8853a303"
P231_BATTERY_BASE = "1ea22aa5c36d2d6dfe0e9f50dfee146030bc10b2"

# The derived census (scout section 2, three sources):
# the gate pins exactly these figures or stops.
EXPECTED_TOTALS = {
    "HAVE": 27, "HAVE-THIN": 76, "MISSING": 32,
    "SHIPPED-SOVEREIGN": 6,
}
EXPECTED_SIZES = (12, 10, 14, 12, 19, 5, 1, 23, 4, 5, 2, 4, 30)
TRANCHE_FILES = tuple(
    f"test_p{218 + n}_parity_matrix.py" for n in range(1, 14))
TRANCHE_COUNTS = (16,) + (18,) * 12
ROMAN = ("II", "III", "IV", "V", "VI", "VII", "VIII",
         "IX", "X", "XI", "XII", "XIII")

GOLDEN_SHA256 = {
    "chat.golden.txt":
        "fd626410ff18feeb276f6b92ff9219ba456283acb1d70e5fa7024bb7d8cd909c",
    "connections.golden.txt":
        "5da18caa330ca0083c347e9d1f8597b0e4eb68397a7f910b088ecf88b6d20b2d",
    "editor.golden.txt":
        "2c1e2dd0739e83274541f6366796b8a3fa3b37c09ab2c4ae0d3be18d9f96bab9",
    "gallery.golden.txt":
        "e588e0d283ced2efd5eaeb0c50ca58230e4e1513343ff6bd17d1f088b1aa842f",
    "group.golden.txt":
        "bef5447cce4839b434ddcc00e8ff6808738975a8e8f4676371c63ac8a8108c3c",
    "inspector.golden.txt":
        "c88e22e8b4fcdf6f672a81b9f0ba6bc4b2ea9f8226e42fb8f7c5fca4e7b2d74a",
    "lorebooks.golden.txt":
        "e4681c31c2feba872435997365bd338c0be8c9294c3ca168c4874f15ca98a624",
    "tools.golden.txt":
        "be6991e8bf7aa82f3bdfc6d9ce47e89a3d8a8c6a5e7439d28397a138ceed79d8",
}

CARD_ASTA = {
    "name": "ZqxAsta232",
    "description": "Keeper of the mead hall at TESTHOLD.",
    "personality": "Warm but exact.",
    "scenario": "A longhouse hall.",
    "first_mes": "Sit, traveller.",
    "system_prompt": "You are Asta of TESTHOLD.",
}
CARD_BRAM = {
    "name": "ZqxBram232",
    "description": "Keeper of the bridge at TESTHOLD.",
    "personality": "Stern but fair.",
    "scenario": "A stone bridge over a cold river.",
    "first_mes": "State your business.",
    "system_prompt": "You are Bram of TESTHOLD.",
}
NOTE_TEXT = "ZqxGate232TideNote"
CONTENT_A = "ZqxGate232RecordedAnswer"
THINK_A = "ZqxGate232ChatThinking"

SCENARIO_BODY = {
    "name": "Harbour Lights at Dusk",
    "description": "A quiet harbour, first evening.",
    "scenario_text": "The ferry has just left.",
    "flow": "story",
    "style": "storytelling",
    "narrator_name": "The Harbour Voice",
    "impersonation_name": "Ash",
    "roles": [
        {"name": "Narrator", "character_name": "Maera",
         "enabled_on_start": True, "can_speak": True},
    ],
    "bootstrap_messages": [
        {"kind": "note", "text": NOTE_TEXT, "role": "Narrator"},
    ],
    "initial_flags": {"met_maera": True},
    "initial_variables": {"trust": 2},
}


def _load_battery(filename):
    path = TESTS / filename
    spec = importlib.util.spec_from_file_location(
        path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


P231 = _load_battery("test_p231_parity_matrix.py")
TRANCHES = tuple(
    getattr(P231, f"TRANCHE{n}") for n in range(1, 14))
UNIVERSE = P231.JUDGED


def _verdict_map():
    """The battery-data verdict for every row the batteries
    carry as explicit sets or uniform rules (tranches
    6..13). Tranches 1..5 carry their rows as split counts
    plus founding text; B1 pins those against the founding
    text the P-231 battery itself pins (its BASE)."""
    verdicts = {}
    for rid in TRANCHES[5]:
        verdicts[rid] = "HAVE-THIN"  # P-224 battery, Q2 rule
    for rid in TRANCHES[6]:
        verdicts[rid] = "HAVE-THIN"  # P-225 battery, Q1 rule
    for rid in TRANCHES[7]:
        if rid in P231.TRANCHE8_HAVE:
            verdicts[rid] = "HAVE"
        elif rid in P231.TRANCHE8_HAVE_THIN:
            verdicts[rid] = "HAVE-THIN"
        else:
            assert rid in P231.TRANCHE8_MISSING, rid
            verdicts[rid] = "MISSING"
    for rid in TRANCHES[8]:
        verdicts[rid] = "MISSING"  # TRANCHE9_MISSING = whole
    for rid in TRANCHES[9]:
        verdicts[rid] = (
            "HAVE-THIN" if rid in P231.TRANCHE10_HAVE_THIN
            else "MISSING")
    for rid in TRANCHES[10]:
        verdicts[rid] = (
            "HAVE-THIN" if rid in P231.TRANCHE11_HAVE_THIN
            else "SHIPPED-SOVEREIGN")
    for rid in TRANCHES[11]:
        verdicts[rid] = (
            "HAVE-THIN" if rid in P231.TRANCHE12_HAVE_THIN
            else "MISSING")
    for rid in TRANCHES[12]:
        if rid in P231.TRANCHE13_HAVE:
            verdicts[rid] = "HAVE"
        elif rid in P231.TRANCHE13_HAVE_THIN:
            verdicts[rid] = "HAVE-THIN"
        elif rid in P231.TRANCHE13_MISSING:
            verdicts[rid] = "MISSING"
        else:
            assert rid in P231.TRANCHE13_SHIPPED_SOVEREIGN, rid
            verdicts[rid] = "SHIPPED-SOVEREIGN"
    return verdicts


VERDICTS = _verdict_map()


def _rows(path):
    return P231._rows(path)


def _closing(cells):
    return P231._closing_token(cells)


def _doc_rows():
    return _rows(MATRIX)


def _section(text, heading):
    return P231._section(text, heading)


def _flat(text):
    return " ".join(text.split())


def _recount(rows, ids):
    counts = {t: 0 for t in EXPECTED_TOTALS}
    for rid in ids:
        counts[_closing(rows[rid])] += 1
    return counts


def _record_sections():
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
    # The records wrap mid-token at hyphens ("HAVE-\nTHIN");
    # the de-hyphenated flat text is the tally surface.
    return _flat(section).replace("- ", "-")


def _cumulative(section):
    match = re.search(
        r"Cumulative judged (\d+) rows: HAVE (\d+) / "
        r"HAVE-THIN (\d+) / MISSING (\d+) / "
        r"SHIPPED-SOVEREIGN (\d+)", _tally_flat(section))
    assert match, "record carries no cumulative tally line"
    return tuple(int(g) for g in match.groups())


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0042"
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    client = TestClient(create_app(factory))
    client.factory = factory
    client.db_path = db_path
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    client.token = token
    return client


def census(client):
    paths = client.get("/openapi.json").json()["paths"]
    operations = sum(
        len([k for k in methods
             if k in ("get", "post", "put", "delete", "patch")])
        for methods in paths.values()
    )
    return paths, operations


def walk_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from walk_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_keys(item)


def chat_messages(client, chat_id):
    resp = client.get(f"/api/v1/chats/{chat_id}/messages")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    return rows["messages"] if isinstance(rows, dict) else rows


def build_world(client):
    """ZqxGate232, fresh-authored for this gate: one owner,
    two characters, one chat carrying a bound scenario
    whose bootstrap note is the chat's first stored
    message (the VX-32 surface), and one recorded-
    reasoning message for the Inspector legs."""
    world = {}
    asta = client.post(
        "/api/v1/characters", json={"card": dict(CARD_ASTA)})
    assert asta.status_code == 201, asta.text
    bram = client.post(
        "/api/v1/characters", json={"card": dict(CARD_BRAM)})
    assert bram.status_code == 201, bram.text
    world["asta_id"] = asta.json()["id"]
    world["bram_id"] = bram.json()["id"]
    created = client.post(
        "/api/v1/chats", json={"title": "ZqxGate232 Saga"})
    assert created.status_code == 201, created.text
    chat_id = created.json()["id"]
    world["chat_id"] = chat_id
    definition = client.post(
        "/api/v1/scenarios", json=dict(SCENARIO_BODY))
    assert definition.status_code == 201, definition.text
    bound = client.post(
        f"/api/v1/scenarios/{definition.json()['id']}/bind",
        json={"chat_id": chat_id})
    assert bound.status_code == 201, bound.text
    world["scenario_binding_id"] = bound.json()["id"]
    resp = client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"role": "assistant", "content": CONTENT_A,
              "reasoning": {"status": "recorded",
                            "text": THINK_A}})
    assert resp.status_code == 201, resp.text
    world["message_ids"] = [
        m["id"] for m in chat_messages(client, chat_id)]
    return world


def group_js_segment(name):
    text = GROUP_JS.read_text(encoding="utf-8")
    start = text.index(f"function {name}(")
    boundaries = [
        text.find("\nfunction ", start + 1),
        text.find("\nasync function ", start + 1),
        text.find('\n$("group-form")', start + 1),
    ]
    ends = [b for b in boundaries if b > start]
    end = min(ends) if ends else len(text)
    return text[start:end]


def submit_segment():
    text = GROUP_JS.read_text(encoding="utf-8")
    start = text.index('$("group-form")')
    end = text.index("\nloadRoster()", start)
    return text[start:end]


# -- Area A: Census x10 -----------------------------------------------------


def test_a1_row_universe_exactly_141():
    rows = _doc_rows()
    assert len(rows) == 141
    st = sorted(r for r in rows if r.startswith("ST-"))
    vx = sorted(r for r in rows if r.startswith("VX-"))
    assert st == [f"ST-{n:02d}" for n in range(1, 75)]
    assert vx == [f"VX-{n:02d}" for n in range(1, 68)]
    assert set(rows) == UNIVERSE


def test_a2_finality_zero_not_yet_rejudged():
    rows = _doc_rows()
    for rid, cells in rows.items():
        assert _closing(cells) != "NOT-YET-REJUDGED", rid
        assert _closing(cells) in EXPECTED_TOTALS, rid
    text = MATRIX.read_text(encoding="utf-8")
    flat = _flat(_section(text, "## " + S + "3"))
    assert "Unjudged remainder: 0 rows NOT-YET-REJUDGED." in flat


def test_a3_verdict_totals_exact():
    rows = _doc_rows()
    counts = _recount(rows, rows.keys())
    assert counts == EXPECTED_TOTALS, counts
    assert sum(counts.values()) == 141


def test_a4_tranche_partition_agrees_across_batteries():
    rows = _doc_rows()
    for filename in TRANCHE_FILES:
        module = _load_battery(filename)
        for n in range(1, 14):
            assert getattr(module, f"TRANCHE{n}") == TRANCHES[n - 1], (
                filename, n)
        # P-232 heal: twelve batteries carry JUDGED at
        # module level; test_p220 carries its cumulative
        # chain inside its test bodies, not as module
        # data. The gate pins the identity in the form
        # each battery carries it - the union of its own
        # TRANCHE sets, plus JUDGED itself where defined.
        union = set()
        for n in range(1, 14):
            union |= getattr(module, f"TRANCHE{n}")
        assert union == UNIVERSE, filename
        if hasattr(module, "JUDGED"):
            assert module.JUDGED == UNIVERSE, filename
    for i in range(13):
        for j in range(i + 1, 13):
            assert not (TRANCHES[i] & TRANCHES[j]), (i, j)
    union = set()
    for tranche in TRANCHES:
        union |= tranche
    assert union == set(rows) == UNIVERSE


def test_a5_tranche_sizes_banked():
    # P-232 heal (design section 2, A5): the scout's size
    # shorthand was garbled for tranches 6..8; the sizes
    # pinned here are read from the battery data itself
    # (5, 1, 23) - the tree governs over the shorthand.
    sizes = tuple(len(t) for t in TRANCHES)
    assert sizes == EXPECTED_SIZES, sizes
    assert sum(sizes) == 141


def test_a6_citizen_battery_counts():
    total = 0
    for filename, expected in zip(
            TRANCHE_FILES, TRANCHE_COUNTS, strict=True):
        path = TESTS / filename
        assert path.exists(), filename
        count = len(re.findall(
            r"def test_", path.read_text(encoding="utf-8")))
        assert count == expected, (filename, count, expected)
        total += count
    assert total == 232


def test_a7_clean_room_census_and_gaps():
    log = CLEAN_ROOM_LOG.read_text(encoding="utf-8")
    for n in range(219, 232):
        pat = f"(?m)^- [*][*]P-{n} [(]"
        assert len(re.findall(pat, log)) == 1, n
    headed = set(re.findall(r"(?m)^- \*\*(P-\d{3}) \(", log))
    # The two Part XIII record gaps, pinned AS THEY ARE
    # (the P-218 gate's census fact, restated at the
    # Part XIV gate at equal strength).
    assert "P-208" not in headed
    assert "P-209" not in headed
    assert (REPO / "docs" / "REASONING_GROUPCHAT_2026-11-09.md").exists()
    titled = {}
    for path in (REPO / "docs").glob("*.md"):
        first = path.read_text(encoding="utf-8").splitlines()[0]
        match = re.search(r"\(P-(\d{3})\)", first)
        if match:
            titled.setdefault(f"P-{match.group(1)}", []).append(
                path.name)
    assert titled.get("P-208") == ["REASONING_GROUPCHAT_2026-11-09.md"]
    assert "P-209" not in titled


def test_a8_matrix_doc_structure():
    text = MATRIX.read_text(encoding="utf-8")
    flat3 = _flat(_section(text, "## " + S + "3"))
    positions = []
    for n in range(1, 14):
        label = f"Tranche {n} closing counts"
        assert label in flat3, label
        positions.append(flat3.index(label))
    assert positions == sorted(positions)
    got = P231._count_line(
        flat3,
        "Cumulative judged counts [(]tranches 1, 2, 3, 4, 5, "
        "6, 7, 8, 9, 10, 11, 12 and 13[)]")
    assert got == (27, 76, 32, 6, 0, 141), got
    s2 = _section(text, "## " + S + "2")
    for n in range(219, 233):
        assert f"P-{n}" in s2, n
    assert "P-232 the Part XIV gate" in _flat(s2)
    assert "reconciliation, 30 rows; remainder 0" in _flat(s2)


def test_a9_standing_census(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    paths, operations = census(client)
    assert len(paths) == 356
    assert operations == 439
    assert MIGRATIONS[-1][0] == "0042"
    migrations_dir = SRC / "db" / "migrations"
    assert not [p.name for p in migrations_dir.glob("m0043*")]


def test_a10_part_xiv_touched_no_src():
    out = subprocess.run(
        ["git", "log", "--name-only", "--pretty=format:",
         f"{P218_RECORD}..{BUILD_BASE}"],
        cwd=REPO, capture_output=True, text=True,
        check=True).stdout
    paths = {line.strip() for line in out.splitlines()
             if line.strip()}
    assert paths, "the Part XIV range must not be empty"
    assert not [p for p in paths if p.startswith("src/")], paths
    assert all(
        p.startswith(("docs/", "tests/")) or p == "CAMPAIGN_STATE.md"
        for p in paths), paths


# -- Area B: Together x8 ----------------------------------------------------


def test_b1_row_for_row_doc_equals_battery_data():
    rows = _doc_rows()
    for rid, expected in VERDICTS.items():
        assert _closing(rows[rid]) == expected, rid
    # Tranches 1..5: the batteries carry their rows as
    # split counts over the tranche set plus the founding
    # text; the P-231 battery's own test_07 pins the
    # tranches 1..12 closing cells identical to its BASE
    # text. The gate re-measures exactly that: every
    # tranche 1..5 cell identical to the founding text at
    # the P-231 battery's BASE, and every tranche recount
    # equal to the doc's own section 3 closing line (the
    # line each tranche battery's test_09 asserts).
    founded = subprocess.run(
        ["git", "show",
         P231_BATTERY_BASE + ":docs/PARITY_MATRIX_2026-11-10.md"],
        cwd=REPO, capture_output=True, text=True,
        check=True).stdout
    import tempfile
    with tempfile.NamedTemporaryFile(
            "w", suffix=".md", delete=False,
            encoding="utf-8") as fh:
        fh.write(founded)
        founded_path = Path(fh.name)
    try:
        founding_rows = _rows(founded_path)
    finally:
        founded_path.unlink()
    for tranche in TRANCHES[:5]:
        for rid in tranche:
            assert rows[rid][4] == founding_rows[rid][4], rid
            assert rows[rid][5] == founding_rows[rid][5], rid
    text = MATRIX.read_text(encoding="utf-8")
    flat3 = _flat(_section(text, "## " + S + "3"))
    for n, tranche in enumerate(TRANCHES, start=1):
        got = P231._count_line(flat3, f"Tranche {n} closing counts")
        # P-232 heal: the tuple is built with the banked
        # battery's own _counts (which carries the
        # NOT-YET-REJUDGED key its _as_tuple requires) -
        # stronger than the gate's four-class recount,
        # never weaker.
        assert got == P231._as_tuple(
            P231._counts(rows, tranche), len(tranche)), (n, got)


def test_b2_cumulative_chain():
    rows = _doc_rows()
    chain = (
        ("JUDGED7", 7), ("JUDGED8", 8), ("JUDGED9", 9),
        ("JUDGED10", 10), ("JUDGED11", 11), ("JUDGED12", 12),
    )
    for name, upto in chain:
        expected = set()
        for tranche in TRANCHES[:upto]:
            expected |= tranche
        assert getattr(P231, name) == expected, name
    assert P231.JUDGED == set(rows)
    assert len(P231.JUDGED) == 141


def test_b3_reconciliation_closure():
    rows = _doc_rows()
    assert TRANCHES[12] == set(rows) - P231.JUDGED12
    assert len(TRANCHES[12]) == 30
    assert _recount(rows, TRANCHES[12]) == {
        "HAVE": 13, "HAVE-THIN": 11, "MISSING": 2,
        "SHIPPED-SOVEREIGN": 4}
    assert len(P231.TRANCHE13_HAVE) == 13
    assert len(P231.TRANCHE13_HAVE_THIN) == 11
    assert len(P231.TRANCHE13_MISSING) == 2
    assert len(P231.TRANCHE13_SHIPPED_SOVEREIGN) == 4


def test_b4_have_spotcheck_vx32_bootstrap_live(tmp_path, monkeypatch):
    rows = _doc_rows()
    assert _closing(rows["VX-32"]) == "HAVE"
    client = make_client(tmp_path, monkeypatch)
    world = build_world(client)
    messages = chat_messages(client, world["chat_id"])
    # The authored typed opening line is the chat's first
    # stored message: the shipped VX-32 surface, live.
    assert messages[0]["content"] == NOTE_TEXT
    contents = [m["content"] for m in messages]
    assert CONTENT_A in contents


def test_b5_have_thin_spotcheck_vx65_inspector_live(
        tmp_path, monkeypatch):
    rows = _doc_rows()
    assert _closing(rows["VX-65"]) == "HAVE-THIN"
    client = make_client(tmp_path, monkeypatch)
    world = build_world(client)
    chat_id = world["chat_id"]
    # The shipped core, live: the per-chat Inspector
    # documents answer as pure reads over the gate world.
    overview = client.get(f"/api/v1/inspector/chats/{chat_id}")
    assert overview.status_code == 200, overview.text
    assert overview.json()["schema"] == OVERVIEW_SCHEMA
    events = client.get(
        f"/api/v1/inspector/chats/{chat_id}/events")
    assert events.status_code == 200, events.text
    events_doc = events.json()
    # Hidden calls are named in the document's own
    # not_recorded family - named, never silently absent.
    assert "not_recorded" in set(walk_keys(events_doc))
    # Counts-only by the no-payload law: no stored message
    # content leaks into the events document.
    assert CONTENT_A not in events.text
    assert THINK_A not in events.text
    # The named missing pieces stay absent as VIEWS: the
    # Inspector router carries exactly the four banked
    # GET roads - no Flags view, no Contexts view, no
    # script-log view exists as a road.
    router_text = (SRC / "inspector" / "router.py").read_text(
        encoding="utf-8")
    gets = re.findall(r'@router\.get\("([^"]+)"\)', router_text)
    assert gets == [
        "/inspector/chats/{chat_id}",
        "/inspector/chats/{chat_id}/events",
        "/inspector/chats/{chat_id}/reasoning",
        "/inspector/groups/{group_id}/reasoning",
    ]


def test_b6_missing_spotcheck_vx48_animation_absent(
        tmp_path, monkeypatch):
    rows = _doc_rows()
    assert _closing(rows["VX-48"]) == "MISSING"
    client = make_client(tmp_path, monkeypatch)
    paths, _operations = census(client)
    # No animation road, no animation module: the still
    # picture never moves. The pairing is data only.
    assert not any("anim" in p.lower() for p in paths)
    assert not [p.name for p in SRC.rglob("*.py")
                if "anim" in p.name.lower()]
    roster = _flat((SRC / "faces" / "speaking_roster.py").read_text(
        encoding="utf-8")).lower()
    assert "performs no lip-sync or animation" in roster
    assert "no timing contract exists in-tree" in roster
    census_text = _flat(
        (SRC / "faces" / "speaking_census.py").read_text(
            encoding="utf-8")).lower()
    assert "performs no lip-sync" in census_text
    # The preserved-as-data half stands: the speaking
    # pairing module itself is a shipped citizen.
    assert (SRC / "faces" / "speaking.py").is_file()


def test_b7_shipped_sovereign_spotcheck_vx59_hub_live(
        tmp_path, monkeypatch):
    rows = _doc_rows()
    assert _closing(rows["VX-59"]) == "SHIPPED-SOVEREIGN"
    assert rows["VX-59"][2] == "DELIBERATELY-DIFFERENT"
    client = make_client(tmp_path, monkeypatch)
    build_world(client)
    # The sovereign shape, exercised as shipped: a local
    # owner-scoped registry whose browse, census and
    # unified-search roads answer as pure reads over the
    # packs the operator already holds (here: none yet -
    # the honest empty estate).
    listing = client.get("/api/v1/hub")
    assert listing.status_code == 200, listing.text
    hub_census = client.get("/api/v1/hub/census")
    assert hub_census.status_code == 200, hub_census.text
    search = client.get(
        "/api/v1/hub/unified-search",
        params={"q": "ZqxGate232"})
    assert search.status_code == 200, search.text
    # Stated plainly, as the row's own record states it:
    # the packs ship WITHOUT signatures - no signing or
    # attestation road exists anywhere in the census.
    paths, _operations = census(client)
    assert not any(
        "sign" in p.lower() or "attest" in p.lower()
        for p in paths)


def test_b8_cross_part_composition(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    world = build_world(client)
    chat_id = world["chat_id"]
    # Part IX citizen (VX-32's home): the scenario
    # bootstrap seeded the authored note on this world.
    messages = chat_messages(client, chat_id)
    assert messages[0]["content"] == NOTE_TEXT
    # Part XIII citizen (VX-65's home): the Inspector
    # overview of the very same chat answers on the
    # same world and names the same chat.
    overview = client.get(f"/api/v1/inspector/chats/{chat_id}")
    assert overview.status_code == 200, overview.text
    assert overview.json()["chat_id"] == chat_id
    # Part XII citizen (VX-59's home): the hub's unified
    # search answers for the same owner on the same
    # world - three road-home parts, one world, agreeing.
    search = client.get(
        "/api/v1/hub/unified-search",
        params={"q": "ZqxGate232"})
    assert search.status_code == 200, search.text
    listing = client.get("/api/v1/hub")
    assert listing.status_code == 200, listing.text


# -- Area C: Composed scenario x7 (the published matrix, walked) -------------


def test_c1_walk_loads_doc_as_data():
    text = MATRIX.read_text(encoding="utf-8")
    rows = _doc_rows()
    assert len(rows) == 141
    s1 = _section(text, "## " + S + "1")
    used = set()
    for cells in rows.values():
        used.add(cells[2])
        used.add(_closing(cells))
    assert used <= P231.ALL_TOKENS, used
    for token in P231.ALL_TOKENS:
        assert token in s1, token


def test_c2_walk_groups_by_road_home_part():
    text = MATRIX.read_text(encoding="utf-8")
    s2 = _flat(_section(text, "## " + S + "2"))
    rows = _doc_rows()
    for n in range(1, 13):
        match = re.search(
            rf"tranche {n} = (Part [IVX]+) rows", s2)
        assert match, n
        assert match.group(1) == f"Part {ROMAN[n - 1]}", (
            n, match.group(1))
        for rid in TRANCHES[n - 1]:
            assert _closing(rows[rid]) in EXPECTED_TOTALS, rid
    # The doc's own per-tranche notes list the judged
    # rows for tranches 2..13 (the batteries' test_18
    # form); their union is exactly the complement of
    # tranche 1, whose rows the founding segment carries.
    # P-232 heal: a first-draft leg asserted each row's
    # founding home cell names its tranche's part; the
    # tree contradicts it (VX-03: home "Part X (title
    # only)", judged in tranche 1) - home cells are the
    # P-004 founding assignments and the section 2 map is
    # labelled a sketch, re-derived per slice. The notes
    # form below is the doc's own judged-rows statement,
    # at equal-or-greater strength.
    flat3 = _flat(_section(text, "## " + S + "3"))
    noted = set()
    for n in range(2, 14):
        match = re.search(
            rf"rows judged in tranche {n} are ([^.]+)[.]",
            flat3)
        assert match, n
        listed = set(re.findall(
            r"(?:ST|VX)-[0-9]{2}", match.group(1)))
        assert listed == TRANCHES[n - 1], (n, listed)
        noted |= listed
    assert noted == set(rows) - TRANCHES[0]


def test_c3_walk_verdict_classes():
    rows = _doc_rows()
    doc_classes = {t: set() for t in EXPECTED_TOTALS}
    for rid, cells in rows.items():
        doc_classes[_closing(cells)].add(rid)
    for token, ids in doc_classes.items():
        assert len(ids) == EXPECTED_TOTALS[token], token
    # The battery-data classes agree with the doc classes
    # for every row the batteries carry as data.
    data_classes = {t: set() for t in EXPECTED_TOTALS}
    for rid, token in VERDICTS.items():
        data_classes[token].add(rid)
    for token in EXPECTED_TOTALS:
        assert data_classes[token] <= doc_classes[token], token


def test_c4_walk_row_three_source_agreement():
    rows = _doc_rows()
    sections = _record_sections()
    cases = (
        ("VX-09", 231, "HAVE"),
        ("VX-65", 230, "HAVE-THIN"),
        ("ST-55", 230, "MISSING"),
        ("VX-59", 229, "SHIPPED-SOVEREIGN"),
    )
    for rid, record_n, token in cases:
        # Source 1: the published doc cell.
        assert _closing(rows[rid]) == token, rid
        # Source 2: the owning tranche battery's data.
        assert VERDICTS[rid] == token, rid
        # Source 3: the tranche's banked CAMPAIGN_STATE
        # record names the row, and its cumulative tally
        # (checked whole in the record battery) carries
        # the class.
        section = sections[record_n]
        assert rid in _flat(section), (rid, record_n)
        cumulative = _cumulative(section)
        assert cumulative[0] == sum(
            len(t) for t in TRANCHES[:record_n - 218])
    # The P-231 record states VX-09's ruling verbatim.
    assert "VX-09 = HAVE" in _tally_flat(sections[231])


def test_c5_walk_gate_doc_census_equals_recount():
    rows = _doc_rows()
    gate = _flat(GATE_DOC.read_text(encoding="utf-8"))
    totals = re.search(
        r"HAVE 27 / HAVE-THIN 76 / MISSING 32 / "
        r"SHIPPED-SOVEREIGN 6", gate)
    assert totals, "the gate doc must state the census"
    for n, tranche in enumerate(TRANCHES, start=1):
        counts = _recount(rows, tranche)
        line = (
            f"tranche {n}: HAVE {counts['HAVE']} / "
            f"HAVE-THIN {counts['HAVE-THIN']} / "
            f"MISSING {counts['MISSING']} / "
            f"SHIPPED-SOVEREIGN {counts['SHIPPED-SOVEREIGN']}")
        assert line in gate, line


def test_c6_walk_reconciliation_story():
    text = MATRIX.read_text(encoding="utf-8")
    flat3 = _flat(_section(text, "## " + S + "3"))
    match = re.search(
        r"rows judged in tranche 13 are ([^.]+)[.]", flat3)
    assert match, "the tranche 13 note must list its rows"
    listed = set(re.findall(r"(?:ST|VX)-[0-9]{2}", match.group(1)))
    assert listed == TRANCHES[12], listed
    sections = _record_sections()
    record = _flat(sections[231])
    assert "RECONCILIATION" in record
    assert "the rows no home tranche carried" in record
    assert "dash / NO-HOME / ledger" in record


def test_c7_walk_close_same_141_truths():
    rows = _doc_rows()
    counts = _recount(rows, rows.keys())
    assert counts == EXPECTED_TOTALS
    sections = _record_sections()
    assert _cumulative(sections[231]) == (
        141, 27, 76, 32, 6)
    # The battery chain closes on the same universe the
    # doc publishes: 141 ids, no remainder.
    assert P231.JUDGED == set(rows)
    assert len(P231.JUDGED12) == 111


# -- Area D: Accounting x8 ----------------------------------------------------


def test_d1_d1_fence_stands(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    paths, _operations = census(client)
    assert "post" in paths["/api/v1/group/turn"]
    # The stateless SSE loop's banked shape is unchanged:
    # the page's submit segment handles exactly the five
    # banked event types and reads no error / done dict -
    # the fence is measured here; no gate pin asserts the
    # failed-generation turn is honest, and the ruling
    # stays Volmarr's / the keeper's, outstanding. The
    # S305 contract battery itself stands as neighbour.
    submit = submit_segment()
    handled = set(re.findall(r'event\.type === "(\w+)"', submit))
    assert handled == {
        "typing", "reasoning", "token", "message", "turn_end"}
    s305 = (TESTS / "test_s305_group_ui.py").read_text(
        encoding="utf-8")
    assert len(re.findall(r"def test_", s305)) == 5


def test_d2_per_swipe_browsing_absent(tmp_path, monkeypatch):
    for path in (GROUP_JS, APP_JS, RENDERER_JS, GROUP_HTML):
        text = path.read_text(encoding="utf-8")
        for marker in ("show-all-swipes", "show_all_swipes",
                       "showAllSwipes"):
            assert marker not in text, (marker, path.name)
    client = make_client(tmp_path, monkeypatch)
    paths, _operations = census(client)
    assert not any(
        "all-swipes" in p or "all_swipes" in p for p in paths)
    # The active view is the only view the chat read
    # serves: one reasoning dict per message, never a
    # per-swipe browsing surface (P-206 ruling,
    # DECLINED-PENDING-WORD).
    world = build_world(client)
    for message in chat_messages(client, world["chat_id"]):
        assert isinstance(message["reasoning"], dict)


def test_d3_bot_runtime_absent(tmp_path, monkeypatch):
    policy = (SRC / "sandbox" / "policy.py").read_text(
        encoding="utf-8")
    assert ('"chat.write",  # reserved in v1: declared, '
            'honoured nowhere') in policy
    plugins_api = (SRC / "plugins" / "api.py").read_text(
        encoding="utf-8")
    assert '"chat.write"' in plugins_api
    assert "RESERVED" in plugins_api
    # No code path honours it and no bots package exists.
    assert not (SRC / "bots").exists()
    client = make_client(tmp_path, monkeypatch)
    paths, _operations = census(client)
    assert not any("bot" in path.lower() for path in paths)


def test_d4_ka_stands_open(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    paths, _operations = census(client)
    hub_paths = {p: m for p, m in paths.items() if "/hub/" in p}
    assert hub_paths, "the hub surface the item rides on must exist"
    for path, methods in hub_paths.items():
        assert "update" not in path, path
        assert "label" not in path, path
        assert "put" not in methods, (path, methods)
        assert "patch" not in methods, (path, methods)
    # The entry road's verbs are exactly the banked
    # register / read / remove set - remove-then-register
    # is the only road to a changed label (K-A's binding
    # label half, NAMED OPEN). The delete_chat cascade
    # half is reserved expressly for Volmarr: no road in
    # the census performs or names a binding cascade.
    entry_methods = set(paths["/api/v1/hub/entries/{entry_id}"])
    assert entry_methods <= {"get", "delete"}
    assert "delete" in entry_methods
    assert not any("cascade" in p.lower() for p in paths)


def test_d5_kb_stands_open(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    paths, _operations = census(client)
    for path in paths:
        for word in ("retention", "bulk-clear", "bulk_clear",
                     "clear-all", "clear_all"):
            assert word not in path, (word, path)
    for module in (svc, group_store):
        verbs = [n for n in dir(module) if not n.startswith("_")]
        for verb in verbs:
            lowered = verb.lower()
            assert "retention" not in lowered, verb
            assert "bulk" not in lowered, verb
            assert "clear_all" not in lowered, verb
    assert not any("retention" in p.name
                   for p in SRC.rglob("*.py"))


def test_d6_kc_stands_open(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    paths, _operations = census(client)
    for path in paths:
        assert not ("search" in path and "history" in path), path
    assert not any(
        "search_history" in p.name or "history_search" in p.name
        for p in SRC.rglob("*.py"))
    hub_paths = [p for p in paths if "/hub/" in p]
    assert hub_paths
    assert not any("history" in p for p in hub_paths)


def test_d7_record_gaps_repinned():
    # The P-218 gate pinned these gaps as census facts;
    # the Part XIV gate re-pins the record AS IT IS -
    # accounted, never repaired retroactively.
    log = CLEAN_ROOM_LOG.read_text(encoding="utf-8")
    headed = set(re.findall(r"(?m)^- \*\*(P-\d{3}) \(", log))
    assert "P-208" not in headed
    assert "P-209" not in headed
    assert (REPO / "docs" / "REASONING_GROUPCHAT_2026-11-09.md").exists()
    titled = set()
    for path in (REPO / "docs").glob("*.md"):
        first = path.read_text(encoding="utf-8").splitlines()[0]
        match = re.search(r"\(P-(\d{3})\)", first)
        if match:
            titled.add(f"P-{match.group(1)}")
    assert "P-209" not in titled


def test_d8_sitting_absent_and_live_sse_excluded(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    paths, _operations = census(client)
    # The Evaluation Sitting is Volmarr's to call: it is
    # absent from every queue surface the gate can see -
    # no road, no module, no scheduled surface.
    assert not any(
        "sitting" in p.lower() or "evaluation" in p.lower()
        for p in paths)
    assert not any("sitting" in p.name.lower()
                   for p in SRC.rglob("*.py"))
    # Web /generate live-SSE reasoning wiring stays
    # excluded (P-206 / P-209): the chats stream path
    # collects reasoning for STORAGE only and renders
    # nothing live.
    app_js = APP_JS.read_text(encoding="utf-8")
    stream = app_js.split("async function streamGeneration", 1)[1]
    stream = stream.split("async function sendMessage", 1)[0]
    assert 'event.type === "reasoning"' in stream
    assert "reasoningParts.push(event.text)" in stream
    assert "reasoningView" not in stream
    assert "reasoningPanel" not in stream


# -- Hygiene x2 ---------------------------------------------------------------


def test_h1_tree_law_footprint():
    footprint = {
        "tests/test_p232_part_xiv_gate.py",
        "tests/test_p232_gate_record.py",
        "docs/PART_XIV_GATE_2026-11-10.md",
        "docs/CLEAN_ROOM_LOG_2026-10-30.md",
    }
    changed = set()
    out = subprocess.run(
        ["git", "diff", "--name-only", BUILD_BASE, "HEAD"],
        cwd=REPO, capture_output=True, text=True,
        check=True).stdout
    changed |= {line.strip() for line in out.splitlines()
                if line.strip()}
    out = subprocess.run(
        ["git", "diff", "--name-only", BUILD_BASE],
        cwd=REPO, capture_output=True, text=True,
        check=True).stdout
    changed |= {line.strip() for line in out.splitlines()
                if line.strip()}
    out = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=REPO, capture_output=True, text=True,
        check=True).stdout
    changed |= {line.strip() for line in out.splitlines()
                if line.strip()}
    changed = {
        p for p in changed
        if not p.startswith("hidden_files/")
        and p != "WAVE_PLAN.md"}
    assert changed == footprint, changed
    assert "README.md" not in changed
    assert ("docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md"
            not in changed)


def test_h2_goldens_unmoved():
    golden_dir = TESTS / "fixtures" / "ui"
    assert {p.name for p in golden_dir.glob("*.golden.txt")} == (
        set(GOLDEN_SHA256))
    for name, expected in GOLDEN_SHA256.items():
        digest = hashlib.sha256(
            (golden_dir / name).read_bytes()).hexdigest()
        assert digest == expected, name
