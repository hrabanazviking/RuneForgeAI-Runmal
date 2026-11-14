"""R-02 acceptance: backend-profile API over backends/profiles.py (S306).

CRUD + write-only secret set/delete (INV-023: the canary secret value
must never appear in ANY response body) + health + model list, plus the
create -> secret -> health -> models -> generate round trip against the
fake backend, and the legacy S211 connections separation.

The canary discipline mirrors test_s306_profiles: assertions check the
raw response TEXT, not just parsed fields, so a leak through any extra
field, error detail, or header-shaped payload fails the test.
"""

import json

from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head

CHAT_CANARY = "R02-CHAT-SECRET-CANARY"
EMBED_CANARY = "R02-EMBED-SECRET-CANARY"


def make_client(tmp_path, monkeypatch, *, auth=True):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    # Hermetic probes: loopback backend probes must never be routed
    # through whatever proxy env the test host happens to carry (some
    # hosts export no_proxy forms httpx cannot parse at all).
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


def _create(client, **overrides):
    body = {"name": "hearth", "chat_backend": "fake", "chat_model": "fake-1"}
    body.update(overrides)
    resp = client.post("/api/v1/backend-profiles", json=body)
    assert resp.status_code == 201, resp.text
    return resp


# ---------------------------------------------------------------- CRUD


def test_crud_round_trip(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    created = _create(
        client,
        embedding_backend="fake",
        embedding_model="fake-embed",
        config={"base_url": "http://127.0.0.1:11434"},
    ).json()
    assert created["chat_backend"] == "fake"
    assert created["has_chat_secret"] is False
    assert created["has_embedding_secret"] is False
    assert created["config"] == {"base_url": "http://127.0.0.1:11434"}

    listed = client.get("/api/v1/backend-profiles")
    assert listed.status_code == 200
    assert [p["name"] for p in listed.json()] == ["hearth"]

    detail = client.get(f"/api/v1/backend-profiles/{created['id']}")
    assert detail.status_code == 200
    assert detail.json()["embedding_model"] == "fake-embed"

    patched = client.patch(
        f"/api/v1/backend-profiles/{created['id']}",
        json={"chat_model": "fake-2", "name": "hearth-2"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["chat_model"] == "fake-2"
    assert patched.json()["name"] == "hearth-2"
    # Untouched fields survive a partial patch.
    assert patched.json()["embedding_backend"] == "fake"

    assert client.delete(f"/api/v1/backend-profiles/{created['id']}").status_code == 200
    assert client.get(f"/api/v1/backend-profiles/{created['id']}").status_code == 404
    assert client.get("/api/v1/backend-profiles").json() == []


def test_create_validation_and_conflicts(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    assert client.post(
        "/api/v1/backend-profiles", json={"name": "  "}
    ).status_code == 422
    assert client.post(
        "/api/v1/backend-profiles",
        json={"name": "x", "chat_backend": "carrier-pigeon"},
    ).status_code == 422
    assert client.post(
        "/api/v1/backend-profiles",
        json={"name": "x", "embedding_backend": "carrier-pigeon"},
    ).status_code == 422
    _create(client)
    dup = client.post("/api/v1/backend-profiles", json={"name": "hearth"})
    assert dup.status_code == 409
    # Patch-side validation mirrors create-side.
    pid = client.get("/api/v1/backend-profiles").json()[0]["id"]
    assert client.patch(
        f"/api/v1/backend-profiles/{pid}", json={"chat_backend": "nope"}
    ).status_code == 422
    assert client.patch(
        "/api/v1/backend-profiles/ghost", json={"chat_model": "m"}
    ).status_code == 404
    assert client.delete("/api/v1/backend-profiles/ghost").status_code == 404


def test_requires_local_auth(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch, auth=False)
    assert client.get("/api/v1/backend-profiles").status_code == 401
    assert client.post(
        "/api/v1/backend-profiles", json={"name": "x"}
    ).status_code == 401


# ------------------------------------------------------------- secrets


def test_secret_set_replace_delete_never_echoed(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    pid = _create(client).json()["id"]

    set_chat = client.put(
        f"/api/v1/backend-profiles/{pid}/chat-secret",
        json={"value": CHAT_CANARY},
    )
    assert set_chat.status_code == 200, set_chat.text
    assert CHAT_CANARY not in set_chat.text
    assert set_chat.json()["has_chat_secret"] is True
    assert set_chat.json()["chat_secret_ref"].startswith("secret:")

    set_embed = client.put(
        f"/api/v1/backend-profiles/{pid}/embedding-secret",
        json={"value": EMBED_CANARY},
    )
    assert set_embed.status_code == 200, set_embed.text
    assert EMBED_CANARY not in set_embed.text
    assert set_embed.json()["has_embedding_secret"] is True

    # No read path echoes either value: list, detail, health, models.
    for url in (
        "/api/v1/backend-profiles",
        f"/api/v1/backend-profiles/{pid}",
        f"/api/v1/backend-profiles/{pid}/health",
        f"/api/v1/backend-profiles/{pid}/models",
    ):
        resp = client.get(url)
        assert resp.status_code == 200, (url, resp.text)
        assert CHAT_CANARY not in resp.text, url
        assert EMBED_CANARY not in resp.text, url

    # Replacement works and still never echoes the new value either.
    rotated = "R02-ROTATED-CANARY"
    resp = client.put(
        f"/api/v1/backend-profiles/{pid}/chat-secret", json={"value": rotated}
    )
    assert resp.status_code == 200
    assert rotated not in resp.text
    assert resp.json()["has_chat_secret"] is True

    cleared = client.delete(f"/api/v1/backend-profiles/{pid}/chat-secret")
    assert cleared.status_code == 200
    assert cleared.json()["has_chat_secret"] is False
    assert cleared.json()["chat_secret_ref"] == ""
    # Clearing is idempotent; the embedding secret is untouched.
    again = client.delete(f"/api/v1/backend-profiles/{pid}/chat-secret")
    assert again.status_code == 200
    assert again.json()["has_embedding_secret"] is True


def test_secret_inline_on_create_is_write_only(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    resp = _create(
        client,
        name="cloud",
        chat_backend="openrouter",
        chat_model="openai/gpt-4o-mini",
        chat_secret=CHAT_CANARY,
        embedding_secret=EMBED_CANARY,
    )
    assert CHAT_CANARY not in resp.text
    assert EMBED_CANARY not in resp.text
    body = resp.json()
    assert body["has_chat_secret"] is True
    assert body["has_embedding_secret"] is True
    detail = client.get(f"/api/v1/backend-profiles/{body['id']}")
    assert CHAT_CANARY not in detail.text
    assert EMBED_CANARY not in detail.text


def test_secret_errors(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    pid = _create(client).json()["id"]
    assert client.put(
        f"/api/v1/backend-profiles/{pid}/chat-secret", json={"value": ""}
    ).status_code == 422
    assert client.put(
        "/api/v1/backend-profiles/ghost/chat-secret", json={"value": "x"}
    ).status_code == 404
    assert client.delete(
        "/api/v1/backend-profiles/ghost/embedding-secret"
    ).status_code == 404


async def test_replaced_and_deleted_secrets_are_removed_from_store(
    tmp_path, monkeypatch
) -> None:
    """Service-level INV-023 hygiene: rotating or deleting a profile's
    secret deletes the old secret ROW (unless another profile shares
    the reference) — values do not linger server-side."""
    from runmal.backends.profiles import (
        clear_profile_secret,
        create_profile,
        delete_profile,
        resolve_secret,
        set_profile_secret,
    )
    from runmal.db.models import User

    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    factory = create_session_factory(create_db_engine(db_path))
    async with factory() as session:
        user = User(name="volmarr")
        session.add(user)
        await session.commit()
        user_id = user.id
    async with factory() as session:
        profile = await create_profile(session, user_id, name="p")
        profile = await set_profile_secret(
            session, user_id, profile.id, "chat", CHAT_CANARY
        )
        first_ref = profile.chat_secret_ref
        assert await resolve_secret(session, user_id, first_ref) == CHAT_CANARY
        profile = await set_profile_secret(
            session, user_id, profile.id, "chat", "rotated-value"
        )
        assert await resolve_secret(session, user_id, first_ref) is None
        second_ref = profile.chat_secret_ref
        profile = await clear_profile_secret(session, user_id, profile.id, "chat")
        assert profile.chat_secret_ref == ""
        assert await resolve_secret(session, user_id, second_ref) is None
        # Deleting the profile drops its remaining secrets too.
        profile = await set_profile_secret(
            session, user_id, profile.id, "embedding", EMBED_CANARY
        )
        embed_ref = profile.embedding_secret_ref
        assert await delete_profile(session, user_id, profile.id) is True
        assert await resolve_secret(session, user_id, embed_ref) is None


# ------------------------------------------------------- health/models


def test_health_and_models_fake_backend(tmp_path, monkeypatch) -> None:
    client = make_client(tmp_path, monkeypatch)
    pid = _create(client).json()["id"]
    health = client.get(f"/api/v1/backend-profiles/{pid}/health")
    assert health.status_code == 200, health.text
    body = health.json()
    assert body["ok"] is True
    assert body["profile_id"] == pid
    assert body["backend"] == "fake"
    assert body["latency_ms"] is not None

    models = client.get(f"/api/v1/backend-profiles/{pid}/models")
    assert models.status_code == 200, models.text
    body = models.json()
    assert body["profile_id"] == pid
    assert [m["model_id"] for m in body["models"]] == ["fake-1"]
    assert body["models"][0]["backend_key"] == "fake"

    assert client.get("/api/v1/backend-profiles/ghost/health").status_code == 404
    assert client.get("/api/v1/backend-profiles/ghost/models").status_code == 404


def test_health_unreachable_ollama_is_data_not_error(
    tmp_path, monkeypatch
) -> None:
    """An unreachable backend answers ok:false (never a 500) and the
    profile's config.base_url is honoured — port 9 on loopback refuses
    immediately, and this profile also carries a secret that must not
    leak through the failure path."""
    client = make_client(tmp_path, monkeypatch)
    pid = _create(
        client,
        name="dead-ollama",
        chat_backend="ollama",
        chat_model="llama3.1",
        config={"base_url": "http://127.0.0.1:9"},
        chat_secret=CHAT_CANARY,
    ).json()["id"]
    health = client.get(f"/api/v1/backend-profiles/{pid}/health")
    assert health.status_code == 200, health.text
    assert health.json()["ok"] is False
    assert CHAT_CANARY not in health.text
    models = client.get(f"/api/v1/backend-profiles/{pid}/models")
    assert models.status_code == 502, models.text
    assert CHAT_CANARY not in models.text


# ------------------------------------------------------ generate proof


def test_create_secret_health_generate_round_trip(tmp_path, monkeypatch) -> None:
    """The plan's R-02 round trip: create -> secret -> health -> generate,
    with the reply coming through the created profile (X-Backend-Key)
    and the secret never appearing in the streamed output."""
    client = make_client(tmp_path, monkeypatch)
    pid = _create(client).json()["id"]
    client.put(
        f"/api/v1/backend-profiles/{pid}/chat-secret",
        json={"value": CHAT_CANARY},
    )
    health = client.get(f"/api/v1/backend-profiles/{pid}/health").json()
    assert health["ok"] is True

    resp = client.post(
        "/api/v1/generate",
        json={
            "profile_id": pid,
            "messages": [{"role": "user", "content": "hello"}],
        },
    )
    assert resp.status_code == 200, resp.text
    assert resp.headers["x-backend-key"] == "fake"
    assert CHAT_CANARY not in resp.text
    events = [
        json.loads(line.removeprefix("data: "))
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    tokens = [e for e in events if e["type"] == "token"]
    # The profile's FakeChatBackend script — proof the stream really came
    # through the created profile (the no-profile stub appends text).
    assert "".join(t["text"] for t in tokens) == "Rúnmál hears you."


# ------------------------------------------------- legacy separation


def test_legacy_connections_stay_readable_and_separate(
    tmp_path, monkeypatch
) -> None:
    """Retirement note made executable: S211 connections data still
    reads back through its own routes, and the two profile systems do
    not bleed into each other (no migration theatre)."""
    client = make_client(tmp_path, monkeypatch)
    legacy = client.post(
        "/api/v1/connections", json={"name": "old", "backend": "fake"}
    )
    assert legacy.status_code == 201, legacy.text
    assert client.get("/api/v1/connections").status_code == 200
    assert client.get("/api/v1/backend-profiles").json() == []
    _create(client)
    names = [p["name"] for p in client.get("/api/v1/connections").json()]
    assert names == ["old"]
