"""P-203 acceptance: the composed Inspector overview —
Part XIII opener (Assistant View, Inspector & Bots,
DERIVED scope).

Contract under test:
- ONE schema-versioned document (runmal-p203-inspector-
  overview-v1) per owned chat, joining the three
  roadmap-named banked sources (P-043 activation
  inspection, P-059 prompt preview, P-075 message
  provenance) plus scenario-binding state.
- The P-075 summary is carried VERBATIM from the banked
  read; a legacy (no-provenance) chat reads its honest
  not_recorded counts, never reconstructed facts.
- The GET composes no prompt and runs no activation
  inspection: no prompt text and no activation outcomes
  appear in the document (a read must not consume
  probability rolls as a side effect).
- Scenario bound vs unbound is stated honestly, counts
  only — no seeded content, no flag values.
- Unknown and unowned chats are refused in the house
  idiom; the document carries no message content, no
  prompt content and no secrets.
- No migration: head stays 0041; 0042 is not taken.
Fixtures mirror test_p075_message_provenance.py.
"""

from __future__ import annotations

import asyncio
import copy
import json

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Message, User
from runmal.inspector import OVERVIEW_SCHEMA
from runmal.inspector import overview as overview_mod

MARKER = "ZqxP203UnmistakableContent"


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0041"
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    client = TestClient(create_app(factory))
    client.factory = factory  # same DB, for service-layer seeding
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    client.token = token
    return client


def run(coro):
    return asyncio.run(coro)


def make_chat(client, title="Saga"):
    created = client.post("/api/v1/chats", json={"title": title})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def post_message(client, chat_id, role, content):
    resp = client.post(
        f"/api/v1/chats/{chat_id}/messages",
        json={"role": role, "content": content},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def get_overview(client, chat_id):
    resp = client.get(f"/api/v1/inspector/chats/{chat_id}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def walk_keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from walk_keys(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_keys(item)


# -- Schema + shape -------------------------------------------------------


def test_schema_pinned_and_no_migration(tmp_path, monkeypatch):
    make_client(tmp_path, monkeypatch)
    assert OVERVIEW_SCHEMA == "runmal-p203-inspector-overview-v1"
    assert MIGRATIONS[-1][0] == "0041"
    assert all(rev != "0042" for rev, _name, _mod in MIGRATIONS)


def test_document_shape_and_section_statuses(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    doc = get_overview(client, chat_id)
    assert doc["schema"] == "runmal-p203-inspector-overview-v1"
    assert doc["chat_id"] == chat_id
    assert doc["generated_from"] == [
        "P-043", "P-059", "P-075", "scenario bindings"]
    assert set(doc["sections"]) == {
        "provenance", "prompt", "lore_activation", "scenario"}
    for section in doc["sections"].values():
        assert section["status"] in overview_mod.SECTION_STATUSES
        assert "reason" in section
    # An empty chat is honestly empty on provenance.
    prov = doc["sections"]["provenance"]
    assert prov["status"] == "empty"
    assert prov["summary"]["total"] == 0


# -- Provenance: verbatim + legacy honesty ---------------------------------


def test_provenance_summary_carried_verbatim(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    post_message(client, chat_id, "user", "Hello there.")
    post_message(client, chat_id, "assistant", "A pasted reply.")
    banked = client.get(f"/api/v1/chats/{chat_id}/provenance")
    assert banked.status_code == 200, banked.text
    doc = get_overview(client, chat_id)
    section = doc["sections"]["provenance"]
    assert section["status"] == "available"
    assert section["reason"] is None
    # Verbatim: the very dict the banked P-075 road returns.
    assert section["summary"] == banked.json()["summary"]
    assert section["summary"]["total"] == 2
    assert section["summary"]["recorded"] == 2
    # Counts and statuses only: no per-message records ride along.
    assert "messages" not in section


def test_legacy_chat_honesty_never_reconstructed(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    factory = client.factory

    async def seed_legacy():
        async with factory() as session:
            session.add(Message(
                chat_id=chat_id, role="assistant",
                content="A legacy line.", provenance_json="{}"))
            await session.commit()

    run(seed_legacy())
    banked = client.get(f"/api/v1/chats/{chat_id}/provenance").json()
    assert banked["summary"]["recorded"] == 0
    assert banked["summary"]["not_recorded"] == 1
    doc = get_overview(client, chat_id)
    section = doc["sections"]["provenance"]
    # The not_recorded truth is carried verbatim, not rebuilt
    # into invented production facts.
    assert section["summary"] == banked["summary"]
    assert section["summary"]["by_model_status"] == {"unknown": 1}
    assert "messages" not in section


# -- No side effects: no prompt text, no activation outcomes ----------------


def test_no_prompt_text_and_no_activation_outcomes(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    post_message(client, chat_id, "user", f"{MARKER} hello")
    book = client.post("/api/v1/lorebooks", json={"name": "Tide Lore"})
    assert book.status_code == 201, book.text
    book_id = book.json()["id"]
    entry = client.post(
        f"/api/v1/lorebooks/{book_id}/entries",
        json={"name": "Tide", "content": f"{MARKER} lore body",
              "keys": ["tide"], "probability": 50},
    )
    assert entry.status_code == 201, entry.text
    scoped = client.put(
        f"/api/v1/lorebooks/{book_id}/scope",
        json={"scope_kind": "chat", "owner_id": chat_id},
    )
    assert scoped.status_code == 201, scoped.text
    doc = get_overview(client, chat_id)
    blob = json.dumps(doc)
    # No message content, no lore content, no composed prompt
    # text and no activation outcome of any kind.
    assert MARKER not in blob
    assert "roll" not in blob
    assert "probability" not in blob
    # The lore section names the bound book and points at the
    # banked P-043 road instead of running it.
    lore = doc["sections"]["lore_activation"]
    assert lore["status"] == "available"
    assert [b["lorebook_id"] for b in lore["books"]] == [book_id]
    pointer = lore["books"][0]["inspect"]
    assert pointer["method"] == "POST"
    assert pointer["path"] == f"/api/v1/lorebooks/{book_id}/inspect"
    assert pointer["schema"] == "runmal-p043-activation-inspection-v1"
    # The prompt section points at the banked POST roads.
    prompt = doc["sections"]["prompt"]
    assert prompt["status"] == "available"
    assert prompt["roads"]["inspect"] == {
        "method": "POST", "path": "/api/v1/debug/prompt-inspect"}
    assert prompt["roads"]["preview"] == {
        "method": "POST", "path": "/api/v1/debug/prompt-preview"}


def test_unbound_lore_reads_empty(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    doc = get_overview(client, chat_id)
    lore = doc["sections"]["lore_activation"]
    assert lore["status"] == "empty"
    assert lore["books"] == []
    assert lore["reason"]


# -- Scenario: bound vs unbound ---------------------------------------------

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


def test_scenario_bound_vs_unbound(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client, title="Harbour")
    doc = get_overview(client, chat_id)
    section = doc["sections"]["scenario"]
    assert section["status"] == "empty"
    assert section["bound"] is False
    assert section["reason"]
    definition = client.post("/api/v1/scenarios", json=copy.deepcopy(SCENARIO_BODY))
    assert definition.status_code == 201, definition.text
    definition = definition.json()
    bound = client.post(
        f"/api/v1/scenarios/{definition['id']}/bind",
        json={"chat_id": chat_id},
    )
    assert bound.status_code == 201, bound.text
    doc = get_overview(client, chat_id)
    section = doc["sections"]["scenario"]
    assert section["status"] == "available"
    assert section["bound"] is True
    assert section["binding"]["id"] == bound.json()["id"]
    assert section["binding"]["definition_id"] == definition["id"]
    assert section["binding"]["chat_id"] == chat_id
    # Counts only: seeded content and flag values stay on the
    # banked single-read road.
    blob = json.dumps(section)
    assert "The tide is going out." not in blob
    assert "met_maera" not in blob


# -- Refusals + safety --------------------------------------------------------


def test_unknown_chat_refused(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.get("/api/v1/inspector/chats/no-such-chat")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "chat not found"


def test_unowned_chat_refused_at_service_layer(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    factory = client.factory

    async def probe():
        async with factory() as session:
            stranger = User(name="stranger")
            session.add(stranger)
            await session.commit()
            return await overview_mod.build_overview(
                session, stranger.id, chat_id)

    assert run(probe()) is None


def test_document_carries_no_content_and_no_secrets(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    post_message(client, chat_id, "user", f"{MARKER} again")
    doc = get_overview(client, chat_id)
    blob = json.dumps(doc)
    assert MARKER not in blob
    assert client.token not in blob
    keys = set(walk_keys(doc))
    assert "content" not in keys
    assert "api_key" not in keys
    assert "secret" not in keys


def test_overview_is_a_pure_read(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    post_message(client, chat_id, "user", "One line.")
    first = get_overview(client, chat_id)
    second = get_overview(client, chat_id)
    assert first == second
    messages = client.get(f"/api/v1/chats/{chat_id}/messages")
    assert messages.status_code == 200
    rows = messages.json()
    rows = rows["messages"] if isinstance(rows, dict) else rows
    assert len(rows) == 1
