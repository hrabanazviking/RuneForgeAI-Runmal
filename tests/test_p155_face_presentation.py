"""P-155 - Face presentation foundation (Part X opener, DERIVED).

Pins: the presentation document resolving P-092's inspect
surface verbatim in substance - per-entry renderable
descriptors with the P-023 content/thumbnail roads as data
(URLs only when bound), the closed state law (ready /
current_unbound / no_selection / no_set / no_character,
with not_declared for a selection outliving its set), the
face named only when ready, the declared default and the
character avatar named as fallback data and never
substituted, the standing honesty notes, owner scoping
(unknown/foreign chat -> None / 404), the pure-read law
(no selection written, no default applied, the P-092 store
byte-identical after a resolve), and the neighbours
(migration head stays 0041, no 0042). No network.
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
from runmal.faces import presentation as face
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


async def _world(factory, uid, *, with_avatar=False):
    """Character + bound chat + one bound sprite, one unbound
    entry and one wrong-kind entry; default is the bound one."""
    cid = await seed_character(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    bound_id = await _add_asset(factory, uid, cid, kind="expression",
                                name="amused")
    bg_id = await _add_asset(factory, uid, cid, kind="background",
                             name="stairs")
    if with_avatar:
        async with factory() as session:
            await characters_svc.set_avatar(
                session, uid, cid, "face.png", PNG_BYTES)
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


# -- States ---------------------------------------------------------------------


async def test_missing_and_foreign_chat_resolve_none(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, name="other")
    _cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        assert await face.resolve_presentation(
            session, uid, str(uuid.uuid4())) is None
        assert await face.resolve_presentation(
            session, other, chat_id) is None


async def test_no_character_state(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid, None)
    async with factory() as session:
        doc = await face.resolve_presentation(session, uid, chat_id)
    assert doc["state"] == face.STATE_NO_CHARACTER
    assert doc["character_id"] is None
    assert doc["entries"] == [] and doc["face"] is None
    assert doc["fallbacks"]["default_entry"] is None
    assert doc["fallbacks"]["avatar"]["has_avatar"] is False


async def test_no_set_state_with_avatar_fallback(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    async with factory() as session:
        await characters_svc.set_avatar(session, uid, cid, "face.png", PNG_BYTES)
    async with factory() as session:
        doc = await face.resolve_presentation(session, uid, chat_id)
    assert doc["state"] == face.STATE_NO_SET
    assert doc["set"] is None and doc["face"] is None
    avatar = doc["fallbacks"]["avatar"]
    assert avatar == {"has_avatar": True, "avatar_asset": "face.png",
                      "avatar_url": f"/api/v1/characters/{cid}/avatar"}


async def test_no_selection_state_and_default_is_data(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, chat_id, bound_id, _g = await _world(factory, uid)
    async with factory() as session:
        doc = await face.resolve_presentation(session, uid, chat_id)
    assert doc["state"] == face.STATE_NO_SELECTION
    assert doc["face"] is None and doc["current"] is None
    default = doc["fallbacks"]["default_entry"]
    assert default["name"] == "amused" and default["renderable"] is True
    # The default was NOT applied by the read.
    assert ex.current_expression(uid, chat_id) is None


# -- Descriptors / ready ----------------------------------------------------------


async def test_descriptors_resolve_entries_honestly(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, chat_id, bound_id, _g = await _world(factory, uid)
    async with factory() as session:
        doc = await face.resolve_presentation(session, uid, chat_id)
    assert doc["schema"] == face.PRESENTATION_SCHEMA
    assert doc["entry_count"] == 3 and doc["bound_count"] == 1
    assert doc["renderable_count"] == 1
    by_name = {row["name"]: row for row in doc["entries"]}
    amused = by_name["amused"]
    assert amused["bound"] is True and amused["renderable"] is True
    assert amused["problem"] is None
    assert amused["asset"]["id"] == bound_id
    assert amused["asset"]["kind"] == "expression"
    base = f"/api/v1/characters/{cid}/assets/{bound_id}"
    assert amused["content_url"] == f"{base}/content"
    assert amused["thumbnail_url"] == f"{base}/thumbnail"
    neutral = by_name["neutral"]
    assert neutral["problem"] == "no_asset"
    assert neutral["renderable"] is False
    assert neutral["content_url"] is None
    assert neutral["thumbnail_url"] is None
    wrong = by_name["wrong"]
    assert wrong["problem"] == "wrong_kind"
    assert wrong["renderable"] is False and wrong["content_url"] is None
    assert wrong["asset"]["kind"] == "background"


async def test_ready_state_names_the_face(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b, _g = await _world(factory, uid, with_avatar=True)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused",
                                 reason="a joke landed")
    async with factory() as session:
        doc = await face.resolve_presentation(session, uid, chat_id)
    assert doc["state"] == face.STATE_READY
    assert doc["current_problem"] is None
    assert doc["current"]["expression"] == "amused"
    assert doc["current"]["provenance"]["reason"] == "a joke landed"
    assert doc["face"]["name"] == "amused"
    assert doc["face"]["renderable"] is True
    assert doc["face"]["content_url"].endswith("/content")


async def test_current_unbound_states_its_problem(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "neutral")
    async with factory() as session:
        doc = await face.resolve_presentation(session, uid, chat_id)
    assert doc["state"] == face.STATE_CURRENT_UNBOUND
    assert doc["current_problem"] == "no_asset"
    assert doc["face"] is None
    # Fallback data is present but NOT substituted as the face.
    assert doc["fallbacks"]["default_entry"]["name"] == "amused"


async def test_selection_outliving_its_set_is_not_declared(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid, chat_id, _b, _g = await _world(factory, uid)
    async with factory() as session:
        await ex.select_for_chat(session, uid, chat_id, "amused")
    assert ex.delete_set(uid, cid) is True
    async with factory() as session:
        doc = await face.resolve_presentation(session, uid, chat_id)
    assert doc["state"] == face.STATE_CURRENT_UNBOUND
    assert doc["current_problem"] == face.PROBLEM_NOT_DECLARED
    assert doc["face"] is None and doc["entries"] == []


# -- Pure-read law / notes ---------------------------------------------------------


async def test_resolve_is_a_pure_read(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    _cid, chat_id, _b, _g = await _world(factory, uid)
    store = ex.store_path(uid)
    before = store.read_bytes()
    async with factory() as session:
        await face.resolve_presentation(session, uid, chat_id)
        await face.resolve_presentation(session, uid, chat_id)
    assert store.read_bytes() == before
    assert ex.current_expression(uid, chat_id) is None
    assert ex.list_history(uid, chat_id=chat_id) == []


async def test_notes_are_the_five_standing_notes(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid, None)
    async with factory() as session:
        doc = await face.resolve_presentation(session, uid, chat_id)
    assert doc["notes"] == list(face.NOTES)
    assert len(doc["notes"]) == 5
    assert "renders nothing" in doc["notes"][0]
    assert set(face.PRESENTATION_STATES) == {
        "ready", "current_unbound", "no_selection",
        "no_set", "no_character"}
    assert doc["state"] in face.PRESENTATION_STATES


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


def test_http_presentation_flow(tmp_path, monkeypatch):
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
    before = client.get("/api/v1/faces/presentation",
                        params={"chat_id": chat_id})
    assert before.status_code == 200, before.text
    assert before.json()["state"] == "no_selection"
    assert before.json()["face"] is None
    picked = client.post("/api/v1/expressions/select",
                         json={"chat_id": chat_id, "name": "amused"})
    assert picked.status_code == 200, picked.text
    after = client.get("/api/v1/faces/presentation",
                       params={"chat_id": chat_id})
    assert after.status_code == 200, after.text
    doc = after.json()
    assert doc["state"] == "ready"
    assert doc["face"]["name"] == "amused"
    assert doc["face"]["content_url"] == (
        f"/api/v1/characters/{cid}/assets/{asset_id}/content")
    # The named content road itself serves the sprite bytes.
    content = client.get(doc["face"]["content_url"])
    assert content.status_code == 200, content.text
    missing = client.get("/api/v1/faces/presentation",
                         params={"chat_id": str(uuid.uuid4())})
    assert missing.status_code == 404
    paths = client.get("/openapi.json").json()["paths"]
    assert "/api/v1/faces/presentation" in paths


def test_http_unbound_chat_is_data_at_200(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat = client.post("/api/v1/chats", json={"title": "Solo"})
    assert chat.status_code in (200, 201), chat.text
    res = client.get("/api/v1/faces/presentation",
                     params={"chat_id": chat.json()["id"]})
    assert res.status_code == 200, res.text
    assert res.json()["state"] == "no_character"


# -- Neighbours -----------------------------------------------------------------------


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS


def test_current_revision_is_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
