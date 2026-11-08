"""Vector Storage plugin (P-085): per-chat/character vector memory.

Roadmap line: "Vector Storage plugin: per-chat/character vector
memory with the founding sqlite-vec store."

A first-class P-081 citizen (pattern: P-084) giving chats and
characters their own vector memory on the founding store
(:mod:`runmal.memory.vectorstore`: the sqlite-vec adapter or
the in-memory contract twin). Scoped memories (founding
``scope='chat'`` / ``scope='character'`` rows) are embedded and
indexed under a scoped doc id; search only ever returns docs
from the ONE scope named, so a chat's vector memory and a
character's vector memory stay separate and inspectable even
when a cross-scope vector would score highest.

Embedding honesty (P-041 banked law): the built-in local
provider (:class:`~runmal.lorebooks.vector_match.LocalEmbeddingBackend`,
provider ``local``, model ``hash-ngram-1``) is lexical-semantic,
not neural — results through it carry road ``lexical_vector``.
A configured profile backend gives true semantics through the
same seam and its results carry road ``vector``. When embedding
fails or is unavailable, search degrades to a keyword scan over
the scoped memories and every hit carries road
``keyword_fallback`` — a keyword fallback is NEVER disguised
as a vector hit. An empty query carries road ``none``.

Sandbox stance (P-082): only v1 surface permissions are
declared, so the derived resource grant set is EMPTY
(:func:`sandbox_grants` proves it): no network, files or
secrets. Database/store access is host-supplied wiring handed
to trusted in-tree registration code, not a plugin grant.

Wiring: :func:`register_plugin` only. ``build_registry`` /
``create_app`` are unchanged (P-081 pins the empty boot
registry); P-084 banks before this slice and the keeper
reconciles liveness at banking. No migration: the index rides
the founding vector-store tables. See
docs/VECTOR_STORAGE_PLUGIN_2026-11-07.md.
"""
from __future__ import annotations
from dataclasses import dataclass
from sqlalchemy.ext.asyncio import AsyncSession
from runmal.backends.embeddings import EmbeddingProvenance
from runmal.db.models import Chat
from runmal.memory import service as memory_service
from runmal.memory.vectorstore import InMemoryVectorStore, VectorStore
from runmal.plugins.manifest import PluginManifest, manifest_from_data, manifest_to_data
from runmal.plugins.registry import PluginHandlers, PluginRecord, PluginRegistry
from runmal.prompt.slots import Slot
from runmal.sandbox.policy import GrantSet, grants_from_manifest
PLUGIN_ID = "runmal.vector-storage"
PLUGIN_VERSION = "1.0.0"
HOOK_ID = "vector-recall"
SLOT_LOCAL_ID = "vector-memory"
UI_LOCAL_ID = "vector-panel"
DEFAULT_TOP_K = 5
DEFAULT_MIN_SCORE = 0.0
SCOPE_KINDS = ("chat", "character")
REFRESH_EVENTS = frozenset({"message.created", "message.edited", "message.deleted"})
DECLARED_EVENTS = ("chat.created",) + tuple(sorted(REFRESH_EVENTS))
_HEADER = "Vector memory for this scope (inspectable; road and provider named):"
def _is_int(v):
    return isinstance(v, int) and not isinstance(v, bool)
def _check_scope(scope_kind, scope_id):
    if scope_kind not in SCOPE_KINDS:
        raise ValueError(f"scope_kind must be one of {SCOPE_KINDS}: {scope_kind!r}")
    if not isinstance(scope_id, str) or not scope_id or "|" in scope_id:
        raise ValueError(f"scope_id must be a non-empty string without '|': {scope_id!r}")
def scoped_doc_id(scope_kind, scope_id, memory_id):
    _check_scope(scope_kind, scope_id)
    if not isinstance(memory_id, str) or not memory_id or "|" in memory_id:
        raise ValueError(f"memory_id must be a non-empty string without '|': {memory_id!r}")
    return f"{scope_kind}|{scope_id}|{memory_id}"
def parse_scoped_doc_id(doc_id):
    parts = str(doc_id).split("|", 2)
    if len(parts) != 3 or parts[0] not in SCOPE_KINDS or not parts[1] or not parts[2]:
        raise ValueError(f"not a scoped doc id: {doc_id!r}")
    return parts[0], parts[1], parts[2]
def road_for_provenance(provenance):
    if provenance is None:
        return "none"
    return "lexical_vector" if provenance.provider == "local" else "vector"
@dataclass(frozen=True)
class VectorStorageConfig:
    top_k: int = DEFAULT_TOP_K
    min_score: float = DEFAULT_MIN_SCORE
    def __post_init__(self):
        if not _is_int(self.top_k) or self.top_k < 1:
            raise ValueError(f"top_k must be an int >= 1: {self.top_k!r}")
        if isinstance(self.min_score, bool) or not isinstance(self.min_score, (int, float)):
            raise ValueError(f"min_score must be a number: {self.min_score!r}")
        if not -1.0 <= float(self.min_score) <= 1.0:
            raise ValueError(f"min_score must be in [-1, 1]: {self.min_score!r}")
class VectorMemoryIndex:
    """Scoped index over a founding VectorStore."""
    def __init__(self, store=None):
        self.store = store or InMemoryVectorStore()
        self._meta = {}
        self.last_provenance = None
    def index_vector(self, scope_kind, scope_id, memory_id, vector, provenance):
        doc_id = scoped_doc_id(scope_kind, scope_id, memory_id)
        self.store.insert(provenance, doc_id, tuple(vector))
        self._meta[doc_id] = (scope_kind, scope_id, memory_id)
        self.last_provenance = provenance
        return doc_id
    def forget(self, scope_kind, scope_id, memory_id, provenance=None):
        doc_id = scoped_doc_id(scope_kind, scope_id, memory_id)
        prov = provenance or self.last_provenance
        if prov is not None:
            self.store.delete(prov, doc_id)
        self._meta.pop(doc_id, None)
    def clear_scope(self, scope_kind, scope_id, provenance=None):
        _check_scope(scope_kind, scope_id)
        prov = provenance or self.last_provenance
        for doc_id, (k, sid, _m) in list(self._meta.items()):
            if k == scope_kind and sid == scope_id:
                if prov is not None:
                    self.store.delete(prov, doc_id)
                self._meta.pop(doc_id, None)
    def count_scope(self, scope_kind, scope_id):
        _check_scope(scope_kind, scope_id)
        return sum(1 for k, sid, _ in self._meta.values() if k == scope_kind and sid == scope_id)
    def doc_ids(self, scope_kind=None, scope_id=None):
        return sorted(d for d, (k, sid, _m) in self._meta.items() if (scope_kind is None or k == scope_kind) and (scope_id is None or sid == scope_id))
    def search_vectors(self, scope_kind, scope_id, query_vector, provenance, top_k=5):
        _check_scope(scope_kind, scope_id)
        raw = self.store.search(provenance, tuple(query_vector), top_k=max(top_k * 4, top_k, len(self._meta)))
        out = []
        for doc_id, score in raw:
            meta = self._meta.get(doc_id)
            if meta is None or meta[0] != scope_kind or meta[1] != scope_id:
                continue
            out.append({"memory_id": meta[2], "score": float(score), "scope_kind": scope_kind, "scope_id": scope_id, "doc_id": doc_id})
            if len(out) >= top_k:
                break
        return out
def manifest_data():
    return {"id": PLUGIN_ID, "name": "Vector Storage", "version": PLUGIN_VERSION, "api_version": 1, "description": "Per-chat and per-character vector memory on the founding sqlite-vec store.", "author": "Runmal", "capabilities": ["chat.events", "prompt.hooks", "ui.slots"], "permissions": ["chat.read", "prompt.inject", "ui.contribute"], "events": list(DECLARED_EVENTS), "prompt_hooks": [{"id": HOOK_ID, "stage": "slots", "priority": 90}], "ui_slots": [{"id": UI_LOCAL_ID, "slot": "chat.sidebar", "label": "Vector Memory", "order": 90, "payload": {"kind": "panel", "route": "vector-storage"}}], "settings": {"schema": {"top_k": {"type": "integer", "minimum": 1}, "min_score": {"type": "number", "minimum": -1, "maximum": 1}}, "defaults": {"top_k": DEFAULT_TOP_K, "min_score": DEFAULT_MIN_SCORE}}, "enabled_by_default": False}
def build_manifest():
    return manifest_from_data(manifest_data())
def config_from_manifest(manifest):
    defaults = {}
    if isinstance(manifest.settings, dict):
        raw = manifest.settings.get("defaults")
        if isinstance(raw, dict):
            defaults = raw
    top_k = defaults.get("top_k", DEFAULT_TOP_K)
    if not _is_int(top_k) or top_k < 1:
        top_k = DEFAULT_TOP_K
    ms = defaults.get("min_score", DEFAULT_MIN_SCORE)
    if isinstance(ms, bool) or not isinstance(ms, (int, float)) or not -1.0 <= float(ms) <= 1.0:
        ms = DEFAULT_MIN_SCORE
    return VectorStorageConfig(top_k=top_k, min_score=float(ms))
def sandbox_grants():
    return grants_from_manifest(manifest_to_data(build_manifest()))
def _default_backend():
    from runmal.lorebooks.vector_match import LocalEmbeddingBackend
    return LocalEmbeddingBackend()
async def scoped_memories(session, user_id, scope_kind, scope_id):
    _check_scope(scope_kind, scope_id)
    rows = await memory_service.list_memories(session, user_id)
    if scope_kind == "chat":
        return [m for m in rows if m.scope == "chat" and m.chat_id == scope_id]
    return [m for m in rows if m.scope == "character" and m.character_id == scope_id]
async def vector_status(session, user_id, scope_kind, scope_id, *, index, backend=None):
    memories = await scoped_memories(session, user_id, scope_kind, scope_id)
    prov = index.last_provenance
    if prov is None and backend is not None:
        try:
            info = backend.model_info()
            prov = EmbeddingProvenance(provider=info.provider, model=info.model_id, dims=info.dims, version=info.version)
        except Exception:
            prov = None
    return {"plugin_id": PLUGIN_ID, "scope_kind": scope_kind, "scope_id": scope_id, "memory_count": len(memories), "indexed_count": index.count_scope(scope_kind, scope_id), "provenance": prov.to_dict() if prov else None, "road": road_for_provenance(prov)}
async def rebuild_scope_index(session, user_id, scope_kind, scope_id, *, index, backend=None, config=None):
    backend = backend or _default_backend()
    memories = await scoped_memories(session, user_id, scope_kind, scope_id)
    if not memories:
        index.clear_scope(scope_kind, scope_id)
        return await vector_status(session, user_id, scope_kind, scope_id, index=index, backend=backend)
    try:
        result = await backend.embed([m.content for m in memories])
    except Exception:
        index.clear_scope(scope_kind, scope_id)
        status = await vector_status(session, user_id, scope_kind, scope_id, index=index, backend=backend)
        status.update(road="keyword_fallback", degraded=True, provenance=None)
        return status
    index.clear_scope(scope_kind, scope_id, provenance=result.provenance)
    for memory, vector in zip(memories, result.vectors, strict=True):
        index.index_vector(scope_kind, scope_id, memory.id, vector, result.provenance)
    status = await vector_status(session, user_id, scope_kind, scope_id, index=index, backend=backend)
    status["degraded"] = False
    return status
def _keyword_hits(memories, query_text, top_k):
    terms = {t for t in "".join(ch if (ch.isalnum() or ch == "_") else " " for ch in query_text.lower()).split() if t}
    if not terms:
        return []
    out = []
    for m in memories:
        words = {t for t in "".join(ch if (ch.isalnum() or ch == "_") else " " for ch in m.content.lower()).split() if t}
        overlap = len(terms & words)
        if overlap:
            out.append({"memory_id": m.id, "score": overlap / len(terms), "scope_kind": m.scope if m.scope in SCOPE_KINDS else None, "road": "keyword_fallback"})
    out.sort(key=lambda h: (-h["score"], h["memory_id"]))
    return out[:top_k]
async def search_scoped_memories(session, user_id, scope_kind, scope_id, query_text, *, index, backend=None, config=None):
    config = config or VectorStorageConfig()
    backend = backend or _default_backend()
    if not query_text or not query_text.strip():
        return {"plugin_id": PLUGIN_ID, "scope_kind": scope_kind, "scope_id": scope_id, "road": "none", "provenance": None, "hits": []}
    memories = await scoped_memories(session, user_id, scope_kind, scope_id)
    try:
        qresult = await backend.embed([query_text])
    except Exception:
        hits = _keyword_hits(memories, query_text, config.top_k)
        for h in hits:
            h["scope_kind"] = scope_kind; h["scope_id"] = scope_id
        return {"plugin_id": PLUGIN_ID, "scope_kind": scope_kind, "scope_id": scope_id, "road": "keyword_fallback", "provenance": None, "hits": hits}
    provenance = qresult.provenance; road = road_for_provenance(provenance)
    if index.count_scope(scope_kind, scope_id) == 0 and memories:
        rebuilt = await rebuild_scope_index(session, user_id, scope_kind, scope_id, index=index, backend=backend, config=config)
        if rebuilt.get("degraded"):
            hits = _keyword_hits(memories, query_text, config.top_k)
            for h in hits:
                h["scope_kind"] = scope_kind; h["scope_id"] = scope_id
            return {"plugin_id": PLUGIN_ID, "scope_kind": scope_kind, "scope_id": scope_id, "road": "keyword_fallback", "provenance": None, "hits": hits}
    raw = index.search_vectors(scope_kind, scope_id, qresult.vectors[0], provenance, top_k=config.top_k)
    hits = [{**h, "road": road} for h in raw if h["score"] >= float(config.min_score)]
    return {"plugin_id": PLUGIN_ID, "scope_kind": scope_kind, "scope_id": scope_id, "road": road, "provenance": provenance.to_dict(), "hits": hits}
class VectorStoragePlugin:
    def __init__(self, session_factory=None, index=None, backend=None, config=None):
        self._session_factory = session_factory; self.index = index; self._backend = backend; self.config = config or config_from_manifest(build_manifest())
    @property
    def manifest(self):
        return build_manifest()
    def bind_session_factory(self, session_factory):
        self._session_factory = session_factory
    def bind_index(self, index):
        self.index = index
    def handlers(self):
        return PluginHandlers(on_event=self.on_event, prompt_hooks={HOOK_ID: self.vector_slot})
    async def on_event(self, event):
        if event.name not in REFRESH_EVENTS or not event.chat_id:
            return
        if self._session_factory is None or self.index is None:
            return
        async with self._session_factory() as session:
            chat = await session.get(Chat, event.chat_id)
            if chat is None:
                return
            await rebuild_scope_index(session, chat.user_id, "chat", chat.id, index=self.index, backend=self._backend, config=self.config)
    async def vector_slot(self, ctx, slots):
        if self._session_factory is None or self.index is None:
            return None
        scope_kind = scope_id = None
        if getattr(ctx, "chat_id", None):
            scope_kind, scope_id = "chat", ctx.chat_id
        elif getattr(ctx, "character_id", None):
            scope_kind, scope_id = "character", ctx.character_id
        else:
            return None
        count = self.index.count_scope(scope_kind, scope_id)
        if count == 0:
            return None
        prov = self.index.last_provenance; road = road_for_provenance(prov); prov_text = f"{prov.provider}/{prov.model}" if prov else "unknown"
        return [Slot(id=SLOT_LOCAL_ID, kind="vector_memory", role="system", content=f"{_HEADER}\n{count} indexed vector memories for {scope_kind} {scope_id} via {road} ({prov_text}).", order=4, priority=90, trigger="vector-storage")]
def register_plugin(registry, session_factory=None, *, index=None, backend=None, config=None, enable=False):
    plugin = VectorStoragePlugin(session_factory, index, backend, config)
    record = registry.register(plugin.manifest, plugin.handlers())
    if enable:
        registry.enable(PLUGIN_ID); record = registry.get(PLUGIN_ID)
    return record, plugin
__all__ = ["DECLARED_EVENTS", "DEFAULT_MIN_SCORE", "DEFAULT_TOP_K", "HOOK_ID", "PLUGIN_ID", "PLUGIN_VERSION", "REFRESH_EVENTS", "SCOPE_KINDS", "SLOT_LOCAL_ID", "UI_LOCAL_ID", "VectorMemoryIndex", "VectorStorageConfig", "VectorStoragePlugin", "build_manifest", "config_from_manifest", "manifest_data", "parse_scoped_doc_id", "rebuild_scope_index", "register_plugin", "road_for_provenance", "sandbox_grants", "scoped_doc_id", "scoped_memories", "search_scoped_memories", "vector_status"]
