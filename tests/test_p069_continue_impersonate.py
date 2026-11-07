"""P-069 Continue & impersonate battery (team-01).

Pins the mirrors' pair: CONTINUE (nudge-generation) and
IMPERSONATE (user-turn drafting by the model).

Continue: ``auto`` resolves to ``extend`` when the last message
is the assistant's (the generated fragment is appended onto
that message in place, swipe-deck aware) and to ``next``
otherwise (the generated text lands as a NEW assistant
message). Explicit modes are validated; an empty chat refuses;
a failed, cancelled, or empty generation stores nothing.

Impersonate: the model drafts the next USER turn and the
result is visibly a draft -- a draft document, never a
message. History is untouched until the user accepts a final
text (verbatim or edited) through the accept road, which is
the only road by which impersonated text becomes a message.
Discarding a draft stores nothing.

No migration taken by P-069: provisional 0040 is NOT used.
On this slice's base the head was 0037; at banking, P-068's
0038 (message actions) banked ahead of this slice, so the
merged head is 0038 -- from P-068, never from P-069.

Generation in these tests runs on the deterministic fake
backend: through the API it yields the stub text; at the
service layer an injected FakeChatBackend scripts the text.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends.errors import BackendUnavailable
from runmal.backends.fake import FakeChatBackend
from runmal.chats import continue_impersonate as ci
from runmal.chats import service as svc
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.db.migrations import MIGRATIONS
from runmal.db.models import User

STUB = "Rúnmál hears you. This is a stub."
SECRET = "ZqxDraftSecret69"

CARD = {
    "name": "Sigrun",
    "description": "A skald of the northern fjords.",
    "personality": "Warm, quick with a verse.",
    "scenario": "A fire-lit hall.",
    "first_mes": "Sit, tell me where you sailed.",
    "system_prompt": "You are Sigrun of the TESTHALL.",
}


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


def _chat(client, title="Saga", character_id=None):
    body = {"title": title}
    if character_id:
        body["character_id"] = character_id
    r = client.post("/api/v1/chats", json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _character(client):
    r = client.post("/api/v1/characters", json={"card": CARD})
    assert r.status_code in (200, 201), r.text
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


def _contents(client, chat_id):
    return [m["content"] for m in _history(client, chat_id)]


def _events(client, chat_id):
    r = client.get(f"/api/v1/chats/{chat_id}/events")
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


async def seed_chat(factory, user, turns):
    async with factory() as session:
        chat = await svc.create_chat(session, user, "Saga")
        chat_id = chat.id
        for role, content in turns:
            await svc.append_message(session, user, chat_id, role, content)
    return chat_id


# ---------------- migration: none taken ----------------


def test_migration_head_is_0038_from_p068_none_from_p069_no_0040(tmp_path):
    assert MIGRATIONS[-1][0] == "0038"
    assert all(rev != "0040" for rev, _desc, _mod in MIGRATIONS)
    db_path = tmp_path / "m.db"
    applied = migrate_to_head(db_path)
    assert applied[-1] == "0038"


# ---------------- pure: mode resolution ----------------

HIST_USER = [{"role": "user", "content": "Hail."}]
HIST_ASSISTANT = [
    {"role": "user", "content": "Hail."},
    {"role": "assistant", "content": "Well met."},
]


def test_resolve_mode_auto():
    assert ci.resolve_continue_mode(HIST_ASSISTANT) == "extend"
    assert ci.resolve_continue_mode(HIST_USER) == "next"
    assert ci.resolve_continue_mode([{"role": "system", "content": "s"}]) == "next"


def test_resolve_mode_explicit_and_validation():
    assert ci.resolve_continue_mode(HIST_USER, "next") == "next"
    assert ci.resolve_continue_mode(HIST_ASSISTANT, "next") == "next"
    assert ci.resolve_continue_mode(HIST_ASSISTANT, "extend") == "extend"
    with pytest.raises(ValueError):
        ci.resolve_continue_mode(HIST_USER, "extend")
    with pytest.raises(ValueError):
        ci.resolve_continue_mode(HIST_ASSISTANT, "sideways")
    with pytest.raises(ValueError):
        ci.resolve_continue_mode([], "auto")
    with pytest.raises(ValueError):
        ci.resolve_continue_mode([], "next")


# ---------------- pure: prompt builders ----------------


def test_build_continue_extend_prompt_shape():
    messages, resolved = ci.build_continue_messages(HIST_ASSISTANT, "SYS")
    assert resolved == "extend"
    assert [(m.role, m.content) for m in messages] == [
        ("system", "SYS"),
        ("user", "Hail."),
        ("assistant", "Well met."),
        ("system", ci.EXTEND_INSTRUCTION),
    ]


def test_build_continue_next_prompt_and_instruction_append():
    messages, resolved = ci.build_continue_messages(
        HIST_USER, "", instruction="Ask about the ship."
    )
    assert resolved == "next"
    assert messages[0].role == "user"  # no system prompt slot when empty
    last = messages[-1]
    assert last.role == "system"
    assert last.content.startswith(ci.NEXT_INSTRUCTION)
    assert "Ask about the ship." in last.content


def test_build_continue_blank_instruction_ignored_and_bad_type():
    messages, _ = ci.build_continue_messages(HIST_USER, "", instruction="   ")
    assert messages[-1].content == ci.NEXT_INSTRUCTION
    with pytest.raises(ValueError):
        ci.build_continue_messages(HIST_USER, "", instruction=7)


def test_build_impersonate_prompt_shape():
    messages = ci.build_impersonate_messages(HIST_ASSISTANT, "SYS")
    assert [(m.role, m.content) for m in messages] == [
        ("system", "SYS"),
        ("user", "Hail."),
        ("assistant", "Well met."),
        ("system", ci.IMPERSONATE_INSTRUCTION),
    ]
    with pytest.raises(ValueError):
        ci.build_impersonate_messages([], "SYS")


def test_instructions_are_distinct_and_first_person_for_impersonate():
    assert ci.EXTEND_INSTRUCTION != ci.NEXT_INSTRUCTION
    assert ci.NEXT_INSTRUCTION != ci.IMPERSONATE_INSTRUCTION
    assert "first person" in ci.IMPERSONATE_INSTRUCTION
    assert "user" in ci.IMPERSONATE_INSTRUCTION


# ---------------- service: continue ----------------


async def test_service_continue_extend_appends_in_place(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(
        factory, user, [("user", "Hail."), ("assistant", "Well met")]
    )
    backend = FakeChatBackend(chunks=(" and welcome.",))
    async with factory() as session:
        result = await ci.continue_chat(session, user, chat_id, backend=backend)
    assert result["mode"] == "extend"
    assert result["content"] == " and welcome."
    assert result["backend"] == "fake"
    assert result["generation_state"] == "committed"
    message = result["message"]
    assert message["content"] == "Well met and welcome."
    assert message["swipes"][message["swipe_id"]] == "Well met and welcome."
    assert result["continuation_of"] == message["id"]
    async with factory() as session:
        history = await svc.get_history(session, user, chat_id)
        assert len(history) == 2  # extended, not appended


async def test_service_continue_next_appends_assistant_message(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    backend = FakeChatBackend(chunks=("Well met, traveller.",))
    async with factory() as session:
        result = await ci.continue_chat(session, user, chat_id, backend=backend)
    assert result["mode"] == "next"
    assert result["continuation_of"] is None
    assert result["message"]["role"] == "assistant"
    assert result["message"]["content"] == "Well met, traveller."
    async with factory() as session:
        history = await svc.get_history(session, user, chat_id)
        assert [m.content for m in history] == ["Hail.", "Well met, traveller."]


async def test_service_continue_failure_stores_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    failing = FakeChatBackend(fail_with=BackendUnavailable("down"))
    empty = FakeChatBackend(chunks=())
    async with factory() as session:
        with pytest.raises(ci.GenerationFailedError):
            await ci.continue_chat(session, user, chat_id, backend=failing)
        with pytest.raises(ci.GenerationFailedError):
            await ci.continue_chat(session, user, chat_id, backend=empty)
        history = await svc.get_history(session, user, chat_id)
        assert [m.content for m in history] == ["Hail."]
        events = await svc.list_events(session, user, chat_id)
        assert not [e for e in events if e.kind == "message.continued"]


async def test_service_continue_empty_chat_and_bad_mode(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    async with factory() as session:
        chat = await svc.create_chat(session, user, "Empty")
        with pytest.raises(ValueError):
            await ci.continue_chat(session, user, chat.id)
        chat_id = await seed_chat(factory, user, [("user", "Hail.")])
        with pytest.raises(ValueError):
            await ci.continue_chat(session, user, chat_id, mode="extend")
        with pytest.raises(ValueError):
            await ci.continue_chat(session, user, chat_id, mode="bogus")


# ---------------- service: impersonate ----------------


async def test_service_impersonate_draft_never_lands(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(
        factory, user, [("user", "Hail, Sigrun."), ("assistant", "Well met.")]
    )
    backend = FakeChatBackend(chunks=(SECRET + " draft words",))
    async with factory() as session:
        draft = await ci.impersonate_draft(session, user, chat_id, backend=backend)
    assert draft["status"] == "draft"
    assert draft["draft"] is True
    assert draft["role"] == "user"
    assert draft["message_id"] is None
    assert draft["content"] == SECRET + " draft words"
    assert draft["generation_state"] == "candidate_ready"
    assert draft["based_on_message_id"]
    async with factory() as session:
        history = await svc.get_history(session, user, chat_id)
        assert len(history) == 2  # the draft is NOT in history
        events = await svc.list_events(session, user, chat_id)
        drafted = [e for e in events if e.kind == "impersonate.drafted"]
        assert len(drafted) == 1
        # metadata only: the drafted text never reaches the event log
        assert SECRET not in json.dumps([svc.event_to_dict(e) for e in events])


async def test_service_accept_impersonate_verbatim_and_edited(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    async with factory() as session:
        m1 = await ci.accept_impersonate(
            session, user, chat_id, "Tell me of the sea.", draft_id="d1"
        )
        assert m1.role == "user" and m1.content == "Tell me of the sea."
        m2 = await ci.accept_impersonate(session, user, chat_id, "Edited words.")
        assert m2.content == "Edited words."
        history = await svc.get_history(session, user, chat_id)
        assert [m.content for m in history] == [
            "Hail.",
            "Tell me of the sea.",
            "Edited words.",
        ]
        events = await svc.list_events(session, user, chat_id)
        accepted = [e for e in events if e.kind == "impersonate.accepted"]
        assert len(accepted) == 2
        with pytest.raises(ValueError):
            await ci.accept_impersonate(session, user, chat_id, "")


async def test_service_discard_impersonate_stores_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    async with factory() as session:
        assert await ci.discard_impersonate(session, user, chat_id, draft_id="d9")
        history = await svc.get_history(session, user, chat_id)
        assert len(history) == 1
        events = await svc.list_events(session, user, chat_id)
        discarded = [e for e in events if e.kind == "impersonate.discarded"]
        assert len(discarded) == 1
        assert svc.event_to_dict(discarded[0])["data"] == {"draft_id": "d9"}


async def test_service_owner_isolation(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    other = await make_user(factory, "intruder")
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    backend = FakeChatBackend(chunks=("nope",))
    async with factory() as session:
        assert await ci.continue_chat(session, other, chat_id, backend=backend) is None
        assert await ci.impersonate_draft(session, other, chat_id, backend=backend) is None
        assert await ci.accept_impersonate(session, other, chat_id, "x") is None
        assert await ci.discard_impersonate(session, other, chat_id) is False
        assert await ci.continue_chat(session, user, "missing", backend=backend) is None
        assert await ci.impersonate_draft(session, user, "missing") is None
        history = await svc.get_history(session, user, chat_id)
        assert len(history) == 1


# ---------------- API: continue ----------------


def test_api_continue_next_then_extend_with_fake_backend(app_client):
    chat = _chat(app_client)
    _msg(app_client, chat["id"], "Hail.")
    r = app_client.post(f"/api/v1/chats/{chat['id']}/continue", json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["kind"] == "continue"
    assert body["mode"] == "next"
    assert body["content"] == STUB
    assert body["message"]["role"] == "assistant"
    assert body["message"]["content"] == STUB
    assert _contents(app_client, chat["id"]) == ["Hail.", STUB]
    # last message is now the assistant's: auto resolves to extend
    r = app_client.post(f"/api/v1/chats/{chat['id']}/continue", json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["mode"] == "extend"
    assert body["continuation_of"] == body["message"]["id"]
    assert _contents(app_client, chat["id"]) == ["Hail.", STUB + STUB]
    assert len(_history(app_client, chat["id"])) == 2


def test_api_continue_events_metadata_only(app_client):
    chat = _chat(app_client)
    _msg(app_client, chat["id"], "Hail.")
    app_client.post(f"/api/v1/chats/{chat['id']}/continue", json={})
    events = _events(app_client, chat["id"])
    continued = [e for e in events if e["kind"] == "message.continued"]
    assert len(continued) == 1
    assert continued[0]["data"]["mode"] == "next"
    assert continued[0]["data"]["chars"] == len(STUB)
    assert STUB not in json.dumps(continued)


def test_api_continue_empty_chat_422_and_missing_404(app_client):
    chat = _chat(app_client)
    r = app_client.post(f"/api/v1/chats/{chat['id']}/continue", json={})
    assert r.status_code == 422, r.text
    r = app_client.post("/api/v1/chats/missing/continue", json={})
    assert r.status_code == 404, r.text
    _msg(app_client, chat["id"], "Hail.")
    r = app_client.post(
        f"/api/v1/chats/{chat['id']}/continue", json={"mode": "extend"}
    )
    assert r.status_code == 422, r.text
    r = app_client.post(
        f"/api/v1/chats/{chat['id']}/continue", json={"mode": "bogus"}
    )
    assert r.status_code == 422, r.text


def test_api_continue_with_character_speaker_snapshot(app_client):
    character = _character(app_client)
    chat = _chat(app_client, character_id=character["id"])
    _msg(app_client, chat["id"], "Hail.")
    r = app_client.post(f"/api/v1/chats/{chat['id']}/continue", json={})
    assert r.status_code == 201, r.text
    message = r.json()["message"]
    assert message["speaker_id"] == character["id"]
    assert message["speaker_name"] == "Sigrun"


# ---------------- API: impersonate ----------------


def test_api_impersonate_draft_is_not_a_message(app_client):
    chat = _chat(app_client)
    _msg(app_client, chat["id"], "Hail, Sigrun.")
    _msg(app_client, chat["id"], "Well met.", role="assistant")
    before = _history(app_client, chat["id"])
    r = app_client.post(f"/api/v1/chats/{chat['id']}/impersonate", json={})
    assert r.status_code == 201, r.text
    draft = r.json()
    assert draft["status"] == "draft"
    assert draft["draft"] is True
    assert draft["role"] == "user"
    assert draft["message_id"] is None
    assert draft["content"] == STUB
    assert draft["based_on_message_id"] == before[-1]["id"]
    assert draft["generation_state"] == "candidate_ready"
    # history is exactly as it was: the draft never landed
    assert _history(app_client, chat["id"]) == before


def test_api_impersonate_accept_edited_text_lands(app_client):
    chat = _chat(app_client)
    _msg(app_client, chat["id"], "Hail.")
    draft = app_client.post(f"/api/v1/chats/{chat['id']}/impersonate", json={}).json()
    r = app_client.post(
        f"/api/v1/chats/{chat['id']}/impersonate/accept",
        json={"content": "My own edited words.", "draft_id": draft["id"]},
    )
    assert r.status_code == 201, r.text
    message = r.json()
    assert message["role"] == "user"
    assert message["content"] == "My own edited words."
    assert _contents(app_client, chat["id"]) == ["Hail.", "My own edited words."]
    events = _events(app_client, chat["id"])
    kinds = [e["kind"] for e in events]
    assert "impersonate.drafted" in kinds
    assert "impersonate.accepted" in kinds


def test_api_impersonate_discard_stores_nothing(app_client):
    chat = _chat(app_client)
    _msg(app_client, chat["id"], "Hail.")
    draft = app_client.post(f"/api/v1/chats/{chat['id']}/impersonate", json={}).json()
    r = app_client.post(
        f"/api/v1/chats/{chat['id']}/impersonate/discard",
        json={"draft_id": draft["id"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["discarded"] is True
    assert _contents(app_client, chat["id"]) == ["Hail."]
    kinds = [e["kind"] for e in _events(app_client, chat["id"])]
    assert "impersonate.discarded" in kinds
    assert "impersonate.accepted" not in kinds


def test_api_impersonate_empty_chat_422_missing_404(app_client):
    chat = _chat(app_client)
    r = app_client.post(f"/api/v1/chats/{chat['id']}/impersonate", json={})
    assert r.status_code == 422, r.text
    r = app_client.post("/api/v1/chats/missing/impersonate", json={})
    assert r.status_code == 404, r.text
    r = app_client.post(
        "/api/v1/chats/missing/impersonate/accept", json={"content": "x"}
    )
    assert r.status_code == 404, r.text
    r = app_client.post(
        "/api/v1/chats/missing/impersonate/discard", json={}
    )
    assert r.status_code == 404, r.text
    r = app_client.post(
        f"/api/v1/chats/{chat['id']}/impersonate/accept", json={"content": ""}
    )
    assert r.status_code == 422, r.text


def test_api_exports_surface(app_client):
    from runmal.chats import (
        accept_impersonate,
        build_continue_messages,
        build_impersonate_messages,
        continue_chat,
        discard_impersonate,
        impersonate_draft,
        resolve_continue_mode,
    )

    for fn in (
        accept_impersonate,
        build_continue_messages,
        build_impersonate_messages,
        continue_chat,
        discard_impersonate,
        impersonate_draft,
        resolve_continue_mode,
    ):
        assert callable(fn)

# ---------------- P-069 hardening: designer-review clauses ----------------


async def test_service_continue_cancelled_stores_nothing(tmp_path):
    from runmal.backends.errors import GenerationCancelled

    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(
        factory, user, [("user", "Hail."), ("assistant", "Well met.")]
    )
    cancelled = FakeChatBackend(fail_with=GenerationCancelled("cancelled"))
    async with factory() as session:
        with pytest.raises(ci.GenerationFailedError):
            await ci.continue_chat(session, user, chat_id, backend=cancelled)
        history = await svc.get_history(session, user, chat_id)
        assert [m.content for m in history] == ["Hail.", "Well met."]
        events = await svc.list_events(session, user, chat_id)
        assert not [e for e in events if e.kind == "message.continued"]


async def test_service_impersonate_failure_stores_nothing_no_drafted_event(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(
        factory, user, [("user", "Hail."), ("assistant", "Well met.")]
    )
    failing = FakeChatBackend(fail_with=BackendUnavailable("down"))
    async with factory() as session:
        with pytest.raises(ci.GenerationFailedError):
            await ci.impersonate_draft(session, user, chat_id, backend=failing)
        history = await svc.get_history(session, user, chat_id)
        assert [m.content for m in history] == ["Hail.", "Well met."]
        events = await svc.list_events(session, user, chat_id)
        assert not [e for e in events if e.kind == "impersonate.drafted"]


async def test_service_continue_whitespace_only_stores_nothing(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    whitespace = FakeChatBackend(chunks=("   ", " \n\t "))
    async with factory() as session:
        with pytest.raises(ci.GenerationFailedError):
            await ci.continue_chat(session, user, chat_id, backend=whitespace)
        history = await svc.get_history(session, user, chat_id)
        assert [m.content for m in history] == ["Hail."]
        events = await svc.list_events(session, user, chat_id)
        assert not [e for e in events if e.kind == "message.continued"]


async def test_service_accept_impersonate_whitespace_only_rejected(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    async with factory() as session:
        with pytest.raises(ValueError):
            await ci.accept_impersonate(session, user, chat_id, "   \n\t  ")
        history = await svc.get_history(session, user, chat_id)
        assert [m.content for m in history] == ["Hail."]
        events = await svc.list_events(session, user, chat_id)
        assert not [e for e in events if e.kind == "impersonate.accepted"]


async def test_service_impersonate_draft_document_completeness(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(
        factory, user, [("user", "Hail."), ("assistant", "Well met.")]
    )
    backend = FakeChatBackend(chunks=("Draft words.",))
    async with factory() as session:
        draft = await ci.impersonate_draft(session, user, chat_id, backend=backend)
    assert isinstance(draft["fingerprint"], str)
    assert draft["fingerprint"] != ""
    assert "backend" in draft
    assert draft["backend"] == "fake"
    assert draft["backend"] == backend.backend_key


async def test_service_accept_impersonate_events_metadata_only_and_source(tmp_path):
    factory = make_factory(tmp_path)
    user = await make_user(factory)
    chat_id = await seed_chat(factory, user, [("user", "Hail.")])
    accepted_text = "ZqxAcceptedSecret69 own words"
    async with factory() as session:
        message = await ci.accept_impersonate(
            session, user, chat_id, accepted_text, draft_id="d-accept"
        )
        assert message.content == accepted_text
        events = await svc.list_events(session, user, chat_id)
        accepted = [e for e in events if e.kind == "impersonate.accepted"]
        assert len(accepted) == 1
        # metadata only: the accepted text never reaches the event payload
        assert svc.event_to_dict(accepted[0])["data"] == {"draft_id": "d-accept"}
        assert accepted_text not in json.dumps(
            [svc.event_to_dict(e) for e in accepted]
        )
        # the appended user message carries its origin on its creation event
        appended = [
            e
            for e in events
            if e.kind == "message.appended" and e.message_id == message.id
        ]
        assert len(appended) == 1
        data = svc.event_to_dict(appended[0])["data"]
        assert data["source"] == "impersonate"
        assert data["role"] == "user"


def test_build_impersonate_messages_instruction_merged_into_trailing_system():
    messages = ci.build_impersonate_messages(
        HIST_ASSISTANT, "SYS", instruction="Ask about the ship."
    )
    assert [(m.role, m.content) for m in messages[:-1]] == [
        ("system", "SYS"),
        ("user", "Hail."),
        ("assistant", "Well met."),
    ]
    last = messages[-1]
    assert last.role == "system"
    assert last.content.startswith(ci.IMPERSONATE_INSTRUCTION)
    assert "Ask about the ship." in last.content
    # exactly one trailing system instruction carries the impersonate text
    carriers = [m for m in messages if ci.IMPERSONATE_INSTRUCTION in m.content]
    assert len(carriers) == 1
    assert carriers[0] is last


def test_generation_failed_error_exported_from_chats_package():
    import runmal.chats as chats_pkg

    exported = chats_pkg.GenerationFailedError
    assert exported is ci.GenerationFailedError
    assert isinstance(exported, type)
    assert issubclass(exported, Exception)


def test_api_continue_failing_backend_returns_502(app_client, monkeypatch):
    async def _failing_resolve(session, user_id, chat):
        return FakeChatBackend(fail_with=BackendUnavailable("down"))

    monkeypatch.setattr(ci, "resolve_backend", _failing_resolve)
    chat = _chat(app_client)
    _msg(app_client, chat["id"], "Hail.")
    r = app_client.post(f"/api/v1/chats/{chat['id']}/continue", json={})
    assert r.status_code == 502, r.text
    assert _contents(app_client, chat["id"]) == ["Hail."]
