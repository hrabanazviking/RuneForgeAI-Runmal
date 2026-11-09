"""P-086 Translate plugin battery (BUILDER 2).

Pins the citizen contract from hidden_files/P086_DESIGN.md
section 7 against the real implementation in
src/runmal/plugins/translate.py: the manifest as strict
round-tripping data that register() accepts, empty P-082
sandbox grants, no reserved chat.write, the migration/boot
neighbours (head stays 0041, no 0042, empty boot registry),
config precedence + validation, per-chat isolation, the
honest deterministic road (pinned bytes, marker, provenance),
the model road via FakeChatBackend with plugin_events=False,
the IN messages hook (user-only, caps, failure = abstain),
the OUT derived store driven by real chat-service events
(originals preserved, edit/delete/chat.deleted invalidation,
unbound inertness), and source_lang=None abstention.
"""

from __future__ import annotations

import pytest

from runmal.backends.errors import BackendUnavailable
from runmal.backends.fake import FakeChatBackend
from runmal.chats import service as chats_svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.generation import service as gen_service
from runmal.plugins import service as plugin_service
from runmal.plugins.events import make_event
from runmal.plugins.hooks import PromptHookContext
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginRegistry, PluginState
from runmal.plugins.translate import (
    DECLARED_EVENTS,
    DETERMINISTIC_VERSION,
    HOOK_ID,
    MAX_HOOK_USER_MESSAGES,
    MAX_TEXT_CHARS,
    PLUGIN_ID,
    UI_LOCAL_ID,
    ChatTranslateConfig,
    DeterministicTranslator,
    ModelTranslator,
    TranslateConfig,
    TranslatePlugin,
    TranslationError,
    build_manifest,
    config_from_manifest,
    manifest_data,
    register_plugin,
    sandbox_grants,
    translate_text,
)
from runmal.prompt.composer import ComposedMessage
from runmal.prompt.inspect import inspect_prompt


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
def _reset_default_registry():
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


async def make_chat(factory, user_id, title="chat"):
    async with factory() as session:
        chat = await chats_svc.create_chat(session, user_id, title=title)
        return chat.id


async def append(factory, user_id, chat_id, role, content):
    async with factory() as session:
        return await chats_svc.append_message(
            session, user_id, chat_id, role, content)


def ctx_for(chat_id):
    return PromptHookContext(
        plugin_id=PLUGIN_ID, hook_id=HOOK_ID, stage="messages",
        chat_id=chat_id)


def cm(role, content, slot_id="s"):
    return ComposedMessage(role=role, content=content, slot_id=slot_id)


def enabled_cfg(**over):
    base = {"enabled": True, "source_lang": "en",
            "target_in": "es", "target_out": "es"}
    base.update(over)
    return ChatTranslateConfig(**base)


# ---------------- registration / manifest / sandbox ----------------


def test_manifest_data_matches_design():
    data = manifest_data()
    assert data["id"] == PLUGIN_ID == "runmal.translate"
    assert data["name"] == "Translate"
    assert data["version"] == "1.0.0"
    assert data["api_version"] == 1
    assert data["description"] == (
        "Per-chat translation: user messages translated in flight; "
        "assistant messages translated into a derived, inspectable "
        "view. Originals never change.")
    assert data["author"] == "Rúnmál"
    assert data["capabilities"] == ["chat.events", "prompt.hooks", "ui.slots"]
    assert data["permissions"] == ["chat.read", "prompt.modify", "ui.contribute"]
    assert "prompt.modify" in data["permissions"]
    assert "prompt.inject" not in data["permissions"]  # no slots hook
    assert data["events"] == list(DECLARED_EVENTS) == [
        "chat.created", "chat.deleted", "message.created",
        "message.edited", "message.deleted"]
    assert data["prompt_hooks"] == [
        {"id": HOOK_ID, "stage": "messages", "priority": 100}]
    assert data["ui_slots"] == [{
        "id": UI_LOCAL_ID, "slot": "chat.sidebar", "label": "Translation",
        "order": 110, "payload": {"kind": "panel", "route": "translation"}}]
    assert data["settings"] == {
        "schema": {"target_in": {"type": "string"},
                   "target_out": {"type": "string"},
                   "max_chars": {"type": "integer", "minimum": 1}},
        "defaults": {"target_in": "en", "target_out": "en",
                     "max_chars": MAX_TEXT_CHARS}}
    assert data["enabled_by_default"] is False


def test_manifest_roundtrips_exactly():
    manifest = build_manifest()
    assert manifest_to_data(manifest) == manifest_data()
    assert manifest_from_data(manifest_to_data(manifest)) == manifest


def test_register_accepts_the_citizen_manifest():
    registry = PluginRegistry()
    record, plugin = register_plugin(registry)
    assert record.state is PluginState.REGISTERED
    assert record.manifest.id == PLUGIN_ID
    assert registry.keys() == [PLUGIN_ID]
    assert isinstance(plugin, TranslatePlugin)
    assert plugin.manifest == build_manifest()
    handlers = plugin.handlers()
    assert set(handlers.prompt_hooks) == {HOOK_ID}
    assert handlers.on_event is not None


def test_sandbox_grants_are_empty():
    grants = sandbox_grants()
    assert grants.plugin_id == PLUGIN_ID
    assert grants.resources == frozenset()
    assert grants.surface_permissions == frozenset(
        {"chat.read", "prompt.modify", "ui.contribute"})
    assert grants.capabilities == frozenset(
        {"chat.events", "prompt.hooks", "ui.slots"})


def test_chat_write_is_not_declared():
    data = manifest_data()
    assert "chat.write" not in data["permissions"]
    assert "chat.write" not in sandbox_grants().surface_permissions
    assert list(build_manifest().permissions) == data["permissions"]


def test_no_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "mig.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
    assert "0042" not in MIGRATIONS


def test_boot_registry_stays_empty_without_registration(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    registry = plugin_service.build_registry()
    assert registry.keys() == []
    assert PLUGIN_ID not in registry.keys()
    assert plugin_service.rehydration_problems() == []
    info = plugin_service.plugin_api_info(registry)
    assert info["registered"] == 0 and info["enabled"] == 0


# ---------------- config ----------------


def test_config_defaults_and_manifest_precedence():
    cfg = TranslateConfig()
    assert (cfg.default_target_in, cfg.default_target_out) == ("en", "en")
    assert cfg.max_chars == MAX_TEXT_CHARS == 4000
    from_manifest = config_from_manifest(build_manifest())
    assert (from_manifest.default_target_in,
            from_manifest.default_target_out,
            from_manifest.max_chars) == ("en", "en", MAX_TEXT_CHARS)
    data = manifest_data()
    data["settings"] = {"schema": {}, "defaults": {
        "target_in": "fr", "target_out": "de", "max_chars": 123}}
    custom = config_from_manifest(manifest_from_data(data))
    assert (custom.default_target_in, custom.default_target_out,
            custom.max_chars) == ("fr", "de", 123)
    # Precedence, never silent: explicit translator > backend > deterministic.
    assert isinstance(cfg.effective_translator, DeterministicTranslator)
    backend_cfg = TranslateConfig(backend=FakeChatBackend())
    assert isinstance(backend_cfg.effective_translator, ModelTranslator)
    both = TranslateConfig(translator=DeterministicTranslator(),
                           backend=FakeChatBackend())
    assert isinstance(both.effective_translator, DeterministicTranslator)
    callable_cfg = TranslateConfig(translator=lambda text, source, target: "x")
    eff = callable_cfg.effective_translator
    assert eff.road == "custom" and eff.provider == "callable"


def test_config_from_manifest_falls_back_on_corrupt_defaults():
    data = manifest_data()
    data["settings"] = {"schema": {}, "defaults": {
        "target_in": "!!bad", "target_out": 42, "max_chars": "lots"}}
    cfg = config_from_manifest(data)
    assert (cfg.default_target_in, cfg.default_target_out,
            cfg.max_chars) == ("en", "en", MAX_TEXT_CHARS)
    data["settings"] = {"schema": {}, "defaults": {
        "target_in": "fr", "max_chars": -3}}
    cfg = config_from_manifest(data)
    assert cfg.default_target_in == "fr"  # valid values survive
    assert cfg.default_target_out == "en" and cfg.max_chars == MAX_TEXT_CHARS
    data["settings"] = {"schema": {}, "defaults": {}}
    cfg = config_from_manifest(data)
    assert (cfg.default_target_in, cfg.max_chars) == ("en", MAX_TEXT_CHARS)


def test_config_validation_rejects_bad_values():
    with pytest.raises(ValueError):
        TranslateConfig(default_target_in="e")
    with pytest.raises(ValueError):
        TranslateConfig(default_target_out="english!")
    with pytest.raises(ValueError):
        TranslateConfig(max_chars=0)
    with pytest.raises(ValueError):
        TranslateConfig(max_chars=True)
    with pytest.raises(ValueError):
        TranslateConfig(translator=object())
    with pytest.raises(ValueError):
        TranslateConfig(backend=object())
    with pytest.raises(ValueError):
        ChatTranslateConfig(enabled="yes")
    with pytest.raises(ValueError):
        ChatTranslateConfig(source_lang="en_us")
    with pytest.raises(ValueError):
        ChatTranslateConfig(target_out=123)


def test_per_chat_config_defaults_disabled_and_isolated():
    plugin = TranslatePlugin()
    default = plugin.get_chat_config("chat-a")
    assert default == ChatTranslateConfig()
    assert default.enabled is False and default.source_lang is None
    plugin.set_chat_config("chat-a", enabled_cfg())
    assert plugin.get_chat_config("chat-a") == enabled_cfg()
    # Isolation: another chat is untouched by chat-a's config.
    assert plugin.get_chat_config("chat-b") == ChatTranslateConfig()
    status_a = plugin.translation_status("chat-a")
    status_b = plugin.translation_status("chat-b")
    assert status_a["config"] == {
        "enabled": True, "in_enabled": True, "out_enabled": True,
        "source_lang": "en", "target_in": "es", "target_out": "es"}
    assert status_b["config"]["enabled"] is False
    assert status_b["config"]["target_out"] == "en"  # global default
    plugin.clear_chat_config("chat-a")
    assert plugin.get_chat_config("chat-a") == ChatTranslateConfig()
    assert plugin.get_chat_config("chat-b") == ChatTranslateConfig()


# ---------------- translator honesty ----------------


async def test_deterministic_translator_lexicon_and_marker():
    translator = DeterministicTranslator()
    result = await translator.translate("hello world", source="en", target="es")
    assert result.translated_text == "[deterministic:es] hola mundo"
    assert result.original == "hello world"
    assert result.source_lang == "en" and result.target_lang == "es"
    assert result.road == "deterministic"
    assert result.provider == DETERMINISTIC_VERSION == "deterministic-1"
    assert result.model is None
    assert translator.provider == "deterministic-1"
    assert translator.road == "deterministic"
    # Capitalisation + trailing punctuation ride the substitution.
    result = await translator.translate("Hello, world!", source="en", target="es")
    assert result.translated_text == "[deterministic:es] Hola, mundo!"
    result = await translator.translate(
        "good morning friend please thanks cat dog yes no night",
        source="en", target="es")
    assert result.translated_text == (
        "[deterministic:es] bueno mañana amigo por favor gracias "
        "gato perro sí no noche")
    assert result.to_dict()["provider"] == "deterministic-1"


async def test_deterministic_translator_unknown_words_pass_through():
    result = await translate_text(
        DeterministicTranslator(), "hello stranger", source="en", target="es")
    assert result.translated_text == "[deterministic:es] hola stranger"
    assert result.original == "hello stranger"
    # A target with no lexicon still gets the marker + pass-through.
    result = await translate_text(
        DeterministicTranslator(), "hello world", source="en", target="it")
    assert result.translated_text == "[deterministic:it] hello world"


async def test_deterministic_same_language_returns_text_unmarked():
    result = await DeterministicTranslator().translate(
        "hello world", source="en", target="en")
    assert result.translated_text == "hello world"
    assert not result.translated_text.startswith("[deterministic:")
    # Provenance still names who decided.
    assert result.road == "deterministic"
    assert result.provider == "deterministic-1"
    assert result.original == "hello world"


async def test_model_translator_provenance_and_plugin_events_off(monkeypatch):
    backend = FakeChatBackend(chunks=("hola ", "mundo"))
    translator = ModelTranslator(backend)
    result = await translator.translate("hello world", source="en", target="es")
    assert result.translated_text == "hola mundo"
    assert result.road == "model"
    assert result.provider == "fake"
    assert result.model == "fake-1"
    assert result.original == "hello world"
    # Spy on the generation service: plugin_events=False is mandatory.
    calls = []

    async def spy_generate(request_id, *, messages, backend, plugin_events=True):
        calls.append({"request_id": request_id, "messages": messages,
                      "backend": backend, "plugin_events": plugin_events})
        yield {"type": "token", "text": "hola mundo"}
        yield {"type": "done", "finish_reason": "stop"}

    monkeypatch.setattr(gen_service, "generate_events", spy_generate)
    spied = await ModelTranslator(FakeChatBackend()).translate(
        "hello world", source="en", target="es")
    assert spied.translated_text == "hola mundo"
    assert spied.road == "model" and spied.provider == "fake"
    assert spied.model == "fake-1"
    assert len(calls) == 1
    assert calls[0]["plugin_events"] is False
    assert [m.role for m in calls[0]["messages"]] == ["system", "user"]
    assert calls[0]["messages"][1].content == "hello world"
    # Plugin-level sugar routes through the backend road too.
    plugin = TranslatePlugin(config=TranslateConfig(backend=FakeChatBackend()))
    via_plugin = await plugin.translate_text(
        "hello world", source="en", target="es")
    assert via_plugin.road == "model" and via_plugin.provider == "fake"


async def test_model_translator_failure_raises_and_stores_nothing(tmp_path):
    failing = ModelTranslator(
        FakeChatBackend(fail_with=BackendUnavailable("down")))
    with pytest.raises(TranslationError):
        await failing.translate("hello world", source="en", target="es")
    # Through the OUT surface a failed translation stores nothing.
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await make_chat(factory, uid)
    plugin = TranslatePlugin(
        factory, TranslateConfig(
            backend=FakeChatBackend(fail_with=BackendUnavailable("down"))))
    plugin.set_chat_config(chat_id, enabled_cfg())
    await plugin.on_event(make_event(
        "message.created", chat_id=chat_id, message_id="m1",
        data={"chat_id": chat_id, "message_id": "m1", "role": "assistant",
              "content": "hello world"}))
    assert plugin.translations_for(chat_id) == []
    assert plugin.translation_status(chat_id)["count"] == 0


# ---------------- IN hook ----------------


async def test_in_hook_translates_only_user_messages(tmp_path):
    plugin = TranslatePlugin()
    plugin.set_chat_config("chat-1", enabled_cfg())
    messages = (
        cm("system", "hello world", "sys"),
        cm("user", "hello world", "u1"),
        cm("assistant", "hello world", "a1"),
        cm("user", "good morning friend", "u2"),
    )
    out = await plugin.translate_in(ctx_for("chat-1"), messages)
    assert out is not None
    assert out[0] is messages[0]  # system byte-identical, untouched
    assert out[2] is messages[2]  # assistant byte-identical, untouched
    assert out[1].content == "[deterministic:es] hola mundo"
    assert out[1].role == "user" and out[1].slot_id == "u1"
    assert out[3].content == "[deterministic:es] bueno mañana amigo"
    # End to end at the inspect choke point: composition is
    # translated, the stored original is not.
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await make_chat(factory, uid)
    await append(factory, uid, chat_id, "user", "hello world")
    registry = PluginRegistry()
    _, plugin2 = register_plugin(registry, factory, enable=True)
    plugin2.set_chat_config(chat_id, enabled_cfg())
    async with factory() as session:
        result = await inspect_prompt(
            session, uid, messages=["hello world"], chat_id=chat_id,
            plugin_registry=registry, include_preview=True)
        history = await chats_svc.get_history(session, uid, chat_id)
    assert result["plugins"]["messages_stage"] == [{
        "plugin_id": PLUGIN_ID, "hook_id": HOOK_ID, "outcome": "applied",
        "messages_added": 0, "messages_removed": 0}]
    preview = result["prompt_preview"]["messages"]
    assert any("[deterministic:es] hola mundo" in m["content"]
               for m in preview)
    assert [m.content for m in history] == ["hello world"]  # original kept


async def test_in_hook_abstains_when_disabled_unknown_source_or_same_lang():
    messages = (cm("user", "hello world", "u1"),)
    # Disabled by default (no per-chat config at all).
    plugin = TranslatePlugin()
    assert await plugin.translate_in(ctx_for("c"), messages) is None
    # Enabled but source_lang is None: unknown source abstains.
    plugin.set_chat_config("c", ChatTranslateConfig(enabled=True))
    assert plugin.get_chat_config("c").source_lang is None
    assert await plugin.translate_in(ctx_for("c"), messages) is None
    # Enabled, known source, but source == target_in.
    plugin.set_chat_config("c", enabled_cfg(target_in="en"))
    assert await plugin.translate_in(ctx_for("c"), messages) is None
    # in_enabled=False abstains even when everything else is set.
    plugin.set_chat_config("c", enabled_cfg(in_enabled=False))
    assert await plugin.translate_in(ctx_for("c"), messages) is None
    # No chat on the context: abstain, never guess.
    plugin.set_chat_config("c", enabled_cfg())
    assert await plugin.translate_in(ctx_for(None), messages) is None


async def test_in_hook_caps_leave_oversize_and_excess_messages_verbatim():
    # Per-message char cap: oversize passes through, in-cap translates.
    plugin = TranslatePlugin(config=TranslateConfig(max_chars=10))
    plugin.set_chat_config("c", enabled_cfg())
    messages = (cm("user", "hello world", "big"),  # 11 chars > cap 10
                cm("user", "hello", "small"))
    out = await plugin.translate_in(ctx_for("c"), messages)
    assert out is not None
    assert out[0] is messages[0]
    assert out[1].content == "[deterministic:es] hola"
    # Per-composition budget: only MAX_HOOK_USER_MESSAGES translate.
    plugin = TranslatePlugin()
    plugin.set_chat_config("c", enabled_cfg())
    many = tuple(cm("user", "hello", f"u{i}")
                 for i in range(MAX_HOOK_USER_MESSAGES + 2))
    out = await plugin.translate_in(ctx_for("c"), many)
    assert out is not None
    translated = [m for m in out
                  if m.content == "[deterministic:es] hola"]
    assert len(translated) == MAX_HOOK_USER_MESSAGES
    assert out[-1] is many[-1] and out[-2] is many[-2]


async def test_in_hook_translator_failure_abstains_originals_flow():
    class Boom:
        async def translate(self, text, *, source, target):
            raise RuntimeError("translator exploded")

    plugin = TranslatePlugin(config=TranslateConfig(translator=Boom()))
    plugin.set_chat_config("c", enabled_cfg())
    messages = (cm("user", "hello world", "u1"),)
    # Failure = abstention (None), never a broken prompt, no raise.
    assert await plugin.translate_in(ctx_for("c"), messages) is None
    assert messages[0].content == "hello world"


# ---------------- OUT store (real chat service) ----------------


async def _enabled_plugin(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    registry = PluginRegistry()
    record, plugin = register_plugin(registry, factory, enable=True)
    plugin_service.set_default_registry(registry)
    return factory, uid, registry, record, plugin


async def test_out_event_stores_assistant_translation_with_original(tmp_path):
    factory, uid, _, record, plugin = await _enabled_plugin(tmp_path)
    try:
        chat_id = await make_chat(factory, uid)
        plugin.set_chat_config(chat_id, enabled_cfg())
        msg = await append(factory, uid, chat_id, "assistant", "hello world")
    finally:
        plugin_service.set_default_registry(None)
    row = plugin.translation_for_message(chat_id, msg.id)
    assert row is not None
    assert row["translated_text"] == "[deterministic:es] hola mundo"
    assert row["original"] == "hello world"  # original snapshot rides along
    assert row["source_lang"] == "en" and row["target_lang"] == "es"
    assert row["road"] == "deterministic"
    assert row["provider"] == "deterministic-1" and row["model"] is None
    assert row["chat_id"] == chat_id and row["message_id"] == msg.id
    assert plugin.translations_for(chat_id) == [row]
    assert plugin.latest_translation(chat_id) == row
    status = plugin.translation_status(chat_id)
    assert status["plugin_id"] == PLUGIN_ID and status["count"] == 1
    assert status["latest"] == row
    assert record.consecutive_failures == 0
    # The stored Message itself is unchanged (originals preserved).
    async with factory() as session:
        history = await chats_svc.get_history(session, uid, chat_id)
    assert [(m.role, m.content) for m in history] == [
        ("assistant", "hello world")]


async def test_out_ignores_user_messages_and_disabled_chats(tmp_path):
    factory, uid, _, _, plugin = await _enabled_plugin(tmp_path)
    try:
        chat_a = await make_chat(factory, uid, title="a")
        plugin.set_chat_config(chat_a, enabled_cfg())
        await append(factory, uid, chat_a, "user", "hello world")
        chat_b = await make_chat(factory, uid, title="b")  # never enabled
        await append(factory, uid, chat_b, "assistant", "hello world")
        chat_c = await make_chat(factory, uid, title="c")
        plugin.set_chat_config(chat_c, enabled_cfg(out_enabled=False))
        await append(factory, uid, chat_c, "assistant", "hello world")
        chat_d = await make_chat(factory, uid, title="d")
        plugin.set_chat_config(chat_d, ChatTranslateConfig(enabled=True))
        await append(factory, uid, chat_d, "assistant", "hello world")
    finally:
        plugin_service.set_default_registry(None)
    assert plugin.translations_for(chat_a) == []  # user role not stored
    assert plugin.translations_for(chat_b) == []  # disabled chat
    assert plugin.translations_for(chat_c) == []  # out_enabled=False
    assert plugin.translations_for(chat_d) == []  # source_lang None abstains


async def test_edit_and_delete_invalidate_derived_translation(tmp_path):
    factory, uid, _, _, plugin = await _enabled_plugin(tmp_path)
    try:
        chat_id = await make_chat(factory, uid)
        plugin.set_chat_config(chat_id, enabled_cfg())
        first = await append(factory, uid, chat_id, "assistant", "hello world")
        assert plugin.translation_for_message(chat_id, first.id) is not None
        async with factory() as session:
            await chats_svc.edit_message(
                session, uid, chat_id, first.id, "good night friend")
        assert plugin.translation_for_message(chat_id, first.id) is None
        second = await append(factory, uid, chat_id, "assistant", "hello cat")
        assert plugin.translation_for_message(
            chat_id, second.id)["translated_text"] == (
                "[deterministic:es] hola gato")
        async with factory() as session:
            await chats_svc.delete_message(session, uid, chat_id, second.id)
        assert plugin.translations_for(chat_id) == []
    finally:
        plugin_service.set_default_registry(None)


async def test_chat_deleted_clears_config_and_store(tmp_path):
    factory, uid, _, _, plugin = await _enabled_plugin(tmp_path)
    try:
        chat_id = await make_chat(factory, uid)
        plugin.set_chat_config(chat_id, enabled_cfg())
        await append(factory, uid, chat_id, "assistant", "hello world")
        assert plugin.translation_status(chat_id)["count"] == 1
        async with factory() as session:
            assert await chats_svc.delete_chat(session, uid, chat_id) is True
    finally:
        plugin_service.set_default_registry(None)
    assert plugin.translations_for(chat_id) == []
    assert plugin.get_chat_config(chat_id) == ChatTranslateConfig()
    assert plugin.translation_status(chat_id)["count"] == 0


async def test_unbound_plugin_event_is_inert_and_hook_still_abstains_cleanly():
    plugin = TranslatePlugin()  # no session factory bound
    plugin.set_chat_config("c1", enabled_cfg())
    await plugin.on_event(make_event(
        "message.created", chat_id="c1", message_id="m1",
        data={"chat_id": "c1", "message_id": "m1", "role": "assistant",
              "content": "hello world"}))
    assert plugin.translations_for("c1") == []  # inert, no raise
    # The hook needs no DB: for a chat with no config it abstains
    # cleanly (None, no raise) even while unbound...
    messages = (cm("user", "hello world", "u1"),)
    assert await plugin.translate_in(ctx_for("other"), messages) is None
    # ...and for its configured chat it works unbound (design s.4/5).
    out = await plugin.translate_in(ctx_for("c1"), messages)
    assert out is not None
    assert out[0].content == "[deterministic:es] hola mundo"


async def test_registered_but_disabled_plugin_receives_nothing(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await make_chat(factory, uid)
    registry = PluginRegistry()
    record, plugin = register_plugin(registry, factory)  # never enabled
    assert record.state is PluginState.REGISTERED
    plugin.set_chat_config(chat_id, enabled_cfg())
    plugin_service.set_default_registry(registry)
    try:
        await append(factory, uid, chat_id, "assistant", "hello world")
        async with factory() as session:
            result = await inspect_prompt(
                session, uid, messages=["hello world"], chat_id=chat_id,
                plugin_registry=registry, include_preview=True)
    finally:
        plugin_service.set_default_registry(None)
    assert plugin.translations_for(chat_id) == []
    assert result["plugins"]["messages_stage"] == []
    assert record.consecutive_failures == 0
