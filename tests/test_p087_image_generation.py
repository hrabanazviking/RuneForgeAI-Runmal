"""P-087 Image Generation plugin battery.

Pins the citizen contract from hidden_files/P087_DESIGN.md:
the manifest as strict round-tripping data that register()
accepts, the P-082 sandbox stance (empty resource grants),
per-chat enablement (generation is explicit, never automatic),
the extractive prompt-from-scene derivation (inspectable
before use, every word from the chat itself), manual prompts,
provider honesty (loopback-only local diffusion through an
injected transport; the deterministic local test road labelled
and reproducible, never disguised), P-023 asset landing for
character-bound chats and the plainly-stated unlanded record
where the stack cannot land, the slots-stage hook at the
inspect choke point, the sidebar UI contribution, and the
neighbours (migration head stays 0041, no '0042').
"""

from __future__ import annotations

import base64

import pytest

from runmal.assets import service as assets_service
from runmal.assets.imaging import make_png_thumbnail, sniff_image
from runmal.characters import service as characters_svc
from runmal.chats import service as chats_svc
from runmal.chats.greetings import GreetingChoice
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.plugins import service as plugin_service
from runmal.plugins.events import make_event
from runmal.plugins.image_generation import (
    PLUGIN_ID,
    ChatNotEnabledError,
    DeterministicImageProvider,
    GeneratedImage,
    ImageGenConfig,
    ImageProviderError,
    ImageRequest,
    LocalDiffusionProvider,
    build_manifest,
    build_provider,
    config_from_manifest,
    derive_scene_prompt,
    generate_image,
    image_status,
    is_loopback_endpoint,
    manifest_data,
    normalise_manual_prompt,
    preview_scene_prompt,
    register_plugin,
    render_deterministic_png,
    sandbox_grants,
)
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginRegistry, PluginState
from runmal.prompt.inspect import inspect_prompt

PNG_BYTES = render_deterministic_png("seed image", "", 1, 32)


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path / "data"))
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


def card_dict(name="Asta"):
    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "name": name,
        "description": "A keeper of the northern lighthouse.",
        "personality": "Steady.",
        "scenario": "A test hall.",
        "first_mes": "Hail!",
        "mes_example": "",
        "creator_notes": "",
        "system_prompt": "",
        "post_history_instructions": "",
        "alternate_greetings": [],
        "tags": [],
        "creator": "forge",
        "character_version": "1.0",
    }


async def seed_chat(factory, uid, with_character=False):
    async with factory() as session:
        character_id = None
        if with_character:
            character = await characters_svc.create_character(session, uid, card_dict())
            character_id = character.id
        chat = await chats_svc.create_chat(
            session,
            uid,
            title="The Lighthouse",
            character_id=character_id,
            greeting=GreetingChoice(mode="quiet"),
        )
        await chats_svc.append_message(
            session, uid, chat.id, "user", "The storm is rising over the black harbour tonight."
        )
        await chats_svc.append_message(
            session, uid, chat.id, "assistant", "Asta lights the great lamp as waves break below."
        )
        await session.commit()
        return chat.id, character_id


class FakeTransport:
    def __init__(self, body, status=200, content_type="application/json"):
        self.body = body
        self.status = status
        self.content_type = content_type
        self.calls = []

    def __call__(self, url, payload, timeout):
        self.calls.append((url, payload, timeout))
        return self.status, self.content_type, self.body


class BadBytesProvider:
    provider_id = "bad-bytes"
    model = "junk-1"
    endpoint = None
    road = "local_diffusion"

    async def generate(self, request):
        return GeneratedImage(
            data=b"not an image at all",
            provider=self.provider_id,
            model=self.model,
            endpoint=None,
            road=self.road,
        )


# -- manifest / registration / sandbox -------------------------------
def test_manifest_data():
    data = manifest_data()
    assert data["id"] == "runmal.image-generation"
    assert set(data["capabilities"]) == {"chat.events", "prompt.hooks", "ui.slots"}
    assert set(data["permissions"]) == {"chat.read", "prompt.inject", "ui.contribute"}
    assert "chat.write" not in data["permissions"]
    assert data["events"] == ["chat.created"]
    assert data["prompt_hooks"] == [{"id": "image-scene", "stage": "slots", "priority": 80}]
    assert data["ui_slots"][0]["slot"] == "chat.sidebar"
    assert data["enabled_by_default"] is False


def test_manifest_roundtrip():
    manifest = build_manifest()
    assert manifest_to_data(manifest) == manifest_data()
    assert manifest_from_data(manifest_to_data(manifest)) == manifest


def test_register_accepts():
    registry = PluginRegistry()
    record, _plugin = register_plugin(registry)
    assert record.state is PluginState.REGISTERED
    assert registry.keys() == [PLUGIN_ID]


def test_sandbox_empty():
    grants = sandbox_grants()
    assert grants.plugin_id == PLUGIN_ID
    assert grants.resources == frozenset()
    assert grants.surface_permissions == frozenset({"chat.read", "prompt.inject", "ui.contribute"})


def test_enable_param():
    registry = PluginRegistry()
    record, _plugin = register_plugin(registry, enable=True)
    assert record.state is PluginState.ENABLED


def test_ui_contribution():
    registry = PluginRegistry()
    register_plugin(registry)
    rows = [r for r in registry.ui_contributions("chat.sidebar") if r["plugin_id"] == PLUGIN_ID]
    assert len(rows) == 1 and rows[0]["id"] == "image-panel"
    assert rows[0]["active"] is False
    registry.enable(PLUGIN_ID)
    active = registry.ui_contributions("chat.sidebar", active_only=True)
    assert [r["plugin_id"] for r in active] == [PLUGIN_ID]


# -- config ----------------------------------------------------------
def test_config_strict():
    assert ImageGenConfig().default_width == 512
    for bad in (
        dict(default_width=10),
        dict(default_height=9999),
        dict(canvas_size=8),
        dict(timeout_seconds=0),
        dict(max_prompt_chars=10),
        dict(endpoint=3),
    ):
        with pytest.raises(ValueError):
            ImageGenConfig(**bad)


def test_config_from_manifest_fallback():
    assert config_from_manifest(build_manifest()).endpoint == ""
    data = manifest_data()
    data["settings"] = {
        "schema": {},
        "defaults": {"default_width": "wide", "endpoint": 5, "model": "sdxl-local"},
    }
    config = config_from_manifest(manifest_from_data(data))
    assert config.default_width == 512 and config.endpoint == ""
    assert config.model == "sdxl-local"
    data["settings"] = {
        "schema": {},
        "defaults": {"endpoint": "http://127.0.0.1:7860/sdapi/v1/txt2img"},
    }
    config = config_from_manifest(manifest_from_data(data))
    assert config.endpoint.endswith("/txt2img")


def test_provider_selection():
    plain = build_provider(ImageGenConfig())
    assert isinstance(plain, DeterministicImageProvider)
    local = build_provider(
        ImageGenConfig(endpoint="http://localhost:7860/sdapi/v1/txt2img", model="m1")
    )
    assert isinstance(local, LocalDiffusionProvider)
    assert local.model == "m1" and local.road == "local_diffusion"


# -- providers -------------------------------------------------------
def test_loopback_refusal():
    assert is_loopback_endpoint("http://127.0.0.1:7860/x")
    assert is_loopback_endpoint("http://localhost:7860/x")
    assert is_loopback_endpoint("http://[::1]:7860/x")
    for bad in (
        "https://api.example.com/x",
        "http://192.168.1.5/x",
        "ftp://127.0.0.1/x",
        "",
        "not-a-url",
    ):
        assert not is_loopback_endpoint(bad)
        with pytest.raises(ValueError):
            LocalDiffusionProvider(bad)


async def test_deterministic_reproducible_and_real_png():
    provider = DeterministicImageProvider(canvas_size=32)
    request = ImageRequest(prompt="a lighthouse in a storm", seed=7)
    first = await provider.generate(request)
    second = await provider.generate(request)
    assert first.data == second.data
    assert first.road == "deterministic_local"
    assert first.provider == "deterministic-local"
    assert first.model == "hash-canvas-1" and first.endpoint is None
    info = sniff_image(first.data)
    assert info.format == "png" and info.width == 32 and info.height == 32
    assert make_png_thumbnail(first.data, 16) is not None
    other = await provider.generate(ImageRequest(prompt="a lighthouse in a storm", seed=8))
    assert other.data != first.data


async def test_local_provider_a1111_shape():
    body = ('{"images": ["' + base64.b64encode(PNG_BYTES).decode() + '"]}').encode()
    transport = FakeTransport(body)
    provider = LocalDiffusionProvider(
        "http://127.0.0.1:7860/sdapi/v1/txt2img", model="sdxl-local", transport=transport
    )
    out = await provider.generate(ImageRequest(prompt="harbour", seed=3))
    assert out.data == PNG_BYTES and out.road == "local_diffusion"
    assert out.model == "sdxl-local"
    assert out.endpoint == "http://127.0.0.1:7860/sdapi/v1/txt2img"
    url, payload, _timeout = transport.calls[0]
    assert url == provider.endpoint and payload["prompt"] == "harbour"
    assert payload["seed"] == 3


async def test_local_provider_raw_bytes_and_failures():
    raw = LocalDiffusionProvider(
        "http://localhost:7860/x", transport=FakeTransport(PNG_BYTES, content_type="image/png")
    )
    out = await raw.generate(ImageRequest(prompt="x"))
    assert out.data == PNG_BYTES
    failing = LocalDiffusionProvider(
        "http://localhost:7860/x", transport=FakeTransport(b"nope", status=500)
    )
    with pytest.raises(ImageProviderError):
        await failing.generate(ImageRequest(prompt="x"))

    def boom(url, payload, timeout):
        raise OSError("connection refused")

    down = LocalDiffusionProvider("http://localhost:7860/x", transport=boom)
    with pytest.raises(ImageProviderError):
        await down.generate(ImageRequest(prompt="x"))
    empty = LocalDiffusionProvider("http://localhost:7860/x", transport=FakeTransport(b"{}"))
    with pytest.raises(ImageProviderError):
        await empty.generate(ImageRequest(prompt="x"))


# -- scene derivation --------------------------------------------------
def test_scene_derivation_pure():
    messages = [
        {
            "role": "user",
            "content": "The storm is rising over the black harbour tonight. We should hurry.",
        },
        {"role": "assistant", "content": "Asta lights the great lamp."},
        {"role": "user", "content": "   "},
    ]
    out = derive_scene_prompt(messages, character_name="Asta", chat_title="Ignored Title")
    assert out["generator"] == "extractive-scene-1"
    assert out["subject"] == "Asta" and out["message_count"] == 2
    assert out["prompt"].startswith("Asta. The storm is rising")
    assert "We should hurry" not in out["prompt"]
    assert out["sources"] == ["user", "assistant"]
    titled = derive_scene_prompt([], chat_title="The Lighthouse")
    assert titled["prompt"] == "The Lighthouse"
    empty = derive_scene_prompt([])
    assert empty["prompt"] == "" and empty["message_count"] == 0
    capped = derive_scene_prompt(messages, character_name="Asta", max_chars=40)
    assert len(capped["prompt"]) <= 40


def test_manual_prompt_normalise():
    assert normalise_manual_prompt("  a   red  boat ") == "a red boat"
    with pytest.raises(ValueError):
        normalise_manual_prompt("   ")
    with pytest.raises(ValueError):
        normalise_manual_prompt("x" * 1001)
    with pytest.raises(ValueError):
        ImageRequest(prompt="  ")


# -- generation over the DB -------------------------------------------
async def test_generate_requires_per_chat_enablement(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id, _ = await seed_chat(factory, uid)
    registry = PluginRegistry()
    _record, plugin = register_plugin(registry, factory, enable=True)
    async with factory() as session:
        with pytest.raises(ChatNotEnabledError):
            await generate_image(session, uid, chat_id, plugin=plugin, prompt="a red boat")
        assert plugin.set_chat_enabled(chat_id) is True
        record = await generate_image(session, uid, chat_id, plugin=plugin, prompt="a red boat")
    assert record["id"] == "gen-0001"
    assert record["prompt_source"] == "manual"
    assert record["road"] == "deterministic_local"
    assert record["provider"] == "deterministic-local"
    assert record["format"] == "png" and record["byte_size"] > 0
    assert record["landed"] is False
    assert record["landing_reason"] == "no_character_bound"
    assert record["asset_id"] is None


async def test_generate_scene_prompt_and_preview(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id, _ = await seed_chat(factory, uid)
    _record, plugin = register_plugin(PluginRegistry(), factory)
    plugin.set_chat_enabled(chat_id)
    async with factory() as session:
        preview = await preview_scene_prompt(session, uid, chat_id, plugin=plugin)
        assert preview["enabled"] is True
        assert "storm is rising" in preview["prompt"]
        assert plugin.history(chat_id) == []
        record = await generate_image(session, uid, chat_id, plugin=plugin)
        assert record["prompt_source"] == "scene"
        assert record["prompt"] == preview["prompt"]
        other = await make_user(factory, "mallory")
        assert await preview_scene_prompt(session, other, chat_id, plugin=plugin) is None
        assert await generate_image(session, other, chat_id, plugin=plugin, prompt="x") is None
        assert await image_status(session, other, chat_id, plugin=plugin) is None


async def test_generate_lands_character_asset(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id, character_id = await seed_chat(factory, uid, with_character=True)
    _record, plugin = register_plugin(PluginRegistry(), factory)
    plugin.set_chat_enabled(chat_id)
    async with factory() as session:
        record = await generate_image(session, uid, chat_id, plugin=plugin)
        assert record["prompt_source"] == "scene"
        assert "Asta" in record["prompt"]
        assert record["landed"] is True
        assert record["landing_reason"] == "character_asset"
        rows = await assets_service.list_assets(session, uid, character_id)
        assert len(rows) == 1
        row = rows[0]
        assert row.id == record["asset_id"] and row.kind == "background"
        assert row.source_type == "upload" and row.format == "png"
        assert row.thumbnail_status == "ready"
        found = assets_service.read_asset_content(character_id, row)
        assert found is not None and found[1] == "image/png"
        assert sniff_image(found[0]).format == "png"


async def test_landing_failure_degrades_honestly(tmp_path, monkeypatch):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id, _cid = await seed_chat(factory, uid, with_character=True)
    _record, plugin = register_plugin(PluginRegistry(), factory)
    plugin.set_chat_enabled(chat_id)

    async def boom(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(assets_service, "add_asset", boom)
    async with factory() as session:
        record = await generate_image(
            session, uid, chat_id, plugin=plugin, prompt="harbour at dusk"
        )
    assert record["landed"] is False
    assert record["landing_reason"] == "landing_failed"
    assert record["landing_error"] == "RuntimeError"
    assert record["asset_id"] is None and record["byte_size"] > 0


async def test_bad_bytes_provider_refused(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id, _ = await seed_chat(factory, uid)
    _record, plugin = register_plugin(PluginRegistry(), factory)
    plugin.bind_provider(BadBytesProvider())
    plugin.set_chat_enabled(chat_id)
    async with factory() as session:
        with pytest.raises(ImageProviderError):
            await generate_image(session, uid, chat_id, plugin=plugin, prompt="anything")
    assert plugin.history(chat_id) == []


async def test_status_and_history(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id, _ = await seed_chat(factory, uid)
    _record, plugin = register_plugin(PluginRegistry(), factory)
    async with factory() as session:
        status = await image_status(session, uid, chat_id, plugin=plugin)
        assert status["enabled"] is False and status["generation_count"] == 0
        assert status["road"] == "deterministic_local"
        plugin.set_chat_enabled(chat_id)
        await generate_image(session, uid, chat_id, plugin=plugin, prompt="one")
        await generate_image(session, uid, chat_id, plugin=plugin, prompt="two", seed=9)
        status = await image_status(session, uid, chat_id, plugin=plugin)
    assert status["enabled"] is True and status["generation_count"] == 2
    assert status["latest"]["prompt"] == "two"
    assert status["latest"]["seed"] == 9
    assert [r["id"] for r in plugin.history(chat_id)] == ["gen-0001", "gen-0002"]
    plugin.set_chat_enabled(chat_id, False)
    assert plugin.is_chat_enabled(chat_id) is False


# -- events + hook ------------------------------------------------------
async def test_events_never_generate(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    registry = PluginRegistry()
    _record, plugin = register_plugin(registry, factory, enable=True)
    plugin_service.set_default_registry(registry)
    try:
        async with factory() as session:
            chat = await chats_svc.create_chat(session, uid, title="Fresh")
            await chats_svc.append_message(session, uid, chat.id, "user", "a scene worth picturing")
            await session.commit()
    finally:
        plugin_service.set_default_registry(None)
    assert plugin.history() == []
    event = make_event("chat.created", chat_id="whatever")
    assert await plugin.on_event(event) is None


async def test_hook_applied_and_abstains(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id, _ = await seed_chat(factory, uid)
    registry = PluginRegistry()
    _record, plugin = register_plugin(registry, factory, enable=True)
    async with factory() as session:
        result = await inspect_prompt(
            session,
            uid,
            messages=["hi"],
            chat_id=chat_id,
            plugin_registry=registry,
            include_preview=True,
        )
        assert result["plugins"]["slots_stage"][0]["outcome"] == "abstained"
        plugin.set_chat_enabled(chat_id)
        await generate_image(session, uid, chat_id, plugin=plugin, prompt="the lamp room")
        result = await inspect_prompt(
            session,
            uid,
            messages=["hi"],
            chat_id=chat_id,
            plugin_registry=registry,
            include_preview=True,
        )
    assert result["plugins"]["slots_stage"][0]["outcome"] == "applied"
    rows = {r["slot_id"]: r for r in result["slots"]}
    key = "runmal.image-generation:generated-image"
    assert rows[key]["provenance"] == "plugin:runmal.image-generation"
    assert "deterministic_local" in str(result["prompt_preview"])
    assert "no_character_bound" in str(result["prompt_preview"])


# -- neighbours ----------------------------------------------------------
def test_no_migration():
    assert "0042" not in MIGRATIONS


async def test_migration_head(tmp_path):
    db_path = tmp_path / "mig.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
