"""W-08 compositions: Voice + Vision tabs (desktop R-13 parity).

All over EXISTING engine roads (no new engine routes):

VOICE - the desktop Voice dialog's surface (voice/router.py +
live_router.py + projection_router.py): GET /voice/status,
/voice/devices, /voice/roles (+ PUT /voice/roles/{role}),
GET /voice/backends (+ POST .../install), GET/PUT
/voice/settings/defaults, and the per-chat session roads
(POST/GET /voice/sessions, detail / latency / stop / turns,
POST .../project, and the live roads start / status / speak /
interrupt / stop). The words renderers below are the
desktop's own (desktop/voice_logic.py), ported to the raw
payloads the webface carries, wording unchanged.

HONEST GAPS - no engine road exists, so no control here
pretends otherwise:
- NO road returns synthesized audio bytes. Speaking runs
  through a live voice session and plays on the ENGINE
  HOST's playback device; there is no audio file for the
  browser to play or download, and this tab never fakes
  one. (The TTS citizens in plugins/tts.py are instance-
  only host wiring - no HTTP road calls them.)
- NO road transcribes an uploaded audio file. Speech-to-
  text runs inside a live session, from the engine host's
  own microphone capture. A transcript reaches a chat by
  recording the session's turns and projecting them (the
  engine's own roads) - both wired here.
- NO road reads or writes a character's stored voice
  profile; the profile resolves at session start (S512)
  and the resolved voice is what the session record shows.
- The live engine's device provider is its fixture provider
  until a deployment wires real audio hardware: the device
  names below are the engine's own, labelled as such.

VISION - the desktop Vision dialog's surface
(vision/router.py): GET /vision/providers (the provider
truth: the in-tree providers describe image FACTS; no
semantic caption provider exists and no chat backend
declares vision - the engine's note is carried verbatim),
POST /vision/attachments (base64, the engine's own attach
road; optional message binding + describe opt-in), the
attachment reads (list / content / thumbnail), POST
/vision/describe, the description reads, and the watch-
folder roads. The words renderers are the desktop's own
(desktop/vision_logic.py), ported the same way.

Attachments are CHAT records, not prompt content: no
generation road reads them, so sending a message with an
image attached sends the words through the ordinary
guarded send road and binds the image to that message -
the pinned mind does not see the picture, and the tab
says so in plain words rather than implying otherwise.
"""
from __future__ import annotations

import base64
from typing import Any

# ------------------------------------------------------------ notes

SYNTH_ROAD_NOTE = (
    "No engine road returns synthesized audio: speaking runs "
    "through a live voice session and plays on the engine "
    "host's playback device. There is no audio file to play "
    "or download in the browser, and this page does not "
    "pretend otherwise."
)

TRANSCRIBE_ROAD_NOTE = (
    "No engine road transcribes an uploaded audio file: "
    "speech-to-text runs inside a live voice session, from "
    "the engine host's own microphone. What reaches a chat "
    "is a session's recorded turns, projected by the "
    "engine's own road - both are wired below."
)

MIC_SECURE_NOTE = (
    "Your browser will not grant the microphone over this "
    "connection: microphone access needs a secure context "
    "(HTTPS or localhost), and this face is served over "
    "plain HTTP on the tailnet. Recording a clip elsewhere "
    "and uploading it does the same job the browser allows - "
    "and the engine's own transcription limits above still "
    "apply."
)

CHARACTER_VOICE_NOTE = (
    "A character's voice is chosen on the character (its "
    "stored voice profile) and resolves when a voice session "
    "starts - the engine has no road to read or change that "
    "profile from here, so this page shows the resolved "
    "voice on each session and offers no editor for it."
)

VISION_SEND_NOTE = (
    "Attachments are chat records, not prompt content: no "
    "chat backend declares vision, so the pinned mind does "
    "not see an attached picture. Sending with an image "
    "sends your words through the ordinary send road and "
    "binds the image to that message - it is stored, shown "
    "and describable as image facts, never silently fed to "
    "a mind that cannot see it."
)

FIXTURE_PROVIDER_NOTE = (
    "This engine's device provider is its fixture provider: "
    "the devices listed are the engine's fixture devices, "
    "not audio hardware on the engine host. A deployment "
    "wires real hardware by giving the engine a sound-device "
    "provider (Connections / the engine's own setup)."
)

# ------------------------------------------------------- voice words
# Ported from runmal.desktop.voice_logic (R-13), unchanged in
# wording; inputs are the raw engine payloads.

_ROLE_STATUS_WORDS = {
    "ok": "ready",
    "unassigned": "not assigned",
    "remap_required": "saved device missing — remap required",
}


def status_words(status: dict) -> str:
    status = status if isinstance(status, dict) else {}
    lines: list[str] = []
    state = status.get("state")
    if state:
        lines.append(f"State: {state}")
    turns = status.get("turns")
    if isinstance(turns, int):
        lines.append(f"Turns this session: {turns}")
    metrics = status.get("metrics")
    if not isinstance(metrics, dict):
        lines.append("No metrics collector is attached to this engine.")
        return "\n".join(lines)
    counted = metrics.get("turns")
    if isinstance(counted, int):
        lines.append(f"Metrics: {counted} turn(s) counted.")
    violations = metrics.get("violations")
    if isinstance(violations, list):
        lines.append(f"Latency violations: {len(violations)}.")
        lines.extend(f"- {v}" for v in violations if isinstance(v, str))
    series = metrics.get("series")
    if isinstance(series, dict) and series:
        lines.append("Measured stages: " + ", ".join(sorted(series)))
    return "\n".join(lines)


def device_line(device: dict) -> str:
    device = device if isinstance(device, dict) else {}
    bits = [str(device.get("name") or device.get("device_id") or "")]
    if device.get("direction"):
        bits.append(str(device["direction"]))
    if device.get("host_api"):
        bits.append(str(device["host_api"]))
    bits.append(f"{device.get('max_channels', 0)} channel(s)")
    if device.get("sample_rates"):
        rates = ", ".join(f"{r} Hz" for r in device["sample_rates"])
        bits.append(f"sample rates: {rates}")
    if device.get("is_system_default"):
        bits.append("system default")
    return " · ".join(bits)


def role_lines(roles: dict, devices: list) -> list[str]:
    roles = roles if isinstance(roles, dict) else {}
    by_id = {str(d.get("device_id")): d for d in devices
             if isinstance(d, dict)}
    resolution = roles.get("resolution")
    if not isinstance(resolution, dict):
        return []
    lines: list[str] = []
    for role, entry in resolution.items():
        if not isinstance(entry, dict):
            continue
        status = str(entry.get("status", "") or "")
        words = _ROLE_STATUS_WORDS.get(status, status or "unknown")
        line = f"{role} · {words}"
        device_id = entry.get("device_id")
        if status == "ok" and device_id:
            device = by_id.get(str(device_id))
            name = (str(device.get("name")) if device is not None
                    else str(device_id))
            if name:
                line += f" · {name}"
        if status == "remap_required":
            line += (
                " — the saved device is missing; pick a present device."
                " Rúnmál never substitutes the OS default silently.")
        lines.append(line)
    return lines


def backend_line(backend: dict) -> str:
    backend = backend if isinstance(backend, dict) else {}
    bits = [str(backend.get("display_name") or backend.get("key") or "")]
    bits.append("shipped by default" if backend.get("default_shipped")
                else "user-installed")
    bits.append("installed: yes" if backend.get("installed")
                else "installed: no")
    if backend.get("selected"):
        bits.append("selected default")
    status = backend.get("install_status")
    if status and status not in ("not_started", "done"):
        line = f"install: {status}"
        if backend.get("install_step"):
            line += f" ({backend['install_step']})"
        if backend.get("install_error"):
            line += f" — {backend['install_error']}"
        bits.append(line)
    if backend.get("unverified_label"):
        bits.append(str(backend["unverified_label"]))
    return " · ".join(bits)


def audit_words(backend: dict) -> str:
    backend = backend if isinstance(backend, dict) else {}
    audit = backend.get("audit")
    if not isinstance(audit, dict):
        return "license audit: not installed yet"
    if audit.get("passed"):
        checked = audit.get("checked")
        words = (f"license audit: PASS ({checked} distributions checked)"
                 if isinstance(checked, int) else "license audit: PASS")
    else:
        violations = audit.get("violations")
        joined = ("; ".join(str(v) for v in violations)
                  if isinstance(violations, list) and violations
                  else "failed")
        words = f"license audit: {joined}"
    if audit.get("binding"):
        words += " (binding for default-shipped backends)"
    else:
        words += " (information only — your choice, your terms)"
    return words


def session_line(session: dict) -> str:
    session = session if isinstance(session, dict) else {}
    bits = [str(session.get("state") or "session")]
    if session.get("chat_id"):
        bits.append(f"chat {session['chat_id']}")
    bits.append(f"{session.get('turn_count', 0)} turn(s)")
    if session.get("created_at"):
        bits.append(f"started {session['created_at']}")
    if session.get("stopped_at"):
        stopped = f"stopped {session['stopped_at']}"
        if session.get("stop_note"):
            stopped += f" — {session['stop_note']}"
        bits.append(stopped)
    return " · ".join(bits)


def _excerpt(text: str, limit: int = 80) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def session_detail_words(detail: dict) -> str:
    if not detail:
        return "No voice session selected."
    lines: list[str] = []
    state = detail.get("state")
    if state:
        lines.append(f"State: {state}")
    settings = detail.get("settings")
    if isinstance(settings, dict) and settings:
        lines.append("")
        lines.append("Settings:")
        for key in sorted(settings):
            value = settings[key]
            if isinstance(value, dict):
                inner = ", ".join(
                    f"{k}={v}" for k, v in sorted(value.items()))
                lines.append(f"- {key}: {inner}")
            else:
                lines.append(f"- {key}: {value}")
    turns = detail.get("turns")
    if isinstance(turns, list) and turns:
        lines.append("")
        lines.append("Turns:")
        for turn in turns:
            if not isinstance(turn, dict):
                continue
            number = turn.get("turn_no", "?")
            bits = [f"Turn {number}"]
            transcript = str(turn.get("transcript_text", "") or "")
            if transcript:
                bits.append(f"heard: {_excerpt(transcript)}")
            response = str(turn.get("response_text", "") or "")
            if response:
                bits.append(f"said: {_excerpt(response)}")
            if turn.get("interrupted"):
                bits.append("interrupted")
            error = turn.get("error")
            if error:
                bits.append(f"error: {error}")
            lines.append("- " + " · ".join(bits))
    return "\n".join(lines)


def latency_words(payload: dict) -> str:
    if not payload:
        return "No latency record."
    lines: list[str] = []
    turn_count = payload.get("turn_count")
    if isinstance(turn_count, int):
        lines.append(f"Turns: {turn_count}")
    with_evidence = payload.get("turns_with_evidence")
    if isinstance(with_evidence, int):
        lines.append(f"Turns with latency evidence: {with_evidence}")
    aggregate = payload.get("aggregate")
    if isinstance(aggregate, dict) and aggregate:
        for key in sorted(aggregate):
            entry = aggregate[key]
            if not isinstance(entry, dict):
                continue
            count = entry.get("count")
            count = count if isinstance(count, int) else 0
            lines.append(
                f"{key}: p50 {entry.get('p50')} s · p95 {entry.get('p95')} s"
                f" over {count} turn(s)")
    else:
        lines.append("No latency evidence recorded yet.")
    return "\n".join(lines)

# ------------------------------------------------------ voice flows


def backend_state(backends: dict) -> dict:
    """What can actually be spoken / heard on this engine, in
    words: the SELECTED defaults and whether each is installed.
    Nothing is ready because a registry lists it - only an
    installed selected backend can run."""
    backends = backends if isinstance(backends, dict) else {}
    out: dict[str, Any] = {"words": []}
    for kind, verb, noun in (("tts", "spoken", "text-to-speech"),
                             ("stt", "transcribed", "speech-to-text")):
        rows = backends.get(kind) or []
        selected = next((r for r in rows if isinstance(r, dict)
                         and r.get("selected")), None)
        key = str((selected or {}).get("key") or "")
        name = str((selected or {}).get("display_name") or key)
        installed = bool(selected and selected.get("installed"))
        out[f"{kind}_selected"] = key
        out[f"{kind}_installed"] = installed
        if selected is None:
            out["words"].append(
                f"No {noun} backend is selected on this engine, so "
                f"nothing can be {verb} yet.")
        elif installed:
            out["words"].append(
                f"{name} is the selected {noun} backend and is "
                f"installed, so it can be {verb} through a live "
                "voice session.")
        else:
            out["words"].append(
                f"The selected {noun} backend, {name}, is not "
                f"installed on this engine, so nothing can be "
                f"{verb} yet. Install it from the backends list "
                "(the engine's own one-button install), or choose "
                "an installed backend as the default.")
    out["synthesis_ready"] = bool(out.get("tts_installed"))
    out["transcription_ready"] = bool(out.get("stt_installed"))
    return out


def voice_overview(engine) -> dict:
    status = engine.request("GET", "/api/v1/voice/status")
    status = status if isinstance(status, dict) else {}
    devices_payload = engine.request("GET", "/api/v1/voice/devices")
    devices_payload = devices_payload if isinstance(
        devices_payload, dict) else {}
    devices = [d for d in devices_payload.get("devices") or []
               if isinstance(d, dict)]
    provider = str(devices_payload.get("provider") or "")
    roles = engine.request("GET", "/api/v1/voice/roles")
    roles = roles if isinstance(roles, dict) else {}
    backends = engine.request("GET", "/api/v1/voice/backends")
    backends = backends if isinstance(backends, dict) else {}
    defaults = engine.request("GET", "/api/v1/voice/settings/defaults")
    defaults = defaults if isinstance(defaults, dict) else {}
    backend_rows: dict[str, list] = {}
    line_rows: dict[str, list] = {}
    audit: dict[str, str] = {}
    for kind in ("tts", "stt"):
        rows = [r for r in backends.get(kind) or [] if isinstance(r, dict)]
        backend_rows[kind] = rows
        line_rows[kind] = [backend_line(r) for r in rows]
        for row in rows:
            audit[str(row.get("key") or "")] = audit_words(row)
    return {
        "status": status, "status_words": status_words(status),
        "devices": devices,
        "device_lines": [device_line(d) for d in devices],
        "provider": provider,
        "provider_note": (FIXTURE_PROVIDER_NOTE
                          if provider == "fixture" else ""),
        "roles": roles, "role_lines": role_lines(roles, devices),
        "backends": backend_rows, "backend_lines": line_rows,
        "audit": audit, "defaults": defaults,
        "state": backend_state(backends),
        "notes": {
            "synthesis": SYNTH_ROAD_NOTE,
            "transcription": TRANSCRIBE_ROAD_NOTE,
            "microphone": MIC_SECURE_NOTE,
            "character_voice": CHARACTER_VOICE_NOTE,
        },
    }


def set_role(engine, role: str, device_id: str) -> dict:
    payload = engine.request(
        "PUT", f"/api/v1/voice/roles/{role}",
        json_body={"device_id": str(device_id or "")})
    return payload if isinstance(payload, dict) else {}


def install_backend(engine, kind: str, key: str) -> dict:
    payload = engine.request(
        "POST", f"/api/v1/voice/backends/{kind}/{key}/install",
        json_body={})
    return payload if isinstance(payload, dict) else {}


def set_defaults(engine, payload: dict) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    body: dict[str, Any] = {}
    if payload.get("tts_backend"):
        body["tts_backend"] = str(payload["tts_backend"])
    if payload.get("stt_backend"):
        body["stt_backend"] = str(payload["stt_backend"])
    result = engine.request(
        "PUT", "/api/v1/voice/settings/defaults", json_body=body)
    return result if isinstance(result, dict) else {}


def list_sessions(engine, chat_id: str = "") -> dict:
    params = {"chat_id": chat_id} if chat_id else None
    payload = engine.request("GET", "/api/v1/voice/sessions",
                             params=params)
    payload = payload if isinstance(payload, dict) else {}
    rows = [r for r in payload.get("sessions") or []
            if isinstance(r, dict)]
    return {"sessions": rows, "lines": [session_line(r) for r in rows],
            "active_session_id": payload.get("active_session_id")}


def start_session(engine, chat_id: str, auto_project: bool = False) -> dict:
    payload = engine.request(
        "POST", "/api/v1/voice/sessions",
        json_body={"chat_id": str(chat_id or ""),
                   "auto_project": bool(auto_project)})
    payload = payload if isinstance(payload, dict) else {}
    return {"session": payload, "words": session_detail_words(payload)}


def session_detail(engine, session_id: str) -> dict:
    payload = engine.request(
        "GET", f"/api/v1/voice/sessions/{session_id}")
    payload = payload if isinstance(payload, dict) else {}
    return {"session": payload, "words": session_detail_words(payload)}


def session_latency(engine, session_id: str) -> dict:
    payload = engine.request(
        "GET", f"/api/v1/voice/sessions/{session_id}/latency")
    payload = payload if isinstance(payload, dict) else {}
    return {"latency": payload, "words": latency_words(payload)}


def stop_session(engine, session_id: str, note: str = "") -> dict:
    payload = engine.request(
        "POST", f"/api/v1/voice/sessions/{session_id}/stop",
        json_body={"note": str(note or "")})
    payload = payload if isinstance(payload, dict) else {}
    return {"session": payload, "words": session_detail_words(payload)}


def record_turn(engine, session_id: str, payload: dict) -> dict:
    """Record a turn on a session: the transcript the user
    holds, plus the reply text when there is one. This is the
    engine's record road - it transcribes nothing itself."""
    payload = payload if isinstance(payload, dict) else {}
    body: dict[str, Any] = {
        "transcript_text": str(payload.get("transcript_text") or ""),
    }
    if payload.get("response_text"):
        body["response_text"] = str(payload["response_text"])
    if payload.get("transcript_language"):
        body["transcript_language"] = str(payload["transcript_language"])
    result = engine.request(
        "POST", f"/api/v1/voice/sessions/{session_id}/turns",
        json_body=body)
    return result if isinstance(result, dict) else {}


def project_session(engine, session_id: str) -> dict:
    payload = engine.request(
        "POST", f"/api/v1/voice/sessions/{session_id}/project",
        json_body={})
    return payload if isinstance(payload, dict) else {}


def live_status(engine, session_id: str) -> dict:
    payload = engine.request(
        "GET", f"/api/v1/voice/sessions/{session_id}/live")
    return payload if isinstance(payload, dict) else {}


def live_start(engine, session_id: str) -> dict:
    payload = engine.request(
        "POST", f"/api/v1/voice/sessions/{session_id}/live/start",
        json_body={})
    return payload if isinstance(payload, dict) else {}


def live_speak(engine, session_id: str, text: str) -> dict:
    payload = engine.request(
        "POST", f"/api/v1/voice/sessions/{session_id}/live/speak",
        json_body={"text": str(text or "")})
    return payload if isinstance(payload, dict) else {}


def live_interrupt(engine, session_id: str) -> dict:
    payload = engine.request(
        "POST", f"/api/v1/voice/sessions/{session_id}/live/interrupt",
        json_body={})
    return payload if isinstance(payload, dict) else {}


def live_stop(engine, session_id: str) -> dict:
    payload = engine.request(
        "POST", f"/api/v1/voice/sessions/{session_id}/live/stop",
        json_body={})
    return payload if isinstance(payload, dict) else {}


def transcribe_attempt(payload: dict) -> dict:
    """The upload-transcribe attempt, answered honestly: the
    engine has no such road (see TRANSCRIBE_ROAD_NOTE), so the
    webface refuses in plain words instead of accepting an
    upload it cannot honour. Nothing is stored."""
    return {"error": TRANSCRIBE_ROAD_NOTE, "no_road": True}

# ------------------------------------------------------ vision words
# Ported from runmal.desktop.vision_logic (R-13), unchanged
# in wording; inputs are the raw engine payloads.


def provider_line(provider: dict) -> str:
    provider = provider if isinstance(provider, dict) else {}
    bits = [str(provider.get("provider_id") or "")]
    if provider.get("model"):
        bits.append(str(provider["model"]))
    if provider.get("road"):
        bits.append(str(provider["road"]))
    if provider.get("semantic"):
        bits.append("semantic")
    bits.append("available" if provider.get("available")
                else "unavailable")
    if provider.get("note"):
        bits.append(str(provider["note"]))
    return " · ".join(bits)


def providers_words(payload: dict) -> str:
    payload = payload if isinstance(payload, dict) else {}
    lines: list[str] = []
    providers = payload.get("providers")
    if isinstance(providers, list):
        for row in providers:
            if isinstance(row, dict):
                lines.append(provider_line(row))
    note = payload.get("semantic_caption_note")
    if isinstance(note, str) and note:
        lines.append("")
        lines.append(note)
    backends = payload.get("backends")
    if isinstance(backends, list) and backends:
        lines.append("")
        for row in backends:
            if not isinstance(row, dict):
                continue
            declared = "yes" if row.get("vision_declared") else "no"
            lines.append(
                f"{row.get('backend_key', '')} · {row.get('model_id', '')}"
                f" · vision declared: {declared}")
    return "\n".join(lines)


def _dims(view: dict) -> str:
    if view.get("image_width") and view.get("image_height"):
        return f"{view['image_width']}x{view['image_height']}"
    return ""


def _flat(view: dict) -> dict:
    """Flatten one vision record for the words layer: the
    engine serialises provider and image as nested dicts
    (the desktop client's views flatten them the same way);
    the raw payload itself is never altered."""
    if not isinstance(view, dict):
        return {}
    out = dict(view)
    image = view.get("image")
    if isinstance(image, dict):
        if not out.get("image_format"):
            out["image_format"] = image.get("format")
        if not out.get("image_width"):
            out["image_width"] = image.get("width")
        if not out.get("image_height"):
            out["image_height"] = image.get("height")
        if not out.get("image_size"):
            out["image_size"] = image.get("bytes")
    provider = view.get("provider")
    if isinstance(provider, dict):
        if not out.get("provider_id"):
            out["provider_id"] = provider.get("provider_id")
        if not out.get("provider_model"):
            out["provider_model"] = provider.get("model")
        if not out.get("provider_road"):
            out["provider_road"] = provider.get("road")
    return out


def description_line(description: dict) -> str:
    description = _flat(description)
    bits: list[str] = []
    if description.get("created_at"):
        bits.append(str(description["created_at"]))
    if description.get("provider_id"):
        bits.append(str(description["provider_id"]))
    if description.get("source_kind"):
        bits.append(str(description["source_kind"]))
    text = " ".join(str(description.get("description") or "").split())
    if text:
        bits.append(text[:60])
    return " · ".join(bits)


def description_words(description: dict) -> str:
    description = _flat(description)
    lines: list[str] = [str(description.get("description") or "")]
    lines.append("")
    provider_bits = [
        str(b) for b in (description.get("provider_id"),
                         description.get("provider_model"),
                         description.get("provider_road")) if b]
    if provider_bits:
        lines.append("Provider: " + " · ".join(provider_bits))
    source = str(description.get("source_kind") or "")
    if description.get("source_ref"):
        source = f"{source} {description['source_ref']}".strip()
    if source:
        lines.append(f"Source: {source}")
    if description.get("question"):
        lines.append(f"Question: {description['question']}")
    facts: list[str] = []
    if description.get("image_format"):
        facts.append(str(description["image_format"]))
    dims = _dims(description)
    if dims:
        facts.append(dims)
    if description.get("image_size"):
        facts.append(f"{description['image_size']} bytes")
    if facts:
        lines.append("Image: " + " · ".join(facts))
    return "\n".join(lines)


def attachment_line(attachment: dict) -> str:
    attachment = _flat(attachment)
    bits = [str(attachment.get("filename") or "(unnamed)")]
    if attachment.get("image_format"):
        bits.append(str(attachment["image_format"]))
    dims = _dims(attachment)
    if dims:
        bits.append(dims)
    if attachment.get("image_size"):
        bits.append(f"{attachment['image_size']} bytes")
    if attachment.get("created_at"):
        bits.append(str(attachment["created_at"]))
    if attachment.get("message_id"):
        bits.append("on a message")
    return " · ".join(bits)


def watch_line(watch: dict) -> str:
    watch = watch if isinstance(watch, dict) else {}
    bits = [str(watch.get("path") or watch.get("id") or "")]
    bits.append("enabled" if watch.get("enabled") else "disabled")
    bits.append("recursive" if watch.get("recursive") else "flat")
    if watch.get("chat_id"):
        bits.append(f"chat {watch['chat_id']}")
    return " · ".join(bits)


def scan_report_words(report: dict) -> str:
    report = report if isinstance(report, dict) else {}
    lines: list[str] = []
    scanned = report.get("scanned")
    if isinstance(scanned, int):
        lines.append(f"Scanned: {scanned} file(s).")
    ingested = report.get("ingested")
    if isinstance(ingested, list):
        lines.append(f"Ingested: {len(ingested)} new attachment(s).")
        lines.extend(f"- {item}" for item in ingested)
    skipped = report.get("skipped")
    if isinstance(skipped, list) and skipped:
        lines.append("Skipped:")
        for row in skipped:
            if isinstance(row, dict):
                path = row.get("path") or row.get("source_path") or "?"
                reason = row.get("reason") or ""
                lines.append(f"- {path}: {reason}" if reason else f"- {path}")
            else:
                lines.append(f"- {row}")
    if report.get("truncated"):
        lines.append("The scan was truncated at the file limit.")
    described = report.get("described")
    if isinstance(described, list):
        lines.append(f"Described: {len(described)} image(s).")
        lines.extend(f"- {item}" for item in described)
    return "\n".join(lines)


def ingested_line(row: dict) -> str:
    row = row if isinstance(row, dict) else {}
    bits = [str(row.get("source_path", "") or "")]
    size = row.get("size")
    if isinstance(size, int) and size:
        bits.append(f"{size} bytes")
    if row.get("attachment_id"):
        bits.append(f"attachment {row['attachment_id']}")
    if row.get("ingested_at"):
        bits.append(str(row["ingested_at"]))
    return " · ".join(bits)

# ----------------------------------------------------- vision flows


def providers_view(engine) -> dict:
    payload = engine.request("GET", "/api/v1/vision/providers")
    payload = payload if isinstance(payload, dict) else {}
    return {"providers": payload, "words": providers_words(payload),
            "semantic_available": bool(
                payload.get("semantic_caption_available")),
            "send_note": VISION_SEND_NOTE}


def attach_image(engine, chat_id: str, filename: str, data: bytes,
                 message_id: str | None = None, describe: bool = False,
                 question: str = "") -> dict:
    """The engine's attach road, verbatim in shape: base64
    bytes, the chat, an optional message binding, and the
    describe opt-in only when asked. The bytes the browser
    sent are copied to the engine - the user's own file is
    never moved or touched."""
    body: dict[str, Any] = {
        "chat_id": str(chat_id or ""),
        "filename": str(filename or ""),
        "image_b64": base64.b64encode(data).decode(),
    }
    if message_id:
        body["message_id"] = str(message_id)
    if describe:
        body["describe"] = True
        body["describe_question"] = str(question or "")
    record = engine.request("POST", "/api/v1/vision/attachments",
                            json_body=body)
    record = record if isinstance(record, dict) else {}
    out = {"attachment": record, "line": attachment_line(record)}
    description = record.get("description")
    if isinstance(description, dict):
        out["description"] = description
        out["description_words"] = description_words(description)
    return out


def list_attachments(engine, chat_id: str) -> dict:
    payload = engine.request("GET", "/api/v1/vision/attachments",
                             params={"chat_id": chat_id})
    payload = payload if isinstance(payload, dict) else {}
    rows = [r for r in payload.get("attachments") or []
            if isinstance(r, dict)]
    return {"chat_id": payload.get("chat_id", chat_id),
            "attachments": rows,
            "lines": [attachment_line(r) for r in rows]}


def delete_attachment(engine, attachment_id: str) -> dict:
    payload = engine.request(
        "DELETE", f"/api/v1/vision/attachments/{attachment_id}")
    return payload if isinstance(payload, dict) else {}


def describe(engine, payload: dict) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    body: dict[str, Any] = {"chat_id": str(payload.get("chat_id") or ""),
                            "question": str(payload.get("question") or "")}
    if payload.get("attachment_id"):
        body["attachment_id"] = str(payload["attachment_id"])
    if payload.get("image_b64"):
        body["image_b64"] = str(payload["image_b64"])
    if payload.get("provider"):
        body["provider"] = str(payload["provider"])
    if payload.get("require_semantic"):
        body["require_semantic"] = True
    record = engine.request("POST", "/api/v1/vision/describe",
                            json_body=body)
    record = record if isinstance(record, dict) else {}
    return {"description": record, "words": description_words(record),
            "line": description_line(record)}


def list_descriptions(engine, chat_id: str) -> dict:
    payload = engine.request("GET", "/api/v1/vision/descriptions",
                             params={"chat_id": chat_id})
    payload = payload if isinstance(payload, dict) else {}
    rows = [r for r in payload.get("descriptions") or []
            if isinstance(r, dict)]
    return {"chat_id": payload.get("chat_id", chat_id),
            "descriptions": rows,
            "lines": [description_line(r) for r in rows]}


def delete_description(engine, description_id: str) -> dict:
    payload = engine.request(
        "DELETE", f"/api/v1/vision/descriptions/{description_id}")
    return payload if isinstance(payload, dict) else {}


def list_watch_folders(engine, chat_id: str) -> dict:
    payload = engine.request("GET", "/api/v1/vision/watch-folders",
                             params={"chat_id": chat_id})
    payload = payload if isinstance(payload, dict) else {}
    rows = [r for r in payload.get("watch_folders") or []
            if isinstance(r, dict)]
    return {"chat_id": payload.get("chat_id", chat_id),
            "watch_folders": rows,
            "lines": [watch_line(r) for r in rows]}


def create_watch_folder(engine, payload: dict) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    body = {"chat_id": str(payload.get("chat_id") or ""),
            "path": str(payload.get("path") or ""),
            "recursive": bool(payload.get("recursive"))}
    record = engine.request("POST", "/api/v1/vision/watch-folders",
                            json_body=body)
    record = record if isinstance(record, dict) else {}
    return {"watch": record, "line": watch_line(record)}


def update_watch_folder(engine, watch_id: str, payload: dict) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    body: dict[str, Any] = {}
    if payload.get("enabled") is not None:
        body["enabled"] = bool(payload["enabled"])
    if payload.get("recursive") is not None:
        body["recursive"] = bool(payload["recursive"])
    record = engine.request(
        "PATCH", f"/api/v1/vision/watch-folders/{watch_id}",
        json_body=body)
    record = record if isinstance(record, dict) else {}
    return {"watch": record, "line": watch_line(record)}


def delete_watch_folder(engine, watch_id: str) -> dict:
    payload = engine.request(
        "DELETE", f"/api/v1/vision/watch-folders/{watch_id}")
    return payload if isinstance(payload, dict) else {}


def scan_watch_folder(engine, watch_id: str, payload: dict) -> dict:
    payload = payload if isinstance(payload, dict) else {}
    body: dict[str, Any] = {}
    if payload.get("describe"):
        body["describe"] = True
        body["describe_question"] = str(payload.get("question") or "")
    record = engine.request(
        "POST", f"/api/v1/vision/watch-folders/{watch_id}/scan",
        json_body=body)
    record = record if isinstance(record, dict) else {}
    return {"report": record, "words": scan_report_words(record)}


def list_watch_ingested(engine, watch_id: str) -> dict:
    payload = engine.request(
        "GET", f"/api/v1/vision/watch-folders/{watch_id}/ingested")
    payload = payload if isinstance(payload, dict) else {}
    rows = payload.get("ingested")
    rows = rows if isinstance(rows, list) else []
    rows = [r for r in rows if isinstance(r, dict)]
    return {"ingested": rows, "lines": [ingested_line(r) for r in rows]}
