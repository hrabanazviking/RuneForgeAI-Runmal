"""P-218 acceptance: the Part XIII gate battery (G = 35).

Part XIII (Assistant View, Inspector & Bots, DERIVED)
closes the way P-202 closed Part XII: ONE fresh gate
world (ZqxGate218) on which the part's load-bearing
cross-surface agreements are re-measured, every
carried item pinned BY NAME at full strength, and the
citizen batteries stood on as neighbours (never
duplicated silently).

Areas: A Census x10, B Together x8, C composed
group-page scenario x7, D Accounting x8, hygiene x2.

Honesty lines (design sections 1/5):
- the record gaps are census facts: P-209 shipped no
  slice doc and no headed clean-room entry; P-208
  shipped a slice doc but no headed entry. Area A pins
  the record AS IT IS at the build base.
- Area C is a COMPOSED scenario, not a browser run:
  substrate legs over real HTTP roads, JS lifecycle
  legs as segmented source-contract pins over the
  banked P-213..P-217 form.
- The S311 group golden is expected UNMOVED at this
  gate; the golden watch runs as a neighbour.

Fixtures mirror the banked citizen batteries
(test_p203 / test_p208 / test_p210 / test_p213 /
test_p215 in particular). Fresh-authored for this
gate (P-005 discipline); no real user files.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
import sqlite3
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends.fake import FakeChatBackend
from runmal.characters.service import create_character
from runmal.chats import continue_impersonate as ci
from runmal.chats import reasoning as rsn
from runmal.chats import service as svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Message, User
from runmal.db.owners import get_or_create_owner
from runmal.generation import service as gen_service
from runmal.groupchat import store as group_store
from runmal.inspector import (
    EVENTS_SCHEMA,
    GROUP_REASONING_SCHEMA,
    OVERVIEW_SCHEMA,
    REASONING_SCHEMA,
)
from runmal.inspector import events as events_mod
from runmal.inspector import group_reasoning as group_rsn_mod
from runmal.inspector import overview as overview_mod
from runmal.inspector import reasoning as inspector_rsn_mod

REPO = Path(__file__).parent.parent
SRC = REPO / "src" / "runmal"
GROUP_JS = SRC / "web" / "static" / "group.js"
GROUP_HTML = SRC / "web" / "templates" / "group.html"
APP_JS = SRC / "web" / "static" / "app.js"
RENDERER_JS = SRC / "web" / "static" / "renderer.js"
CLEAN_ROOM_LOG = REPO / "docs" / "CLEAN_ROOM_LOG_2026-10-30.md"

THINK_A = "ZqxGate218ChatThinking"
THINK_B = "weigh the toll at the gate"
CONTENT_A = "ZqxGate218RecordedAnswer"
GROUP_THINK_TEXT = "weigh the toll"

CARD_ASTA = {
    "name": "ZqxAsta218",
    "description": "Keeper of the mead hall at TESTHOLD.",
    "personality": "Warm but exact.",
    "scenario": "A longhouse hall.",
    "first_mes": "Sit, traveller.",
    "system_prompt": "You are Asta of TESTHOLD.",
}
CARD_BRAM = {
    "name": "ZqxBram218",
    "description": "Keeper of the bridge at TESTHOLD.",
    "personality": "Stern but fair.",
    "scenario": "A stone bridge over a cold river.",
    "first_mes": "State your business.",
    "system_prompt": "You are Bram of TESTHOLD.",
}

STATUSES = ("recorded", "not_present", "not_recorded", "unknown")

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
        {"kind": "note", "text": "The tide is going out.",
         "role": "Narrator"},
    ],
    "initial_flags": {"met_maera": True},
    "initial_variables": {"trust": 2},
}


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0042"
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    client = TestClient(create_app(factory))
    client.factory = factory  # same DB, for service-layer seeding
    client.db_path = db_path
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    client.token = token
    return client


def run(coro):
    return asyncio.run(coro)


async def _owner_id(factory):
    async with factory() as session:
        return (await get_or_create_owner(session)).id


def owner_id(client):
    return run(_owner_id(client.factory))


def walk_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from walk_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_keys(item)


def census(client):
    paths = client.get("/openapi.json").json()["paths"]
    operations = sum(
        len([k for k in methods
             if k in ("get", "post", "put", "delete", "patch")])
        for methods in paths.values()
    )
    return paths, operations


def group_js_segment(name):
    """One top-level function segment of group.js, in the
    banked citizen form (split on the next top-level
    declaration or the submit wiring)."""
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


# -- The gate world -------------------------------------------------------


def build_world(client):
    """ZqxGate218, fresh-authored for this gate: one owner
    with a chat carrying recorded / not_present /
    not_recorded reasoning across messages and swipes, a
    saved group whose stored transcript carries recorded
    reasoning, and a second foreign owner with their own
    chat and group for the custody legs."""
    world = {}
    asta = client.post("/api/v1/characters", json={"card": dict(CARD_ASTA)})
    assert asta.status_code == 201, asta.text
    bram = client.post("/api/v1/characters", json={"card": dict(CARD_BRAM)})
    assert bram.status_code == 201, bram.text
    world["asta_id"] = asta.json()["id"]
    world["bram_id"] = bram.json()["id"]

    created = client.post("/api/v1/chats", json={"title": "ZqxGate218 Saga"})
    assert created.status_code == 201, created.text
    chat_id = created.json()["id"]
    world["chat_id"] = chat_id

    # A bound scenario, so the overview's scenario section
    # has honest state to report (the P-203 shape). The
    # bind is an opening act: it precedes every message.
    definition = client.post("/api/v1/scenarios", json=dict(SCENARIO_BODY))
    assert definition.status_code == 201, definition.text
    bound = client.post(
        f"/api/v1/scenarios/{definition.json()['id']}/bind",
        json={"chat_id": chat_id})
    assert bound.status_code == 201, bound.text
    world["scenario_binding_id"] = bound.json()["id"]

    def post_message(role, content, reasoning=None):
        body = {"role": role, "content": content}
        if reasoning is not None:
            body["reasoning"] = reasoning
        resp = client.post(f"/api/v1/chats/{chat_id}/messages", json=body)
        assert resp.status_code == 201, resp.text
        return resp.json()

    m1 = post_message(
        "assistant", CONTENT_A,
        reasoning={"status": "recorded", "text": THINK_A})
    swipe = client.post(
        f"/api/v1/chats/{chat_id}/messages/{m1['id']}/swipes",
        json={"content": "ZqxGate218SecondAnswer",
              "reasoning": {"status": "not_present"}})
    assert swipe.status_code == 201, swipe.text
    m2 = post_message(
        "assistant", "ZqxGate218PlainAnswer",
        reasoning={"status": "not_present"})
    m3 = post_message("user", "ZqxGate218Question")
    # The scenario bind seeded its bootstrap note as the
    # chat's first stored message (the banked bind
    # behaviour), so the world's chat carries FOUR stored
    # messages: the bootstrap note plus the three posted
    # here. The census tallies are read from the chat
    # itself, never assumed.
    world["message_ids"] = [
        m["id"] for m in chat_messages(client, chat_id)]
    assert len(world["message_ids"]) == 4
    assert world["message_ids"][1:] == [m1["id"], m2["id"], m3["id"]]

    group = client.post(
        "/api/v1/groups",
        json={"name": "ZqxGate218 Hall",
              "member_character_ids": [world["asta_id"], world["bram_id"]]})
    assert group.status_code == 201, group.text
    world["group_id"] = group.json()["id"]
    world["group_chat_id"] = group.json()["chat_id"]
    uid = owner_id(client)

    async def seed_group():
        async with client.factory() as session:
            await group_store.append_message(
                session, uid, world["group_id"], "user",
                "ZqxGate218UserTurn")
            await group_store.append_message(
                session, uid, world["group_id"], world["asta_id"],
                "ZqxGate218GroupReply",
                reasoning=rsn.build_record(
                    status="recorded", text=THINK_B))
            await group_store.append_message(
                session, uid, world["group_id"], world["bram_id"],
                "ZqxGate218GroupPlain",
                reasoning=rsn.build_record(status="not_present"))

    run(seed_group())

    async def seed_foreign():
        async with client.factory() as session:
            stranger = User(name="zqx-gate218-stranger")
            session.add(stranger)
            await session.commit()
            sid = stranger.id
            chat = await svc.create_chat(session, sid, "Foreign Saga")
            await svc.append_message(
                session, sid, chat.id, "assistant", "Foreign answer.",
                reasoning=rsn.build_record(
                    status="recorded", text="foreign thought"))
            character = await create_character(
                session, sid, dict(CARD_ASTA, name="ZqxForeign218"))
            fgroup = await group_store.create_group(
                session, sid, "Foreign Hall", [character.id])
            await group_store.append_message(
                session, sid, fgroup.id, character.id,
                "A foreign group answer.",
                reasoning=rsn.build_record(
                    status="recorded", text="foreign group thought"))
            return sid, chat.id, fgroup.id

    sid, fchat, fgroup = run(seed_foreign())
    world["foreign_owner_id"] = sid
    world["foreign_chat_id"] = fchat
    world["foreign_group_id"] = fgroup
    return world


def get_inspector(client, path):
    resp = client.get(path)
    assert resp.status_code == 200, resp.text
    return resp.json()


def chat_messages(client, chat_id):
    resp = client.get(f"/api/v1/chats/{chat_id}/messages")
    assert resp.status_code == 200, resp.text
    rows = resp.json()
    return rows["messages"] if isinstance(rows, dict) else rows


def group_transcript(client, group_id):
    resp = client.get(f"/api/v1/groups/{group_id}/messages")
    assert resp.status_code == 200, resp.text
    return resp.json()


# -- Area A: Census x10 -----------------------------------------------------

CITIZEN_BATTERIES = {
    "P-203": ("test_p203_inspector_overview.py", 11),
    "P-204": ("test_p204_inspector_events.py", 15),
    "P-205": ("test_p205_reasoning_record.py", 23),
    "P-206": ("test_p206_assistant_view.py", 18),
    "P-207": ("test_p207_continue_impersonate_reasoning.py", 16),
    "P-208": ("test_p208_groupchat_reasoning.py", 18),
    "P-209": ("test_p209_swipe_generate_reasoning.py", 16),
    "P-210": ("test_p210_inspector_reasoning.py", 14),
    "P-211": ("test_p211_inspector_group_reasoning.py", 15),
    "P-212": ("test_p212_group_assistant_view.py", 14),
    "P-213": ("test_p213_group_transcript_loader.py", 14),
    "P-214": ("test_p214_group_composer_wiring.py", 14),
    "P-215": ("test_p215_group_mode_toggle.py", 14),
    "P-216": ("test_p216_group_creation.py", 14),
    "P-217": ("test_p217_group_persistent_refinements.py", 14),
}

SLICE_DOCS = {
    "P-203": "INSPECTOR_OVERVIEW_2026-11-09.md",
    "P-204": "INSPECTOR_EVENTS_2026-11-09.md",
    "P-205": "REASONING_RECORD_2026-11-09.md",
    "P-206": "ASSISTANT_VIEW_2026-11-09.md",
    "P-207": "REASONING_CONTINUE_IMPERSONATE_2026-11-09.md",
    "P-208": "REASONING_GROUPCHAT_2026-11-09.md",
    "P-210": "INSPECTOR_REASONING_2026-11-09.md",
    "P-211": "INSPECTOR_GROUP_REASONING_2026-11-10.md",
    "P-212": "ASSISTANT_VIEW_GROUP_2026-11-10.md",
    "P-213": "GROUP_TRANSCRIPT_LOADER_2026-11-10.md",
    "P-214": "GROUP_COMPOSER_WIRING_2026-11-10.md",
    "P-215": "GROUP_MODE_TOGGLE_2026-11-10.md",
    "P-216": "GROUP_CREATION_2026-11-10.md",
    "P-217": "GROUP_PERSISTENT_REFINEMENTS_2026-11-10.md",
}


def test_a1_slice_continuity_battery_counts():
    tests_dir = REPO / "tests"
    total = 0
    for slice_id, (filename, expected) in CITIZEN_BATTERIES.items():
        path = tests_dir / filename
        assert path.exists(), (slice_id, filename)
        count = len(re.findall(r"def test_", path.read_text(encoding="utf-8")))
        assert count == expected, (slice_id, count, expected)
        total += count
    assert total == 230


def test_a2_slice_docs_exactly_one_and_p209_gap():
    docs_dir = REPO / "docs"
    # The titled slice docs: exactly one per slice, named
    # by the slice tag in the document's own title line.
    titled = {}
    for path in docs_dir.glob("*.md"):
        first = path.read_text(encoding="utf-8").splitlines()[0]
        match = re.search(r"\(P-(\d{3})\)", first)
        if match:
            titled.setdefault(f"P-{match.group(1)}", []).append(path.name)
    for slice_id, filename in SLICE_DOCS.items():
        path = docs_dir / filename
        assert path.exists(), (slice_id, filename)
        assert titled.get(slice_id) == [filename], (slice_id, titled.get(slice_id))
    # P-209 shipped NO slice doc: the gap pinned as a fact,
    # not filled. No titled doc anywhere names P-209.
    assert "P-209" not in titled


def test_a3_headed_clean_room_entries_and_gaps():
    text = CLEAN_ROOM_LOG.read_text(encoding="utf-8")
    headed = set(re.findall(r"(?m)^- \*\*(P-\d{3}) \(", text))
    for slice_id in ("P-203", "P-204", "P-205", "P-206", "P-207",
                     "P-210", "P-211", "P-212", "P-213", "P-214",
                     "P-215", "P-216", "P-217"):
        assert slice_id in headed, slice_id
    # Absent AS HEADED ENTRIES (mentions inside other
    # slices' entries do not count): the two record gaps.
    assert "P-208" not in headed
    assert "P-209" not in headed


def test_a4_inspector_package_exactly_six_files():
    package = SRC / "inspector"
    files = {p.name for p in package.iterdir()
             if p.is_file() and p.suffix == ".py"}
    assert files == {
        "__init__.py", "overview.py", "events.py",
        "reasoning.py", "group_reasoning.py", "router.py",
    }


def test_a5_inspector_roads_exactly_four_gets_in_order():
    router_text = (SRC / "inspector" / "router.py").read_text(encoding="utf-8")
    gets = re.findall(r'@router\.get\("([^"]+)"\)', router_text)
    assert gets == [
        "/inspector/chats/{chat_id}",
        "/inspector/chats/{chat_id}/events",
        "/inspector/chats/{chat_id}/reasoning",
        "/inspector/groups/{group_id}/reasoning",
    ]
    for verb in ("post", "put", "delete", "patch"):
        assert f"@router.{verb}" not in router_text


def test_a6_schema_tags_exactly_five_verbatim():
    assert OVERVIEW_SCHEMA == "runmal-p203-inspector-overview-v1"
    assert EVENTS_SCHEMA == "runmal-p204-inspector-events-v1"
    assert REASONING_SCHEMA == "runmal-p210-inspector-reasoning-v1"
    assert GROUP_REASONING_SCHEMA == "runmal-p211-inspector-group-reasoning-v1"
    assert rsn.REASONING_SCHEMA == "runmal-p205-message-reasoning-v1"


def test_a7_census_migration_and_part_delta(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    paths, operations = census(client)
    assert len(paths) == 365
    assert operations == 455
    assert MIGRATIONS[-1][0] == "0042"
    migrations_dir = SRC / "db" / "migrations"
    assert not [p.name for p in migrations_dir.glob("m0043*")]
    # The part's census delta over the P-209 census
    # (354 / 437) was exactly the two Inspector reasoning
    # roads: P-210 +1/+1 and P-211 +1/+1. R-03 heal: the
    # non-reasoning remainder has since grown by the R-02
    # backend-profile roads (+7 paths / +12 operations,
    # landed unhealed) and R-03's persona/user-name roads
    # (+2 / +4), so the remainder pins move with the census.
    reasoning_paths = {
        "/api/v1/inspector/chats/{chat_id}/reasoning",
        "/api/v1/inspector/groups/{group_id}/reasoning",
    }
    assert reasoning_paths <= set(paths)
    assert len(paths) - len(reasoning_paths) == 363
    assert operations - 2 == 453


def test_a8_group_page_census_twenty_ids():
    html = GROUP_HTML.read_text(encoding="utf-8")
    ids = re.findall(r'id="([^"]+)"', html)
    assert set(ids) == {
        "close-group", "create-group", "error-banner",
        "error-dismiss", "error-text", "group-form",
        "group-input", "group-layout", "group-main",
        "group-mode", "group-thread", "new-group-name",
        "open-group", "palette", "palette-card",
        "palette-input", "palette-list", "roster",
        "saved-group", "strategy",
    }
    assert len(ids) == 20
    # Script order as banked: renderer.js before group.js.
    assert html.index("/static/renderer.js") < html.index("/static/group.js")


def test_a9_reasoning_record_shape_one_law():
    # The P-205 record's four-status law is the ONE law:
    # the chats record module owns it as a frozenset and
    # validates records against it.
    assert rsn.STATUSES == frozenset(STATUSES)
    record_text = (SRC / "chats" / "reasoning.py").read_text(encoding="utf-8")
    assert "if status not in STATUSES" in record_text
    with pytest.raises(Exception):
        rsn.build_record(status="telepathic", text="boo")
    # The P-210 join re-states it as the ordered tuple the
    # count families zero-fill in (shape-identical), the
    # P-211 join imports that very object (is-identical),
    # and the P-207 seam resolves through the record
    # module itself.
    assert inspector_rsn_mod.STATUSES == STATUSES
    assert set(inspector_rsn_mod.STATUSES) == set(rsn.STATUSES)
    assert group_rsn_mod.STATUSES is inspector_rsn_mod.STATUSES
    assert group_rsn_mod.summarise_reasoning is inspector_rsn_mod.summarise_reasoning
    ci_text = (SRC / "chats" / "continue_impersonate.py").read_text(encoding="utf-8")
    assert "from runmal.chats import reasoning" in ci_text or \
        "from runmal.chats.reasoning import" in ci_text
    # Both Assistant Views resolve through the one shared
    # renderer model, whose status vocabulary is exactly
    # the four statuses and three honest status lines.
    renderer = RENDERER_JS.read_text(encoding="utf-8")
    # The model names three statuses in comparisons; the
    # fourth (unknown) is its fall-through line, never a
    # named comparison - the banked P-206 form (its own
    # battery pins unrecognised statuses landing there).
    for status in ("recorded", "not_present", "not_recorded"):
        assert f'"{status}"' in renderer
    view_segment = renderer.split("function reasoningView", 1)[1].split(
        "var api", 1)[0]
    assert view_segment.count("status ===") == 3
    assert '"unknown"' not in view_segment
    for line in ("No thinking was returned for this reply.",
                 "Thinking was not recorded for this reply.",
                 "Thinking record state is unknown for this reply."):
        assert line in renderer
    group_js = GROUP_JS.read_text(encoding="utf-8")
    assert "window.RunmalRenderer.reasoningView" in group_js


def test_a10_no_bots_census(tmp_path, monkeypatch):
    assert not (SRC / "bots").exists()
    client = make_client(tmp_path, monkeypatch)
    paths, _operations = census(client)
    assert not any("bot" in path.lower() for path in paths)
    conn = sqlite3.connect(client.db_path)
    try:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
    finally:
        conn.close()
    assert not any("bot" in name.lower() for name in tables)


# -- Area B: Together x8 (one fresh gate world) -----------------------------


def test_b1_overview_agreement(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    world = build_world(client)
    doc = get_inspector(client, f"/api/v1/inspector/chats/{world['chat_id']}")
    assert doc["schema"] == OVERVIEW_SCHEMA
    # The overview's counts equal the gate world's own
    # tallies, carried verbatim from the banked P-075 road.
    banked = client.get(f"/api/v1/chats/{world['chat_id']}/provenance")
    assert banked.status_code == 200, banked.text
    provenance = doc["sections"]["provenance"]
    assert provenance["summary"] == banked.json()["summary"]
    assert provenance["summary"]["total"] == len(world["message_ids"]) == 4
    assert provenance["status"] == "available"
    # Sections carry the honest statuses for this world:
    # prompt roads available, no lore bound, scenario bound.
    for section in doc["sections"].values():
        assert section["status"] in overview_mod.SECTION_STATUSES
        assert "reason" in section
    assert doc["sections"]["lore_activation"]["status"] == "empty"
    assert doc["sections"]["lore_activation"]["books"] == []
    scenario = doc["sections"]["scenario"]
    assert scenario["status"] == "available"
    assert scenario["bound"] is True
    assert scenario["binding"]["id"] == world["scenario_binding_id"]
    assert scenario["binding"]["chat_id"] == world["chat_id"]


def test_b2_events_agreement(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    world = build_world(client)
    doc = get_inspector(
        client, f"/api/v1/inspector/chats/{world['chat_id']}/events")
    assert doc["schema"] == EVENTS_SCHEMA
    uid = owner_id(client)

    async def read_log():
        async with client.factory() as session:
            return await svc.list_events(session, uid, world["chat_id"])

    events = run(read_log())
    assert events, "the gate world must carry a stored event log"
    by_kind = {}
    for event in events:
        by_kind[event.kind] = by_kind.get(event.kind, 0) + 1
    section = doc["sections"]["events"]
    assert section["status"] == "available"
    assert section["total"] == len(events)
    assert section["by_kind"] == by_kind
    assert section["first_at"] == events[0].created_at.isoformat()
    assert section["last_at"] == events[-1].created_at.isoformat()
    assert section["latest"] == {
        "kind": events[-1].kind,
        "created_at": events[-1].created_at.isoformat(),
    }
    # No payload anywhere in the document.
    blob = json.dumps(doc)
    assert THINK_A not in blob
    assert CONTENT_A not in blob
    assert "payload" not in set(walk_keys(doc))


def _direct_chat_resolution(client, world):
    """Resolve the chat's stored reasoning_json directly
    through the banked raw road (the P-210 test_07 form):
    per-status counts over active views and over all
    swipe documents, computed without the summariser."""
    active_by_status = {status: 0 for status in STATUSES}
    swipes_by_status = {status: 0 for status in STATUSES}
    swipes_total = 0
    swipes_recorded = 0
    messages_with_recorded = 0
    for message_id in world["message_ids"]:
        raw_resp = client.get(
            f"/api/v1/chats/{world['chat_id']}/messages/"
            f"{message_id}/reasoning")
        assert raw_resp.status_code == 200, raw_resp.text
        raw = raw_resp.json()
        active_record = raw["swipes"].get(
            str(raw["active_swipe_id"]), {"status": "not_recorded"})
        active_by_status[active_record["status"]] += 1
        if raw["recorded"]:
            messages_with_recorded += 1
        swipes_total += len(raw["swipes"])
        for record in raw["swipes"].values():
            swipes_by_status[record["status"]] += 1
            if record["status"] == "recorded":
                swipes_recorded += 1
    return {
        "messages_total": len(world["message_ids"]),
        "active_by_status": active_by_status,
        "messages_with_recorded": messages_with_recorded,
        "swipes_total": swipes_total,
        "swipes_recorded": swipes_recorded,
        "swipes_by_status": swipes_by_status,
    }


def test_b3_reasoning_join_agreement(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    world = build_world(client)
    doc = get_inspector(
        client, f"/api/v1/inspector/chats/{world['chat_id']}/reasoning")
    assert doc["schema"] == REASONING_SCHEMA
    assert doc["summary"] == _direct_chat_resolution(client, world)
    # The designed world, stated exactly: the bootstrap
    # note reads not_recorded; recorded lives on swipe 0
    # of message 2, under a not_present active swipe;
    # message 3 not_present; message 4 not_recorded.
    assert doc["summary"]["active_by_status"] == {
        "recorded": 0, "not_present": 2, "not_recorded": 2, "unknown": 0}
    assert doc["summary"]["swipes_by_status"] == {
        "recorded": 1, "not_present": 2, "not_recorded": 2, "unknown": 0}
    assert doc["summary"]["swipes_total"] == 5


def _direct_group_resolution(client, world):
    """Resolve the group transcript's stored reasoning
    directly through the banked tolerant readers over the
    room chat's stored rows (never the summariser)."""
    uid = owner_id(client)

    async def read_rows():
        async with client.factory() as session:
            history = await svc.get_history(
                session, uid, world["group_chat_id"])
            return [
                (group_store.message_to_dict(m), rsn.full_view(m),
                 rsn.active_view(m, getattr(m, "swipe_id", 0) or 0))
                for m in history
            ]

    rows = run(read_rows())
    active_by_status = {status: 0 for status in STATUSES}
    swipes_by_status = {status: 0 for status in STATUSES}
    speakers = []
    by_key = {}
    swipes_total = 0
    swipes_recorded = 0
    messages_with_recorded = 0
    for as_dict, full, active in rows:
        active_by_status[active["reasoning_status"]] += 1
        if full["recorded"]:
            messages_with_recorded += 1
        swipes_total += len(full["swipes"])
        for record in full["swipes"].values():
            swipes_by_status[record["status"]] += 1
            if record["status"] == "recorded":
                swipes_recorded += 1
        key = (as_dict["speaker_id"], as_dict["speaker_name"])
        speaker = by_key.get(key)
        if speaker is None:
            speaker = {
                "speaker_id": as_dict["speaker_id"],
                "speaker_name": as_dict["speaker_name"],
                "messages_total": 0,
                "active_by_status": {s: 0 for s in STATUSES},
                "messages_with_recorded": 0,
            }
            by_key[key] = speaker
            speakers.append(speaker)
        speaker["messages_total"] += 1
        speaker["active_by_status"][active["reasoning_status"]] += 1
        if full["recorded"]:
            speaker["messages_with_recorded"] += 1
    summary = {
        "messages_total": len(rows),
        "active_by_status": active_by_status,
        "messages_with_recorded": messages_with_recorded,
        "swipes_total": swipes_total,
        "swipes_recorded": swipes_recorded,
        "swipes_by_status": swipes_by_status,
    }
    return summary, speakers


def test_b4_group_join_agreement(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    world = build_world(client)
    doc = get_inspector(
        client,
        f"/api/v1/inspector/groups/{world['group_id']}/reasoning")
    assert doc["schema"] == GROUP_REASONING_SCHEMA
    summary, speakers = _direct_group_resolution(client, world)
    assert doc["summary"] == summary
    # Per-speaker roll-up in first-appearance order: the
    # user turn, then Asta (recorded), then Bram.
    assert doc["speakers"] == speakers
    assert [(s["speaker_id"], s["speaker_name"]) for s in doc["speakers"]] == [
        (None, None),
        (world["asta_id"], "ZqxAsta218"),
        (world["bram_id"], "ZqxBram218"),
    ]
    assert doc["summary"]["active_by_status"] == {
        "recorded": 1, "not_present": 1, "not_recorded": 1, "unknown": 0}


def test_b5_cross_join_agreement(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    world = build_world(client)
    chat_doc = get_inspector(
        client, f"/api/v1/inspector/chats/{world['chat_id']}/reasoning")
    group_doc = get_inspector(
        client,
        f"/api/v1/inspector/groups/{world['group_id']}/reasoning")
    # Shape-identical summaries, both composed by the one
    # banked summariser (is-identical, pinned in A9).
    assert set(chat_doc["summary"]) == set(group_doc["summary"])
    assert set(chat_doc["summary"]["active_by_status"]) == set(STATUSES)
    assert set(group_doc["summary"]["swipes_by_status"]) == set(STATUSES)
    # A chat and a group with equal reasoning states read
    # equal censuses: a matched pair built for this leg.
    created = client.post("/api/v1/chats", json={"title": "ZqxGate218 Pair"})
    assert created.status_code == 201, created.text
    pair_chat = created.json()["id"]
    for role, content, reasoning in (
        ("assistant", "Pair recorded.",
         {"status": "recorded", "text": "pair thought"}),
        ("assistant", "Pair plain.", {"status": "not_present"}),
    ):
        resp = client.post(
            f"/api/v1/chats/{pair_chat}/messages",
            json={"role": role, "content": content,
                  "reasoning": reasoning})
        assert resp.status_code == 201, resp.text
    pair_group_resp = client.post(
        "/api/v1/groups",
        json={"name": "ZqxGate218 Pair Hall",
              "member_character_ids": [world["asta_id"], world["bram_id"]]})
    assert pair_group_resp.status_code == 201, pair_group_resp.text
    pair_group = pair_group_resp.json()["id"]
    uid = owner_id(client)

    async def seed_pair():
        async with client.factory() as session:
            await group_store.append_message(
                session, uid, pair_group, world["asta_id"],
                "Pair group recorded.",
                reasoning=rsn.build_record(
                    status="recorded", text="pair thought"))
            await group_store.append_message(
                session, uid, pair_group, world["bram_id"],
                "Pair group plain.",
                reasoning=rsn.build_record(status="not_present"))

    run(seed_pair())
    pair_chat_doc = get_inspector(
        client, f"/api/v1/inspector/chats/{pair_chat}/reasoning")
    pair_group_doc = get_inspector(
        client, f"/api/v1/inspector/groups/{pair_group}/reasoning")
    assert pair_chat_doc["summary"] == pair_group_doc["summary"]


def _run_view_model(views):
    """The P-206 renderer model, run the banked way
    (node over renderer.js, as test_p206 does)."""
    calls = ", ".join(
        "r.reasoningView(" + json.dumps(view) + ")" for view in views)
    script = (
        "const r = require(" + repr(str(RENDERER_JS)) + ");"
        "const out = [" + calls + "];"
        "console.log(JSON.stringify(out));"
    )
    proc = subprocess.run(
        ["node", "-e", script], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout.strip())


def test_b6_assistant_view_agreement(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    world = build_world(client)
    doc = get_inspector(
        client, f"/api/v1/inspector/chats/{world['chat_id']}/reasoning")
    messages = chat_messages(client, world["chat_id"])
    assert len(messages) == 4
    views = [m["reasoning"] for m in messages]
    # The stored views the chat read serves are exactly
    # the views the P-210 census counts: one truth, two
    # surfaces - same statuses, same order, same tallies.
    assert [v["reasoning_status"] for v in views] == [
        entry["active_status"] for entry in doc["messages"]]
    tally = {status: 0 for status in STATUSES}
    for view in views:
        tally[view["reasoning_status"]] += 1
    assert tally == doc["summary"]["active_by_status"]
    # And the P-206 renderer model over those stored views
    # produces the panel models for exactly those views.
    models = _run_view_model(views)
    for view, model in zip(views, models):
        if view["reasoning_status"] == "recorded":
            assert model == {
                "kind": "recorded", "label": "Thinking",
                "text": view["text"]}
        else:
            assert model["kind"] == "status"
            assert "text" in model
    # The recorded panel model itself, over the stored
    # swipe-0 view of the recorded message (its active
    # view is the not_present swipe, counted above).
    uid = owner_id(client)

    async def recorded_view():
        async with client.factory() as session:
            history = await svc.get_history(session, uid, world["chat_id"])
            rows = [m for m in history if m.id == world["message_ids"][1]]
            assert len(rows) == 1
            return rsn.active_view(rows[0], 0)

    stored = run(recorded_view())
    assert stored["reasoning_status"] == "recorded"
    (model,) = _run_view_model([stored])
    assert model == {
        "kind": "recorded", "label": "Thinking", "text": THINK_A}


def test_b7_group_stored_view_agreement(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    world = build_world(client)
    doc = get_inspector(
        client,
        f"/api/v1/inspector/groups/{world['group_id']}/reasoning")
    transcript = group_transcript(client, world["group_id"])
    assert len(transcript) == 3
    views = [m["reasoning"] for m in transcript]
    # The P-213 loader's stored views over the transcript
    # are the views the P-211 census counts.
    assert [v["reasoning_status"] for v in views] == [
        entry["active_status"] for entry in doc["messages"]]
    tally = {status: 0 for status in STATUSES}
    for view in views:
        tally[view["reasoning_status"]] += 1
    assert tally == doc["summary"]["active_by_status"]
    recorded = [v for v in views if v["reasoning_status"] == "recorded"]
    assert len(recorded) == 1
    assert recorded[0]["text"] == THINK_B


def test_b8_refusal_agreement(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    world = build_world(client)
    chat_roads = [
        "/api/v1/inspector/chats/{}/",
        "/api/v1/inspector/chats/{}/events",
        "/api/v1/inspector/chats/{}/reasoning",
    ]
    # Unknown ids read the house 404 on all 4 roads.
    for template in chat_roads:
        resp = client.get(template.format("no-such-chat").rstrip("/"))
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == "chat not found"
    resp = client.get("/api/v1/inspector/groups/no-such-group/reasoning")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "group not found"
    # Foreign ids read the same 404 (existence never leaks).
    for template in chat_roads:
        resp = client.get(template.format(world["foreign_chat_id"]).rstrip("/"))
        assert resp.status_code == 404, resp.text
        assert resp.json()["detail"] == "chat not found"
    resp = client.get(
        f"/api/v1/inspector/groups/{world['foreign_group_id']}/reasoning")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "group not found"
    # Every Inspector road without a bearer reads 401.
    bare = TestClient(create_app(client.factory))
    for url in (
        f"/api/v1/inspector/chats/{world['chat_id']}",
        f"/api/v1/inspector/chats/{world['chat_id']}/events",
        f"/api/v1/inspector/chats/{world['chat_id']}/reasoning",
        f"/api/v1/inspector/groups/{world['group_id']}/reasoning",
    ):
        resp = bare.get(url)
        assert resp.status_code == 401, (url, resp.status_code)


# -- Area C: Composed group-page scenario x7 --------------------------------
#
# One scenario walked in order against the gate world's
# group roads. Substrate legs run over real HTTP
# (TestClient on the banked roads the page composes);
# JS lifecycle legs are segmented source-contract pins
# over group.js / group.html in the banked citizen
# form. NOT a browser claim, here or in the record.


def _reasoning_fake():
    return FakeChatBackend(
        chunks=("The ", "answer."), reasoning_chunks=("weigh ", "the toll"))


def _patch_backend(monkeypatch):
    monkeypatch.setattr(gen_service, "default_backend", _reasoning_fake)


def _scenario_characters(client):
    asta = client.post("/api/v1/characters", json={"card": dict(CARD_ASTA)})
    assert asta.status_code == 201, asta.text
    bram = client.post("/api/v1/characters", json={"card": dict(CARD_BRAM)})
    assert bram.status_code == 201, bram.text
    return asta.json()["id"], bram.json()["id"]


def _scenario_create(client):
    asta_id, bram_id = _scenario_characters(client)
    resp = client.post(
        "/api/v1/groups",
        json={"name": "ZqxGate218 Scenario Hall",
              "member_character_ids": [asta_id, bram_id]})
    assert resp.status_code == 201, resp.text
    return resp.json(), asta_id, bram_id


def _scenario_send(client, group_id):
    resp = client.post(
        f"/api/v1/groups/{group_id}/next",
        json={"user_text": "ZqxGate218ScenarioTurn", "generate": True})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_c1_create_substrate_and_js_leg(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created, _asta_id, _bram_id = _scenario_create(client)
    # Substrate: 201 in the describe shape, message_count 0,
    # and the group appears in GET /groups.
    for key in ("id", "name", "chat_id", "members",
                "member_count", "message_count"):
        assert key in created, key
    assert created["message_count"] == 0
    assert created["member_count"] == 2
    listed = client.get("/api/v1/groups")
    assert listed.status_code == 200, listed.text
    mine = [g for g in listed.json() if g["id"] == created["id"]]
    assert len(mine) == 1
    assert mine[0]["message_count"] == 0
    # JS leg: createGroup posts exactly there with the
    # roster selection, refreshes the picker, selects the
    # new group - and never opens it.
    segment = group_js_segment("createGroup")
    assert 'api("/api/v1/groups"' in segment
    assert 'method: "POST"' in segment
    assert "member_character_ids: selectedIds()" in segment
    assert "await loadSavedGroups();" in segment
    assert '$("saved-group").value = group.id;' in segment
    assert "openSavedGroup" not in segment
    assert "openGroupId" not in segment


def test_c2_open_substrate_and_js_leg(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created, _a, _b = _scenario_create(client)
    # Substrate: the empty group reads an empty transcript.
    assert group_transcript(client, created["id"]) == []
    # JS leg: openSavedGroup's success path alone sets
    # openGroupId, restates the mode line and enables
    # close - the P-215 segment, failure catch clean.
    segment = group_js_segment("openSavedGroup")
    fetch_at = segment.index('"/messages"')
    set_at = segment.index("openGroupId = groupId;")
    assert fetch_at < set_at
    assert segment.index("addBubble(m.speaker_name") < set_at
    assert '$("group-mode").textContent = "Saved group mode";' in segment
    assert '$("close-group").disabled = false;' in segment
    catch = segment[segment.index("catch"):]
    assert "showError" in catch
    assert "openGroupId" not in catch


def test_c3_persistent_send_substrate_and_js_leg(tmp_path, monkeypatch):
    _patch_backend(monkeypatch)
    client = make_client(tmp_path, monkeypatch)
    created, _a, _b = _scenario_create(client)
    result = _scenario_send(client, created["id"])
    # Substrate: the user turn and the reply are stored;
    # the transcript re-read carries both, the reply with
    # its stored reasoning view.
    assert result["message"] is not None
    assert result["message"]["reasoning"]["status"] == "recorded"
    assert result["message"]["reasoning"]["text"] == GROUP_THINK_TEXT
    transcript = group_transcript(client, created["id"])
    assert [m["content"] for m in transcript] == [
        "ZqxGate218ScenarioTurn", "The answer."]
    assert transcript[0]["role"] == "user"
    reply = transcript[1]
    assert reply["reasoning"]["reasoning_status"] == "recorded"
    assert reply["reasoning"]["text"] == GROUP_THINK_TEXT
    # JS leg: sendPersistent posts exactly there and
    # renders via the banked addBubble + reasoningPanel
    # pair over the shared view model.
    segment = group_js_segment("sendPersistent")
    assert '"/api/v1/groups/" + openGroupId + "/next"' in segment
    assert "generate: true" in segment
    assert "addBubble(m.speaker_name" in segment
    assert "reasoningPanel(" in segment
    assert "window.RunmalRenderer.reasoningView(m.reasoning)" in segment


def test_c4_counts_refresh_substrate_and_js_leg(tmp_path, monkeypatch):
    _patch_backend(monkeypatch)
    client = make_client(tmp_path, monkeypatch)
    created, _a, _b = _scenario_create(client)
    before = client.get("/api/v1/groups").json()
    assert [g for g in before if g["id"] == created["id"]][0][
        "message_count"] == 0
    _scenario_send(client, created["id"])
    stored = group_transcript(client, created["id"])
    after = client.get("/api/v1/groups").json()
    count = [g for g in after if g["id"] == created["id"]][0]["message_count"]
    # Risen by exactly the stored turns (user + reply).
    assert count == len(stored) == 2
    # JS leg: P-217's success-tail refresh - loadSavedGroups
    # re-run and the picker value set to openGroupId, after
    # the send, in the success path only, never on failure.
    segment = group_js_segment("sendPersistent")
    send_at = segment.index("/next")
    refresh_at = segment.index("await loadSavedGroups();")
    assert send_at < refresh_at
    assert '$("saved-group").value = openGroupId;' in segment
    catch = segment[segment.index("catch"):]
    assert "loadSavedGroups" not in catch


def test_c5_controls_disabled_js_source_contract():
    js = GROUP_JS.read_text(encoding="utf-8")
    # Exactly six disabled writes in the whole page: the
    # P-215 enable of close, the P-217 disable pair on the
    # open success path, and their re-enable pair plus the
    # close disable inside closeSavedGroup.
    assert js.count(".disabled =") == 6
    open_segment = group_js_segment("openSavedGroup")
    assert '$("strategy").disabled = true;' in open_segment
    assert "box.disabled = true" in open_segment
    close_segment = group_js_segment("closeSavedGroup")
    guard_at = close_segment.index("if (!openGroupId) return;")
    strategy_at = close_segment.index('$("strategy").disabled = false;')
    roster_at = close_segment.index("box.disabled = false")
    assert guard_at < strategy_at
    assert guard_at < roster_at
    # No other segment writes disabled state; the stateless
    # branch reads the controls live.
    submit = submit_segment()
    assert ".disabled" not in submit
    for name in ("loadRoster", "loadSavedGroups", "createGroup",
                 "sendPersistent", "addBubble"):
        assert ".disabled" not in group_js_segment(name), name


def test_c6_close_substrate_and_js_leg(tmp_path, monkeypatch):
    _patch_backend(monkeypatch)
    client = make_client(tmp_path, monkeypatch)
    created, _a, _b = _scenario_create(client)
    _scenario_send(client, created["id"])
    before = group_transcript(client, created["id"])
    before_bytes = json.dumps(before, sort_keys=True)
    described_before = client.get(f"/api/v1/groups/{created['id']}").json()
    # JS leg: close is client-side - the closeSavedGroup
    # segment holds no fetch, no api call, no POST and no
    # web storage.
    segment = group_js_segment("closeSavedGroup")
    for forbidden in ("fetch", "api(", "POST",
                      "localStorage", "sessionStorage"):
        assert forbidden not in segment, forbidden
    # Substrate: re-reading the transcript over HTTP after
    # a close reads it byte-identical, group untouched.
    after = group_transcript(client, created["id"])
    assert json.dumps(after, sort_keys=True) == before_bytes
    assert client.get(f"/api/v1/groups/{created['id']}").json() == \
        described_before


def test_c7_stateless_truth_restored(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    # JS leg: after close the page's resting state is the
    # reload-equivalent - openGroupId null, the mode line
    # "Stateless room", close disabled, controls live, the
    # stateless turn state reset.
    segment = group_js_segment("closeSavedGroup")
    assert "openGroupId = null;" in segment
    assert '$("group-mode").textContent = "Stateless room";' in segment
    assert '$("close-group").disabled = true;' in segment
    assert '$("strategy").disabled = false;' in segment
    assert "box.disabled = false" in segment
    assert "history = [];" in segment
    assert "rrCursor = 0;" in segment
    # Substrate: the stateless road the page returns to is
    # the banked S305-shaped POST /group/turn.
    paths, _operations = census(client)
    assert "/api/v1/group/turn" in paths
    assert "post" in paths["/api/v1/group/turn"]
    asta_id, bram_id = _scenario_characters(client)
    with client.stream(
        "POST", "/api/v1/group/turn",
        json={"participant_ids": [asta_id, bram_id],
              "history": [], "user_text": "Speak, all.",
              "strategy": "broadcast", "rr_cursor": 0},
    ) as resp:
        assert resp.status_code == 200, resp.status
        raw = "".join(resp.iter_text())
    events = []
    for block in raw.split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    types = [e["type"] for e in events]
    assert types[-1] == "turn_end"
    assert types.index("typing") < types.index("token") < types.index("message")


# -- Area D: Accounting x8 (carried, by name) -------------------------------


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
    assert handled == {"typing", "reasoning", "token", "message", "turn_end"}
    s305 = (REPO / "tests" / "test_s305_group_ui.py").read_text(encoding="utf-8")
    assert len(re.findall(r"def test_", s305)) == 5


def test_d2_per_swipe_browsing_absent(tmp_path, monkeypatch):
    for path in (GROUP_JS, APP_JS, RENDERER_JS, GROUP_HTML):
        text = path.read_text(encoding="utf-8")
        for marker in ("show-all-swipes", "show_all_swipes", "showAllSwipes"):
            assert marker not in text, (marker, path.name)
    client = make_client(tmp_path, monkeypatch)
    paths, _operations = census(client)
    assert not any("all-swipes" in p or "all_swipes" in p for p in paths)
    # The active view is the only view the chat read
    # serves: one reasoning dict per message, never a
    # per-swipe browsing surface (P-206 ruling,
    # DECLINED-PENDING-WORD).
    world = build_world(client)
    for message in chat_messages(client, world["chat_id"]):
        assert isinstance(message["reasoning"], dict)


def test_d3_bot_runtime_absent(tmp_path, monkeypatch):
    policy = (SRC / "sandbox" / "policy.py").read_text(encoding="utf-8")
    assert '"chat.write",  # reserved in v1: declared, honoured nowhere' in policy
    plugins_api = (SRC / "plugins" / "api.py").read_text(encoding="utf-8")
    assert '"chat.write"' in plugins_api
    assert "RESERVED" in plugins_api
    # No code path honours it and no bots package exists
    # (joins A10 by behaviour, not just census).
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
    # is the only road to a changed label.
    entry_methods = set(paths["/api/v1/hub/entries/{entry_id}"])
    assert entry_methods <= {"get", "delete"}
    assert "delete" in entry_methods


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
    assert not any("search_history" in p.name or "history_search" in p.name
                   for p in SRC.rglob("*.py"))
    hub_paths = [p for p in paths if "/hub/" in p]
    assert hub_paths
    assert not any("history" in p for p in hub_paths)


def test_d7_stored_only_stands(tmp_path, monkeypatch):
    # The chats stream path (app.js streamGeneration)
    # collects reasoning for STORAGE only and renders
    # nothing live - the P-206 / P-209 banked pin,
    # restated at the gate at equal strength.
    app_js = APP_JS.read_text(encoding="utf-8")
    stream = app_js.split("async function streamGeneration", 1)[1].split(
        "async function sendMessage", 1)[0]
    assert 'event.type === "reasoning"' in stream  # the collector
    assert "reasoningParts.push(event.text)" in stream
    assert 'reasoningParts.join("")' in stream
    assert "reasoningView" not in stream  # no live rendering
    assert "reasoningPanel" not in stream
    # The group page's one transient exception is the
    # P-212 panel: built ONLY from this turn's forwarded
    # reasoning events (turn-local state), at completion,
    # never from a stored road and never persisted.
    submit = submit_segment()
    assert "reasoningByAuthor[event.author]" in submit
    assert submit.count("reasoningPanel(") == 1
    panel_at = submit.index("reasoningPanel(")
    message_at = submit.index('event.type === "message"')
    assert message_at < panel_at
    # Stored roads serve the stored record only: the
    # gate world's transcript view IS the stored row's
    # active view, byte for byte.
    client = make_client(tmp_path, monkeypatch)
    world = build_world(client)
    uid = owner_id(client)

    async def stored_view():
        async with client.factory() as session:
            history = await svc.get_history(
                session, uid, world["group_chat_id"])
            recorded = [m for m in history
                        if m.content == "ZqxGate218GroupReply"]
            assert len(recorded) == 1
            return rsn.active_view(
                recorded[0], getattr(recorded[0], "swipe_id", 0) or 0)

    expected = run(stored_view())
    transcript = group_transcript(client, world["group_id"])
    served = [m for m in transcript
              if m["content"] == "ZqxGate218GroupReply"]
    assert len(served) == 1
    assert served[0]["reasoning"] == expected


def test_d8_honest_limitations_hold(tmp_path, monkeypatch):
    factory_path = tmp_path / "d8.db"
    migrate_to_head(factory_path)
    factory = create_session_factory(create_db_engine(factory_path))

    async def make_user(name):
        async with factory() as session:
            user = User(name=name)
            session.add(user)
            await session.commit()
            return user.id

    user = run(make_user("zqx-gate218-d8"))

    async def seed_chat(turns):
        async with factory() as session:
            chat = await svc.create_chat(session, user, "Saga")
            chat_id = chat.id
            for role, content in turns:
                await svc.append_message(
                    session, user, chat_id, role, content)
            return chat_id

    # Extend onto a legacy / unwired swipe leaves its
    # reasoning_json byte-untouched - the extension
    # thinking is dropped BY DESIGN, while the text
    # extension itself lands.
    chat_id = run(seed_chat([("user", "Hail."), ("assistant", "Well met")]))

    async def last_row(chat):
        async with factory() as session:
            history = await svc.get_history(session, user, chat)
            return history[-1].id, history[-1].reasoning_json

    _mid, before_json = run(last_row(chat_id))
    backend = FakeChatBackend(
        chunks=(" more.",), reasoning_chunks=("lost thought",))

    async def extend():
        async with factory() as session:
            await ci.continue_chat(session, user, chat_id, backend=backend)

    run(extend())

    async def extended_row():
        async with factory() as session:
            history = await svc.get_history(session, user, chat_id)
            return history[-1]

    extended = run(extended_row())
    assert extended.content == "Well met more."
    assert extended.reasoning_json == before_json
    assert rsn.active_view(extended)["status"] == "not_recorded"

    # Impersonate's record lives only on the draft; accept
    # attaches nothing.
    chat2 = run(seed_chat([("user", "Hail."), ("assistant", "Well met")]))
    draft_backend = FakeChatBackend(
        chunks=("I will go.",), reasoning_chunks=("draft thought",))

    async def make_draft():
        async with factory() as session:
            return await ci.impersonate_draft(
                session, user, chat2, backend=draft_backend)

    draft = run(make_draft())
    assert draft["reasoning"] == {
        "status": "recorded", "text": "draft thought"}

    async def accept():
        async with factory() as session:
            return await ci.accept_impersonate(
                session, user, chat2, draft["content"],
                draft_id=draft["id"])

    accepted = run(accept())
    assert accepted.role == "user"
    assert rsn.active_view(accepted)["status"] == "not_recorded"

    # The trail declines name no road, segment or
    # surface: no cross-subject Inspector roll-up, no
    # /run or raw-append wiring from the group page, no
    # manual_speaker_id pick, no group management web
    # surfaces.
    client = make_client(tmp_path, monkeypatch)
    paths, _operations = census(client)
    assert not any("rollup" in p or "roll-up" in p for p in paths)
    group_js = GROUP_JS.read_text(encoding="utf-8")
    # The /run decline is a PAGE decline (P-214's ruling:
    # no /run or raw-append wiring from this page); the
    # banked backend road itself is not the page's to
    # remove. The page never names it.
    assert "/run" not in group_js
    assert group_js.count('method: "POST"') == 3
    assert "DELETE" not in group_js
    assert "PATCH" not in group_js
    assert "manual_speaker_id" not in group_js


# -- Hygiene x2 ---------------------------------------------------------------


async def _unit_documents(factory, uid, chat_id, group_id):
    async with factory() as session:
        overview = await overview_mod.build_overview(session, uid, chat_id)
        events = await events_mod.build_events_document(
            session, uid, chat_id)
        reasoning = await inspector_rsn_mod.build_reasoning_document(
            session, uid, chat_id)
        group_reasoning = await group_rsn_mod.build_group_reasoning_document(
            session, uid, group_id)
    return overview, events, reasoning, group_reasoning


def _snapshot(client, world):
    uid = owner_id(client)

    async def snap():
        async with client.factory() as session:
            rows = []
            for chat_id in (world["chat_id"], world["group_chat_id"]):
                history = await svc.get_history(session, uid, chat_id)
                rows.extend(
                    (m.id, m.content, m.reasoning_json) for m in history)
            events = await svc.list_events(session, uid, world["chat_id"])
            return rows, [(e.id, e.kind) for e in events]

    rows, events = run(snap())
    listed = client.get("/api/v1/groups").json()
    payload = json.dumps(
        {"rows": rows, "events": events, "groups": listed},
        sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def test_h1_pure_reads(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    world = build_world(client)
    uid = owner_id(client)
    before = _snapshot(client, world)
    first = run(_unit_documents(
        client.factory, uid, world["chat_id"], world["group_id"]))
    second = run(_unit_documents(
        client.factory, uid, world["chat_id"], world["group_id"]))
    # Repeated reads are dict-identical and every GET road
    # leaves the world's stores hash-identical.
    assert first == second
    for url in (
        f"/api/v1/inspector/chats/{world['chat_id']}",
        f"/api/v1/inspector/chats/{world['chat_id']}/events",
        f"/api/v1/inspector/chats/{world['chat_id']}/reasoning",
        f"/api/v1/inspector/groups/{world['group_id']}/reasoning",
    ):
        assert client.get(url).status_code == 200
    assert _snapshot(client, world) == before
    # No census document retains thinking text or message
    # content anywhere (the P-204 / P-210 law).
    for doc in first:
        blob = json.dumps(doc)
        assert THINK_A not in blob
        assert THINK_B not in blob
        assert CONTENT_A not in blob
        assert "ZqxGate218GroupReply" not in blob
    for doc in (first[2], first[3]):
        assert "text" not in set(walk_keys(doc))


def test_h2_one_session_agreement(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    world = build_world(client)
    uid = owner_id(client)
    unit = run(_unit_documents(
        client.factory, uid, world["chat_id"], world["group_id"]))
    http_overview = get_inspector(
        client, f"/api/v1/inspector/chats/{world['chat_id']}")
    http_events = get_inspector(
        client, f"/api/v1/inspector/chats/{world['chat_id']}/events")
    http_reasoning = get_inspector(
        client, f"/api/v1/inspector/chats/{world['chat_id']}/reasoning")
    http_group = get_inspector(
        client,
        f"/api/v1/inspector/groups/{world['group_id']}/reasoning")
    # One session walks all 4 Inspector roads plus the
    # Area C substrate roads on the gate world; every
    # HTTP document is dict-equal to its unit document.
    assert http_overview == unit[0]
    assert http_events == unit[1]
    assert http_reasoning == unit[2]
    assert http_group == unit[3]
    listed = client.get("/api/v1/groups")
    assert listed.status_code == 200, listed.text
    mine = [g for g in listed.json() if g["id"] == world["group_id"]]
    assert len(mine) == 1
    transcript = group_transcript(client, world["group_id"])
    assert mine[0]["message_count"] == len(transcript) == 3
    assert [m["id"] for m in transcript] == [
        entry["message_id"] for entry in http_group["messages"]]
