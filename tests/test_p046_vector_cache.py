"""P-046 vector-cache battery (ALWAYS RUN, STRICT).

Design Sec.4.2: the stored entry-vector cache (the in-process
half of the P-041 debt) must be outcome-invisible -- cold cache
== uncached, warm cache == uncached, an edited entry re-embeds,
a provider/model switch misses structurally (INV-019: spaces
never mix), LRU eviction changes speed only, and an embed-call
counting fake proves a warm tick embeds only the query plus
cache misses. The query vector is never cached.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import pytest

from runmal.backends.embeddings import (
    EmbeddingProvenance,
    EmbeddingResult,
    FakeEmbeddingBackend,
)
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.vector_match import (
    EntryVectorCache,
    LocalEmbeddingBackend,
    match_vectorised,
    match_vectorised_sync,
    vector_candidates,
)

MSGS = ["a dragon flies over the high mountains"]


def _orm(eid, name, content, keys=(), **kw):
    base = dict(id=eid, name=name, content=content, enabled=True, constant=False,
                vectorised=True, keys=tuple(keys), whole_word=True,
                case_sensitive=False, selective_logic="and_any")
    base.update(kw)
    return SimpleNamespace(**base)


def book():
    return [
        _orm("d", "Dragon Peaks", "Dragons fly over high mountain peaks and roar", ("dragon",)),
        _orm("b", "Market Bread", "Fresh bread is baked at dawn for copper coins", ("bread",)),
        _orm("bell", "Gale Bell", "The bell rings when storms approach the coast", ("gale bell",)),
    ]


class CountingSyncEmbedder:
    """Deterministic sync embedder that records every call.

    Declares its space via ``provenance`` (bound-method owner),
    like LocalEmbeddingBackend; ``report_model`` lets a test make
    the RETURNED provenance differ from the declared one.
    """

    def __init__(self, provider="counting", model="count-1", dims=8, report_model=None, version="1"):
        self.provenance = EmbeddingProvenance(provider=provider, model=model, dims=dims, version=version)
        self._version = version
        self._report_model = report_model or model
        self._provider = provider
        self._dims = dims
        self.calls = []

    def _vector(self, text):
        digest = hashlib.sha256(f"{self._provider}:{self._report_model}:{self._version}:{text}".encode()).digest()
        return tuple(digest[i % len(digest)] / 255.0 for i in range(self._dims))

    def embed_sync(self, texts):
        self.calls.append(list(texts))
        return EmbeddingResult(
            vectors=tuple(self._vector(t) for t in texts),
            provenance=EmbeddingProvenance(provider=self._provider, model=self._report_model, dims=self._dims, version=self._version),
        )


def test_cold_cache_equals_uncached_sync():
    emb = CountingSyncEmbedder()
    uncached = match_vectorised_sync(book(), MSGS, emb.embed_sync)
    cache = EntryVectorCache()
    cold = match_vectorised_sync(book(), MSGS, emb.embed_sync, cache=cache)
    assert cold == uncached
    assert len(cache) == 3
    assert emb.calls[1] == emb.calls[0]  # cold tick embeds everything


def test_warm_cache_embeds_only_query_and_matches_uncached():
    emb = CountingSyncEmbedder()
    cache = EntryVectorCache()
    first = match_vectorised_sync(book(), MSGS, emb.embed_sync, cache=cache)
    second = match_vectorised_sync(book(), MSGS, emb.embed_sync, cache=cache)
    uncached = match_vectorised_sync(book(), MSGS, emb.embed_sync)
    assert first == uncached
    assert second == uncached
    assert len(emb.calls) == 3
    assert len(emb.calls[1]) == 1  # warm tick: query only
    assert emb.calls[1][0] == emb.calls[0][0]  # the query text
    assert cache.hits == 3 and cache.misses == 3


def test_local_backend_warm_tick_matches_uncached():
    backend = LocalEmbeddingBackend()
    cache = EntryVectorCache()
    first = match_vectorised_sync(book(), MSGS, backend.embed_sync, cache=cache)
    second = match_vectorised_sync(book(), MSGS, backend.embed_sync, cache=cache)
    uncached = match_vectorised_sync(book(), MSGS, backend.embed_sync)
    assert first == second == uncached
    assert len(cache) == 3


def test_edited_entry_reembeds_only_itself():
    emb = CountingSyncEmbedder()
    cache = EntryVectorCache()
    match_vectorised_sync(book(), MSGS, emb.embed_sync, cache=cache)
    edited = book()
    edited[1] = _orm("b", "Market Bread", "Sourdough loaves prove slowly overnight", ("bread",))
    out = match_vectorised_sync(edited, MSGS, emb.embed_sync, cache=cache)
    uncached = match_vectorised_sync(edited, MSGS, emb.embed_sync)
    assert out == uncached
    tick2 = emb.calls[1]
    assert len(tick2) == 2  # query + the one edited candidate
    cand_b = next(c for c in vector_candidates(edited) if c.id == "b")
    assert tick2[1] == cand_b.embed_text


def test_provider_switch_misses_never_mixes():
    emb_a = CountingSyncEmbedder(provider="prov-a", model="m1")
    emb_b = CountingSyncEmbedder(provider="prov-b", model="m1")
    cache = EntryVectorCache()
    out_a = match_vectorised_sync(book(), MSGS, emb_a.embed_sync, cache=cache)
    out_b = match_vectorised_sync(book(), MSGS, emb_b.embed_sync, cache=cache)
    assert len(emb_b.calls[0]) == 4  # full re-embed under the new space
    assert out_b == match_vectorised_sync(book(), MSGS, emb_b.embed_sync)
    assert out_b.provenance["provider"] == "prov-b"
    assert out_a.provenance["provider"] == "prov-a"


def test_model_switch_misses():
    emb_a = CountingSyncEmbedder(model="m1")
    emb_b = CountingSyncEmbedder(model="m2")
    cache = EntryVectorCache()
    match_vectorised_sync(book(), MSGS, emb_a.embed_sync, cache=cache)
    out_b = match_vectorised_sync(book(), MSGS, emb_b.embed_sync, cache=cache)
    assert len(emb_b.calls[0]) == 4
    assert out_b == match_vectorised_sync(book(), MSGS, emb_b.embed_sync)


def test_returned_provenance_mismatch_discards_cache():
    # Declared space == cache space (so reads hit), but the embedder
    # ANSWERS from a different space: cached vectors must be
    # discarded and everything re-embedded, never mixed.
    emb_fill = CountingSyncEmbedder(provider="p", model="declared")
    cache = EntryVectorCache()
    match_vectorised_sync(book(), MSGS, emb_fill.embed_sync, cache=cache)
    emb_lie = CountingSyncEmbedder(provider="p", model="declared", report_model="actual")
    out = match_vectorised_sync(book(), MSGS, emb_lie.embed_sync, cache=cache)
    assert len(emb_lie.calls) == 2  # partial call, then full re-embed
    assert len(emb_lie.calls[0]) == 1 and len(emb_lie.calls[1]) == 4
    assert out == match_vectorised_sync(book(), MSGS, emb_lie.embed_sync)
    assert out.provenance["model"] == "actual"


def test_lru_bound_evicts_without_changing_outcomes():
    emb = CountingSyncEmbedder()
    cache = EntryVectorCache(maxsize=2)
    out = match_vectorised_sync(book(), MSGS, emb.embed_sync, cache=cache)
    assert out == match_vectorised_sync(book(), MSGS, emb.embed_sync)
    assert len(cache) <= 2
    again = match_vectorised_sync(book(), MSGS, emb.embed_sync, cache=cache)
    assert again == out
    assert len(cache) <= 2


def test_cache_unit_keying_and_validation():
    cache = EntryVectorCache(maxsize=4)
    cache.put("e1", "text one", (1.0, 0.0), "p", "m", 2)
    assert cache.get("e1", "text one", "p", "m", 2) == (1.0, 0.0)
    assert cache.get("e1", "text EDITED", "p", "m", 2) is None
    assert cache.get("e1", "text one", "other", "m", 2) is None
    assert cache.get("e1", "text one", "p", "m", 99) is None
    assert cache.get("e1", "text one", "p", "m") == (1.0, 0.0)  # dims inferred
    with pytest.raises(ValueError):
        EntryVectorCache(maxsize=0)
    with pytest.raises(ValueError):
        EntryVectorCache(maxsize=True)


class CountingAsyncBackend(FakeEmbeddingBackend):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.calls = []

    async def embed(self, texts):
        self.calls.append(list(texts))
        return await super().embed(texts)


async def test_async_warm_cache_embeds_only_query():
    backend = CountingAsyncBackend(dims=8)
    cache = EntryVectorCache()
    first = await match_vectorised(book(), MSGS, backend=backend, cache=cache)
    second = await match_vectorised(book(), MSGS, backend=backend, cache=cache)
    uncached = await match_vectorised(book(), MSGS, backend=backend)
    assert first == second == uncached
    assert len(backend.calls[0]) == 4
    assert len(backend.calls[1]) == 1  # query only
    assert len(cache) == 3


async def test_async_provider_switch_misses():
    backend_a = CountingAsyncBackend(dims=8, model="am-1")
    backend_b = CountingAsyncBackend(dims=8, model="am-2")
    cache = EntryVectorCache()
    await match_vectorised(book(), MSGS, backend=backend_a, cache=cache)
    out_b = await match_vectorised(book(), MSGS, backend=backend_b, cache=cache)
    assert len(backend_b.calls[0]) == 4
    assert out_b == await match_vectorised(book(), MSGS, backend=backend_b)


def test_preview_forwards_cache():
    import json as _json
    def orm(eid, name, content, keys=()):
        return SimpleNamespace(
            id=eid, name=name, content=content, enabled=True, constant=False,
            vectorised=True, keys_json=_json.dumps(list(keys)), secondary_keys_json="[]",
            whole_word=True, case_sensitive=False, selective_logic="and_any",
            sticky_prompts=0, cooldown_prompts=0, delay_prompts=0, inclusion_group="",
            group_weight=100, priority=100, probability=100, position="before_char",
            depth=None, role="system")
    entries = [orm("d", "Dragon Peaks", "Dragons fly over high mountain peaks", ("dragon",))]
    backend = LocalEmbeddingBackend()
    cache = EntryVectorCache()
    out1 = preview_activation(entries, MSGS, 4, None, vector_embedder=backend.embed_sync, vector_cache=cache)
    assert len(cache) == 1
    out2 = preview_activation(entries, MSGS, 4, None, vector_embedder=backend.embed_sync, vector_cache=cache)
    assert out1["vector_match"] == out2["vector_match"]
    assert cache.hits >= 1


class CountingPlainListEmbedder:
    """Sync embedder returning a PLAIN list of vectors (the
    non-EmbeddingResult branch) while declaring its space via a
    ``provenance`` attribute on the bound-method owner."""

    def __init__(self, dims=8):
        self.provenance = EmbeddingProvenance(provider="plain", model="plain-1", dims=dims, version="1")
        self._dims = dims
        self.calls = []

    def _vector(self, text):
        digest = hashlib.sha256(f"plain:{text}".encode()).digest()
        return tuple(digest[i % len(digest)] / 255.0 for i in range(self._dims))

    def embed_sync(self, texts):
        self.calls.append(list(texts))
        return [self._vector(t) for t in texts]


def test_plain_list_embedder_warm_cache():
    emb = CountingPlainListEmbedder()
    cache = EntryVectorCache()
    first = match_vectorised_sync(book(), MSGS, emb.embed_sync, cache=cache)
    second = match_vectorised_sync(book(), MSGS, emb.embed_sync, cache=cache)
    uncached = match_vectorised_sync(book(), MSGS, emb.embed_sync)
    assert first == second == uncached
    assert len(emb.calls[0]) == 4
    assert len(emb.calls[1]) == 1  # warm tick: query only
    assert len(cache) == 3


class MismatchAsyncBackend(FakeEmbeddingBackend):
    """Declares model am-1 via model_info but ANSWERS with
    provenance am-2 and am-2-tagged vectors."""

    def __init__(self):
        super().__init__(dims=8, model="am-1")
        self.calls = []

    def _vector(self, text):
        digest = hashlib.sha256(f"am-2:{text}".encode()).digest()
        return tuple(digest[i % len(digest)] / 255.0 for i in range(self._dims))

    async def embed(self, texts):
        self.calls.append(list(texts))
        return EmbeddingResult(
            vectors=tuple(self._vector(t) for t in texts),
            provenance=EmbeddingProvenance(provider="fake", model="am-2", dims=self._dims, version="1"),
        )


async def test_async_returned_provenance_mismatch_discards_cache():
    fill = CountingAsyncBackend(dims=8, model="am-1")
    cache = EntryVectorCache()
    await match_vectorised(book(), MSGS, backend=fill, cache=cache)
    lying = MismatchAsyncBackend()
    out = await match_vectorised(book(), MSGS, backend=lying, cache=cache)
    assert len(lying.calls) == 2  # query-only call, then full re-embed
    assert len(lying.calls[0]) == 1 and len(lying.calls[1]) == 4
    assert out.provenance["model"] == "am-2"
    assert out == await match_vectorised(book(), MSGS, backend=MismatchAsyncBackend())


# --- Review-fix regressions (independent review, D1-D5) ---------------------


def test_version_bump_misses_and_reembeds():
    # D1: the space identity includes version (EmbeddingProvenance
    # .key()); a version bump with provider/model/dims unchanged
    # must miss, never score old-version vectors against a
    # new-version query.
    emb_v1 = CountingSyncEmbedder(provider="p", model="m", version="1")
    emb_v2 = CountingSyncEmbedder(provider="p", model="m", version="2")
    cache = EntryVectorCache()
    match_vectorised_sync(book(), MSGS, emb_v1.embed_sync, cache=cache)
    out = match_vectorised_sync(book(), MSGS, emb_v2.embed_sync, cache=cache)
    assert len(emb_v2.calls[0]) == 4  # full re-embed, no stale hits
    assert out == match_vectorised_sync(book(), MSGS, emb_v2.embed_sync)
    assert out.provenance["version"] == "2"


class DeclaredDimsLiarEmbedder:
    """Declares dims=8 via its provenance attribute but ANSWERS
    with dims=4 vectors and dims=4 provenance (a model re-pulled
    under the same name)."""

    def __init__(self):
        self.provenance = EmbeddingProvenance(provider="p", model="m", dims=8, version="1")
        self.calls = []

    def _vector(self, text):
        digest = hashlib.sha256(f"shifted:{text}".encode()).digest()
        return tuple(digest[i % len(digest)] / 255.0 for i in range(4))

    def embed_sync(self, texts):
        self.calls.append(list(texts))
        return EmbeddingResult(
            vectors=tuple(self._vector(t) for t in texts),
            provenance=EmbeddingProvenance(provider="p", model="m", dims=4, version="1"),
        )


def test_answered_dims_change_discards_cache():
    # D2: warm cache under dims=8; the embedder answers dims=4
    # under the same provider/model. Cached 8-dim vectors must
    # be discarded and everything re-embedded -- the uncached
    # outcome is vector hits, NOT a no_comparable_vectors
    # fallback with vanished scores.
    honest = CountingSyncEmbedder(provider="p", model="m", dims=8)
    cache = EntryVectorCache()
    match_vectorised_sync(book(), MSGS, honest.embed_sync, cache=cache)
    liar = DeclaredDimsLiarEmbedder()
    out = match_vectorised_sync(book(), MSGS, liar.embed_sync, cache=cache)
    assert len(liar.calls) == 2
    assert len(liar.calls[0]) == 1 and len(liar.calls[1]) == 4
    assert out == match_vectorised_sync(book(), MSGS, liar.embed_sync)
    assert out.mode == "vector" and out.scores


def test_duplicate_candidate_ids_last_wins_with_cache():
    # D4: two candidates share an id; the uncached build lets
    # the LATER candidate's vector win the id's score. The
    # cached path (one hit, one miss) must resolve identically.
    emb = CountingSyncEmbedder()
    cache = EntryVectorCache()
    first_only = [_orm("dup", "Alpha", "alpha alpha dragon mountain", ("alpha",))]
    match_vectorised_sync(first_only, MSGS, emb.embed_sync, cache=cache)
    both = [
        _orm("dup", "Alpha", "alpha alpha dragon mountain", ("alpha",)),
        _orm("dup", "Beta", "beta bread bread dawn market", ("beta",)),
    ]
    cached = match_vectorised_sync(both, MSGS, emb.embed_sync, cache=cache)
    uncached = match_vectorised_sync(both, MSGS, emb.embed_sync)
    assert cached == uncached


class PlainAfterMismatchEmbedder:
    """Declares (p, declared); first call ANSWERS (p, actual)
    as an EmbeddingResult, the re-embed call answers with a
    PLAIN list (no provenance at all)."""

    def __init__(self):
        self.provenance = EmbeddingProvenance(provider="p", model="declared", dims=8, version="1")
        self.calls = []

    def _vector(self, text):
        digest = hashlib.sha256(f"actual:{text}".encode()).digest()
        return tuple(digest[i % len(digest)] / 255.0 for i in range(8))

    def embed_sync(self, texts):
        self.calls.append(list(texts))
        vectors = tuple(self._vector(t) for t in texts)
        if len(self.calls) == 1:
            return EmbeddingResult(vectors=vectors, provenance=EmbeddingProvenance(provider="p", model="actual", dims=8, version="1"))
        return list(vectors)


def test_mismatch_reembed_plain_list_stores_nothing():
    # D5: vectors from an unprovenanced re-embed must NOT be
    # stored under the discarded space (or any space): the tick
    # uses them, the cache keeps only what was verified.
    honest = CountingSyncEmbedder(provider="p", model="declared")
    cache = EntryVectorCache()
    match_vectorised_sync(book(), MSGS, honest.embed_sync, cache=cache)
    assert len(cache) == 3
    liar = PlainAfterMismatchEmbedder()
    out = match_vectorised_sync(book(), MSGS, liar.embed_sync, cache=cache)
    assert len(liar.calls) == 2 and len(liar.calls[1]) == 4
    assert len(cache) == 3  # nothing new stored, nothing poisoned
    plain = CountingPlainListEmbedder()
    plain._provider = "actual"  # same vector seed family check below
    # outcome uses the re-embedded vectors: compare against the
    # same vectors scored uncached via a provenance twin
    twin = CountingSyncEmbedder(provider="p", model="actual")
    twin._vector = liar._vector  # identical vector function
    assert out.scores == match_vectorised_sync(book(), MSGS, twin.embed_sync).scores


class ZeroDimsAsyncBackend(FakeEmbeddingBackend):
    """model_info declares dims=0 (Ollama-style); embed answers
    with its real dims in provenance."""

    def __init__(self, dims, model="am-1"):
        super().__init__(dims=dims, model=model)
        self.calls = []

    def model_info(self):
        info = super().model_info()
        return type(info)(model_id=info.model_id, provider=info.provider, dims=0, version=info.version)

    async def embed(self, texts):
        self.calls.append(list(texts))
        return await super().embed(texts)


async def test_async_zero_declared_dims_change_discards():
    # D3 backstop: with dims undeclared (0), a warm cache filled
    # at dims=8 must not serve 8-dim vectors into a dims=4 tick;
    # the answered query length exposes the stale vectors and
    # the tick re-embeds, equalling the uncached outcome.
    backend_a = ZeroDimsAsyncBackend(dims=8)
    cache = EntryVectorCache()
    await match_vectorised(book(), MSGS, backend=backend_a, cache=cache)
    backend_b = ZeroDimsAsyncBackend(dims=4)
    out = await match_vectorised(book(), MSGS, backend=backend_b, cache=cache)
    assert len(backend_b.calls) == 2
    assert len(backend_b.calls[0]) == 1 and len(backend_b.calls[1]) == 4
    assert out == await match_vectorised(book(), MSGS, backend=ZeroDimsAsyncBackend(dims=4))
