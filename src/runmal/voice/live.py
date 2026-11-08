"""Live voice host (P-102, Part VII — DERIVED scope, L1).

P-101 built the voice session citizen and named its first
honest limitation: no live orchestrator is wired into the app
process — sessions could only record turns a caller posted by
hand. This module is that wiring:

- :func:`build_live_orchestrator` assembles a VoiceOrchestrator
  for ONE session from its resolved settings snapshot (P-101's
  SessionSettings shape, consumed duck-typed so this module
  imports only founding modules), subscribing a PlaybackLedger
  (S508) to the orchestrator's chunk hooks so every live turn
  carries playback evidence from the moment it runs.
- :class:`LiveVoiceController` owns the live orchestrators of
  one app process, keyed by session_id: start / speak /
  feed_frames / interrupt / stop / status. Every completed
  turn is persisted through the session citizen's own road —
  ``append_orchestrator_turn(record, heard)`` with the ledger
  reconstruction — followed by the bound store's save.

Honesty rules (battery-pinned):
- backends build through the registry factories from the
  session snapshot; BackendUnavailable is wrapped in
  LiveVoiceError and surfaced — never a silent fake, never an
  install (ADR-0005/0006). Nothing here imports a fake backend.
- wiring road labels are data: "fake" iff the BUILT backend's
  key names a fake (fake-tts / fake-stt), else "registry".
- the default responder is :func:`unavailable_responder`,
  labelled "unavailable": the generation stack is async and
  DB-bound, so until a host injects a synchronous responder a
  mic-driven turn records an honest error turn through the
  orchestrator's ERROR_RECOVERY — never a fabricated reply.
- playback is never defaulted silently: a build without an
  explicit sink or factory refuses plainly. The HTTP road
  supplies one from the app provider through the RoleMap
  (companion_output first, user_playback second; an
  unresolvable role surfaces its truth, INV-022).
- live hosts are process state: a restart drops them. The
  sessions and their recorded turns persist (P-101 store);
  a session can simply be started live again.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from runmal.voice.backends import BackendUnavailable, build_tts_backend
from runmal.voice.ledger import PlaybackLedger
from runmal.voice.orchestrator import Responder, VoiceOrchestrator
from runmal.voice.profiles import DEFAULT_VOICE
from runmal.voice.stt_backends import build_stt_backend
from runmal.voice.tts import VoiceInfo
from runmal.voice.vad import EnergyVadModel, VadSegmenter


class LiveVoiceError(RuntimeError):
    """A live-voice refusal with a plain reason. Nothing degrades silently."""


def unavailable_responder(text: str):
    """The honest default responder: no responder is wired yet.

    The orchestrator catches this through its own error road,
    so a mic turn records the error — it never invents a reply.
    """
    raise LiveVoiceError(
        "no voice responder is wired into this app process; "
        "a deployment injects a synchronous responder to answer mic turns"
    )
    yield  # pragma: no cover - makes this a generator like a real responder


@dataclass(frozen=True)
class LiveWiring:
    """The as-built wiring of one live host, as data."""

    tts_backend: str
    stt_backend: str
    road_tts: str  # "fake" | "registry"
    road_stt: str  # "fake" | "registry"
    vad_model: str
    responder: str  # "unavailable" | "injected"
    voice_id: str
    language: str

    def to_dict(self) -> dict:
        return {
            "tts_backend": self.tts_backend,
            "stt_backend": self.stt_backend,
            "road_tts": self.road_tts,
            "road_stt": self.road_stt,
            "vad_model": self.vad_model,
            "responder": self.responder,
            "voice_id": self.voice_id,
            "language": self.language,
        }


def _road(key: str) -> str:
    return "fake" if key in ("fake-tts", "fake-stt") else "registry"


def _backend_key(backend, fallback: str) -> str:
    return str(getattr(backend, "backend_key", "") or getattr(backend, "name", "") or fallback)


def build_live_orchestrator(
    settings,
    *,
    responder: Responder | None = None,
    tts=None,
    stt=None,
    playback=None,
    segmenter: VadSegmenter | None = None,
    clock: Callable[[], float] | None = None,
) -> tuple[VoiceOrchestrator, PlaybackLedger, LiveWiring]:
    """Assemble one session's live orchestrator + subscribed ledger.

    ``settings`` is duck-typed (tts_backend / stt_backend /
    voice_id / language — P-101's SessionSettings shape).
    Explicit seams win; otherwise the registry factories build
    from the snapshot and BackendUnavailable is wrapped, never
    hidden. Playback must be explicit — there is no default sink.
    """
    if playback is None:
        raise LiveVoiceError(
            "live voice needs an explicit playback sink; "
            "no device is ever defaulted silently"
        )
    try:
        tts_backend = tts if tts is not None else build_tts_backend(settings.tts_backend)
    except BackendUnavailable as exc:
        raise LiveVoiceError(str(exc)) from exc
    try:
        stt_backend = stt if stt is not None else build_stt_backend(settings.stt_backend)
    except BackendUnavailable as exc:
        raise LiveVoiceError(str(exc)) from exc
    seg = segmenter if segmenter is not None else VadSegmenter(EnergyVadModel())
    voice = VoiceInfo(
        voice_id=settings.voice_id,
        language=settings.language,
        backend_key=settings.tts_backend,
        prompt_text=(
            DEFAULT_VOICE.prompt_text if settings.voice_id == DEFAULT_VOICE.voice_id else ""
        ),
    )
    ledger = PlaybackLedger()
    orchestrator = VoiceOrchestrator(
        segmenter=seg,
        stt=stt_backend,
        responder=responder if responder is not None else unavailable_responder,
        tts=tts_backend,
        voice=voice,
        playback=playback,
        clock=clock or time.monotonic,
        on_chunk_started=ledger.chunk_started,
        on_chunk_finished=ledger.chunk_finished,
        frame_hook=ledger.chunk_progress,
    )
    wiring = LiveWiring(
        tts_backend=_backend_key(tts_backend, settings.tts_backend),
        stt_backend=_backend_key(stt_backend, settings.stt_backend),
        road_tts=_road(_backend_key(tts_backend, settings.tts_backend)),
        road_stt=_road(_backend_key(stt_backend, settings.stt_backend)),
        vad_model=str(getattr(seg.model, "model_key", type(seg.model).__name__)),
        responder="unavailable" if responder is None else "injected",
        voice_id=settings.voice_id,
        language=settings.language,
    )
    return orchestrator, ledger, wiring


@dataclass
class _LiveHost:
    session: object
    store: object | None
    orchestrator: VoiceOrchestrator
    ledger: PlaybackLedger
    wiring: LiveWiring
    persisted: int = 0  # orchestrator turns already recorded on the session


class LiveVoiceController:
    """Owns the live orchestrators of one app process.

    Factories supply the process defaults; per-call seams
    override. Defaults are the honest ones: responder
    unavailable, no playback factory (start refuses plainly
    until a host supplies playback), energy-model segmenter.
    """

    def __init__(
        self,
        *,
        responder: Responder | None = None,
        playback_factory: Callable | None = None,
        segmenter_factory: Callable | None = None,
        clock: Callable[[], float] | None = None,
    ):
        self._responder = responder
        self.playback_factory = playback_factory
        self._segmenter_factory = segmenter_factory
        self._clock = clock
        self._hosts: dict[str, _LiveHost] = {}
        self._app = None

    # ------------------------------------------------------------ app

    def attach_app(self, app) -> None:
        """Bind the app so start/stop publish the live orchestrator
        to app.state.voice_session — the slot the founding
        /voice/status route has always read."""
        self._app = app

    def is_live(self, session_id: str) -> bool:
        return session_id in self._hosts

    def live_session_ids(self) -> list[str]:
        return sorted(self._hosts)

    # ---------------------------------------------------------- status

    def status(self, session_id: str | None = None):
        if session_id is not None:
            host = self._hosts.get(session_id)
            if host is None:
                return {
                    "session_id": session_id,
                    "chat_id": None,
                    "live": False,
                    "state": None,
                    "wiring": None,
                    "turns_live": 0,
                    "turns_recorded": 0,
                }
            return {
                "session_id": session_id,
                "chat_id": host.session.chat_id,
                "live": True,
                "state": host.orchestrator.state.value,
                "wiring": host.wiring.to_dict(),
                "turns_live": len(host.orchestrator.turns),
                "turns_recorded": len(host.session.turns),
            }
        return {"sessions": [self.status(sid) for sid in self.live_session_ids()]}

    # ----------------------------------------------------------- start

    def start(
        self,
        session,
        *,
        store=None,
        responder: Responder | None = None,
        playback=None,
        playback_factory: Callable | None = None,
        segmenter=None,
        tts=None,
        stt=None,
    ) -> dict:
        if not session.active:
            raise LiveVoiceError(
                f"session {session.session_id} is stopped; its turns are history"
            )
        if session.session_id in self._hosts:
            raise LiveVoiceError(f"session {session.session_id} is already live")
        factory = playback_factory or self.playback_factory
        sink = playback if playback is not None else (factory(session) if factory else None)
        seg = segmenter
        if seg is None and self._segmenter_factory is not None:
            seg = self._segmenter_factory()
        orchestrator, ledger, wiring = build_live_orchestrator(
            session.settings,
            responder=responder if responder is not None else self._responder,
            tts=tts,
            stt=stt,
            playback=sink,
            segmenter=seg,
            clock=self._clock,
        )
        self._hosts[session.session_id] = _LiveHost(
            session=session, store=store, orchestrator=orchestrator,
            ledger=ledger, wiring=wiring,
        )
        if self._app is not None:
            self._app.state.voice_session = orchestrator
        return self.status(session.session_id)

    # --------------------------------------------------------- persist

    def _drop(self, host: _LiveHost) -> None:
        self._hosts.pop(host.session.session_id, None)
        if self._app is not None and getattr(self._app.state, "voice_session", None) is host.orchestrator:
            self._app.state.voice_session = None

    def _persist_new_turns(self, host: _LiveHost) -> list[dict]:
        out: list[dict] = []
        turns = host.orchestrator.turns
        while host.persisted < len(turns):
            record = turns[host.persisted]
            heard = host.ledger.heard_text(record.turn_id, record.response_text)
            try:
                turn = host.session.append_orchestrator_turn(record, heard)
            except Exception as exc:
                # The citizen's road refused (stopped session):
                # a stopped session cannot stay live.
                self._drop(host)
                raise LiveVoiceError(str(exc)) from exc
            host.persisted += 1
            if host.store is not None:
                host.store.save_session(host.session)
            if hasattr(turn, "to_dict"):
                out.append(turn.to_dict())
            else:
                out.append(
                    {
                        "turn_no": host.persisted,
                        "response_text": record.response_text,
                        "heard_certain": heard.certain_text,
                        "heard_uncertain": heard.uncertain_text,
                        "heard_unplayed": heard.unplayed_text,
                    }
                )
        return out

    # ------------------------------------------------------------ roads

    def _host(self, session_id: str) -> _LiveHost:
        host = self._hosts.get(session_id)
        if host is None:
            raise LiveVoiceError(f"session {session_id} is not live")
        return host

    def speak(self, session_id: str, text: str) -> dict:
        host = self._host(session_id)
        if not str(text or "").strip():
            raise LiveVoiceError("speak text must not be empty")
        host.orchestrator.speak_text(text)
        recorded = self._persist_new_turns(host)
        return recorded[-1] if recorded else {}

    def feed_frames(self, session_id: str, frames) -> list[dict]:
        host = self._host(session_id)
        host.orchestrator.feed_frames(frames)
        return self._persist_new_turns(host)

    def interrupt(self, session_id: str) -> bool:
        return self._host(session_id).orchestrator.interrupt()

    def stop(self, session_id: str, *, note: str = "") -> dict:
        host = self._host(session_id)
        final = self.status(session_id)
        if host.store is not None:
            if host.session.active:
                host.session.stop(note)
            host.store.save_session(host.session)
            final["turns_recorded"] = len(host.session.turns)
        self._drop(host)
        final["live"] = False
        return final
