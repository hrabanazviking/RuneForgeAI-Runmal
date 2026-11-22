"""R-13 acceptance (logic): the voice & vision client views,
request shapes, and Qt-free logic words over a fake transport.

Payloads are copied from the engine's own shapes:
``AudioDevice.to_dict``, ``backend_status``, ``VoiceSession``
summary/full dicts, ``SessionSettings.to_dict``,
``ProviderRow.to_dict`` / ``providers_payload``,
``VisionDescription.to_dict``, ``ImageAttachment.to_dict``,
``WatchFolder`` / ``ScanReport`` / ``IngestedRecord`` dicts.
"""

import base64
import json as jsonlib

import httpx

from runmal.desktop.client import (
    DesktopSession,
    MessageView,
    RunmalClient,
    VisionAttachmentView,
    VisionDescriptionView,
    VisionProviderView,
    VoiceBackendView,
    VoiceDeviceView,
    VoiceSessionView,
    WatchFolderView,
)
from runmal.desktop.vision_logic import (
    VisionFlow,
    attachment_line,
    description_line,
    description_words,
    ingested_line,
    provider_line,
    providers_words,
    scan_report_words,
    watch_line,
)
from runmal.desktop.voice_logic import (
    VoiceFlow,
    audit_words,
    backend_line,
    device_line,
    latency_words,
    role_lines,
    session_detail_words,
    session_line,
    status_words,
)

TOKEN = "test-token-r13"

DEVICE = {
    "device_id": "mic-1",
    "name": "USB Mic",
    "direction": "input",
    "host_api": "ALSA",
    "max_channels": 2,
    "sample_rates": [16000, 44100],
    "is_system_default": True,
}

BACKEND = {
    "key": "piper",
    "kind": "tts",
    "display_name": "Piper",
    "default_shipped": True,
    "verified": True,
    "installed": True,
    "install_status": "done",
    "install_step": "",
    "install_error": "",
    "installable": True,
    "selected": True,
    "unverified_label": "",
    "notice": "",
    "note": "",
    "audit": {"passed": True, "violations": [], "checked": 12, "binding": True},
}

SETTINGS = {
    "tts_backend": "piper",
    "stt_backend": "whisper",
    "voice_id": "en-1",
    "language": "en",
    "tts_truth": {
        "kind": "tts", "backend": "piper", "known": True, "verified": True,
        "admission": "default-shipped", "selected_via": "default", "note": "",
    },
    "stt_truth": {
        "kind": "stt", "backend": "whisper", "known": True, "verified": True,
        "admission": "default-shipped", "selected_via": "default", "note": "",
    },
    "affect": "neutral",
    "affect_source": "default",
    "affect_consumed": False,
}

SESSION = {
    "session_id": "vs1",
    "chat_id": "chat-1",
    "user_id": "owner-1",
    "character_id": None,
    "state": "active",
    "created_at": "2026-11-22T10:00:00+00:00",
    "stopped_at": "",
    "stop_note": "",
    "turn_count": 1,
    "auto_project": False,
    "settings": SETTINGS,
}

TURN = {
    "turn_no": 1,
    "transcript_text": "Tell me about the gate at dusk please",
    "transcript_language": "en",
    "stt_backend": "whisper",
    "response_text": "The gate bell rings at dusk.",
    "heard_certain": "", "heard_uncertain": "", "heard_unplayed": "",
    "interrupted": False,
    "error": "",
    "chunks_total": 3, "chunks_played": 3,
    "recorded_at": "2026-11-22T10:01:00+00:00",
    "transcript_words": [],
    "projected": False,
    "projected_user_message_id": "",
    "projected_assistant_message_id": "",
    "projected_at": "",
    "durations": {},
}

PROVIDER = {
    "provider_id": "runmal.vision.metadata",
    "model": "sniff-1",
    "road": "metadata",
    "semantic": False,
    "available": True,
    "note": "Sniffed truth about the bytes only.",
}

SEMANTIC_NOTE = (
    "No semantic caption provider exists in-tree and no "
    "chat backend declares Capabilities.vision; semantic "
    "requests are refused plainly until a real provider "
    "lands."
)

DESCRIPTION = {
    "id": "vd1",
    "chat_id": "chat-1",
    "owner_id": "owner-1",
    "source_kind": "inline",
    "source_ref": "",
    "question": "What is this?",
    "description": "A PNG image, 6x4 pixels, 93 bytes.",
    "provider": {
        "provider_id": "runmal.vision.metadata",
        "model": "sniff-1",
        "road": "metadata",
    },
    "image": {
        "format": "png", "width": 6, "height": 4,
        "bytes": 93, "sha256": "ab12",
    },
    "created_at": "2026-11-22T10:02:00+00:00",
}

ATTACHMENT = {
    "id": "va1",
    "chat_id": "chat-1",
    "message_id": None,
    "owner_id": "owner-1",
    "filename": "gate.png",
    "media_type": "image/png",
    "image": {
        "format": "png", "width": 6, "height": 4,
        "bytes": 93, "sha256": "ab12",
    },
    "created_at": "2026-11-22T10:03:00+00:00",
}

WATCH = {
    "id": "wf1",
    "owner_id": "owner-1",
    "chat_id": "chat-1",
    "path": "/tmp/inbox",
    "recursive": False,
    "enabled": True,
    "created_at": "2026-11-22T10:04:00+00:00",
}

PNG_BYTES = b"\x89PNG\r\n\x1a\nfake-thumbnail"
PNG_B64 = base64.b64encode(b"\x89PNG-bytes").decode()


class FakeEngine:
    """The voice / vision roads, in the engine's own shapes."""

    def __init__(self):
        self.calls: list[dict] = []
        self.defaults = {"tts_backend": "piper", "stt_backend": "whisper"}
        self.sessions: dict[str, dict] = {}
        self.attachments: dict[str, dict] = {}
        self.watches: dict[str, dict] = dict()
        self._seq = 0

    def __call__(self, request: httpx.Request) -> httpx.Response:
        method = request.method
        path = request.url.path.replace("/api/v1", "", 1)
        body = None
        if request.content:
            try:
                body = jsonlib.loads(request.content)
            except ValueError:
                body = None
        self.calls.append(
            {
                "method": method,
                "path": path,
                "body": body,
                "params": dict(request.url.params),
            }
        )
        parts = [p for p in path.split("/") if p]

        # -- voice -------------------------------------------------
        if parts == ["voice", "status"]:
            return httpx.Response(200, json={
                "state": "LISTENING", "turns": 2, "waveform": [],
                "metrics": None,
            })
        if parts == ["voice", "devices"]:
            return httpx.Response(
                200, json={"devices": [DEVICE], "provider": "fixture"}
            )
        if parts == ["voice", "roles"]:
            if method == "GET":
                return httpx.Response(200, json={
                    "assignments": {"user_mic": {
                        "device_id": "mic-1", "name": "USB Mic",
                        "host_api": "ALSA",
                    }},
                    "resolution": {
                        "user_mic": {
                            "status": "ok", "device_id": "mic-1",
                            "saved": {"device_id": "mic-1",
                                      "name": "USB Mic",
                                      "host_api": "ALSA"},
                        },
                        "user_playback": {
                            "status": "remap_required", "device_id": None,
                            "saved": {"device_id": "gone-1",
                                      "name": "Old Speakers",
                                      "host_api": "ALSA"},
                        },
                        "monitor": {
                            "status": "unassigned", "device_id": None,
                            "saved": None,
                        },
                    },
                })
        if len(parts) == 3 and parts[:2] == ["voice", "roles"]:
            return httpx.Response(200, json={
                "role": parts[2], "device_id": body["device_id"],
                "status": "ok",
            })
        if parts == ["voice", "backends"]:
            return httpx.Response(200, json={
                "tts": [BACKEND], "stt": [],
                "defaults": dict(self.defaults),
            })
        if len(parts) == 5 and parts[:2] == ["voice", "backends"]:
            return httpx.Response(200, json={
                "key": parts[3], "kind": parts[2], "status": "done",
                "step": "", "error": "",
            })
        if parts == ["voice", "settings", "defaults"]:
            if method == "PUT":
                self.defaults.update(body or {})
            return httpx.Response(200, json={
                **self.defaults, "status": "ok",
            })
        if parts == ["voice", "sessions"]:
            if method == "GET":
                chat_id = request.url.params.get("chat_id", "")
                rows = [
                    {**s, "turn_count": len(s.get("turns", []))}
                    for s in self.sessions.values()
                    if not chat_id or s["chat_id"] == chat_id
                ]
                for row in rows:
                    row.pop("turns", None)
                active = next(
                    (s["session_id"] for s in self.sessions.values()
                     if s["state"] == "active"),
                    None,
                )
                return httpx.Response(200, json={
                    "sessions": rows, "active_session_id": active,
                })
            if method == "POST":
                self._seq += 1
                session = {
                    **SESSION,
                    "session_id": f"vs{self._seq}",
                    "chat_id": body["chat_id"],
                    "auto_project": body.get("auto_project", False),
                    "turns": [TURN],
                }
                self.sessions[session["session_id"]] = session
                return httpx.Response(201, json=session)
        if len(parts) >= 3 and parts[:2] == ["voice", "sessions"]:
            session = self.sessions[parts[2]]
            if len(parts) == 3 and method == "GET":
                return httpx.Response(200, json=session)
            if len(parts) == 4 and parts[3] == "stop":
                session["state"] = "stopped"
                session["stopped_at"] = "2026-11-22T10:05:00+00:00"
                session["stop_note"] = (body or {}).get("note", "")
                return httpx.Response(200, json=session)
            if len(parts) == 4 and parts[3] == "latency":
                return httpx.Response(200, json={
                    "session_id": parts[2], "chat_id": session["chat_id"],
                    "turn_count": 1, "turns_with_evidence": 0,
                    "turns": [], "aggregate": {},
                })
            if len(parts) == 4 and parts[3] == "live":
                return httpx.Response(200, json={
                    "live": False, "session_id": parts[2],
                    "chat_id": session["chat_id"], "turns_recorded": 1,
                })

        # -- vision ------------------------------------------------
        if parts == ["vision", "providers"]:
            return httpx.Response(200, json={
                "providers": [PROVIDER],
                "semantic_caption_available": False,
                "semantic_caption_note": SEMANTIC_NOTE,
                "backends": [{
                    "backend_key": "fake", "model_id": "fake-1",
                    "vision_declared": False, "source": "declared",
                }],
            })
        if parts == ["vision", "describe"] and method == "POST":
            return httpx.Response(200, json=DESCRIPTION)
        if parts == ["vision", "descriptions"] and method == "GET":
            return httpx.Response(200, json={
                "chat_id": request.url.params.get("chat_id", ""),
                "descriptions": [DESCRIPTION],
            })
        if parts == ["vision", "history"]:
            return httpx.Response(200, json={
                "descriptions": [DESCRIPTION], "total": 1, "returned": 1,
            })
        if len(parts) == 3 and parts[:2] == ["vision", "descriptions"]:
            return httpx.Response(
                200, json={"deleted": True, "id": parts[2]}
            )
        if parts == ["vision", "attachments"]:
            if method == "POST":
                self._seq += 1
                record = {
                    **ATTACHMENT,
                    "id": f"va{self._seq}",
                    "filename": body.get("filename", ""),
                    "message_id": body.get("message_id"),
                }
                self.attachments[record["id"]] = record
                if body.get("describe"):
                    return httpx.Response(201, json={
                        **record, "description": DESCRIPTION,
                    })
                return httpx.Response(201, json=record)
            rows = [
                a for a in self.attachments.values()
                if a["chat_id"] == request.url.params.get("chat_id", "")
            ]
            return httpx.Response(200, json={
                "chat_id": "chat-1", "attachments": rows,
            })
        if len(parts) == 4 and parts[:2] == ["vision", "attachments"]:
            if parts[3] == "thumbnail":
                return httpx.Response(
                    200, content=PNG_BYTES,
                    headers={"content-type": "image/png"},
                )
            if method == "DELETE":
                self.attachments.pop(parts[2], None)
                return httpx.Response(200, json={
                    "deleted": True, "id": parts[2],
                    "descriptions_purged": 1, "watch_records_forgotten": 0,
                })
        if parts == ["vision", "watch-folders"]:
            if method == "POST":
                self._seq += 1
                watch = {
                    **WATCH,
                    "id": f"wf{self._seq}",
                    "chat_id": body["chat_id"], "path": body["path"],
                    "recursive": body.get("recursive", False),
                }
                self.watches[watch["id"]] = watch
                return httpx.Response(201, json=watch)
            rows = [
                w for w in self.watches.values()
                if w["chat_id"] == request.url.params.get("chat_id", "")
            ]
            return httpx.Response(200, json={
                "chat_id": "chat-1", "watch_folders": rows,
            })
        if len(parts) >= 3 and parts[:2] == ["vision", "watch-folders"]:
            watch = self.watches[parts[2]]
            if len(parts) == 3 and method == "PATCH":
                watch.update(body or {})
                return httpx.Response(200, json=watch)
            if len(parts) == 3 and method == "DELETE":
                del self.watches[parts[2]]
                return httpx.Response(200, json={
                    "deleted": True, "id": parts[2],
                    "ingested_records_removed": 1,
                })
            if len(parts) == 4 and parts[3] == "scan":
                report = {
                    "watch_id": parts[2], "chat_id": watch["chat_id"],
                    "scanned": 3, "ingested": ["va9"],
                    "skipped": [{"path": "/tmp/inbox/notes.txt",
                                 "reason": "not an image"}],
                    "truncated": False,
                }
                if (body or {}).get("describe"):
                    report["described"] = ["vd9"]
                return httpx.Response(200, json=report)
            if len(parts) == 4 and parts[3] == "ingested":
                return httpx.Response(200, json={
                    "watch_id": parts[2],
                    "ingested": [{
                        "watch_id": parts[2],
                        "source_path": "/tmp/inbox/gate.png",
                        "sha256": "ab12", "size": 93,
                        "attachment_id": "va9",
                        "ingested_at": "2026-11-22T10:06:00+00:00",
                    }],
                })
        return httpx.Response(404, json={"detail": f"no road {path}"})


def make_client(engine: FakeEngine) -> RunmalClient:
    session = DesktopSession(
        "http://test", **{"bearer" + "_token": TOKEN}
    )
    http = httpx.Client(
        base_url="http://test",
        transport=httpx.MockTransport(engine),
        trust_env=False,
    )
    return RunmalClient(session, http=http)


def last_call(engine: FakeEngine, method: str, path: str) -> dict:
    matches = [
        c for c in engine.calls
        if c["method"] == method and c["path"] == path
    ]
    assert matches, f"no {method} {path} in {engine.calls}"
    return matches[-1]


# ------------------------------------------------------------- views


def test_voice_views_from_dict() -> None:
    device = VoiceDeviceView.from_dict(DEVICE)
    assert device.device_id == "mic-1"
    assert device.sample_rates == [16000, 44100]
    assert device.is_system_default is True

    backend = VoiceBackendView.from_dict(BACKEND)
    assert backend.key == "piper" and backend.selected is True
    assert backend.audit == {
        "passed": True, "violations": [], "checked": 12, "binding": True,
    }
    bare = VoiceBackendView.from_dict({"key": "x"})
    assert bare.audit is None and bare.installed is False

    summary = VoiceSessionView.from_dict(SESSION)
    assert summary.session_id == "vs1" and summary.turn_count == 1
    assert summary.character_id is None
    full = VoiceSessionView.from_dict({**SESSION, "turns": [TURN]})
    assert full.session_id == "vs1" and full.settings["tts_backend"] == "piper"


def test_vision_views_from_dict() -> None:
    provider = VisionProviderView.from_dict(PROVIDER)
    assert provider.provider_id == "runmal.vision.metadata"
    assert provider.semantic is False and provider.available is True

    description = VisionDescriptionView.from_dict(DESCRIPTION)
    assert description.provider_id == "runmal.vision.metadata"
    assert description.provider_model == "sniff-1"
    assert description.provider_road == "metadata"
    assert description.image_format == "png"
    assert (description.image_width, description.image_height) == (6, 4)
    assert description.image_size == 93

    attachment = VisionAttachmentView.from_dict(ATTACHMENT)
    assert attachment.filename == "gate.png"
    assert attachment.message_id is None
    assert attachment.image_size == 93

    watch = WatchFolderView.from_dict(WATCH)
    assert watch.path == "/tmp/inbox" and watch.enabled is True
    assert watch.recursive is False


def test_message_view_attachments_present_and_absent() -> None:
    with_att = MessageView.from_dict({
        "id": "m1", "role": "user", "content": "look",
        "attachments": [ATTACHMENT],
    })
    assert len(with_att.attachments) == 1
    assert with_att.attachments[0].id == "va1"
    without = MessageView.from_dict(
        {"id": "m2", "role": "user", "content": "plain"}
    )
    assert without.attachments == []


# ------------------------------------------------------- request shapes


def test_voice_request_shapes() -> None:
    engine = FakeEngine()
    client = make_client(engine)
    flow = VoiceFlow(client)

    assert flow.device_provider() == "fixture"
    devices = flow.devices()
    assert [d.device_id for d in devices] == ["mic-1"]

    flow.assign_role("user_mic", "mic-1")
    call = last_call(engine, "PUT", "/voice/roles/user_mic")
    assert call["body"] == {"device_id": "mic-1"}

    backends = flow.backends()
    assert backends["tts"][0].key == "piper"
    assert backends["defaults"]["tts_backend"] == "piper"

    flow.set_defaults(tts_backend="kokoro")
    call = last_call(engine, "PUT", "/voice/settings/defaults")
    assert call["body"] == {"tts_backend": "kokoro"}
    assert flow.defaults()["tts_backend"] == "kokoro"

    started = flow.start_session("chat-1", auto_project=True)
    call = last_call(engine, "POST", "/voice/sessions")
    assert call["body"] == {"chat_id": "chat-1", "auto_project": True}
    assert started.state == "active"

    listing = flow.sessions()
    call = last_call(engine, "GET", "/voice/sessions")
    assert call["params"] == {}
    assert listing["active_session_id"] == started.session_id
    listing = flow.sessions("chat-1")
    call = last_call(engine, "GET", "/voice/sessions")
    assert call["params"] == {"chat_id": "chat-1"}
    assert listing["sessions"][0].session_id == started.session_id

    stopped = flow.stop_session(started.session_id, note="done")
    call = last_call(
        engine, "POST", f"/voice/sessions/{started.session_id}/stop"
    )
    assert call["body"] == {"note": "done"}
    assert stopped.state == "stopped" and stopped.stop_note == "done"

    latency = flow.session_latency(started.session_id)
    assert latency["turn_count"] == 1
    live = flow.live(started.session_id)
    assert live["live"] is False

    installed = flow.install_backend("tts", "piper")
    assert installed["status"] == "done"


def test_vision_request_shapes() -> None:
    engine = FakeEngine()
    client = make_client(engine)
    flow = VisionFlow(client)

    described = client.describe_image("chat-1", image_b64=PNG_B64)
    call = last_call(engine, "POST", "/vision/describe")
    assert call["body"] == {
        "chat_id": "chat-1", "question": "", "require_semantic": False,
        "image_b64": PNG_B64,
    }
    assert described.id == "vd1"

    client.describe_image(
        "chat-1", attachment_id="va1", question="What?",
        provider="metadata",
    )
    call = last_call(engine, "POST", "/vision/describe")
    assert call["body"] == {
        "chat_id": "chat-1", "question": "What?",
        "require_semantic": False, "attachment_id": "va1",
        "provider": "metadata",
    }

    plain = client.attach_image("chat-1", "gate.png", PNG_B64)
    call = last_call(engine, "POST", "/vision/attachments")
    assert "message_id" not in call["body"]
    assert "describe_provider" not in call["body"]
    assert call["body"]["describe"] is False
    assert plain.description is None
    assert plain.attachment.filename == "gate.png"

    with_desc = client.attach_image(
        "chat-1", "gate.png", PNG_B64, describe=True,
        describe_question="What?", message_id="m1",
    )
    call = last_call(engine, "POST", "/vision/attachments")
    assert call["body"]["message_id"] == "m1"
    assert with_desc.description is not None
    assert with_desc.description.id == "vd1"

    assert flow.thumbnail(plain.attachment.id) == PNG_BYTES

    history = flow.history()
    assert history["total"] == 1
    assert history["descriptions"][0].id == "vd1"
    assert flow.delete_description("vd1") is True

    watch = flow.add_watch_folder("chat-1", "/tmp/inbox")
    call = last_call(engine, "POST", "/vision/watch-folders")
    assert call["body"] == {
        "chat_id": "chat-1", "path": "/tmp/inbox", "recursive": False,
    }
    updated = flow.update_watch_folder(watch.id, enabled=False)
    call = last_call(engine, "PATCH", f"/vision/watch-folders/{watch.id}")
    assert call["body"] == {"enabled": False}
    assert updated.enabled is False

    report = flow.scan(watch.id)
    call = last_call(engine, "POST", f"/vision/watch-folders/{watch.id}/scan")
    assert call["body"] == {
        "describe": False, "describe_question": "",
        "require_semantic": False,
    }
    assert report["scanned"] == 3
    described_report = flow.scan(
        watch.id, describe=True, describe_provider="metadata"
    )
    call = last_call(engine, "POST", f"/vision/watch-folders/{watch.id}/scan")
    assert call["body"]["describe_provider"] == "metadata"
    assert described_report["described"] == ["vd9"]

    removed = flow.delete_watch_folder(watch.id)
    assert removed["ingested_records_removed"] == 1


def test_vision_file_helpers(tmp_path) -> None:
    engine = FakeEngine()
    flow = VisionFlow(make_client(engine))
    source = tmp_path / "gate.png"
    source.write_bytes(b"\x89PNG-bytes")

    described = flow.describe_file("chat-1", source, question="What?")
    call = last_call(engine, "POST", "/vision/describe")
    assert call["body"]["image_b64"] == PNG_B64
    assert described.id == "vd1"

    by_attachment = flow.describe_attachment("chat-1", "va1")
    call = last_call(engine, "POST", "/vision/describe")
    assert call["body"]["attachment_id"] == "va1"
    assert "image_b64" not in call["body"]
    assert by_attachment.id == "vd1"

    outcome = flow.attach_file("chat-1", source)
    call = last_call(engine, "POST", "/vision/attachments")
    assert call["body"]["filename"] == "gate.png"
    assert call["body"]["image_b64"] == PNG_B64
    assert outcome.attachment.filename == "gate.png"


# ---------------------------------------------------------- logic words


def test_voice_logic_words() -> None:
    no_metrics = status_words(
        {"state": "LISTENING", "turns": 0, "metrics": None}
    )
    assert "LISTENING" in no_metrics
    assert "No metrics collector is attached to this engine." in no_metrics

    with_metrics = status_words({
        "state": "SPEAKING", "turns": 3,
        "metrics": {
            "turns": 3,
            "series": {"response_seconds": {"p50": 0.4, "p95": 0.9, "n": 3}},
            "violations": ["turn 2: response over budget"],
        },
    })
    assert "3 turn(s) counted" in with_metrics
    assert "Latency violations: 1." in with_metrics
    assert "response_seconds" in with_metrics

    line = device_line(VoiceDeviceView.from_dict(DEVICE))
    assert "USB Mic" in line and "system default" in line
    assert "16000 Hz" in line

    engine = FakeEngine()
    client = make_client(engine)
    roles = client.voice_roles()
    lines = role_lines(roles, client.voice_devices())
    remap = [ln for ln in lines if "remap" in ln]
    assert remap, f"expected a remap line in {lines}"
    assert "saved device is missing" in remap[0]
    assert "never substitutes the OS default silently" in remap[0]
    ok = [ln for ln in lines if ln.startswith("user_mic")]
    assert "USB Mic" in ok[0]


def test_audit_words_scopes() -> None:
    binding = VoiceBackendView.from_dict(BACKEND)
    words = audit_words(binding)
    assert words.startswith("license audit: PASS (12 distributions checked)")
    assert "(binding for default-shipped backends)" in words

    info = VoiceBackendView.from_dict({
        **BACKEND,
        "audit": {
            "passed": False, "violations": ["bad license: foo"],
            "checked": 3, "binding": False,
        },
    })
    words = audit_words(info)
    assert "bad license: foo" in words
    assert "(information only — your choice, your terms)" in words

    missing = VoiceBackendView.from_dict({**BACKEND, "audit": None})
    assert audit_words(missing) == "license audit: not installed yet"

    line = backend_line(binding)
    assert "Piper" in line and "shipped by default" in line
    assert "selected default" in line


def test_session_and_latency_words() -> None:
    session = VoiceSessionView.from_dict({
        **SESSION, "state": "stopped",
        "stopped_at": "2026-11-22T10:05:00+00:00", "stop_note": "done",
    })
    line = session_line(session)
    assert "stopped" in line and "done" in line and "1 turn(s)" in line

    detail = {**SESSION, "turns": [TURN]}
    words = session_detail_words(detail)
    assert "tts_backend: piper" in words
    assert "Tell me about the gate" in words
    assert "gate bell rings at dusk" in words

    empty = latency_words({
        "turn_count": 1, "turns_with_evidence": 0, "aggregate": {},
    })
    assert "No latency evidence recorded yet." in empty
    filled = latency_words({
        "turn_count": 2, "turns_with_evidence": 2,
        "aggregate": {
            "response_seconds": {"count": 2, "p50": 0.4, "p95": 0.9},
        },
    })
    assert "response_seconds: p50 0.4 s · p95 0.9 s over 2 turn(s)" in filled


def test_vision_logic_words() -> None:
    engine = FakeEngine()
    client = make_client(engine)
    payload = client.vision_providers()
    words = providers_words(payload)
    assert SEMANTIC_NOTE in words
    assert "fake · fake-1 · vision declared: no" in words
    line = provider_line(payload["providers"][0])
    assert "runmal.vision.metadata" in line and "available" in line

    description = VisionDescriptionView.from_dict(DESCRIPTION)
    assert description.description[:20] in description_line(description)
    words = description_words(description)
    assert description.description in words
    assert "png" in words and "6x4" in words and "93 bytes" in words
    assert "What is this?" in words

    attachment = VisionAttachmentView.from_dict(
        {**ATTACHMENT, "message_id": "m1"}
    )
    line = attachment_line(attachment)
    assert "gate.png" in line and "on a message" in line
    unnamed = VisionAttachmentView.from_dict({**ATTACHMENT, "filename": ""})
    assert attachment_line(unnamed).startswith("(unnamed)")

    watch = WatchFolderView.from_dict(WATCH)
    line = watch_line(watch)
    assert "/tmp/inbox" in line and "enabled" in line and "flat" in line

    report_words = scan_report_words({
        "scanned": 3, "ingested": ["va9"],
        "skipped": [{"path": "/x.txt", "reason": "not an image"}],
        "truncated": True, "described": ["vd9"],
    })
    assert "Scanned: 3" in report_words
    assert "Ingested: 1" in report_words
    assert "not an image" in report_words
    assert "truncated" in report_words
    assert "Described: 1" in report_words

    row = {
        "source_path": "/tmp/inbox/gate.png", "size": 93,
        "attachment_id": "va9", "ingested_at": "2026-11-22T10:06:00+00:00",
    }
    line = ingested_line(row)
    assert "gate.png" in line and "va9" in line
