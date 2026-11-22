"""R-13 acceptance (live): the voice & vision flows against the
real engine, in-process — device enumeration + role assignment
through the fixture provider the engine defaults to, backend
defaults round trip, a voice session's start/list/stop/detail/
latency roads, and vision end to end: describe via the in-tree
metadata provider, attach → thumbnail → describe-by-attachment
→ delete (with its derived description purged), and a watch
folder over a real directory (scan, rescan, patch, delete).
"""

import base64
import struct
import zlib
from collections.abc import Iterator
from pathlib import Path

import pytest

from runmal.desktop.client import DesktopSession, RunmalClient
from runmal.desktop.engine import EngineHandle, EngineState
from runmal.desktop.vision_logic import VisionFlow
from runmal.desktop.voice_logic import VoiceFlow


def make_png_bytes(width=6, height=4, color=(30, 200, 30)) -> bytes:
    """The tiny valid PNG the engine vision tests build
    (tests/test_p122_vision_history_custody.py's recipe)."""

    def chunk(ctype, data):
        raw = ctype + data
        return struct.pack(">I", len(data)) + raw + struct.pack(
            ">I", zlib.crc32(raw) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    row = b"\x00" + bytes(color) * width
    idat = zlib.compress(row * height)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", idat)
        + chunk(b"IEND", b"")
    )


PNG = make_png_bytes()
PNG_B64 = base64.b64encode(PNG).decode()


@pytest.fixture()
def engine(tmp_path: Path, monkeypatch) -> Iterator[EngineHandle]:
    monkeypatch.setenv("RUNMAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("no_proxy", "127.0.0.1,localhost")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1,localhost")
    handle = EngineHandle()
    assert handle.start(timeout=30.0).state is EngineState.RUNNING
    try:
        yield handle
    finally:
        handle.stop()


def make_client(engine: EngineHandle) -> RunmalClient:
    session = DesktopSession.from_local_credential(engine.base_url)
    return RunmalClient(session)


def test_voice_devices_roles_and_defaults(engine: EngineHandle) -> None:
    client = make_client(engine)
    flow = VoiceFlow(client)

    status = flow.status()
    assert status["state"]
    assert flow.device_provider() == "fixture"
    devices = flow.devices()
    assert devices, "the fixture provider must enumerate devices"
    mic = next(d for d in devices if d.direction == "input")

    result = flow.assign_role("user_mic", mic.device_id)
    assert result["status"] == "ok"
    roles = flow.roles()
    resolution = roles["resolution"]["user_mic"]
    assert resolution["status"] == "ok"
    assert resolution["device_id"] == mic.device_id
    assert roles["assignments"]["user_mic"]["device_id"] == mic.device_id

    backends = flow.backends()
    assert backends["tts"] and backends["stt"]
    assert all(b.key for b in backends["tts"] + backends["stt"])
    defaults = flow.defaults()
    assert defaults["tts_backend"] and defaults["stt_backend"]

    other = next(
        b.key for b in backends["tts"] if b.key != defaults["tts_backend"]
    )
    updated = flow.set_defaults(tts_backend=other)
    assert updated["tts_backend"] == other
    assert flow.defaults()["tts_backend"] == other
    restored = flow.set_defaults(tts_backend=defaults["tts_backend"])
    assert restored["tts_backend"] == defaults["tts_backend"]


def test_voice_session_lifecycle(engine: EngineHandle) -> None:
    client = make_client(engine)
    flow = VoiceFlow(client)
    chat = client.create_chat(title="Voice stage")

    started = flow.start_session(chat.id)
    assert started.session_id and started.state == "active"
    assert started.chat_id == chat.id

    listing = flow.sessions(chat.id)
    assert listing["active_session_id"] == started.session_id
    assert [s.session_id for s in listing["sessions"]] == [started.session_id]

    detail = flow.session_detail(started.session_id)
    assert detail["session_id"] == started.session_id
    assert detail["settings"]["tts_backend"]

    latency = flow.session_latency(started.session_id)
    assert latency["session_id"] == started.session_id
    assert latency["turn_count"] == 0

    live = flow.live(started.session_id)
    assert live["live"] is False

    stopped = flow.stop_session(started.session_id, note="wrapped")
    assert stopped.state == "stopped"
    assert stopped.stop_note == "wrapped"
    listing = flow.sessions(chat.id)
    assert listing["active_session_id"] is None


def test_vision_describe_attach_delete(engine: EngineHandle) -> None:
    client = make_client(engine)
    flow = VisionFlow(client)
    chat = client.create_chat(title="Vision stage")

    providers = flow.providers()
    assert providers["providers"]
    assert providers["semantic_caption_available"] is False

    described = client.describe_image(chat.id, image_b64=PNG_B64)
    assert described.id
    assert described.provider_id == "runmal.vision.metadata"
    assert described.image_format == "png"
    assert (described.image_width, described.image_height) == (6, 4)
    assert described.image_size == len(PNG)
    assert [d.id for d in flow.chat_descriptions(chat.id)] == [described.id]

    outcome = client.attach_image(chat.id, "gate.png", PNG_B64)
    attachment = outcome.attachment
    assert attachment.id and outcome.description is None
    assert [a.id for a in flow.attachments(chat.id)] == [attachment.id]

    thumbnail = flow.thumbnail(attachment.id)
    assert thumbnail.startswith(b"\x89PNG")

    derived = flow.describe_attachment(chat.id, attachment.id)
    assert derived.source_kind == "attachment"
    assert derived.source_ref == attachment.id

    removed = flow.delete_attachment(attachment.id)
    assert removed["deleted"] is True
    assert removed["descriptions_purged"] >= 1
    assert flow.attachments(chat.id) == []
    history = flow.history(chat_id=chat.id)
    remaining = [d.id for d in history["descriptions"]]
    assert derived.id not in remaining
    assert described.id in remaining
    assert flow.delete_description(described.id) is True
    assert flow.history(chat_id=chat.id)["total"] == 0


def test_vision_watch_folder_round_trip(
    engine: EngineHandle, tmp_path: Path
) -> None:
    client = make_client(engine)
    flow = VisionFlow(client)
    chat = client.create_chat(title="Watch stage")
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "gate.png").write_bytes(PNG)

    watch = flow.add_watch_folder(chat.id, str(inbox))
    assert watch.id and watch.enabled is True
    assert [w.id for w in flow.watch_folders(chat.id)] == [watch.id]

    report = flow.scan(watch.id)
    assert report["scanned"] >= 1
    assert len(report["ingested"]) == 1
    ingested = flow.ingested(watch.id)
    assert len(ingested) == 1
    assert ingested[0]["attachment_id"] == report["ingested"][0]
    assert [a.id for a in flow.attachments(chat.id)] == report["ingested"]

    rescan = flow.scan(watch.id)
    assert rescan["ingested"] == []

    updated = flow.update_watch_folder(watch.id, enabled=False)
    assert updated.enabled is False

    removed = flow.delete_watch_folder(watch.id)
    assert removed["deleted"] is True
    assert removed["ingested_records_removed"] >= 1
    assert flow.watch_folders(chat.id) == []
