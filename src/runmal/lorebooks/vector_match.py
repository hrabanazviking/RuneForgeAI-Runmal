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
"""

from __future__ import annotations

import hashlib
import math
import re
from dataclasses import dataclass, field, replace

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
    for candidate in candidates:
        vector = entry_vectors.get(candidate.id)
        if vector is None or len(vector) != len(query_vector):
            continue
        scores[candidate.id] = cosine_similarity(query_vector, vector)
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
) -> VectorMatchOutcome:
    """Sync matcher for the sync preview path.

    ``embed_texts`` is a callable taking the text list
    ``[query, *candidate_texts]`` and returning an
    ``EmbeddingResult`` or a plain sequence of vectors; returning
    None or raising means embeddings are unavailable and the tick
    degrades to the keyword fallback.
    """
    settings = settings or ScanSettings.normalised()
    candidates = vector_candidates(entries)
    if not candidates:
        return VectorMatchOutcome(candidates=0)
    query_text = _window_query_text(messages, settings, external_context)
    if not query_text.strip():
        return VectorMatchOutcome(candidates=len(candidates))
    try:
        result = embed_texts([query_text] + [c.embed_text for c in candidates])
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
    entry_vectors = {c.id: vectors[i + 1] for i, c in enumerate(candidates)}
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
) -> VectorMatchOutcome:
    """Async matcher on the founding RAG stack (S304 seam).

    Embeds the window query text and every candidate in ONE
    batched call through ``embed_or_fallback``: a ``BackendError``
    (or any backend exception) degrades to the keyword fallback
    with the reason recorded -- never a crash, never a silently
    mixed space (all compared vectors come from this one call).
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
    try:
        result = await embed_or_fallback(
            backend, [query_text] + [c.embed_text for c in candidates]
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
    if len(vectors) != 1 + len(candidates):
        return _fallback_outcome(
            entries, messages, settings=settings, external_context=external_context,
            keyword_fallback=keyword_fallback, reason="vector_count_mismatch",
            provenance=provenance, scores={}, ranked=(), candidates=len(candidates),
        )
    entry_vectors = {c.id: vectors[i + 1] for i, c in enumerate(candidates)}
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
