"""P-205 acceptance: the reasoning-content record -- capture,
stream, store (Part XIII, DERIVED).

Contract under test:
- ReasoningDelta capture at the wire: the four adapters stop
  silently dropping the reasoning/thinking fields their
  provider streams already carry; reasoning is NEVER merged
  into TextDelta (TextDelta concatenation == answer text).
- The generation service bridges it as {"type": "reasoning"};
  a reasoning delta counts as visible output for retry.
- Migration PROVISIONAL 0042: messages.reasoning_json, one
  JSON reasoning document per message, one record per swipe
  (schema runmal-p205-message-reasoning-v1), in the P-075
  honesty idiom: recorded / not_present / not_recorded /
  unknown; strict builders, tolerant readers.
- Produced end-to-end by the bridge conversation road ONLY;
  every other road honestly records not_recorded.
Fixtures mirror test_p075_message_provenance.py / p069 / s602.
"""

import asyncio
import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends.aesir import AesirChatBackend
from runmal.backends.errors import RateLimited
from runmal.backends.events import Done, Event, ReasoningDelta, TextDelta
from runmal.backends.fake import FakeChatBackend
from runmal.backends.messages import ChatMessage
from runmal.backends.ollama import OllamaChatBackend
from runmal.backends.openai_compat import OpenAICompatibleChatBackend
from runmal.backends.openrouter import OpenRouterChatBackend
from runmal.backends.params import SamplingParams
from runmal.backends.retry import RetryPolicy, stream_with_retry
from runmal.chats import reasoning as rsn
from runmal.chats import service as svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import current_revision, migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User

MSGS = [ChatMessage("user", "hi")]
CARD = {
    "name": "Bridge Warden",
    "description": "Keeper of the bridge at TESTHOLD.",
    "personality": "Stern but fair.",
    "scenario": "A stone bridge over a cold river.",
    "first_mes": "State your business.",
    "system_prompt": "You are the Bridge Warden of TESTHOLD.",
}


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0042"
    engine = create_db_engine(db_path)
    factory = create_session_factory(engine)
    client = TestClient(create_app(factory))
    client.factory = factory
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


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


async def seed_chat(factory, user, turns):
    async with factory() as session:
        chat = await svc.create_chat(session, user, "Saga")
        chat_id = chat.id
        for role, content in turns:
            await svc.append_message(session, user, chat_id, role, content)
    return chat_id


def sse_transport(body: bytes):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            return httpx.Response(
                200, content=body,
                headers={"Content-Type": "text/event-stream"})
        return httpx.Response(404, content=b"{}")
    return httpx.MockTransport(handler)


def ndjson_transport(body: bytes):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/api/chat"):
            return httpx.Response(200, content=body)
        return httpx.Response(404, content=b"{}")
    return httpx.MockTransport(handler)


async def collect(backend, **kw):
    return [e async for e in backend.chat_stream(
        MSGS, SamplingParams(), asyncio.Event(), **kw)]


def reasoning_texts(events):
    return [e.text for e in events if isinstance(e, ReasoningDelta)]


def answer_text(events):
    return "".join(e.text for e in events if isinstance(e, TextDelta))


# -- A. Capture -------------------------------------------------------------


def test_a1_reasoning_delta_shape_and_union():
    delta = ReasoningDelta("thinking")
    assert delta.to_dict() == {"type": "reasoning_delta", "text": "thinking"}
    import typing
    assert ReasoningDelta in typing.get_args(Event)
    assert TextDelta("x").to_dict() == {"type": "text_delta", "text": "x"}


async def test_a2_fake_reasoning_order_and_text_invariant():
    backend = FakeChatBackend(
        chunks=("Ans", "wer"), reasoning_chunks=("plan ", "step"))
    events = await collect(backend)
    assert reasoning_texts(events) == ["plan ", "step"]
    kinds = [type(e).__name__ for e in events]
    assert kinds == ["ReasoningDelta", "ReasoningDelta",
                     "TextDelta", "TextDelta", "Done"]
    plain = await collect(FakeChatBackend(chunks=("Ans", "wer")))
    assert answer_text(events) == answer_text(plain) == "Answer"
    assert reasoning_texts(plain) == []


def _openai_sse(deltas, finish=True):
    lines = []
    for delta in deltas:
        lines.append("data: " + json.dumps({"choices": [{"delta": delta}]}))
    if finish:
        lines.append('data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}')
    lines.append("data: [DONE]")
    return ("\n\n".join(lines) + "\n\n").encode()


async def test_a3_openai_compat_reasoning_content_capture():
    body = _openai_sse([
        {"reasoning_content": "plan ", "content": ""},
        {"reasoning_content": "step", "content": "Ans"},
        {"content": "wer"},
    ])
    backend = OpenAICompatibleChatBackend(
        api_key="k", transport=sse_transport(body))
    events = await collect(backend)
    assert reasoning_texts(events) == ["plan ", "step"]
    assert answer_text(events) == "Answer"
    # reasoning arrives BEFORE the answer text of the same chunk
    kinds = [type(e).__name__ for e in events]
    assert kinds.index("ReasoningDelta") < kinds.index("TextDelta")


async def test_a4_openai_compat_fallback_and_fieldless_zero():
    body = _openai_sse([{"reasoning": "alt think", "content": "X"}])
    backend = OpenAICompatibleChatBackend(
        api_key="k", transport=sse_transport(body))
    events = await collect(backend)
    assert reasoning_texts(events) == ["alt think"]
    assert answer_text(events) == "X"
    plain = _openai_sse([{"content": "Only"}, {"content": " text"}])
    backend2 = OpenAICompatibleChatBackend(
        api_key="k", transport=sse_transport(plain))
    events2 = await collect(backend2)
    assert reasoning_texts(events2) == []
    assert answer_text(events2) == "Only text"


async def test_a5_openrouter_reasoning_capture():
    body = _openai_sse([
        {"reasoning": "or think", "content": "Yo"},
        {"content": "!"},
    ])
    backend = OpenRouterChatBackend(api_key="k", transport=sse_transport(body))
    events = await collect(backend)
    assert reasoning_texts(events) == ["or think"]
    assert answer_text(events) == "Yo!"


async def test_a6_aesir_reasoning_content_capture():
    body = _openai_sse([
        {"reasoning_content": "aesir think", "content": "Ha"},
        {"content": "il"},
    ])
    backend = AesirChatBackend(api_key="k", transport=sse_transport(body))
    events = await collect(backend)
    assert reasoning_texts(events) == ["aesir think"]
    assert answer_text(events) == "Hail"


async def test_a7_ollama_thinking_capture():
    rows = [
        {"message": {"role": "assistant", "thinking": "deep ", "content": ""}, "done": False},
        {"message": {"role": "assistant", "thinking": "thought", "content": "Ans"}, "done": False},
        {"message": {"role": "assistant", "content": ""}, "done": True,
         "done_reason": "stop", "prompt_eval_count": 3, "eval_count": 2},
    ]
    body = ("\n".join(json.dumps(r) for r in rows) + "\n").encode()
    backend = OllamaChatBackend(transport=ndjson_transport(body))
    events = await collect(backend)
    assert reasoning_texts(events) == ["deep ", "thought"]
    assert answer_text(events) == "Ans"


# -- B. Stream ---------------------------------------------------------------


def test_b1_bridge_event_reasoning_and_banked_mappings():
    from runmal.backends.events import ErrorEvent, UsageUpdate
    from runmal.generation.service import bridge_event
    assert bridge_event(ReasoningDelta("t")) == {"type": "reasoning", "text": "t"}
    assert bridge_event(TextDelta("x")) == {"type": "token", "text": "x"}
    assert bridge_event(Done("stop")) == {"type": "done", "finish_reason": "stop"}
    assert bridge_event(UsageUpdate(1, 2, 3)) == {
        "type": "usage", "prompt_tokens": 1,
        "completion_tokens": 2, "total_tokens": 3}
    assert bridge_event(ErrorEvent("c", "m", False)) == {
        "type": "error", "code": "c", "message": "m", "retryable": False}


async def test_b2_generate_events_reasoning_in_arrival_order():
    from runmal.generation import service as gen
    backend = FakeChatBackend(
        chunks=("A", "B"), reasoning_chunks=("t1", "t2"))
    events = [e async for e in gen.generate_events(
        "req-p205-b2", messages=MSGS, backend=backend, plugin_events=False)]
    assert [e["type"] for e in events] == [
        "reasoning", "reasoning", "token", "token", "done"]
    assert events[0] == {"type": "reasoning", "text": "t1"}
    assert events[2] == {"type": "token", "text": "A"}
    assert events[-1] == {"type": "done", "finish_reason": "stop"}


class _ReasonThenFail:
    backend_key = "reasonfail"
    default_model = None

    async def chat_stream(self, messages, params, cancel, *, structured=None):
        yield ReasoningDelta("shown thinking")
        raise RateLimited("slow down")


class _FailOnceThenOk:
    backend_key = "failonce"
    default_model = None

    def __init__(self):
        self.calls = 0

    async def chat_stream(self, messages, params, cancel, *, structured=None):
        self.calls += 1
        if self.calls == 1:
            raise RateLimited("slow down")
        yield TextDelta("ok")
        yield Done("stop")


async def test_b3_retry_reasoning_counts_as_visible_output():
    attempts = []
    policy = RetryPolicy(max_attempts=3, base_delay_s=0.0, max_delay_s=0.0)

    async def no_sleep(_delay):
        return None

    seen = []
    with pytest.raises(RateLimited):
        async for event in stream_with_retry(
                _ReasonThenFail(), MSGS, SamplingParams(), asyncio.Event(),
                request_id="req-p205-b3", policy=policy, sleep=no_sleep,
                on_attempt=attempts.append):
            seen.append(event)
    assert [type(e).__name__ for e in seen] == ["ReasoningDelta"]
    assert len(attempts) == 1  # thinking was shown: NEVER retried
    attempts2 = []
    events = [e async for e in stream_with_retry(
        _FailOnceThenOk(), MSGS, SamplingParams(), asyncio.Event(),
        request_id="req-p205-b3b", policy=policy, sleep=no_sleep,
        on_attempt=attempts2.append)]
    assert [type(e).__name__ for e in events] == ["TextDelta", "Done"]
    assert len(attempts2) == 2  # pre-output failure still retries as banked


# -- C. Record ---------------------------------------------------------------


def test_c1_schema_pinned_and_roundtrip():
    assert rsn.REASONING_SCHEMA == "runmal-p205-message-reasoning-v1"
    record = rsn.build_record(status="recorded", text="deep thought")
    document = rsn.build_document(record)
    assert document["schema"] == "runmal-p205-message-reasoning-v1"
    parsed = rsn.parse_document(rsn.dump_document(document))
    assert parsed["recorded"] is True
    assert parsed["swipes"] == {"0": {"status": "recorded", "text": "deep thought"}}
    view = rsn.active_view(rsn.dump_document(document))
    assert view["status"] == "recorded" and view["text"] == "deep thought"
    assert view["reasoning_status"] == "recorded"


def test_c2_strict_builders_refuse_lies():
    with pytest.raises(ValueError):
        rsn.build_record(status="recorded", text=7)
    with pytest.raises(ValueError):
        rsn.build_record(status="recorded")  # recorded without text
    with pytest.raises(ValueError):
        rsn.build_record(status="telepathic")
    with pytest.raises(ValueError):
        rsn.build_record(status="not_present", text="smuggled")
    with pytest.raises(ValueError):
        rsn.build_document({"status": "not_recorded", "text": "smuggled"})
    with pytest.raises(ValueError):
        rsn.build_document({"status": "recorded", "text": "x", "extra": 1})


def test_c3_tolerant_readers_not_recorded_document():
    for raw in ("{}", "not json{", None, "",
                json.dumps({"schema": "foreign-v9", "swipes": {}})):
        document = rsn.parse_document(raw)
        assert document["recorded"] is False
        assert document["swipes"] == {}
        view = rsn.active_view(raw)
        assert view["status"] == "not_recorded"
        assert view["reasoning_status"] == "not_recorded"
        assert "text" not in view


def test_c4_three_way_honesty_distinction():
    not_present = rsn.active_view(rsn.dump_document(
        rsn.build_document(rsn.build_record(status="not_present"))))
    assert not_present["status"] == "not_present"
    not_recorded = rsn.active_view("{}")
    assert not_recorded["status"] == "not_recorded"
    corrupt = rsn.dump_document({
        "schema": rsn.REASONING_SCHEMA, "recorded": True,
        "recorded_at": "2026-11-09T00:00:00+00:00",
        "swipes": {"0": {"status": "recorded"}}})  # text missing: corrupt
    unknown = rsn.active_view(corrupt)
    assert unknown["status"] == "unknown"
    assert len({not_present["status"], not_recorded["status"],
                unknown["status"]}) == 3


async def test_c5_prompt_marker_never_stored(tmp_path):
    from runmal.generation import service as gen
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    backend = FakeChatBackend(
        chunks=("the answer",), reasoning_chunks=("real thinking",))
    events = [e async for e in gen.generate_events(
        "req-p205-c5", prompt="PROMPT-MARKER-205", backend=backend,
        plugin_events=False)]
    thought = "".join(e["text"] for e in events if e["type"] == "reasoning")
    record = rsn.build_record(status="recorded", text=thought)
    async with factory() as session:
        message = await svc.append_message(
            session, user, chat_id, "assistant", "the answer",
            reasoning=record)
        stored = message.reasoning_json
    assert "PROMPT-MARKER-205" not in stored
    assert "real thinking" in stored
    assert "the answer" not in stored  # reasoning doc holds thinking only


# -- D. Storage + plumbing ---------------------------------------------------


def test_d1_migration_0042_head_idempotent_and_upgrade(tmp_path):
    assert MIGRATIONS[-1][0] == "0042"
    assert MIGRATIONS[-1][2].__name__.endswith("m0042_message_reasoning")
    assert MIGRATIONS[-2][0] == "0041"
    db_path = tmp_path / "legacy.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations "
            "(revision TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        for revision, _desc, module in MIGRATIONS[:-1]:
            module.upgrade(conn)
            conn.execute(
                "INSERT INTO schema_migrations (revision, applied_at) "
                "VALUES (?, ?)", (revision, "2026-11-09T00:00:00+00:00"))
            conn.commit()
        assert current_revision(db_path) == "0041"
        cols = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
        assert "reasoning_json" not in cols
        conn.execute(
            "INSERT INTO users (id, name, created_at) VALUES "
            "('u-d1', 'volmarr', '2026-01-01T00:00:00+00:00')")
        conn.execute(
            "INSERT INTO chats (id, user_id, title, created_at) VALUES "
            "('c-d1', 'u-d1', 'Saga', '2026-01-01T00:00:00+00:00')")
        conn.execute(
            "INSERT INTO messages (id, chat_id, role, content, "
            "swipes_json, created_at) VALUES "
            "('m-d1', 'c-d1', 'assistant', 'Legacy answer.', "
            "'[\"Legacy answer.\"]', '2026-01-01T00:00:00+00:00')")
        conn.commit()
    finally:
        conn.close()
    applied = migrate_to_head(db_path)
    assert applied == ["0042"]
    assert current_revision(db_path) == "0042"
    stored = None
    conn = sqlite3.connect(db_path)
    try:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(messages)")}
        assert "reasoning_json" in cols
        stored = conn.execute(
            "SELECT reasoning_json FROM messages WHERE id = 'm-d1'"
        ).fetchone()[0]
        assert stored == "{}"
        # idempotent: the upgrade itself is PRAGMA-guarded.
        MIGRATIONS[-1][2].upgrade(conn)
        MIGRATIONS[-1][2].upgrade(conn)
        conn.commit()
    finally:
        conn.close()
    assert migrate_to_head(db_path) == []
    view = rsn.active_view(stored)
    assert view["status"] == "not_recorded"
    assert "text" not in view


async def test_d2_append_with_reasoning_stores_swipe0(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    record = rsn.build_record(status="recorded", text="bridge thinking")
    async with factory() as session:
        message = await svc.append_message(
            session, user, chat_id, "assistant", "The answer.",
            reasoning=record)
        stored = rsn.parse_document(message.reasoning_json)
        view = svc.message_to_dict(message)["reasoning"]
    assert stored["swipes"] == {
        "0": {"status": "recorded", "text": "bridge thinking"}}
    assert view["status"] == "recorded"
    assert view["text"] == "bridge thinking"
    assert view["reasoning_status"] == "recorded"


async def test_d3_append_without_reasoning_reads_not_recorded(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    async with factory() as session:
        history = await svc.get_history(session, user, chat_id)
        view = svc.message_to_dict(history[0])["reasoning"]
        full = await svc.get_message_reasoning(
            session, user, chat_id, history[0].id)
    assert view["status"] == "not_recorded"
    assert view["reasoning_status"] == "not_recorded"
    assert "text" not in view
    assert full["swipes"] == {"0": {"status": "not_recorded"}}


async def test_d4_full_document_road_all_swipes_and_404(tmp_path, monkeypatch):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    other = await make_user(factory, name="mallory")
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    record = rsn.build_record(status="recorded", text="first thought")
    async with factory() as session:
        message = await svc.append_message(
            session, user, chat_id, "assistant", "Answer.", reasoning=record)
        message_id = message.id
        await svc.add_swipe(session, user, chat_id, message_id, "Answer two.")
        full = await svc.get_message_reasoning(
            session, user, chat_id, message_id)
        assert full["swipes"]["0"] == {
            "status": "recorded", "text": "first thought"}
        assert full["swipes"]["1"] == {"status": "not_recorded"}
        assert full["message_id"] == message_id
        assert full["chat_id"] == chat_id
        assert await svc.get_message_reasoning(
            session, user, chat_id, "nope") is None
        assert await svc.get_message_reasoning(
            session, user, "nope", message_id) is None
        assert await svc.get_message_reasoning(
            session, other, chat_id, message_id) is None
    # HTTP road: exactly one reasoning road in the app, house 404 idiom.
    # P-210 heal: a second /reasoning road exists since
    # P-210 (the Inspector census road); the P-205
    # per-message road is still exactly one, now pinned
    # by its full path, and the /reasoning total is exact.
    client = make_client(tmp_path / "http", monkeypatch)
    paths = list(client.get("/openapi.json").json()["paths"])
    assert [
        p for p in paths if p.endswith("/messages/{message_id}/reasoning")
    ] == ["/api/v1/chats/{chat_id}/messages/{message_id}/reasoning"]
    assert len([p for p in paths if p.endswith("/reasoning")]) == 2
    created = client.post("/api/v1/chats", json={"title": "Saga"})
    assert created.status_code == 201, created.text
    http_chat = created.json()["id"]
    posted = client.post(
        f"/api/v1/chats/{http_chat}/messages",
        json={"role": "assistant", "content": "Answer."})
    assert posted.status_code == 201, posted.text
    http_message = posted.json()["id"]
    assert posted.json()["reasoning"]["status"] == "not_recorded"
    road = client.get(
        f"/api/v1/chats/{http_chat}/messages/{http_message}/reasoning")
    assert road.status_code == 200, road.text
    assert road.json()["swipes"] == {"0": {"status": "not_recorded"}}
    missing = client.get(
        f"/api/v1/chats/{http_chat}/messages/nope/reasoning")
    assert missing.status_code == 404
    foreign = client.get("/api/v1/chats/nope/messages/nope/reasoning")
    assert foreign.status_code == 404


async def test_d5_swipe_lifecycle_and_branch_copy(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    record = rsn.build_record(status="recorded", text="original thought")
    async with factory() as session:
        message = await svc.append_message(
            session, user, chat_id, "assistant", "Answer.", reasoning=record)
        message_id = message.id
        updated = await svc.add_swipe(
            session, user, chat_id, message_id, "Answer two.")
        doc = rsn.parse_document(updated.reasoning_json)
        assert doc["swipes"]["0"] == {
            "status": "recorded", "text": "original thought"}
        assert doc["swipes"]["1"] == {"status": "not_recorded"}
        updated = await svc.delete_swipe(
            session, user, chat_id, message_id, 1)
        doc = rsn.parse_document(updated.reasoning_json)
        assert doc["swipes"] == {
            "0": {"status": "recorded", "text": "original thought"}}
        result = await svc.copy_message_to_branch(
            session, user, chat_id, message_id)
        copied_doc = rsn.parse_document(result["copied_message"].reasoning_json)
    assert copied_doc["swipes"] == {
        "0": {"status": "recorded", "text": "original thought"}}


# -- E. End-to-end -------------------------------------------------------------


async def _bridge_world(factory, user):
    from runmal.characters.service import create_character
    async with factory() as session:
        character = await create_character(session, user, CARD)
        chat = await svc.create_chat(
            session, user, "Bridge chat", character_id=character.id)
        chat_id = chat.id
        await svc.append_message(session, user, chat_id, "user", "I seek passage.")
    return chat_id


async def _run_bridge_turn(factory, user, chat_id, backend, monkeypatch):
    from runmal.bridge import conversation

    async def fake_resolve(session, user_id, chat):
        return backend

    monkeypatch.setattr(conversation, "resolve_chat_backend", fake_resolve)
    return [event async for event in conversation.stream_generation(
        factory, user, "bridge-p205", chat_id, "req-p205-e")]


async def test_e1_bridge_turn_records_reasoning_verbatim(tmp_path, monkeypatch):
    from runmal.chats import provenance as prov_mod
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await _bridge_world(factory, user)
    backend = FakeChatBackend(
        chunks=("The bridge ", "is open."),
        reasoning_chunks=("weigh ", "the toll"))
    events = await _run_bridge_turn(factory, user, chat_id, backend, monkeypatch)
    kinds = [e["type"] for e in events]
    assert kinds[0] == "turn_started" and kinds[-1] == "turn_stored"
    assert [e["text"] for e in events if e["type"] == "reasoning"] == [
        "weigh ", "the toll"]
    message_id = events[-1]["message_id"]
    async with factory() as session:
        history = await svc.get_history(session, user, chat_id)
        message = [m for m in history if m.id == message_id][0]
        view = svc.message_to_dict(message)["reasoning"]
        prov_doc = prov_mod.parse_provenance(message)
    assert message.content == "The bridge is open."
    assert "weigh" not in message.content
    assert "toll" not in message.content
    assert view["status"] == "recorded"
    assert view["text"] == "weigh the toll"
    # the provenance document is unchanged in shape: same sections.
    assert prov_doc["recorded"] is True
    assert set(prov_doc["swipes"]["0"]) == {
        "origin", "model", "preset", "lore", "generation",
        "speaker", "amendments"}


async def test_e2_bridge_turn_without_reasoning_reads_not_present(
        tmp_path, monkeypatch):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await _bridge_world(factory, user)
    backend = FakeChatBackend(chunks=("Plain answer.",))
    events = await _run_bridge_turn(factory, user, chat_id, backend, monkeypatch)
    assert [e for e in events if e["type"] == "reasoning"] == []
    assert events[-1]["type"] == "turn_stored"
    message_id = events[-1]["message_id"]
    async with factory() as session:
        history = await svc.get_history(session, user, chat_id)
        message = [m for m in history if m.id == message_id][0]
        view = svc.message_to_dict(message)["reasoning"]
    assert message.content == "Plain answer."
    assert view["status"] == "not_present"
    assert "text" not in view


async def test_e3_unwired_roads_read_not_recorded(tmp_path):
    from runmal.characters.service import create_character
    from runmal.chats import continue_impersonate as ci
    from runmal.groupchat import store as group_store
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    backend = FakeChatBackend(
        chunks=("Well met, traveller.",),
        reasoning_chunks=("unseen thought",))
    async with factory() as session:
        result = await ci.continue_chat(session, user, chat_id, backend=backend)
    # P-207 supersedes the continue half of this pin: the continue
    # road now captures through its shared seam, so its message
    # reads recorded with the fake's scripted thought verbatim.
    assert result["message"]["content"] == "Well met, traveller."
    assert result["message"]["reasoning"]["status"] == "recorded"
    assert result["message"]["reasoning"]["text"] == "unseen thought"
    # the groupchat road writes its Message rows directly, with no
    # reasoning capture at all: not_recorded, never an invented record.
    async with factory() as session:
        character = await create_character(session, user, CARD)
        group = await group_store.create_group(
            session, user, "Mead Hall", [character.id])
        gmessage = await group_store.append_message(
            session, user, group.id, "user", "Hail all.")
    assert rsn.active_view(gmessage)["status"] == "not_recorded"
