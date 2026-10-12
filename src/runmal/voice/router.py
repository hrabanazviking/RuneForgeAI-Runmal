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
from runmal.voice.metrics import MetricsCollector

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
        window = values[i * size:(i + 1) * size]
        if not window:
            levels.append(0.0)
        else:
            levels.append(round(max(abs(v) for v in window) / 32768.0, 4))
    return levels


@router.get("/voice/devices")
async def list_devices(request: Request) -> dict:
    provider = get_provider(request)
    return {"devices": [d.to_dict() for d in provider.list_devices()],
            "provider": provider.provider_key}


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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail=f"unknown role: {role}") from None
    provider = get_provider(request)
    device = provider.find(str(payload.get("device_id", "")))
    if device is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="device not present; pick a present device "
                                   "(no silent default substitution)")
    roles = load_roles(request)
    try:
        roles.assign(device_role, device)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=str(exc)) from None
    roles.save(_roles_path(request))
    return {"role": role, "device_id": device.device_id, "status": "ok"}


@router.get("/voice/status")
async def voice_status(request: Request) -> dict:
    session = getattr(request.app.state, "voice_session", None)
    collector: MetricsCollector | None = getattr(
        request.app.state, "voice_metrics", None)
    ring = getattr(request.app.state, "voice_ring", None)
    report = collector.report().to_dict() if collector is not None else None
    return {
        "state": session.state.value if session is not None else "LISTENING",
        "turns": len(session.turns) if session is not None else 0,
        "waveform": waveform_levels(ring.snapshot()) if ring is not None else [],
        "metrics": report,
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
                f"{html.escape(device.name)}</option>")
        selectors.append(
            f'<label>{role.value} [{html.escape(entry.status.value)}] '
            f'<select name="{role.value}">{"".join(options)}</select></label>')
    page = _PAGE.format(state="LISTENING", selectors="\n".join(selectors))
    if any_remap:
        page = page.replace('id="remap-warning" hidden', 'id="remap-warning"')
    return HTMLResponse(page)
