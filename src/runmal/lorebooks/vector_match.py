"""Vectorised lore matching (P-041).

Roadmap line: *Vectorised lore: embedding-matched entries for
large books, on the founding RAG stack, with keyword fallback.*

Before this slice the vectorised activation kind (P-035) was
dormant in the live paths: ``activate()`` honoured caller-supplied
``vector_hit_ids`` but nothing in Rúnmál computed them. This
module is the matcher that computes them, on the founding RAG
stack -- the S304 embedding seam
(``runmal.backends.embeddings.EmbeddingBackend`` +
``embed_or_fallback``), the S311 provenance discipline (a match
only ever compares vectors from ONE embedding call, one space;
spaces never mix, INV-019), and the S401 cosine contract.

Semantics (normative):
- Only vectorised-kind entries are candidates: enabled, not
  constant (constant dominates and fires anyway), derived kind
  ``vectorised`` (P-035). Selective entries are never touched
  here; their keyword path is the scanner's alone.
- The query text is the scan window the keyword scanner would
  see (P-037 ``ScanSettings`` over the messages plus, when the
  book admits it, the external segment), joined in window order.
  Vector matching and keyword scanning look at the same context.
- Each candidate's embed text is its name, its keys, and its
  content -- the three things an author declares the entry to be
  about. Query and candidates are embedded in ONE batched
  ``embed()`` call (one round trip however large the book; the
  per-entry cost is the provider's, and the S204 token-budget
  pass still bounds what actually injects).
- A candidate is a vector hit when its cosine similarity to the
  query is >= the threshold (default ``DEFAULT_VECTOR_THRESHOLD``,
  per-call overridable). Hits are ranked by score descending
  (ties: input order, then entry id -- deterministic), and the
  ranked list may be capped by ``max_entries`` (the per-extension
  max-entries cap P-035 left to this slice); the cap drops the
  LOWEST-ranked hits and is reported, never silent.
- Keyword fallback (the deliberate P-041 design, closing P-035's
  kind exclusivity for the degraded cases only): when embeddings
  are unavailable -- no backend, a backend error, or the S304
  FTS-fallback result -- OR when no candidate reaches the
  threshold, vectorised entries fall back to keyword matching
  over the same window, reusing the S202 scan core with the
  entry's own keys / secondary keys / selective logic / whole-
  word / case flags. Fallback hits fire via
  ``"vector_fallback"`` (activation.py), never disguised as
  vector hits. When at least one vector hit lands, the keyword
  fallback does NOT run: the threshold would be meaningless if
  every keyed entry got a second chance on a working vector tick.
- Degradation is a documented result, never a crash: every
  failure mode lands in the outcome's ``degraded`` /
  ``fallback_reason`` fields with the mode ``"keyword_fallback"``
  or ``"none"``.

The deterministic local provider: ``LocalEmbeddingBackend``
implements the repo's own ``EmbeddingBackend`` interface with a
hashed token + character-ngram bag (light suffix stemming), so
vectorised lore works -- and is testable -- with no external
provider configured. It is a lexical-semantic surrogate, honestly
labelled (provider ``"local"``, model ``"hash-ngram-1"``): it
matches paraphrases that share stems/roots, not true neural
semantics. When the owner has an active embedding profile (S311
activation), :func:`resolve_lore_embedding_backend` builds THAT
profile's backend instead (Ollama / OpenAI-compatible / Aesir /
fake, per ``backends.profiles.build_embedding_backend``); the
local backend is only the no-profile default.

Stored entry-vector cache (P-046, closing the P-041 debt in
part): :class:`EntryVectorCache` is an opt-in, in-memory,
per-process bounded LRU the matchers accept via ``cache=``.
On a cache hit only the query and changed/new candidate texts
are embedded; cached candidate vectors are reused. Cache keys
carry the embedding space (entry id, embed-text hash,
provider, model, dims, version -- the full
``EmbeddingProvenance.key()`` identity), so a space switch
misses structurally and spaces never mix (INV-019); an
answered space that contradicts the declared one, or cached
vectors whose length contradicts the answered query, are
discarded and re-embedded, never mixed. The query vector is never
cached. This is deliberately only the in-process half of the
debt: there is NO persistent or database-backed vector store
in this slice (no migration was added); a cache dies with
its process, and a cold cache behaves exactly like the
uncached path.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import OrderedDict
from dataclasses import dataclass, field, replace
from functools import lru_cache

from runmal.backends.embeddings import (
    EmbeddingBackend,
    EmbeddingProvenance,
    EmbeddingResult,
    FtsFallbackResult,
    embed_or_fallback,
)
from runmal.backends.models import HealthStatus
from runmal.lorebooks.scan import ScanEntry, ScanHit, scan_entries_windowed
from runmal.lorebooks.states import KIND_VECTORISED, activation_kind_for, normalise_vectorised
from runmal.lorebooks.windows import ScanSettings, build_scan_window

#: Default cosine threshold for a vector hit. Calibrated against
#: the local provider: stem-sharing paraphrases score ~0.35-0.9,
#: unrelated texts ~0.0-0.15 (battery-pinned ranges).
DEFAULT_VECTOR_THRESHOLD = 0.30

#: Local provider identity (provenance is reported on every match).
LOCAL_PROVIDER = "local"
LOCAL_MODEL = "hash-ngram-1"
DEFAULT_LOCAL_DIMS = 256

__all__ = [
    "DEFAULT_VECTOR_THRESHOLD",
    "LOCAL_PROVIDER",
    "LOCAL_MODEL",
    "DEFAULT_LOCAL_DIMS",
    "VectorCandidate",
    "VectorMatchOutcome",
    "LocalEmbeddingBackend",
    "check_vector_threshold",
    "normalise_vector_threshold",
    "check_max_vector_entries",
    "normalise_max_vector_entries",
    "cosine_similarity",
    "vector_candidates",
    "entry_embed_text",
    "keyword_fallback_hits",
    "match_with_vectors",
    "match_vectorised",
    "match_vectorised_sync",
    "EntryVectorCache",
    "resolve_lore_embedding_backend",
]


# --- Vocabulary: threshold + cap -------------------------------------------


def check_vector_threshold(value) -> float:
    """Strict validation: a real number in [-1, 1] (bool rejected)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"vector threshold must be a number: {value!r}")
    result = float(value)
    if result < -1.0 or result > 1.0:
        raise ValueError(f"vector threshold must be in [-1, 1]: {value!r}")
    return result


def normalise_vector_threshold(value, default: float = DEFAULT_VECTOR_THRESHOLD) -> float:
    """Tolerant normaliser: valid -> itself, anything else -> default."""
    if value is None:
        return default
    try:
        return check_vector_threshold(value)
    except ValueError:
        return default


def check_max_vector_entries(value) -> int | None:
    """Strict validation: None (no cap) or an int >= 1 (bool rejected)."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError(f"max vector entries must be an int >= 1 or None: {value!r}")
    return value


def normalise_max_vector_entries(value) -> int | None:
    """Tolerant normaliser: valid -> itself, anything else -> None."""
    try:
        return check_max_vector_entries(value)
    except ValueError:
        return None


# --- Candidates --------------------------------------------------------------


def _decode_keys(entry) -> tuple[str, ...]:
    """Keys from an ORM row (``keys_json``) or a plain ``keys`` attr."""
    keys = getattr(entry, "keys", None)
    if isinstance(keys, (list, tuple)):
        return tuple(str(k) for k in keys)
    raw = getattr(entry, "keys_json", None)
    if isinstance(raw, str):
        import json as _json

        try:
            decoded = _json.loads(raw)
        except _json.JSONDecodeError:
            return ()
        if isinstance(decoded, list):
            return tuple(str(k) for k in decoded)
    return ()


@dataclass(frozen=True)
class VectorCandidate:
    """One vectorised-kind entry, as the matcher sees it."""

    id: str
    name: str = ""
    keys: tuple[str, ...] = ()
    content: str = ""

    @property
    def embed_text(self) -> str:
        """The text embedded for this entry: name, keys, content."""
        return entry_embed_text(self.name, self.keys, self.content)

    @classmethod
    def from_orm(cls, entry) -> VectorCandidate:
        return cls(
            id=str(entry.id),
            name=str(getattr(entry, "name", "") or ""),
            keys=_decode_keys(entry),
            content=str(getattr(entry, "content", "") or ""),
        )


def entry_embed_text(name: str, keys, content: str) -> str:
    """The embed text for an entry: name + keys + content, in that order."""
    parts = [str(name or "").strip(), " ".join(str(k) for k in keys), str(content or "")]
    return "\n".join(part for part in parts if part.strip())


def vector_candidates(entries) -> list[VectorCandidate]:
    """The vectorised-kind candidates among ``entries``, input order.

    Disabled entries and constant entries are excluded (constant
    dominates in P-035's precedence and fires without any hit);
    selective entries belong to the keyword scanner alone.
    """
    out: list[VectorCandidate] = []
    for entry in entries:
        if not bool(getattr(entry, "enabled", True)):
            continue
        kind = activation_kind_for(
            bool(getattr(entry, "constant", False)),
            normalise_vectorised(getattr(entry, "vectorised", None)),
        )
        if kind != KIND_VECTORISED:
            continue
        out.append(VectorCandidate.from_orm(entry))
    return out



# --- Stored entry-vector cache (P-046) ---------------------------------------


def _embed_text_sha256(text: str) -> str:
    return hashlib.sha256(str(text).encode("utf-8")).hexdigest()


class EntryVectorCache:
    """In-memory stored-vector cache (P-046; P-041 debt, partial).

    Key shape: ``(entry_id, sha256(embed_text), provider,
    model, dims, version)`` -- the embedding space is the
    codebase's own ``EmbeddingProvenance.key()`` identity.
    Provenance is IN the key, so a provider/model/dims/version
    switch misses instead of ever mixing
    spaces (INV-019); an edit to an entry's name/keys/content
    changes its embed text, hence its hash, hence its key --
    invalidation is by content hash, with no explicit hooks.
    The query vector is NEVER stored here: callers only ever
    ``put`` candidate vectors. Bounded LRU (default 20,000
    vectors, per the P-046 design): eviction never changes
    outcomes, only speed. In-memory and per-process ONLY: no
    DB/persistent store exists yet (the recorded remainder
    of the P-041 debt). ``hits``/``misses`` count ``get`` calls.
    """

    def __init__(self, maxsize: int = 20000):
        if isinstance(maxsize, bool) or not isinstance(maxsize, int) or maxsize < 1:
            raise ValueError("cache maxsize must be an int >= 1")
        self._maxsize = maxsize
        self._store: OrderedDict = OrderedDict()
        self._dims_by_space: dict = {}
        self.hits = 0
        self.misses = 0

    @property
    def maxsize(self) -> int:
        return self._maxsize

    def __len__(self) -> int:
        return len(self._store)

    def clear(self) -> None:
        self._store.clear()
        self._dims_by_space.clear()
        self.hits = 0
        self.misses = 0

    def _key(self, entry_id, embed_text, provider, model, dims, version=""):
        return (
            str(entry_id),
            _embed_text_sha256(embed_text),
            str(provider),
            str(model),
            int(dims),
            str(version),
        )

    def get(self, entry_id, embed_text, provider, model, dims=None, version=""):
        """Cached vector for one entry in one space, or None.

        ``dims`` may be omitted when the caller does not know
        the space's dims up front (some backends report dims=0
        in ``model_info``); the dims of the last vector stored
        for the same (entry, text, provider, model) are then
        used. A dims mismatch when dims IS given is a miss.
        """
        if dims:
            key = self._key(entry_id, embed_text, provider, model, dims, version)
        else:
            idx = (
                str(entry_id),
                _embed_text_sha256(embed_text),
                str(provider),
                str(model),
                str(version),
            )
            known = self._dims_by_space.get(idx)
            if known is None:
                self.misses += 1
                return None
            key = self._key(entry_id, embed_text, provider, model, known, version)
        vector = self._store.get(key)
        if vector is None:
            self.misses += 1
            return None
        self._store.move_to_end(key)
        self.hits += 1
        return vector

    def put(self, entry_id, embed_text, vector, provider, model, dims=None, version=""):
        """Store one candidate vector under its space-tagged key."""
        vec = tuple(vector)
        # A vector's true dims are its length; a declared dims
        # that disagrees is never trusted over the vector itself.
        if not dims or int(dims) != len(vec):
            dims = len(vec)
        key = self._key(entry_id, embed_text, provider, model, dims, version)
        self._store[key] = vec
        self._store.move_to_end(key)
        self._dims_by_space[(key[0], key[1], key[2], key[3], key[5])] = key[4]
        while len(self._store) > self._maxsize:
            old_key, _ = self._store.popitem(last=False)
            idx = (old_key[0], old_key[1], old_key[2], old_key[3], old_key[5])
            if self._dims_by_space.get(idx) == old_key[4]:
                del self._dims_by_space[idx]
        return vec


def _space_from_provenance_dict(provenance) -> tuple | None:
    if not provenance:
        return None
    provider = provenance.get("provider")
    model = provenance.get("model")
    if not provider or not model:
        return None
    return (
        str(provider),
        str(model),
        provenance.get("dims") or None,
        str(provenance.get("version") or ""),
    )


def _declared_space(owner) -> tuple | None:
    """(provider, model, dims|None, version) an embedder declares.

    The space identity is ``EmbeddingProvenance.key()``:
    provider, model, dims, version -- all four, always.
    """
    if owner is None:
        return None
    prov = getattr(owner, "provenance", None)
    if prov is not None:
        try:
            return (
                str(prov.provider),
                str(prov.model),
                prov.dims or None,
                str(getattr(prov, "version", "") or ""),
            )
        except Exception:
            pass
    try:
        info = owner.model_info()
    except Exception:
        return None
    if info is None or not getattr(info, "provider", None) or not getattr(info, "model_id", None):
        return None
    return (
        str(info.provider),
        str(info.model_id),
        getattr(info, "dims", None) or None,
        str(getattr(info, "version", "") or ""),
    )


def _sync_embedder_space(embed_texts) -> tuple | None:
    return _declared_space(getattr(embed_texts, "__self__", None))


def _cache_space_mismatch(space, actual, query_vector, cached_by_idx) -> bool:
    """True when cached vectors must be discarded (INV-019).

    The embedder's ANSWER is the authority: cached vectors are
    unusable when the answered space differs from the space the
    cache was read under in provider, model or version, or in
    dims when both sides state them -- or when any cached
    vector's length differs from the answered query vector's
    length (the dims check that needs no provenance at all, and
    the backstop for backends that declare dims=0).
    """
    if not cached_by_idx:
        return False
    if actual is not None and space is not None:
        if actual[0] != space[0] or actual[1] != space[1] or actual[3] != space[3]:
            return True
        if actual[2] and space[2] and actual[2] != space[2]:
            return True
    query_len = len(query_vector)
    return any(len(vec) != query_len for vec in cached_by_idx.values())


# --- Scoring (pure) ----------------------------------------------------------


def cosine_similarity(a, b) -> float:
    """Cosine similarity; dims must match (one space, INV-019)."""
    if len(a) != len(b):
        raise ValueError(f"vector dims differ: {len(a)} != {len(b)}")
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def _cosine_precomputed_query_norm(a, norm_a: float, b) -> float:
    """``cosine_similarity`` with the query norm hoisted (P-046).

    Arithmetic identical to :func:`cosine_similarity` (same dot
    order, same norm_b, same ``dot / (norm_a * norm_b)``);
    ``match_with_vectors`` uses this so the query norm is
    computed once per tick, not once per candidate (scout-
    indicted). Callers guarantee ``len(a) == len(b)``.
    """
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    norm_b = math.sqrt(sum(y * y for y in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@dataclass(frozen=True)
class VectorMatchOutcome:
    """One matcher tick's honest result.

    ``mode`` is ``"vector"`` (embedding hits fired), ``"keyword_
    fallback"`` (the degraded/below-threshold keyword path fired),
    or ``"none"``. ``hit_ids`` are vector hits (input order);
    ``fallback_ids`` are keyword-fallback hits (input order);
    ``scores`` carries every scored candidate's cosine (so a
    below-threshold score is inspectable, not hidden); ``ranked``
    is the full ranked list ``((entry_id, score), ...)`` best
    first; ``capped`` counts ranked hits the cap dropped.
    """

    hit_ids: tuple[str, ...] = ()
    fallback_ids: tuple[str, ...] = ()
    scores: dict = field(default_factory=dict)
    ranked: tuple = ()
    provenance: dict | None = None
    degraded: bool = False
    mode: str = "none"
    fallback_reason: str = ""
    capped: int = 0
    candidates: int = 0
    keyword_hits: tuple = ()

    def to_dict(self) -> dict:
        return {
            "mode": self.mode,
            "degraded": self.degraded,
            "fallback_reason": self.fallback_reason,
            "hit_ids": list(self.hit_ids),
            "fallback_ids": list(self.fallback_ids),
            "scores": dict(self.scores),
            "ranked": [[entry_id, score] for entry_id, score in self.ranked],
            "provenance": self.provenance,
            "capped": self.capped,
            "candidates": self.candidates,
        }


# --- Keyword fallback ----------------------------------------------------------


def keyword_fallback_hits(entries, messages, settings=None, external_context=()) -> list[ScanHit]:
    """Keyword-scan the vectorised candidates over the scan window.

    Reuses the S202 core exactly: each candidate is flipped to a
    non-vectorised ``ScanEntry`` (the one deliberate un-skip) and
    scanned with its own keys, secondary keys, selective logic,
    whole-word and case flags over the P-037 window. Only
    vectorised-kind entries are flipped -- selective entries were
    already scanned by the caller's normal pass and are never
    double-reported here.
    """
    settings = settings or ScanSettings.normalised()
    candidates = vector_candidates(entries)
    if not candidates:
        return []
    candidate_ids = {c.id for c in candidates}
    flipped = [
        replace(view, vectorised=False)
        for view in (ScanEntry.from_orm(e) for e in entries)
        if view.id in candidate_ids
    ]
    return scan_entries_windowed(flipped, list(messages), settings, list(external_context or ()))


def _fallback_outcome(
    entries,
    messages,
    *,
    settings,
    external_context,
    keyword_fallback: bool,
    reason: str,
    provenance: dict | None,
    scores: dict,
    ranked: tuple,
    candidates: int,
    degraded: bool = True,
) -> VectorMatchOutcome:
    fb_hits: list[ScanHit] = []
    if keyword_fallback:
        fb_hits = keyword_fallback_hits(entries, messages, settings, external_context)
    fallback_ids = tuple(h.entry_id for h in fb_hits)
    return VectorMatchOutcome(
        hit_ids=(),
        fallback_ids=fallback_ids,
        scores=scores,
        ranked=ranked,
        provenance=provenance,
        degraded=degraded,
        mode="keyword_fallback" if fallback_ids else "none",
        fallback_reason=reason,
        capped=0,
        candidates=candidates,
        keyword_hits=tuple(fb_hits),
    )


def match_with_vectors(
    entries,
    messages,
    query_vector,
    entry_vectors,
    *,
    provenance: dict | None = None,
    threshold=None,
    max_entries=None,
    settings=None,
    external_context=(),
    keyword_fallback: bool = True,
) -> VectorMatchOutcome:
    """Score precomputed vectors (pure). ``entry_vectors`` maps id -> vector.

    A candidate whose vector is missing or whose dims differ from
    the query's is unscored (never mixed across spaces); if NO
    candidate can be scored the tick degrades to the fallback with
    reason ``"no_comparable_vectors"``.
    """
    settings = settings or ScanSettings.normalised()
    threshold = normalise_vector_threshold(threshold)
    max_entries = normalise_max_vector_entries(max_entries)
    candidates = vector_candidates(entries)
    if not candidates:
        return VectorMatchOutcome(candidates=0)
    scores: dict[str, float] = {}
    query_norm = math.sqrt(sum(x * x for x in query_vector))
    for candidate in candidates:
        vector = entry_vectors.get(candidate.id)
        if vector is None or len(vector) != len(query_vector):
            continue
        scores[candidate.id] = _cosine_precomputed_query_norm(
            query_vector, query_norm, vector
        )
    if not scores:
        return _fallback_outcome(
            entries, messages, settings=settings, external_context=external_context,
            keyword_fallback=keyword_fallback, reason="no_comparable_vectors",
            provenance=provenance, scores={}, ranked=(), candidates=len(candidates),
        )
    order = {c.id: i for i, c in enumerate(candidates)}
    ranked = tuple(
        sorted(scores.items(), key=lambda kv: (-kv[1], order[kv[0]], kv[0]))
    )
    hits_ranked = [entry_id for entry_id, score in ranked if score >= threshold]
    capped = 0
    if max_entries is not None and len(hits_ranked) > max_entries:
        capped = len(hits_ranked) - max_entries
        hits_ranked = hits_ranked[:max_entries]
    if hits_ranked:
        hit_set = set(hits_ranked)
        return VectorMatchOutcome(
            hit_ids=tuple(c.id for c in candidates if c.id in hit_set),
            scores=scores, ranked=ranked, provenance=provenance,
            mode="vector", capped=capped, candidates=len(candidates),
        )
    # Below threshold is NOT degradation: embeddings worked, they
    # simply matched nothing -- the fallback is a matching outcome.
    return _fallback_outcome(
        entries, messages, settings=settings, external_context=external_context,
        keyword_fallback=keyword_fallback, reason="below_threshold",
        provenance=provenance, scores=scores, ranked=ranked,
        candidates=len(candidates), degraded=False,
    )


# --- Matchers (sync core + async seam) -----------------------------------------


def _window_query_text(messages, settings, external_context) -> str:
    window = build_scan_window(settings, list(messages), list(external_context or ()))
    return "\n".join(window.texts)


def match_vectorised_sync(
    entries,
    messages,
    embed_texts,
    *,
    threshold=None,
    max_entries=None,
    settings=None,
    external_context=(),
    keyword_fallback: bool = True,
    cache: EntryVectorCache | None = None,
) -> VectorMatchOutcome:
    """Sync matcher for the sync preview path.

    ``embed_texts`` is a callable taking the text list
    ``[query, *candidate_texts]`` and returning an
    ``EmbeddingResult`` or a plain sequence of vectors; returning
    None or raising means embeddings are unavailable and the tick
    degrades to the keyword fallback.

    ``cache`` (P-046): optional :class:`EntryVectorCache`. When
    the embedder's space is known up front (a bound backend
    method such as ``LocalEmbeddingBackend.embed_sync`` declares
    one), cached candidate vectors are reused and only the query
    plus cache-miss candidate texts are embedded, in ONE batched
    call; the result provenance is checked against the cache
    space and a mismatch discards the cached vectors and
    re-embeds everything rather than mixing spaces (INV-019).
    When the space cannot be known up front, nothing is reused
    (fresh vectors are still stored, tagged with the result
    provenance when it carries one). ``cache=None`` (the
    default) is exactly the pre-P-046 behaviour.
    """
    settings = settings or ScanSettings.normalised()
    candidates = vector_candidates(entries)
    if not candidates:
        return VectorMatchOutcome(candidates=0)
    query_text = _window_query_text(messages, settings, external_context)
    if not query_text.strip():
        return VectorMatchOutcome(candidates=len(candidates))
    texts = [c.embed_text for c in candidates]
    space = _sync_embedder_space(embed_texts) if cache is not None else None
    cached_by_idx: dict[int, tuple] = {}
    miss_idx: list[int] = list(range(len(candidates)))
    if cache is not None and space is not None:
        miss_idx = []
        for i, cand in enumerate(candidates):
            vec = cache.get(cand.id, texts[i], space[0], space[1], space[2], space[3])
            if vec is None:
                miss_idx.append(i)
            else:
                cached_by_idx[i] = vec
    try:
        result = embed_texts([query_text] + [texts[i] for i in miss_idx])
    except Exception:
        result = None
    if result is None:
        return _fallback_outcome(
            entries, messages, settings=settings, external_context=external_context,
            keyword_fallback=keyword_fallback, reason="embeddings_unavailable",
            provenance=None, scores={}, ranked=(), candidates=len(candidates),
        )
    if isinstance(result, EmbeddingResult):
        vectors = result.vectors
        provenance = result.provenance.to_dict()
    else:
        vectors = result
        provenance = None
    if len(vectors) != 1 + len(miss_idx):
        return _fallback_outcome(
            entries, messages, settings=settings, external_context=external_context,
            keyword_fallback=keyword_fallback, reason="vector_count_mismatch",
            provenance=provenance, scores={}, ranked=(), candidates=len(candidates),
        )
    actual = _space_from_provenance_dict(provenance) or space
    if _cache_space_mismatch(space, actual, vectors[0], cached_by_idx):
        # Embedder answered from a different space than the cache
        # was read under: never mix -- discard, re-embed all.
        cached_by_idx = {}
        miss_idx = list(range(len(candidates)))
        try:
            result = embed_texts([query_text] + texts)
        except Exception:
            result = None
        if result is None:
            return _fallback_outcome(
                entries, messages, settings=settings, external_context=external_context,
                keyword_fallback=keyword_fallback, reason="embeddings_unavailable",
                provenance=None, scores={}, ranked=(), candidates=len(candidates),
            )
        if isinstance(result, EmbeddingResult):
            vectors = result.vectors
            provenance = result.provenance.to_dict()
        else:
            vectors = result
            provenance = None
        if len(vectors) != 1 + len(candidates):
            return _fallback_outcome(
                entries, messages, settings=settings, external_context=external_context,
                keyword_fallback=keyword_fallback, reason="vector_count_mismatch",
                provenance=provenance, scores={}, ranked=(), candidates=len(candidates),
            )
        actual = _space_from_provenance_dict(provenance)  # never the discarded space
    if cache is not None and actual is not None:
        for j, i in enumerate(miss_idx):
            cache.put(candidates[i].id, texts[i], vectors[j + 1], actual[0], actual[1], actual[2], actual[3])
    fresh_by_idx = {i: vectors[j + 1] for j, i in enumerate(miss_idx)}
    entry_vectors = {}
    for i, cand in enumerate(candidates):
        # Candidate order, so a duplicate id resolves last-wins
        # exactly as the uncached dict build does.
        if i in cached_by_idx:
            entry_vectors[cand.id] = cached_by_idx[i]
        elif i in fresh_by_idx:
            entry_vectors[cand.id] = fresh_by_idx[i]
    return match_with_vectors(
        entries, messages, vectors[0], entry_vectors, provenance=provenance,
        threshold=threshold, max_entries=max_entries, settings=settings,
        external_context=external_context, keyword_fallback=keyword_fallback,
    )



async def match_vectorised(
    entries,
    messages,
    *,
    backend: EmbeddingBackend | None = None,
    threshold=None,
    max_entries=None,
    settings=None,
    external_context=(),
    keyword_fallback: bool = True,
    cache: EntryVectorCache | None = None,
) -> VectorMatchOutcome:
    """Async matcher on the founding RAG stack (S304 seam).

    Embeds the window query text and every candidate in ONE
    batched call through ``embed_or_fallback``: a ``BackendError``
    (or any backend exception) degrades to the keyword fallback
    with the reason recorded -- never a crash, never a silently
    mixed space (all compared vectors come from this one call).

    ``cache`` (P-046): optional :class:`EntryVectorCache`; the
    same contract as :func:`match_vectorised_sync` -- only the
    query and cache-miss candidates are embedded, the backend's
    declared space (``model_info``) keys the cache, and the
    result provenance is verified before any cached vector is
    used. ``cache=None`` (default) is pre-P-046 behaviour.
    """
    settings = settings or ScanSettings.normalised()
    candidates = vector_candidates(entries)
    if not candidates:
        return VectorMatchOutcome(candidates=0)
    if backend is None:
        return _fallback_outcome(
            entries, messages, settings=settings, external_context=external_context,
            keyword_fallback=keyword_fallback, reason="no_backend",
            provenance=None, scores={}, ranked=(), candidates=len(candidates),
        )
    query_text = _window_query_text(messages, settings, external_context)
    if not query_text.strip():
        return VectorMatchOutcome(candidates=len(candidates))
    texts = [c.embed_text for c in candidates]
    space = _declared_space(backend) if cache is not None else None
    cached_by_idx: dict[int, tuple] = {}
    miss_idx: list[int] = list(range(len(candidates)))
    if cache is not None and space is not None:
        miss_idx = []
        for i, cand in enumerate(candidates):
            vec = cache.get(cand.id, texts[i], space[0], space[1], space[2], space[3])
            if vec is None:
                miss_idx.append(i)
            else:
                cached_by_idx[i] = vec
    try:
        result = await embed_or_fallback(
            backend, [query_text] + [texts[i] for i in miss_idx]
        )
    except Exception as exc:  # a broken backend degrades, never crashes lore
        return _fallback_outcome(
            entries, messages, settings=settings, external_context=external_context,
            keyword_fallback=keyword_fallback,
            reason=f"backend_error:{type(exc).__name__}",
            provenance=None, scores={}, ranked=(), candidates=len(candidates),
        )
    if isinstance(result, FtsFallbackResult):
        return _fallback_outcome(
            entries, messages, settings=settings, external_context=external_context,
            keyword_fallback=keyword_fallback,
            reason=result.reason or "embeddings_unavailable",
            provenance=result.provenance.to_dict() if result.provenance else None,
            scores={}, ranked=(), candidates=len(candidates),
        )
    vectors = result.vectors
    provenance = result.provenance.to_dict()
    if len(vectors) != 1 + len(miss_idx):
        return _fallback_outcome(
            entries, messages, settings=settings, external_context=external_context,
            keyword_fallback=keyword_fallback, reason="vector_count_mismatch",
            provenance=provenance, scores={}, ranked=(), candidates=len(candidates),
        )
    actual = _space_from_provenance_dict(provenance) or space
    if _cache_space_mismatch(space, actual, vectors[0], cached_by_idx):
        cached_by_idx = {}
        miss_idx = list(range(len(candidates)))
        try:
            result = await embed_or_fallback(backend, [query_text] + texts)
        except Exception as exc:
            return _fallback_outcome(
                entries, messages, settings=settings, external_context=external_context,
                keyword_fallback=keyword_fallback,
                reason=f"backend_error:{type(exc).__name__}",
                provenance=None, scores={}, ranked=(), candidates=len(candidates),
            )
        if isinstance(result, FtsFallbackResult):
            return _fallback_outcome(
                entries, messages, settings=settings, external_context=external_context,
                keyword_fallback=keyword_fallback,
                reason=result.reason or "embeddings_unavailable",
                provenance=result.provenance.to_dict() if result.provenance else None,
                scores={}, ranked=(), candidates=len(candidates),
            )
        vectors = result.vectors
        provenance = result.provenance.to_dict()
        if len(vectors) != 1 + len(candidates):
            return _fallback_outcome(
                entries, messages, settings=settings, external_context=external_context,
                keyword_fallback=keyword_fallback, reason="vector_count_mismatch",
                provenance=provenance, scores={}, ranked=(), candidates=len(candidates),
            )
        actual = _space_from_provenance_dict(provenance)  # never the discarded space
    if cache is not None and actual is not None:
        for j, i in enumerate(miss_idx):
            cache.put(candidates[i].id, texts[i], vectors[j + 1], actual[0], actual[1], actual[2], actual[3])
    fresh_by_idx = {i: vectors[j + 1] for j, i in enumerate(miss_idx)}
    entry_vectors = {}
    for i, cand in enumerate(candidates):
        # Candidate order, so a duplicate id resolves last-wins
        # exactly as the uncached dict build does.
        if i in cached_by_idx:
            entry_vectors[cand.id] = cached_by_idx[i]
        elif i in fresh_by_idx:
            entry_vectors[cand.id] = fresh_by_idx[i]
    return match_with_vectors(
        entries, messages, vectors[0], entry_vectors, provenance=provenance,
        threshold=threshold, max_entries=max_entries, settings=settings,
        external_context=external_context, keyword_fallback=keyword_fallback,
    )



# --- Deterministic local provider ----------------------------------------------

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_SUFFIXES = ("ingly", "edly", "ing", "ed", "es", "ly", "s")

#: Function words carry no aboutness; excluding them keeps
#: unrelated texts that merely share grammar near zero.
_STOPWORDS = frozenset({
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "by",
    "for", "with", "from", "as", "is", "was", "were", "are", "be",
    "been", "it", "its", "she", "he", "they", "we", "you", "her", "his",
    "their", "our", "your", "that", "this", "those", "these", "there",
    "here", "when", "where", "who", "what", "which", "into", "upon",
    "about", "above", "over", "under", "between", "through", "during",
    "before", "after", "again", "once", "just", "very", "too", "also",
    "not", "no", "if", "but", "so", "than", "then", "now", "had", "has",
    "have", "do", "does", "did", "will", "would", "can", "could", "may",
    "might", "must", "shall", "should",
})


def _stem(token: str) -> str:
    """Light suffix stemming: dragons->dragon, flying->fly, peaks->peak."""
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def _tokens(text: str) -> list[str]:
    return [
        _stem(tok)
        for tok in _TOKEN_RE.findall(str(text).lower())
        if len(tok) >= 2 and tok not in _STOPWORDS
    ]


# P-046: memoised -- this pure sha256 projection was called per
# token/trigram per text per tick (scout-indicted hot spot).
@lru_cache(maxsize=65536)
def _feature_bucket(feature: str, dims: int) -> tuple[int, float]:
    digest = hashlib.sha256(feature.encode("utf-8")).digest()
    bucket = int.from_bytes(digest[:4], "little") % dims
    sign = 1.0 if digest[4] % 2 == 0 else -1.0
    return bucket, sign


class LocalEmbeddingBackend(EmbeddingBackend):
    """Deterministic local embeddings on the repo's own seam.

    Hashed bag of stemmed tokens (weight 1.0) plus character
    trigrams of each stem (weight 0.4), signed-hash projected into
    ``dims`` buckets and L2-normalised. Same text -> same vector,
    always; paraphrases sharing stems/roots score high, unrelated
    texts score near zero. This is a lexical-semantic surrogate
    for use when no real provider is configured -- it is NOT a
    neural embedding model and never claims to be one.
    """

    backend_key = "local"

    def __init__(self, dims: int = DEFAULT_LOCAL_DIMS):
        if isinstance(dims, bool) or not isinstance(dims, int) or dims < 8:
            raise ValueError("local embedding dims must be an int >= 8")
        self._dims = dims

    @property
    def provenance(self) -> EmbeddingProvenance:
        return EmbeddingProvenance(
            provider=LOCAL_PROVIDER, model=LOCAL_MODEL, dims=self._dims, version="1"
        )

    def _vector(self, text: str) -> tuple[float, ...]:
        vec = [0.0] * self._dims
        for token in _tokens(text):
            bucket, sign = _feature_bucket(f"tok:{token}", self._dims)
            vec[bucket] += sign * 1.0
            padded = f"#{token}#"
            for i in range(len(padded) - 2):
                bucket, sign = _feature_bucket(f"tri:{padded[i:i + 3]}", self._dims)
                vec[bucket] += sign * 0.4
        norm = math.sqrt(sum(x * x for x in vec))
        if norm == 0:
            return tuple(vec)
        return tuple(x / norm for x in vec)

    def embed_sync(self, texts: list[str]) -> EmbeddingResult:
        """Sync embedding (the preview path is sync); ``embed`` delegates."""
        return EmbeddingResult(
            vectors=tuple(self._vector(t) for t in texts), provenance=self.provenance
        )

    async def embed(self, texts: list[str]) -> EmbeddingResult:
        return self.embed_sync(texts)

    def model_info(self):
        from runmal.backends.embeddings import EmbeddingModelInfo

        return EmbeddingModelInfo(
            model_id=LOCAL_MODEL, provider=LOCAL_PROVIDER, dims=self._dims, version="1"
        )

    async def health_check(self) -> HealthStatus:
        return HealthStatus(ok=True, detail="local deterministic embeddings")


# --- Live-path backend resolution -----------------------------------------------


async def resolve_lore_embedding_backend(session, user_id: str) -> EmbeddingBackend:
    """The backend lore matching should use for this owner.

    The owner's ACTIVE embedding profile (S311 activation table)
    wins when one is set: its backend is built by the profile
    machinery (which may itself be the unavailable backend, in
    which case the matcher degrades to keyword fallback -- the
    owner's explicit configuration is honoured, never silently
    replaced). With no active profile, the deterministic local
    backend is the built-in default so vectorised lore works out
    of the box. Resolution failures fall back to the local
    backend rather than breaking a prompt build.
    """
    try:
        from runmal.backends.embedding_profiles import get_activation
        from runmal.backends.profiles import build_embedding_backend, get_profile

        activation = await get_activation(session, user_id)
        if activation is not None and activation.profile_id:
            profile = await get_profile(session, user_id, activation.profile_id)
            if profile is not None:
                return await build_embedding_backend(session, profile)
    except Exception:
        pass
    return LocalEmbeddingBackend()
