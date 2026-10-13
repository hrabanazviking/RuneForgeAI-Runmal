"""Bridge TTS hook (S604, BRIDGE_PROTOCOL §9).

A bridge requests synthesis by text; Rúnmál runs it through the voice
seam (S504 registry) as a job with an explicit lifecycle:

    tts.requested -> tts.synthesizing -> tts.ready | tts.failed | tts.cancelled

The bridge fetches the WAV when ready and reports its own playback
(`playback.started` / `playback.completed` / `playback.interrupted`).
Playback happens on the bridge's side of the wall, so it is recorded
as job lifecycle only — the S508 playback-truth ledger is fed only
when Rúnmál owns the audio path (protocol §9), and bridge turns are
never marked "heard" from a bridge's say-so.

Jobs are in-process (like generation request ids): they are a live
hook, not durable state. A job is visible only to the bridge that
requested it.
"""

from __future__ import annotations

import io
import threading
import uuid
import wave
from dataclasses import dataclass, field
from datetime import UTC, datetime

from runmal.voice.backends import BackendUnavailable, resolve_tts_backend
from runmal.voice.tts import SAMPLE_RATE, TTSBackend, VoiceInfo

STATUS_QUEUED = "queued"
STATUS_SYNTHESIZING = "synthesizing"
STATUS_READY = "ready"
STATUS_FAILED = "failed"
STATUS_CANCELLED = "cancelled"

PLAYBACK_EVENTS = frozenset({"playback.started", "playback.completed", "playback.interrupted"})


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class TTSJob:
    id: str
    bridge_id: str
    user_id: str
    text: str
    backend_key: str
    voice_id: str
    chat_id: str | None = None
    status: str = STATUS_QUEUED
    events: list[dict] = field(default_factory=list)
    audio: bytes | None = None
    sample_rate: int = SAMPLE_RATE
    error: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    done: threading.Event = field(default_factory=threading.Event)

    def record(self, kind: str, detail: dict | None = None) -> dict:
        event = {"seq": len(self.events) + 1, "kind": kind, "at": _now_iso()}
        if detail:
            event.update(detail)
        self.events.append(event)
        return event

    def to_dict(self) -> dict:
        return {
            "job_id": self.id,
            "status": self.status,
            "backend": self.backend_key,
            "voice_id": self.voice_id,
            "chat_id": self.chat_id,
            "text": self.text,
            "error": self.error,
            "sample_rate": self.sample_rate,
            "audio_ready": self.audio is not None,
            "events": list(self.events),
        }


_jobs: dict[str, TTSJob] = {}
_jobs_lock = threading.Lock()


def resolve_backend(key: str) -> TTSBackend:
    """Indirection over the registry resolver (tests substitute fakes)."""
    return resolve_tts_backend(key)


def _pcm_to_wav(pcm: bytes, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(pcm)
    return buffer.getvalue()


def _run_job(job: TTSJob, backend: TTSBackend, voice: VoiceInfo, speaking_rate: float) -> None:
    try:
        job.status = STATUS_SYNTHESIZING
        job.record("tts.synthesizing", {"backend": job.backend_key})
        chunks = []
        stream = backend.synthesize(job.text, voice, speaking_rate=speaking_rate)
        for chunk in stream:
            if job.cancel.is_set():
                close = getattr(stream, "close", None)
                if close is not None:
                    close()
                break
            if chunk.is_final or not chunk.pcm:
                continue
            chunks.append(chunk)
        if job.cancel.is_set():
            job.status = STATUS_CANCELLED
            job.record("tts.cancelled")
            return
        job.sample_rate = chunks[0].sample_rate if chunks else SAMPLE_RATE
        job.audio = _pcm_to_wav(b"".join(c.pcm for c in chunks), job.sample_rate)
        job.status = STATUS_READY
        job.record(
            "tts.ready",
            {"chunks": len(chunks), "bytes": len(job.audio)},
        )
    except Exception as exc:  # backend failure becomes job truth, not a crash
        job.status = STATUS_FAILED
        job.error = f"{type(exc).__name__}: {exc}"
        job.record("tts.failed", {"error": job.error})
    finally:
        job.done.set()


def start_job(
    *,
    bridge_id: str,
    user_id: str,
    text: str,
    backend_key: str,
    voice: VoiceInfo,
    chat_id: str | None = None,
    speaking_rate: float = 1.0,
    backend: TTSBackend | None = None,
) -> TTSJob:
    """Create a job and start synthesis on a worker thread.

    The backend is constructed eagerly so an unavailable backend fails
    the job immediately and honestly (event `tts.failed`) instead of
    pretending to queue.
    """
    job = TTSJob(
        id=uuid.uuid4().hex,
        bridge_id=bridge_id,
        user_id=user_id,
        text=text,
        backend_key=backend_key,
        voice_id=voice.voice_id,
        chat_id=chat_id,
    )
    job.record("tts.requested", {"backend": backend_key, "voice_id": voice.voice_id})
    with _jobs_lock:
        _jobs[job.id] = job
    try:
        resolved = backend or resolve_backend(backend_key)
    except BackendUnavailable as exc:
        job.status = STATUS_FAILED
        job.error = f"BackendUnavailable: {exc}"
        job.record("tts.failed", {"error": job.error})
        job.done.set()
        return job
    thread = threading.Thread(
        target=_run_job, args=(job, resolved, voice, speaking_rate), daemon=True
    )
    thread.start()
    return job


def get_job(bridge_id: str, job_id: str) -> TTSJob | None:
    """A bridge sees only its own jobs; anyone else's id is a 404."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if job is None or job.bridge_id != bridge_id:
        return None
    return job


def cancel_job(job: TTSJob) -> bool:
    """Signal cancellation. Returns False when the job already finished."""
    if job.status in (STATUS_READY, STATUS_FAILED, STATUS_CANCELLED):
        return False
    job.cancel.set()
    return True


def report_playback(job: TTSJob, kind: str, detail: dict | None = None) -> dict:
    """Record a bridge-reported playback lifecycle event (see module doc)."""
    if kind not in PLAYBACK_EVENTS:
        raise ValueError(f"unknown playback event: {kind!r}")
    if job.status != STATUS_READY:
        raise ValueError(f"job is {job.status}; playback requires a ready job")
    return job.record(kind, detail or None)
