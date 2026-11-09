"""P-177 - Workspace binding-history census (Part XI, DERIVED).

Pins: the census document (P-173 history document composed
verbatim with no chat filter and embedded whole, its counts
carried), the closed census law (no_history / no_live_chats /
all_live_chats / some_live_chats), the event axis carried from
P-173, the folder-state axis (each entry folder_state summed
under P-169 closed law, no second law), the existence axis
(live vs gone entries and distinct chats, judged live at
read), the sharing axis over ended bindings, the label axis,
live re-judgement (a folder created and a chat deleted after
one census flip the next), owner scoping, the pure-read law,
the P-175 interplay (a deleted entry drops out of the census),
the HTTP road (GET /workspaces/history-census at 200 in every
state), and the neighbours (migration head stays 0041). No
network.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.chats import service as chats_svc
from runmal.chats.greetings import GreetingChoice
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.plugins import service as plugin_service
from runmal.workspaces import bindings as ws
from runmal.workspaces import history as hist
from runmal.workspaces import history_census as hc


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


def make_store(tmp_path):
    return ws.WorkspaceStore(tmp_path / "data")


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


async def seed_chat(factory, uid, title="The Workshop"):
    async with factory() as session:
        chat = await chats_svc.create_chat(
            session, uid, title=title, character_id=None,
            greeting=GreetingChoice(mode="quiet"))
        await session.commit()
        return chat.id


async def census(factory, store, uid):
    async with factory() as session:
        return await hc.resolve_workspace_history_census(session, store, uid)


def end_binding(store, uid, chat_id, folder, label=""):
    binding = ws.register_binding(
        store, owner_id=uid, chat_id=chat_id,
        folder_path=str(folder), label=label)
    store.remove_binding(binding.id)
    return binding


# --------------------------------------------------------- empty axes


@pytest.mark.asyncio
async def test_no_history_is_the_honest_empty_census(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    doc = await census(factory, make_store(tmp_path), uid)
    assert doc["schema"] == "runmal-p177-workspace-history-census-v1"
    assert doc["census_state"] == "no_history"
    assert doc["census_state"] in hc.HISTORY_CENSUS_STATES
    assert hc.HISTORY_CENSUS_STATES == {
        "no_history", "no_live_chats", "all_live_chats",
        "some_live_chats"}
    assert doc["entry_count"] == 0
    assert doc["unbound_count"] == 0
    assert doc["chat_deleted_count"] == 0
    assert doc["chat_count"] == 0
    assert doc["live_chat_entry_count"] == 0
    assert doc["gone_chat_entry_count"] == 0
    assert doc["distinct_folder_count"] == 0
    assert doc["labelled_count"] == 0
    assert doc["history_document"]["history"] == []
    assert doc["folder_state_counts"] == {
        "missing": 0, "not_a_directory": 0, "ready": 0, "unreadable": 0}
    assert len(doc["notes"]) == 6


@pytest.mark.asyncio
async def test_live_bindings_alone_are_not_history(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(real))
    doc = await census(factory, store, uid)
    assert doc["census_state"] == "no_history"
    assert doc["entry_count"] == 0


# ------------------------------------------------------------ states


@pytest.mark.asyncio
async def test_all_live_chats_and_document_verbatim(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    end_binding(store, uid, chat_id, real, label="bench")
    async with factory() as session:
        hist_doc = await hist.resolve_workspace_history(
            session, store, uid, None)
    doc = await census(factory, store, uid)
    assert doc["history_document"] == hist_doc  # verbatim, whole
    assert doc["census_state"] == "all_live_chats"
    assert doc["entry_count"] == hist_doc["entry_count"] == 1
    assert doc["unbound_count"] == 1
    assert doc["chat_deleted_count"] == 0
    assert doc["chat_count"] == 1
    assert doc["live_chat_entry_count"] == 1
    assert doc["gone_chat_entry_count"] == 0
    assert doc["live_chat_count"] == 1
    assert doc["gone_chat_count"] == 0
    assert doc["ready_count"] == 1


@pytest.mark.asyncio
async def test_no_live_chats_ghost_entries(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    store = make_store(tmp_path)
    end_binding(store, uid, "ghost-one", tmp_path / "a")
    end_binding(store, uid, "ghost-two", tmp_path / "b")
    doc = await census(factory, store, uid)
    assert doc["census_state"] == "no_live_chats"
    assert doc["entry_count"] == 2
    assert doc["live_chat_entry_count"] == 0
    assert doc["gone_chat_entry_count"] == 2
    assert doc["gone_chat_count"] == 2
    assert doc["chat_count"] == 2


@pytest.mark.asyncio
async def test_some_live_chats_mixed(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    end_binding(store, uid, chat_id, tmp_path / "live")
    end_binding(store, uid, "ghost-chat", tmp_path / "gone")
    doc = await census(factory, store, uid)
    assert doc["census_state"] == "some_live_chats"
    assert doc["live_chat_entry_count"] == 1
    assert doc["gone_chat_entry_count"] == 1
    assert doc["live_chat_count"] == 1
    assert doc["gone_chat_count"] == 1


@pytest.mark.asyncio
async def test_chat_deleted_event_axis_carried(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(tmp_path / "bench"))
    assert store.purge_chat(chat_id) == 1
    end_binding(store, uid, chat_id, tmp_path / "other")
    doc = await census(factory, store, uid)
    assert doc["entry_count"] == 2
    assert doc["unbound_count"] == 1
    assert doc["chat_deleted_count"] == 1
    assert doc["chat_count"] == 1  # both entries, one distinct chat
    assert doc["live_chat_count"] == 1
    assert doc["live_chat_entry_count"] == 2


# ------------------------------------------------------ folder states


@pytest.mark.asyncio
async def test_folder_state_axis_under_p169_law(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    one = await seed_chat(factory, uid, "One")
    two = await seed_chat(factory, uid, "Two")
    three = await seed_chat(factory, uid, "Three")
    store = make_store(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    a_file = tmp_path / "file.txt"
    a_file.write_text("x")
    end_binding(store, uid, one, real)
    end_binding(store, uid, two, tmp_path / "ghost")
    end_binding(store, uid, three, a_file)
    doc = await census(factory, store, uid)
    assert doc["folder_state_counts"] == {
        "missing": 1, "not_a_directory": 1, "ready": 1, "unreadable": 0}
    assert doc["ready_count"] == 1
    assert doc["missing_count"] == 1
    assert doc["not_a_directory_count"] == 1
    assert doc["unreadable_count"] == 0
    assert sum(doc["folder_state_counts"].values()) == 3


# ----------------------------------------------------------- sharing


@pytest.mark.asyncio
async def test_shared_folder_across_endings(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    one = await seed_chat(factory, uid, "One")
    two = await seed_chat(factory, uid, "Two")
    three = await seed_chat(factory, uid, "Three")
    store = make_store(tmp_path)
    shared = tmp_path / "shared"
    shared.mkdir()
    solo = tmp_path / "solo"
    solo.mkdir()
    end_binding(store, uid, one, shared)
    end_binding(store, uid, two, shared)
    end_binding(store, uid, three, solo)
    doc = await census(factory, store, uid)
    assert doc["distinct_folder_count"] == 2
    assert doc["shared_folder_count"] == 1
    assert doc["entries_on_shared_folders"] == 2


@pytest.mark.asyncio
async def test_label_axis_counts_verbatim_labels(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    one = await seed_chat(factory, uid, "One")
    two = await seed_chat(factory, uid, "Two")
    three = await seed_chat(factory, uid, "Three")
    store = make_store(tmp_path)
    end_binding(store, uid, one, tmp_path / "a", label="bench")
    end_binding(store, uid, two, tmp_path / "b", label="lab")
    end_binding(store, uid, three, tmp_path / "c")
    doc = await census(factory, store, uid)
    assert doc["labelled_count"] == 2
    assert doc["unlabelled_count"] == 1


# --------------------------------------------------- live rejudgement


@pytest.mark.asyncio
async def test_live_rejudgement_folder_and_chat(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    ghost = tmp_path / "ghost"
    end_binding(store, uid, chat_id, ghost)
    doc = await census(factory, store, uid)
    assert doc["census_state"] == "all_live_chats"
    assert doc["missing_count"] == 1
    ghost.mkdir()
    doc2 = await census(factory, store, uid)
    assert doc2["ready_count"] == 1
    assert doc2["missing_count"] == 0
    async with factory() as session:
        assert await chats_svc.delete_chat(session, uid, chat_id)
        await session.commit()
    doc3 = await census(factory, store, uid)
    # delete_chat custody archives a second entry (chat_deleted)
    # for the re-bound? No live binding remained, so the one
    # history entry now judges its chat gone.
    assert doc3["census_state"] == "no_live_chats"
    assert doc3["gone_chat_entry_count"] == doc3["entry_count"]


# ----------------------------------------------------- scope / purity


@pytest.mark.asyncio
async def test_owner_scoping_foreign_history_invisible(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, "someone-else")
    other_chat = await seed_chat(factory, other, "Foreign")
    store = make_store(tmp_path)
    end_binding(store, other, other_chat, tmp_path / "real")
    doc = await census(factory, store, uid)
    assert doc["census_state"] == "no_history"
    assert doc["entry_count"] == 0
    foreign = await census(factory, store, other)
    assert foreign["entry_count"] == 1
    assert foreign["census_state"] == "all_live_chats"


@pytest.mark.asyncio
async def test_census_is_pure_read(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    folder = tmp_path / "bench"
    folder.mkdir()
    marker = folder / "keep.txt"
    marker.write_text("mine")
    store = make_store(tmp_path)
    end_binding(store, uid, chat_id, folder)
    store_bytes = store.index_path.read_bytes()
    first = await census(factory, store, uid)
    second = await census(factory, store, uid)
    assert first == second
    assert marker.read_text() == "mine"
    assert [p.name for p in folder.iterdir()] == ["keep.txt"]
    assert store.index_path.read_bytes() == store_bytes


@pytest.mark.asyncio
async def test_p175_deleted_entry_drops_out(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    end_binding(store, uid, chat_id, tmp_path / "a")
    end_binding(store, uid, chat_id, tmp_path / "b")
    before = await census(factory, store, uid)
    assert before["entry_count"] == 2  # unbind frees the chat to rebind
    entries = store.list_history_for_owner(uid)
    removed = hist.delete_workspace_history_entry(store, uid, entries[0].id)
    assert removed is not None
    after = await census(factory, store, uid)
    assert after["entry_count"] == 1
    assert after["census_state"] == "all_live_chats"


# ------------------------------------------------- pure builder unit


def test_build_history_census_sums_only_document_fields():
    doc = {
        "schema": ws.HISTORY_SCHEMA, "history": [
            {"entry": {"id": "e1", "chat_id": "c1",
                       "folder_path": "/x", "label": "a",
                       "event": "unbound"},
             "folder_state": "ready", "chat_exists": True,
             "chat_title": "One"},
            {"entry": {"id": "e2", "chat_id": "c1",
                       "folder_path": "/x", "label": "",
                       "event": "chat_deleted"},
             "folder_state": "missing", "chat_exists": False,
             "chat_title": None},
        ],
        "entry_count": 2, "unbound_count": 1,
        "chat_deleted_count": 1, "chat_count": 1,
        "chat_id": None, "notes": []}
    out = hc.build_history_census(doc)
    assert out["history_document"] is doc
    assert out["census_state"] == "some_live_chats"
    assert out["live_chat_count"] == 1
    assert out["gone_chat_count"] == 1
    assert out["shared_folder_count"] == 1
    assert out["entries_on_shared_folders"] == 2
    assert out["labelled_count"] == 1


# --------------------------------------------------------------- HTTP


def _client(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return factory, client


@pytest.mark.asyncio
async def test_http_history_census_road(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    empty = client.get("/api/v1/workspaces/history-census")
    assert empty.status_code == 200, empty.text
    assert empty.json()["census_state"] == "no_history"
    store = make_store(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    end_binding(store, uid, chat_id, folder, label="bench")
    got = client.get("/api/v1/workspaces/history-census")
    assert got.status_code == 200, got.text
    doc = got.json()
    assert doc["schema"] == "runmal-p177-workspace-history-census-v1"
    assert doc["census_state"] == "all_live_chats"
    assert doc["entry_count"] == 1
    assert doc["history_document"]["history"][0]["folder_state"] == "ready"


# ---------------------------------------------------------- neighbours


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
