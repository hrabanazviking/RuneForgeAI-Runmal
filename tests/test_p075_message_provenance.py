"""P-075 acceptance: message-level provenance — which model/
preset/lore produced each message, recorded.

Contract under test:
- Migration PROVISIONAL 0040: messages.provenance_json, one
  JSON production document per message, one record per swipe.
- Records state only what the producing road knew at
  production time. Gaps are explicit statuses (unknown /
  not_run / not_applicable / not_recorded), never invented.
- Live generation does not run lore on the bridge/continue
  roads (recorded not_run); group deepening does run lore and
  records the entries it actually included.
- Builders strict, readers tolerant: legacy '{}' and corrupt
  rows read as explicit not_recorded documents.
- The public API accepts no caller-supplied provenance.
Fixtures mirror test_p073_chat_metadata.py / p069 / p070.
"""

import asyncio
import copy
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends.fake import FakeChatBackend
from runmal.chats import provenance as prov
from runmal.chats import service as svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import Message, User

FIXTURES = Path(__file__).parent / "fixtures" / "cards"
V2_CARD = json.loads((FIXTURES / "v2.json").read_text())
STUB = "Rúnmál hears you. This is a stub."


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0040"  # P-075 PROVISIONAL migration
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    client = TestClient(create_app(factory))
    client.factory = factory  # same DB, for service-layer seeding
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_factory(tmp_path):
    db_path = tmp_path / "svc.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


def run(coro):
    return asyncio.run(coro)


def make_character(client, name):
    card = copy.deepcopy(V2_CARD)
    card["name"] = name
    created = client.post("/api/v1/characters", json={"card": card})
    assert created.status_code == 201, created.text
    return created.json()["id"]


def make_chat(client, character_id=None, title="Saga"):
    body = {"title": title}
    if character_id:
        body["character_id"] = character_id
    created = client.post("/api/v1/chats", json=body)
    assert created.status_code == 201, created.text
    return created.json()["id"]


def post_message(client, chat_id, role, content, **extra):
    body = {"role": role, "content": content}
    body.update(extra)
    resp = client.post(f"/api/v1/chats/{chat_id}/messages", json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# -- Migration -------------------------------------------------------------


def test_migration_0040_shape(tmp_path):
    assert MIGRATIONS[-1][0] == "0040"
    assert "PROVISIONAL" in MIGRATIONS[-1][1]
    db_path = tmp_path / "mig.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0040"
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
        assert "provenance_json" in cols
    finally:
        conn.close()


# -- Pure builders: strict ---------------------------------------------------


def test_builders_reject_records_that_would_lie():
    with pytest.raises(ValueError):
        prov.build_record(origin_kind="telepathy")
    with pytest.raises(ValueError):
        prov.model_section(status="recorded")  # no facts
    with pytest.raises(ValueError):
        prov.model_section(status="unknown", backend_key="fake")
    with pytest.raises(ValueError):
        prov.preset_section(status="recorded")  # no preset id
    with pytest.raises(ValueError):
        prov.lore_section(status="included")  # no entries
    with pytest.raises(ValueError):
        prov.lore_section(status="not_run", entries=[{"entry_id": "e1"}])
    with pytest.raises(ValueError):
        prov.lore_section(entries=[{"entry_id": "e1", "content": "x"}])
    with pytest.raises(ValueError):
        prov.lore_section(entries=[{"entry_id": "e1", "roll": {"seed": [1]}}])
    with pytest.raises(ValueError):
        prov.build_record(origin_kind="manual", origin={"nested": {"a": 1}})


def test_record_fixed_point_through_dump_and_parse():
    record = prov.build_record(
        origin_kind="generated",
        model=prov.model_section(backend_key="fake", model_id="fake-1"),
        preset=prov.preset_section(preset_id="p1", name="Warm",
                                    params={"temperature": 0.7}),
        lore=prov.lore_section(status="not_run", reason="no lore road"),
        generation={"fingerprint": "abc", "mode": "next"},
    )
    doc = prov.build_document(record)
    parsed = prov.parse_document(prov.dump_document(doc))
    assert parsed["recorded"] is True
    assert parsed["swipes"]["0"] == record


def test_lore_from_report_and_inspection():
    empty = prov.lore_from_report([])
    assert empty["status"] == "ran_none_included" and empty["entries"] == []
    report = [{"scope": "character", "lorebook_id": "b1", "entry_id": "e1"}]
    filled = prov.lore_from_report(report)
    assert filled["status"] == "included"
    assert filled["entries"][0]["entry_id"] == "e1"
    assert filled["entries"][0]["roll"] is None  # report carries no roll
    payload = {"lorebook_inspections": [{
        "lorebook_id": "b9",
        "entries": [
            {"entry_id": "e9", "status": "included", "scope": "global",
             "via": "constant",
             "probability": {"roll": {"entry_id": "e9", "roll": 0.5,
                                       "passed": True, "seed": 7,
                                       "seeded": True}}},
            {"entry_id": "e8", "status": "not_triggered"},
        ]}]}
    insp = prov.lore_from_inspection(payload)
    assert insp["status"] == "included"
    assert [e["entry_id"] for e in insp["entries"]] == ["e9"]
    assert insp["entries"][0]["roll"]["seed"] == 7


def test_readers_are_tolerant_and_gaps_are_explicit():
    for raw in (None, "", "{}", "not json", "[]", '{"schema": "other"}'):
        view = prov.active_view(raw, 0)
        assert view["recorded"] is False
        assert view["provenance_status"] == "not_recorded"
        assert view["origin"]["kind"] == "unknown"
        assert view["model"]["status"] == "unknown"
        assert view["preset"]["status"] == "unknown"
        assert view["lore"]["status"] == "unknown"
    doc = prov.parse_document('{"schema": "runmal-p075-message-provenance-v1", ')
    assert doc["recorded"] is False


def test_summarise_counts_statuses_only():
    views = [
        prov.active_view(prov.build_document(prov.build_record(
            origin_kind="manual",
            model=prov.model_section(status="not_applicable"))), 0),
        prov.active_view(None, 0),
        prov.active_view(prov.build_document(prov.build_record(
            origin_kind="group_generated",
            lore=prov.lore_from_report(
                [{"scope": "chat", "lorebook_id": "b", "entry_id": "e"}]))), 0),
    ]
    summary = prov.summarise_provenance(views)
    assert summary["total"] == 3 and summary["recorded"] == 2
    assert summary["not_recorded"] == 1
    assert summary["by_origin"] == {
        "manual": 1, "unknown": 1, "group_generated": 1}
    assert summary["messages_with_unknown_model"] == 2
    assert summary["with_lore_included"] == 1


def test_backend_model_fields_uses_the_backend_object():
    assert prov.backend_model_fields(FakeChatBackend()) == ("fake", "fake-1")
    assert prov.backend_model_fields(None) == (None, None)
    assert prov.backend_model_fields(object()) == (None, None)


# -- API: bare appends --------------------------------------------------------


def test_manual_appends_record_honest_gaps(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    user_msg = post_message(client, chat_id, "user", "Hello there.")
    p = user_msg["provenance"]
    assert p["recorded"] is True and p["provenance_status"] == "recorded"
    assert p["origin"]["kind"] == "manual"
    assert p["model"]["status"] == "not_applicable"
    assert p["preset"]["status"] == "not_applicable"  # no preset applied
    assert p["lore"]["status"] == "not_applicable"
    asst = post_message(client, chat_id, "assistant", "A pasted reply.")
    assert asst["provenance"]["model"]["status"] == "unknown"
    assert asst["provenance"]["model"]["model_id"] is None


def test_api_cannot_inject_provenance(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    msg = post_message(
        client, chat_id, "assistant", "Trust me, a model wrote this.",
        provenance={"origin": {"kind": "generated"},
                    "model": {"status": "recorded", "model_id": "gpt-x"}})
    assert msg["provenance"]["origin"]["kind"] == "manual"
    assert msg["provenance"]["model"]["model_id"] is None


def test_preset_and_profile_snapshot_survive_later_changes(
        tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    factory = client.factory

    async def seed():
        async with factory() as session:
            from runmal.db.owners import get_or_create_owner
            user = (await get_or_create_owner(session)).id
        async with factory() as session:
            from runmal.presets import service as presets
            from runmal.backends import profiles as bp
            preset = await presets.create_preset(
                session, user, "Warm", params={"temperature": 0.7})
            profile = await bp.create_profile(
                session, user, name="Local", chat_backend="fake",
                chat_model="fake-1")
            return user, preset.id, profile.id

    user, preset_id, profile_id = run(seed())
    chat_id = make_chat(client)
    assert client.post(f"/api/v1/chats/{chat_id}/preset",
                       json={"preset_id": preset_id}).status_code == 200
    assert client.post(f"/api/v1/chats/{chat_id}/backend-profile",
                       json={"profile_id": profile_id}).status_code == 200
    msg = post_message(client, chat_id, "user", "With config.")
    p = msg["provenance"]
    assert p["preset"]["status"] == "recorded"
    assert p["preset"]["preset_id"] == preset_id
    assert p["preset"]["name"] == "Warm"
    assert p["preset"]["params"] == {"temperature": 0.7}
    assert p["model"]["backend_profile_id"] == profile_id
    assert p["model"]["backend_profile_name"] == "Local"
    # Clearing the chat config afterwards must not rewrite the record.
    assert client.post(f"/api/v1/chats/{chat_id}/preset",
                       json={"preset_id": None}).status_code == 200
    again = client.get(f"/api/v1/chats/{chat_id}/messages").json()
    kept = [m for m in again if m["id"] == msg["id"]][0]
    assert kept["provenance"]["preset"]["preset_id"] == preset_id


# -- Read endpoints + deck roads (finisher additions)


def test_provenance_endpoints_full_document_and_summary(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat_id = make_chat(client)
    msg = post_message(client, chat_id, "user", "Endpoint check.")
    post_message(client, chat_id, "assistant", "Second line.")
    full = client.get(
        f"/api/v1/chats/{chat_id}/messages/{msg['id']}/provenance")
    assert full.status_code == 200, full.text
    doc = full.json()
    assert doc["recorded"] is True and doc["message_id"] == msg["id"]
    assert doc["swipes"]["0"]["origin"]["kind"] == "manual"
    listing = client.get(f"/api/v1/chats/{chat_id}/provenance")
    assert listing.status_code == 200, listing.text
    body = listing.json()
    assert body["summary"]["total"] == 2
    assert body["summary"]["recorded"] == 2
    assert body["summary"]["by_origin"] == {"manual": 2}
    missing = client.get(
        f"/api/v1/chats/{chat_id}/messages/nope/provenance")
    assert missing.status_code == 404
    assert client.get("/api/v1/chats/nope/provenance").status_code == 404


def test_swipe_edit_delete_records_follow_the_deck(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    factory = client.factory
    chat_id = make_chat(client)
    msg = post_message(client, chat_id, "assistant", "First take.")

    async def scenario():
        from runmal.db.owners import get_or_create_owner
        async with factory() as session:
            user = (await get_or_create_owner(session)).id
        async with factory() as session:
            await svc.add_swipe(session, user, chat_id, msg["id"], "Alt take.")
            await session.commit()
        async with factory() as session:
            m = await svc.get_history(session, user, chat_id)
            doc = prov.parse_provenance(m[0])
            assert sorted(doc["swipes"]) == ["0", "1"]
            assert doc["swipes"]["1"]["origin"]["kind"] == "swipe_manual"
            assert doc["swipes"]["1"]["model"]["status"] == "not_applicable"
        async with factory() as session:
            await svc.select_swipe(session, user, chat_id, msg["id"], index=0)
            await session.commit()
        async with factory() as session:
            await svc.edit_message(session, user, chat_id, msg["id"], "Edited.")
            await session.commit()
        async with factory() as session:
            m = await svc.get_history(session, user, chat_id)
            active = prov.active_record(m[0])
            assert [a["kind"] for a in active["amendments"]] == ["edit"]
            assert active["origin"]["kind"] == "manual"  # producer unchanged
        async with factory() as session:
            await svc.delete_swipe(session, user, chat_id, msg["id"], 0)
            await session.commit()
        async with factory() as session:
            m = await svc.get_history(session, user, chat_id)
            doc = prov.parse_provenance(m[0])
            assert sorted(doc["swipes"]) == ["0"]  # renumbered onto the deck
            assert doc["swipes"]["0"]["origin"]["kind"] == "swipe_manual"

    run(scenario())


def test_copy_to_branch_nests_the_source_record(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    factory = client.factory
    chat_id = make_chat(client)
    msg = post_message(client, chat_id, "user", "Copy me.")

    async def scenario():
        from runmal.db.owners import get_or_create_owner
        async with factory() as session:
            user = (await get_or_create_owner(session)).id
        async with factory() as session:
            result = await svc.copy_message_to_branch(
                session, user, chat_id, msg["id"])
            await session.commit()
            copied = result["copied_message"]
            session.expunge(copied)
            return copied

    copied = run(scenario())
    assert copied.content == "Copy me."
    record = prov.active_record(copied)
    assert record["origin"]["kind"] == "copied"
    assert record["origin"]["source_message_id"] == msg["id"]
    assert record["origin"]["source_chat_id"] == chat_id
    nested = record["origin"]["source_provenance"]
    assert nested["origin"]["kind"] == "manual"
