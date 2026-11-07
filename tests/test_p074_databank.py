"""P-074 Data bank battery (team-03).

Pins: per-chat attached documents the model can read, scoped
(chat + global) and budgeted. Design: hidden_files/P074_DESIGN.md.

Storage rides the P-067 checkpoint pattern: self-contained
SHA-256-sealed JSON files under data_dir()/databank -- NO
migration (head stays 0038; no m0039/m0040 from this slice).
Budget honesty: one counter (runmal.tokens) over the rendered
document text; selection includes WHOLE documents within the
chat's declared budget or excludes them whole with a reason --
nothing is truncated; spend is visible in the accounting echo,
the prompt trace (discarded slots), and the P-058 governor's
"context" section. Cross-user isolation is pinned at the SERVICE
layer with two owner rows (the single-credential test client
cannot express a second owner at API level -- the P-069/P-072
evidence limitation).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import data_dir, get_or_create_credential
from runmal.chats import databank
from runmal.chats import service as svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.prompt.governor import budget_from_slots
from runmal.tokens import estimate_tokens


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _chat(client, title="Saga"):
    r = client.post("/api/v1/chats", json={"title": title})
    assert r.status_code == 201, r.text
    return r.json()


def _attach(client, chat_id, name="Field Notes", content="The ford is shallow in summer.", **kw):
    body = {"name": name, "content": content}
    body.update(kw)
    r = client.post(f"/api/v1/chats/{chat_id}/databank", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _inspect(client, chat_id):
    r = client.post("/api/v1/debug/prompt-inspect", json={"chat_id": chat_id, "messages": ["hello"]})
    assert r.status_code == 200, r.text
    return r.json()


def _events(client, chat_id):
    r = client.get(f"/api/v1/chats/{chat_id}/events")
    assert r.status_code == 200, r.text
    return r.json()


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


async def make_chat(factory, user_id, title="Saga"):
    async with factory() as session:
        chat = await svc.create_chat(session, user_id, title)
        return chat.id


# ---------------- migration discipline ----------------


def test_migration_head_stays_0039():
    assert MIGRATIONS[-1][0] == "0040"  # re-pinned at P-074 banking: 0039 is P-073 m0039_chat_metadata; P-074 took no migration
    revisions = [r for r, _d, _m in MIGRATIONS]
    # P-075 banking heal: 0040 now exists exactly once and is P-075's
    # m0040_message_provenance -- still none from P-074.
    assert revisions.count("0040") == 1
    assert MIGRATIONS[-1][2].__name__.endswith("m0040_message_provenance")


# ---------------- attach / get / list ----------------


def test_attach_get_roundtrip(app_client):
    chat = _chat(app_client)
    doc = _attach(app_client, chat["id"])
    assert doc["scope"] == "chat" and doc["chat_id"] == chat["id"]
    assert doc["content"] == "The ford is shallow in summer."
    assert doc["content_type"] == "text/plain"
    assert doc["enabled"] is True and doc["priority"] == 0
    assert doc["tokens"] == estimate_tokens("[Data bank: Field Notes]\nThe ford is shallow in summer.")
    r = app_client.get(f"/api/v1/chats/{chat['id']}/databank/{doc['id']}")
    assert r.status_code == 200, r.text
    assert r.json() == doc


def test_list_metadata_no_content_with_accounting(app_client):
    chat = _chat(app_client)
    doc = _attach(app_client, chat["id"])
    r = app_client.get(f"/api/v1/chats/{chat['id']}/databank")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["documents"]) == 1
    row = body["documents"][0]
    assert row["id"] == doc["id"] and "content" not in row
    acc = body["accounting"]
    assert acc["budget_tokens"] == databank.DEFAULT_BUDGET_TOKENS
    assert acc["spent_tokens"] == doc["tokens"]
    assert acc["remaining_tokens"] == acc["budget_tokens"] - doc["tokens"]
    assert acc["governor_section"] == "context"
    assert acc["included"][0]["id"] == doc["id"] and acc["excluded"] == []
    assert "ford" not in json.dumps(acc)


def test_attach_missing_chat_404(app_client):
    r = app_client.post("/api/v1/chats/nope/databank", json={"name": "X", "content": "y"})
    assert r.status_code == 404, r.text
    r = app_client.get("/api/v1/chats/nope/databank")
    assert r.status_code == 404, r.text


def test_validation_refusals(app_client):
    chat = _chat(app_client)
    base = f"/api/v1/chats/{chat['id']}/databank"
    for body in (
        {"name": "  ", "content": "y"},
        {"name": "X", "content": "y", "content_type": "application/pdf"},
        {"name": "X", "content": "y", "priority": 101},
        {"name": "X", "content": "y", "priority": True},
        {"name": "n" * 201, "content": "y"},
    ):
        r = app_client.post(base, json=body)
        assert r.status_code == 422, (body, r.text)


async def test_oversize_content_refused_service(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await make_chat(factory, user)
    async with factory() as session:
        with pytest.raises(ValueError):
            await databank.attach_document(session, user, "chat", chat_id, name="Big", content="x" * (databank.MAX_CONTENT_CHARS + 1))


# ---------------- update / detach ----------------


def test_update_and_disable_flow(app_client):
    chat = _chat(app_client)
    doc = _attach(app_client, chat["id"])
    url = f"/api/v1/chats/{chat['id']}/databank/{doc['id']}"
    r = app_client.put(url, json={"name": "Renamed", "enabled": False, "priority": 5})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "Renamed" and body["enabled"] is False and body["priority"] == 5
    listing = app_client.get(f"/api/v1/chats/{chat['id']}/databank").json()
    acc = listing["accounting"]
    assert acc["spent_tokens"] == 0
    assert acc["excluded"][0]["id"] == doc["id"]
    assert acc["excluded"][0]["reason"] == "disabled"
    r = app_client.put(url, json={"enabled": True})
    assert r.json()["enabled"] is True


def test_detach_flow(app_client):
    chat = _chat(app_client)
    doc = _attach(app_client, chat["id"])
    url = f"/api/v1/chats/{chat['id']}/databank/{doc['id']}"
    r = app_client.delete(url)
    assert r.status_code == 200 and r.json()["deleted"] is True
    assert app_client.get(url).status_code == 404
    assert app_client.delete(url).status_code == 404
    listing = app_client.get(f"/api/v1/chats/{chat['id']}/databank").json()
    assert listing["documents"] == []


# ---------------- budget: the honest core ----------------


def test_budget_excludes_whole_documents_never_truncates(app_client):
    chat = _chat(app_client)
    small = _attach(app_client, chat["id"], name="Small", content="tiny note")
    big_content = "word " * 400
    big = _attach(app_client, chat["id"], name="Big", content=big_content)
    budget = small["tokens"] + 10
    assert big["tokens"] > budget
    r = app_client.put(f"/api/v1/chats/{chat['id']}/databank/budget", json={"budget_tokens": budget})
    assert r.status_code == 200 and r.json()["budget_tokens"] == budget
    result = _inspect(app_client, chat["id"])
    echo = result["databank"]
    assert echo["budget_tokens"] == budget
    assert [row["id"] for row in echo["included"]] == [small["id"]]
    assert echo["excluded"][0]["id"] == big["id"]
    assert echo["excluded"][0]["reason"] == "over_databank_budget"
    assert echo["spent_tokens"] == small["tokens"]
    slots = {row["slot_id"]: row for row in result["slots"]}
    assert slots[f"databank/{small['id']}"]["status"] == "included"
    assert slots[f"databank/{small['id']}"]["tokens"] == small["tokens"]
    discarded = slots[f"databank/{big['id']}"]
    assert discarded["status"] == "discarded" and discarded["reason"] == "databank_over_budget"
    assert discarded["tokens"] == big["tokens"]


def test_priority_wins_the_budget(app_client):
    chat = _chat(app_client)
    first = _attach(app_client, chat["id"], name="First", content="alpha " * 30, priority=0)
    second = _attach(app_client, chat["id"], name="Second", content="beta " * 30, priority=9)
    budget = max(first["tokens"], second["tokens"])
    app_client.put(f"/api/v1/chats/{chat['id']}/databank/budget", json={"budget_tokens": budget})
    result = _inspect(app_client, chat["id"])
    assert [row["id"] for row in result["databank"]["included"]] == [second["id"]]


def test_budget_zero_excludes_everything(app_client):
    chat = _chat(app_client)
    doc = _attach(app_client, chat["id"])
    app_client.put(f"/api/v1/chats/{chat['id']}/databank/budget", json={"budget_tokens": 0})
    result = _inspect(app_client, chat["id"])
    assert result["databank"]["included"] == []
    assert result["databank"]["excluded"][0]["id"] == doc["id"]


def test_budget_validation(app_client):
    chat = _chat(app_client)
    url = f"/api/v1/chats/{chat['id']}/databank/budget"
    assert app_client.get(url).json()["budget_tokens"] == databank.DEFAULT_BUDGET_TOKENS
    for bad in (-1, databank.MAX_BUDGET_TOKENS + 1, True):
        r = app_client.put(url, json={"budget_tokens": bad})
        assert r.status_code == 422, (bad, r.text)


def test_governor_counts_databank_under_context():
    docs = [
        {"id": "d1", "scope": "chat", "chat_id": "c", "name": "A", "content_type": "text/plain", "content": "hello world", "enabled": True, "priority": 0, "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"},
    ]
    selection = databank.select_documents(docs, 2000)
    slots = databank.slots_for_selection(selection)
    assert len(slots) == 1 and slots[0].kind == "databank"
    budget = budget_from_slots(slots, input_budget=4096)
    assert budget.sections["context"].tokens == selection.spent_tokens
    assert budget.sections["context"].slot_ids == ("databank/d1",)
    assert budget.total_tokens == selection.spent_tokens


def test_exact_counter_is_labelled_exact():
    docs = [
        {"id": "d1", "scope": "chat", "chat_id": "c", "name": "A", "content_type": "text/plain", "content": "one two three", "enabled": True, "priority": 0, "created_at": "2026-01-01T00:00:00+00:00", "updated_at": "2026-01-01T00:00:00+00:00"},
    ]
    words = lambda text: len(text.split())
    selection = databank.select_documents(docs, 2000, counter=words)
    # rendered: "[Data bank: A]\none two three" -> 6 words
    assert selection.spent_tokens == 6
    acc = databank.accounting_to_dict(selection)
    assert acc["count_quality"] == "exact"


def test_inspect_without_chat_has_no_databank(app_client):
    r = app_client.post("/api/v1/debug/prompt-inspect", json={"messages": ["hello"]})
    assert r.status_code == 200, r.text
    assert r.json()["databank"] is None


# ---------------- scope: global + per-chat isolation ----------------


def test_global_document_read_by_every_chat(app_client):
    chat_a = _chat(app_client, "A")
    chat_b = _chat(app_client, "B")
    r = app_client.post("/api/v1/databank/global", json={"name": "World Facts", "content": "The sea is wide."})
    assert r.status_code == 201, r.text
    gdoc = r.json()
    assert gdoc["scope"] == "global" and gdoc["chat_id"] is None
    own = _attach(app_client, chat_a["id"], name="A Only", content="secret to A")
    for chat in (chat_a, chat_b):
        result = _inspect(app_client, chat["id"])
        included_ids = [row["id"] for row in result["databank"]["included"]]
        assert gdoc["id"] in included_ids
    result_b = _inspect(app_client, chat_b["id"])
    assert own["id"] not in [row["id"] for row in result_b["databank"]["included"]]
    result_a = _inspect(app_client, chat_a["id"])
    assert own["id"] in [row["id"] for row in result_a["databank"]["included"]]


def test_global_crud(app_client):
    r = app_client.post("/api/v1/databank/global", json={"name": "G", "content": "g"})
    doc = r.json()
    listing = app_client.get("/api/v1/databank/global").json()
    assert [d["id"] for d in listing["documents"]] == [doc["id"]]
    r = app_client.put(f"/api/v1/databank/global/{doc['id']}", json={"enabled": False})
    assert r.json()["enabled"] is False
    r = app_client.delete(f"/api/v1/databank/global/{doc['id']}")
    assert r.json()["deleted"] is True
    assert app_client.get(f"/api/v1/databank/global/{doc['id']}").status_code == 404


async def test_cross_owner_isolation_service(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    factory = make_factory(tmp_path)
    alice = await make_user(factory, "alice")
    bob = await make_user(factory, "bob")
    chat_a = await make_chat(factory, alice)
    chat_b = await make_chat(factory, bob)
    async with factory() as session:
        doc = await databank.attach_document(session, alice, "chat", chat_a, name="A doc", content="alice words")
        glob = await databank.attach_document(session, alice, "global", None, name="A global", content="alice global")
        # Bob sees nothing of Alice's chat bank.
        assert await databank.list_documents(session, bob, "chat", chat_a) is None
        assert await databank.get_document(session, bob, "chat", chat_a, doc["id"]) is None
        assert await databank.attach_document(session, bob, "chat", chat_a, name="X", content="y") is None
        assert await databank.detach_document(session, bob, "chat", chat_a, doc["id"]) is None
        # Bob's own prompt selection holds neither of Alice's docs.
        selection = await databank.load_prompt_selection(session, bob, chat_b)
        assert selection is not None and selection.included == ()
        # Alice's selection holds both.
        selection_a = await databank.load_prompt_selection(session, alice, chat_a)
        assert {d["id"] for d in selection_a.included} == {doc["id"], glob["id"]}


# ---------------- integrity: tamper, traversal, corrupt ----------------


def _bank_dir(tmp_path, user_id, scope_key):
    return Path(tmp_path) / "databank" / user_id / scope_key


async def test_tampered_content_raises_service(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await make_chat(factory, user)
    async with factory() as session:
        doc = await databank.attach_document(session, user, "chat", chat_id, name="Notes", content="original")
        path = _bank_dir(tmp_path, user, chat_id) / f"{doc['id']}.json"
        raw = json.loads(path.read_text())
        raw["document"]["content"] = "forged"
        path.write_text(json.dumps(raw))
        with pytest.raises(databank.DataBankError):
            await databank.get_document(session, user, "chat", chat_id, doc["id"])
        with pytest.raises(databank.DataBankError):
            await databank.list_documents(session, user, "chat", chat_id)


def test_tampered_file_is_422_at_api(app_client, tmp_path):
    chat = _chat(app_client)
    doc = _attach(app_client, chat["id"])
    owner_dir = Path(tmp_path) / "databank"
    files = list(owner_dir.rglob(f"{doc['id']}.json"))
    assert len(files) == 1
    raw = json.loads(files[0].read_text())
    raw["checksum"] = "0" * 64
    files[0].write_text(json.dumps(raw))
    r = app_client.get(f"/api/v1/chats/{chat['id']}/databank/{doc['id']}")
    assert r.status_code == 422, r.text


async def test_traversal_ids_refused_service(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await make_chat(factory, user)
    async with factory() as session:
        for bad in ("../secret", "a/b", "..", "_settings", ""):
            with pytest.raises(ValueError):
                await databank.get_document(session, user, "chat", chat_id, bad)


def test_malformed_id_422_at_api(app_client):
    chat = _chat(app_client)
    r = app_client.get(f"/api/v1/chats/{chat['id']}/databank/_settings")
    assert r.status_code == 422, r.text


async def test_settings_tamper_raises_service(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await make_chat(factory, user)
    async with factory() as session:
        await databank.set_budget(session, user, chat_id, 500)
        path = _bank_dir(tmp_path, user, chat_id) / "_settings.json"
        raw = json.loads(path.read_text())
        raw["budget_tokens"] = 99999
        path.write_text(json.dumps(raw))
        with pytest.raises(databank.DataBankError):
            await databank.get_budget(session, user, chat_id)


async def test_scope_cap_service(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(databank, "MAX_DOCS_PER_SCOPE", 2)
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await make_chat(factory, user)
    async with factory() as session:
        await databank.attach_document(session, user, "chat", chat_id, name="One", content="1")
        await databank.attach_document(session, user, "chat", chat_id, name="Two", content="2")
        with pytest.raises(ValueError):
            await databank.attach_document(session, user, "chat", chat_id, name="Three", content="3")


# ---------------- events + chat deletion ----------------


def test_events_carry_metadata_only(app_client):
    chat = _chat(app_client)
    secret = "CONTENT-THAT-MUST-NOT-LEAK-INTO-EVENTS"
    doc = _attach(app_client, chat["id"], content=secret)
    app_client.put(f"/api/v1/chats/{chat['id']}/databank/{doc['id']}", json={"name": "Renamed"})
    app_client.put(f"/api/v1/chats/{chat['id']}/databank/budget", json={"budget_tokens": 1234})
    app_client.delete(f"/api/v1/chats/{chat['id']}/databank/{doc['id']}")
    events = _events(app_client, chat["id"])
    kinds = [e["kind"] for e in events]
    for kind in ("databank.attached", "databank.updated", "databank.budget_changed", "databank.detached"):
        assert kind in kinds, kinds
    assert secret not in json.dumps(events)


async def test_chat_deletion_removes_chat_bank_keeps_global(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await make_chat(factory, user)
    async with factory() as session:
        await databank.attach_document(session, user, "chat", chat_id, name="Chat doc", content="c")
        glob = await databank.attach_document(session, user, "global", None, name="Global doc", content="g")
        assert _bank_dir(tmp_path, user, chat_id).is_dir()
        assert await svc.delete_chat(session, user, chat_id) is True
    assert not _bank_dir(tmp_path, user, chat_id).exists()
    global_files = list(_bank_dir(tmp_path, user, "_global").glob("*.json"))
    assert [p.stem for p in global_files] == [glob["id"]]
