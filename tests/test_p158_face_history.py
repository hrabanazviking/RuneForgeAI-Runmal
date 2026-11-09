"""P-158 - Face selection history (Part X, DERIVED).

Pins: the history document resolving P-092's kept
selection history for one chat against today's binding
truth - P-155's presentation document composed verbatim
(presentation_state / current ride whole), every kept
event verbatim in substance with its provenance, newest
first, each classified under the closed entry-state law
(still_ready / declared_unbound / no_longer_declared /
cleared) with the still-declared entry's P-155 descriptor
named as data, the kept window named honestly
(kept_limit == P-092's MAX_HISTORY_KEPT, at_kept_limit,
never a claim of a complete record), the standing
honesty notes, owner scoping (unknown/foreign chat ->
None / 404), the pure-read law (no selection written,
no clearing recorded, the P-092 store byte-identical
after a resolve), and the neighbours (migration head
stays 0041, no 0042). No network.
"""

from __future__ import annotations

import struct
import uuid
import zlib

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.assets import service as assets_svc
from runmal.auth import get_or_create_credential
from runmal.characters import service as characters_svc
from runmal.chats import service as chats_svc
from runmal.chats.greetings import GreetingChoice
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.faces import history as hist
from runmal.plugins import expressions as ex
from runmal.plugins import service as plugin_service
from runmal.plugins.image_generation import render_deterministic_png

PNG_BYTES = render_deterministic_png("sprite seed", "", 1, 32)


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


async def seed_character(factory, uid, name="Asta"):
    async with factory() as session:
        character = await characters_svc.create_character(
            session, uid, card_dict(name))
        await session.commit()
        return character.id


async def seed_chat(factory, uid, character_id=None):
    async with factory() as session:
        chat = await chats_svc.create_chat(
            session, uid, title="The Lighthouse",
            character_id=character_id,
            greeting=GreetingChoice(mode="quiet"))
        await session.commit()
        return chat.id


async def _add_asset(factory, uid, cid, *, kind, name):
    async with factory() as session:
        asset = await assets_svc.add_asset(
            session, uid, cid, kind=kind, name=name,
            filename=f"{name.replace(' ', '_')}.png", data=PNG_BYTES)
        return asset.id


async def _world(factory, uid):
    """Character + bound chat + set: neutral (no asset),
    amused (bound sprite), wrong (wrong-kind asset);
    default is the bound one."""
    cid = await seed_character(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    bound_id = await _add_asset(factory, uid, cid, kind="expression",
                                name="amused")
    bg_id = await _add_asset(factory, uid, cid, kind="background",
                             name="stairs")
    ex.create_set(uid, {
        "character_id": cid,
        "entries": [
            {"name": "neutral", "label": "Neutral"},
            {"name": "amused", "label": "Amused", "asset_id": bound_id},
            {"name": "wrong", "label": "Wrong", "asset_id": bg_id},
        ],
        "default": "amused",
    })
    return cid, chat_id, bound_id, bg_id


# -- Scoping / empty documents -------------------------------------------------


async def test_missing_and_foreign_chat_resolve_none(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, name="other")
    _cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        assert await hist.resolve_face_history(
            session, uid, str(uuid.uuid4())) is None
        assert await hist.resolve_face_history(
            session, other, chat_id) is None


async def test_no_character_chat_has_empty_history(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid, None)
    async with factory() as session:
        doc = await hist.resolve_face_history(session, uid, chat_id)
    assert doc["schema"] == hist.HISTORY_SCHEMA
    assert doc["character_id"] is None
    assert doc["presentation_state"] == "no_character"
    assert doc["current"] is None
    assert doc["events"] == []
    assert doc["event_count"] == 0
    assert doc["selection_count"] == 0
    assert doc["cleared_count"] == 0
    assert doc["still_ready_count"] == 0
    assert doc["kept_limit"] == ex.MAX_HISTORY_KEPT == 100
    assert doc["at_kept_limit"] is False


async def test_no_events_yet_is_an_empty_document(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        doc = await hist.resolve_face_history(session, uid, chat_id)
    assert doc["presentation_state"] == "no_selection"
    assert doc["events"] == [] and doc["event_count"] == 0


async def test_history_is_scoped_to_the_one_chat(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, chat_id, _b, _g = await _world(factory, uid)
    other_chat = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
        doc = await hist.resolve_face_history(session, uid, other_chat)
    assert doc["events"] == [] and doc["event_count"] == 0


# -- Events: order, provenance, classification -----------------------------------


async def test_events_newest_first_with_provenance(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused",
                                 reason="a joke landed")
        await ex.select_for_chat(session, uid, chat_id, "neutral",
                                 reason="the news turned grave")
        doc = await hist.resolve_face_history(session, uid, chat_id)
    assert doc["event_count"] == 2
    assert doc["selection_count"] == 2 and doc["cleared_count"] == 0
    newest, oldest = doc["events"]
    assert newest["expression"] == "neutral"
    assert newest["provenance"]["reason"] == "the news turned grave"
    assert newest["provenance"]["previous_expression"] == "amused"
    assert newest["provenance"]["source"] == "manual"
    assert oldest["expression"] == "amused"
    assert oldest["provenance"]["reason"] == "a joke landed"
    assert oldest["provenance"]["previous_expression"] is None
    # The rows ride P-092's kept history verbatim in substance.
    kept = ex.list_history(uid, chat_id=chat_id)
    for event, row in zip(doc["events"], kept, strict=True):
        for key in ("chat_id", "character_id", "expression",
                    "selected_at", "provenance"):
            assert event[key] == row[key]


async def test_still_ready_event_names_its_descriptor(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, chat_id, bound_id, _g = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
        doc = await hist.resolve_face_history(session, uid, chat_id)
    (event,) = doc["events"]
    assert event["entry_state"] == hist.ENTRY_STATE_STILL_READY
    assert event["problem_now"] is None
    assert doc["still_ready_count"] == 1
    descriptor = event["descriptor"]
    assert descriptor["name"] == "amused"
    assert descriptor["bound"] is True
    assert descriptor["renderable"] is True
    base = f"/api/v1/characters/{cid}/assets/{bound_id}"
    assert descriptor["content_url"] == f"{base}/content"
    assert descriptor["thumbnail_url"] == f"{base}/thumbnail"
    assert doc["presentation_state"] == "ready"
    assert doc["current"]["expression"] == "amused"


async def test_declared_unbound_event_states_its_problem(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "neutral")
        await ex.select_for_chat(session, uid, chat_id, "wrong")
        doc = await hist.resolve_face_history(session, uid, chat_id)
    by_name = {e["expression"]: e for e in doc["events"]}
    neutral = by_name["neutral"]
    assert neutral["entry_state"] == hist.ENTRY_STATE_DECLARED_UNBOUND
    assert neutral["problem_now"] == "no_asset"
    assert neutral["descriptor"]["renderable"] is False
    assert neutral["descriptor"]["content_url"] is None
    wrong = by_name["wrong"]
    assert wrong["entry_state"] == hist.ENTRY_STATE_DECLARED_UNBOUND
    assert wrong["problem_now"] == "wrong_kind"
    assert doc["still_ready_count"] == 0


async def test_event_outliving_its_set_is_no_longer_declared(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
    assert ex.delete_set(uid, cid) is True
    async with factory() as session:
        doc = await hist.resolve_face_history(session, uid, chat_id)
    (event,) = doc["events"]
    assert event["entry_state"] == hist.ENTRY_STATE_NO_LONGER_DECLARED
    assert event["problem_now"] == "not_declared"
    assert event["descriptor"] is None
    assert doc["presentation_state"] == "current_unbound"


async def test_replaced_set_makes_old_names_no_longer_declared(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, chat_id, bound_id, _g = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
    ex.update_set(uid, cid, {
        "character_id": cid,
        "entries": [
            {"name": "calm", "label": "Calm", "asset_id": bound_id},
        ],
        "default": "calm",
    })
    async with factory() as session:
        doc = await hist.resolve_face_history(session, uid, chat_id)
    (event,) = doc["events"]
    assert event["expression"] == "amused"
    assert event["entry_state"] == hist.ENTRY_STATE_NO_LONGER_DECLARED
    assert event["descriptor"] is None


async def test_cleared_event_is_not_a_face(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
    assert ex.clear_selection(uid, chat_id, reason="scene over") is True
    async with factory() as session:
        doc = await hist.resolve_face_history(session, uid, chat_id)
    assert doc["event_count"] == 2
    assert doc["selection_count"] == 1 and doc["cleared_count"] == 1
    newest = doc["events"][0]
    assert newest["entry_state"] == hist.ENTRY_STATE_CLEARED
    assert newest["expression"] is None
    assert newest["descriptor"] is None
    assert newest["problem_now"] is None
    assert newest["provenance"]["reason"] == "scene over"
    assert newest["provenance"]["previous_expression"] == "amused"
    assert doc["presentation_state"] == "no_selection"
    assert doc["current"] is None


async def test_default_application_provenance_rides(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        applied = await ex.apply_default_for_chat(session, uid, chat_id)
        assert applied is not None
        doc = await hist.resolve_face_history(session, uid, chat_id)
    (event,) = doc["events"]
    assert event["expression"] == "amused"
    assert event["provenance"]["source"] == "default"
    assert event["entry_state"] == hist.ENTRY_STATE_STILL_READY


# -- Pure-read law / notes --------------------------------------------------------


async def test_resolve_is_a_pure_read(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
    store = ex.store_path(uid)
    before = store.read_bytes()
    async with factory() as session:
        await hist.resolve_face_history(session, uid, chat_id)
        await hist.resolve_face_history(session, uid, chat_id)
    assert store.read_bytes() == before
    assert ex.current_expression(uid, chat_id)["expression"] == "amused"
    assert len(ex.list_history(uid, chat_id=chat_id)) == 1


async def test_notes_and_closed_state_law(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid, None)
    async with factory() as session:
        doc = await hist.resolve_face_history(session, uid, chat_id)
    assert doc["notes"] == list(hist.NOTES)
    assert len(doc["notes"]) == 5
    assert "renders nothing" in doc["notes"][0]
    assert "kept window" in doc["notes"][2]
    assert set(hist.ENTRY_STATES) == {
        "still_ready", "declared_unbound",
        "no_longer_declared", "cleared"}


async def test_kept_window_is_named_honestly(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        for i in range(105):
            name = "amused" if i % 2 == 0 else "neutral"
            await ex.select_for_chat(session, uid, chat_id, name)
        doc = await hist.resolve_face_history(session, uid, chat_id)
    assert doc["kept_limit"] == 100
    assert doc["event_count"] == 100
    assert doc["at_kept_limit"] is True
    assert doc["selection_count"] == 100
    assert doc["cleared_count"] == 0


# -- HTTP surface -------------------------------------------------------------------


def _png_chunk(ctype: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + ctype + data
            + struct.pack(">I", zlib.crc32(ctype + data) & 0xFFFFFFFF))


def make_png_bytes(width=16, height=16, color=(200, 30, 30)) -> bytes:
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))
    return (b"\x89PNG\r\n\x1a\n"
            + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + _png_chunk(b"IDAT", zlib.compress(raw))
            + _png_chunk(b"IEND", b""))


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client

def test_http_history_flow(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/characters", json={"card": card_dict()})
    assert created.status_code in (200, 201), created.text
    cid = created.json()["id"]
    up = client.post(
        f"/api/v1/characters/{cid}/assets",
        data={"kind": "expression", "name": "amused"},
        files={"file": ("amused.png", make_png_bytes(), "image/png")})
    assert up.status_code == 201, up.text
    asset_id = up.json()["id"]
    made = client.post("/api/v1/expressions/sets", json={
        "character_id": cid,
        "entries": [{"name": "neutral"},
                    {"name": "amused", "asset_id": asset_id}],
        "default": "neutral"})
    assert made.status_code == 201, made.text
    chat = client.post("/api/v1/chats",
                       json={"title": "T", "character_id": cid})
    assert chat.status_code in (200, 201), chat.text
    chat_id = chat.json()["id"]
    before = client.get("/api/v1/faces/history",
                        params={"chat_id": chat_id})
    assert before.status_code == 200, before.text
    assert before.json()["events"] == []
    assert before.json()["presentation_state"] == "no_selection"
    picked = client.post("/api/v1/expressions/select",
                         json={"chat_id": chat_id, "name": "amused"})
    assert picked.status_code == 200, picked.text
    after = client.get("/api/v1/faces/history",
                       params={"chat_id": chat_id})
    assert after.status_code == 200, after.text
    doc = after.json()
    assert doc["schema"] == "runmal-p158-face-history-v1"
    assert doc["event_count"] == 1
    assert doc["events"][0]["expression"] == "amused"
    assert doc["events"][0]["entry_state"] == "still_ready"
    assert doc["events"][0]["descriptor"]["content_url"] == (
        f"/api/v1/characters/{cid}/assets/{asset_id}/content")
    assert doc["presentation_state"] == "ready"
    missing = client.get("/api/v1/faces/history",
                         params={"chat_id": str(uuid.uuid4())})
    assert missing.status_code == 404
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/faces/history" in paths


def test_http_unbound_chat_is_data_at_200(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat = client.post("/api/v1/chats", json={"title": "Solo"})
    assert chat.status_code in (200, 201), chat.text
    res = client.get("/api/v1/faces/history",
                     params={"chat_id": chat.json()["id"]})
    assert res.status_code == 200, res.text
    assert res.json()["presentation_state"] == "no_character"
    assert res.json()["events"] == []


# -- Neighbours -----------------------------------------------------------------------


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS


def test_current_revision_is_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
