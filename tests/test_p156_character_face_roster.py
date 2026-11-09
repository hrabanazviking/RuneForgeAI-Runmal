"""P-156 Character face roster battery (Part X, DERIVED).

Pins the contract from hidden_files/P156_DESIGN.md: the
per-character (chat-less) face roster as a pure read over
P-092's character-keyed binding_report - None for a
missing/foreign character (existence never leaks), every
declared entry resolved to a presentation descriptor in
P-155's shape (P-023 content/thumbnail roads as data,
present only when bound), the roster classified under the
closed ROSTER_STATES law, the declared default and the
character avatar named as fallback DATA (never applied,
never substituted), NO current face anywhere in the
document (selection is per chat, P-092's explicit act),
the HTTP road (404 unknown/foreign, every state data at
200), and the neighbours (migration head stays 0041,
no 0042).
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.assets import service as assets_svc
from runmal.auth import get_or_create_credential
from runmal.characters import service as characters_svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.faces import roster as fr
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


async def seed_asset(factory, uid, cid, kind="expression",
                     name="amused", filename="amused.png"):
    async with factory() as session:
        row = await assets_svc.add_asset(
            session, uid, cid, kind=kind, name=name,
            filename=filename, data=PNG_BYTES)
        await session.commit()
        return row.id


def declare(uid, cid, base, entries, default=None):
    return ex.create_set(uid, {
        "character_id": cid, "entries": entries,
        "default": default}, base_dir=base)


async def roster(factory, uid, cid, base):
    async with factory() as session:
        return await fr.resolve_character_roster(
            session, uid, cid, base_dir=base)


# -- Existence / owner scoping ---------------------------------


async def test_missing_character_resolves_none(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    doc = await roster(factory, uid, str(uuid.uuid4()),
                       tmp_path / "store")
    assert doc is None


async def test_foreign_character_resolves_none(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, "other")
    cid = await seed_character(factory, uid)
    assert await roster(factory, other, cid,
                        tmp_path / "store") is None
    assert await roster(factory, uid, cid,
                        tmp_path / "store") is not None


# -- State law ---------------------------------------------------


async def test_no_set_state_and_envelope(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    doc = await roster(factory, uid, cid, tmp_path / "store")
    assert doc["schema"] == fr.ROSTER_SCHEMA == (
        "runmal-p156-character-face-roster-v1")
    assert doc["state"] == fr.STATE_NO_SET == "no_set"
    assert doc["state"] in fr.ROSTER_STATES
    assert doc["character_id"] == cid
    assert doc["character"]["id"] == cid
    assert doc["character"]["name"] == "Asta"
    assert doc["set"] is None
    assert doc["entries"] == []
    assert doc["entry_count"] == doc["bound_count"] == 0
    assert doc["renderable_count"] == doc["unbound_count"] == 0
    assert doc["default_entry"] is None
    assert doc["avatar"] == {"has_avatar": False,
                             "avatar_asset": None,
                             "avatar_url": None}
    assert doc["selection_scope"] == "per_chat"
    assert doc["notes"] == list(fr.NOTES)
    assert len(doc["notes"]) == 5


async def test_empty_set_state(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    base = tmp_path / "store"
    declare(uid, cid, base, [], default=None)
    doc = await roster(factory, uid, cid, base)
    assert doc["state"] == fr.STATE_EMPTY_SET == "empty_set"
    assert doc["set"] is not None
    assert doc["entries"] == []


async def test_no_renderable_state(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    base = tmp_path / "store"
    declare(uid, cid, base,
            [{"name": "neutral", "label": "Neutral"},
             {"name": "ghost", "asset_id": str(uuid.uuid4())}],
            default="neutral")
    doc = await roster(factory, uid, cid, base)
    assert doc["state"] == fr.STATE_NO_RENDERABLE
    assert doc["renderable_count"] == 0
    assert doc["unbound_count"] == 2
    problems = {e["name"]: e["problem"] for e in doc["entries"]}
    assert problems == {"neutral": "no_asset",
                        "ghost": "asset_missing"}
    for entry in doc["entries"]:
        assert entry["renderable"] is False
        assert entry["content_url"] is None
        assert entry["thumbnail_url"] is None
    # The default rides as data even when unbound.
    assert doc["default_entry"]["name"] == "neutral"
    assert doc["default_entry"]["bound"] is False


async def test_ready_state_descriptors_and_counts(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    base = tmp_path / "store"
    asset_id = await seed_asset(factory, uid, cid)
    bg_id = await seed_asset(factory, uid, cid, kind="background",
                             name="hall", filename="hall.png")
    declare(uid, cid, base,
            [{"name": "neutral", "label": "Neutral"},
             {"name": "amused", "label": "Amused",
              "asset_id": asset_id, "notes": " grin "},
             {"name": "hall", "asset_id": bg_id}],
            default="amused")
    doc = await roster(factory, uid, cid, base)
    assert doc["state"] == fr.STATE_READY == "ready"
    assert doc["entry_count"] == 3
    assert doc["bound_count"] == 1
    assert doc["renderable_count"] == 1
    assert doc["unbound_count"] == 2
    by_name = {e["name"]: e for e in doc["entries"]}
    amused = by_name["amused"]
    assert amused["bound"] is True
    assert amused["problem"] is None
    assert amused["renderable"] is True
    assert amused["label"] == "Amused"
    assert amused["asset"]["id"] == asset_id
    assert amused["content_url"] == (
        f"/api/v1/characters/{cid}/assets/{asset_id}/content")
    assert amused["thumbnail_url"] == (
        f"/api/v1/characters/{cid}/assets/{asset_id}/thumbnail")
    assert by_name["hall"]["problem"] == "wrong_kind"
    assert by_name["hall"]["asset"]["id"] == bg_id
    assert by_name["hall"]["content_url"] is None
    assert by_name["neutral"]["problem"] == "no_asset"
    assert doc["default_entry"] == amused
    # Set rides verbatim from the binding report.
    assert doc["set"]["default"] == "amused"
    assert [e["name"] for e in doc["set"]["entries"]] == [
        "neutral", "amused", "hall"]


# -- No current face / pure read ---------------------------------


async def test_roster_names_no_current_face(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    base = tmp_path / "store"
    asset_id = await seed_asset(factory, uid, cid)
    declare(uid, cid, base,
            [{"name": "amused", "asset_id": asset_id}],
            default="amused")
    doc = await roster(factory, uid, cid, base)
    assert "current" not in doc
    assert "face" not in doc
    assert "current_binding" not in doc
    assert doc["selection_scope"] == fr.SELECTION_SCOPE


async def test_roster_is_a_pure_read(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    base = tmp_path / "store"
    declare(uid, cid, base, [{"name": "neutral"}], default="neutral")
    before = ex.get_set(uid, cid, base_dir=base)
    first = await roster(factory, uid, cid, base)
    second = await roster(factory, uid, cid, base)
    assert first == second
    assert ex.get_set(uid, cid, base_dir=base) == before


# -- Avatar fallback ----------------------------------------------


async def test_avatar_fallback_named_as_data(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    async with factory() as session:
        stored = await characters_svc.set_avatar(
            session, uid, cid, "asta.png", PNG_BYTES)
    assert stored == "asta.png"
    doc = await roster(factory, uid, cid, tmp_path / "store")
    assert doc["avatar"] == {
        "has_avatar": True, "avatar_asset": "asta.png",
        "avatar_url": f"/api/v1/characters/{cid}/avatar"}
    assert doc["character"]["has_avatar"] is True


# -- HTTP surface ---------------------------------------------------


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    client = TestClient(create_app(factory))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client, factory


def test_http_roster_flow(tmp_path, monkeypatch):
    client, _factory = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/characters",
                          json={"card": card_dict()})
    assert created.status_code in (200, 201), created.text
    cid = created.json()["id"]
    res = client.get("/api/v1/faces/roster",
                     params={"character_id": cid})
    assert res.status_code == 200, res.text
    doc = res.json()
    assert doc["schema"] == fr.ROSTER_SCHEMA
    assert doc["state"] == "no_set"
    assert "current" not in doc and "face" not in doc
    missing = client.get("/api/v1/faces/roster",
                         params={"character_id": str(uuid.uuid4())})
    assert missing.status_code == 404


def test_http_roster_ready_with_declared_set(tmp_path, monkeypatch):
    client, _factory = make_client(tmp_path, monkeypatch)
    created = client.post("/api/v1/characters",
                          json={"card": card_dict()})
    cid = created.json()["id"]
    up = client.post(
        f"/api/v1/characters/{cid}/assets",
        data={"kind": "expression", "name": "amused"},
        files={"file": ("amused.png", PNG_BYTES, "image/png")})
    assert up.status_code == 201, up.text
    made = client.post("/api/v1/expressions/sets", json={
        "character_id": cid,
        "entries": [{"name": "amused",
                     "asset_id": up.json()["id"]}],
        "default": "amused"})
    assert made.status_code == 201, made.text
    res = client.get("/api/v1/faces/roster",
                     params={"character_id": cid})
    assert res.status_code == 200, res.text
    doc = res.json()
    assert doc["state"] == "ready"
    assert doc["renderable_count"] == 1
    assert doc["default_entry"]["name"] == "amused"
    assert doc["entries"][0]["content_url"].endswith("/content")


# -- Neighbours -------------------------------------------------------


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0041"
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
