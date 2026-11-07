"""P-072 Chat search battery (team-01).

Pins: full-text + semantic search across all of the caller's
chats, with jump-to-message results (chat_id, message_id,
ordinal). Design: hidden_files/P072_DESIGN.md.

Search is a READ over the existing message store: no new
table, no stored index, no stored vectors, NO migration
(on this slice's base the head was 0038 and the provisional
0039 was NOT used by this slice; at P-073 banking the merged
head became 0039 -- P-073's chat-metadata migration, never
from P-072). Full-text is deterministic token/phrase scoring over
the ACTIVE message content only (content == swipes[swipe_id];
inactive swipes and variant history are never searched, and
chat titles never create a hit). Semantic reuses the P-041
road: ONE backend resolved per query, ONE batched embed,
cosine >= 0.30, one embedding space. Keyword fallback is
LABELLED, never disguised: no token-scored row is ever
returned under mode_used == "semantic".

Cross-user isolation is pinned at the SERVICE layer with two
owner rows (the single-credential test client cannot express
a second owner at API level -- the P-069 evidence limitation).
Semantic cases inject deterministic backends via
search_chats(backend=...); API-level semantic uses the local
default backend (provider local, model hash-ngram-1).
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends.embeddings import (
    EmbeddingBackend,
    EmbeddingModelInfo,
    EmbeddingProvenance,
    EmbeddingResult,
    FakeEmbeddingBackend,
    FtsFallbackResult,
    UnavailableEmbeddingBackend,
)
from runmal.backends.errors import RateLimited
from runmal.backends.models import HealthStatus
from runmal.chats import search
from runmal.chats import service as svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User


# ---------------- fixtures + helpers ----------------


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _chat(client, title="Saga"):
    r = client.post("/api/v1/chats", json={"title": title})
    assert r.status_code == 201, r.text
    return r.json()


def _msg(client, chat_id, content, role="user"):
    r = client.post(
        f"/api/v1/chats/{chat_id}/messages", json={"role": role, "content": content}
    )
    assert r.status_code == 201, r.text
    return r.json()


def _history(client, chat_id):
    r = client.get(f"/api/v1/chats/{chat_id}/messages")
    assert r.status_code == 200, r.text
    return r.json()


def _events(client, chat_id):
    r = client.get(f"/api/v1/chats/{chat_id}/events")
    assert r.status_code == 200, r.text
    return r.json()


def _search(client, **params):
    r = client.get("/api/v1/chats/search", params=params)
    assert r.status_code == 200, r.text
    return r.json()


def make_factory(tmp_path):
    db_path = tmp_path / "svc.db"
    migrate_to_head(db_path)
    return create_session_factory(create_db_engine(db_path))


async def make_user(factory, name="volmarr"):
    async with factory() as session:
        user = User(name=name)
        session.add(user)
        await session.commit()
        return user.id


async def seed_chat(factory, user, title, turns):
    async with factory() as session:
        chat = await svc.create_chat(session, user, title)
        chat_id = chat.id
        ids = []
        for role, content in turns:
            msg = await svc.append_message(session, user, chat_id, role, content)
            ids.append(msg.id)
    return chat_id, ids


# ---------------- injected embedding backends ----------------


class MapBackend(EmbeddingBackend):
    """Deterministic backend: rule(text) -> vector tuple."""

    backend_key = "map"

    def __init__(self, rule):
        self._rule = rule

    async def embed(self, texts):
        return EmbeddingResult(
            vectors=tuple(self._rule(t) for t in texts),
            provenance=EmbeddingProvenance(
                provider="map", model="map-1", dims=2, version="1"
            ),
        )

    def model_info(self):
        return EmbeddingModelInfo(model_id="map-1", provider="map", dims=2, version="1")

    async def health_check(self):
        return HealthStatus(ok=True, detail="map backend")


class CountingBackend(FakeEmbeddingBackend):
    def __init__(self):
        super().__init__()
        self.calls = 0

    async def embed(self, texts):
        self.calls += 1
        return await super().embed(texts)


class CodeErrorBackend(EmbeddingBackend):
    backend_key = "code-error"

    async def embed(self, texts):
        raise RateLimited("slow down")

    def model_info(self):
        return EmbeddingModelInfo(model_id="x", provider="x", dims=2, version="1")

    async def health_check(self):
        return HealthStatus(ok=False, detail="rate limited")


class FtsReturnBackend(EmbeddingBackend):
    backend_key = "fts-return"

    async def embed(self, texts):
        return FtsFallbackResult(reason="")

    def model_info(self):
        return EmbeddingModelInfo(model_id="x", provider="x", dims=2, version="1")

    async def health_check(self):
        return HealthStatus(ok=True, detail="fts")


class DimsMismatchBackend(EmbeddingBackend):
    backend_key = "dims-mismatch"

    async def embed(self, texts):
        vectors = [(1.0, 0.0)] + [(1.0, 0.0, 0.0)] * (len(texts) - 1)
        return EmbeddingResult(
            vectors=tuple(vectors),
            provenance=EmbeddingProvenance(
                provider="dims", model="dims-1", dims=2, version="1"
            ),
        )

    def model_info(self):
        return EmbeddingModelInfo(model_id="dims-1", provider="dims", dims=2, version="1")

    async def health_check(self):
        return HealthStatus(ok=True, detail="dims")


# ---------------- migration: none taken ----------------


def test_migration_head_is_0039_from_p073_none_from_p072(tmp_path):
    assert MIGRATIONS[-1][0] == "0040"
    # The single 0039 in the registry is P-073's chat-metadata
    # migration; P-072 took no migration of its own.
    assert [rev for rev, _desc, _mod in MIGRATIONS].count("0039") == 1
    # P-075 banking heal: 0039 now stands at [-2] beneath P-075's 0040.
    assert MIGRATIONS[-2][0] == "0039"
    assert MIGRATIONS[-2][2].__name__.endswith("m0039_chat_metadata")
    assert MIGRATIONS[-1][2].__name__.endswith("m0040_message_provenance")
    db_path = tmp_path / "m.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0040"


# ---------------- pure: tokenise ----------------


def test_tokenise_case_punctuation_stemming():
    assert search.tokenise("The DRAGONS, crossed!") == ["dragon", "cross"]
    assert search.tokenise("running quickly") == ["runn", "quick"]


def test_tokenise_stopwords_and_short_tokens_vanish():
    assert search.tokenise("the and of") == []
    assert search.tokenise("x bb y") == ["bb"]


def test_tokenise_preserves_order_and_duplicates():
    assert search.tokenise("fjord dragon fjord") == ["fjord", "dragon", "fjord"]


# ---------------- pure: score_fulltext ----------------


def test_score_fulltext_worked_example_is_9():
    scored = search.score_fulltext(
        ["dragon", "fjord"], "The dragon crossed the dragon fjord at dawn"
    )
    assert scored == (9.0, ["dragon", "fjord"])


def test_score_fulltext_frequency_cap():
    # one token repeated 9x contributes min(9, 4) = 4, plus coverage 2.0
    assert search.score_fulltext(["dragon"], "dragon " * 9) == (6.0, ["dragon"])


def test_score_fulltext_coverage_partial_vs_full():
    partial = search.score_fulltext(["dragon", "fjord"], "dragon only here")
    assert partial == (2.0, ["dragon"])
    full = search.score_fulltext(["dragon", "fjord"], "dragon fjord")
    assert full == (8.0, ["dragon", "fjord"])
    assert partial[0] < full[0]


def test_score_fulltext_no_match_and_no_tokens():
    assert search.score_fulltext(["dragon"], "calm harbour water") is None
    assert search.score_fulltext([], "dragon") is None


# ---------------- pure: snippets + ranking ----------------


def test_snippet_short_content_returned_whole():
    assert search.make_snippet("calm harbour", ["calm"], "fulltext") == "calm harbour"


def test_snippet_whitespace_collapsed():
    assert search.make_snippet("a  \n\t b", [], "fulltext") == "a b"


def test_snippet_long_content_anchored_mid_message():
    content = ("filler " * 40) + "dragon " + ("filler " * 40)
    snippet = search.make_snippet(content, ["dragon"], "fulltext")
    assert "dragon" in snippet
    assert snippet.startswith("...") and snippet.endswith("...")
    assert len(snippet) <= search.SNIPPET_MAX + 6


def test_snippet_anchor_is_first_occurrence():
    content = "dragon " + ("filler " * 60) + "dragon"
    snippet = search.make_snippet(content, ["dragon"], "fulltext")
    assert not snippet.startswith("...")
    assert snippet.startswith("dragon")


def test_snippet_semantic_is_head():
    content = "headword " + ("filler " * 60)
    snippet = search.make_snippet(content, [], "semantic")
    assert snippet.startswith("headword")
    assert snippet.endswith("...")
    assert len(snippet) <= search.SNIPPET_MAX + 3


def test_rank_hits_total_order_and_ranks():
    hits = [
        {"score": 5.0, "chat_id": "b", "ordinal": 0, "message_id": "m2"},
        {"score": 5.0, "chat_id": "a", "ordinal": 1, "message_id": "m3"},
        {"score": 7.0, "chat_id": "z", "ordinal": 0, "message_id": "m9"},
        {"score": 5.0, "chat_id": "a", "ordinal": 0, "message_id": "m1"},
    ]
    ranked = search.rank_hits([dict(h) for h in hits])
    assert [h["message_id"] for h in ranked] == ["m9", "m1", "m3", "m2"]
    assert [h["rank"] for h in ranked] == [1, 2, 3, 4]


# ---------------- API: full-text road ----------------


def test_api_fulltext_hits_across_two_chats(app_client):
    c1 = _chat(app_client, "Alpha")
    _msg(app_client, c1["id"], "The dragon crossed the dragon fjord at dawn")
    c2 = _chat(app_client, "Beta")
    _msg(app_client, c2["id"], "dragon fjord", role="assistant")
    doc = _search(app_client, q="dragon fjord", mode="fulltext")
    assert doc["mode_requested"] == "fulltext"
    assert doc["mode_used"] == "fulltext"
    assert doc["fallback"] is False and doc["degraded"] is False
    assert doc["fallback_reason"] == ""
    assert doc["embedding"] is None
    assert doc["total"] == 2 and doc["returned"] == 2
    assert doc["scanned_chats"] == 2 and doc["scanned_messages"] == 2
    assert [r["rank"] for r in doc["results"]] == [1, 2]
    assert doc["results"][0]["score"] == 9.0
    by_chat = {r["chat_id"]: r for r in doc["results"]}
    assert by_chat[c1["id"]]["chat_title"] == "Alpha"
    assert by_chat[c2["id"]]["role"] == "assistant"
    for row in doc["results"]:
        assert row["matched_terms"] == ["dragon", "fjord"]
        assert row["created_at"]
        assert row["ordinal"] == 0


def test_api_phrase_query_outranks_scattered_tokens(app_client):
    c1 = _chat(app_client, "Phrase")
    _msg(app_client, c1["id"], "dragon fjord")
    c2 = _chat(app_client, "Scattered")
    _msg(app_client, c2["id"], "a dragon met a fjord")
    doc = _search(app_client, q="dragon fjord", mode="fulltext")
    assert doc["total"] == 2
    assert doc["results"][0]["chat_id"] == c1["id"]
    assert doc["results"][0]["score"] > doc["results"][1]["score"]


def test_api_determinism_identical_documents(app_client):
    c1 = _chat(app_client, "Saga")
    _msg(app_client, c1["id"], "dragon fjord dragon")
    first = _search(app_client, q="dragon fjord", mode="fulltext")
    second = _search(app_client, q="dragon fjord", mode="fulltext")
    assert first == second


def test_api_query_dedup_order_in_matched_terms(app_client):
    c1 = _chat(app_client, "Saga")
    _msg(app_client, c1["id"], "dragon fjord")
    doc = _search(app_client, q="fjord dragon fjord", mode="fulltext")
    assert doc["results"][0]["matched_terms"] == ["fjord", "dragon"]


def test_api_equal_scores_ordered_by_chat_id(app_client):
    c1 = _chat(app_client, "One")
    _msg(app_client, c1["id"], "dragon fjord")
    c2 = _chat(app_client, "Two")
    _msg(app_client, c2["id"], "dragon fjord")
    doc = _search(app_client, q="dragon fjord", mode="fulltext")
    assert doc["total"] == 2
    assert doc["results"][0]["score"] == doc["results"][1]["score"]
    assert [r["chat_id"] for r in doc["results"]] == sorted([c1["id"], c2["id"]])


def test_api_title_only_term_never_hits(app_client):
    c1 = _chat(app_client, "Zqxtitleterm Hall")
    _msg(app_client, c1["id"], "calm harbour water")
    doc = _search(app_client, q="zqxtitleterm", mode="fulltext")
    assert doc["total"] == 0 and doc["results"] == []


# ---------------- active text only ----------------


async def test_service_inactive_swipe_never_searched(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await seed_chat(factory, user, "Swipes", [("user", "visible harbour")])
    async with factory() as session:
        await svc.add_swipe(session, user, chat_id, ids[0], "zqxhidden alternate text")
        doc = await search.search_chats(session, user, "zqxhidden", mode="fulltext")
        assert doc["total"] == 1  # the new alternate IS the active text now
        await svc.select_swipe(session, user, chat_id, ids[0], index=0)
        doc = await search.search_chats(session, user, "zqxhidden", mode="fulltext")
        assert doc["total"] == 0  # inactive again: never searched
        doc = await search.search_chats(session, user, "visible", mode="fulltext")
        assert doc["total"] == 1


async def test_service_variant_history_never_searched(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await seed_chat(factory, user, "Edits", [("user", "zqxold draft words")])
    async with factory() as session:
        await svc.edit_message(session, user, chat_id, ids[0], "fresh visible words")
        doc = await search.search_chats(session, user, "zqxold", mode="fulltext")
        assert doc["total"] == 0
        doc = await search.search_chats(session, user, "fresh", mode="fulltext")
        assert doc["total"] == 1


# ---------------- semantic road (injected backends) ----------------


def _quixotic_rule(text):
    return (1.0, 0.0) if "quixotic" in text else (0.0, 1.0)


async def test_service_semantic_hit_and_below_threshold_excluded(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    await seed_chat(factory, user, "Sem", [
        ("user", "a quixotic lantern tale"),
        ("user", "ordinary harbour talk"),
    ])
    async with factory() as session:
        doc = await search.search_chats(
            session, user, "quixotic lantern", mode="semantic",
            backend=MapBackend(_quixotic_rule),
        )
    assert doc["mode_used"] == "semantic"
    assert doc["fallback"] is False
    assert doc["total"] == 1
    row = doc["results"][0]
    assert row["score"] == 1.0  # the cosine, 6dp
    assert row["matched_terms"] == []
    assert doc["embedding"]["provider"] == "map"
    assert doc["embedding"]["model"] == "map-1"


async def test_service_semantic_explicit_zero_hits_stays_semantic(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    await seed_chat(factory, user, "Sem", [("user", "dragon lair")])
    backend = MapBackend(lambda t: (1.0, 0.0) if t == "qqqprobe" else (0.0, 1.0))
    async with factory() as session:
        doc = await search.search_chats(
            session, user, "qqqprobe", mode="semantic", backend=backend
        )
    assert doc["total"] == 0 and doc["results"] == []
    assert doc["mode_used"] == "semantic"  # no silent keyword re-run
    assert doc["fallback"] is False


def test_api_semantic_local_default_paraphrase_and_provenance(app_client):
    c1 = _chat(app_client, "Saga")
    _msg(app_client, c1["id"], "the lighthouse keepers watched the sea")
    doc = _search(app_client, q="lighthouse keeper", mode="semantic")
    assert doc["mode_used"] == "semantic"
    assert doc["total"] >= 1
    assert doc["embedding"]["provider"] == "local"
    assert doc["embedding"]["model"] == "hash-ngram-1"
    assert doc["embedding"]["dims"] == 256


# ---------------- fallback honesty ----------------


async def test_service_unavailable_backend_keyword_fallback(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    await seed_chat(factory, user, "Fb", [("user", "dragon lair")])
    async with factory() as session:
        doc = await search.search_chats(
            session, user, "dragon", mode="semantic",
            backend=UnavailableEmbeddingBackend(),
        )
    assert doc["total"] == 1
    assert doc["mode_used"] == "keyword_fallback"
    assert doc["fallback"] is True and doc["degraded"] is True
    assert doc["fallback_reason"] == "embeddings_unavailable"


async def test_service_backend_error_reason_carries_code(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    await seed_chat(factory, user, "Fb", [("user", "dragon lair")])
    async with factory() as session:
        doc = await search.search_chats(
            session, user, "dragon", mode="semantic", backend=CodeErrorBackend()
        )
    assert doc["mode_used"] == "keyword_fallback"
    assert doc["fallback_reason"] == "backend_error:rate_limited"
    assert doc["total"] == 1


async def test_service_fts_fallback_result_reason(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    await seed_chat(factory, user, "Fb", [("user", "dragon lair")])
    async with factory() as session:
        doc = await search.search_chats(
            session, user, "dragon", mode="semantic", backend=FtsReturnBackend()
        )
    assert doc["mode_used"] == "keyword_fallback"
    assert doc["fallback_reason"] == "fts_fallback"


async def test_service_auto_failing_backend_labelled_fallback(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    await seed_chat(factory, user, "Fb", [("user", "dragon lair")])
    async with factory() as session:
        doc = await search.search_chats(
            session, user, "dragon", mode="auto",
            backend=FakeEmbeddingBackend(fail=True),
        )
    assert doc["mode_used"] == "keyword_fallback"
    assert doc["fallback_reason"] == "embeddings_unavailable"
    assert doc["total"] == 1


async def test_service_auto_no_semantic_hits_keyword_fallback(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    await seed_chat(factory, user, "Fb", [("user", "dragon lair")])
    backend = MapBackend(lambda t: (1.0, 0.0) if t == "dragon" else (0.0, 1.0))
    async with factory() as session:
        doc = await search.search_chats(
            session, user, "dragon", mode="auto", backend=backend
        )
    assert doc["total"] == 1
    assert doc["mode_used"] == "keyword_fallback"
    assert doc["fallback_reason"] == "no_semantic_hits"
    assert doc["embedding"]["provider"] == "map"


async def test_service_auto_semantic_hits_exclude_keyword_only(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    await seed_chat(factory, user, "Fb", [
        ("user", "zqxvector waves"),
        ("user", "dragon waves"),
    ])
    backend = MapBackend(lambda t: (1.0, 0.0) if "zqxvector" in t else (0.0, 1.0))
    async with factory() as session:
        doc = await search.search_chats(
            session, user, "zqxvector dragon", mode="auto", backend=backend
        )
    assert doc["mode_used"] == "semantic"
    assert doc["fallback"] is False
    assert doc["total"] == 1
    assert "zqxvector" in doc["results"][0]["snippet"]


async def test_service_dims_mismatch_whole_query_fallback(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    await seed_chat(factory, user, "Fb", [
        ("user", "dragon lair"),
        ("user", "dragon fjord"),
    ])
    async with factory() as session:
        doc = await search.search_chats(
            session, user, "dragon", mode="semantic", backend=DimsMismatchBackend()
        )
    assert doc["mode_used"] == "keyword_fallback"
    assert doc["fallback_reason"] == "embedding_space_mismatch"
    assert doc["total"] == 2  # keyword count only: no partial semantic rows


# ---------------- isolation + chat_id filter ----------------


async def test_service_cross_user_isolation_all_modes(tmp_path):
    factory = make_factory(tmp_path)
    alice = await make_user(factory, "alice")
    bob = await make_user(factory, "bob")
    await seed_chat(factory, alice, "Alice", [("user", "ordinary harbour talk")])
    await seed_chat(factory, bob, "Bob", [("user", "zqxsecret isolation term")])
    all_map = MapBackend(lambda t: (1.0, 0.0))
    async with factory() as session:
        for mode, backend in (
            ("fulltext", None),
            ("semantic", all_map),
            ("auto", all_map),
        ):
            doc = await search.search_chats(
                session, alice, "zqxsecret", mode=mode, backend=backend
            )
            if mode == "fulltext":
                assert doc["total"] == 0, mode
            assert "zqxsecret" not in json.dumps(doc["results"]), mode
            assert "Bob" not in json.dumps(doc["results"]), mode
            assert all(r["chat_title"] == "Alice" for r in doc["results"]), mode
            assert doc["scanned_chats"] == 1, mode
            assert doc["scanned_messages"] == 1, mode


async def test_service_chat_id_filter_narrows_and_foreign_is_none(tmp_path):
    factory = make_factory(tmp_path)
    alice = await make_user(factory, "alice")
    bob = await make_user(factory, "bob")
    chat_a, _ = await seed_chat(factory, alice, "A", [("user", "dragon one")])
    await seed_chat(factory, alice, "A2", [("user", "dragon two")])
    chat_b, _ = await seed_chat(factory, bob, "B", [("user", "dragon three")])
    async with factory() as session:
        doc = await search.search_chats(
            session, alice, "dragon", mode="fulltext", chat_id=chat_a
        )
        assert doc["total"] == 1 and doc["scanned_chats"] == 1
        assert doc["results"][0]["chat_id"] == chat_a
        assert doc["chat_id"] == chat_a
        foreign = await search.search_chats(
            session, alice, "dragon", mode="fulltext", chat_id=chat_b
        )
        assert foreign is None
        missing = await search.search_chats(
            session, alice, "dragon", mode="fulltext", chat_id="no-such-chat"
        )
        assert missing is None


def test_api_chat_id_filter_and_missing_404(app_client):
    c1 = _chat(app_client, "One")
    _msg(app_client, c1["id"], "dragon one")
    c2 = _chat(app_client, "Two")
    _msg(app_client, c2["id"], "dragon two")
    doc = _search(app_client, q="dragon", mode="fulltext", chat_id=c1["id"])
    assert doc["total"] == 1 and doc["scanned_chats"] == 1
    r = app_client.get(
        "/api/v1/chats/search",
        params={"q": "dragon", "mode": "fulltext", "chat_id": "no-such-chat"},
    )
    assert r.status_code == 404, r.text
    assert r.json()["detail"] == "chat not found"


# ---------------- route ordering + validation ----------------


def test_api_route_ordering_search_not_swallowed(app_client):
    c1 = _chat(app_client, "Saga")
    _msg(app_client, c1["id"], "dragon fjord")
    doc = _search(app_client, q="dragon", mode="fulltext")
    assert doc["total"] == 1  # not a 404 for a chat called "search"
    r = app_client.get(f"/api/v1/chats/{c1['id']}")
    assert r.status_code == 200, r.text
    assert r.json()["id"] == c1["id"]


def test_api_validation_errors(app_client):
    c1 = _chat(app_client, "Saga")
    _msg(app_client, c1["id"], "dragon fjord")
    r = app_client.get("/api/v1/chats/search", params={"mode": "fulltext"})
    assert r.status_code == 422, r.text  # q missing
    for bad_q in ("", "   "):
        r = app_client.get("/api/v1/chats/search", params={"q": bad_q})
        assert r.status_code == 422, r.text
    r = app_client.get("/api/v1/chats/search", params={"q": "x" * 501})
    assert r.status_code == 422, r.text
    r = app_client.get(
        "/api/v1/chats/search", params={"q": "dragon", "mode": "bogus"}
    )
    assert r.status_code == 422, r.text


def test_api_all_stopword_query_fulltext_empty_200(app_client):
    c1 = _chat(app_client, "Saga")
    _msg(app_client, c1["id"], "dragon fjord")
    doc = _search(app_client, q="the and of", mode="fulltext")
    assert doc["total"] == 0 and doc["results"] == []
    assert doc["mode_used"] == "fulltext"


def test_api_limit_clamping_and_total(app_client):
    c1 = _chat(app_client, "Saga")
    for i in range(3):
        _msg(app_client, c1["id"], f"dragon entry {i}")
    doc = _search(app_client, q="dragon", mode="fulltext", limit=0)
    assert doc["limit"] == 1 and doc["returned"] == 1 and doc["total"] == 3
    doc = _search(app_client, q="dragon", mode="fulltext", limit=500)
    assert doc["limit"] == 100 and doc["returned"] == 3 and doc["total"] == 3
    doc = _search(app_client, q="dragon", mode="fulltext")
    assert doc["limit"] == 20 and doc["total"] == 3


# ---------------- jump-to-message contract ----------------


async def test_service_jump_ordinal_matches_history_legacy_and_moved(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id, ids = await seed_chat(factory, user, "Jump", [
        ("user", "first calm"),
        ("assistant", "second calm"),
        ("user", "third zqxjump target"),
    ])
    async with factory() as session:
        doc = await search.search_chats(session, user, "zqxjump", mode="fulltext")
        assert doc["total"] == 1
        row = doc["results"][0]
        assert row["chat_id"] == chat_id and row["message_id"] == ids[2]
        history = await svc.get_history(session, user, chat_id)
        assert [m.id for m in history].index(row["message_id"]) == row["ordinal"] == 2
        # after a move materialises positions, ordinal tracks the new order
        await svc.move_message(session, user, chat_id, ids[2], 0)
        doc = await search.search_chats(session, user, "zqxjump", mode="fulltext")
        row = doc["results"][0]
        history = await svc.get_history(session, user, chat_id)
        assert [m.id for m in history].index(row["message_id"]) == row["ordinal"] == 0


def test_api_jump_ordinal_matches_history(app_client):
    c1 = _chat(app_client, "Jump")
    _msg(app_client, c1["id"], "first calm")
    target = _msg(app_client, c1["id"], "second zqxjump target")
    doc = _search(app_client, q="zqxjump", mode="fulltext")
    row = doc["results"][0]
    assert row["message_id"] == target["id"]
    history_ids = [m["id"] for m in _history(app_client, c1["id"])]
    assert history_ids.index(row["message_id"]) == row["ordinal"] == 1


# ---------------- read-only + empty corpus ----------------


def test_api_search_is_read_only(app_client):
    c1 = _chat(app_client, "Saga")
    _msg(app_client, c1["id"], "dragon fjord")
    _msg(app_client, c1["id"], "lighthouse keeper", role="assistant")
    before_history = json.dumps(_history(app_client, c1["id"]), sort_keys=True)
    before_events = json.dumps(_events(app_client, c1["id"]), sort_keys=True)
    _search(app_client, q="dragon", mode="fulltext")
    _search(app_client, q="lighthouse", mode="semantic")
    _search(app_client, q="dragon")
    assert json.dumps(_history(app_client, c1["id"]), sort_keys=True) == before_history
    assert json.dumps(_events(app_client, c1["id"]), sort_keys=True) == before_events


async def test_service_empty_corpus_modes_and_embedder_never_called(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    backend = CountingBackend()
    async with factory() as session:
        fulltext = await search.search_chats(
            session, user, "dragon", mode="fulltext", backend=backend
        )
        semantic = await search.search_chats(
            session, user, "dragon", mode="semantic", backend=backend
        )
        auto = await search.search_chats(
            session, user, "dragon", mode="auto", backend=backend
        )
    assert backend.calls == 0
    assert fulltext["mode_used"] == "fulltext"
    assert semantic["mode_used"] == "semantic"
    assert auto["mode_used"] == "fulltext"
    for doc in (fulltext, semantic, auto):
        assert doc["total"] == 0 and doc["results"] == []
        assert doc["fallback"] is False and doc["embedding"] is None
        assert doc["scanned_chats"] == 0 and doc["scanned_messages"] == 0
