"""R-04 acceptance (client layer): typed clients, session roads,
error mapping, first-run detection — all WITHOUT Qt.

The client core must be importable and testable on hosts with no
PySide6 (the VM venv has none): these tests run against
``httpx.MockTransport`` simulating the engine's auth + route shapes,
plus a subprocess proof that importing the client pulls in no Qt.
"""

import json
import subprocess
import sys

import httpx
import pytest

from runmal.desktop.client import (
    ApiError,
    AuthError,
    BackendProfile,
    CharacterSummary,
    ChatSummary,
    DesktopSession,
    NotFoundError,
    RunmalClient,
    TransportError,
    detect_first_run,
    fetch_snapshot,
)

TOKEN = "R04-TEST-CREDENTIAL"
PROFILES = [
    {
        "id": "p1",
        "name": "hearth",
        "chat_backend": "fake",
        "chat_model": "fake-1",
        "embedding_backend": "",
        "embedding_model": "",
        "has_chat_secret": True,
        "has_embedding_secret": False,
        "config": {"base_url": "http://127.0.0.1:11434"},
        "chat_secret_ref": "secret:opaque",
    }
]
CHATS = [{"id": "c1", "title": "Gate chat", "character_id": "k1",
          "backend_profile_id": "p1", "preset_id": None, "message_count": 3}]
CHARACTERS = [{"id": "k1", "name": "Gate Keeper", "has_avatar": False}]


def make_handler(*, profiles=None, chats=None, characters=None,
                 fail_mode=None):
    profiles = PROFILES if profiles is None else profiles
    chats = CHATS if chats is None else chats
    characters = CHARACTERS if characters is None else characters

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if fail_mode == "transport":
            raise httpx.ConnectError("refused", request=request)
        if path == "/healthz":
            return httpx.Response(200, json={"status": "ok", "version": "0.1.0"})
        if path == "/launcher/bootstrap":
            assert request.url.params.get("nonce")
            return httpx.Response(
                303,
                headers={
                    "location": "/chat",
                    "set-cookie": "runmal_session=v1.session.sig; Path=/; HttpOnly",
                },
            )
        authed = (
            request.headers.get("authorization") == f"Bearer {TOKEN}"
            or "runmal_session=" in request.headers.get("cookie", "")
        )
        if not authed:
            return httpx.Response(401, json={"detail": "Missing or invalid local credential"})
        if fail_mode == "500":
            return httpx.Response(500, json={"detail": "boom"})
        if path == "/api/v1/status":
            return httpx.Response(200, json={"status": "ok", "auth": "local"})
        if path == "/api/v1/backend-profiles":
            return httpx.Response(200, json=profiles)
        if path == "/api/v1/backend-profiles/p1":
            return httpx.Response(200, json=profiles[0])
        if path == "/api/v1/backend-profiles/p1/health":
            return httpx.Response(200, json={
                "profile_id": "p1", "backend": "fake", "ok": True,
                "latency_ms": 1.5,
            })
        if path == "/api/v1/backend-profiles/p1/models":
            return httpx.Response(200, json={
                "profile_id": "p1", "backend": "fake",
                "models": [{"model_id": "fake-1", "backend_key": "fake"}],
            })
        if path == "/api/v1/chats":
            return httpx.Response(200, json=chats)
        if path == "/api/v1/characters":
            return httpx.Response(200, json=characters)
        return httpx.Response(404, json={"detail": "not found"})

    return handler


def make_client(handler, session=None) -> RunmalClient:
    session = session or DesktopSession("http://127.0.0.1:9", bearer_token=TOKEN)
    http = httpx.Client(
        base_url="http://127.0.0.1:9",
        transport=httpx.MockTransport(handler),
        trust_env=False,
    )
    return RunmalClient(session, http=http)


# ------------------------------------------------------------ Qt-freedom


def test_client_core_imports_without_qt() -> None:
    code = (
        "import sys\n"
        "import runmal.desktop.client as c\n"
        "import runmal.desktop.engine as e\n"
        "assert 'PySide6' not in sys.modules, 'client core pulled in Qt'\n"
        "assert hasattr(c, 'RunmalClient') and hasattr(e, 'EngineHandle')\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True
    )
    assert proc.returncode == 0, proc.stderr


# ---------------------------------------------------------------- session


def test_bearer_session_applies_header_and_hides_value() -> None:
    session = DesktopSession("http://127.0.0.1:9/", bearer_token=TOKEN)
    assert session.base_url == "http://127.0.0.1:9"
    assert session.authenticated is True
    assert TOKEN not in repr(session)
    client = make_client(make_handler(), session)
    assert TOKEN not in repr(client)
    # The header really is what authenticates the typed calls.
    assert client.health().ok is True
    assert client.api_status()["auth"] == "local"


def test_bootstrap_session_exchanges_nonce_for_cookie() -> None:
    http = httpx.Client(
        base_url="http://127.0.0.1:9",
        transport=httpx.MockTransport(make_handler()),
        trust_env=False,
    )
    session = DesktopSession.from_bootstrap("http://127.0.0.1:9", http=http)
    assert session.authenticated is True
    assert TOKEN not in repr(session)
    client = make_client(make_handler(), session)
    assert client.list_backend_profiles()[0].name == "hearth"


def test_local_credential_session_reads_owner_file(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    session = DesktopSession.from_local_credential("http://127.0.0.1:9")
    assert session.authenticated is True
    # The stored credential authenticates against the mock only if it
    # equals TOKEN — it does not, so the typed call must 401-map.
    client = make_client(make_handler(), session)
    with pytest.raises(AuthError):
        client.list_chats()


# ------------------------------------------------------------ typed parse


def test_typed_clients_parse_engine_shapes() -> None:
    client = make_client(make_handler())
    health = client.health()
    assert health.ok is True and health.version == "0.1.0"

    profile = client.list_backend_profiles()[0]
    assert isinstance(profile, BackendProfile)
    assert profile.label == "hearth · fake · fake-1"
    assert profile.has_chat_secret is True
    assert profile.config == {"base_url": "http://127.0.0.1:11434"}
    # Secret VALUES never exist in this layer — refs/booleans only.
    assert not hasattr(profile, "chat_secret")

    assert client.get_backend_profile("p1").id == "p1"
    assert client.profile_health("p1")["ok"] is True
    assert client.profile_models("p1")[0]["model_id"] == "fake-1"

    chat = client.list_chats()[0]
    assert isinstance(chat, ChatSummary)
    assert chat.message_count == 3 and chat.backend_profile_id == "p1"
    character = client.list_characters()[0]
    assert isinstance(character, CharacterSummary)
    assert character.name == "Gate Keeper"


def test_parsing_tolerates_shape_drift() -> None:
    weird = BackendProfile.from_dict({"id": "x", "config": "not-a-dict"})
    assert weird.config == {} and weird.name == ""
    assert ChatSummary.from_dict({"id": "y", "message_count": "many"}).message_count == 0
    assert CharacterSummary.from_dict({}).id == ""


# ------------------------------------------------------------ error mapping


def test_error_mapping() -> None:
    anon = DesktopSession("http://127.0.0.1:9")  # no auth material
    client = make_client(make_handler(), anon)
    with pytest.raises(AuthError) as caught:
        client.list_chats()
    assert caught.value.status_code == 401
    assert TOKEN not in str(caught.value)

    client = make_client(make_handler())
    with pytest.raises(NotFoundError):
        client.get_backend_profile("ghost")
    with pytest.raises(ApiError):
        make_client(make_handler(fail_mode="500")).list_chats()
    with pytest.raises(TransportError):
        make_client(make_handler(fail_mode="transport")).health()


# -------------------------------------------------------------- first run


def test_detect_first_run_pure_rule() -> None:
    assert detect_first_run([], []).is_first_run is True
    profile = BackendProfile.from_dict(PROFILES[0])
    character = CharacterSummary.from_dict(CHARACTERS[0])
    assert detect_first_run([profile], []).is_first_run is False
    assert detect_first_run([], [character]).is_first_run is False
    state = detect_first_run([profile], [character])
    assert state.profile_count == 1 and state.character_count == 1
    assert "Configured" in state.label
    assert "First run" in detect_first_run([], []).label


def test_first_run_and_snapshot_via_client() -> None:
    empty = make_client(make_handler(profiles=[], chats=[], characters=[]))
    state = empty.first_run_state()
    assert state.is_first_run is True

    full = make_client(make_handler())
    snapshot = fetch_snapshot(full)
    assert snapshot.health.ok is True
    assert snapshot.first_run.is_first_run is False
    assert [c.title for c in snapshot.chats] == ["Gate chat"]
    assert json.dumps(snapshot.first_run.label)  # label is plain text
