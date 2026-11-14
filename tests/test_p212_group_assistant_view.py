"""P-212 acceptance: group Assistant-View rendering
(Part XIII, DERIVED).

Contract under test (UI-only slice; no new endpoint, no
migration, no server change):
- group.html loads the banked renderer.js BEFORE group.js,
  so the shared P-206 view-model RunmalRenderer.reasoningView
  is the one source of truth for status semantics on the
  group page (called unchanged, never edited).
- group.js collects each author's forwarded stateless SSE
  reasoning events per turn (the banked P-208 road) into a
  per-turn, per-author collector inside the submit handler,
  rendering nothing mid-stream; at that author's message
  event it builds the P-205 input view (recorded + verbatim
  joined text when parts were collected, not_present when
  none were) and appends a group-local reasoningPanel -
  mirroring app.js's banked construction, textContent only,
  collapsed <details> - to the author's .gmsg container.
- The user bubble never carries a panel; history entries
  stay exactly {author, content}; reasoning is never
  persisted client-side and never sent back to the server.
- The stateless road still stores nothing; the persistent
  transcript road is untouched. D1 stays FENCED: no pin
  here asserts anything about an errored stream's panel.
- Fences: migration head stays 0042 (no m0043); the app
  route census stays 356 paths / 439 operations (zero
  census heals - no road is added); the chat page wiring
  (P-206) still holds.
Fixtures mirror test_s305_group_ui.py /
test_p206_assistant_view.py / test_p208_groupchat_reasoning.py.
group.js is not a node module - it exports nothing and
binds DOM listeners at load - so, like app.js before it,
its wiring is pinned by page, served-source and segment
assertions, never by importing it.
"""

import asyncio
import copy
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends.fake import FakeChatBackend
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Group, Message
from runmal.generation import service as gen_service

REPO = Path(__file__).parent.parent
GROUP_JS = REPO / "src" / "runmal" / "web" / "static" / "group.js"
RENDERER = REPO / "src" / "runmal" / "web" / "static" / "renderer.js"
APP_JS = REPO / "src" / "runmal" / "web" / "static" / "app.js"
FIXTURES = Path(__file__).parent / "fixtures" / "cards"
V2_CARD = json.loads((FIXTURES / "v2.json").read_text())

THINK = ("weigh ", "the toll")
THINK_TEXT = "weigh the toll"
ANSWER = ("The ", "answer.")
ANSWER_TEXT = "The answer."


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
    return client


def patch_backend(monkeypatch, factory):
    monkeypatch.setattr(gen_service, "default_backend", factory)


def reasoning_fake():
    return FakeChatBackend(chunks=ANSWER, reasoning_chunks=THINK)


def make_character(client, name):
    card = copy.deepcopy(V2_CARD)
    card["name"] = name
    created = client.post("/api/v1/characters", json={"card": card})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def make_stateless_characters(client):
    ids = {}
    for name in ("Bryn", "Una", "Kol"):
        ids[name] = make_character(client, name)
    return ids


def run_stateless_turn(client, ids, user_text, strategy="mention"):
    with client.stream(
        "POST",
        "/api/v1/group/turn",
        json={
            "participant_ids": list(ids),
            "history": [],
            "user_text": user_text,
            "strategy": strategy,
            "rr_cursor": 0,
        },
    ) as resp:
        assert resp.status_code == 200, resp.status
        raw = "".join(resp.iter_text())
    events = []
    for block in raw.split("\n\n"):
        for line in block.split("\n"):
            if line.startswith("data:"):
                events.append(json.loads(line[5:]))
    return events


def make_group(client, members, policy=None):
    resp = client.post(
        "/api/v1/groups",
        json={"name": "Mead Hall", "member_character_ids": list(members)})
    assert resp.status_code == 201, resp.text
    group = resp.json()
    if policy:
        upd = client.patch(
            f"/api/v1/groups/{group['id']}", json={"speaker_policy": policy})
        assert upd.status_code == 200, upd.text
    return group


def list_group(client, members):
    group = make_group(client, members, policy="list")
    gid = group["id"]
    upd = client.patch(
        f"/api/v1/groups/{gid}", json={"speaker_config": {"order": list(members)}})
    assert upd.status_code == 200, upd.text
    return group


def next_turn(client, gid, **kw):
    resp = client.post(f"/api/v1/groups/{gid}/next", json=kw)
    assert resp.status_code == 200, resp.text
    return resp.json()


# -- source segmentation helpers (group.js wiring pins) ---------------------


def group_source():
    return GROUP_JS.read_text()


def handler_segment(source):
    return source.split('addEventListener("submit"', 1)[1]


def branch_segment(handler, kind, next_kind=None):
    start = handler.index(f'event.type === "{kind}"')
    if next_kind is None:
        return handler[start:]
    return handler[start:handler.index(f'event.type === "{next_kind}"', start)]


# -- 1. Page wiring ------------------------------------------------------------


def test_01_page_loads_renderer_before_group_js(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    page = client.get("/group")
    assert page.status_code == 200, page.text
    assert page.text.index("/static/theme.js") < page.text.index(
        "/static/renderer.js")  # theme stays first
    assert page.text.index("/static/renderer.js") < page.text.index(
        "/static/group.js")  # the model lands BEFORE its consumer
    assert client.get("/static/renderer.js").status_code == 200
    assert client.get("/static/group.js").status_code == 200


# -- 2. Shared model, unchanged -------------------------------------------------


def run_view_model(calls):
    script = (
        "const r = require(" + repr(str(RENDERER)) + ");"
        "const out = [" + ", ".join(
            "r.reasoningView(" + c + ")" for c in calls) + "];"
        "console.log(JSON.stringify(out));"
    )
    proc = subprocess.run(["node", "-e", script],
                          capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0, proc.stderr  # never throws
    return json.loads(proc.stdout.strip())


needs_node = pytest.mark.skipif(
    shutil.which("node") is None, reason="node not available")


@needs_node
def test_02_shared_reasoning_view_model_unchanged():
    source = RENDERER.read_text()
    assert "reasoningView" in source  # exported via RunmalRenderer
    assert "RunmalRenderer" in source
    recorded, not_present = run_view_model([
        "{status: 'recorded', text: 'deep thought'}",
        "{status: 'not_present'}",
    ])
    # The two shapes P-212 builds, read by the BANKED model -
    # the group page's model is that model, not a copy.
    assert recorded == {"kind": "recorded", "label": "Thinking",
                        "text": "deep thought"}
    assert not_present == {"kind": "status",
                           "text": "No thinking was returned for this reply."}


# -- 3-10. group.js wiring pins ---------------------------------------------------


def test_03_reasoning_branch_collects_only():
    handler = handler_segment(group_source())
    branch = branch_segment(handler, "reasoning", "token")
    assert "reasoningByAuthor[event.author] = []" in branch  # first sight
    assert "reasoningByAuthor[event.author].push(event.text)" in branch
    assert "addBubble" not in branch  # creates NO bubble
    assert "reasoningPanel" not in branch  # renders NOTHING mid-stream
    assert "history" not in branch  # touches no history


def test_04_collector_is_per_turn_inside_submit_handler():
    source = group_source()
    prefix, handler = source.split('addEventListener("submit"', 1)
    assert "reasoningByAuthor" not in prefix  # no module-level state
    assert "let bubbles = {};" in handler
    assert "let typing = {};" in handler
    assert "let reasoningByAuthor = {};" in handler
    # Declared beside bubbles / typing, before the read loop:
    # the per-turn reset is the declaration's position.
    assert handler.index("let bubbles") < handler.index(
        "let reasoningByAuthor") < handler.index("for (;;)")


def test_05_render_is_completion_only_in_message_branch():
    handler = handler_segment(group_source())
    message = branch_segment(handler, "message", "turn_end")
    assert "window.RunmalRenderer.reasoningView(view)" in message
    assert "reasoningPanel(" in message
    for kind, nxt in (("typing", "reasoning"), ("reasoning", "token"),
                      ("token", "message"), ("turn_end", None)):
        branch = branch_segment(handler, kind, nxt)
        assert "reasoningView" not in branch, kind
        assert "reasoningPanel" not in branch, kind
    # The panel is appended only AFTER the banked history.push.
    assert message.index("history.push") < message.index("reasoningPanel(")
    assert handler.count("reasoningPanel(") == 1  # one render site


def test_06_recorded_construction_from_collected_parts():
    handler = handler_segment(group_source())
    message = branch_segment(handler, "message", "turn_end")
    assert 'status: "recorded"' in message
    assert 'reasoningByAuthor[event.author].join("")' in message
    assert "(reasoningByAuthor[event.author] || []).length" in message


def test_07_not_present_construction_and_no_other_status():
    source = group_source()
    handler = handler_segment(source)
    message = branch_segment(handler, "message", "turn_end")
    assert '{ status: "not_present" }' in message
    # not_recorded and unknown are STORAGE states; this surface
    # stores nothing, so group.js constructs neither, anywhere.
    assert "not_recorded" not in source
    assert 'status: "unknown"' not in source


def test_08_panel_dom_safety_textcontent_only():
    source = group_source()
    panel = source.split("function reasoningPanel(view)", 1)[1].split(
        "async function loadRoster", 1)[0]
    assert "body.textContent = view.text" in panel
    assert "line.textContent = view.text" in panel
    assert "summary.textContent = view.label" in panel
    assert "innerHTML" not in panel  # never innerHTML
    assert "renderMarkdown" not in panel  # never the markdown road
    assert 'createElement("details")' in panel  # native disclosure
    assert "details.open" not in panel  # collapsed by default
    assert 'setAttribute("open"' not in panel
    assert "if (!view) return null;" in panel  # the banked null fence


def test_09_panel_placement_and_user_bubble_untouched():
    source = group_source()
    handler = handler_segment(source)
    message = branch_segment(handler, "message", "turn_end")
    # Appended to the author's .gmsg container: the parent of
    # the body element addBubble returned and bubbles holds.
    assert "bubbles[event.author].parentElement.appendChild(panel)" in message
    assert "if (panel && bubbles[event.author])" in message  # no bubble, no panel
    # The user bubble: banked call site, no reasoning, no panel.
    assert "function addBubble(author, content)" in source
    assert 'addBubble("user", text);' in handler
    before_fetch = handler.split('"/api/v1/group/turn"', 1)[0]
    assert "reasoningPanel" not in before_fetch
    assert "reasoningView" not in before_fetch


def test_10_history_law_and_request_body_keys():
    source = group_source()
    handler = handler_segment(source)
    assert 'history.push({ author: "user", content: text });' in handler
    assert ("history.push({ author: event.author, content: event.content });"
            in handler)  # entries stay exactly {author, content}
    body = handler.split("JSON.stringify({", 1)[1].split("})", 1)[0]
    for key in ("participant_ids", "history: sentHistory", "user_text",
                "strategy", "rr_cursor"):
        assert key in body, key  # the banked S305 request set
    assert "reasoning" not in body  # never sent back to the server


# -- 11-12. Server truth / storage honesty (behaviour) ---------------------------


def test_11_stateless_stream_surface_unmoved(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    ids = make_stateless_characters(client)
    patch_backend(monkeypatch, lambda: FakeChatBackend(
        chunks=("Hello ", "there."), reasoning_chunks=THINK))
    events = run_stateless_turn(client, ids.values(), "Hey @Una, your counsel?")
    reasoning = [e for e in events if e["type"] == "reasoning"]
    assert reasoning == [
        {"type": "reasoning", "author": "Una", "text": "weigh "},
        {"type": "reasoning", "author": "Una", "text": "the toll"},
    ]  # per speaker, in arrival order - the parts the collector joins
    message_idx = next(i for i, e in enumerate(events) if e["type"] == "message")
    assert all(i < message_idx for i, e in enumerate(events)
               if e["type"] == "reasoning")  # before that speaker's message
    assert [e["type"] for e in events] == [
        "typing", "reasoning", "reasoning", "token", "token",
        "message", "turn_end"]  # otherwise the banked S305 shape
    message = next(e for e in events if e["type"] == "message")
    assert message["content"] == "Hello there."
    assert "weigh" not in message["content"]


def _row_counts(db_path):
    async def _count():
        engine = create_db_engine(db_path)
        factory = create_session_factory(engine)
        async with factory() as session:
            messages = await session.execute(select(func.count(Message.id)))
            groups = await session.execute(select(func.count(Group.id)))
            return int(messages.scalar_one()), int(groups.scalar_one())
    return asyncio.run(_count())


def test_12_stateless_stores_nothing_persistent_road_untouched(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    ids = make_stateless_characters(client)
    before = _row_counts(client.db_path)
    patch_backend(monkeypatch, lambda: FakeChatBackend(
        chunks=("Hello ", "there."), reasoning_chunks=THINK))
    events = run_stateless_turn(client, ids.values(), "Hey @Una, your counsel?")
    assert any(e["type"] == "reasoning" for e in events)  # it really streamed
    # NO group, NO transcript message, NO stored reasoning:
    # the road stores nothing before or after P-212.
    assert _row_counts(client.db_path) == before
    # The persistent transcript road still serves its banked
    # active reasoning view for a stored group fixture.
    # Reuse two of the stateless roster's characters (a fresh
    # duplicate card would answer the duplicate_exact 200).
    group = list_group(client, [ids["Bryn"], ids["Una"]])
    gid = group["id"]
    patch_backend(monkeypatch, reasoning_fake)
    result = next_turn(client, gid, user_text="Speak, friends.", generate=True)
    assert result["message"]["content"] == ANSWER_TEXT
    assert result["message"]["reasoning"]["status"] == "recorded"
    assert result["message"]["reasoning"]["text"] == THINK_TEXT
    transcript = client.get(f"/api/v1/groups/{gid}/messages").json()
    stored = [m for m in transcript if m["id"] == result["message"]["id"]][0]
    assert stored["reasoning"]["status"] == "recorded"
    assert stored["reasoning"]["text"] == THINK_TEXT


# -- 13-14. Fences ------------------------------------------------------------------


def test_13_route_census_unchanged_no_heal(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    paths = client.get("/openapi.json").json()["paths"]
    operations = sum(
        len([k for k in methods
             if k in ("get", "post", "put", "delete", "patch")])
        for methods in paths.values())
    # No road is added, moved or removed by P-212: the census
    # stands at the P-211 census and NO pin is healed.
    assert len(paths) == 365
    assert operations == 455


def test_14_migration_head_and_chat_wiring_fences(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0042"
    assert current_revision(client.db_path) == "0042"
    assert all(rev != "0043" for rev, _desc, _mod in MIGRATIONS)
    import runmal.db.migrations as migrations_pkg
    names = os.listdir(os.path.dirname(migrations_pkg.__file__))
    assert not any(name.startswith("m0043") for name in names)
    # The chat surface (P-206 test_14's assertions) still holds:
    # the group render moved nothing it did not own.
    page = client.get("/chat")
    assert page.status_code == 200, page.text
    assert "renderer.js" in page.text and "app.js" in page.text
    app = APP_JS.read_text()
    assert "function reasoningPanel(view)" in app
    assert "RunmalRenderer.reasoningView(reasoning)" in app
    assert "m.reasoning || null" in app
    assert ("function appendMessage(role, text, rendered, marking, "
            "reasoning)") in app
