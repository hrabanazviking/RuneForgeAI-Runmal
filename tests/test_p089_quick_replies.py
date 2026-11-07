"""P-089 Quick Replies battery.

Pins the contract from hidden_files/P089_DESIGN.md: the
citizen manifest as strict round-tripping data, the P-082
empty-grant stance, the durable per-user definition store
with strict CRUD validation (shorthand text, chained steps,
scopes, duplicate names, owner isolation, corrupt-store
refusal), one-tap execution through the chats road (P-055
strict macro expansion, variables threading across steps,
declared order), per-step failure reporting with a persisted
record (never silently half-applied), input-sender semantics
(user-role message + an honest P-075 receipt), P-076 undo
coverage per appended step, the HTTP surface, and the
neighbours (migration head stays 0041, no 0042).
"""

from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.characters import service as characters_svc
from runmal.chats import service as chats_svc
from runmal.chats import undo as undo_mod
from runmal.chats.greetings import GreetingChoice
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.plugins import quick_replies as qr
from runmal.plugins import service as plugin_service
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginRegistry, PluginState


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


def card_dict(name="Asta"):
    return {
        "spec": "chara_card_v2", "spec_version": "2.0", "name": name,
        "description": "A keeper of the northern lighthouse.",
        "personality": "Steady.", "scenario": "A test hall.",
        "first_mes": "Hail!", "mes_example": "", "creator_notes": "",
        "system_prompt": "", "post_history_instructions": "",
        "alternate_greetings": [], "tags": [], "creator": "forge",
        "character_version": "1.0",
    }


async def seed_chat(factory, uid, with_character=True):
    async with factory() as session:
        character_id = None
        if with_character:
            character = await characters_svc.create_character(
                session, uid, card_dict())
            character_id = character.id
        chat = await chats_svc.create_chat(
            session, uid, title="The Lighthouse",
            character_id=character_id,
            greeting=GreetingChoice(mode="quiet"))
        await session.commit()
        return chat.id


async def history(factory, uid, chat_id):
    async with factory() as session:
        messages = await chats_svc.get_history(session, uid, chat_id)
        return [(m.role, m.content) for m in messages]


# -- Citizen / manifest -----------------------------------------------------


def test_manifest_round_trips_and_registers():
    data = qr.manifest_data()
    manifest = manifest_from_data(data)
    assert manifest_to_data(manifest) == data
    assert manifest.id == qr.PLUGIN_ID == "runmal.quick-replies"
    assert "chat.write" not in manifest.permissions
    registry = PluginRegistry()
    record, _plugin = qr.register_plugin(registry)
    assert record.state == PluginState.REGISTERED
    assert registry.get(qr.PLUGIN_ID).manifest.id == qr.PLUGIN_ID


def test_sandbox_grants_are_empty():
    grants = qr.sandbox_grants()
    assert grants.resources == frozenset()


def test_ui_contribution_is_the_one_tap_toolbar_panel():
    registry = PluginRegistry()
    qr.register_plugin(registry, enable=True)
    contributions = registry.ui_contributions("chat.toolbar")
    assert any(c["plugin_id"] == qr.PLUGIN_ID for c in contributions)


# -- Definition validation ----------------------------------------------------


def test_text_shorthand_becomes_one_input_sender_step():
    body = qr.reply_from_data({"name": "Hail", "text": "Hail, {{char}}!"})
    assert body["steps"] == [{
        "kind": "message", "role": "user",
        "text": "Hail, {{char}}!", "sender": "input_sender"}]
    assert body["scope"] == "user" and body["chat_id"] is None
    assert body["enabled"] is True


def test_text_and_steps_together_reject():
    with pytest.raises(qr.QuickReplyError):
        qr.reply_from_data({"name": "X", "text": "hi",
                            "steps": [{"text": "hi"}]})


def test_unknown_keys_and_bad_shapes_reject():
    with pytest.raises(qr.QuickReplyError):
        qr.reply_from_data({"name": "X", "text": "hi", "bogus": 1})
    with pytest.raises(qr.QuickReplyError):
        qr.reply_from_data({"name": "X", "steps": []})
    with pytest.raises(qr.QuickReplyError):
        qr.reply_from_data({"name": " ", "text": "hi"})
    with pytest.raises(qr.QuickReplyError):
        qr.reply_from_data({"name": "X", "steps": [{"text": "hi"}] * 9})
    with pytest.raises(qr.QuickReplyError):
        qr.reply_from_data({"name": "X", "steps": [{"text": " "}]})


def test_input_sender_requires_user_role():
    with pytest.raises(qr.QuickReplyError):
        qr.step_from_data({"text": "hi", "role": "assistant",
                           "sender": "input_sender"})
    step = qr.step_from_data({"text": "hi", "role": "assistant"})
    assert step["sender"] == "quick_reply"


def test_scope_rules():
    chat_id = str(uuid.uuid4())
    body = qr.reply_from_data({"name": "X", "text": "hi",
                               "scope": "chat", "chat_id": chat_id})
    assert body["chat_id"] == chat_id
    with pytest.raises(qr.QuickReplyError):
        qr.reply_from_data({"name": "X", "text": "hi", "scope": "chat"})
    with pytest.raises(qr.QuickReplyError):
        qr.reply_from_data({"name": "X", "text": "hi",
                            "chat_id": chat_id})


# -- Store CRUD -----------------------------------------------------------------


def test_crud_round_trip_and_persistence(tmp_path):
    uid = str(uuid.uuid4())
    created = qr.create_reply(uid, {"name": "Hail", "text": "Hail!"})
    assert qr.get_reply(uid, created["id"])["name"] == "Hail"
    # A fresh read from disk (the store is the memory) agrees.
    doc = json.loads(qr.store_path(uid).read_text(encoding="utf-8"))
    assert doc["schema"] == qr.STORE_SCHEMA
    assert doc["replies"][0]["id"] == created["id"]
    updated = qr.update_reply(uid, created["id"],
                              {"name": "Hail Twice", "text": "Hail hail!"})
    assert updated["name"] == "Hail Twice"
    assert updated["created_at"] == created["created_at"]
    assert qr.delete_reply(uid, created["id"]) is True
    assert qr.get_reply(uid, created["id"]) is None
    assert qr.delete_reply(uid, created["id"]) is False


def test_duplicate_names_reject_per_scope(tmp_path):
    uid = str(uuid.uuid4())
    qr.create_reply(uid, {"name": "Hail", "text": "one"})
    with pytest.raises(qr.QuickReplyError):
        qr.create_reply(uid, {"name": "Hail", "text": "two"})
    chat_id = str(uuid.uuid4())
    other = qr.create_reply(uid, {"name": "Hail", "text": "three",
                                  "scope": "chat", "chat_id": chat_id})
    assert other["scope"] == "chat"


def test_list_replies_scope_filtering(tmp_path):
    uid = str(uuid.uuid4())
    chat_a, chat_b = str(uuid.uuid4()), str(uuid.uuid4())
    qr.create_reply(uid, {"name": "Global", "text": "g"})
    qr.create_reply(uid, {"name": "For A", "text": "a",
                          "scope": "chat", "chat_id": chat_a})
    names_all = [r["name"] for r in qr.list_replies(uid)]
    assert names_all == ["Global"]
    names_a = [r["name"] for r in qr.list_replies(uid, chat_id=chat_a)]
    assert names_a == ["For A", "Global"]
    names_b = [r["name"] for r in qr.list_replies(uid, chat_id=chat_b)]
    assert names_b == ["Global"]


def test_owner_isolation(tmp_path):
    uid, other = str(uuid.uuid4()), str(uuid.uuid4())
    created = qr.create_reply(uid, {"name": "Mine", "text": "hi"})
    assert qr.get_reply(other, created["id"]) is None
    assert qr.list_replies(other) == []
    assert qr.update_reply(other, created["id"],
                           {"name": "Stolen", "text": "x"}) is None
    assert qr.delete_reply(other, created["id"]) is False


def test_corrupt_store_raises_never_wipes(tmp_path):
    uid = str(uuid.uuid4())
    path = qr.store_path(uid)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(qr.QuickReplyError):
        qr.list_replies(uid)
    assert path.read_text(encoding="utf-8") == "{not json"


# -- Execution --------------------------------------------------------------------


async def test_execute_input_sender_lands_as_user_with_honest_receipt(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    reply = qr.create_reply(uid, {"name": "Hail",
                                  "text": "Hail, {{char}}! I am {{user}}."})
    async with factory() as session:
        record = await qr.execute_reply(session, uid, chat_id, reply["id"])
    assert record["status"] == "ok"
    assert record["steps"][0]["expanded_text"] == "Hail, Asta! I am volmarr."
    assert await history(factory, uid, chat_id) == [
        ("user", "Hail, Asta! I am volmarr.")]
    async with factory() as session:
        messages = await chats_svc.get_history(session, uid, chat_id)
        view = chats_svc.message_to_dict(messages[0])
    origin = view["provenance"]["origin"]
    assert origin["kind"] == "manual"
    assert origin["via"] == "quick_reply"
    assert origin["sender"] == "input_sender"
    assert origin["quick_reply_id"] == reply["id"]
    assert origin["step_index"] == 0
    # The execution record persisted.
    stored = qr.list_executions(uid)
    assert stored and stored[0]["id"] == record["id"]


async def test_execute_chained_steps_in_order_variables_thread(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    reply = qr.create_reply(uid, {
        "name": "Chain",
        "steps": [
            {"text": "{{setvar::place::the lighthouse}}We gather.",
             "role": "system"},
            {"text": "Meet at {{getvar::place}}, {{user}}.",
             "role": "user"},
        ]})
    async with factory() as session:
        record = await qr.execute_reply(session, uid, chat_id, reply["id"])
    assert record["status"] == "ok"
    assert record["variables"]["place"] == "the lighthouse"
    assert await history(factory, uid, chat_id) == [
        ("system", "We gather."),
        ("user", "Meet at the lighthouse, volmarr.")]


async def test_execute_partial_failure_is_recorded_never_silent(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    reply = qr.create_reply(uid, {
        "name": "Fragile",
        "steps": [
            {"text": "First lands."},
            {"text": "Boom {{nosuchmacro}} here."},
            {"text": "Third never runs."},
        ]})
    async with factory() as session:
        record = await qr.execute_reply(session, uid, chat_id, reply["id"])
    assert record["status"] == "partial"
    assert [s["status"] for s in record["steps"]] == [
        "ok", "failed", "skipped"]
    assert "MacroError" in record["steps"][1]["error"]
    # Only the first step landed; raw macro text was never posted.
    assert await history(factory, uid, chat_id) == [("user", "First lands.")]
    assert qr.list_executions(uid)[0]["status"] == "partial"


async def test_execute_first_step_failure_status_failed(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    reply = qr.create_reply(uid, {"name": "Bad", "text": "{{getvar::unset}}"})
    async with factory() as session:
        record = await qr.execute_reply(session, uid, chat_id, reply["id"])
    assert record["status"] == "failed"
    assert await history(factory, uid, chat_id) == []


async def test_execute_missing_and_scope_guards(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    other_chat = await seed_chat(factory, uid)
    ghost = str(uuid.uuid4())
    async with factory() as session:
        assert await qr.execute_reply(session, uid, ghost, ghost) is None
        assert await qr.execute_reply(session, uid, chat_id, ghost) is None
    scoped = qr.create_reply(uid, {"name": "Scoped", "text": "hi",
                                   "scope": "chat", "chat_id": chat_id})
    async with factory() as session:
        assert await qr.execute_reply(
            session, uid, other_chat, scoped["id"]) is None
        record = await qr.execute_reply(session, uid, chat_id, scoped["id"])
    assert record["status"] == "ok"


async def test_execute_disabled_reply_refuses_loudly(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    reply = qr.create_reply(uid, {"name": "Off", "text": "hi",
                                  "enabled": False})
    async with factory() as session:
        with pytest.raises(qr.QuickReplyError):
            await qr.execute_reply(session, uid, chat_id, reply["id"])
    assert await history(factory, uid, chat_id) == []


async def test_execute_is_undoable_per_appended_step(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    reply = qr.create_reply(uid, {"name": "Once", "text": "One tap."})
    async with factory() as session:
        await qr.execute_reply(session, uid, chat_id, reply["id"])
    async with factory() as session:
        entries = await undo_mod.list_journal(session, uid, chat_id)
        assert entries, "the append must be journaled (P-076)"
        undone = await undo_mod.undo_last(session, uid, chat_id)
    assert undone is not None
    assert await history(factory, uid, chat_id) == []


async def test_execute_quick_reply_sender_keeps_declared_role(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    reply = qr.create_reply(uid, {
        "name": "Narrate",
        "steps": [{"text": "The lamp is lit.", "role": "assistant"}]})
    async with factory() as session:
        record = await qr.execute_reply(session, uid, chat_id, reply["id"])
        messages = await chats_svc.get_history(session, uid, chat_id)
        view = chats_svc.message_to_dict(messages[0])
    assert record["steps"][0]["sender"] == "quick_reply"
    assert view["role"] == "assistant"
    assert view["provenance"]["origin"]["sender"] == "quick_reply"


# -- HTTP surface -------------------------------------------------------------------


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def test_http_crud_and_execute(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/quick-replies",
                          json={"name": "Hail", "text": "Hail, {{user}}!"})
    assert created.status_code == 201
    reply = created.json()
    listed = client.get("/api/v1/quick-replies")
    assert [r["id"] for r in listed.json()] == [reply["id"]]
    bad = client.post("/api/v1/quick-replies",
                      json={"name": "Hail", "text": "dup"})
    assert bad.status_code == 422
    chat = client.post("/api/v1/chats", json={"title": "T"})
    assert chat.status_code in (200, 201)
    chat_id = chat.json()["id"]
    run = client.post(f"/api/v1/quick-replies/{reply['id']}/execute",
                      json={"chat_id": chat_id})
    assert run.status_code == 200
    assert run.json()["status"] == "ok"
    history_resp = client.get(f"/api/v1/chats/{chat_id}")
    assert history_resp.status_code == 200
    executions = client.get("/api/v1/quick-replies/executions")
    assert executions.json()[0]["reply_id"] == reply["id"]
    missing = client.get(f"/api/v1/quick-replies/{uuid.uuid4()}")
    assert missing.status_code == 404
    deleted = client.delete(f"/api/v1/quick-replies/{reply['id']}")
    assert deleted.status_code == 200


# -- Neighbours -----------------------------------------------------------------------


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in MIGRATIONS


def test_current_revision_is_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
