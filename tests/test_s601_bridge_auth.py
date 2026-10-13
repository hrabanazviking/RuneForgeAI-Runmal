"""S601 acceptance: bridge auth — scoped/revocable per-bridge credentials.

Covers BRIDGE_PROTOCOL §2/§13 + INV-029: wrong-scope denial, revoked
denial, bridge/local credential separation, token shown exactly once,
only the hash persisted, and no secret material in any response.
"""

from __future__ import annotations

import hashlib
import sqlite3

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.bridge.auth import require_bridge_scope
from runmal.bridge.scopes import parse_scope, scope_allows, validate_scopes
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    app = create_app(create_session_factory(engine))

    @app.get(
        "/api/v1/bridge/probe/tts",
        dependencies=[Depends(require_bridge_scope("tts:request"))],
    )
    def probe_tts():
        return {"ok": True}

    @app.get(
        "/api/v1/bridge/probe/chats/{chat_id}",
        dependencies=[Depends(require_bridge_scope("chat:write", resource_param="chat_id"))],
    )
    def probe_write(chat_id: str):
        return {"ok": True, "chat_id": chat_id}

    client = TestClient(app)
    client.headers.update({"Authorization": f"Bearer {get_or_create_credential()}"})
    client.runmal_db_path = db_path  # type: ignore[attr-defined]
    return client


def _create_bridge(client, scopes, name="vrchat-home"):
    response = client.post("/api/v1/bridge/credentials", json={"name": name, "scopes": scopes})
    assert response.status_code == 201, response.text
    return response.json()


def _bridge_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --- scope grammar -------------------------------------------------------


def test_scope_grammar_parses_protocol_forms() -> None:
    assert str(parse_scope("chat:read:chat-1")) == "chat:read:chat-1"
    assert str(parse_scope("chat:write:*")) == "chat:write:*"
    assert str(parse_scope("persona:select:char-9")) == "persona:select:char-9"
    assert str(parse_scope("events:read:chat-1")) == "events:read:chat-1"
    assert str(parse_scope("tts:request")) == "tts:request"


@pytest.mark.parametrize(
    "bad",
    [
        "chat:read",  # resource required
        "tts:request:somewhere",  # resource forbidden
        "chat:delete:chat-1",  # unknown capability
        "admin",
        "",
        "chat:read:a:b",  # resource may not contain ':'
    ],
)
def test_scope_grammar_rejects_bad_forms(bad: str) -> None:
    with pytest.raises(ValueError):
        parse_scope(bad)


def test_scope_matching_is_exact_or_wildcard_only() -> None:
    granted = ["chat:read:chat-1", "persona:select:*", "tts:request"]
    assert scope_allows(granted, "chat:read", "chat-1")
    assert not scope_allows(granted, "chat:read", "chat-2")
    assert not scope_allows(granted, "chat:write", "chat-1")
    assert scope_allows(granted, "persona:select", "anyone")
    assert scope_allows(granted, "tts:request")
    assert not scope_allows(granted, "tts:request", "somewhere")
    assert scope_allows(["chat:read:*"], "chat:read", "chat-99")
    assert not scope_allows(["chat:read:*"], "events:read", "chat-99")
    assert validate_scopes([" chat:read:x ", "chat:read:x"]) == ["chat:read:x"]


# --- credential lifecycle --------------------------------------------------


def test_create_shows_token_once_and_stores_only_hash(app_client) -> None:
    created = _create_bridge(app_client, ["chat:read:chat-1", "tts:request"])
    token = created["token"]
    assert token.startswith("rmb_")
    assert created["scopes"] == ["chat:read:chat-1", "tts:request"]
    assert created["revoked_at"] is None

    conn = sqlite3.connect(app_client.runmal_db_path)
    try:
        rows = conn.execute("SELECT token_hash FROM bridge_credentials").fetchall()
    finally:
        conn.close()
    assert len(rows) == 1
    assert rows[0][0] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in rows[0][0]

    listed = app_client.get("/api/v1/bridge/credentials").json()
    assert len(listed) == 1
    assert "token" not in listed[0] and "token_hash" not in listed[0]
    assert token not in str(listed) and rows[0][0] not in str(listed)


def test_create_rejects_invalid_scopes(app_client) -> None:
    for scopes in (["chat:delete:x"], ["chat:read"], ["tts:request:lab"]):
        response = app_client.post(
            "/api/v1/bridge/credentials",
            json={"name": "bad", "scopes": scopes},
        )
        assert response.status_code == 422, (scopes, response.text)
    response = app_client.post("/api/v1/bridge/credentials", json={"name": "bad", "scopes": []})
    assert response.status_code == 422


def test_admin_routes_require_local_credential(app_client) -> None:
    response = app_client.get("/api/v1/bridge/credentials", headers=_bridge_headers("rmb_whatever"))
    assert response.status_code == 401
    response = app_client.get("/api/v1/bridge/credentials", headers={})
    # TestClient merges client-level headers; an explicit empty dict does
    # not clear them, so check with a bogus credential instead.
    response = app_client.get(
        "/api/v1/bridge/credentials",
        headers={"Authorization": "Bearer not-the-local-one"},
    )
    assert response.status_code == 401


# --- bridge authentication ---------------------------------------------------


def test_whoami_round_trip_and_last_used(app_client) -> None:
    created = _create_bridge(app_client, ["chat:read:chat-1"])
    assert created["last_used_at"] is None
    response = app_client.get("/api/v1/bridge/whoami", headers=_bridge_headers(created["token"]))
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "bridge_id": created["id"],
        "name": "vrchat-home",
        "scopes": ["chat:read:chat-1"],
    }
    assert created["token"] not in response.text
    listed = app_client.get("/api/v1/bridge/credentials").json()
    assert listed[0]["last_used_at"] is not None


def test_bridge_auth_rejects_missing_garbage_and_local_tokens(app_client) -> None:
    created = _create_bridge(app_client, ["tts:request"])
    local_token = get_or_create_credential()
    for headers in (
        {"Authorization": "Bearer rmb_garbage"},
        {"Authorization": f"Bearer {local_token}"},  # local != bridge
        {"Authorization": "Bearer "},
    ):
        response = app_client.get("/api/v1/bridge/whoami", headers=headers)
        assert response.status_code == 401, headers
    # ... and the bridge token is not a local credential either.
    response = app_client.get("/api/v1/chats", headers=_bridge_headers(created["token"]))
    assert response.status_code == 401


def test_wrong_scope_is_forbidden_not_unauthorized(app_client) -> None:
    reader = _create_bridge(app_client, ["chat:read:chat-1"])
    response = app_client.get("/api/v1/bridge/probe/tts", headers=_bridge_headers(reader["token"]))
    assert response.status_code == 403
    response = app_client.get(
        "/api/v1/bridge/probe/chats/chat-1",
        headers=_bridge_headers(reader["token"]),
    )
    assert response.status_code == 403

    writer = _create_bridge(app_client, ["chat:write:chat-1"])
    response = app_client.get(
        "/api/v1/bridge/probe/chats/chat-2",
        headers=_bridge_headers(writer["token"]),
    )
    assert response.status_code == 403  # right capability, wrong resource
    response = app_client.get(
        "/api/v1/bridge/probe/chats/chat-1",
        headers=_bridge_headers(writer["token"]),
    )
    assert response.status_code == 200

    star = _create_bridge(app_client, ["chat:write:*", "tts:request"])
    response = app_client.get(
        "/api/v1/bridge/probe/chats/anything",
        headers=_bridge_headers(star["token"]),
    )
    assert response.status_code == 200
    response = app_client.get("/api/v1/bridge/probe/tts", headers=_bridge_headers(star["token"]))
    assert response.status_code == 200


def test_revoked_token_authenticates_nothing(app_client) -> None:
    created = _create_bridge(app_client, ["tts:request"])
    headers = _bridge_headers(created["token"])
    assert app_client.get("/api/v1/bridge/whoami", headers=headers).status_code == 200
    revoked = app_client.post(f"/api/v1/bridge/credentials/{created['id']}/revoke")
    assert revoked.status_code == 200
    assert revoked.json()["revoked_at"] is not None
    assert app_client.get("/api/v1/bridge/whoami", headers=headers).status_code == 401
    assert app_client.get("/api/v1/bridge/probe/tts", headers=headers).status_code == 401
    # Revoking a stranger's credential id is a 404, not a leak.
    response = app_client.post("/api/v1/bridge/credentials/nope/revoke")
    assert response.status_code == 404
