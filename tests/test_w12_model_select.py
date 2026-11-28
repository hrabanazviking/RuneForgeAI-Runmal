"""W-12 acceptance: the Model menu and the house default profile.

Volmarr's bug (2026-11-28): in the webface chat there was NO way
to determine or set which model answers — a connection profile
could be pinned only from the Connections tab, and the engine had
no default-profile mechanism, so an unpinned chat fell through to
the offline fake. This slice cures both halves:

- engine: the owner's DEFAULT chat profile as data (m0043 +
  /backend-profiles/default), consulted by every generation
  resolution (generate router, bridge, continue/impersonate)
  between the chat's pin and the fake fall-through;
- webface: a Model dropdown in the chat view itself, rendered
  from the server-reported mind, pinning on change; new chats
  start pinned to the default; the guard's mind is default-aware.

Engine half runs the REAL app (TestClient) with a recording
backend patched at the profiles seam — the assertions are on
WHICH profile's backend was built, never on stub text. Webface
half runs the guard's pure resolution plus the real chat page.
"""
from __future__ import annotations

import json

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.backends.events import Done, TextDelta
from runmal.backends.fake import FakeChatBackend
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.webface import stub_guard
from runmal.webface import templates

CARD = {
    "name": "Gate Keeper",
    "description": "Keeper of the gate.",
    "system_prompt": "You are the Gate Keeper.",
}


class TaggedBackend(FakeChatBackend):
    """A backend whose reply names the profile it was built from."""

    def __init__(self, tag: str):
        super().__init__(chunks=(f"FROM[{tag}]",))
        self.tag = tag

    async def chat_stream(self, messages, params, cancel, *, structured=None):
        yield TextDelta(f"FROM[{self.tag}]")
        yield Done("stop", None)


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    token = get_or_create_credential()
    client.headers.update({"Authorization": f"Bearer {token}"})
    return client


def _patch_build(monkeypatch, built: list):
    from runmal.backends import profiles as profiles_mod

    async def fake_build(session, profile):
        built.append(profile.id)
        return TaggedBackend(profile.name)

    monkeypatch.setattr(profiles_mod, "build_chat_backend", fake_build)


def _profile(client, name: str) -> dict:
    resp = client.post(
        "/api/v1/backend-profiles",
        json={"name": name, "chat_backend": "ollama", "chat_model": f"{name}-model"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def _chat(client) -> dict:
    character = client.post("/api/v1/characters", json={"card": CARD}).json()
    chat = client.post(
        "/api/v1/chats",
        json={"title": "Gate chat", "character_id": character["id"],
              "greeting_mode": "quiet"},
    ).json()
    client.post(
        f"/api/v1/chats/{chat['id']}/messages",
        json={"role": "user", "content": "I seek passage."},
    )
    return chat


def _sse_text(resp) -> str:
    events = [
        json.loads(line.removeprefix("data: "))
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    return "".join(e["text"] for e in events if e["type"] == "token")


# ------------------------------------------------------- default CRUD


def test_default_profile_round_trip(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    profile = _profile(client, "hearth")
    unset = client.get("/api/v1/backend-profiles/default")
    assert unset.status_code == 200, unset.text
    assert unset.json() == {"profile_id": "", "profile": None}
    named = client.put(
        "/api/v1/backend-profiles/default", json={"profile_id": profile["id"]})
    assert named.status_code == 200, named.text
    assert named.json()["profile_id"] == profile["id"]
    assert named.json()["profile"]["name"] == "hearth"
    # ... and the naming persists across requests (the service commits).
    reread = client.get("/api/v1/backend-profiles/default")
    assert reread.json()["profile_id"] == profile["id"]
    # The literal "default" is never swallowed by the {profile_id} road.
    detail = client.get(f"/api/v1/backend-profiles/{profile['id']}")
    assert detail.status_code == 200, detail.text
    cleared = client.delete("/api/v1/backend-profiles/default")
    assert cleared.status_code == 200, cleared.text
    assert cleared.json() == {"profile_id": "", "profile": None}


def test_default_profile_unknown_id_is_404(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    resp = client.put(
        "/api/v1/backend-profiles/default", json={"profile_id": "ghost"})
    assert resp.status_code == 404, resp.text


def test_default_profile_dangling_after_delete_reads_unset(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    profile = _profile(client, "hearth")
    client.put("/api/v1/backend-profiles/default",
               json={"profile_id": profile["id"]})
    client.delete(f"/api/v1/backend-profiles/{profile['id']}")
    view = client.get("/api/v1/backend-profiles/default")
    assert view.status_code == 200, view.text
    assert view.json() == {"profile_id": "", "profile": None}


# ------------------------------------------------- generation fallback


def test_unpinned_chat_answers_through_default(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    built: list = []
    _patch_build(monkeypatch, built)
    profile = _profile(client, "hearth")
    client.put("/api/v1/backend-profiles/default",
               json={"profile_id": profile["id"]})
    chat = _chat(client)
    resp = client.post("/api/v1/generate", json={"chat_id": chat["id"]})
    assert resp.status_code == 200, resp.text
    assert built == [profile["id"]]
    assert _sse_text(resp) == "FROM[hearth]"


def test_pin_beats_default(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    built: list = []
    _patch_build(monkeypatch, built)
    default = _profile(client, "hearth")
    pinned = _profile(client, "anvil")
    client.put("/api/v1/backend-profiles/default",
               json={"profile_id": default["id"]})
    chat = _chat(client)
    resp = client.post(
        f"/api/v1/chats/{chat['id']}/backend-profile",
        json={"profile_id": pinned["id"]})
    assert resp.status_code == 200, resp.text
    resp = client.post("/api/v1/generate", json={"chat_id": chat["id"]})
    assert resp.status_code == 200, resp.text
    assert built == [pinned["id"]]
    assert _sse_text(resp) == "FROM[anvil]"


def test_no_default_no_pin_still_fake(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    chat = _chat(client)
    resp = client.post("/api/v1/generate", json={"chat_id": chat["id"]})
    assert resp.status_code == 200, resp.text
    assert resp.headers["x-backend-key"] == "fake"
    assert _sse_text(resp) == "Rúnmál hears you. This is a stub."


def test_raw_mode_never_uses_default(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    built: list = []
    _patch_build(monkeypatch, built)
    profile = _profile(client, "hearth")
    client.put("/api/v1/backend-profiles/default",
               json={"profile_id": profile["id"]})
    resp = client.post(
        "/api/v1/generate",
        json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 200, resp.text
    assert resp.headers["x-generation-mode"] == "raw"
    assert built == []
    assert _sse_text(resp) == "Rúnmál hears you. This is a stub."


# ------------------------------------------------------- webface guard


REAL = {"id": "p-real", "name": "House Gemma", "chat_backend": "openai",
        "chat_model": "gemma-26b", "config": {}}
OTHER = {"id": "p-other", "name": "House Phi", "chat_backend": "ollama",
         "chat_model": "phi3:mini", "config": {}}
DEMO = {"id": "p-demo", "name": "Demo mode", "chat_backend": "fake",
        "chat_model": "fake-1", "config": {}}


def test_guard_unpinned_with_real_default():
    mind = stub_guard.mind_for_chat(
        {"id": "c1", "backend_profile_id": None}, [REAL, OTHER], default=REAL)
    assert mind["state"] == "real"
    assert mind["via"] == "default"
    assert mind["words"] == "Answering: House Gemma · gemma-26b (house default)"
    assert mind["pinned_profile_id"] == ""
    assert mind["default_profile"]["id"] == "p-real"
    assert mind["no_mind"] is None


def test_guard_pin_still_beats_default():
    mind = stub_guard.mind_for_chat(
        {"id": "c1", "backend_profile_id": "p-other"}, [REAL, OTHER], default=REAL)
    assert mind["state"] == "real"
    assert mind["via"] == "pin"
    assert mind["words"] == "Answering: House Phi · phi3:mini"
    assert mind["pinned_profile_id"] == "p-other"


def test_guard_demo_default_is_labelled_demo():
    mind = stub_guard.mind_for_chat(
        {"id": "c1", "backend_profile_id": None}, [REAL, DEMO], default=DEMO)
    assert mind["state"] == "demo"
    assert mind["via"] == "default"
    assert mind["words"] == "Demo — not a real model (house default)"


def test_guard_no_default_still_no_mind():
    mind = stub_guard.mind_for_chat(
        {"id": "c1", "backend_profile_id": None}, [REAL, OTHER])
    assert mind["state"] == "none"
    assert mind["via"] == ""
    assert mind["default_profile"] is None
    assert [p["id"] for p in mind["profiles"]] == ["p-real", "p-other"]


def test_chat_page_carries_the_model_menu():
    user = {"username": "t", "account_type": "member"}
    page = templates.chat_page(user)
    assert 'id="model-select"' in page
    assert 'id="model-default"' in page
    assert 'id="model-note"' in page
    connections = templates.connections_page(user)
    assert "There is no default profile" not in connections
    assert "house default" in connections
