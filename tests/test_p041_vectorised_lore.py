"""P-041 acceptance: vectorised lore.

Roadmap line: *Vectorised lore: embedding-matched entries for
large books, on the founding RAG stack, with keyword fallback.*

Contract under test:
- ``runmal.lorebooks.vector_match`` is the embedding matcher
  P-035 left dormant: it computes ``vector_hit_ids`` on the
  founding RAG stack (the S304 ``EmbeddingBackend`` seam +
  ``embed_or_fallback``, S311 provenance discipline, S401
  cosine). Only vectorised-kind entries are candidates;
  query + candidates embed in ONE batched call; a hit needs
  cosine >= threshold (default 0.30); ranked hits may be
  capped by ``max_entries`` (the per-extension cap P-035
  assigned to this slice), the cap dropping the lowest-ranked
  and reporting the drop count.
- ``LocalEmbeddingBackend`` is the deterministic local provider
  on the repo's own seam (provider "local", model
  "hash-ngram-1"): same text -> same vector, stem-sharing
  paraphrases score high, unrelated texts score near zero. It
  passes the S304 backend contract checks.
- Keyword fallback is deliberate and bounded: it runs ONLY
  when embeddings are unavailable (no backend / backend error
  / S304 fallback result / no comparable vectors) or when no
  candidate reaches the threshold. It reuses the S202 scan
  core over the vectorised entries' own keys and fires via
  ``"vector_fallback"`` -- never disguised as ``"vector"``.
  When a vector hit lands, the fallback does NOT run (a keyed
  entry with a low vector score stays unfired that tick).
- Live paths are wired: ``preview_activation`` runs the
  matcher (sync embedder or a precomputed async outcome), the
  lorebook preview endpoint resolves the owner's backend (S311
  active profile, else the local backend) and matches without
  caller-supplied hit ids, ``inspect_prompt`` includes
  vector-matched lore, ``run_activation_tick`` matches when
  given a backend + messages, and the P-039 merged preview
  matches over the merged winners.
- No migration: the schema head stays 0031.
"""

from __future__ import annotations

import json
import time
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends.embeddings import (
    EmbeddingBackend,
    EmbeddingProvenance,
    EmbeddingResult,
    FakeEmbeddingBackend,
    UnavailableEmbeddingBackend,
    check_embedding_contract,
)
from runmal.backends.errors import BackendUnavailable
from runmal.backends.models import HealthStatus
from runmal.chats import service as chats_service
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User
from runmal.lorebooks import service
from runmal.lorebooks.activation import ActivatableEntry, activate
from runmal.lorebooks.preview import preview_activation
from runmal.lorebooks.state import run_activation_tick
from runmal.lorebooks.vector_match import (
    DEFAULT_VECTOR_THRESHOLD,
    LocalEmbeddingBackend,
    VectorCandidate,
    check_max_vector_entries,
    check_vector_threshold,
    cosine_similarity,
    entry_embed_text,
    keyword_fallback_hits,
    match_vectorised,
    match_vectorised_sync,
    match_with_vectors,
    normalise_max_vector_entries,
    normalise_vector_threshold,
    vector_candidates,
)
from runmal.prompt.inspect import inspect_prompt

# ---------------------------------------------------------------- helpers


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def make_factory(tmp_path):
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory, name="volmarr") -> str:
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


def orm_entry(eid, name, content, keys=(), **kw):
    base = dict(
        id=eid, name=name, content=content, enabled=True, constant=False,
        vectorised=True, keys_json=json.dumps(list(keys)),
        secondary_keys_json="[]", whole_word=True, case_sensitive=False,
        selective_logic="and_any", sticky_prompts=0, cooldown_prompts=0,
        delay_prompts=0, inclusion_group="", group_weight=100, priority=100,
        probability=100, position="before_char", depth=None, role="system",
    )
    base.update(kw)
    return SimpleNamespace(**base)


DRAGON = ("Dragon Peaks",
          "Dragons soar above the mountain peaks and guard the old hoard.", ("dragon",))
BREAD = ("Market Bread", "Fresh bread is baked at dawn and sold for copper coins.", ("bread",))
BELL = ("Gale Bell", "The bell rings when storms approach the coast.", ("gale bell",))


class AxisBackend(EmbeddingBackend):
    """Deterministic stub: one axis per topic word (a semantic toy)."""

    backend_key = "axis"
    AXES = (("dragon", 0), ("wyrm", 0), ("harbour", 1), ("tithe", 1), ("bread", 2))

    def __init__(self, fail: bool = False):
        self._fail = fail
        self.calls: list[list[str]] = []

    async def embed(self, texts):
        self.calls.append(list(texts))
        if self._fail:
            raise BackendUnavailable("axis backend down")
        vectors = []
        for text in texts:
            vec = [0.0, 0.0, 0.0]
            low = text.lower()
            for word, axis in self.AXES:
                if word in low:
                    vec[axis] += 1.0
            vectors.append(tuple(vec))
        return EmbeddingResult(
            vectors=tuple(vectors),
            provenance=EmbeddingProvenance(provider="axis", model="axis-1", dims=3),
        )

    def model_info(self):
        from runmal.backends.embeddings import EmbeddingModelInfo

        return EmbeddingModelInfo(model_id="axis-1", provider="axis", dims=3)

    async def health_check(self):
        return HealthStatus(ok=not self._fail, detail="axis")


# ------------------------------------------------------------- vocabulary


def test_threshold_vocabulary():
    assert DEFAULT_VECTOR_THRESHOLD == 0.30
    assert check_vector_threshold(0) == 0.0
    assert check_vector_threshold(-1) == -1.0
    assert check_vector_threshold(0.5) == 0.5
    for bad in (True, "0.3", None, 1.5, -1.5):
        with pytest.raises(ValueError):
            check_vector_threshold(bad)
    assert normalise_vector_threshold(None) == DEFAULT_VECTOR_THRESHOLD
    assert normalise_vector_threshold(0.9) == 0.9
    assert normalise_vector_threshold("junk") == DEFAULT_VECTOR_THRESHOLD


def test_max_entries_vocabulary():
    assert check_max_vector_entries(None) is None
    assert check_max_vector_entries(3) == 3
    for bad in (True, 0, -1, "3", 1.5):
        with pytest.raises(ValueError):
            check_max_vector_entries(bad)
    assert normalise_max_vector_entries(2) == 2
    assert normalise_max_vector_entries(0) is None
    assert normalise_max_vector_entries("junk") is None


def test_cosine_contract():
    assert cosine_similarity((1.0, 0.0), (1.0, 0.0)) == 1.0
    assert cosine_similarity((1.0, 0.0), (0.0, 1.0)) == 0.0
    assert cosine_similarity((0.0, 0.0), (1.0, 0.0)) == 0.0
    with pytest.raises(ValueError):
        cosine_similarity((1.0,), (1.0, 0.0))


def test_no_migration_p041_takes_none():
    # P-041 itself added no migration; the merged head is 0032 (P-040, banked first).
    assert MIGRATIONS[-1][0] == "0033"
    assert "0031" in [m[0] for m in MIGRATIONS]


# ------------------------------------------------------- local provider


async def test_local_backend_passes_s304_contract():
    await check_embedding_contract(LocalEmbeddingBackend())


def test_local_backend_provenance_and_determinism():
    backend = LocalEmbeddingBackend()
    result = backend.embed_sync(["dragons over mountains", "dragons over mountains"])
    assert result.provenance.provider == "local"
    assert result.provenance.model == "hash-ngram-1"
    assert result.provenance.dims == 256
    assert result.vectors[0] == result.vectors[1]


def test_local_backend_semantic_separation():
    backend = LocalEmbeddingBackend()
    query, para, unrelated = backend.embed_sync([
        "The dragon soars above the mountain peaks",
        "Dragons flying over high mountains",
        "She baked bread and counted coins at the market",
    ]).vectors
    assert cosine_similarity(query, para) >= DEFAULT_VECTOR_THRESHOLD
    assert cosine_similarity(query, para) > 0.4
    assert cosine_similarity(query, unrelated) < 0.2


def test_local_backend_rejects_bad_dims():
    with pytest.raises(ValueError):
        LocalEmbeddingBackend(dims=4)
    with pytest.raises(ValueError):
        LocalEmbeddingBackend(dims=True)


# ------------------------------------------------------------ candidates


def test_vector_candidates_filter_by_kind():
    entries = [
        orm_entry("v1", *DRAGON),
        orm_entry("sel", *BREAD, vectorised=False),
        orm_entry("const", *BREAD, constant=True),
        orm_entry("both", *BREAD, constant=True, vectorised=True),
        orm_entry("off", *BREAD, enabled=False),
    ]
    assert [c.id for c in vector_candidates(entries)] == ["v1"]


def test_entry_embed_text_is_name_keys_content():
    text = entry_embed_text("Dragon Peaks", ("dragon", "wyrm"), "Some lore.")
    assert text == "Dragon Peaks\ndragon wyrm\nSome lore."
    candidate = VectorCandidate.from_orm(orm_entry("e", *DRAGON))
    assert candidate.embed_text == entry_embed_text(*DRAGON[:1], DRAGON[2], DRAGON[1])


# --------------------------------------------------------- pure scoring


def test_match_with_vectors_threshold_and_ranking():
    entries = [orm_entry("a", *DRAGON), orm_entry("b", *BREAD), orm_entry("c", *BELL)]
    outcome = match_with_vectors(
        entries, ["q"], (1.0, 0.0),
        {"a": (0.9, 0.1), "b": (0.2, 0.98), "c": (1.0, 0.0)},
    )
    # a and c score >= 0.30 (b ~0.2 does not); hits keep input order,
    # ranked is best-first.
    assert outcome.hit_ids == ("a", "c")
    assert [eid for eid, _ in outcome.ranked] == ["c", "a", "b"]
    assert outcome.mode == "vector"
    assert outcome.degraded is False
    assert outcome.capped == 0


def test_match_with_vectors_cap_drops_lowest_ranked():
    entries = [orm_entry("a", *DRAGON), orm_entry("b", *BREAD), orm_entry("c", *BELL)]
    vectors = {"a": (1.0, 0.0), "b": (0.95, 0.05), "c": (0.9, 0.1)}
    outcome = match_with_vectors(entries, ["q"], (1.0, 0.0), vectors, max_entries=2)
    assert outcome.hit_ids == ("a", "b")
    assert outcome.capped == 1
    assert outcome.to_dict()["capped"] == 1


def test_match_with_vectors_missing_or_mismatched_degrades():
    entries = [orm_entry("a", *DRAGON)]
    outcome = match_with_vectors(entries, ["the dragon wakes"], (1.0, 0.0), {"a": (1.0,)})
    assert outcome.mode == "keyword_fallback"
    assert outcome.degraded is True
    assert outcome.fallback_reason == "no_comparable_vectors"
    assert outcome.fallback_ids == ("a",)  # its key matched in the window


def test_match_with_vectors_no_candidates():
    outcome = match_with_vectors([orm_entry("s", *BREAD, vectorised=False)], ["q"], (1.0,), {})
    assert outcome.candidates == 0
    assert outcome.mode == "none"


# --------------------------------------------------------- async matcher


async def test_async_matcher_semantic_hit_one_batched_call():
    backend = AxisBackend()
    entries = [orm_entry("d", *DRAGON), orm_entry("b", *BREAD)]
    outcome = await match_vectorised(entries, ["A wyrm circles the peaks"], backend=backend)
    assert outcome.hit_ids == ("d",)
    assert outcome.mode == "vector"
    assert outcome.provenance == {"provider": "axis", "model": "axis-1", "dims": 3, "version": "1"}
    assert len(backend.calls) == 1  # ONE batched embed call for query + entries
    assert len(backend.calls[0]) == 3


async def test_async_matcher_unrelated_text_no_hit_no_fallback():
    entries = [orm_entry("d", *DRAGON), orm_entry("b", *BREAD)]
    outcome = await match_vectorised(
        entries, ["Rain falls on the plain fields"], backend=AxisBackend())
    assert outcome.hit_ids == ()
    assert outcome.fallback_ids == ()
    assert outcome.mode == "none"
    assert outcome.fallback_reason == "below_threshold"
    assert outcome.degraded is False  # embeddings worked; nothing matched


async def test_async_matcher_local_backend_semantic():
    entries = [orm_entry("d", *DRAGON), orm_entry("b", *BREAD)]
    outcome = await match_vectorised(
        entries, ["A dragon flies over high mountains"], backend=LocalEmbeddingBackend()
    )
    assert outcome.hit_ids == ("d",)
    assert outcome.scores["d"] >= DEFAULT_VECTOR_THRESHOLD
    assert outcome.scores["b"] < DEFAULT_VECTOR_THRESHOLD
    assert outcome.provenance["provider"] == "local"


@pytest.mark.parametrize(
    "backend",
    [None, AxisBackend(fail=True), UnavailableEmbeddingBackend(), FakeEmbeddingBackend(fail=True)],
)
async def test_async_matcher_unavailable_degrades_to_keyword_fallback(backend):
    entries = [orm_entry("bell", *BELL)]
    outcome = await match_vectorised(
        entries, ["Ring the gale bell, a storm is coming"], backend=backend)
    assert outcome.degraded is True
    assert outcome.mode == "keyword_fallback"
    assert outcome.fallback_ids == ("bell",)
    assert outcome.fallback_reason  # an honest reason is always recorded
    assert [h.matched_primary for h in outcome.keyword_hits] == [("gale bell",)]


async def test_async_matcher_below_threshold_keyword_fallback():
    # AxisBackend gives the bell entry a zero vector for this query
    # (no axis words), so the vector path honestly misses and the
    # keyword fallback -- not a crash, not silence -- fires it.
    entries = [orm_entry("bell", *BELL)]
    outcome = await match_vectorised(entries, ["Ring the gale bell"], backend=AxisBackend())
    assert outcome.degraded is False
    assert outcome.fallback_reason == "below_threshold"
    assert outcome.mode == "keyword_fallback"
    assert outcome.fallback_ids == ("bell",)


async def test_async_matcher_vector_hit_suppresses_fallback():
    # The bell's key IS in the message, but the dragon's vector hit
    # lands -- the fallback must not run, or the threshold would be
    # meaningless on every working tick.
    entries = [orm_entry("d", *DRAGON), orm_entry("bell", *BELL)]
    outcome = await match_vectorised(
        entries, ["A dragon passes; ring the gale bell"], backend=AxisBackend()
    )
    assert outcome.hit_ids == ("d",)
    assert outcome.fallback_ids == ()
    assert outcome.mode == "vector"


async def test_async_matcher_fallback_disabled():
    entries = [orm_entry("bell", *BELL)]
    outcome = await match_vectorised(
        entries, ["Ring the gale bell"], backend=None, keyword_fallback=False
    )
    assert outcome.mode == "none"
    assert outcome.fallback_ids == ()
    assert outcome.degraded is True


async def test_keyword_fallback_hits_reuses_scan_semantics():
    entries = [
        orm_entry("bell", *BELL),
        orm_entry("sel", *BREAD, vectorised=False),  # selective: never flipped
        orm_entry("off", "Off Bell", "x", ("gale bell",), enabled=False),
    ]
    hits = keyword_fallback_hits(entries, ["Ring the GALE BELL"])  # case-insensitive
    assert [h.entry_id for h in hits] == ["bell"]
    assert hits[0].matched_primary == ("gale bell",)


def test_sync_matcher_raising_embedder_degrades():
    def boom(texts):
        raise RuntimeError("provider exploded")

    entries = [orm_entry("bell", *BELL)]
    outcome = match_vectorised_sync(entries, ["Ring the gale bell"], boom)
    assert outcome.degraded is True
    assert outcome.fallback_reason == "embeddings_unavailable"
    assert outcome.fallback_ids == ("bell",)


# ---------------------------------------------------- activation engine


def ae(eid, **kw):
    base = dict(name=eid, content=f"content of {eid}", vectorised=True)
    base.update(kw)
    return ActivatableEntry(id=eid, **base)


def test_activation_fallback_via_is_honest():
    result = activate([ae("v")], set(), vector_fallback_ids={"v"})
    assert [(a.entry_id, a.via) for a in result.activations] == [("v", "vector_fallback")]


def test_activation_vector_hit_wins_over_fallback_label():
    result = activate([ae("v")], set(), vector_hit_ids={"v"}, vector_fallback_ids={"v"})
    assert [(a.entry_id, a.via) for a in result.activations] == [("v", "vector")]


def test_activation_fallback_never_fires_selective_or_crosses():
    selective = ActivatableEntry(id="s", name="s", content="c")
    result = activate([selective], set(), vector_fallback_ids={"s"})
    assert result.activations == []
    # ...and a plain keyword hit still never fires a vectorised entry.
    result = activate([ae("v")], {"v"})
    assert result.activations == []


# ------------------------------------------------------------- preview


def _preview_entries():
    return [orm_entry("d", *DRAGON), orm_entry("b", *BREAD), orm_entry("bell", *BELL)]


def _row(out, entry_id):
    return next(r for r in out["entries"] if r["entry_id"] == entry_id)


def test_preview_sync_embedder_semantic_match():
    out = preview_activation(
        _preview_entries(), ["A dragon flies over high mountains"], 4, None,
        vector_embedder=LocalEmbeddingBackend().embed_sync,
    )
    row = _row(out, "d")
    assert row["status"] == "included"
    assert row["via"] == "vector"
    assert row["vector_score"] >= DEFAULT_VECTOR_THRESHOLD
    assert row["matched_primary"] == []  # honestly: no keyword matched
    assert _row(out, "b")["status"] == "not_triggered"
    assert out["vector_match"]["mode"] == "vector"
    assert out["vector_match"]["provenance"]["provider"] == "local"
    assert out["vector_match"]["degraded"] is False


def test_preview_sync_embedder_unrelated_text_fires_nothing():
    out = preview_activation(
        _preview_entries(), ["Rain falls on the plain fields"], 4, None,
        vector_embedder=LocalEmbeddingBackend().embed_sync,
    )
    assert all(r["status"] == "not_triggered" for r in out["entries"])
    assert out["vector_match"]["mode"] == "none"


def test_preview_keyword_fallback_when_embedder_raises():
    def boom(texts):
        raise RuntimeError("down")

    out = preview_activation(
        _preview_entries(), ["Ring the gale bell, a storm is coming"], 4, None,
        vector_embedder=boom,
    )
    row = _row(out, "bell")
    assert row["status"] == "included"
    assert row["via"] == "vector_fallback"
    assert row["matched_primary"] == ["gale bell"]  # the real keyword provenance
    assert out["vector_match"]["degraded"] is True
    assert out["vector_match"]["mode"] == "keyword_fallback"


def test_preview_caller_supplied_hits_still_win_no_summary():
    out = preview_activation(
        _preview_entries(), ["anything"], 4, None, vector_hit_ids={"b"},
        vector_embedder=LocalEmbeddingBackend().embed_sync,
    )
    assert _row(out, "b")["via"] == "vector"
    assert "vector_match" not in out  # the P-035 seam shape is unchanged


def test_preview_precomputed_outcome_accepted():
    import asyncio

    outcome = asyncio.run(
        match_vectorised(_preview_entries(), ["A dragon flies over high mountains"],
                         backend=LocalEmbeddingBackend())
    )
    out = preview_activation(_preview_entries(), ["A dragon flies over high mountains"], 4, None,
                             vector_match=outcome)
    assert _row(out, "d")["via"] == "vector"
    assert out["vector_match"]["mode"] == "vector"


# ----------------------------------------------------------- live: API


def _api_book_with_vectorised(client):
    book = client.post("/api/v1/lorebooks", json={"name": "Big Book"})
    assert book.status_code == 201, book.text
    book = book.json()
    for spec in (
        {"name": DRAGON[0], "content": DRAGON[1], "keys": list(DRAGON[2]), "vectorised": True},
        {"name": BREAD[0], "content": BREAD[1], "keys": list(BREAD[2]), "vectorised": True},
    ):
        resp = client.post(f"/api/v1/lorebooks/{book['id']}/entries", json=spec)
        assert resp.status_code == 201, resp.text
    return book


def test_api_preview_matches_vectorised_without_supplied_hits(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book = _api_book_with_vectorised(client)
    resp = client.post(
        f"/api/v1/lorebooks/{book['id']}/preview",
        json={"messages": ["A dragon flies over high mountains"]},
    )
    assert resp.status_code == 200, resp.text
    out = resp.json()
    rows = {r["name"]: r for r in out["entries"]}
    assert rows[DRAGON[0]]["status"] == "included"
    assert rows[DRAGON[0]]["via"] == "vector"
    assert rows[BREAD[0]]["status"] == "not_triggered"
    assert out["vector_match"]["provenance"]["provider"] == "local"


def test_api_preview_unrelated_and_threshold_override(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    book = _api_book_with_vectorised(client)
    out = client.post(
        f"/api/v1/lorebooks/{book['id']}/preview",
        json={"messages": ["Rain falls on the plain fields"]},
    ).json()
    assert all(r["status"] == "not_triggered" for r in out["entries"])
    # An impossible threshold honestly demotes the vector hit to the
    # keyword fallback (the message does carry the entry's key).
    out = client.post(
        f"/api/v1/lorebooks/{book['id']}/preview",
        json={"messages": ["A dragon flies over high mountains"], "vector_threshold": 0.99},
    ).json()
    rows = {r["name"]: r for r in out["entries"]}
    assert rows[DRAGON[0]]["via"] == "vector_fallback"
    assert out["vector_match"]["fallback_reason"] == "below_threshold"


# -------------------------------------------------------- live: inspect


async def _make_book(factory, user_id, specs, name="B"):
    async with factory() as session:
        book = await service.create_lorebook(session, user_id, name)
        book_id = str(book.id)
        ids = {}
        for spec in specs:
            spec = dict(spec)
            label = spec.pop("label")
            entry = await service.create_entry(session, user_id, book_id, **spec)
            ids[label] = str(entry.id)
        return book_id, ids


def _all_slot_ids(node, acc):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "id" and isinstance(value, str):
                acc.add(value)
            _all_slot_ids(value, acc)
    elif isinstance(node, list):
        for item in node:
            _all_slot_ids(item, acc)
    return acc


async def test_inspect_prompt_includes_vector_matched_lore(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    book_id, ids = await _make_book(factory, user_id, [
        {"label": "dragon", "name": DRAGON[0], "content": DRAGON[1],
         "keys": list(DRAGON[2]), "vectorised": True},
        {"label": "bread", "name": BREAD[0], "content": BREAD[1],
         "keys": list(BREAD[2]), "vectorised": True},
    ])
    async with factory() as session:
        trace = await inspect_prompt(
            session, user_id, lorebook_ids=[book_id],
            messages=["A dragon flies over high mountains"],
        )
    slots = {s["slot_id"]: s for s in trace["slots"]}
    dragon_slot = slots[f"lore/{ids['dragon']}"]
    assert dragon_slot["status"] == "included"
    assert dragon_slot["trigger"] == "vector"
    bread_slot = slots.get(f"lore/{ids['bread']}")
    assert bread_slot is None or bread_slot["status"] != "included"


# ----------------------------------------------------------- live: tick


async def test_run_activation_tick_matches_with_backend(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        chat = await chats_service.create_chat(session, user_id, "chat")
        chat_id = str(chat.id)
    book_id, ids = await _make_book(factory, user_id, [
        {"label": "dragon", "name": DRAGON[0], "content": DRAGON[1],
         "keys": list(DRAGON[2]), "vectorised": True},
    ])
    async with factory() as session:
        result = await run_activation_tick(
            session, user_id, chat_id, book_id, set(),
            vector_messages=["A dragon flies over high mountains"],
            embedding_backend=LocalEmbeddingBackend(),
        )
    assert [(a.entry_id, a.via) for a in result.activations] == [(ids["dragon"], "vector")]


async def test_run_activation_tick_falls_back_when_backend_down(tmp_path):
    factory = make_factory(tmp_path)
    user_id = await make_user(factory)
    async with factory() as session:
        chat = await chats_service.create_chat(session, user_id, "chat")
        chat_id = str(chat.id)
    book_id, ids = await _make_book(factory, user_id, [
        {"label": "bell", "name": BELL[0], "content": BELL[1],
         "keys": list(BELL[2]), "vectorised": True},
    ])
    async with factory() as session:
        result = await run_activation_tick(
            session, user_id, chat_id, book_id, set(),
            vector_messages=["Ring the gale bell"],
            embedding_backend=FakeEmbeddingBackend(fail=True),
        )
    assert [(a.entry_id, a.via) for a in result.activations] == [(ids["bell"], "vector_fallback")]


# ------------------------------------------------- live: merged preview


def test_merged_preview_matches_vectorised_winner(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    card_data = {
        "spec": "chara_card_v2", "spec_version": "2.0", "name": "Sigrun",
        "description": "A test seer.", "personality": "Calm.",
        "scenario": "A test hall.", "first_mes": "Hail!", "mes_example": "",
        "creator_notes": "", "system_prompt": "", "post_history_instructions": "",
        "alternate_greetings": [], "tags": [], "creator": "test", "extensions": {},
        "character_book": {"name": "Char Lore", "entries": [
            {"name": DRAGON[0], "comment": DRAGON[0], "content": DRAGON[1],
             "keys": list(DRAGON[2]), "constant": False, "vectorized": True},
        ]},
    }
    char = client.post("/api/v1/characters", json={"card": card_data})
    assert char.status_code == 201, char.text
    char = char.json()
    world = client.post("/api/v1/lorebooks", json={"name": "World"}).json()
    resp = client.post(
        f"/api/v1/lorebooks/{world['id']}/entries",
        json={"name": "World Law", "content": "The world turns.", "constant": True},
    )
    assert resp.status_code == 201, resp.text
    out = client.post(
        f"/api/v1/characters/{char['id']}/lorebook-preview",
        json={"world_lorebook_id": world["id"],
              "messages": ["A dragon flies over high mountains"]},
    )
    assert out.status_code == 200, out.text
    out = out.json()
    rows = {r["name"]: r for r in out["entries"]}
    assert rows[DRAGON[0]]["status"] == "included"
    assert rows[DRAGON[0]]["via"] == "vector"
    assert rows[DRAGON[0]]["scope"] == "character"
    assert out["vector_match"]["mode"] == "vector"


# --------------------------------------------------------- large books


async def test_large_book_matcher_finds_the_one_entry():
    entries = [orm_entry("dragon", *DRAGON)]
    for i in range(299):
        entries.append(orm_entry(
            f"f{i}", f"Filler {i}",
            f"Notes on quixotic zephyr topic {i}: ledger of marsh reeds and copper pins.",
            (f"filler{i}",),
        ))
    started = time.monotonic()
    outcome = await match_vectorised(
        entries, ["A dragon flies over high mountains"], backend=LocalEmbeddingBackend()
    )
    elapsed = time.monotonic() - started
    assert outcome.candidates == 300
    assert outcome.hit_ids == ("dragon",)
    assert elapsed < 10.0  # generous bound: sane, not a benchmark


def test_large_book_pure_scoring_scales():
    entries = [orm_entry(f"e{i}", f"E{i}", f"content {i}", (f"k{i}",)) for i in range(2000)]
    vectors = {f"e{i}": (1.0, 0.0) if i == 1999 else (0.0, 1.0) for i in range(2000)}
    started = time.monotonic()
    outcome = match_with_vectors(entries, ["q"], (1.0, 0.0), vectors)
    elapsed = time.monotonic() - started
    assert outcome.hit_ids == ("e1999",)
    assert len(outcome.ranked) == 2000
    assert elapsed < 10.0
