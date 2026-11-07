"""Chat search (P-072): full-text + semantic search across all
of the caller's chats, with jump-to-message results.

Roadmap line: *Chat search: full-text + semantic search across
all chats, jump-to-message.* Part V (Chat Surgery).

Design: hidden_files/P072_DESIGN.md. The contract in brief:

- READ-ONLY. Search writes nothing: no message, no ChatEvent,
  no stored index, no stored vectors, no search history. No
  migration was taken (head stays 0038): the full-text index
  is rebuilt per query from stored messages, and semantic
  vectors are computed per query in one batched call and
  discarded. An index that can be rebuilt from stored
  messages is not storage.
- ISOLATION IS STRUCTURAL. The corpus query itself filters
  Chat.user_id == user_id; foreign rows are never loaded,
  scored, counted, or snippeted. The optional chat_id filter
  resolves through service._get_owned_chat first (foreign or
  missing -> None -> the router's 404, the house rule).
- ACTIVE TEXT ONLY. Only message.content is searched (the
  P-065 invariant content == swipes[swipe_id]): inactive swipe
  alternates and variant_history_json are never searched, and
  chat titles never create a hit (titles are P-073 territory).
- FULL-TEXT is deterministic token/phrase scoring in pure
  Python (the pinned formula in score_fulltext). SQLite FTS5
  was rejected on record in the design: it would need a
  migration plus sync triggers across every content-mutating
  road, and bm25 ranks cannot be pinned in a battery.
- SEMANTIC reuses the P-041 road verbatim: ONE backend
  resolved per query (the owner's active embedding profile via
  resolve_lore_embedding_backend, else the deterministic local
  hash-ngram-1 surrogate, honestly labelled in the response
  provenance), ONE batched embed_or_fallback call, cosine via
  lorebooks.vector_match.cosine_similarity, threshold imported
  from vector_match (one threshold, one home), one embedding
  space only (INV-019). A dims mismatch degrades the WHOLE
  query, never a partial result over a mixed space.
- FALLBACK IS LABELLED, NEVER DISGUISED (P-041 precedent):
  when embeddings are unavailable, token scoring runs and the
  response carries mode_used == "keyword_fallback",
  fallback == True, degraded == True and a machine
  fallback_reason. An explicit semantic request that honestly
  finds nothing returns empty AS semantic -- it is never
  silently re-run as keyword. No row produced by token
  scoring is ever returned under mode_used == "semantic".
- JUMP-TO-MESSAGE is data: every result carries chat_id,
  message_id (authoritative) and ordinal (the message's index
  in service.get_history display order, a fast hint).

Performance boundary, stated plainly: this is a linear scan
per query, fresh and interactive at personal-library scale;
it is NOT claimed fluid for 10k-message chats or 10k chats
(P-077 territory). scanned_messages in every response makes
the cost visible; there are no silent corpus caps -- limit
truncates results only, total always reports the full count.
"""

from __future__ import annotations

import re
from collections import Counter

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from runmal.backends.embeddings import (
    EmbeddingResult,
    FtsFallbackResult,
    UnavailableEmbeddingBackend,
    embed_or_fallback,
)
from runmal.chats.service import _get_owned_chat, _ordered_messages
from runmal.db.models import Chat
from runmal.lorebooks import vector_match
from runmal.lorebooks.vector_match import cosine_similarity

__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "MIN_LIMIT",
    "MAX_QUERY_CHARS",
    "SNIPPET_MAX",
    "SNIPPET_CONTEXT",
    "SEMANTIC_THRESHOLD",
    "MODES",
    "SearchError",
    "tokenise",
    "score_fulltext",
    "make_snippet",
    "rank_hits",
    "search_chats",
]

DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MIN_LIMIT = 1
MAX_QUERY_CHARS = 500
SNIPPET_MAX = 240
SNIPPET_CONTEXT = 80
EMBED_TEXT_MAX = 4000
SEMANTIC_THRESHOLD = vector_match.DEFAULT_VECTOR_THRESHOLD
MODES = ("auto", "fulltext", "semantic")

_TOKEN_RE = re.compile(r"[^\W_]+", re.UNICODE)
_SUFFIXES = ("ingly", "edly", "ing", "ed", "es", "ly", "s")
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


class SearchError(ValueError):
    """Caller error in a search request; the router maps it to 422."""


def _stem(token: str) -> str:
    for suffix in _SUFFIXES:
        if token.endswith(suffix) and len(token) - len(suffix) >= 3:
            return token[: -len(suffix)]
    return token


def tokenise(text) -> list[str]:
    """Tokens for scoring: lowercase, word regex, drop tokens
    under 2 chars and stopwords, light suffix stemming.

    Mirrors lorebooks.vector_match._tokens semantics, implemented
    here on purpose (no private cross-module import); the battery
    pins this function directly so any drift is a visible test
    change. Order and duplicates are preserved (frequency counts
    depend on them); query-level dedup happens in search_chats.
    """
    return [
        _stem(tok)
        for tok in _TOKEN_RE.findall(str(text).lower())
        if len(tok) >= 2 and tok not in _STOPWORDS
    ]


def _dedup(tokens: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for tok in tokens:
        if tok not in seen:
            seen.add(tok)
            out.append(tok)
    return out


def _collapse(text: str) -> str:
    return " ".join(str(text).split())


def score_fulltext(query_tokens, content):
    """Score one message's content against deduped query tokens.

    Returns (score, matched_terms) or None when no query token
    matches. The pinned formula:
      token_score   = sum(min(count[t], 4) for t in matched)
      coverage      = len(matched) / len(query_tokens)
      coverage_score = 2.0 * coverage
      phrase_score  = 4.0 when the query has >= 2 tokens and the
                      joined token phrase is a substring of the
                      whitespace-collapsed lowercased content
      score = token_score + coverage_score + phrase_score
    Worked pin: q tokens [dragon, fjord], content "The dragon
    crossed the dragon fjord at dawn" -> 3 + 2.0 + 4.0 = 9.0.
    The phrase is derived from the (stemmed, deduped) query
    tokens joined by single spaces -- score_fulltext receives
    tokens, not the raw query (lead-confirmed reading of the
    design; the worked example pins this reading).
    """
    tokens = _dedup(list(query_tokens))
    if not tokens:
        return None
    counts = Counter(tokenise(content))
    matched = [t for t in tokens if counts.get(t, 0) > 0]
    if not matched:
        return None
    token_score = sum(min(counts[t], 4) for t in matched)
    coverage_score = 2.0 * (len(matched) / len(tokens))
    phrase_score = 0.0
    if len(tokens) >= 2 and " ".join(tokens) in _collapse(content).lower():
        phrase_score = 4.0
    return (round(token_score + coverage_score + phrase_score, 6), matched)


def make_snippet(content, matched_terms, mode="fulltext") -> str:
    """A bounded plain-text snippet (<= SNIPPET_MAX chars plus
    ellipsis markers). Full-text/keyword: anchored on the earliest
    occurrence of any matched term, up to SNIPPET_CONTEXT chars
    before it. Semantic (no literal anchor guaranteed): the head
    of the content. No markup is ever injected server-side."""
    text = _collapse(content)
    if len(text) <= SNIPPET_MAX:
        return text
    if mode == "semantic" or not matched_terms:
        return text[:SNIPPET_MAX] + "..."
    lowered = text.lower()
    anchor = -1
    for term in matched_terms:
        idx = lowered.find(str(term).lower())
        if idx >= 0 and (anchor < 0 or idx < anchor):
            anchor = idx
    if anchor < 0:
        return text[:SNIPPET_MAX] + "..."
    start = max(0, anchor - SNIPPET_CONTEXT)
    end = min(len(text), start + SNIPPET_MAX)
    snippet = text[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(text):
        snippet = snippet + "..."
    return snippet


def rank_hits(hits: list[dict]) -> list[dict]:
    """The one deterministic ordering: (-score, chat_id, ordinal,
    message_id). Rank is the 1-based position after sorting,
    assigned here, before any limit truncation."""
    ordered = sorted(
        hits,
        key=lambda h: (-h["score"], h["chat_id"], h["ordinal"], h["message_id"]),
    )
    for index, hit in enumerate(ordered):
        hit["rank"] = index + 1
    return ordered


def _row(chat, message, ordinal: int, score: float, matched_terms, mode: str) -> dict:
    return {
        "rank": 0,
        "chat_id": chat.id,
        "chat_title": chat.title,
        "message_id": message.id,
        "role": message.role,
        "speaker_name": message.speaker_name,
        "ordinal": ordinal,
        "snippet": make_snippet(message.content, matched_terms, mode),
        "score": round(float(score), 6),
        "matched_terms": list(matched_terms),
        "created_at": message.created_at.isoformat() if message.created_at else None,
    }


def _document(*, query, mode_requested, mode_used, fallback, fallback_reason,
              embedding, chat_id, limit, ranked, scanned_chats, scanned_messages):
    total = len(ranked)
    return {
        "query": query,
        "mode_requested": mode_requested,
        "mode_used": mode_used,
        "fallback": fallback,
        "degraded": fallback,
        "fallback_reason": fallback_reason,
        "embedding": embedding,
        "chat_id": chat_id,
        "limit": limit,
        "total": total,
        "returned": min(total, limit),
        "scanned_chats": scanned_chats,
        "scanned_messages": scanned_messages,
        "results": ranked[:limit],
    }


async def search_chats(session: AsyncSession, user_id: str, q, *,
                       mode: str = "auto", limit=DEFAULT_LIMIT,
                       chat_id: str | None = None, backend=None):
    """Search the caller's own chats. Returns the result document,
    or None when a chat_id filter names a foreign/missing chat
    (the router maps that to the same 404 as any chat road).
    Raises SearchError for caller errors (the router's 422)."""
    if not isinstance(q, str) or not q.strip():
        raise SearchError("q must not be empty")
    query = q.strip()
    if len(query) > MAX_QUERY_CHARS:
        raise SearchError("q is too long (max 500 chars)")
    if mode not in MODES:
        raise SearchError(f"mode must be one of {', '.join(MODES)}: {mode!r}")
    try:
        effective_limit = int(limit)
    except (TypeError, ValueError):
        raise SearchError(f"limit must be an int: {limit!r}") from None
    effective_limit = max(MIN_LIMIT, min(MAX_LIMIT, effective_limit))

    # Corpus, owned-first: isolation is in the query itself.
    if chat_id is not None:
        chat = await _get_owned_chat(session, user_id, chat_id)
        if chat is None:
            return None
        chats = [chat]
    else:
        result = await session.execute(
            select(Chat).where(Chat.user_id == user_id).order_by(Chat.created_at, Chat.id)
        )
        chats = list(result.scalars().all())
    corpus: list[tuple] = []  # (chat, message, ordinal)
    for chat in chats:
        for ordinal, message in enumerate(await _ordered_messages(session, chat.id)):
            corpus.append((chat, message, ordinal))
    scanned_chats = len(chats)
    scanned_messages = len(corpus)

    def fulltext_ranked():
        qtokens = _dedup(tokenise(query))
        hits = []
        for chat, message, ordinal in corpus:
            scored = score_fulltext(qtokens, message.content)
            if scored is not None:
                score, matched = scored
                hits.append(_row(chat, message, ordinal, score, matched, "fulltext"))
        return rank_hits(hits)

    def fallback_document(reason: str, embedding=None):
        return _document(
            query=query, mode_requested=mode, mode_used="keyword_fallback",
            fallback=True, fallback_reason=reason, embedding=embedding,
            chat_id=chat_id, limit=effective_limit, ranked=fulltext_ranked(),
            scanned_chats=scanned_chats, scanned_messages=scanned_messages,
        )

    if mode == "fulltext":
        return _document(
            query=query, mode_requested=mode, mode_used="fulltext",
            fallback=False, fallback_reason="", embedding=None,
            chat_id=chat_id, limit=effective_limit, ranked=fulltext_ranked(),
            scanned_chats=scanned_chats, scanned_messages=scanned_messages,
        )

    # Empty corpus short-circuits BEFORE any embed call: no road
    # ran and nothing degraded, so no fallback label is owed.
    if scanned_messages == 0:
        return _document(
            query=query, mode_requested=mode,
            mode_used="semantic" if mode == "semantic" else "fulltext",
            fallback=False, fallback_reason="", embedding=None,
            chat_id=chat_id, limit=effective_limit, ranked=[],
            scanned_chats=scanned_chats, scanned_messages=scanned_messages,
        )

    # Semantic road: one backend, one batched call, one space.
    if backend is None:
        try:
            backend = await vector_match.resolve_lore_embedding_backend(session, user_id)
        except Exception:
            return fallback_document("embeddings_unavailable")
    if backend is None or isinstance(backend, UnavailableEmbeddingBackend):
        return fallback_document("embeddings_unavailable")
    texts = [query] + [message.content[:EMBED_TEXT_MAX] for _c, message, _o in corpus]
    try:
        embedded = await embed_or_fallback(backend, texts)
    except Exception as exc:  # non-BackendError escape: degraded, never a crash
        return fallback_document(f"backend_error:{type(exc).__name__}")
    if isinstance(embedded, FtsFallbackResult):
        reason = (embedded.reason or "").strip()
        if reason == "backend_unavailable":
            return fallback_document("embeddings_unavailable")
        if not reason:
            return fallback_document("fts_fallback")
        return fallback_document(f"backend_error:{reason}")
    if not isinstance(embedded, EmbeddingResult):
        return fallback_document("fts_fallback")
    provenance = embedded.provenance.to_dict()
    vectors = embedded.vectors
    if len(vectors) != len(texts) or any(len(v) != len(vectors[0]) for v in vectors):
        return fallback_document("embedding_space_mismatch", embedding=provenance)
    query_vector = vectors[0]
    hits = []
    try:
        for (chat, message, ordinal), vector in zip(corpus, vectors[1:], strict=True):
            score = cosine_similarity(query_vector, vector)
            if score >= SEMANTIC_THRESHOLD:
                hits.append(_row(chat, message, ordinal, score, [], "semantic"))
    except ValueError:
        return fallback_document("embedding_space_mismatch", embedding=provenance)
    ranked = rank_hits(hits)
    if ranked:
        return _document(
            query=query, mode_requested=mode, mode_used="semantic",
            fallback=False, fallback_reason="", embedding=provenance,
            chat_id=chat_id, limit=effective_limit, ranked=ranked,
            scanned_chats=scanned_chats, scanned_messages=scanned_messages,
        )
    if mode == "semantic":
        # An explicit semantic request that finds nothing returns
        # empty AS semantic -- never silently re-run as keyword.
        return _document(
            query=query, mode_requested=mode, mode_used="semantic",
            fallback=False, fallback_reason="", embedding=provenance,
            chat_id=chat_id, limit=effective_limit, ranked=[],
            scanned_chats=scanned_chats, scanned_messages=scanned_messages,
        )
    # auto with a working backend but no semantic hit: the P-041
    # below-threshold keyword fallback, labelled as what it is.
    return fallback_document("no_semantic_hits", embedding=provenance)
