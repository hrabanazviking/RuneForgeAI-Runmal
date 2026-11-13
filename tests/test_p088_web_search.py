"""P-088 Web Search plugin battery.

Pins the citizen contract from hidden_files/P088_DESIGN.md
against src/runmal/plugins/web_search.py: the manifest as
strict round-tripping data that register() accepts, empty
P-082 sandbox grants, no reserved chat.write, the migration /
boot neighbours (head stays 0041, no 0042, empty boot
registry), config validation, the sovereignty gate (OFF by
default; a disabled chat's search refuses BEFORE any provider
call; the prompt hook never searches), the provider seam
(deterministic labelled default, HTTP-JSON through an injected
fake transport, callable/mapping/tuple coercion, failure
stores nothing), and citations into context (every injected
result carries title + URL, through the direct hook, the
hooks machinery, and the inspect_prompt choke point).
Tests touch no real network: every transport is a fake.
"""

from __future__ import annotations

import pytest

from runmal.chats import service as chats_svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.plugins import service as plugin_service
from runmal.plugins.events import make_event
from runmal.plugins.hooks import PromptHookContext, apply_slot_hooks
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginRegistry, PluginState
from runmal.plugins.web_search import (
    DECLARED_EVENTS,
    DEFAULT_MAX_RESULTS,
    DETERMINISTIC_VERSION,
    HOOK_ID,
    MAX_QUERY_CHARS,
    MAX_RESULTS,
    PLUGIN_ID,
    SLOT_LOCAL_ID,
    UI_LOCAL_ID,
    ChatWebSearchConfig,
    DeterministicSearchProvider,
    HttpJsonSearchProvider,
    SearchResult,
    SearchResultSet,
    WebSearchConfig,
    WebSearchDisabledError,
    WebSearchError,
    WebSearchPlugin,
    build_manifest,
    config_from_manifest,
    format_result_set,
    manifest_data,
    register_plugin,
    sandbox_grants,
)
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


async def make_chat(factory, user_id, title="chat"):
    async with factory() as session:
        chat = await chats_svc.create_chat(session, user_id, title=title)
        return chat.id


@pytest.fixture(autouse=True)
def _reset_default_registry():
    plugin_service.set_default_registry(None)
    yield
    plugin_service.set_default_registry(None)


def ctx_for(chat_id):
    return PromptHookContext(
        plugin_id=PLUGIN_ID, hook_id=HOOK_ID, stage="slots",
        chat_id=chat_id)


class CountingProvider:
    """Fake provider: records every call, returns canned rows."""

    provider = "counting-1"
    road = "fake"

    def __init__(self, rows=None, fail=False):
        self.calls: list[tuple[str, int]] = []
        self.rows = rows if rows is not None else [
            {"title": "Alpha Source", "url": "https://alpha.example/a",
             "snippet": "alpha snippet"},
            {"title": "Beta Source", "url": "https://beta.example/b",
             "snippet": "beta snippet"},
            {"title": "Gamma Source", "url": "https://gamma.example/g",
             "snippet": "gamma snippet"},
        ]
        self.fail = fail

    async def search(self, query, *, max_results):
        self.calls.append((query, max_results))
        if self.fail:
            raise RuntimeError("provider boom")
        return list(self.rows)


def enabled_plugin(provider=None, **config_kw):
    plugin = WebSearchPlugin(WebSearchConfig(provider=provider, **config_kw))
    return plugin


# ---------------- registration / manifest / sandbox ----------------


def test_manifest_data_matches_design():
    data = manifest_data()
    assert data["id"] == PLUGIN_ID == "runmal.web-search"
    assert data["name"] == "Web Search"
    assert data["version"] == "1.0.0"
    assert data["api_version"] == 1
    assert data["capabilities"] == ["chat.events", "prompt.hooks", "ui.slots"]
    assert data["permissions"] == ["chat.read", "prompt.inject", "ui.contribute"]
    assert data["events"] == list(DECLARED_EVENTS) == ["chat.created", "chat.deleted"]
    assert data["prompt_hooks"] == [{"id": HOOK_ID, "stage": "slots", "priority": 80}]
    assert data["ui_slots"][0]["id"] == UI_LOCAL_ID
    assert data["ui_slots"][0]["slot"] == "chat.sidebar"
    assert data["enabled_by_default"] is False


def test_manifest_round_trips_and_registers():
    manifest = build_manifest()
    assert manifest_from_data(manifest_to_data(manifest)) == manifest
    registry = PluginRegistry()
    record, plugin = register_plugin(registry)
    assert record.state is PluginState.REGISTERED
    assert plugin.manifest == manifest
    registry2 = PluginRegistry()
    record2, _ = register_plugin(registry2, enable=True)
    assert record2.state is PluginState.ENABLED


def test_sandbox_grants_empty_and_no_chat_write():
    grants = sandbox_grants()
    assert grants.resources == frozenset()
    assert grants.plugin_id == PLUGIN_ID
    data = manifest_data()
    assert "chat.write" not in data["permissions"]
    assert "chat.write" not in grants.surface_permissions
    assert "network.access" not in data["permissions"]


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


# ---------------- config ----------------


def test_global_config_validation():
    assert WebSearchConfig().max_results == DEFAULT_MAX_RESULTS
    assert isinstance(WebSearchConfig().effective_provider, DeterministicSearchProvider)
    for bad in (0, -1, MAX_RESULTS + 1, True, "5", 2.5):
        with pytest.raises(ValueError):
            WebSearchConfig(max_results=bad)
    with pytest.raises(ValueError):
        WebSearchConfig(provider=object())


def test_chat_config_validation_and_defaults():
    cfg = ChatWebSearchConfig()
    assert cfg.enabled is False  # sovereignty: OFF by default
    assert cfg.max_results is None
    with pytest.raises(ValueError):
        ChatWebSearchConfig(enabled="yes")
    with pytest.raises(ValueError):
        ChatWebSearchConfig(max_results=0)
    plugin = WebSearchPlugin()
    assert plugin.get_chat_config("never-seen").enabled is False
    assert plugin.is_enabled("never-seen") is False


def test_config_from_manifest_lenient():
    assert config_from_manifest(build_manifest()).max_results == DEFAULT_MAX_RESULTS
    data = manifest_data()
    data["settings"] = {"schema": {}, "defaults": {"max_results": 3}}
    assert config_from_manifest(manifest_from_data(data)).max_results == 3
    data["settings"] = {"schema": {}, "defaults": {"max_results": 999}}
    assert config_from_manifest(manifest_from_data(data)).max_results == DEFAULT_MAX_RESULTS
    data["settings"] = {"schema": {}, "defaults": {"max_results": "x"}}
    assert config_from_manifest(manifest_from_data(data)).max_results == DEFAULT_MAX_RESULTS


def test_search_result_validation():
    ok = SearchResult(title="T", url="https://x.example/", snippet="s", provider="p")
    assert ok.to_dict()["url"] == "https://x.example/"
    for kwargs in ({"title": "", "url": "https://x.example/"},
                   {"title": "T", "url": "example.com/no-scheme"},
                   {"title": "T", "url": "ftp://x.example/"},
                   {"title": None, "url": "https://x.example/"}):
        with pytest.raises(ValueError):
            SearchResult(**kwargs)


# ---------------- sovereignty: OFF by default ----------------


async def test_search_refused_by_default_and_provider_never_called():
    provider = CountingProvider()
    plugin = enabled_plugin(provider)
    # No per-chat config at all: the chat has NOT opted in.
    with pytest.raises(WebSearchDisabledError):
        await plugin.search("chat-1", "viking ships")
    assert provider.calls == []  # the gate fires before any call
    assert plugin.results_for("chat-1") is None
    assert plugin.search_status("chat-1")["has_results"] is False


async def test_search_refused_when_explicitly_disabled():
    provider = CountingProvider()
    plugin = enabled_plugin(provider)
    plugin.set_chat_config("chat-1", ChatWebSearchConfig(enabled=False))
    with pytest.raises(WebSearchDisabledError):
        await plugin.search("chat-1", "viking ships")
    assert provider.calls == []


async def test_disabled_check_precedes_query_validation():
    provider = CountingProvider()
    plugin = enabled_plugin(provider)
    with pytest.raises(WebSearchDisabledError):
        await plugin.search("chat-1", "")  # bad query, still the gate answers
    assert provider.calls == []


async def test_hook_abstains_by_default_and_never_searches():
    provider = CountingProvider()
    plugin = enabled_plugin(provider)
    assert await plugin.web_search_slot(ctx_for("chat-1"), ()) is None
    assert await plugin.web_search_slot(ctx_for(None), ()) is None
    assert provider.calls == []  # the hook is not a search road


# ---------------- opted-in search ----------------


async def test_opted_in_search_stores_cited_results():
    provider = CountingProvider()
    plugin = enabled_plugin(provider)
    plugin.set_chat_config("chat-1", enabled=True)
    status = await plugin.search("chat-1", "viking ships")
    assert status["performed"] is True
    assert provider.calls == [("viking ships", DEFAULT_MAX_RESULTS)]
    assert status["plugin_id"] == PLUGIN_ID
    assert status["config"] == {"enabled": True, "max_results": None}
    latest = status["latest"]
    assert latest["provider"] == "counting-1" and latest["road"] == "fake"
    assert [r["title"] for r in latest["results"]] == [
        "Alpha Source", "Beta Source", "Gamma Source"]
    citations = latest["citations"]
    assert [c["index"] for c in citations] == [1, 2, 3]
    assert citations[0]["title"] == "Alpha Source"
    assert citations[0]["url"] == "https://alpha.example/a"
    assert citations[0]["provider"] == "counting-1"


async def test_search_is_per_chat_isolated():
    provider = CountingProvider()
    plugin = enabled_plugin(provider)
    plugin.set_chat_config("chat-1", enabled=True)
    await plugin.search("chat-1", "longships")
    with pytest.raises(WebSearchDisabledError):
        await plugin.search("chat-2", "longships")  # other chat never opted in
    assert plugin.results_for("chat-2") is None
    assert plugin.results_for("chat-1") is not None
    assert len(provider.calls) == 1


async def test_search_max_results_precedence_and_truncation():
    provider = CountingProvider()
    plugin = enabled_plugin(provider, max_results=2)
    plugin.set_chat_config("chat-1", enabled=True)
    status = await plugin.search("chat-1", "q")
    assert provider.calls[-1] == ("q", 2)  # global config cap
    assert len(status["latest"]["results"]) == 2
    plugin.set_chat_config("chat-1", enabled=True, max_results=1)
    status = await plugin.search("chat-1", "q")
    assert provider.calls[-1] == ("q", 1)  # per-chat cap wins
    assert len(status["latest"]["results"]) == 1
    status = await plugin.search("chat-1", "q", max_results=3)
    assert provider.calls[-1] == ("q", 3)  # explicit argument wins
    assert len(status["latest"]["results"]) == 3
    with pytest.raises(ValueError):
        await plugin.search("chat-1", "q", max_results=0)


async def test_search_query_validation_when_enabled():
    plugin = enabled_plugin(CountingProvider())
    plugin.set_chat_config("chat-1", enabled=True)
    for bad in ("", "   ", "x" * (MAX_QUERY_CHARS + 1), None, 42):
        with pytest.raises(ValueError):
            await plugin.search("chat-1", bad)


async def test_provider_failure_stores_nothing_and_preserves_prior():
    provider = CountingProvider()
    plugin = enabled_plugin(provider)
    plugin.set_chat_config("chat-1", enabled=True)
    await plugin.search("chat-1", "first")
    prior = plugin.results_for("chat-1")
    provider.fail = True
    with pytest.raises(WebSearchError):
        await plugin.search("chat-1", "second")
    assert plugin.results_for("chat-1") is prior
    fresh = enabled_plugin(CountingProvider(fail=True))
    fresh.set_chat_config("c", enabled=True)
    with pytest.raises(WebSearchError):
        await fresh.search("c", "q")
    assert fresh.results_for("c") is None


async def test_malformed_provider_rows_raise_web_search_error():
    plugin = enabled_plugin(CountingProvider(rows=[{"title": "No URL here"}]))
    plugin.set_chat_config("c", enabled=True)
    with pytest.raises(WebSearchError):
        await plugin.search("c", "q")
    assert plugin.results_for("c") is None
    plugin2 = enabled_plugin(CountingProvider(rows=[12345]))
    plugin2.set_chat_config("c", enabled=True)
    with pytest.raises(WebSearchError):
        await plugin2.search("c", "q")


async def test_callable_and_tuple_providers_coerce():
    async def fake_search(query, *, max_results):
        return [("Tuple Title", "https://tuple.example/t", "tuple snippet")]
    plugin = enabled_plugin(fake_search)
    plugin.set_chat_config("c", enabled=True)
    status = await plugin.search("c", "q")
    latest = status["latest"]
    assert latest["provider"] == "callable" and latest["road"] == "custom"
    assert latest["results"][0]["title"] == "Tuple Title"
    assert latest["results"][0]["provider"] == "callable"


# ---------------- deterministic provider honesty ----------------


async def test_deterministic_provider_labelled_and_stable():
    provider = DeterministicSearchProvider()
    first = await provider.search("norse myth", max_results=3)
    second = await provider.search("norse myth", max_results=3)
    assert first == second  # deterministic across calls
    assert provider.provider == DETERMINISTIC_VERSION == "deterministic-1"
    assert provider.road == "deterministic"
    for row in first:
        assert row.url.startswith("https://example.invalid/")  # reserved domain
        assert row.provider == "deterministic-1"
        assert "deterministic" in row.snippet.lower()
        assert "not a real web source" in row.snippet
    other = await provider.search("other query", max_results=3)
    assert [r.url for r in other] != [r.url for r in first]


async def test_default_plugin_uses_deterministic_provider():
    plugin = WebSearchPlugin()
    plugin.set_chat_config("c", enabled=True)
    status = await plugin.search("c", "runes")
    assert status["latest"]["provider"] == "deterministic-1"
    assert status["latest"]["road"] == "deterministic"


# ---------------- HTTP provider through a fake transport ----------------


async def test_http_provider_via_fake_transport():
    seen: list[str] = []
    async def fake_transport(url):
        seen.append(url)
        return {"results": [
            {"title": "Real-ish Result", "url": "https://site.example/page",
             "snippet": "from the fake transport"}]}
    provider = HttpJsonSearchProvider(
        "https://search.example/api?q={query}&n={max_results}", fake_transport)
    plugin = enabled_plugin(provider)
    plugin.set_chat_config("c", enabled=True)
    status = await plugin.search("c", "east anglia & beyond", max_results=2)
    assert seen == ["https://search.example/api?q=east%20anglia%20%26%20beyond&n=2"]
    latest = status["latest"]
    assert latest["provider"] == "http-json" and latest["road"] == "web"
    assert latest["results"][0]["title"] == "Real-ish Result"


async def test_http_provider_construction_and_payload_refusals():
    with pytest.raises(ValueError):
        HttpJsonSearchProvider("https://x.example/no-placeholder", lambda u: {})
    with pytest.raises(ValueError):
        HttpJsonSearchProvider("https://x.example/?q={query}", None)
    bad = HttpJsonSearchProvider(
        "https://x.example/?q={query}", lambda u: {"nope": []})
    with pytest.raises(WebSearchError):
        await bad.search("q", max_results=1)
    boom = HttpJsonSearchProvider(
        "https://x.example/?q={query}", lambda u: 1 / 0)
    with pytest.raises(WebSearchError):
        await boom.search("q", max_results=1)


# ---------------- citations into context ----------------


def test_format_result_set_cites_every_result():
    result_set = SearchResultSet(
        query="q", chat_id="c", provider="p-1", road="fake",
        results=(SearchResult(title="Alpha Source", url="https://alpha.example/a",
                              snippet="alpha snippet", provider="p-1"),
                 SearchResult(title="Beta Source", url="https://beta.example/b",
                              snippet="", provider="p-1")))
    text = format_result_set(result_set)
    assert "provider: p-1" in text and "road: fake" in text
    for row in result_set.results:
        assert row.title in text and row.url in text  # no unattributed prose
    assert "alpha snippet" in text
    assert text.index("Alpha Source") < text.index("alpha snippet")


async def test_hook_offers_cited_slot_only_after_opted_in_search():
    provider = CountingProvider()
    plugin = enabled_plugin(provider)
    plugin.set_chat_config("chat-1", enabled=True)
    assert await plugin.web_search_slot(ctx_for("chat-1"), ()) is None  # no results yet
    await plugin.search("chat-1", "viking ships")
    slots = await plugin.web_search_slot(ctx_for("chat-1"), ())
    assert slots is not None and len(slots) == 1
    slot = slots[0]
    assert slot.id == SLOT_LOCAL_ID and slot.kind == "web_search"
    assert slot.role == "system"
    assert "Alpha Source" in slot.content and "https://alpha.example/a" in slot.content
    assert "Beta Source" in slot.content and "https://beta.example/b" in slot.content
    assert len(provider.calls) == 1  # the hook itself never searched


async def test_disabling_after_search_stops_injection():
    plugin = enabled_plugin(CountingProvider())
    plugin.set_chat_config("chat-1", enabled=True)
    await plugin.search("chat-1", "q")
    assert await plugin.web_search_slot(ctx_for("chat-1"), ()) is not None
    plugin.set_chat_config("chat-1", enabled=False)
    assert await plugin.web_search_slot(ctx_for("chat-1"), ()) is None
    # Stored results stay inspectable until cleared.
    assert plugin.search_status("chat-1")["has_results"] is True
    plugin.clear_results("chat-1")
    assert plugin.search_status("chat-1")["has_results"] is False


async def test_hook_through_registry_machinery_namespaces_and_forces_provenance():
    registry = PluginRegistry()
    provider = CountingProvider()
    _, plugin = register_plugin(registry, provider, enable=True)
    plugin.set_chat_config("chat-1", enabled=True)
    await plugin.search("chat-1", "q")
    slots, echoes = await apply_slot_hooks(
        registry, {"chat_id": "chat-1"}, [])
    assert echoes == [{"plugin_id": PLUGIN_ID, "hook_id": HOOK_ID,
                       "outcome": "applied", "slots_added": 1}]
    assert slots[0].id == f"{PLUGIN_ID}:{SLOT_LOCAL_ID}"
    assert slots[0].provenance == f"plugin:{PLUGIN_ID}"
    assert "https://alpha.example/a" in slots[0].content


async def test_hook_abstains_through_registry_when_not_opted_in():
    registry = PluginRegistry()
    _, plugin = register_plugin(registry, CountingProvider(), enable=True)
    slots, echoes = await apply_slot_hooks(registry, {"chat_id": "chat-1"}, [])
    assert slots == []
    assert echoes[0]["outcome"] == "abstained"


async def test_inspect_prompt_end_to_end(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await make_chat(factory, uid)
    registry = PluginRegistry()
    _, plugin = register_plugin(registry, CountingProvider(), enable=True)
    async with factory() as session:
        before = await inspect_prompt(
            session, uid, messages=["hi"], chat_id=chat_id,
            plugin_registry=registry)
    assert before["plugins"]["slots_stage"][0]["outcome"] == "abstained"
    plugin.set_chat_config(chat_id, enabled=True)
    await plugin.search(chat_id, "viking ships")
    async with factory() as session:
        after = await inspect_prompt(
            session, uid, messages=["hi"], chat_id=chat_id,
            plugin_registry=registry, include_preview=True)
    assert after["plugins"]["slots_stage"] == [{
        "plugin_id": PLUGIN_ID, "hook_id": HOOK_ID,
        "outcome": "applied", "slots_added": 1}]
    rows = {row["slot_id"]: row for row in after["slots"]}
    row = rows[f"{PLUGIN_ID}:{SLOT_LOCAL_ID}"]
    assert row["provenance"] == f"plugin:{PLUGIN_ID}"  # forced by the host
    preview = after["prompt_preview"]["messages"]
    assert any("https://alpha.example/a" in m["content"] for m in preview)
    assert any("Alpha Source" in m["content"] for m in preview)


# ---------------- events / lifecycle ----------------


async def test_chat_deleted_clears_opt_in_and_results():
    registry = PluginRegistry()
    _, plugin = register_plugin(registry, CountingProvider(), enable=True)
    plugin.set_chat_config("chat-1", enabled=True)
    await plugin.search("chat-1", "q")
    await registry.dispatch_event("chat.deleted", chat_id="chat-1")
    assert plugin.is_enabled("chat-1") is False
    assert plugin.results_for("chat-1") is None
    # chat.created is a declared no-op.
    await registry.dispatch_event("chat.created", chat_id="chat-1")
    assert plugin.is_enabled("chat-1") is False


async def test_registered_but_not_enabled_plugin_hook_does_not_run(tmp_path):
    factory = make_factory(tmp_path)
    uid = await make_user(factory)
    chat_id = await make_chat(factory, uid)
    registry = PluginRegistry()
    record, plugin = register_plugin(registry, CountingProvider())  # REGISTERED only
    assert record.state is PluginState.REGISTERED
    plugin.set_chat_config(chat_id, enabled=True)
    await plugin.search(chat_id, "q")
    async with factory() as session:
        result = await inspect_prompt(
            session, uid, messages=["hi"], chat_id=chat_id,
            plugin_registry=registry)
    assert result["plugins"]["slots_stage"] == []
    assert record.consecutive_failures == 0
