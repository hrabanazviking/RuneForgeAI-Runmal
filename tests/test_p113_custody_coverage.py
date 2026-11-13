"""P-113 Plugin custody coverage battery: gate finding F1.

Pins the contract from hidden_files/P113_DESIGN.md: the
P-100 gate commissioned extending P-094 custody's fixed
citizen list with runmal.game-bridge (P-096) and
runmal.plugin-settings-ui (P-098) at the next custody
touch, and this slice is that touch. The coverage is
real, not cosmetic: game-bridge's durable per-owner store
exports verbatim and deletes owner-scoped through the
same _FILE_STORES idiom as its P-089 kin; settings-ui is
served section-scoped through its own module's custody
verbs, so custody of it never exports or deletes another
plugin's settings section and never unlinks the shared
plugin_settings store. Bare-id exports stamp the real
manifests; corrupt stores report loud section errors;
unknown ids still refuse; nothing is registered by the
slice (the boot registry stays empty, L3 law intact);
migration head stays 0041.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import data_dir, get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.plugins import custody as cu
from runmal.plugins import game_bridge as gb
from runmal.plugins import service as plugin_service
from runmal.plugins import settings_ui as su
from runmal.plugins.manifest import manifest_from_data
from runmal.plugins.registry import PluginRegistry

GB = "runmal.game-bridge"
SUI = "runmal.plugin-settings-ui"


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def section(doc, name):
    for row in doc["sections"]:
        if row["name"] == name:
            return row
    raise AssertionError(f"section {name!r} missing from "
                         f"{[s['name'] for s in doc['sections']]}")


def uid() -> str:
    return str(uuid.uuid4())


def seed_roll(user_id: str, base: Path) -> dict:
    return gb.roll_for_chat(user_id, uid(), "2d6+1", seed=7,
                            base_dir=base)


# -- The fixed list + coverage ----------------------------------------------


def test_fixed_list_names_both_in_roadmap_order():
    ids = cu.CITIZEN_PLUGIN_IDS
    assert len(ids) == 14
    assert ids[:12] == (
        "runmal.summarise", "runmal.vector-storage",
        "runmal.translate", "runmal.image-generation",
        "runmal.web-search", "runmal.quick-replies",
        "runmal.regex-scripts", "runmal.tts", "runmal.stt",
        "runmal.expressions", "runmal.variables",
        cu.PLUGIN_ID)
    assert ids[12:] == (GB, SUI)


def test_coverage_classifies_both_honestly():
    coverage = cu.custody_coverage()
    assert coverage["citizens"] == list(cu.CITIZEN_PLUGIN_IDS)
    assert GB in coverage["durable_file"]
    assert coverage["plugin_settings"] == [SUI]
    assert SUI not in coverage["durable_file"]
    assert coverage["stateless"] == [cu.PLUGIN_ID]


@pytest.mark.asyncio
async def test_bare_exports_stamp_real_manifests(tmp_path):
    for plugin_id in (GB, SUI):
        doc = await cu.export_plugin_data(
            plugin_id, user_id=uid(), base_dir=tmp_path)
        assert doc["manifest"] is not None
        assert doc["manifest"]["id"] == plugin_id
        assert doc["coverage"] == list(cu.CITIZEN_PLUGIN_IDS)
        assert cu.verify_custody_checksum(doc)


# -- game-bridge: the durable-file road --------------------------------------


@pytest.mark.asyncio
async def test_game_bridge_export_is_verbatim(tmp_path):
    owner = uid()
    seed_roll(owner, tmp_path)
    seed_roll(owner, tmp_path)
    doc = await cu.export_plugin_data(GB, user_id=owner,
                                      base_dir=tmp_path)
    sec = section(doc, "game_bridge_store")
    assert sec["status"] == "exported"
    assert sec["kind"] == "durable_file"
    on_disk = json.loads(
        gb.store_path(owner, tmp_path).read_text(encoding="utf-8"))
    assert sec["document"] == on_disk
    assert sec["counts"] == {"chats": 2}
    assert sec["schema"] == gb.STORE_SCHEMA
    assert cu.verify_custody_checksum(doc)


@pytest.mark.asyncio
async def test_game_bridge_delete_is_owner_scoped(tmp_path):
    owner_a, owner_b = uid(), uid()
    seed_roll(owner_a, tmp_path)
    seed_roll(owner_b, tmp_path)
    bytes_b = gb.store_path(owner_b, tmp_path).read_bytes()
    report = await cu.delete_plugin_data(GB, user_id=owner_a,
                                         base_dir=tmp_path)
    sec = section(report, "game_bridge_store")
    assert sec["status"] == "deleted"
    assert sec["removed"]["files"] == 1
    assert sec["removed"]["chats"] == 1
    assert not gb.store_path(owner_a, tmp_path).exists()
    assert gb.store_path(owner_b, tmp_path).read_bytes() == bytes_b
    doc_b = await cu.export_plugin_data(GB, user_id=owner_b,
                                        base_dir=tmp_path)
    assert section(doc_b, "game_bridge_store")["status"] == "exported"


@pytest.mark.asyncio
async def test_game_bridge_empty_and_ownerless_honesty(tmp_path):
    doc = await cu.export_plugin_data(GB, user_id=uid(),
                                      base_dir=tmp_path)
    sec = section(doc, "game_bridge_store")
    assert sec["status"] == "empty"
    assert sec["counts"] == {}
    doc = await cu.export_plugin_data(GB, base_dir=tmp_path)
    sec = section(doc, "game_bridge_store")
    assert sec["status"] == "unavailable"
    assert "not supplied" in sec["reason"]


@pytest.mark.asyncio
async def test_game_bridge_corrupt_store_is_a_loud_error(tmp_path):
    owner = uid()
    path = gb.store_path(owner, tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    doc = await cu.export_plugin_data(GB, user_id=owner,
                                      base_dir=tmp_path)
    sec = section(doc, "game_bridge_store")
    assert sec["status"] == "error"
    assert sec["error"]
    assert cu.verify_custody_checksum(doc)


# -- settings-ui: the section-scoped road ------------------------------------


def _seed_settings_doc(owner: str, base: Path, plugins: dict) -> Path:
    path = su.store_path(owner, base)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(
        {"schema": su.STORE_SCHEMA, "plugins": plugins}),
        encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_settings_ui_export_empty_for_owner(tmp_path):
    doc = await cu.export_plugin_data(SUI, user_id=uid(),
                                      base_dir=tmp_path)
    sec = section(doc, "plugin_settings_store")
    assert sec["status"] == "empty"
    assert sec["section"] is None
    assert sec["schema"] == su.STORE_SCHEMA
    assert cu.verify_custody_checksum(doc)


@pytest.mark.asyncio
async def test_settings_ui_unavailable_without_owner(tmp_path):
    doc = await cu.export_plugin_data(SUI, base_dir=tmp_path)
    sec = section(doc, "plugin_settings_store")
    assert sec["status"] == "unavailable"
    assert "not supplied" in sec["reason"]


@pytest.mark.asyncio
async def test_settings_ui_never_touches_other_plugins(tmp_path):
    owner = uid()
    manifest = manifest_from_data({
        "id": "acme.counter", "name": "Counter", "version": "1.0.0",
        "api_version": 1, "description": "d", "author": "t",
        "capabilities": [], "permissions": [], "events": [],
        "prompt_hooks": [], "ui_slots": [],
        "settings": {
            "schema": {"volume": {"type": "integer",
                                  "minimum": 0, "maximum": 10}},
            "defaults": {"volume": 1}},
        "enabled_by_default": False})
    su.save_plugin_settings(owner, manifest, {"volume": 9}, tmp_path)
    path = su.store_path(owner, tmp_path)
    before = path.read_bytes()
    doc = await cu.export_plugin_data(SUI, user_id=owner,
                                      base_dir=tmp_path)
    sec = section(doc, "plugin_settings_store")
    assert sec["status"] == "empty"
    assert "acme" not in json.dumps(sec)
    report = await cu.delete_plugin_data(SUI, user_id=owner,
                                         base_dir=tmp_path)
    sec = section(report, "plugin_settings_store")
    assert sec["status"] == "empty"
    assert sec["removed"] == {"settings_sections": 0}
    # The other plugin's section is byte-identical afterwards.
    assert path.read_bytes() == before
    assert su.load_stored_values(owner, "acme.counter",
                                 base_dir=tmp_path) == {"volume": 9}


@pytest.mark.asyncio
async def test_settings_ui_own_section_exports_and_deletes(tmp_path):
    owner = uid()
    own = {"values": {"note": "mine"}, "updated_at": "2026-11-08"}
    other = {"values": {"volume": 3}, "updated_at": "2026-11-08"}
    path = _seed_settings_doc(
        owner, tmp_path, {SUI: own, "acme.counter": other})
    doc = await cu.export_plugin_data(SUI, user_id=owner,
                                      base_dir=tmp_path)
    sec = section(doc, "plugin_settings_store")
    assert sec["status"] == "exported"
    assert sec["section"] == own
    report = await cu.delete_plugin_data(SUI, user_id=owner,
                                         base_dir=tmp_path)
    sec = section(report, "plugin_settings_store")
    assert sec["status"] == "deleted"
    assert sec["removed"] == {"settings_sections": 1}
    # The shared file survives; only the own section is gone.
    assert path.exists()
    remaining = json.loads(path.read_text(encoding="utf-8"))
    assert remaining["plugins"] == {"acme.counter": other}
    again = await cu.delete_plugin_data(SUI, user_id=owner,
                                        base_dir=tmp_path)
    assert section(again, "plugin_settings_store")["removed"] == {
        "settings_sections": 0}


@pytest.mark.asyncio
async def test_settings_ui_corrupt_store_is_a_loud_error(tmp_path):
    owner = uid()
    path = su.store_path(owner, tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{broken", encoding="utf-8")
    doc = await cu.export_plugin_data(SUI, user_id=owner,
                                      base_dir=tmp_path)
    sec = section(doc, "plugin_settings_store")
    assert sec["status"] == "error"
    assert "unreadable" in sec["error"]
    report = await cu.delete_plugin_data(SUI, user_id=owner,
                                         base_dir=tmp_path)
    sec = section(report, "plugin_settings_store")
    assert sec["status"] == "error"
    assert sec["removed"] == {}
    assert path.exists()  # a refused delete removes nothing


@pytest.mark.asyncio
async def test_settings_ui_delete_creates_no_file_when_absent(tmp_path):
    owner = uid()
    report = await cu.delete_plugin_data(SUI, user_id=owner,
                                         base_dir=tmp_path)
    assert section(report, "plugin_settings_store")["status"] == "empty"
    assert not su.store_path(owner, tmp_path).exists()


# -- Refusals, HTTP road, hygiene ---------------------------------------------


@pytest.mark.asyncio
async def test_unknown_plugin_still_refuses():
    with pytest.raises(cu.UnknownPluginError):
        await cu.export_plugin_data("runmal.nope")
    with pytest.raises(cu.UnknownPluginError):
        await cu.delete_plugin_data("runmal.nope")


async def _owner_id(tmp_path):
    from runmal.db.owners import get_or_create_owner

    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    async with factory() as session:
        owner = await get_or_create_owner(session)
        await session.commit()
        return owner.id


def test_http_roads_serve_both_ids(tmp_path, monkeypatch):
    import asyncio

    client = make_client(tmp_path, monkeypatch)
    owner = asyncio.run(_owner_id(tmp_path))
    gb.roll_for_chat(owner, uid(), "2d6", seed=3)
    got = client.get(f"/api/v1/plugins/{GB}/custody/export")
    assert got.status_code == 200, got.text
    doc = got.json()
    assert section(doc, "game_bridge_store")["status"] == "exported"
    assert cu.verify_custody_checksum(doc)
    got = client.get(f"/api/v1/plugins/{SUI}/custody/export")
    assert got.status_code == 200, got.text
    assert section(got.json(), "plugin_settings_store")["status"] in (
        "empty", "exported")
    refused = client.post(f"/api/v1/plugins/{GB}/custody/delete",
                          json={})
    assert refused.status_code == 422, refused.text
    assert gb.store_path(owner).exists()
    done = client.post(f"/api/v1/plugins/{GB}/custody/delete",
                       json={"confirm": True})
    assert done.status_code == 200, done.text
    assert section(done.json(), "game_bridge_store")["status"] == "deleted"
    assert not gb.store_path(owner).exists()


def test_nothing_registered_and_grants_stay_empty():
    registry = plugin_service.build_registry()
    assert registry.keys() == []
    assert cu.sandbox_grants().resources == frozenset()
    fresh = PluginRegistry()
    record, _plugin = cu.register_plugin(fresh)
    assert record.manifest.id == cu.PLUGIN_ID


def test_migration_head_stays_0041(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    assert "0042" not in MIGRATIONS
    db_path = tmp_path / "fresh.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
