"""P-085 Vector Storage plugin battery."""
from __future__ import annotations
import pytest
from runmal.backends.embeddings import EmbeddingProvenance, FakeEmbeddingBackend
from runmal.backends.errors import BackendUnavailable
from runmal.backends.embeddings import EmbeddingBackend, EmbeddingResult
from runmal.backends.models import HealthStatus
from runmal.chats import service as chats_svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.memory import service as memory_service
from runmal.memory.vectorstore import InMemoryVectorStore
from runmal.plugins import service as plugin_service
from runmal.plugins.events import make_event
from runmal.plugins.manifest import manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginRegistry, PluginState
from runmal.plugins.vector_storage import PLUGIN_ID, DEFAULT_TOP_K, VectorMemoryIndex, VectorStorageConfig, build_manifest, config_from_manifest, manifest_data, parse_scoped_doc_id, rebuild_scope_index, register_plugin, road_for_provenance, sandbox_grants, scoped_doc_id, search_scoped_memories, vector_status
from runmal.prompt.inspect import inspect_prompt
PROV = EmbeddingProvenance(provider="fake", model="m1", dims=3, version="1")
def make_factory(tmp_path):
    db_path = tmp_path / "test.db"; migrate_to_head(db_path); return create_session_factory(create_db_engine(db_path))
async def make_user(factory, name="volmarr"):
    async with factory() as session:
        u = User(name=name); session.add(u); await session.commit(); return u.id
@pytest.fixture(autouse=True)
def _reset():
    plugin_service.set_default_registry(None); yield; plugin_service.set_default_registry(None)
class FailingBackend(EmbeddingBackend):
    backend_key = "failing"
    async def embed(self, texts): raise BackendUnavailable("down")
    def model_info(self):
        from runmal.backends.embeddings import EmbeddingModelInfo; return EmbeddingModelInfo(model_id="x", provider="failing", dims=3)
    async def health_check(self): return HealthStatus(ok=False, detail="down")
# manifest
def test_manifest_data():
    d = manifest_data(); assert d["id"] == "runmal.vector-storage"; assert set(d["capabilities"]) == {"chat.events", "prompt.hooks", "ui.slots"}; assert set(d["permissions"]) == {"chat.read", "prompt.inject", "ui.contribute"}; assert "chat.write" not in d["permissions"]; assert set(d["events"]) == {"chat.created", "message.created", "message.edited", "message.deleted"}; assert d["prompt_hooks"] == [{"id": "vector-recall", "stage": "slots", "priority": 90}]; assert d["ui_slots"][0]["slot"] == "chat.sidebar"; assert d["enabled_by_default"] is False
def test_manifest_roundtrip():
    m = build_manifest(); assert manifest_to_data(m) == manifest_data(); assert manifest_from_data(manifest_to_data(m)) == m
def test_register_accepts():
    r = PluginRegistry(); rec, plugin = register_plugin(r); assert rec.state is PluginState.REGISTERED; assert r.keys() == [PLUGIN_ID]
def test_sandbox_empty():
    g = sandbox_grants(); assert g.plugin_id == PLUGIN_ID; assert g.resources == frozenset(); assert g.surface_permissions == frozenset({"chat.read", "prompt.inject", "ui.contribute"})
def test_config():
    assert VectorStorageConfig().top_k == DEFAULT_TOP_K; assert config_from_manifest(build_manifest()).top_k == DEFAULT_TOP_K
    for bad in (dict(top_k=0), dict(top_k=True), dict(min_score=2), dict(min_score="x")):
        with pytest.raises(ValueError): VectorStorageConfig(**bad)
def test_config_from_manifest_fallback():
    d = manifest_data(); d["settings"] = {"schema": {}, "defaults": {"top_k": "lots", "min_score": 9}}; c = config_from_manifest(manifest_from_data(d)); assert c.top_k == DEFAULT_TOP_K and c.min_score == 0.0
    d["settings"] = {"schema": {}, "defaults": {"top_k": 3, "min_score": 0.5}}; c = config_from_manifest(manifest_from_data(d)); assert (c.top_k, c.min_score) == (3, 0.5)
def test_road_labels():
    assert road_for_provenance(EmbeddingProvenance(provider="local", model="hash-ngram-1", dims=256)) == "lexical_vector"; assert road_for_provenance(PROV) == "vector"; assert road_for_provenance(None) == "none"
def test_scoped_doc_id():
    assert parse_scoped_doc_id(scoped_doc_id("chat", "c1", "m1")) == ("chat", "c1", "m1")
    for args in (("user", "c1", "m1"), ("chat", "", "m1"), ("chat", "c1", ""), ("chat", "a|b", "m1")):
        with pytest.raises(ValueError): scoped_doc_id(*args)
    with pytest.raises(ValueError): parse_scoped_doc_id("bogus")
# index core
def test_index_scope_separation():
    idx = VectorMemoryIndex(InMemoryVectorStore()); idx.index_vector("chat", "c1", "m-chat", (1.0, 0.0, 0.0), PROV); idx.index_vector("character", "hero", "m-char", (1.0, 0.0, 0.0), PROV)
    assert idx.count_scope("chat", "c1") == 1 and idx.count_scope("character", "hero") == 1
    hits = idx.search_vectors("chat", "c1", (1.0, 0.0, 0.0), PROV, top_k=5); assert [h["memory_id"] for h in hits] == ["m-chat"]
    hits = idx.search_vectors("character", "hero", (1.0, 0.0, 0.0), PROV, top_k=5); assert [h["memory_id"] for h in hits] == ["m-char"]
    assert idx.search_vectors("chat", "other", (1.0, 0.0, 0.0), PROV) == []
def test_index_forget_and_clear():
    idx = VectorMemoryIndex(); idx.index_vector("chat", "c1", "a", (1.0, 0.0, 0.0), PROV); idx.index_vector("chat", "c1", "b", (0.0, 1.0, 0.0), PROV); idx.index_vector("chat", "c2", "c", (1.0, 0.0, 0.0), PROV)
    idx.forget("chat", "c1", "a"); assert idx.count_scope("chat", "c1") == 1
    idx.clear_scope("chat", "c1"); assert idx.count_scope("chat", "c1") == 0 and idx.count_scope("chat", "c2") == 1
def test_sqlite_vec_store_parity(tmp_path):
    try:
        from runmal.memory.vectorstore import SqliteVecVectorStore
        store = SqliteVecVectorStore(tmp_path / "vec.db")
    except Exception as exc:
        pytest.skip(f"sqlite-vec unavailable: {exc}")
    idx = VectorMemoryIndex(store); idx.index_vector("chat", "c1", "m1", (1.0, 0.0, 0.0), PROV); idx.index_vector("character", "h1", "m2", (1.0, 0.0, 0.0), PROV)
    assert [h["memory_id"] for h in idx.search_vectors("chat", "c1", (1.0, 0.0, 0.0), PROV)] == ["m1"]; store.close()
# DB layer
async def seed_memories(factory, uid):
    async with factory() as session:
        chat = await chats_svc.create_chat(session, uid, title="t")
        m1 = await memory_service.create_memory(session, uid, content="dragons guard the mountain hoard", scope="chat", chat_id=chat.id)
        m2 = await memory_service.create_memory(session, uid, content="fresh bread baked at dawn in the market", scope="chat", chat_id=chat.id)
        m3 = await memory_service.create_memory(session, uid, content="dragons are the sworn companions of the hero", scope="character", character_id="hero-1")
        await session.commit(); return chat.id, m1.id, m2.id, m3.id
async def test_rebuild_and_status(tmp_path):
    factory = make_factory(tmp_path); uid = await make_user(factory); chat_id, m1, m2, m3 = await seed_memories(factory, uid); idx = VectorMemoryIndex()
    async with factory() as session:
        st = await rebuild_scope_index(session, uid, "chat", chat_id, index=idx); assert st["memory_count"] == 2 and st["indexed_count"] == 2 and st["road"] == "lexical_vector" and st["provenance"]["provider"] == "local"
        st2 = await vector_status(session, uid, "character", "hero-1", index=idx); assert st2["memory_count"] == 1 and st2["indexed_count"] == 0
async def test_search_local_is_lexical_and_scoped(tmp_path):
    factory = make_factory(tmp_path); uid = await make_user(factory); chat_id, m1, m2, m3 = await seed_memories(factory, uid); idx = VectorMemoryIndex()
    async with factory() as session:
        out = await search_scoped_memories(session, uid, "chat", chat_id, "dragons mountain hoard", index=idx); assert out["road"] == "lexical_vector"; assert out["hits"] and out["hits"][0]["memory_id"] == m1; assert all(h["road"] == "lexical_vector" for h in out["hits"]); assert m3 not in [h["memory_id"] for h in out["hits"]]
        outc = await search_scoped_memories(session, uid, "character", "hero-1", "dragons companions hero", index=idx); assert [h["memory_id"] for h in outc["hits"]] == [m3]
async def test_search_configured_backend_is_vector(tmp_path):
    factory = make_factory(tmp_path); uid = await make_user(factory); chat_id, m1, m2, m3 = await seed_memories(factory, uid); idx = VectorMemoryIndex(); backend = FakeEmbeddingBackend(dims=8)
    async with factory() as session:
        out = await search_scoped_memories(session, uid, "chat", chat_id, "anything", index=idx, backend=backend); assert out["road"] == "vector"; assert out["provenance"]["provider"] == "fake"; assert all(h["road"] == "vector" for h in out["hits"])
async def test_search_failing_backend_falls_back_labelled(tmp_path):
    factory = make_factory(tmp_path); uid = await make_user(factory); chat_id, m1, m2, m3 = await seed_memories(factory, uid); idx = VectorMemoryIndex()
    async with factory() as session:
        out = await search_scoped_memories(session, uid, "chat", chat_id, "dragons hoard", index=idx, backend=FailingBackend()); assert out["road"] == "keyword_fallback"; assert out["provenance"] is None; assert out["hits"] and out["hits"][0]["memory_id"] == m1; assert all(h["road"] == "keyword_fallback" for h in out["hits"])
async def test_search_empty_query_and_owner_scope(tmp_path):
    factory = make_factory(tmp_path); uid = await make_user(factory); other = await make_user(factory, "mallory"); chat_id, *_ = await seed_memories(factory, uid); idx = VectorMemoryIndex()
    async with factory() as session:
        out = await search_scoped_memories(session, uid, "chat", chat_id, "  ", index=idx); assert out["road"] == "none" and out["hits"] == []
        out2 = await search_scoped_memories(session, other, "chat", chat_id, "dragons", index=idx); assert out2["hits"] == []
        st = await vector_status(session, other, "chat", chat_id, index=idx); assert st["memory_count"] == 0
async def test_rebuild_removes_stale(tmp_path):
    factory = make_factory(tmp_path); uid = await make_user(factory); chat_id, m1, m2, m3 = await seed_memories(factory, uid); idx = VectorMemoryIndex()
    async with factory() as session:
        await rebuild_scope_index(session, uid, "chat", chat_id, index=idx); assert idx.count_scope("chat", chat_id) == 2
        await memory_service.delete_memory(session, uid, m2); await session.commit()
        st = await rebuild_scope_index(session, uid, "chat", chat_id, index=idx); assert st["indexed_count"] == 1
# plugin behaviour
async def test_event_rebuilds_chat_scope(tmp_path):
    factory = make_factory(tmp_path); uid = await make_user(factory); chat_id, *_ = await seed_memories(factory, uid); idx = VectorMemoryIndex(); registry = PluginRegistry(); rec, _ = register_plugin(registry, factory, index=idx, enable=True); plugin_service.set_default_registry(registry)
    try:
        async with factory() as session:
            await chats_svc.append_message(session, uid, chat_id, "user", "hello world"); await session.commit()
    finally: plugin_service.set_default_registry(None)
    assert idx.count_scope("chat", chat_id) == 2; assert rec.consecutive_failures == 0
async def test_unbound_plugin_inert(tmp_path):
    factory = make_factory(tmp_path); uid = await make_user(factory); chat_id, *_ = await seed_memories(factory, uid); registry = PluginRegistry(); rec, plugin = register_plugin(registry, enable=True)
    report = await registry.dispatch_event("message.created", chat_id=chat_id, message_id="m1", data={"chat_id": chat_id, "message_id": "m1"}); assert report.failed == []; assert rec.consecutive_failures == 0
    ev = make_event("chat.created", chat_id=chat_id); await plugin.on_event(ev)
async def test_hook_injects_status_and_abstains(tmp_path):
    factory = make_factory(tmp_path); uid = await make_user(factory); chat_id, *_ = await seed_memories(factory, uid); idx = VectorMemoryIndex()
    async with factory() as session: await rebuild_scope_index(session, uid, "chat", chat_id, index=idx)
    registry = PluginRegistry(); register_plugin(registry, factory, index=idx, enable=True)
    async with factory() as session:
        result = await inspect_prompt(session, uid, messages=["hi"], chat_id=chat_id, plugin_registry=registry, include_preview=True); assert result["plugins"]["slots_stage"][0]["outcome"] == "applied"; rows = {r["slot_id"]: r for r in result["slots"]}; assert rows["runmal.vector-storage:vector-memory"]["provenance"] == "plugin:runmal.vector-storage"; assert "lexical_vector" in str(result["prompt_preview"])
        empty = await inspect_prompt(session, uid, messages=["hi"], plugin_registry=registry); assert empty["plugins"]["slots_stage"][0]["outcome"] == "abstained"
def test_ui_contribution():
    registry = PluginRegistry(); register_plugin(registry); rows = [r for r in registry.ui_contributions("chat.sidebar") if r["plugin_id"] == PLUGIN_ID]; assert len(rows) == 1 and rows[0]["id"] == "vector-panel" and rows[0]["active"] is False; registry.enable(PLUGIN_ID); assert [r["plugin_id"] for r in registry.ui_contributions("chat.sidebar", active_only=True)] == [PLUGIN_ID]
def test_enable_param():
    registry = PluginRegistry(); rec, _ = register_plugin(registry, enable=True); assert rec.state is PluginState.ENABLED
def test_no_migration():
    assert "0042" not in MIGRATIONS
async def test_migration_head(tmp_path):
    db_path = tmp_path / "mig.db"; migrate_to_head(db_path); assert current_revision(db_path) == "0042"
