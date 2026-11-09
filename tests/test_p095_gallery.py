"""P-095 The gallery plugin battery.

Pins the contract from hidden_files/P095_DESIGN.md: the
citizen manifest as strict round-tripping data, the P-082
empty-grant stance, the durable per-owner gallery store
(owner isolation, corrupt-store refusal, strict entry
re-validation), P-087 generation-history preservation
(provenance verbatim, the deterministic road labelled,
idempotent sync, unlanded records stated plainly), the
asset-derived road through P-023 (bytes never copied,
wrong-character and unbound refusals), the attached road
(P-023 landing for bound chats, the labelled gallery_local
byte store for unbound chats, non-image refusal), curation
(title/notes only; provenance immutable), removal custody
(local bytes removed, P-023 assets untouched), the enriched
gallery view (thumbnail facts live from P-023, missing asset
stated plainly), the pull-based generation import through a
bound P-087 citizen, and the neighbours (migration head
stays 0041, no 0042).
"""

from __future__ import annotations

import pytest

from runmal.assets import service as assets_service
from runmal.chats import service as chats_svc
from runmal.chats.greetings import GreetingChoice
from runmal.characters import service as characters_svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.plugins import gallery as gal
from runmal.plugins import image_generation as igen
from runmal.plugins import service as plugin_service
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginRegistry, PluginState

PNG_BYTES = igen.render_deterministic_png("gallery seed", "", 1, 32)


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


def gen_record(chat_id, **over):
    record = {
        "id": "gen-0001", "chat_id": chat_id,
        "prompt": "a red boat under northern lights",
        "prompt_source": "manual", "negative_prompt": "", "seed": 7,
        "width": 512, "height": 512,
        "provider": "deterministic-local", "model": "hash-canvas-1",
        "endpoint": None, "road": "deterministic_local",
        "format": "png", "image_width": 64, "image_height": 64,
        "byte_size": 1234, "sha256": "a" * 64,
        "asset_id": None, "landed": False,
        "landing_reason": "no_character_bound", "landing_error": "",
    }
    record.update(over)
    return record


# -- Citizen / manifest ------------------------------------------------------


def test_manifest_round_trips_and_registers():
    data = gal.manifest_data()
    manifest = manifest_from_data(data)
    assert manifest_to_data(manifest) == data
    assert manifest.id == gal.PLUGIN_ID == "runmal.gallery"
    assert "chat.write" not in manifest.permissions
    assert data["prompt_hooks"] == []
    registry = PluginRegistry()
    record, _plugin = gal.register_plugin(registry)
    assert record.state == PluginState.REGISTERED
    assert registry.get(gal.PLUGIN_ID).manifest.id == gal.PLUGIN_ID


def test_register_enable():
    registry = PluginRegistry()
    record, _plugin = gal.register_plugin(registry, enable=True)
    assert record.state == PluginState.ENABLED


def test_sandbox_grants_are_empty():
    grants = gal.sandbox_grants()
    assert grants.resources == frozenset()


def test_ui_contribution_is_sidebar_panel():
    registry = PluginRegistry()
    gal.register_plugin(registry)
    rows = [r for r in registry.ui_contributions("chat.sidebar")
            if r["plugin_id"] == gal.PLUGIN_ID]
    assert len(rows) == 1
    assert rows[0]["payload"]["route"] == "chat-gallery"


async def test_event_handler_abstains_and_clears_nothing(tmp_path):
    uid = str(__import__("uuid").uuid4())
    chat_id = str(__import__("uuid").uuid4())
    gal.record_generation(uid, chat_id, gen_record(chat_id), base_dir=tmp_path)
    _record, plugin = gal.register_plugin(PluginRegistry(), base_dir=tmp_path)
    from runmal.plugins.events import make_event
    await plugin.on_event(make_event("chat.created", chat_id=chat_id))
    assert len(gal.list_entries(uid, chat_id, base_dir=tmp_path)) == 1


# -- Generation history preservation ------------------------------------------


def test_record_generation_preserves_provenance(tmp_path):
    import uuid as _uuid
    uid, chat_id = str(_uuid.uuid4()), str(_uuid.uuid4())
    entry = gal.record_generation(uid, chat_id, gen_record(chat_id), base_dir=tmp_path)
    assert entry["id"] == "gal-0001"
    assert entry["source_kind"] == "generated"
    assert entry["generation_id"] == "gen-0001"
    assert entry["road"] == "deterministic_local"
    assert entry["provider"] == "deterministic-local"
    assert entry["model"] == "hash-canvas-1"
    assert entry["prompt_source"] == "manual"
    assert entry["storage"] == "none"
    assert entry["asset_id"] is None
    assert "no_character_bound" in entry["notes"]
    history = gal.generation_history(uid, chat_id, base_dir=tmp_path)
    assert [row["id"] for row in history] == ["gal-0001"]


def test_record_generation_landed_carries_asset(tmp_path):
    import uuid as _uuid
    uid, chat_id, asset_id = (str(_uuid.uuid4()) for _ in range(3))
    entry = gal.record_generation(
        uid, chat_id,
        gen_record(chat_id, asset_id=asset_id, landed=True,
                   landing_reason="character_asset", road="local_diffusion",
                   provider="local-diffusion", model="sdxl-local"),
        base_dir=tmp_path)
    assert entry["storage"] == "asset"
    assert entry["asset_id"] == asset_id
    assert entry["road"] == "local_diffusion"
    assert entry["notes"] == ""


def test_record_generation_is_idempotent(tmp_path):
    import uuid as _uuid
    uid, chat_id = str(_uuid.uuid4()), str(_uuid.uuid4())
    first = gal.record_generation(uid, chat_id, gen_record(chat_id), base_dir=tmp_path)
    again = gal.record_generation(uid, chat_id, gen_record(chat_id), base_dir=tmp_path)
    assert again["id"] == first["id"]
    assert len(gal.list_entries(uid, chat_id, base_dir=tmp_path)) == 1


def test_sync_reports_added_and_skipped(tmp_path):
    import uuid as _uuid
    uid, chat_id = str(_uuid.uuid4()), str(_uuid.uuid4())
    records = [gen_record(chat_id),
               gen_record(chat_id, id="gen-0002", sha256="b" * 64)]
    report = gal.sync_generation_history(uid, chat_id, records, base_dir=tmp_path)
    assert len(report["added"]) == 2 and report["skipped"] == 0
    report2 = gal.sync_generation_history(uid, chat_id, records, base_dir=tmp_path)
    assert report2["added"] == [] and report2["skipped"] == 2


def test_record_generation_refusals(tmp_path):
    import uuid as _uuid
    uid, chat_id, other = (str(_uuid.uuid4()) for _ in range(3))
    with pytest.raises(gal.GalleryError):
        gal.record_generation(uid, chat_id, gen_record(other), base_dir=tmp_path)
    with pytest.raises(gal.GalleryError):
        gal.record_generation(uid, chat_id, gen_record(chat_id, road=""), base_dir=tmp_path)
    with pytest.raises(gal.GalleryError):
        gal.record_generation(uid, chat_id, gen_record(chat_id, sha256="zz"), base_dir=tmp_path)
    assert gal.list_entries(uid, chat_id, base_dir=tmp_path) == []


# -- Store discipline ----------------------------------------------------------


def test_owner_isolation_and_bad_ids(tmp_path):
    import uuid as _uuid
    uid, other, chat_id = (str(_uuid.uuid4()) for _ in range(3))
    gal.record_generation(uid, chat_id, gen_record(chat_id), base_dir=tmp_path)
    assert gal.list_entries(other, chat_id, base_dir=tmp_path) == []
    with pytest.raises(gal.GalleryError):
        gal.list_entries("not-a-uuid", chat_id, base_dir=tmp_path)
    with pytest.raises(gal.GalleryError):
        gal.list_entries(uid, chat_id, source_kind="bogus", base_dir=tmp_path)


def test_corrupt_store_raises_never_resets(tmp_path):
    import uuid as _uuid
    uid, chat_id = str(_uuid.uuid4()), str(_uuid.uuid4())
    gal.record_generation(uid, chat_id, gen_record(chat_id), base_dir=tmp_path)
    path = gal.store_path(uid, tmp_path)
    path.write_text("{not json", encoding="utf-8")
    with pytest.raises(gal.GalleryError):
        gal.list_entries(uid, chat_id, base_dir=tmp_path)
    path.write_text('{"schema": "other", "counter": 0, "chats": {}}', encoding="utf-8")
    with pytest.raises(gal.GalleryError):
        gal.list_entries(uid, chat_id, base_dir=tmp_path)


def test_update_entry_curates_without_touching_provenance(tmp_path):
    import uuid as _uuid
    uid, chat_id = str(_uuid.uuid4()), str(_uuid.uuid4())
    entry = gal.record_generation(uid, chat_id, gen_record(chat_id), base_dir=tmp_path)
    updated = gal.update_entry(uid, chat_id, entry["id"], title="The Boat",
                               notes="kept", base_dir=tmp_path)
    assert updated["title"] == "The Boat" and updated["notes"] == "kept"
    assert updated["road"] == entry["road"]
    assert updated["sha256"] == entry["sha256"]
    with pytest.raises(gal.GalleryNotFoundError):
        gal.update_entry(uid, chat_id, "gal-9999", title="x", base_dir=tmp_path)
    with pytest.raises(gal.GalleryError):
        gal.update_entry(uid, chat_id, entry["id"], title="x" * 121, base_dir=tmp_path)


def test_summary_counts_by_source_and_road(tmp_path):
    import uuid as _uuid
    uid, chat_id = str(_uuid.uuid4()), str(_uuid.uuid4())
    gal.record_generation(uid, chat_id, gen_record(chat_id), base_dir=tmp_path)
    gal.record_generation(uid, chat_id, gen_record(
        chat_id, id="gen-0002", sha256="c" * 64, road="local_diffusion"),
        base_dir=tmp_path)
    summary = gal.gallery_summary(uid, chat_id, base_dir=tmp_path)
    assert summary["entry_count"] == 2
    assert summary["generation_count"] == 2
    assert summary["by_road"] == {"deterministic_local": 1, "local_diffusion": 1}
    assert summary["total_bytes"] == 2468


def test_clear_gallery_is_the_explicit_verb(tmp_path):
    import uuid as _uuid
    uid, chat_id = str(_uuid.uuid4()), str(_uuid.uuid4())
    gal.record_generation(uid, chat_id, gen_record(chat_id), base_dir=tmp_path)
    assert gal.clear_gallery(uid, chat_id, base_dir=tmp_path) == 1
    assert gal.list_entries(uid, chat_id, base_dir=tmp_path) == []
    assert gal.clear_gallery(uid, chat_id, base_dir=tmp_path) == 0


# -- Asset-derived and attached roads -------------------------------------------


async def test_attach_asset_binds_bound_character_asset(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    character_id = await seed_character(factory, uid)
    chat_id = await seed_chat(factory, uid, character_id)
    async with factory() as session:
        row = await assets_service.add_asset(
            session, uid, character_id, kind="background", name="harbour",
            filename="harbour.png", data=PNG_BYTES)
        entry = await gal.attach_asset(session, uid, chat_id, row.id, title="Harbour")
    assert entry["source_kind"] == "asset"
    assert entry["road"] == gal.ROAD_ASSET_DERIVED
    assert entry["storage"] == "asset"
    assert entry["asset_id"] == row.id
    assert entry["sha256"] == row.sha256
    assert entry["format"] == "png"


async def test_attach_asset_refusals(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    character_id = await seed_character(factory, uid)
    other_character = await seed_character(factory, uid, name="Bera")
    bound_chat = await seed_chat(factory, uid, character_id)
    unbound_chat = await seed_chat(factory, uid, None)
    async with factory() as session:
        row = await assets_service.add_asset(
            session, uid, other_character, kind="background", name="x",
            filename="x.png", data=PNG_BYTES)
        with pytest.raises(gal.GalleryError):
            await gal.attach_asset(session, uid, bound_chat, row.id)
        with pytest.raises(gal.GalleryError):
            await gal.attach_asset(session, uid, unbound_chat, row.id)
        missing = "12345678-1234-1234-1234-123456789012"
        assert await gal.attach_asset(session, uid, missing, row.id) is None


async def test_attach_image_bound_chat_lands_via_p023(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    character_id = await seed_character(factory, uid)
    chat_id = await seed_chat(factory, uid, character_id)
    async with factory() as session:
        entry = await gal.attach_image(
            session, uid, chat_id, filename="boat.png", data=PNG_BYTES)
        assert entry["source_kind"] == "attached"
        assert entry["road"] == gal.ROAD_ATTACHED_ASSET
        assert entry["storage"] == "asset" and entry["asset_id"]
        rows = await assets_service.list_assets(session, uid, character_id)
        assert any(r.id == entry["asset_id"] for r in rows)


async def test_attach_image_unbound_chat_uses_labelled_local_store(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid, None)
    base = tmp_path / "store"
    async with factory() as session:
        entry = await gal.attach_image(
            session, uid, chat_id, filename="boat.png", data=PNG_BYTES,
            base_dir=base)
    assert entry["storage"] == "gallery_local"
    assert entry["road"] == "attached_local"
    assert entry["asset_id"] is None
    view_path = gal._local_bytes_path(uid, chat_id, entry["sha256"], "png", base_dir=base)
    assert view_path.is_file() and view_path.read_bytes() == PNG_BYTES
    removed = gal.remove_entry(uid, chat_id, entry["id"], base_dir=base)
    assert removed["id"] == entry["id"]
    assert not view_path.exists()


async def test_attach_image_refuses_non_image_and_missing_chat(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid, None)
    async with factory() as session:
        with pytest.raises(gal.GalleryError):
            await gal.attach_image(session, uid, chat_id, filename="x.png",
                                   data=b"definitely not an image")
        missing = "12345678-1234-1234-1234-123456789012"
        assert await gal.attach_image(session, uid, missing, filename="b.png",
                                      data=PNG_BYTES) is None
    assert gal.list_entries(uid, chat_id) == []


async def test_remove_generated_entry_keeps_p023_asset(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    character_id = await seed_character(factory, uid)
    chat_id = await seed_chat(factory, uid, character_id)
    async with factory() as session:
        entry = await gal.attach_image(
            session, uid, chat_id, filename="boat.png", data=PNG_BYTES)
        gal.remove_entry(uid, chat_id, entry["id"])
        rows = await assets_service.list_assets(session, uid, character_id)
        assert any(r.id == entry["asset_id"] for r in rows)


# -- View and P-087 import -------------------------------------------------------


async def test_gallery_view_enriches_from_p023(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    character_id = await seed_character(factory, uid)
    chat_id = await seed_chat(factory, uid, character_id)
    async with factory() as session:
        entry = await gal.attach_image(
            session, uid, chat_id, filename="boat.png", data=PNG_BYTES)
        view = await gal.gallery_view(session, uid, chat_id)
        assert view["plugin_id"] == gal.PLUGIN_ID
        assert view["character_id"] == character_id
        assert view["summary"]["entry_count"] == 1
        shown = view["entries"][0]
        assert shown["id"] == entry["id"]
        assert shown["asset_state"] == "stored"
        assert shown["has_thumbnail"] is True
        missing = "12345678-1234-1234-1234-123456789012"
        assert await gal.gallery_view(session, uid, missing) is None


async def test_gallery_view_states_missing_asset_plainly(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    character_id = await seed_character(factory, uid)
    chat_id = await seed_chat(factory, uid, character_id)
    import uuid as _uuid
    ghost = str(_uuid.uuid4())
    gal.record_generation(uid, chat_id, gen_record(
        chat_id, asset_id=ghost, landed=True, landing_reason="character_asset"))
    async with factory() as session:
        view = await gal.gallery_view(session, uid, chat_id)
    shown = view["entries"][0]
    assert shown["asset_state"] == "asset_missing"
    assert shown["has_thumbnail"] is False


async def test_import_from_bound_p087_citizen_preserves_history(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    character_id = await seed_character(factory, uid)
    chat_id = await seed_chat(factory, uid, character_id)
    _rec, igen_plugin = igen.register_plugin(PluginRegistry())
    igen_plugin.set_chat_enabled(chat_id)
    async with factory() as session:
        record = await igen.generate_image(
            session, uid, chat_id, plugin=igen_plugin, prompt="a red boat")
        assert record["road"] == "deterministic_local" and record["landed"] is True
        _grec, gallery_plugin = gal.register_plugin(
            PluginRegistry(), image_plugin=igen_plugin)
        report = await gal.import_chat_generations(
            session, uid, chat_id, plugin=gallery_plugin)
        assert report["added_count"] == 1 and report["skipped"] == 0
        history = report["history"]
        assert history[0]["generation_id"] == record["id"]
        assert history[0]["asset_id"] == record["asset_id"]
        assert history[0]["sha256"] == record["sha256"]
        assert history[0]["storage"] == "asset"
        again = await gal.import_chat_generations(
            session, uid, chat_id, plugin=gallery_plugin)
        assert again["added_count"] == 0 and again["skipped"] == 1


async def test_import_without_wiring_refuses(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid, None)
    async with factory() as session:
        with pytest.raises(gal.GalleryError):
            await gal.import_chat_generations(session, uid, chat_id)


async def test_import_unlanded_generation_states_it_plainly(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await seed_chat(factory, uid, None)
    _rec, igen_plugin = igen.register_plugin(PluginRegistry())
    igen_plugin.set_chat_enabled(chat_id)
    async with factory() as session:
        record = await igen.generate_image(
            session, uid, chat_id, plugin=igen_plugin, prompt="open sea")
        assert record["landed"] is False
        report = await gal.import_chat_generations(
            session, uid, chat_id, image_plugin=igen_plugin)
    entry = report["history"][0]
    assert entry["storage"] == "none"
    assert "no_character_bound" in entry["notes"]


# -- Neighbours --------------------------------------------------------------------


def test_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "head.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
    assert "0042" not in MIGRATIONS
