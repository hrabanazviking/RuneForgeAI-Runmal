"""S604 acceptance: bridge TTS hook API.

BRIDGE_PROTOCOL §9: scoped TTS request + lifecycle events, audio
retrieval, cancellation, and bridge-reported playback — proven against
the deterministic fake backend substituted at the resolver seam (the
real registry path, including its failure honesty, is exercised by the
unavailable-backend case).
"""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from runmal.app import create_app
from runmal.auth import get_or_create_credential
from runmal.bridge import tts_hook
from runmal.db.base import create_db_engine, create_session_factory
from runmal.db.migrate import migrate_to_head
from runmal.voice.backends import BackendUnavailable
from runmal.voice.tts import SAMPLE_RATE, AudioChunk, FakeTTSBackend, TTSBackend


@pytest.fixture()
def app_client(tmp_path, monkeypatch):
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    db_path = tmp_path / "test.db"
    migrate_to_head(db_path)
    engine = create_db_engine(db_path)
    client = TestClient(create_app(create_session_factory(engine)))
    client.headers.update({"Authorization": f"Bearer {get_or_create_credential()}"})
    monkeypatch.setattr(
        tts_hook, "resolve_backend", lambda key: FakeTTSBackend(seconds_per_char=0.001)
    )
    return client


def _bridge(client, scopes, name="voice-bridge"):
    created = client.post(
        "/api/v1/bridge/credentials", json={"name": name, "scopes": scopes}
    ).json()
    return {"Authorization": f"Bearer {created['token']}"}


def _wait_status(client, headers, job_id, want, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        body = client.get(f"/api/v1/bridge/tts/{job_id}", headers=headers).json()
        if body["status"] == want:
            return body
        time.sleep(0.02)
    raise AssertionError(f"job never reached {want}: {body}")


def test_tts_round_trip_lifecycle_and_audio(app_client) -> None:
    headers = _bridge(app_client, ["tts:request"])
    created = app_client.post(
        "/api/v1/bridge/tts",
        headers=headers,
        json={"text": "The bridge is open.", "backend": "fake-tts"},
    )
    assert created.status_code == 202, created.text
    job = created.json()
    assert job["status"] in ("queued", "synthesizing", "ready")

    ready = _wait_status(app_client, headers, job["job_id"], "ready")
    kinds = [e["kind"] for e in ready["events"]]
    assert kinds == ["tts.requested", "tts.synthesizing", "tts.ready"]
    assert ready["audio_ready"] is True

    audio = app_client.get(f"/api/v1/bridge/tts/{job['job_id']}/audio", headers=headers)
    assert audio.status_code == 200
    assert audio.headers["content-type"] == "audio/wav"
    assert audio.content[:4] == b"RIFF" and len(audio.content) > 44

    played = app_client.post(
        f"/api/v1/bridge/tts/{job['job_id']}/playback",
        headers=headers,
        json={"event": "playback.completed"},
    )
    assert played.status_code == 200
    assert played.json()["events"][-1]["kind"] == "playback.completed"
    bogus = app_client.post(
        f"/api/v1/bridge/tts/{job['job_id']}/playback",
        headers=headers,
        json={"event": "playback.exploded"},
    )
    assert bogus.status_code == 422


def test_tts_scope_and_job_ownership(app_client) -> None:
    no_scope = _bridge(app_client, ["chat:read:x"])
    response = app_client.post("/api/v1/bridge/tts", headers=no_scope, json={"text": "hi"})
    assert response.status_code == 403

    owner = _bridge(app_client, ["tts:request"], name="owner")
    stranger = _bridge(app_client, ["tts:request"], name="stranger")
    job = app_client.post("/api/v1/bridge/tts", headers=owner, json={"text": "mine"}).json()
    assert (
        app_client.get(f"/api/v1/bridge/tts/{job['job_id']}", headers=stranger).status_code == 404
    )
    assert app_client.get("/api/v1/bridge/tts/nope", headers=owner).status_code == 404


class SlowBackend(TTSBackend):
    name = "slow-fake"

    def synthesize(self, text, voice, *, speaking_rate: float = 1.0):
        for index in range(200):
            time.sleep(0.05)
            yield AudioChunk(pcm=b"\x00\x00" * 160, text=text, index=index, sample_rate=SAMPLE_RATE)


def test_tts_cancellation(app_client, monkeypatch) -> None:
    monkeypatch.setattr(tts_hook, "resolve_backend", lambda key: SlowBackend())
    headers = _bridge(app_client, ["tts:request"])
    job = app_client.post(
        "/api/v1/bridge/tts", headers=headers, json={"text": "a very long saga"}
    ).json()
    _wait_status(app_client, headers, job["job_id"], "synthesizing")
    cancelled = app_client.post(
        f"/api/v1/bridge/tts/{job['job_id']}/cancel", headers=headers
    ).json()
    assert cancelled["cancelled"] is True
    final = _wait_status(app_client, headers, job["job_id"], "cancelled")
    assert final["events"][-1]["kind"] == "tts.cancelled"
    assert final["audio_ready"] is False
    again = app_client.post(f"/api/v1/bridge/tts/{job['job_id']}/cancel", headers=headers).json()
    assert again["cancelled"] is False


def test_tts_unavailable_backend_fails_honestly(app_client, monkeypatch) -> None:
    def unavailable(key):
        raise BackendUnavailable(f"backend '{key}' is not installed")

    monkeypatch.setattr(tts_hook, "resolve_backend", unavailable)
    headers = _bridge(app_client, ["tts:request"])
    job = app_client.post(
        "/api/v1/bridge/tts",
        headers=headers,
        json={"text": "speak", "backend": "cosyvoice"},
    ).json()
    assert job["status"] == "failed"
    assert "not installed" in job["error"]
    assert [e["kind"] for e in job["events"]] == ["tts.requested", "tts.failed"]
    audio = app_client.get(f"/api/v1/bridge/tts/{job['job_id']}/audio", headers=headers)
    assert audio.status_code == 409


def test_tts_persona_voice_resolution(app_client) -> None:
    character = app_client.post(
        "/api/v1/characters",
        json={"card": {"name": "Warden", "description": "Keeper."}},
    ).json()
    chat = app_client.post(
        "/api/v1/chats", json={"title": "t", "character_id": character["id"]}
    ).json()
    headers = _bridge(app_client, ["tts:request", f"chat:read:{chat['id']}"])
    job = app_client.post(
        "/api/v1/bridge/tts",
        headers=headers,
        json={"text": "Hail.", "chat_id": chat["id"]},
    ).json()
    # No S512 profile row -> the S512 default voice (CosyVoice zero-shot).
    assert job["backend"] == "cosyvoice"
    assert job["voice_id"] == "cosyvoice-zero-shot"
    _wait_status(app_client, headers, job["job_id"], "ready")

    # Without chat:read, the persona profile is NOT consulted.
    blind = _bridge(app_client, ["tts:request"], name="blind")
    job2 = app_client.post(
        "/api/v1/bridge/tts",
        headers=blind,
        json={"text": "Hail.", "chat_id": chat["id"]},
    ).json()
    assert job2["voice_id"] == ""
