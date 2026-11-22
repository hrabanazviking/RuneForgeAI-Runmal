"""Voice logic for the desktop shell (R-13) — Qt-free.

The words over the engine's voice surface: status + metrics,
device enumeration and role resolution (a missing saved device
is a REMAP warning, never a silent OS-default substitution —
INV-022), backend install/audit truth (the license audit binds
only what Rúnmál ships by default; for user-installed backends
it is information), and voice sessions bound to chats.
"""

from __future__ import annotations

from typing import Any

from runmal.desktop.client import (
    RunmalClient,
    VoiceBackendView,
    VoiceDeviceView,
    VoiceSessionView,
)

_ROLE_STATUS_WORDS = {
    "ok": "ready",
    "unassigned": "not assigned",
    "remap_required": "saved device missing — remap required",
}


def status_words(status: dict[str, Any]) -> str:
    """The status pane: session state, turns, and the metrics
    report rendered honestly (no collector → said plainly)."""
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


def device_line(device: VoiceDeviceView) -> str:
    bits = [device.name or device.device_id]
    if device.direction:
        bits.append(device.direction)
    if device.host_api:
        bits.append(device.host_api)
    bits.append(f"{device.max_channels} channel(s)")
    if device.sample_rates:
        rates = ", ".join(f"{r} Hz" for r in device.sample_rates)
        bits.append(f"sample rates: {rates}")
    if device.is_system_default:
        bits.append("system default")
    return " · ".join(bits)


def role_lines(
    roles: dict[str, Any], devices: list[VoiceDeviceView]
) -> list[str]:
    """One line per role from the payload's ``resolution`` map:
    role, status in words, and the device name when resolved.
    A remap-required line carries the INV-022 warning in full."""
    by_id = {d.device_id: d for d in devices}
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
            name = device.name if device is not None else str(device_id)
            if name:
                line += f" · {name}"
        if status == "remap_required":
            line += (
                " — the saved device is missing; pick a present device."
                " Rúnmál never substitutes the OS default silently."
            )
        lines.append(line)
    return lines


def backend_line(backend: VoiceBackendView) -> str:
    bits = [backend.display_name or backend.key]
    bits.append(
        "shipped by default" if backend.default_shipped else "user-installed"
    )
    bits.append("installed: yes" if backend.installed else "installed: no")
    if backend.selected:
        bits.append("selected default")
    status = backend.install_status
    if status and status not in ("not_started", "done"):
        line = f"install: {status}"
        if backend.install_step:
            line += f" ({backend.install_step})"
        if backend.install_error:
            line += f" — {backend.install_error}"
        bits.append(line)
    if backend.unverified_label:
        bits.append(backend.unverified_label)
    return " · ".join(bits)


def audit_words(backend: VoiceBackendView) -> str:
    """The license-audit verdict in words, with its scope: the
    audit binds only default-shipped backends; for a user's own
    install it is information (the engine page's honesty)."""
    audit = backend.audit
    if audit is None:
        return "license audit: not installed yet"
    if audit.get("passed"):
        checked = audit.get("checked")
        words = (
            f"license audit: PASS ({checked} distributions checked)"
            if isinstance(checked, int)
            else "license audit: PASS"
        )
    else:
        violations = audit.get("violations")
        joined = (
            "; ".join(str(v) for v in violations)
            if isinstance(violations, list) and violations
            else "failed"
        )
        words = f"license audit: {joined}"
    if audit.get("binding"):
        words += " (binding for default-shipped backends)"
    else:
        words += " (information only — your choice, your terms)"
    return words


def session_line(session: VoiceSessionView) -> str:
    bits = [session.state or "session"]
    if session.chat_id:
        bits.append(f"chat {session.chat_id}")
    bits.append(f"{session.turn_count} turn(s)")
    if session.created_at:
        bits.append(f"started {session.created_at}")
    if session.stopped_at:
        stopped = f"stopped {session.stopped_at}"
        if session.stop_note:
            stopped += f" — {session.stop_note}"
        bits.append(stopped)
    return " · ".join(bits)


def _excerpt(text: str, limit: int = 80) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def session_detail_words(detail: dict[str, Any]) -> str:
    """The session detail pane: the resolved settings as the
    engine gives them, then each turn briefly."""
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
                    f"{k}={v}" for k, v in sorted(value.items())
                )
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


def latency_words(payload: dict[str, Any]) -> str:
    """The latency pane: how many turns carry evidence, and the
    per-key p50/p95 aggregate in seconds."""
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
                f" over {count} turn(s)"
            )
    else:
        lines.append("No latency evidence recorded yet.")
    return "\n".join(lines)


class VoiceFlow:
    """The Voice dialog's verbs over the typed client."""

    def __init__(self, client: RunmalClient) -> None:
        self._client = client

    def status(self) -> dict[str, Any]:
        return self._client.voice_status()

    def devices(self) -> list[VoiceDeviceView]:
        return self._client.voice_devices()

    def device_provider(self) -> str:
        return self._client.voice_device_provider()

    def roles(self) -> dict[str, Any]:
        return self._client.voice_roles()

    def assign_role(self, role: str, device_id: str) -> dict[str, Any]:
        return self._client.set_voice_role(role, device_id)

    def backends(self) -> dict[str, Any]:
        return self._client.voice_backends()

    def install_backend(self, kind: str, key: str) -> dict[str, Any]:
        return self._client.install_voice_backend(kind, key)

    def defaults(self) -> dict[str, Any]:
        return self._client.voice_defaults()

    def set_defaults(
        self,
        tts_backend: str | None = None,
        stt_backend: str | None = None,
    ) -> dict[str, Any]:
        return self._client.set_voice_defaults(
            tts_backend=tts_backend, stt_backend=stt_backend
        )

    def sessions(self, chat_id: str = "") -> dict[str, Any]:
        return self._client.list_voice_sessions(chat_id)

    def start_session(
        self, chat_id: str, auto_project: bool = False
    ) -> VoiceSessionView:
        return self._client.start_voice_session(
            chat_id, auto_project=auto_project
        )

    def stop_session(
        self, session_id: str, note: str = ""
    ) -> VoiceSessionView:
        return self._client.stop_voice_session(session_id, note=note)

    def session_detail(self, session_id: str) -> dict[str, Any]:
        return self._client.get_voice_session(session_id)

    def session_latency(self, session_id: str) -> dict[str, Any]:
        return self._client.voice_session_latency(session_id)

    def live(self, session_id: str) -> dict[str, Any]:
        return self._client.voice_live(session_id)
