"""R-05 acceptance (wizard logic): the Qt-free view-model layer over
a MockTransport engine — backend choices in plain words, Ollama
detection through the R-02 roads, profile creation + write-only
secret handling, plain-words proof, character create/import, the
greeted chat, the persisted user name, and the composed turn.

No Qt here: the wizard widgets are gated separately
(``test_r05_desktop_wizard.py``) and the live engine end-to-end in
``test_r05_wizard_live.py``.
"""

import json

import httpx
import pytest

from runmal.desktop.client import (
    DesktopSession,
    RunmalClient,
)
from runmal.desktop.client.errors import ClientError
from runmal.desktop.wizard_logic import (
    BACKEND_OPTIONS,
    WizardFlow,
    backend_option,
    health_words,
    plain_reason,
)

TOKEN = "R05-TEST-CREDENTIAL"
CANARY = "R05-CANARY-KEY-VALUE"


class FakeEngine:
    """A stateful in-memory stand-in for the R-02/R-03 roads."""

    def __init__(self, *, ollama_ok=True, models_fail=False):
        self.profiles: dict[str, dict] = {}
        self.characters: dict[str, dict] = {}
        self.chats: dict[str, dict] = {}
        self.user_name = ""
        self.secrets_seen: list[str] = []
        self.ollama_ok = ollama_ok
        self.models_fail = models_fail
        self._seq = 0

    def _id(self, prefix):
        self._seq += 1
        return f"{prefix}{self._seq}"

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.headers.get("authorization") != f"Bearer {TOKEN}":
            return httpx.Response(401, json={"detail": "no auth"})
        body = {}
        if request.content:
            try:
                body = json.loads(request.content)
            except ValueError:
                body = {}

        if path == "/api/v1/backend-profiles" and request.method == "POST":
            pid = self._id("p")
            profile = {
                "id": pid,
                "name": body.get("name", ""),
                "chat_backend": body.get("chat_backend", ""),
                "chat_model": body.get("chat_model", ""),
                "embedding_backend": "",
                "embedding_model": "",
                "has_chat_secret": False,
                "has_embedding_secret": False,
                "config": body.get("config") or {},
            }
            self.profiles[pid] = profile
            return httpx.Response(201, json=profile)
        if path == "/api/v1/backend-profiles" and request.method == "GET":
            return httpx.Response(200, json=list(self.profiles.values()))
        if path.startswith("/api/v1/backend-profiles/"):
            rest = path[len("/api/v1/backend-profiles/"):]
            pid, _, tail = rest.partition("/")
            profile = self.profiles.get(pid)
            if profile is None:
                return httpx.Response(404, json={"detail": "not found"})
            if tail == "chat-secret" and request.method == "PUT":
                # The canary is recorded test-side ONLY, to prove the
                # value reached the secret route and nothing else.
                self.secrets_seen.append(body.get("value", ""))
                profile["has_chat_secret"] = True
                return httpx.Response(200, json=profile)
            if tail == "health":
                if profile["chat_backend"] == "ollama" and not self.ollama_ok:
                    return httpx.Response(200, json={
                        "profile_id": pid, "backend": "ollama",
                        "model": profile["chat_model"], "ok": False,
                        "detail": "ollama unreachable: ConnectError",
                        "latency_ms": None,
                    })
                return httpx.Response(200, json={
                    "profile_id": pid,
                    "backend": profile["chat_backend"],
                    "model": profile["chat_model"], "ok": True,
                    "detail": "reachable", "latency_ms": 3.25,
                })
            if tail == "models":
                if self.models_fail:
                    return httpx.Response(
                        502, json={"detail": "ollama unreachable"})
                models = {
                    "fake": [{"model_id": "fake-1", "backend_key": "fake"}],
                    "ollama": [
                        {"model_id": "llama3", "backend_key": "ollama"},
                        {"model_id": "mistral", "backend_key": "ollama"},
                    ],
                }.get(profile["chat_backend"], [
                    {"model_id": "m1", "backend_key": profile["chat_backend"]}
                ])
                return httpx.Response(200, json={
                    "profile_id": pid,
                    "backend": profile["chat_backend"],
                    "models": models,
                })
            if request.method == "PATCH":
                profile.update({k: v for k, v in body.items() if v is not None})
                return httpx.Response(200, json=profile)
            if request.method == "DELETE":
                del self.profiles[pid]
                return httpx.Response(200, json={"ok": True})
            if request.method == "GET":
                return httpx.Response(200, json=profile)

        if path == "/api/v1/characters" and request.method == "POST":
            kid = self._id("k")
            card = body.get("card") or {}
            character = {"id": kid, "name": body.get("name") or card.get("name", "")}
            self.characters[kid] = {**character, "card": card}
            return httpx.Response(201, json=character)
        if path == "/api/v1/characters" and request.method == "GET":
            rows = [
                {"id": c["id"], "name": c["name"], "has_avatar": False}
                for c in self.characters.values()
            ]
            return httpx.Response(200, json=rows)

        if path == "/api/v1/library/imports" and request.method == "POST":
            kid = self._id("k")
            self.characters[kid] = {"id": kid, "name": "Imported Sage"}
            return httpx.Response(200, json={
                "totals": {"total_seen": 1, "accepted": 1},
                "entries": [{
                    "detected_kind": "card", "outcome": "accepted",
                    "created_id": kid, "created_name": "Imported Sage",
                    "reason": "",
                }],
                "skipped": [],
            })

        if path == "/api/v1/chats" and request.method == "POST":
            cid = self._id("c")
            chat = {
                "id": cid, "title": body.get("title", ""),
                "character_id": body.get("character_id"),
                "backend_profile_id": None, "preset_id": None,
                "message_count": 1,
            }
            self.chats[cid] = chat
            return httpx.Response(201, json=chat)
        if path.startswith("/api/v1/chats/"):
            rest = path[len("/api/v1/chats/"):]
            cid, _, tail = rest.partition("/")
            chat = self.chats.get(cid)
            if chat is None:
                return httpx.Response(404, json={"detail": "chat not found"})
            if tail == "backend-profile" and request.method == "POST":
                chat["backend_profile_id"] = body.get("profile_id")
                return httpx.Response(200, json=chat)
            if tail == "messages":
                return httpx.Response(200, json=[{
                    "id": "m1", "role": "assistant",
                    "content": "Well met, traveller.",
                    "speaker_name": "Gate Keeper",
                }])

        if path == "/api/v1/user-name":
            if request.method == "PUT":
                self.user_name = body.get("user_name", "")
            return httpx.Response(200, json={
                "user_name": self.user_name or "User",
                "is_set": bool(self.user_name),
            })

        if path == "/api/v1/generate" and request.method == "POST":
            sse = (
                'data: {"type": "token", "text": "Rúnmál "}\n\n'
                'data: {"type": "token", "text": "hears you."}\n\n'
                'data: {"type": "done", "finish_reason": "stop"}\n\n'
            )
            return httpx.Response(
                200,
                content=sse.encode(),
                headers={
                    "content-type": "text/event-stream",
                    "x-backend-key": "fake",
                    "x-generation-mode": "composed",
                },
            )
        return httpx.Response(404, json={"detail": "not found"})


def make_flow(engine=None):
    engine = engine or FakeEngine()
    session = DesktopSession("http://127.0.0.1:9", bearer_token=TOKEN)
    http = httpx.Client(
        base_url="http://127.0.0.1:9",
        transport=httpx.MockTransport(engine),
        trust_env=False,
    )
    client = RunmalClient(session, http=http)
    return WizardFlow(client), client, engine


# ------------------------------------------------------------ plain words


def test_backend_options_are_plain_and_demo_is_honest() -> None:
    kinds = [o.kind for o in BACKEND_OPTIONS]
    assert kinds == ["ollama", "openrouter", "openai", "aesir", "fake"]
    demo = backend_option("fake")
    assert "not a real model" in demo.title.lower()
    assert "canned" in demo.blurb.lower()
    assert "not a model" in demo.blurb.lower()
    for option in BACKEND_OPTIONS:
        assert option.title and option.blurb and option.profile_name
    assert backend_option("openrouter").needs_api_key is True
    with pytest.raises(ValueError):
        backend_option("carrier-pigeon")


def test_plain_reason_never_shows_raw_json() -> None:
    assert plain_reason('{"detail": "x"}').startswith("the backend answered")
    assert plain_reason("") == "the backend gave no reason"
    assert plain_reason("ollama unreachable: ConnectError") == (
        "ollama unreachable: ConnectError"
    )


def test_health_words_reachable_and_unreachable() -> None:
    ok_words = health_words(
        "Ollama (local)",
        {"ok": True, "latency_ms": 12.4},
        [{"model_id": "llama3"}, {"model_id": "mistral"}],
    )
    assert ok_words.startswith("Reachable")
    assert "2 model(s)" in ok_words and "llama3" in ok_words
    assert "{" not in ok_words
    bad_words = health_words(
        "Ollama (local)",
        {"ok": False, "detail": "ollama unreachable: ConnectError"},
    )
    assert bad_words.startswith("Not reachable")
    assert "ConnectError" in bad_words and "{" not in bad_words


# -------------------------------------------------------------- step 1 + 2


def test_demo_profile_create_and_prove() -> None:
    flow, client, engine = make_flow()
    profile = flow.create_chosen_profile("fake")
    assert profile.chat_backend == "fake"
    assert profile.chat_model == "fake-1"
    assert profile.name == "Demo mode"
    result = flow.prove()
    assert result.ok is True
    assert result.words.startswith("Reachable")
    assert "Demo mode" in result.words
    assert result.model_count == 1 and result.models == ["fake-1"]
    client.close()


def test_secret_is_write_only_and_never_retained() -> None:
    flow, client, engine = make_flow()
    profile = flow.create_chosen_profile(
        "openrouter", chat_model="some/model", api_key=CANARY
    )
    assert engine.secrets_seen == [CANARY]
    assert profile.has_chat_secret is True
    # The value exists nowhere on the flow, the profile, or in words.
    assert CANARY not in repr(flow.__dict__)
    assert CANARY not in repr(profile)
    assert not hasattr(profile, "chat_secret")
    result = flow.prove()
    assert CANARY not in result.words
    client.close()


def test_ollama_detect_reachable_lists_models_and_reuses_profile() -> None:
    flow, client, engine = make_flow()
    found = flow.detect_ollama()
    assert found.reachable is True
    assert found.models == ["llama3", "mistral"]
    assert "Ollama is running" in found.words
    # Detection created exactly one draft profile through R-02.
    assert len(engine.profiles) == 1
    # Choosing the detected model finishes that same profile.
    profile = flow.create_chosen_profile("ollama", chat_model="llama3")
    assert len(engine.profiles) == 1
    assert profile.id == found.profile.id
    assert profile.chat_model == "llama3"
    client.close()


def test_ollama_detect_unreachable_is_plain_words_not_an_exception() -> None:
    flow, client, engine = make_flow(FakeEngine(ollama_ok=False))
    found = flow.detect_ollama()
    assert found.reachable is False
    assert found.models == []
    assert "No Ollama answered" in found.words
    assert "{" not in found.words
    client.close()


def test_detect_draft_is_removed_when_another_mind_is_chosen() -> None:
    flow, client, engine = make_flow()
    found = flow.detect_ollama()
    assert found.reachable is True
    assert len(engine.profiles) == 1
    profile = flow.create_chosen_profile("fake")
    assert profile.chat_backend == "fake"
    # The speculative Ollama draft is gone; only the chosen one stays.
    assert [p["id"] for p in engine.profiles.values()] == [profile.id]
    client.close()


def test_prove_survives_a_failing_model_list() -> None:
    flow, client, engine = make_flow(FakeEngine(models_fail=True))
    flow.create_chosen_profile("fake")
    result = flow.prove()
    assert result.ok is True
    assert "model list could not be read" in result.words
    client.close()


def test_client_profile_crud_round_trip() -> None:
    flow, client, engine = make_flow()
    profile = client.create_backend_profile(
        "scratch", "openai", chat_model="m", config={"base_url": "http://x"}
    )
    assert client.get_backend_profile(profile.id).name == "scratch"
    updated = client.update_backend_profile(profile.id, chat_model="m2")
    assert updated.chat_model == "m2"
    assert client.delete_backend_profile(profile.id) is True
    assert client.list_backend_profiles() == []
    client.close()


# ------------------------------------------------------------------ step 3


def test_create_character_then_greeted_chat_pins_profile() -> None:
    flow, client, engine = make_flow()
    profile = flow.create_chosen_profile("fake")
    character = flow.create_character(
        name="Gate Keeper",
        description="Guards the pass.",
        personality="Calm and dry.",
        first_greeting="Well met, traveller.",
    )
    assert character.name == "Gate Keeper"
    card = engine.characters[character.id]["card"]
    assert card["first_mes"] == "Well met, traveller."
    assert card["description"] == "Guards the pass."

    greeted = flow.open_greeted_chat()
    assert greeted.chat.character_id == character.id
    assert greeted.greeting == "Well met, traveller."
    assert greeted.chat.backend_profile_id == profile.id
    assert greeted.chat.title == "First chat with Gate Keeper"
    client.close()


def test_create_character_requires_a_name() -> None:
    flow, client, _engine = make_flow()
    with pytest.raises(ClientError):
        flow.create_character(name="  ")
    client.close()


def test_import_character_via_library_road() -> None:
    flow, client, _engine = make_flow()
    character = flow.import_character("sage.json", b'{"name": "Imported Sage"}')
    assert character.name == "Imported Sage"
    greeted = flow.open_greeted_chat(character.id)
    assert greeted.chat.character_id == character.id
    client.close()


def test_import_refusal_is_a_plain_error() -> None:
    flow, client, engine = make_flow()

    def refusing(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/library/imports":
            return httpx.Response(200, json={
                "totals": {"total_seen": 1, "refused": 1},
                "entries": [{
                    "detected_kind": "card", "outcome": "refused",
                    "created_id": None, "reason": "not a card",
                }],
                "skipped": [],
            })
        return engine(request)

    session = DesktopSession("http://127.0.0.1:9", bearer_token=TOKEN)
    http = httpx.Client(
        base_url="http://127.0.0.1:9",
        transport=httpx.MockTransport(refusing),
        trust_env=False,
    )
    flow2 = WizardFlow(RunmalClient(session, http=http))
    with pytest.raises(ClientError) as caught:
        flow2.import_character("junk.json", b"junk")
    assert "did not import" in str(caught.value)
    client.close()


# ------------------------------------------------------------------ step 4


def test_user_name_round_trip_and_empty_keeps_current() -> None:
    flow, client, engine = make_flow()
    assert flow.get_user_name() == "User"
    assert flow.set_user_name("Volmarr") == "Volmarr"
    assert engine.user_name == "Volmarr"
    assert flow.set_user_name("   ") == "Volmarr"  # empty never clears here
    client.close()


# ------------------------------------------------------------- composed turn


def test_composed_turn_collects_sse_tokens() -> None:
    flow, client, _engine = make_flow()
    flow.create_chosen_profile("fake")
    flow.create_character(name="Gate Keeper", first_greeting="Well met.")
    greeted = flow.open_greeted_chat()
    reply = client.generate_composed(greeted.chat.id)
    assert reply.text == "Rúnmál hears you."
    assert reply.backend_key == "fake"
    assert reply.mode == "composed"
    client.close()
