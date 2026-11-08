"""P-092 Expression/sprite plugin surface battery.

Pins the contract from hidden_files/P092_DESIGN.md: the
citizen manifest as strict round-tripping data, the P-082
empty-grant stance, strict set/entry validation, the durable
per-user set store (owner isolation, corrupt-store refusal),
per-chat current-expression selection with its provenance
receipt (undeclared names refuse, defaults apply only via
the explicit road, clearing is recorded), the P-023 asset
binding report (bound / no_asset / asset_missing /
wrong_kind / not_stored stated honestly, bytes never read),
the draft derivation from existing expression assets
(returned, never saved), the chat roads, the HTTP surface,
and the neighbours (migration head stays 0041, no 0042).
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
from runmal.plugins import expressions as ex
from runmal.plugins import service as plugin_service
from runmal.plugins.image_generation import render_deterministic_png
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginRegistry, PluginState

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


def set_payload(character_id, **over):
    body = {
        "character_id": character_id,
        "entries": [
            {"name": "neutral", "label": "Neutral"},
            {"name": "amused", "label": "Amused"},
            {"name": "stern"},
        ],
        "default": "neutral",
    }
    body.update(over)
    return body


# -- Citizen / manifest ------------------------------------------------------


def test_manifest_round_trips_and_registers():
    data = ex.manifest_data()
    manifest = manifest_from_data(data)
    assert manifest_to_data(manifest) == data
    assert manifest.id == ex.PLUGIN_ID == "runmal.expressions"
    assert "chat.write" not in manifest.permissions
    registry = PluginRegistry()
    record, _plugin = ex.register_plugin(registry)
    assert record.state == PluginState.REGISTERED
    assert registry.get(ex.PLUGIN_ID).manifest.id == ex.PLUGIN_ID


def test_sandbox_grants_are_empty():
    grants = ex.sandbox_grants()
    assert grants.resources == frozenset()


def test_ui_contribution_is_the_sidebar_panel():
    registry = PluginRegistry()
    ex.register_plugin(registry, enable=True)
    contributions = registry.ui_contributions("chat.sidebar")
    assert any(c["plugin_id"] == ex.PLUGIN_ID for c in contributions)


# -- Declaration validation ----------------------------------------------------


def test_entry_defaults_label_and_unbound_asset():
    entry = ex.entry_from_data({"name": "amused"})
    assert entry == {"name": "amused", "label": "amused",
                     "asset_id": None, "notes": ""}


def test_entry_rejects_bad_slug_unknown_keys_bad_asset():
    with pytest.raises(ex.ExpressionError):
        ex.entry_from_data({"name": "Amused!"})
    with pytest.raises(ex.ExpressionError):
        ex.entry_from_data({"name": "amused", "bogus": 1})
    with pytest.raises(ex.ExpressionError):
        ex.entry_from_data({"name": "amused", "asset_id": "not-a-uuid"})
    with pytest.raises(ex.ExpressionError):
        ex.entry_from_data({"name": "amused", "label": " "})


def test_set_rejects_duplicates_undeclared_default_unknown_keys():
    cid = str(uuid.uuid4())
    with pytest.raises(ex.ExpressionError):
        ex.set_body_from_data(set_payload(
            cid, entries=[{"name": "a"}, {"name": "a"}], default=None))
    with pytest.raises(ex.ExpressionError):
        ex.set_body_from_data(set_payload(cid, default="ghost"))
    with pytest.raises(ex.ExpressionError):
        ex.set_body_from_data(set_payload(cid, bogus=1))
    with pytest.raises(ex.ExpressionError):
        ex.set_body_from_data(set_payload(
            cid, entries=[{"name": f"e{i}"} for i in range(65)],
            default=None))


def test_empty_set_is_a_legal_declaration():
    cid = str(uuid.uuid4())
    body = ex.set_body_from_data(
        {"character_id": cid, "entries": [], "default": None})
    assert body["entries"] == [] and body["default"] is None


# -- Set store CRUD -------------------------------------------------------------


def test_set_crud_and_duplicate_create_refuses(tmp_path):
    uid = str(uuid.uuid4())
    cid = str(uuid.uuid4())
    base = tmp_path / "store"
    created = ex.create_set(uid, set_payload(cid), base_dir=base)
    assert created["character_id"] == cid
    assert created["default"] == "neutral"
    assert created["created_at"] == created["updated_at"]
    with pytest.raises(ex.ExpressionError):
        ex.create_set(uid, set_payload(cid), base_dir=base)
    assert ex.get_set(uid, cid, base_dir=base)["entries"][2]["label"] == "stern"
    assert [s["character_id"] for s in ex.list_sets(uid, base_dir=base)] == [cid]
    updated = ex.update_set(uid, cid, set_payload(
        cid, entries=[{"name": "calm"}], default="calm"), base_dir=base)
    assert [e["name"] for e in updated["entries"]] == ["calm"]
    assert updated["created_at"] == created["created_at"]
    assert ex.delete_set(uid, cid, base_dir=base) is True
    assert ex.get_set(uid, cid, base_dir=base) is None
    assert ex.delete_set(uid, cid, base_dir=base) is False


def test_update_missing_set_none_and_character_mismatch_rejects(tmp_path):
    uid = str(uuid.uuid4())
    cid, other = str(uuid.uuid4()), str(uuid.uuid4())
    base = tmp_path / "store"
    assert ex.update_set(uid, cid, set_payload(cid), base_dir=base) is None
    ex.create_set(uid, set_payload(cid), base_dir=base)
    with pytest.raises(ex.ExpressionError):
        ex.update_set(uid, cid, set_payload(other), base_dir=base)


def test_set_store_is_owner_isolated(tmp_path):
    uid, other = str(uuid.uuid4()), str(uuid.uuid4())
    cid = str(uuid.uuid4())
    base = tmp_path / "store"
    ex.create_set(uid, set_payload(cid), base_dir=base)
    assert ex.get_set(other, cid, base_dir=base) is None
    assert ex.list_sets(other, base_dir=base) == []


def test_corrupt_store_raises_never_silently_resets(tmp_path):
    uid = str(uuid.uuid4())
    base = tmp_path / "store"
    path = ex.store_path(uid, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(ex.ExpressionError):
        ex.list_sets(uid, base_dir=base)
    assert path.read_text(encoding="utf-8") == "{not json"


# -- Selection (sync core) --------------------------------------------------------


def test_select_and_current_carry_provenance(tmp_path):
    uid, cid, chat_id = (str(uuid.uuid4()) for _ in range(3))
    base = tmp_path / "store"
    ex.create_set(uid, set_payload(cid), base_dir=base)
    first = ex.select_expression(uid, chat_id, cid, "amused", base_dir=base)
    assert first["expression"] == "amused"
    assert first["provenance"]["source"] == "manual"
    assert first["provenance"]["via"] == "expression_plugin"
    assert first["provenance"]["previous_expression"] is None
    assert first["provenance"]["actor_user_id"] == uid
    second = ex.select_expression(
        uid, chat_id, cid, "stern", source="message",
        reason="the ninth stair", message_id=str(uuid.uuid4()),
        base_dir=base)
    assert second["provenance"]["previous_expression"] == "amused"
    assert second["provenance"]["reason"] == "the ninth stair"
    assert ex.current_expression(uid, chat_id, base_dir=base) == second


def test_select_undeclared_no_set_and_bad_source_refuse(tmp_path):
    uid, cid, chat_id = (str(uuid.uuid4()) for _ in range(3))
    base = tmp_path / "store"
    with pytest.raises(ex.ExpressionError):
        ex.select_expression(uid, chat_id, cid, "amused", base_dir=base)
    ex.create_set(uid, set_payload(cid), base_dir=base)
    with pytest.raises(ex.ExpressionError):
        ex.select_expression(uid, chat_id, cid, "ghost", base_dir=base)
    with pytest.raises(ex.ExpressionError):
        ex.select_expression(uid, chat_id, cid, "amused",
                             source="telepathy", base_dir=base)
    assert ex.current_expression(uid, chat_id, base_dir=base) is None


def test_clear_selection_records_the_clearing(tmp_path):
    uid, cid, chat_id = (str(uuid.uuid4()) for _ in range(3))
    base = tmp_path / "store"
    ex.create_set(uid, set_payload(cid), base_dir=base)
    assert ex.clear_selection(uid, chat_id, base_dir=base) is False
    ex.select_expression(uid, chat_id, cid, "amused", base_dir=base)
    assert ex.clear_selection(uid, chat_id, reason="scene over",
                              base_dir=base) is True
    assert ex.current_expression(uid, chat_id, base_dir=base) is None
    history = ex.list_history(uid, chat_id=chat_id, base_dir=base)
    assert history[0]["cleared"] is True
    assert history[0]["expression"] is None
    assert history[0]["provenance"]["previous_expression"] == "amused"
    assert history[1]["expression"] == "amused"


def test_apply_default_only_when_nothing_current(tmp_path):
    uid, cid, chat_id = (str(uuid.uuid4()) for _ in range(3))
    base = tmp_path / "store"
    assert ex.apply_default(uid, chat_id, cid, base_dir=base) is None
    ex.create_set(uid, set_payload(cid), base_dir=base)
    applied = ex.apply_default(uid, chat_id, cid, base_dir=base)
    assert applied["expression"] == "neutral"
    assert applied["provenance"]["source"] == "default"
    ex.select_expression(uid, chat_id, cid, "stern", base_dir=base)
    again = ex.apply_default(uid, chat_id, cid, base_dir=base)
    assert again["expression"] == "stern"


def test_history_is_newest_first_and_chat_filtered(tmp_path):
    uid, cid = str(uuid.uuid4()), str(uuid.uuid4())
    chat_a, chat_b = str(uuid.uuid4()), str(uuid.uuid4())
    base = tmp_path / "store"
    ex.create_set(uid, set_payload(cid), base_dir=base)
    ex.select_expression(uid, chat_a, cid, "amused", base_dir=base)
    ex.select_expression(uid, chat_b, cid, "stern", base_dir=base)
    ex.select_expression(uid, chat_a, cid, "neutral", base_dir=base)
    all_rows = ex.list_history(uid, base_dir=base)
    assert [r["expression"] for r in all_rows] == ["neutral", "stern", "amused"]
    a_rows = ex.list_history(uid, chat_id=chat_a, base_dir=base)
    assert [r["expression"] for r in a_rows] == ["neutral", "amused"]


# -- Asset binding / derivation (async, P-023 roads) ------------------------------


async def _add_asset(factory, uid, cid, *, kind, name):
    async with factory() as session:
        asset = await assets_svc.add_asset(
            session, uid, cid, kind=kind, name=name,
            filename=f"{name.replace(' ', '_')}.png", data=PNG_BYTES)
        return asset.id


async def test_binding_report_states_each_problem_honestly(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    bound_id = await _add_asset(factory, uid, cid, kind="expression",
                                name="amused")
    bg_id = await _add_asset(factory, uid, cid, kind="background",
                             name="stairs")
    ex.create_set(uid, {
        "character_id": cid,
        "entries": [
            {"name": "amused", "asset_id": bound_id},
            {"name": "calm"},
            {"name": "lost", "asset_id": str(uuid.uuid4())},
            {"name": "wrong", "asset_id": bg_id},
        ],
        "default": "amused",
    })
    async with factory() as session:
        report = await ex.binding_report(session, uid, cid)
    assert report["bound_count"] == 1 and report["entry_count"] == 4
    by_name = {row["entry"]["name"]: row for row in report["entries"]}
    assert by_name["amused"]["bound"] is True
    assert by_name["amused"]["asset"]["kind"] == "expression"
    assert by_name["calm"]["problem"] == "no_asset"
    assert by_name["lost"]["problem"] == "asset_missing"
    assert by_name["wrong"]["problem"] == "wrong_kind"
    async with factory() as session:
        missing = await ex.binding_report(session, uid, str(uuid.uuid4()))
    assert missing is None


async def test_binding_report_not_stored_asset(tmp_path):
    from runmal.db.models import CharacterAsset

    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    async with factory() as session:
        row = CharacterAsset(
            character_id=cid, user_id=uid, kind="expression", name="far",
            source_type="card", source_uri="https://example.invalid/far.png",
            source_ext="png", status="external_unfetched", detail="",
            format="", media_type="", width=None, height=None,
            byte_size=0, sha256="", storage_relpath=None,
            thumbnail_relpath=None, thumbnail_status="not_applicable")
        session.add(row)
        await session.commit()
        asset_id = row.id
    ex.create_set(uid, {"character_id": cid, "default": None,
                        "entries": [{"name": "far", "asset_id": asset_id}]})
    async with factory() as session:
        report = await ex.binding_report(session, uid, cid)
    assert report["entries"][0]["problem"] == "not_stored"
    assert report["entries"][0]["bound"] is False


async def test_derive_set_from_assets_is_a_draft_never_saved(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    await _add_asset(factory, uid, cid, kind="expression", name="Amused Face")
    await _add_asset(factory, uid, cid, kind="expression", name="amused-face")
    await _add_asset(factory, uid, cid, kind="background", name="stairs")
    async with factory() as session:
        draft = await ex.derive_set_from_assets(session, uid, cid)
    assert [e["name"] for e in draft["entries"]] == ["amused_face", "amused_face-2"]
    assert draft["default"] == "amused_face"
    assert all(e["asset_id"] for e in draft["entries"])
    assert ex.get_set(uid, cid) is None
    saved = ex.create_set(uid, draft)
    assert saved["default"] == "amused_face"
    async with factory() as session:
        assert await ex.derive_set_from_assets(
            session, uid, str(uuid.uuid4())) is None


async def test_select_for_chat_and_inspect_state(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    chat_id = await seed_chat(factory, uid, cid)
    asset_id = await _add_asset(factory, uid, cid, kind="expression",
                                name="amused")
    payload = set_payload(cid)
    payload["entries"][1]["asset_id"] = asset_id
    ex.create_set(uid, payload)
    async with factory() as session:
        selection = await ex.select_for_chat(session, uid, chat_id, "amused")
        state = await ex.inspect_state(session, uid, chat_id)
    assert selection["character_id"] == cid
    assert state["current"]["expression"] == "amused"
    assert state["current_binding"]["bound"] is True
    assert state["set"]["default"] == "neutral"
    assert state["entry_count"] == 3 and state["bound_count"] == 1


async def test_chat_roads_missing_and_unbound(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    cid = await seed_character(factory, uid)
    bound_chat = await seed_chat(factory, uid, cid)
    unbound_chat = await seed_chat(factory, uid, None)
    async with factory() as session:
        assert await ex.select_for_chat(
            session, uid, str(uuid.uuid4()), "amused") is None
        assert await ex.inspect_state(
            session, uid, str(uuid.uuid4())) is None
        with pytest.raises(ex.ExpressionError):
            await ex.select_for_chat(session, uid, unbound_chat, "amused")
        with pytest.raises(ex.ExpressionError):
            await ex.select_for_chat(session, uid, bound_chat, "amused")
        state = await ex.inspect_state(session, uid, unbound_chat)
    assert state["character_id"] is None and state["current"] is None


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


def test_http_set_select_inspect_flow(tmp_path, monkeypatch):
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
    draft = client.post(f"/api/v1/expressions/sets/{cid}/derive")
    assert draft.status_code == 200, draft.text
    assert draft.json()["entries"][0]["asset_id"] == asset_id
    made = client.post("/api/v1/expressions/sets", json={
        "character_id": cid,
        "entries": [{"name": "neutral"},
                    {"name": "amused", "asset_id": asset_id}],
        "default": "neutral"})
    assert made.status_code == 201, made.text
    dup = client.post("/api/v1/expressions/sets",
                      json={"character_id": cid, "entries": []})
    assert dup.status_code == 422
    unknown_char = client.post("/api/v1/expressions/sets", json={
        "character_id": str(uuid.uuid4()), "entries": []})
    assert unknown_char.status_code == 404
    bindings = client.get(f"/api/v1/expressions/sets/{cid}/bindings")
    assert bindings.json()["bound_count"] == 1
    chat = client.post("/api/v1/chats",
                       json={"title": "T", "character_id": cid})
    assert chat.status_code in (200, 201), chat.text
    chat_id = chat.json()["id"]
    picked = client.post("/api/v1/expressions/select",
                         json={"chat_id": chat_id, "name": "amused",
                               "reason": "a joke landed"})
    assert picked.status_code == 200, picked.text
    assert picked.json()["provenance"]["reason"] == "a joke landed"
    ghost = client.post("/api/v1/expressions/select",
                        json={"chat_id": chat_id, "name": "ghost"})
    assert ghost.status_code == 422
    current = client.get("/api/v1/expressions/current",
                         params={"chat_id": chat_id})
    assert current.json()["expression"] == "amused"
    state = client.get("/api/v1/expressions/inspect",
                       params={"chat_id": chat_id})
    assert state.json()["current_binding"]["bound"] is True
    history = client.get("/api/v1/expressions/history",
                         params={"chat_id": chat_id})
    assert history.json()[0]["expression"] == "amused"
    cleared = client.post("/api/v1/expressions/clear",
                          json={"chat_id": chat_id})
    assert cleared.status_code == 200
    gone = client.get("/api/v1/expressions/current",
                      params={"chat_id": chat_id})
    assert gone.status_code == 404
    removed = client.delete(f"/api/v1/expressions/sets/{cid}")
    assert removed.status_code == 200
    missing = client.get(f"/api/v1/expressions/sets/{cid}")
    assert missing.status_code == 404


# -- Neighbours -----------------------------------------------------------------------


def test_migration_head_stays_0041():
    assert MIGRATIONS[-1][0] == "0041"
    assert "0042" not in MIGRATIONS


def test_current_revision_is_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0041"
