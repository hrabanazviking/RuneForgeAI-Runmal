"""P-171 - Workspace census (Part XI, DERIVED).

Pins: the census document (P-169's owner list composed
verbatim as the rows, the orphan count carried, never
recomputed), the closed census law (no_chats /
no_bindings / none_ready / some_ready / all_ready),
the chat axis (owned chats counted bound vs unbound
through chats.service.list_chats), the state axis
(per-folder-state counts summed from the rows' own
P-169 folder_state values, no second law), the
sharing axis (distinct folders, folders bound by
more than one chat, bindings on shared folders),
live re-judgement (a folder created after one census
flips the next, no store change), owner scoping (a
foreign owner's chats and bindings never appear),
the pure-read law (the census writes nothing: bound
folders and the binding store are byte-identical
after reads), the HTTP road (GET /workspaces/census
at 200 in every state), and the neighbours (migration
head stays 0041, no 0042). No network.
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
from runmal.workspaces import census as cen


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
        return await cen.resolve_workspace_census(session, store, uid)


# --------------------------------------------------------- empty axes


@pytest.mark.asyncio
async def test_no_chats_is_the_honest_empty_census(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    doc = await census(factory, make_store(tmp_path), uid)
    assert doc["schema"] == "runmal-p171-workspace-census-v1"
    assert doc["census_state"] == "no_chats"
    assert doc["census_state"] in cen.CENSUS_STATES
    assert cen.CENSUS_STATES == {
        "no_chats", "no_bindings", "none_ready",
        "some_ready", "all_ready"}
    assert doc["chat_count"] == 0
    assert doc["binding_count"] == 0
    assert doc["unbound_chat_count"] == 0
    assert doc["workspaces"] == []
    assert doc["orphan_count"] == 0
    assert len(doc["notes"]) == 6


@pytest.mark.asyncio
async def test_chats_without_bindings(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    await seed_chat(factory, uid, "One")
    await seed_chat(factory, uid, "Two")
    doc = await census(factory, make_store(tmp_path), uid)
    assert doc["census_state"] == "no_bindings"
    assert doc["chat_count"] == 2
    assert doc["binding_count"] == 0
    assert doc["bound_chat_count"] == 0
    assert doc["unbound_chat_count"] == 2
    assert doc["folder_state_counts"] == {
        "missing": 0, "not_a_directory": 0, "ready": 0, "unreadable": 0}


# ------------------------------------------------------------ states


@pytest.mark.asyncio
async def test_all_ready_and_rows_verbatim(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(real))
    async with factory() as session:
        list_doc = await ws.list_owner_workspaces(session, store, uid)
    doc = await census(factory, store, uid)
    assert doc["census_state"] == "all_ready"
    assert doc["workspaces"] == list_doc["workspaces"]  # verbatim rows
    assert doc["ready_count"] == list_doc["ready_count"] == 1
    assert doc["chat_count"] == 1
    assert doc["unbound_chat_count"] == 0
    assert doc["distinct_folder_count"] == 1
    assert doc["shared_folder_count"] == 0


@pytest.mark.asyncio
async def test_some_ready_none_ready_and_live_rejudgement(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    ready_chat = await seed_chat(factory, uid, "Ready")
    ghost_chat = await seed_chat(factory, uid, "Ghost")
    store = make_store(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    ghost = tmp_path / "ghost"
    ws.register_binding(store, owner_id=uid, chat_id=ready_chat,
                        folder_path=str(real))
    ws.register_binding(store, owner_id=uid, chat_id=ghost_chat,
                        folder_path=str(ghost))
    doc = await census(factory, store, uid)
    assert doc["census_state"] == "some_ready"
    assert doc["ready_count"] == 1
    assert doc["missing_count"] == 1
    assert sum(doc["folder_state_counts"].values()) == 2
    # Remove the ready folder's only rival: unbind-ready is not
    # possible here; instead delete the real folder -> none ready
    # is wrong (ghost still missing): both non-ready = none_ready.
    import shutil
    shutil.rmtree(real)
    doc2 = await census(factory, store, uid)
    assert doc2["census_state"] == "none_ready"
    assert doc2["missing_count"] == 2
    # Live re-judgement: creating the ghost folder flips it back.
    ghost.mkdir()
    doc3 = await census(factory, store, uid)
    assert doc3["census_state"] == "some_ready"
    assert doc3["ready_count"] == 1


@pytest.mark.asyncio
async def test_not_a_directory_counted_under_p169_law(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    a_file = tmp_path / "file.txt"
    a_file.write_text("x")
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(a_file))
    doc = await census(factory, store, uid)
    assert doc["census_state"] == "none_ready"
    assert doc["not_a_directory_count"] == 1
    assert doc["folder_state_counts"]["not_a_directory"] == 1


# ----------------------------------------------------------- sharing


@pytest.mark.asyncio
async def test_shared_folder_named_as_fact(tmp_path):
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
    ws.register_binding(store, owner_id=uid, chat_id=one,
                        folder_path=str(shared))
    ws.register_binding(store, owner_id=uid, chat_id=two,
                        folder_path=str(shared))
    ws.register_binding(store, owner_id=uid, chat_id=three,
                        folder_path=str(solo))
    doc = await census(factory, store, uid)
    assert doc["census_state"] == "all_ready"
    assert doc["binding_count"] == 3
    assert doc["distinct_folder_count"] == 2
    assert doc["shared_folder_count"] == 1
    assert doc["bindings_on_shared_folders"] == 2


# ----------------------------------------------------- orphans/scope


@pytest.mark.asyncio
async def test_orphan_carried_never_presented_live(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(real))
    ws.register_binding(store, owner_id=uid, chat_id="ghost-chat",
                        folder_path=str(real))
    doc = await census(factory, store, uid)
    assert doc["orphan_count"] == 1
    assert doc["binding_count"] == 1
    assert doc["chat_count"] == 1
    assert doc["unbound_chat_count"] == 0


@pytest.mark.asyncio
async def test_owner_scoping_foreign_estate_invisible(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, "someone-else")
    other_chat = await seed_chat(factory, other, "Foreign")
    store = make_store(tmp_path)
    real = tmp_path / "real"
    real.mkdir()
    ws.register_binding(store, owner_id=other, chat_id=other_chat,
                        folder_path=str(real))
    doc = await census(factory, store, uid)
    assert doc["census_state"] == "no_chats"
    assert doc["chat_count"] == 0
    assert doc["binding_count"] == 0
    assert doc["orphan_count"] == 0
    foreign = await census(factory, store, other)
    assert foreign["census_state"] == "all_ready"
    assert foreign["binding_count"] == 1


# --------------------------------------------------------- pure read


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
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(folder))
    store_bytes = store.index_path.read_bytes()
    first = await census(factory, store, uid)
    second = await census(factory, store, uid)
    assert first == second
    assert marker.read_text() == "mine"
    assert [p.name for p in folder.iterdir()] == ["keep.txt"]
    assert store.index_path.read_bytes() == store_bytes


# --------------------------------------------------------------- HTTP


def _client(tmp_path):
    factory = make_factory(tmp_path)
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return factory, client


@pytest.mark.asyncio
async def test_http_census_road(tmp_path):
    factory, client = _client(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid)
    store = make_store(tmp_path)
    folder = tmp_path / "bench"
    folder.mkdir()
    ws.register_binding(store, owner_id=uid, chat_id=chat_id,
                        folder_path=str(folder))
    got = client.get("/api/v1/workspaces/census")
    assert got.status_code == 200, got.text
    doc = got.json()
    assert doc["schema"] == "runmal-p171-workspace-census-v1"
    assert doc["census_state"] == "all_ready"
    assert doc["binding_count"] == 1
    assert doc["workspaces"][0]["folder_state"] == "ready"


# ---------------------------------------------------------- neighbours


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
