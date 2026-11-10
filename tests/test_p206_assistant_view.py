"""P-206 acceptance: the Assistant View - rendering the P-205
reasoning record in the chat web surface (Part XIII, DERIVED).

Contract under test (UI-only slice; no new endpoint, no
migration, no server change):
- The banked thread surfaces (chat payload, bare + paged
  GET /chats/{id}/messages) already carry each message's
  P-205 active reasoning view; the recorded text arrives
  verbatim and a non-recorded view exposes NO text key.
- After select_swipe, a re-read returns the NEW swipe's
  record - the server resolves; the view never does.
- The pure view-model RunmalRenderer.reasoningView maps
  recorded + text to the recorded model, the three other
  statuses to three distinct honest status lines with no
  text, and null / malformed input to no panel, never
  throwing (node pins, S302/P-107 road).
- app.js wires m.reasoning through renderThread /
  appendMessage, sets thinking text via textContent only,
  and streamGeneration renders no live thinking (the
  stored-only honesty position; P-209 restated test_16 when
  the stream began collecting reasoning for storage only --
  the pin now asserts the collector AND no live rendering).
- Fences: migration head stays 0042; the app route census
  equals the P-205 census (354 paths / 437 operations).
Fixtures mirror test_p205_reasoning_record.py.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import reasoning as rsn
from runmal.chats import service as svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.deps import get_or_create_owner
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS

REPO = Path(__file__).parent.parent
RENDERER = REPO / "src" / "runmal" / "web" / "static" / "renderer.js"
APP_JS = REPO / "src" / "runmal" / "web" / "static" / "app.js"
THINKING = "weigh the toll"


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


async def seed_world(client):
    """One chat: user line, a recorded reply, a not_present reply."""
    async with client.factory() as session:
        owner = await get_or_create_owner(session)
        chat = await svc.create_chat(session, owner.id, "Saga")
        chat_id = chat.id
        await svc.append_message(session, owner.id, chat_id, "user", "Hail.")
        recorded = await svc.append_message(
            session, owner.id, chat_id, "assistant", "The bridge is open.",
            reasoning=rsn.build_record(status="recorded", text=THINKING))
        await svc.append_message(
            session, owner.id, chat_id, "assistant", "Plain answer.",
            reasoning=rsn.build_record(status="not_present"))
    return chat_id, recorded.id


def by_content(messages):
    return {m["content"]: m for m in messages}


# -- Thread surfaces (the banked reads the view consumes) -------------------


async def test_01_chat_payload_carries_reasoning_verbatim(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id, _mid = await seed_world(client)
    payload = client.get(f"/api/v1/chats/{chat_id}")
    assert payload.status_code == 200, payload.text
    view = by_content(payload.json()["messages"])["The bridge is open."]["reasoning"]
    assert view["status"] == "recorded"
    assert view["text"] == THINKING  # exact, verbatim
    assert view["reasoning_status"] == "recorded"


async def test_02_bare_messages_carry_reasoning(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id, _mid = await seed_world(client)
    listing = client.get(f"/api/v1/chats/{chat_id}/messages")
    assert listing.status_code == 200, listing.text
    view = by_content(listing.json())["The bridge is open."]["reasoning"]
    assert view["status"] == "recorded" and view["text"] == THINKING


async def test_03_paged_messages_carry_reasoning(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id, _mid = await seed_world(client)
    page = client.get(f"/api/v1/chats/{chat_id}/messages?limit=10&offset=0")
    assert page.status_code == 200, page.text
    view = by_content(page.json()["messages"])["The bridge is open."]["reasoning"]
    assert view["status"] == "recorded" and view["text"] == THINKING


async def test_04_unwired_message_reads_not_recorded(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/chats", json={"title": "Saga"})
    assert created.status_code == 201, created.text
    chat_id = created.json()["id"]
    posted = client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"role": "assistant", "content": "Answer."})
    assert posted.status_code == 201, posted.text  # key present, never a 404
    assert posted.json()["reasoning"]["status"] == "not_recorded"
    listing = client.get(f"/api/v1/chats/{chat_id}/messages").json()
    assert listing[0]["reasoning"]["status"] == "not_recorded"


async def test_05_non_recorded_view_exposes_no_text_key(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id, _mid = await seed_world(client)
    listing = client.get(f"/api/v1/chats/{chat_id}/messages").json()
    views = by_content(listing)
    assert views["Plain answer."]["reasoning"]["status"] == "not_present"
    assert "text" not in views["Plain answer."]["reasoning"]
    assert "text" not in views["Hail."]["reasoning"]  # nothing to leak


async def test_06_reread_after_select_swipe_returns_new_record(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id, message_id = await seed_world(client)
    added = client.post(
        f"/api/v1/chats/{chat_id}/messages/{message_id}/swipes",
        json={"content": "Answer two."})
    assert added.status_code == 201, added.text
    selected = client.post(
        f"/api/v1/chats/{chat_id}/messages/{message_id}/swipes/select",
        json={"index": 1})
    assert selected.status_code == 200, selected.text
    listing = client.get(f"/api/v1/chats/{chat_id}/messages").json()
    active = [m for m in listing if m["id"] == message_id][0]
    assert active["content"] == "Answer two."  # server resolved the deck
    assert active["reasoning"]["status"] == "not_recorded"  # NEW swipe's record
    assert "text" not in active["reasoning"]


async def test_07_full_document_reasoning_endpoint_unchanged(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id, message_id = await seed_world(client)
    road = client.get(
        f"/api/v1/chats/{chat_id}/messages/{message_id}/reasoning")
    assert road.status_code == 200, road.text
    doc = road.json()
    assert doc["swipes"]["0"] == {"status": "recorded", "text": THINKING}
    assert doc["message_id"] == message_id and doc["chat_id"] == chat_id
    missing = client.get(f"/api/v1/chats/{chat_id}/messages/nope/reasoning")
    assert missing.status_code == 404  # house 404 idiom, unchanged


# -- View-model pins (renderer.js under node) --------------------------------


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
def test_08_recorded_with_text_gives_recorded_model():
    (model,) = run_view_model(
        ["{status: 'recorded', text: 'deep thought'}"])
    assert model == {"kind": "recorded", "label": "Thinking",
                     "text": "deep thought"}


@needs_node
def test_09_not_present_gives_its_status_line():
    (model,) = run_view_model(["{status: 'not_present'}"])
    assert model == {"kind": "status",
                     "text": "No thinking was returned for this reply."}
    assert "text" not in model or model["kind"] == "status"


@needs_node
def test_10_not_recorded_gives_its_status_line():
    (model,) = run_view_model(["{status: 'not_recorded'}"])
    assert model == {"kind": "status",
                     "text": "Thinking was not recorded for this reply."}


@needs_node
def test_11_unknown_gives_its_status_line():
    (model,) = run_view_model(["{status: 'unknown'}"])
    assert model == {"kind": "status", "text":
                     "Thinking record state is unknown for this reply."}
    # the three status lines are distinct (pins 09/10/11 together)
    lines = run_view_model(["{status: 'not_present'}",
                            "{status: 'not_recorded'}",
                            "{status: 'unknown'}"])
    assert len({m["text"] for m in lines}) == 3
    assert all("label" not in m for m in lines)  # status models carry no text payload


@needs_node
def test_12_null_and_missing_reasoning_give_no_panel():
    assert run_view_model(["null", "undefined", "42", "'junk'"]) == [
        None, None, None, None]


@needs_node
def test_13_unusable_recorded_and_unrecognised_status_give_unknown():
    models = run_view_model([
        "{status: 'recorded'}",                 # recorded, text missing
        "{status: 'recorded', text: ''}",       # recorded, text empty
        "{status: 'recorded', text: 7}",        # recorded, text not a string
        "{status: 'telepathic', text: 'boo'}",  # unrecognised status
    ])
    for model in models:
        assert model == {"kind": "status", "text":
                         "Thinking record state is unknown for this reply."}


# -- Wiring / safety pins ------------------------------------------------------


def test_14_chat_page_and_wiring(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    page = client.get("/chat")
    assert page.status_code == 200, page.text
    assert "renderer.js" in page.text and "app.js" in page.text
    renderer = client.get("/static/renderer.js").text
    assert "reasoningView" in renderer  # exported via RunmalRenderer
    app = client.get("/static/app.js").text
    assert "function reasoningPanel(view)" in app
    assert "RunmalRenderer.reasoningView(reasoning)" in app
    assert "m.reasoning || null" in app  # renderThread passes it through
    assert ("appendMessage(m.role, m.content, true, "
            "m.voice_marking || null, m.reasoning || null)") in app
    assert ("function appendMessage(role, text, rendered, marking, "
            "reasoning)") in app  # one trailing parameter


def test_15_thinking_text_set_via_textcontent_only():
    source = APP_JS.read_text()
    panel = source.split("function reasoningPanel(view)", 1)[1].split(
        "function appendMessage", 1)[0]
    assert "textContent" in panel
    assert "body.textContent = view.text" in panel
    assert "line.textContent = view.text" in panel
    assert "innerHTML" not in panel  # never innerHTML
    assert "renderMarkdownLite" not in panel  # never the markdown road
    assert 'createElement("details")' in panel  # native disclosure
    assert "details.open" not in panel and ".setAttribute(\"open\"" not in panel


def test_16_stream_generation_collects_for_storage_renders_nothing_live():
    # Restated by P-209 (the one named heal; P-207 test_e3
    # precedent): streamGeneration now COLLECTS reasoning
    # dicts for storage only, so the old '"reasoning" not in
    # stream' sentence is false BY DESIGN. The new truth, at
    # equal-or-greater strength: the collector is present,
    # token / done handling is intact, and NOTHING in the
    # stream path renders live thinking -- the panel still
    # renders the STORED record at thread read time.
    source = APP_JS.read_text()
    stream = source.split("async function streamGeneration", 1)[1].split(
        "async function sendMessage", 1)[0]
    assert 'event.type === "token"' in stream
    assert 'event.type === "done"' in stream
    assert 'event.type === "reasoning"' in stream  # the collector
    assert "reasoningParts.push(event.text)" in stream
    assert 'reasoningParts.join("")' in stream  # built for the append
    assert 'status: "recorded"' in stream
    assert 'status: "not_present"' in stream
    assert "reasoningView" not in stream  # no live rendering
    assert "reasoningPanel" not in stream  # no live panel
    assert "bubble.textContent = full" in stream  # tokens only


# -- Fence pins ------------------------------------------------------------------


def test_17_migration_head_stays_0042(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    assert MIGRATIONS[-1][0] == "0042"
    assert current_revision(client.db_path) == "0042"


def test_18_route_census_equals_p205_census(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    paths = client.get("/openapi.json").json()["paths"]
    operations = sum(
        len([k for k in methods
             if k in ("get", "post", "put", "delete", "patch")])
        for methods in paths.values())
    assert len(paths) == 354  # the P-205 census: no new road
    assert operations == 437
