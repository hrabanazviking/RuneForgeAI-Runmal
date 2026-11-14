"""R-03 acceptance: the composed turn.

Chat-bound generation over POST /generate (compose via the
bridge-proven compose_messages path, chat profile resolution, preset
params + per-send overrides with the documented precedence), the new
`params` field reaching the backend, the local persona route, and
the persisted {{user}} name — with the raw-messages contract proven
unchanged.

Params/composition proof uses a recording backend: an echo subclass
of FakeChatBackend that captures the exact messages + SamplingParams
it is handed and streams the composed system prompt back, so the
HTTP tests assert on what the backend RECEIVED, not on stub text.
"""

import json

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends.events import Done, TextDelta
from runmal.backends.fake import FakeChatBackend
from runmal.backends.params import SamplingParams
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head

CARD = {
    "name": "Gate Keeper",
    "description": "Keeper of the gate at R03HOLD.",
    "personality": "Stern but fair.",
    "scenario": "A stone gate.",
    "first_mes": "State your business.",
    "system_prompt": "You are the Gate Keeper of R03HOLD. You serve {{user}}.",
}
OTHER_CARD = {
    "name": "Ferryman",
    "description": "Rows the cold river.",
    "system_prompt": "You are the Ferryman of the COLD RIVER.",
}


class RecordingBackend(FakeChatBackend):
    """Fake backend that records its inputs and echoes the composed
    messages back as its reply text."""

    def __init__(self, captured: dict):
        super().__init__(chunks=("recorded",))
        self.captured = captured

    async def chat_stream(self, messages, params, cancel, *, structured=None):
        self.captured["messages"] = list(messages)
        self.captured["params"] = params
        text = " | ".join(m.content for m in messages)
        yield TextDelta(f"ECHO[{text}]")
        yield Done("stop", None)


def make_client(tmp_path, monkeypatch, *, auth=True):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    if auth:
        token = get_or_create_credential()
        client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _sse_text(resp) -> str:
    events = [
        json.loads(line.removeprefix("data: "))
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    return "".join(e["text"] for e in events if e["type"] == "token")


def _world(client, *, pin_profile=True):
    """Character + quiet chat + one stored user message (+ a fake
    backend profile pinned to the chat). Returns (character, chat,
    profile_id|None)."""
    character = client.post("/api/v1/characters", json={"card": CARD}).json()
    chat = client.post(
        "/api/v1/chats",
        json={
            "title": "Gate chat",
            "character_id": character["id"],
            "greeting_mode": "quiet",
        },
    ).json()
    client.post(
        f"/api/v1/chats/{chat['id']}/messages",
        json={"role": "user", "content": "I seek passage."},
    )
    profile_id = None
    if pin_profile:
        profile_id = client.post(
            "/api/v1/backend-profiles",
            json={"name": "hearth", "chat_backend": "fake", "chat_model": "fake-1"},
        ).json()["id"]
        resp = client.post(
            f"/api/v1/chats/{chat['id']}/backend-profile",
            json={"profile_id": profile_id},
        )
        assert resp.status_code == 200, resp.text
    return character, chat, profile_id


def _patch_profile_backend(monkeypatch, captured):
    from runmal.backends import profiles as profiles_mod

    backend = RecordingBackend(captured)

    async def fake_build(session, profile):
        return backend

    monkeypatch.setattr(profiles_mod, "build_chat_backend", fake_build)
    return backend


# ------------------------------------------------------- composed mode


def test_composed_turn_sends_character_system_prompt_first(
    tmp_path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    captured: dict = {}
    _patch_profile_backend(monkeypatch, captured)
    _, chat, _ = _world(client)

    resp = client.post("/api/v1/generate", json={"chat_id": chat["id"]})
    assert resp.status_code == 200, resp.text
    assert resp.headers["x-generation-mode"] == "composed"
    assert resp.headers["x-backend-key"] == "fake"

    messages = captured["messages"]
    assert messages[0].role == "system"
    assert "Gate Keeper of R03HOLD" in messages[0].content
    # {{user}} resolves to the default when no name is set.
    assert "You serve User." in messages[0].content
    assert messages[-1].role == "user"
    assert messages[-1].content == "I seek passage."
    # The streamed reply is the echo of the composed prompt: the
    # system prompt really crossed the backend seam.
    assert "Gate Keeper of R03HOLD" in _sse_text(resp)


def test_composed_turn_requires_an_existing_chat(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    assert client.post(
        "/api/v1/generate", json={"chat_id": "ghost"}
    ).status_code == 404
    # Neither messages nor chat_id: the pre-R-03 422 stands.
    assert client.post("/api/v1/generate", json={}).status_code == 422
    assert client.post(
        "/api/v1/generate", json={"messages": []}
    ).status_code == 422


def test_composed_turn_empty_chat_is_422(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    chat = client.post("/api/v1/chats", json={"title": "empty"}).json()
    resp = client.post("/api/v1/generate", json={"chat_id": chat["id"]})
    assert resp.status_code == 422


# ------------------------------------------------------------ raw mode


def test_raw_contract_unchanged(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/v1/generate",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["x-generation-mode"] == "raw"
    assert resp.headers["x-backend-key"] == "fake"
    assert _sse_text(resp) == "Rúnmál hears you. This is a stub."


def test_raw_mode_with_chat_id_still_sends_messages_verbatim(
    tmp_path, monkeypatch
) -> None:
    """chat_id + messages = raw mode: the supplied messages are the
    prompt (no composition), the chat only supplies profile/preset
    resolution — the pre-R-03 meaning of chat_id on this route."""
    client = make_client(tmp_path, monkeypatch)
    captured: dict = {}
    _patch_profile_backend(monkeypatch, captured)
    _, chat, _ = _world(client)
    resp = client.post(
        "/api/v1/generate",
        json={
            "chat_id": chat["id"],
            "messages": [{"role": "user", "content": "verbatim line"}],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["x-generation-mode"] == "raw"
    assert [(m.role, m.content) for m in captured["messages"]] == [
        ("user", "verbatim line")
    ]


# --------------------------------------------------------------- params


def test_params_reach_backend_in_raw_mode(tmp_path, monkeypatch) -> None:
    from runmal.generation import service as gen_service

    client = make_client(tmp_path, monkeypatch)
    captured: dict = {}
    backend = RecordingBackend(captured)
    monkeypatch.setattr(gen_service, "default_backend", lambda: backend)
    resp = client.post(
        "/api/v1/generate",
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "params": {"temperature": 0.3, "seed": 7, "max_tokens": 42},
        },
    )
    assert resp.status_code == 200, resp.text
    params = captured["params"]
    assert isinstance(params, SamplingParams)
    assert params.temperature == 0.3
    assert params.seed == 7
    assert params.max_output_tokens == 42


def test_no_params_means_unset_params_at_backend(tmp_path, monkeypatch) -> None:
    from runmal.generation import service as gen_service

    client = make_client(tmp_path, monkeypatch)
    captured: dict = {}
    monkeypatch.setattr(
        gen_service, "default_backend", lambda: RecordingBackend(captured)
    )
    resp = client.post(
        "/api/v1/generate",
        json={"messages": [{"role": "user", "content": "hi"}]},
    )
    assert resp.status_code == 200
    assert captured["params"] == SamplingParams()


def test_precedence_per_send_beats_preset_beats_defaults(
    tmp_path, monkeypatch
) -> None:
    client = make_client(tmp_path, monkeypatch)
    captured: dict = {}
    _patch_profile_backend(monkeypatch, captured)
    _, chat, _ = _world(client)
    preset = client.post(
        "/api/v1/presets",
        json={
            "name": "gate-preset",
            "params": {"temperature": 0.2, "max_tokens": 111, "top_p": 0.5},
        },
    ).json()
    assert client.post(
        f"/api/v1/chats/{chat['id']}/preset", json={"preset_id": preset["id"]}
    ).status_code == 200

    # Preset alone: its values form the base layer.
    resp = client.post("/api/v1/generate", json={"chat_id": chat["id"]})
    assert resp.status_code == 200, resp.text
    params = captured["params"]
    assert params.temperature == 0.2
    assert params.max_output_tokens == 111
    assert params.top_p == 0.5

    # Per-send overrides win per key; unmentioned keys keep the preset.
    resp = client.post(
        "/api/v1/generate",
        json={"chat_id": chat["id"], "params": {"temperature": 0.9}},
    )
    assert resp.status_code == 200, resp.text
    params = captured["params"]
    assert params.temperature == 0.9
    assert params.max_output_tokens == 111
    assert params.top_p == 0.5


async def test_resolve_sampling_params_layers(tmp_path, monkeypatch) -> None:
    """Resolver-level precedence, including the all-defaults floor."""
    from runmal.chats.service import create_chat, set_chat_preset
    from runmal.db.owners import get_or_create_owner
    from runmal.generation.router import resolve_sampling_params
    from runmal.presets.service import create_preset

    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "params.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    async with factory() as session:
        owner = await get_or_create_owner(session)
        chat = await create_chat(session, owner.id, "t")
        # Floor: no preset, no per-send -> everything unset.
        floor = await resolve_sampling_params(session, owner.id, chat=chat)
        assert floor == SamplingParams()
        preset = await create_preset(
            session, owner.id, "p", params={"temperature": 0.2, "seed": 3}
        )
        chat = await set_chat_preset(session, owner.id, chat.id, preset.id)
        based = await resolve_sampling_params(session, owner.id, chat=chat)
        assert based.temperature == 0.2 and based.seed == 3
        over = await resolve_sampling_params(
            session, owner.id, chat=chat, per_send={"temperature": 1.5}
        )
        assert over.temperature == 1.5 and over.seed == 3


def test_invalid_params_are_422_before_streaming(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    for bad in (
        {"temperature": -1},
        {"top_p": 2},
        {"top_k": "hot"},
        {"max_tokens": 0},
        {"seed": -3},
    ):
        resp = client.post(
            "/api/v1/generate",
            json={"messages": [{"role": "user", "content": "hi"}], "params": bad},
        )
        assert resp.status_code == 422, (bad, resp.text)


# -------------------------------------------------------------- persona


def test_persona_local_route_round_trip(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    keeper = client.post("/api/v1/characters", json={"card": CARD}).json()
    ferryman = client.post("/api/v1/characters", json={"card": OTHER_CARD}).json()
    chat = client.post(
        "/api/v1/chats",
        json={"title": "t", "character_id": keeper["id"], "greeting_mode": "quiet"},
    ).json()

    got = client.get(f"/api/v1/chats/{chat['id']}/persona")
    assert got.status_code == 200, got.text
    assert got.json()["persona"] == {
        "character_id": keeper["id"],
        "name": "Gate Keeper",
    }

    switched = client.post(
        f"/api/v1/chats/{chat['id']}/persona",
        json={"character_id": ferryman["id"]},
    )
    assert switched.status_code == 200, switched.text
    assert switched.json()["persona"] == {
        "character_id": ferryman["id"],
        "name": "Ferryman",
    }
    assert switched.json()["previous_character_id"] == keeper["id"]
    assert client.get(f"/api/v1/chats/{chat['id']}/persona").json()[
        "persona"
    ]["character_id"] == ferryman["id"]

    cleared = client.post(
        f"/api/v1/chats/{chat['id']}/persona", json={"character_id": None}
    )
    assert cleared.status_code == 200
    assert cleared.json()["persona"] is None


def test_persona_local_route_errors_and_auth(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    _, chat, _ = _world(client, pin_profile=False)
    assert client.post(
        f"/api/v1/chats/{chat['id']}/persona", json={"character_id": "ghost"}
    ).status_code == 422
    assert client.get("/api/v1/chats/ghost/persona").status_code == 404
    assert client.post(
        "/api/v1/chats/ghost/persona", json={"character_id": None}
    ).status_code == 404

    anon = make_client(tmp_path, monkeypatch, auth=False)
    assert anon.get(f"/api/v1/chats/{chat['id']}/persona").status_code == 401
    assert anon.post(
        f"/api/v1/chats/{chat['id']}/persona", json={"character_id": None}
    ).status_code == 401
    assert anon.get("/api/v1/user-name").status_code == 401
    assert anon.put("/api/v1/user-name", json={"user_name": "X"}).status_code == 401


# ------------------------------------------------------------ user name


def test_user_name_default_set_reset(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    got = client.get("/api/v1/user-name")
    assert got.status_code == 200
    assert got.json() == {"user_name": "User", "is_set": False}

    put = client.put("/api/v1/user-name", json={"user_name": "  Volmarr  "})
    assert put.status_code == 200, put.text
    assert put.json() == {"user_name": "Volmarr", "is_set": True}
    assert client.get("/api/v1/user-name").json()["user_name"] == "Volmarr"

    reset = client.put("/api/v1/user-name", json={"user_name": ""})
    assert reset.status_code == 200
    assert reset.json() == {"user_name": "User", "is_set": False}

    assert client.put(
        "/api/v1/user-name", json={"user_name": "x" * 201}
    ).status_code == 422
    assert client.put(
        "/api/v1/user-name", json={"user_name": "two\nlines"}
    ).status_code == 422


def test_user_name_reaches_composed_prompt(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    captured: dict = {}
    _patch_profile_backend(monkeypatch, captured)
    _, chat, _ = _world(client)
    assert client.put(
        "/api/v1/user-name", json={"user_name": "Volmarr"}
    ).status_code == 200
    resp = client.post("/api/v1/generate", json={"chat_id": chat["id"]})
    assert resp.status_code == 200, resp.text
    assert "You serve Volmarr." in captured["messages"][0].content
    assert "You serve Volmarr." in _sse_text(resp)
