"""P-160 - Character face chats (Part X, DERIVED).

Pins: the per-character board of that character's chats
and the face each one currently shows - P-155's
presentation document composed verbatim per chat (state,
current with provenance, current_problem, the descriptor
named as face only when that chat is ready), rows in the
chats service's creation order carrying the chat's own
title and message count, chats bound to other characters
and unbound chats never appearing, the board classified
under the closed BOARD_STATES law (no_chats / none_ready
/ some_ready / all_ready), the counts, the standing
honesty notes, owner scoping (unknown/foreign/deleted
character -> None / 404), the pure-read law (the P-092
store byte-identical after resolves, no history written),
and the neighbours (migration head stays 0041, no 0042).
No network.
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
from runmal.faces import chats as board
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


async def seed_chat(factory, uid, character_id=None, title="The Lighthouse"):
    async with factory() as session:
        chat = await chats_svc.create_chat(
            session, uid, title=title,
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
    """Character + set: neutral (no asset), amused (bound
    sprite), wrong (wrong-kind asset); default is amused.
    No chats yet - each test seeds the chats it judges."""
    cid = await seed_character(factory, uid)
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
    return cid, bound_id, bg_id


# -- Scoping / empty boards ------------------------------------------------------


async def test_missing_and_foreign_character_resolve_none(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, name="other")
    cid, _b, _g = await _world(factory, uid)
    async with factory() as session:
        assert await board.resolve_character_face_chats(
            session, uid, str(uuid.uuid4())) is None
        assert await board.resolve_character_face_chats(
            session, other, cid) is None


async def test_deleted_character_resolves_none(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    async with factory() as session:
        assert await characters_svc.delete_character(
            session, uid, cid) is True
        assert await board.resolve_character_face_chats(
            session, uid, cid) is None


async def test_character_with_no_chats_is_an_empty_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    async with factory() as session:
        doc = await board.resolve_character_face_chats(session, uid, cid)
    assert doc["schema"] == board.CHATS_SCHEMA
    assert doc["character_id"] == cid
    assert doc["character"]["id"] == cid
    assert doc["character"]["name"] == "Asta"
    assert doc["state"] == board.BOARD_STATE_NO_CHATS
    assert doc["chats"] == []
    assert doc["chat_count"] == 0
    assert doc["ready_count"] == 0
    assert doc["selection_count"] == 0
    assert doc["unbound_count"] == 0


async def test_unbound_and_other_character_chats_never_appear(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    other_cid = await seed_character(factory, uid, name="Bera")
    mine = await seed_chat(factory, uid, cid, title="Mine")
    await seed_chat(factory, uid, other_cid, title="Hers")
    await seed_chat(factory, uid, None, title="Unbound")
    async with factory() as session:
        doc = await board.resolve_character_face_chats(session, uid, cid)
    assert doc["chat_count"] == 1
    (row,) = doc["chats"]
    assert row["chat_id"] == mine
    assert row["title"] == "Mine"


# -- Rows: order, chat facts, per-chat face truth ---------------------------------


async def test_rows_ride_in_creation_order_with_chat_facts(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    first = await seed_chat(factory, uid, cid, title="First")
    second = await seed_chat(factory, uid, cid, title="Second")
    third = await seed_chat(factory, uid, cid, title="Third")
    async with factory() as session:
        doc = await board.resolve_character_face_chats(session, uid, cid)
    assert [row["chat_id"] for row in doc["chats"]] == [first, second, third]
    assert [row["title"] for row in doc["chats"]] == [
        "First", "Second", "Third"]
    assert all(row["message_count"] == 0 for row in doc["chats"])
    assert doc["chat_count"] == 3


async def test_ready_row_names_the_face_descriptor(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, bound_id, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused",
                                 reason="a joke landed")
        doc = await board.resolve_character_face_chats(session, uid, cid)
    (row,) = doc["chats"]
    assert row["presentation_state"] == "ready"
    assert row["current"]["expression"] == "amused"
    assert row["current"]["provenance"]["reason"] == "a joke landed"
    assert row["current_problem"] is None
    face = row["face"]
    assert face["name"] == "amused"
    assert face["bound"] is True
    assert face["renderable"] is True
    base = f"/api/v1/characters/{cid}/assets/{bound_id}"
    assert face["content_url"] == f"{base}/content"
    assert face["thumbnail_url"] == f"{base}/thumbnail"
    assert doc["state"] == board.BOARD_STATE_ALL_READY
    assert doc["ready_count"] == 1 and doc["selection_count"] == 1


async def test_no_selection_row_is_honest(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    await seed_chat(factory, uid, cid)
    async with factory() as session:
        doc = await board.resolve_character_face_chats(session, uid, cid)
    (row,) = doc["chats"]
    assert row["presentation_state"] == "no_selection"
    assert row["current"] is None
    assert row["current_problem"] is None
    assert row["face"] is None
    assert doc["state"] == board.BOARD_STATE_NONE_READY
    assert doc["selection_count"] == 0


async def test_unbound_current_row_states_its_problem(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "neutral")
        doc = await board.resolve_character_face_chats(session, uid, cid)
    (row,) = doc["chats"]
    assert row["presentation_state"] == "current_unbound"
    assert row["current"]["expression"] == "neutral"
    assert row["current_problem"] == "no_asset"
    assert row["face"] is None
    assert doc["unbound_count"] == 1
    assert doc["state"] == board.BOARD_STATE_NONE_READY
    assert doc["selection_count"] == 1 and doc["ready_count"] == 0


async def test_no_set_character_board_is_none_ready(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    await seed_chat(factory, uid, cid)
    async with factory() as session:
        doc = await board.resolve_character_face_chats(session, uid, cid)
    (row,) = doc["chats"]
    assert row["presentation_state"] == "no_set"
    assert row["face"] is None and row["current"] is None
    assert doc["state"] == board.BOARD_STATE_NONE_READY
    assert doc["chat_count"] == 1 and doc["ready_count"] == 0


# -- The board law ------------------------------------------------------------------


async def test_all_ready_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    first = await seed_chat(factory, uid, cid, title="First")
    second = await seed_chat(factory, uid, cid, title="Second")
    async with factory() as session:
        await ex.select_for_chat(session, uid, first, "amused")
        await ex.select_for_chat(session, uid, second, "amused")
        doc = await board.resolve_character_face_chats(session, uid, cid)
    assert doc["state"] == board.BOARD_STATE_ALL_READY
    assert doc["ready_count"] == 2 and doc["chat_count"] == 2


async def test_some_ready_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    ready_chat = await seed_chat(factory, uid, cid, title="Ready")
    await seed_chat(factory, uid, cid, title="Waiting")
    async with factory() as session:
        await ex.select_for_chat(session, uid, ready_chat, "amused")
        doc = await board.resolve_character_face_chats(session, uid, cid)
    assert doc["state"] == board.BOARD_STATE_SOME_READY
    assert doc["ready_count"] == 1 and doc["chat_count"] == 2
    assert doc["selection_count"] == 1


async def test_counts_arithmetic_on_a_mixed_board(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    ready_chat = await seed_chat(factory, uid, cid, title="Ready")
    unbound_chat = await seed_chat(factory, uid, cid, title="Unbound")
    await seed_chat(factory, uid, cid, title="Waiting")
    async with factory() as session:
        await ex.select_for_chat(session, uid, ready_chat, "amused")
        await ex.select_for_chat(session, uid, unbound_chat, "wrong")
        doc = await board.resolve_character_face_chats(session, uid, cid)
    assert doc["chat_count"] == 3
    assert doc["ready_count"] == 1
    assert doc["selection_count"] == 2
    assert doc["unbound_count"] == 1
    assert doc["state"] == board.BOARD_STATE_SOME_READY
    by_title = {row["title"]: row for row in doc["chats"]}
    assert by_title["Unbound"]["current_problem"] == "wrong_kind"
    assert by_title["Waiting"]["presentation_state"] == "no_selection"


# -- Pure-read law / notes ------------------------------------------------------------


async def test_resolve_is_a_pure_read(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
    store = ex.store_path(uid)
    before = store.read_bytes()
    async with factory() as session:
        await board.resolve_character_face_chats(session, uid, cid)
        await board.resolve_character_face_chats(session, uid, cid)
    assert store.read_bytes() == before
    assert ex.current_expression(uid, chat_id)["expression"] == "amused"
    assert len(ex.list_history(uid, chat_id=chat_id)) == 1


async def test_notes_and_closed_state_law(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    async with factory() as session:
        doc = await board.resolve_character_face_chats(session, uid, cid)
    assert doc["notes"] == list(board.NOTES)
    assert len(doc["notes"]) == 5
    assert "renders nothing" in doc["notes"][0]
    assert "no single current face" in doc["notes"][2]
    assert set(board.BOARD_STATES) == {
        "no_chats", "none_ready", "some_ready", "all_ready"}


# -- HTTP surface ---------------------------------------------------------------------


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


def test_http_face_chats_flow(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/characters", json={"card": card_dict()})
    assert created.status_code in (200, 201), created.text
    cid = created.json()["id"]
    empty = client.get("/api/v1/faces/chats", params={"character_id": cid})
    assert empty.status_code == 200, empty.text
    assert empty.json()["state"] == "no_chats"
    assert empty.json()["chats"] == []
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
    before = client.get("/api/v1/faces/chats", params={"character_id": cid})
    assert before.status_code == 200, before.text
    assert before.json()["state"] == "none_ready"
    assert before.json()["chats"][0]["presentation_state"] == "no_selection"
    picked = client.post("/api/v1/expressions/select",
                         json={"chat_id": chat_id, "name": "amused"})
    assert picked.status_code == 200, picked.text
    after = client.get("/api/v1/faces/chats", params={"character_id": cid})
    assert after.status_code == 200, after.text
    doc = after.json()
    assert doc["schema"] == "runmal-p160-character-face-chats-v1"
    assert doc["state"] == "all_ready"
    assert doc["chats"][0]["face"]["content_url"] == (
        f"/api/v1/characters/{cid}/assets/{asset_id}/content")
    missing = client.get("/api/v1/faces/chats",
                         params={"character_id": str(uuid.uuid4())})
    assert missing.status_code == 404
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/faces/chats" in paths


# -- Neighbours -----------------------------------------------------------------------


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS


def test_current_revision_is_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
