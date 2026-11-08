"""Voice UI island (S511): mic/status/waveform/device selector.

JSON API under ``/api/v1/voice`` (bearer-gated like every API) plus a
server-rendered page at ``/voice`` (public page, loopback boundary per
ADR-0003 — same pattern as the S410 memory browser).

The island is a CONTROL SURFACE over the S501 plumbing: it enumerates
devices through the app provider, persists role selection through
``RoleMap`` (missing saved device → REMAP_REQUIRED is rendered as a
warning state, never silently re-defaulted), shows the live session
state, and renders a waveform from the capture ring buffer.

Provider injection: ``app.state.voice_provider`` — production defaults
to the fixture provider until a deployment wires SoundDeviceProvider;
tests inject their own fixture provider to simulate unplug/remap.
"""

from __future__ import annotations

import html
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse

from runmal.voice.audio import (
    DeviceProvider,
    DeviceRole,
    FixtureDeviceProvider,
    RoleMap,
)
from runmal.voice.backends import TTS_REGISTRY
from runmal.voice.install import backend_status, start_install
from runmal.voice.metrics import MetricsCollector
from runmal.voice.settings import VoiceSettings, settings_path
from runmal.voice.stt_backends import STT_REGISTRY

router = APIRouter(tags=["voice"])


def get_provider(request: Request) -> DeviceProvider:
    provider = getattr(request.app.state, "voice_provider", None)
    if provider is None:
        provider = FixtureDeviceProvider()
        request.app.state.voice_provider = provider
    return provider


def _roles_path(request: Request) -> Path:
    data_dir = Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return data_dir / "voice_roles.json"


def load_roles(request: Request) -> RoleMap:
    return RoleMap.load(_roles_path(request))


def waveform_levels(samples, buckets: int = 48) -> list[float]:
    """Peak-amplitude levels per bucket for the waveform island."""
    values = list(samples)
    if not values:
        return [0.0] * buckets
    size = max(1, len(values) // buckets)
    levels: list[float] = []
    for i in range(buckets):
        window = values[i * size : (i + 1) * size]
        if not window:
            levels.append(0.0)
        else:
            levels.append(round(max(abs(v) for v in window) / 32768.0, 4))
    return levels


@router.get("/voice/devices")
async def list_devices(request: Request) -> dict:
    provider = get_provider(request)
    return {
        "devices": [d.to_dict() for d in provider.list_devices()],
        "provider": provider.provider_key,
    }


@router.get("/voice/roles")
async def get_roles(request: Request) -> dict:
    roles = load_roles(request)
    resolved = roles.resolve(get_provider(request))
    return {
        "assignments": roles.to_dict(),
        "resolution": {
            role.value: {
                "status": entry.status.value,
                "device_id": entry.device.device_id if entry.device else None,
                "saved": entry.saved.to_dict() if entry.saved else None,
            }
            for role, entry in resolved.items()
        },
    }


@router.put("/voice/roles/{role}")
async def set_role(role: str, payload: dict, request: Request) -> dict:
    try:
        device_role = DeviceRole(role)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown role: {role}"
        ) from None
    provider = get_provider(request)
    device = provider.find(str(payload.get("device_id", "")))
    if device is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="device not present; pick a present device (no silent default substitution)",
        )
    roles = load_roles(request)
    try:
        roles.assign(device_role, device)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    roles.save(_roles_path(request))
    return {"role": role, "device_id": device.device_id, "status": "ok"}


@router.get("/voice/status")
async def voice_status(request: Request) -> dict:
    session = getattr(request.app.state, "voice_session", None)
    collector: MetricsCollector | None = getattr(request.app.state, "voice_metrics", None)
    ring = getattr(request.app.state, "voice_ring", None)
    report = collector.report().to_dict() if collector is not None else None
    return {
        "state": session.state.value if session is not None else "LISTENING",
        "turns": len(session.turns) if session is not None else 0,
        "waveform": waveform_levels(ring.snapshot()) if ring is not None else [],
        "metrics": report,
    }


# ------------------------------------------------------- backends (ADR-0005/6)


def _backends_payload() -> dict:
    """Registry + live status for every TTS/STT backend (UI surface).

    The audit verdict is BINDING only for default-shipped backends;
    for user-installed backends it is displayed as information, with
    the honest notice — the gate guards only what Rúnmál ships
    (Volmarr's policy-scope ruling, 2026-10-13).
    """
    settings = VoiceSettings.load()
    tts: list[dict] = []
    for key, spec in TTS_REGISTRY.items():
        entry = backend_status(
            spec.plan,
            default_shipped=spec.default_shipped,
            verified=spec.verified,
            tree_packages=spec.tree_packages,
        )
        entry["display_name"] = spec.display_name
        entry["selected"] = settings.tts_backend == key
        entry["thresholds"] = {
            "max_first_audio_p50_s": spec.first_audio_p50_s,
            "max_rtf_p50": spec.rtf_p50,
        }
        tts.append(entry)
    stt: list[dict] = []
    for key, spec in STT_REGISTRY.items():
        entry = backend_status(
            spec.plan,
            default_shipped=spec.default_shipped,
            verified=spec.verified,
            tree_packages=spec.tree_packages,
        )
        entry["display_name"] = spec.display_name
        entry["selected"] = settings.stt_backend == key
        stt.append(entry)
    return {
        "tts": tts,
        "stt": stt,
        "defaults": {"tts_backend": settings.tts_backend, "stt_backend": settings.stt_backend},
    }


@router.get("/voice/backends")
async def list_backends(request: Request) -> dict:
    return _backends_payload()


@router.post("/voice/backends/{kind}/{key}/install")
async def install_backend(kind: str, key: str, request: Request) -> dict:
    """The one-button install: an explicit user action, and the ONLY
    path that installs a backend (ADR-0005/0006). Registered-but-
    unverified plans refuse — the button explains, nothing runs."""
    registry = {"tts": TTS_REGISTRY, "stt": STT_REGISTRY}.get(kind)
    spec = registry.get(key) if registry is not None else None
    if spec is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"unknown backend: {kind}/{key}"
        )
    if not spec.plan.enable:
        return {
            "key": key,
            "kind": kind,
            "status": "refused",
            "error": spec.plan.note or "registered but not forge-verified — no install recipe yet",
        }
    state = start_install(spec.plan)
    return state.as_dict()


@router.get("/voice/settings/defaults")
async def get_defaults(request: Request) -> dict:
    settings = VoiceSettings.load()
    return {"tts_backend": settings.tts_backend, "stt_backend": settings.stt_backend}


@router.put("/voice/settings/defaults")
async def set_defaults(payload: dict, request: Request) -> dict:
    settings = VoiceSettings.load()
    try:
        if payload.get("tts_backend"):
            settings.set_tts_backend(str(payload["tts_backend"]))
        if payload.get("stt_backend"):
            settings.set_stt_backend(str(payload["stt_backend"]))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from None
    settings.save(settings_path())
    return {
        "tts_backend": settings.tts_backend,
        "stt_backend": settings.stt_backend,
        "status": "ok",
    }


_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Rúnmál — Voice</title></head>
<body>
<h1>Voice</h1>
<p id="voice-state">State: {state}</p>
<canvas id="waveform" width="480" height="80" aria-label="microphone waveform"></canvas>
<section id="device-selectors">
{selectors}
</section>
<p id="remap-warning" hidden>⚠ A saved device is missing — remap it above.
Rúnmál never substitutes the OS default silently.</p>
<section id="voice-backends">
<h2>Voice backends</h2>
<!-- BACKENDS -->
</section>
<script>
async function refresh() {{
  const res = await fetch('/api/v1/voice/status');
  if (!res.ok) return;
  const data = await res.json();
  document.getElementById('voice-state').textContent = 'State: ' + data.state;
  const canvas = document.getElementById('waveform');
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  const levels = data.waveform || [];
  levels.forEach((v, i) => {{
    const h = Math.max(1, v * canvas.height);
    ctx.fillRect(i * 10, (canvas.height - h) / 2, 6, h);
  }});
}}
setInterval(refresh, 500); refresh();
</script>
</body></html>"""


def _backends_panel() -> str:
    """Server-rendered backends panel: admission class, install state,
    the honest user-install notice, and the audit verdict (binding
    only for default-shipped backends; information otherwise)."""
    payload = _backends_payload()
    rows: list[str] = []
    for kind in ("tts", "stt"):
        for entry in payload[kind]:
            classes = ["shipped by default" if entry["default_shipped"] else "user-installed"]
            if entry["unverified_label"]:
                classes.append(entry["unverified_label"])
            audit = entry["audit"]
            if audit is None:
                audit_line = "license audit: not installed yet"
            elif audit["passed"]:
                audit_line = f"license audit: PASS ({audit['checked']} distributions checked)"
            else:
                audit_line = "license audit: " + "; ".join(audit["violations"])
            if audit is not None and not audit["binding"]:
                audit_line += " (information only — your choice, your terms)"
            notice = (
                f'<p class="user-install-notice">{html.escape(entry["notice"])}</p>'
                if entry["notice"]
                else ""
            )
            rows.append(
                f'<div class="backend" data-key="{html.escape(entry["key"])}">'
                f"<h3>{html.escape(entry['display_name'])}</h3>"
                f"<p>{html.escape(' · '.join(classes))}</p>"
                f"<p>installed: {'yes' if entry['installed'] else 'no'}"
                f" · selected default: {'yes' if entry['selected'] else 'no'}</p>"
                f"<p>{html.escape(audit_line)}</p>{notice}</div>"
            )
    return "\n".join(rows)


async def voice_page(request: Request) -> HTMLResponse:
    provider = get_provider(request)
    roles = load_roles(request)
    resolved = roles.resolve(provider)
    devices = provider.list_devices()
    selectors: list[str] = []
    any_remap = False
    for role in DeviceRole:
        entry = resolved[role]
        if entry.status.value == "remap_required":
            any_remap = True
        options = []
        for device in devices:
            if device.direction != role.direction:
                continue
            selected = ""
            if entry.device and entry.device.device_id == device.device_id:
                selected = " selected"
            options.append(
                f'<option value="{html.escape(device.device_id)}"{selected}>'
                f"{html.escape(device.name)}</option>"
            )
        selectors.append(
            f"<label>{role.value} [{html.escape(entry.status.value)}] "
            f'<select name="{role.value}">{"".join(options)}</select></label>'
        )
    page = _PAGE.format(state="LISTENING", selectors="\n".join(selectors))
    page = page.replace("<!-- BACKENDS -->", _backends_panel())
    if any_remap:
        page = page.replace('id="remap-warning" hidden', 'id="remap-warning"')
    return HTMLResponse(page)


# ------------------------------------------------- sessions (P-101)
# The voice session as a first-class citizen of a chat: start/stop,
# per-chat settings resolved honestly at start (character voice +
# provider truth), and turns persisted with the session in the
# voice JSON store. Founding routes above are untouched.

from fastapi import Depends  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from runmal.db.deps import get_owner_id, get_session  # noqa: E402
from runmal.db.models import Chat  # noqa: E402
from runmal.voice import session as voice_session  # noqa: E402
from runmal.voice.profiles import resolve_character_voice  # noqa: E402


def _session_store(request: Request) -> voice_session.VoiceSessionStore:
    data_dir = Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return voice_session.VoiceSessionStore(data_dir / voice_session.SESSIONS_FILENAME)


@router.post("/voice/sessions", status_code=status.HTTP_201_CREATED)
async def start_voice_session(
    payload: dict,
    request: Request,
    session: AsyncSession = Depends(get_session),
    owner_id: str = Depends(get_owner_id),
) -> dict:
    chat_id = str(payload.get("chat_id", ""))
    chat = await session.get(Chat, chat_id) if chat_id else None
    if chat is None or chat.user_id != owner_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="chat not found"
        )
    character = None
    if chat.character_id:
        character = await resolve_character_voice(session, owner_id, chat.character_id)
    settings = voice_session.resolve_session_settings(
        defaults=VoiceSettings.load(), character=character
    )
    created = voice_session.start_session(
        _session_store(request),
        chat_id=chat.id,
        user_id=owner_id,
        character_id=chat.character_id,
        settings=settings,
        auto_project=bool(payload.get("auto_project", False)),
    )
    return created.to_dict()


@router.get("/voice/sessions")
async def list_voice_sessions(request: Request, chat_id: str = "") -> dict:
    store = _session_store(request)
    sessions = store.list_for_chat(chat_id) if chat_id else store.all_sessions()
    active = store.active_for_chat(chat_id) if chat_id else None
    return {
        "sessions": [s.summary_dict() for s in sessions],
        "active_session_id": active.session_id if active else None,
    }


@router.get("/voice/sessions/{session_id}")
async def get_voice_session(session_id: str, request: Request) -> dict:
    found = _session_store(request).get(session_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="voice session not found"
        )
    return found.to_dict()


@router.post("/voice/sessions/{session_id}/stop")
async def stop_voice_session(session_id: str, payload: dict, request: Request) -> dict:
    store = _session_store(request)
    found = store.get(session_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="voice session not found"
        )
    found.stop(str(payload.get("note", "") or ""))
    store.save_session(found)
    return found.to_dict()


@router.post("/voice/sessions/{session_id}/turns", status_code=status.HTTP_201_CREATED)
async def record_voice_turn(
    session_id: str,
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict:
    store = _session_store(request)
    found = store.get(session_id)
    if found is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="voice session not found"
        )
    raw_words = payload.get("transcript_words") or []
    if not isinstance(raw_words, list):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="transcript_words must be a list",
        )
    try:
        word_evidence = tuple(
            voice_session.WordConfidence.from_dict(entry)
            for entry in raw_words
            if isinstance(entry, dict)
        )
        if len(word_evidence) != len(raw_words):
            raise ValueError("transcript_words entries must be objects")
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="transcript_words are malformed",
        ) from None
    try:
        turn = found.record_turn(
            transcript_text=str(payload.get("transcript_text", "") or ""),
            transcript_language=str(payload.get("transcript_language", "") or ""),
            response_text=str(payload.get("response_text", "") or ""),
            heard_certain=str(payload.get("heard_certain", "") or ""),
            heard_uncertain=str(payload.get("heard_uncertain", "") or ""),
            heard_unplayed=str(payload.get("heard_unplayed", "") or ""),
            interrupted=bool(payload.get("interrupted", False)),
            error=str(payload.get("error", "") or ""),
            chunks_total=int(payload.get("chunks_total", 0) or 0),
            chunks_played=int(payload.get("chunks_played", 0) or 0),
            transcript_words=word_evidence,
        )
    except voice_session.VoiceSessionError as exc:
        code = (
            status.HTTP_409_CONFLICT
            if "stopped" in str(exc)
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=str(exc)) from None
    except (TypeError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="turn fields are malformed",
        ) from None
    store.save_session(found)
    result = turn.to_dict()
    # P-104: an opted-in session auto-projects through the async
    # host; the report rides along only when one was attempted.
    from runmal.voice import autoproject as _auto

    report = await _auto.autoproject_session(db, session=found, store=store)
    if report["attempted"]:
        result["auto_projection"] = report
    return result


@router.delete("/voice/chats/{chat_id}/sessions")
async def drop_chat_voice_sessions(chat_id: str, request: Request) -> dict:
    dropped = _session_store(request).drop_chat(chat_id)
    return {"chat_id": chat_id, "dropped": dropped}
