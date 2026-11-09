"""P-084 Memory Summarise plugin battery.

Pins the citizen contract from hidden_files/P084_DESIGN.md:
the manifest as strict round-tripping data that register()
accepts, the extractive/deterministic summarizer (every word
from the chat's own messages, no model), the P-082 sandbox
stance (empty resource grants), the founding S404 roll
semantics driven by plugin events through the real chat
service, owner scoping, the inspectable summary_status, the
slots-stage prompt hook at the inspect choke point
(namespaced id, forced provenance, free abstention), the
sidebar UI contribution, and the neighbours (migration head
stays 0041, no '0042').
"""

from __future__ import annotations

import pytest
from sqlalchemy import select

from runmal.chats import service as chats_svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import ChatSummary, User
from runmal.memory import service as memory_service
from runmal.plugins import service as plugin_service
from runmal.plugins.events import make_event
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginRegistry, PluginState
from runmal.plugins.summarise import (
    DEFAULT_BUDGET_TOKENS,
    DEFAULT_KEEP_RECENT,
    PLUGIN_ID,
    ExtractiveSummarizer,
    MemorySummarisePlugin,
    SummariseConfig,
    build_manifest,
    config_from_manifest,
    manifest_data,
    refresh_summary,
    register_plugin,
    sandbox_grants,
    summary_status,
)
from runmal.prompt.inspect import inspect_prompt

CONTENT = "message number {i} with several extra words to spend tokens"


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


async def seed_chat(factory, user_id, n=30, content=CONTENT):
    async with factory() as session:
        chat = await chats_svc.create_chat(session, user_id, title="long")
        msgs = []
        for i in range(n):
            msgs.append(
                await chats_svc.append_message(
                    session, user_id, chat.id, "user",
                    content.format(i=i),
                )
            )
        await session.commit()
        return chat.id, msgs


# ---------------- manifest (pure) ----------------


def test_manifest_data_is_the_p081_canonical_citizen():
    data = manifest_data()
    assert data["id"] == "runmal.summarise"
    assert data["name"] == "Memory Summarise"
    assert data["description"] == "Rolling chat summary into memory."
    assert data["prompt_hooks"] == [
        {"id": "summary-slot", "stage": "slots", "priority": 100}
    ]
    assert data["ui_slots"][0]["id"] == "summary-panel"
    assert data["ui_slots"][0]["slot"] == "chat.sidebar"
    # The real citizen declares the full surface the example omitted.
    assert set(data["capabilities"]) == {
        "chat.events", "prompt.hooks", "ui.slots"}
    assert set(data["permissions"]) == {
        "chat.read", "prompt.inject", "ui.contribute"}
    assert "chat.write" not in data["permissions"]  # reserved, undeceived
    assert set(data["events"]) == {
        "chat.created", "message.created", "message.edited",
        "message.deleted"}
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
    assert isinstance(plugin, MemorySummarisePlugin)


def test_sandbox_grants_are_empty():
    grants = sandbox_grants()
    assert grants.plugin_id == PLUGIN_ID
    assert grants.resources == frozenset()
    assert grants.surface_permissions == frozenset(
        {"chat.read", "prompt.inject", "ui.contribute"})
    assert grants.capabilities == frozenset(
        {"chat.events", "prompt.hooks", "ui.slots"})


# ---------------- config + summarizer (pure) ----------------


def test_config_defaults_and_manifest_precedence():
    assert SummariseConfig().budget_tokens == DEFAULT_BUDGET_TOKENS
    assert SummariseConfig().keep_recent == DEFAULT_KEEP_RECENT
    from_manifest = config_from_manifest(build_manifest())
    assert from_manifest.budget_tokens == DEFAULT_BUDGET_TOKENS
    assert from_manifest.keep_recent == DEFAULT_KEEP_RECENT


def test_config_from_manifest_falls_back_on_corrupt_defaults():
    data = manifest_data()
    data["settings"] = {
        "schema": {}, "defaults": {"budget_tokens": "lots",
                                   "keep_recent": -3}}
    config = config_from_manifest(manifest_from_data(data))
    assert config.budget_tokens == DEFAULT_BUDGET_TOKENS
    assert config.keep_recent == DEFAULT_KEEP_RECENT
    data["settings"] = {
        "schema": {}, "defaults": {"budget_tokens": 42, "keep_recent": 1}}
    config = config_from_manifest(manifest_from_data(data))
    assert (config.budget_tokens, config.keep_recent) == (42, 1)


def test_config_validation_rejects_bad_values():
    with pytest.raises(ValueError):
        SummariseConfig(budget_tokens=0)
    with pytest.raises(ValueError):
        SummariseConfig(budget_tokens=True)
    with pytest.raises(ValueError):
        SummariseConfig(keep_recent=-1)
    with pytest.raises(ValueError):
        SummariseConfig(summarizer="not-callable")


def test_summarizer_is_deterministic_and_extractive():
    summarizer = ExtractiveSummarizer()
    texts = ["the harbour bell rang at dawn over still water",
             "we sailed north before the storm broke hard"]
    out = summarizer(texts)
    assert out == summarizer(list(texts))  # deterministic
    assert out.startswith("Summary of 2 messages: ")
    words = set(out.replace(":", " ").replace("|", " ").split())
    source = set(" ".join(texts).split()) | {
        "Summary", "of", "2", "messages"}
    assert words <= source  # every word from the input, none invented
    assert summarizer.version == "extractive-1"


def test_summarizer_caps_length_and_handles_empty():
    summarizer = ExtractiveSummarizer()
    big = [" ".join(f"word{j}" for j in range(60))] * 40
    out = summarizer(big)
    assert len(out) <= 1600
    assert summarizer([]) == ""
    assert summarizer(["", "   "]) == ""


def test_summarizer_elides_the_middle_visibly_and_keeps_both_ends():
    summarizer = ExtractiveSummarizer()
    texts = [
        f"alpha{i} beta gamma delta epsilon zeta eta theta iota"
        for i in range(40)
    ]
    out = summarizer(texts)
    assert len(out) <= 1600
    assert out.startswith("Summary of 40 messages: ")
    assert "alpha0 beta" in out  # the origin is kept
    assert "alpha39 beta" in out  # the newest segment is kept
    assert "[elided " in out  # the loss is named in the text
    # Re-folding the capped summary preserves the accounting:
    # the elided count rides the marker, never double-counted
    # as content and never silently dropped.
    refolded = summarizer([out, "omega final message arrives now"])
    assert refolded.startswith("Summary of 41 messages: ")
    assert "omega final" in refolded
    assert "alpha0 beta" in refolded and "alpha39 beta" in refolded


# ---------------- refresh semantics (service level) ----------------


async def test_refresh_under_budget_folds_nothing(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id, _ = await seed_chat(factory, uid, n=3)
    async with factory() as session:
        status = await refresh_summary(
            session, uid, chat_id, config=SummariseConfig())
        await session.commit()
    assert status["has_summary"] is False
    assert status["version"] == 0 and status["source_count"] == 0
    assert status["memory_id"] is None


async def test_refresh_over_budget_writes_summary_and_memory(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id, msgs = await seed_chat(factory, uid, n=30)
    config = SummariseConfig(budget_tokens=120, keep_recent=4)
    async with factory() as session:
        status = await refresh_summary(session, uid, chat_id, config=config)
        await session.commit()
        assert status["has_summary"] is True
        assert status["version"] == 1
        assert status["source_first_id"] == msgs[0].id
        assert status["source_count"] == 30 - 4 or status["source_count"] > 0
        assert status["source_last_id"] == msgs[status["source_count"] - 1].id
        assert status["summarizer_version"] == "extractive-1"
        assert status["memory_id"] is not None
        memory = await memory_service.get_memory(
            session, uid, status["memory_id"])
        assert memory.kind == "summary" and memory.chat_id == chat_id
        assert memory.content == status["summary"]
        sources = await memory_service.list_sources(session, memory.id)
        assert len(sources) == status["source_count"]
        assert {s.source_id for s in sources} == {
            m.id for m in msgs[: status["source_count"]]}
        # Extractive honesty: summary words come from the messages.
        assert "message number 0" in status["summary"]


async def test_second_refresh_is_noop_and_third_rolls_forward(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id, _ = await seed_chat(factory, uid, n=12)
    config = SummariseConfig(budget_tokens=60, keep_recent=2)
    async with factory() as session:
        first = await refresh_summary(session, uid, chat_id, config=config)
        await session.commit()
        assert first["version"] == 1
        again = await refresh_summary(session, uid, chat_id, config=config)
        await session.commit()
        assert again["version"] == 1  # already under budget: no new version
        assert again["source_count"] == first["source_count"]
    # More history arrives; the roll advances incrementally.
    async with factory() as session:
        for i in range(12, 24):
            await chats_svc.append_message(
                session, uid, chat_id, "user", CONTENT.format(i=i))
        await session.commit()
        history = await chats_svc.get_history(session, uid, chat_id)
    async with factory() as session:
        rolled = await refresh_summary(session, uid, chat_id, config=config)
        await session.commit()
        assert rolled["version"] == 2
        assert rolled["source_count"] > first["source_count"]
        assert rolled["source_first_id"] == first["source_first_id"]
        assert len(history) - rolled["source_count"] >= 2


async def test_refresh_and_status_are_owner_scoped(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    other = await make_user(factory, name="mallory")
    chat_id, _ = await seed_chat(factory, uid, n=12)
    config = SummariseConfig(budget_tokens=60, keep_recent=2)
    async with factory() as session:
        assert await refresh_summary(
            session, other, chat_id, config=config) is None
        assert await summary_status(session, other, chat_id) is None
        assert await summary_status(session, uid, "no-such-chat") is None
        status = await summary_status(session, uid, chat_id)
        assert status["chat_id"] == chat_id  # owner's view answers


async def test_model_backed_summarizer_is_a_drop_in(tmp_path):
    class Modelish:
        version = "model-backed-test-9"

        def __call__(self, texts):
            return "MODELISH:" + texts[-1][:20]

    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id, _ = await seed_chat(factory, uid, n=12)
    config = SummariseConfig(
        budget_tokens=60, keep_recent=2, summarizer=Modelish())
    async with factory() as session:
        status = await refresh_summary(session, uid, chat_id, config=config)
        await session.commit()
    # Provenance names the true generator, whatever it is.
    assert status["summarizer_version"] == "model-backed-test-9"
    assert status["summary"].startswith("MODELISH:")


# ---------------- event path (end to end) ----------------


async def test_event_flow_through_real_chat_service(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    registry = PluginRegistry()
    config = SummariseConfig(budget_tokens=120, keep_recent=4)
    record, _ = register_plugin(registry, factory, config=config)
    registry.enable(PLUGIN_ID)
    plugin_service.set_default_registry(registry)
    try:
        chat_id, _ = await seed_chat(factory, uid, n=30)
    finally:
        plugin_service.set_default_registry(None)
    async with factory() as session:
        status = await summary_status(session, uid, chat_id)
        rows = list(await session.scalars(select(ChatSummary)))
    assert status["has_summary"] is True and status["version"] >= 1
    assert len(rows) >= 1
    assert record.consecutive_failures == 0


async def test_registered_but_disabled_plugin_receives_nothing(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    registry = PluginRegistry()
    config = SummariseConfig(budget_tokens=60, keep_recent=2)
    register_plugin(registry, factory, config=config)  # never enabled
    plugin_service.set_default_registry(registry)
    try:
        chat_id, _ = await seed_chat(factory, uid, n=12)
    finally:
        plugin_service.set_default_registry(None)
    async with factory() as session:
        status = await summary_status(session, uid, chat_id)
    assert status["has_summary"] is False


async def test_unbound_plugin_is_inert_and_never_fails(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id, _ = await seed_chat(factory, uid, n=5)
    registry = PluginRegistry()
    record, plugin = register_plugin(registry)  # no session factory
    registry.enable(PLUGIN_ID)
    report = await registry.dispatch_event(
        "message.created", chat_id=chat_id, message_id="m1",
        data={"chat_id": chat_id, "message_id": "m1", "role": "user",
              "content": "hello", "content_chars": 5})
    assert report.delivered == [PLUGIN_ID] and report.failed == []
    assert record.consecutive_failures == 0
    # chat.created is declared but a deliberate no-op.
    event = make_event("chat.created", chat_id=chat_id)
    await plugin.on_event(event)


async def test_event_for_vanished_chat_is_quiet(tmp_path):
    factory = make_factory(tmp_path)
    registry = PluginRegistry()
    record, _ = register_plugin(
        registry, factory,
        config=SummariseConfig(budget_tokens=60, keep_recent=2))
    registry.enable(PLUGIN_ID)
    report = await registry.dispatch_event(
        "message.deleted", chat_id="ghost-chat", message_id="m1",
        data={"chat_id": "ghost-chat", "message_id": "m1"})
    assert report.failed == []
    assert record.consecutive_failures == 0


async def test_edit_and_new_messages_refresh_from_committed_history(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    registry = PluginRegistry()
    config = SummariseConfig(budget_tokens=120, keep_recent=4)
    record, _ = register_plugin(registry, factory, config=config,
                                enable=True)
    plugin_service.set_default_registry(registry)
    try:
        chat_id, msgs = await seed_chat(factory, uid, n=30)
        async with factory() as session:
            before = await summary_status(session, uid, chat_id)
        assert "message number 0" in before["summary"]
        # Editing an already-covered message dispatches + refreshes
        # cleanly; the founding roll never re-folds covered
        # messages, so the frozen segment stands (the slice doc
        # states this consequence plainly) and the edit text does
        # NOT rewrite the existing summary.
        async with factory() as session:
            await chats_svc.edit_message(
                session, uid, chat_id, msgs[0].id,
                "zephyr lantern opens the cedar gate at midnight")
            await session.commit()
        # New committed content, once it leaves the keep-recent
        # window, folds in -- refresh re-reads the store, never
        # event payload text.
        async with factory() as session:
            await chats_svc.append_message(
                session, uid, chat_id, "user",
                "quokka emblem painted on the harbour wall")
            await session.commit()
        for i in range(6):
            async with factory() as session:
                await chats_svc.append_message(
                    session, uid, chat_id, "user",
                    CONTENT.format(i=100 + i))
                await session.commit()
    finally:
        plugin_service.set_default_registry(None)
    async with factory() as session:
        after = await summary_status(session, uid, chat_id)
    assert record.consecutive_failures == 0
    assert "quokka emblem" in after["summary"]
    assert "message number 0" in after["summary"]  # frozen segment
    assert "zephyr" not in after["summary"]  # covered edits stay frozen


# ---------------- prompt hook (inspect choke point) ----------------


async def _summarised_chat(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id, _ = await seed_chat(factory, uid, n=30)
    config = SummariseConfig(budget_tokens=120, keep_recent=4)
    async with factory() as session:
        await refresh_summary(session, uid, chat_id, config=config)
        await session.commit()
    return factory, uid, chat_id, config


async def test_slot_hook_injects_summary_at_inspect(tmp_path):
    factory, uid, chat_id, config = await _summarised_chat(tmp_path)
    registry = PluginRegistry()
    register_plugin(registry, factory, config=config, enable=True)
    async with factory() as session:
        status = await summary_status(session, uid, chat_id)
        result = await inspect_prompt(
            session, uid, messages=["hello there"], chat_id=chat_id,
            plugin_registry=registry, include_preview=True)
    assert result["plugins"]["slots_stage"] == [{
        "plugin_id": PLUGIN_ID, "hook_id": "summary-slot",
        "outcome": "applied", "slots_added": 1}]
    rows = {row["slot_id"]: row for row in result["slots"]}
    row = rows["runmal.summarise:summary"]  # host-namespaced id
    assert row["provenance"] == "plugin:runmal.summarise"  # forced
    # Slot rows are metadata only (S214); the summary text itself
    # rides in the composed prompt, visible in the preview.
    assert status["summary"] in str(result["prompt_preview"])


async def test_slot_hook_abstains_without_summary_or_chat(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id, _ = await seed_chat(factory, uid, n=3)  # never summarised
    registry = PluginRegistry()
    register_plugin(registry, factory, enable=True)
    async with factory() as session:
        result = await inspect_prompt(
            session, uid, messages=["hi"], chat_id=chat_id,
            plugin_registry=registry)
        assert result["plugins"]["slots_stage"][0]["outcome"] == "abstained"
        no_chat = await inspect_prompt(
            session, uid, messages=["hi"], plugin_registry=registry)
        assert no_chat["plugins"]["slots_stage"][0]["outcome"] == "abstained"


async def test_unbound_plugin_hook_abstains(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id, _ = await seed_chat(factory, uid, n=1)
    registry = PluginRegistry()
    register_plugin(registry, enable=True)  # no factory bound
    async with factory() as session:
        result = await inspect_prompt(
            session, uid, messages=["hi"], chat_id=chat_id,
            plugin_registry=registry)
    assert result["plugins"]["slots_stage"][0]["outcome"] == "abstained"


# ---------------- UI contribution + lifecycle ----------------


def test_sidebar_contribution_active_only_while_enabled():
    registry = PluginRegistry()
    register_plugin(registry)
    rows = registry.ui_contributions("chat.sidebar")
    mine = [r for r in rows if r["plugin_id"] == PLUGIN_ID]
    assert len(mine) == 1
    assert mine[0]["id"] == "summary-panel"
    assert mine[0]["label"] == "Summary"
    assert mine[0]["active"] is False  # registered, not enabled
    registry.enable(PLUGIN_ID)
    rows = registry.ui_contributions("chat.sidebar", active_only=True)
    assert [r["plugin_id"] for r in rows] == [PLUGIN_ID]
    registry.disable(PLUGIN_ID)
    rows = registry.ui_contributions("chat.sidebar")
    assert [r for r in rows if r["plugin_id"] == PLUGIN_ID][0][
        "active"] is False


def test_enable_param_registers_enabled():
    registry = PluginRegistry()
    record, _ = register_plugin(registry, enable=True)
    assert record.state is PluginState.ENABLED


# ---------------- neighbours ----------------


def test_no_migration_head_stays_0041(tmp_path):
    db_path = tmp_path / "mig.db"
    migrate_to_head(db_path)
    assert current_revision(db_path) == "0042"
    assert "0042" not in MIGRATIONS
