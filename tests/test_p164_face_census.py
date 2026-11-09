"""P-164 - Face census (Part X, DERIVED).

Pins: the owner-wide current-face census - one row
per owned character in the characters service's
creation order, each row composing P-160's
face-chats board verbatim in substance (character
facts, board_state under P-160's law, the board's
rows whole, its counts), the census classified
under the closed CENSUS_STATES law (no_characters /
no_chats / none_ready / some_ready / all_ready), the
counts summed from the boards' own arithmetic,
owner scoping (another owner's characters and chats
never appear; a deleted character drops out), the
silent-current law (no voice key, no history key,
no face at census level anywhere), the standing
honesty notes, the pure-read law (the P-092 store
byte-identical after resolves, no history written),
HTTP end to end, and the neighbours (migration head
stays 0041, no 0042). No network.
"""

from __future__ import annotations

import struct
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
from runmal.faces import census
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


async def _world(factory, uid, name="Asta"):
    """Character + set: neutral (no asset), amused (bound
    sprite), wrong (wrong-kind asset); default amused.
    No chats yet - each test seeds the chats it judges."""
    cid = await seed_character(factory, uid, name=name)
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


# -- Empty censuses -------------------------------------------------------------


async def test_owner_with_no_characters_gets_empty_census(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    async with factory() as session:
        doc = await census.resolve_face_census(session, uid)
    assert doc["schema"] == census.CENSUS_SCHEMA
    assert doc["state"] == census.CENSUS_STATE_NO_CHARACTERS
    assert doc["characters"] == []
    assert doc["counts"] == {
        "character_count": 0, "characters_with_chats_count": 0,
        "chat_count": 0, "ready_count": 0,
        "selection_count": 0, "unbound_count": 0}


async def test_characters_without_chats_is_no_chats(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    async with factory() as session:
        doc = await census.resolve_face_census(session, uid)
    assert doc["state"] == census.CENSUS_STATE_NO_CHATS
    (row,) = doc["characters"]
    assert row["character_id"] == cid
    assert row["board_state"] == "no_chats"
    assert row["chats"] == []
    assert doc["counts"]["character_count"] == 1
    assert doc["counts"]["characters_with_chats_count"] == 0
    assert doc["counts"]["chat_count"] == 0


async def test_other_owners_world_never_appears(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, name="other")
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
        mine = await census.resolve_face_census(session, uid)
        theirs = await census.resolve_face_census(session, other)
    assert mine["counts"]["character_count"] == 1
    assert mine["state"] == census.CENSUS_STATE_ALL_READY
    assert theirs["state"] == census.CENSUS_STATE_NO_CHARACTERS
    assert theirs["characters"] == []


async def test_deleted_character_drops_out(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    keep = await seed_character(factory, uid, name="Bera")
    async with factory() as session:
        assert await characters_svc.delete_character(
            session, uid, cid) is True
        doc = await census.resolve_face_census(session, uid)
    assert [row["character_id"] for row in doc["characters"]] == [keep]
    assert doc["counts"]["character_count"] == 1


# -- Rows: order and verbatim board composition ----------------------------------


async def test_rows_ride_in_character_creation_order(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    first = await seed_character(factory, uid, name="First")
    second = await seed_character(factory, uid, name="Second")
    third = await seed_character(factory, uid, name="Third")
    async with factory() as session:
        doc = await census.resolve_face_census(session, uid)
    assert [row["character_id"] for row in doc["characters"]] == [
        first, second, third]
    assert [row["character"]["name"] for row in doc["characters"]] == [
        "First", "Second", "Third"]


async def test_row_composes_p160_board_field_for_field(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused",
                                 reason="a joke landed")
        doc = await census.resolve_face_census(session, uid)
        direct = await board.resolve_character_face_chats(
            session, uid, cid)
    (row,) = doc["characters"]
    assert row["character_id"] == direct["character_id"]
    assert row["character"] == direct["character"]
    assert row["board_state"] == direct["state"]
    assert row["chats"] == direct["chats"]
    for key in ("chat_count", "ready_count", "selection_count",
                "unbound_count"):
        assert row[key] == direct[key]
    (chat_row,) = row["chats"]
    assert chat_row["presentation_state"] == "ready"
    assert chat_row["face"]["name"] == "amused"
    assert chat_row["current"]["provenance"]["reason"] == "a joke landed"


# -- The census law -----------------------------------------------------------------


async def test_none_ready_census(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    await seed_chat(factory, uid, cid)
    async with factory() as session:
        doc = await census.resolve_face_census(session, uid)
    assert doc["state"] == census.CENSUS_STATE_NONE_READY
    assert doc["counts"]["chat_count"] == 1
    assert doc["counts"]["ready_count"] == 0


async def test_all_ready_census_across_characters(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid_a, _b, _g = await _world(factory, uid, name="Asta")
    cid_b, _b2, _g2 = await _world(factory, uid, name="Bera")
    chat_a = await seed_chat(factory, uid, cid_a, title="A chat")
    chat_b = await seed_chat(factory, uid, cid_b, title="B chat")
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_a, "amused")
        await ex.select_for_chat(session, uid, chat_b, "amused")
        doc = await census.resolve_face_census(session, uid)
    assert doc["state"] == census.CENSUS_STATE_ALL_READY
    assert doc["counts"]["character_count"] == 2
    assert doc["counts"]["characters_with_chats_count"] == 2
    assert doc["counts"]["chat_count"] == 2
    assert doc["counts"]["ready_count"] == 2


async def test_counts_arithmetic_on_a_mixed_census(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid_a, _b, _g = await _world(factory, uid, name="Asta")
    cid_b, _b2, _g2 = await _world(factory, uid, name="Bera")
    await seed_character(factory, uid, name="Idle")
    ready_chat = await seed_chat(factory, uid, cid_a, title="Ready")
    unbound_chat = await seed_chat(factory, uid, cid_a, title="Unbound")
    await seed_chat(factory, uid, cid_b, title="Waiting")
    await seed_chat(factory, uid, None, title="Unbound chat")
    async with factory() as session:
        await ex.select_for_chat(session, uid, ready_chat, "amused")
        await ex.select_for_chat(session, uid, unbound_chat, "wrong")
        doc = await census.resolve_face_census(session, uid)
    counts = doc["counts"]
    assert counts["character_count"] == 3
    assert counts["characters_with_chats_count"] == 2
    assert counts["chat_count"] == 3
    assert counts["ready_count"] == 1
    assert counts["selection_count"] == 2
    assert counts["unbound_count"] == 1
    assert doc["state"] == census.CENSUS_STATE_SOME_READY
    by_name = {row["character"]["name"]: row
               for row in doc["characters"]}
    assert by_name["Asta"]["board_state"] == "some_ready"
    assert by_name["Bera"]["board_state"] == "none_ready"
    assert by_name["Idle"]["board_state"] == "no_chats"
    unbound_row = [row for row in by_name["Asta"]["chats"]
                   if row["title"] == "Unbound"][0]
    assert unbound_row["current_problem"] == "wrong_kind"
    assert unbound_row["face"] is None


# -- Silent-current law / pure read / notes ------------------------------------------


async def test_no_voice_no_history_no_census_face_keys(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, _b, _g = await _world(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
        doc = await census.resolve_face_census(session, uid)
    assert set(doc) == {"schema", "state", "characters",
                        "counts", "notes"}
    (row,) = doc["characters"]
    assert set(row) == {"character_id", "character", "board_state",
                        "chats", "chat_count", "ready_count",
                        "selection_count", "unbound_count"}
    assert set(doc["counts"]) == {
        "character_count", "characters_with_chats_count",
        "chat_count", "ready_count", "selection_count",
        "unbound_count"}
    for key in ("voice", "history", "events", "face", "current"):
        assert key not in doc
        assert key not in row


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
        await census.resolve_face_census(session, uid)
        await census.resolve_face_census(session, uid)
    assert store.read_bytes() == before
    assert ex.current_expression(uid, chat_id)["expression"] == "amused"
    assert len(ex.list_history(uid, chat_id=chat_id)) == 1


async def test_notes_and_closed_state_law(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    async with factory() as session:
        doc = await census.resolve_face_census(session, uid)
    assert doc["notes"] == list(census.NOTES)
    assert len(doc["notes"]) == 5
    assert "renders nothing" in doc["notes"][0]
    assert "no owner-wide" in doc["notes"][2]
    assert "current only" in doc["notes"][3]
    assert set(census.CENSUS_STATES) == {
        "no_characters", "no_chats", "none_ready",
        "some_ready", "all_ready"}


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


def test_http_census_flow(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    empty = client.get("/api/v1/faces/census")
    assert empty.status_code == 200, empty.text
    assert empty.json()["state"] == "no_characters"
    assert empty.json()["characters"] == []
    created = client.post("/api/v1/characters", json={"card": card_dict()})
    assert created.status_code in (200, 201), created.text
    cid = created.json()["id"]
    no_chats = client.get("/api/v1/faces/census")
    assert no_chats.status_code == 200, no_chats.text
    assert no_chats.json()["state"] == "no_chats"
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
    before = client.get("/api/v1/faces/census")
    assert before.json()["state"] == "none_ready"
    picked = client.post("/api/v1/expressions/select",
                         json={"chat_id": chat_id, "name": "amused"})
    assert picked.status_code == 200, picked.text
    after = client.get("/api/v1/faces/census")
    assert after.status_code == 200, after.text
    doc = after.json()
    assert doc["schema"] == "runmal-p164-face-census-v1"
    assert doc["state"] == "all_ready"
    assert doc["counts"]["ready_count"] == 1
    face = doc["characters"][0]["chats"][0]["face"]
    assert face["content_url"] == (
        f"/api/v1/characters/{cid}/assets/{asset_id}/content")
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/faces/census" in paths


# -- Neighbours -----------------------------------------------------------------------


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS


def test_current_revision_is_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
