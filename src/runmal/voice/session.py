"""Voice sessions (P-101, Part VII opener — DERIVED scope).

The roadmap gives Part VII one line only ("Voice, the Voxta Way",
P-101..P-116); this slice's scope is derived from the in-tree
census/architecture/founding record — see the P-101 slice doc.
What the derivation found missing, and what lands here:

- the voice session as a first-class citizen OF A CHAT: until
  now the orchestrator was a bare process object and the only
  "session" the HTTP surface knew was one global app.state slot;
- per-chat voice settings resolved ONCE, as one honest record:
  the character's voice (S512 equipment) over the user's backend
  defaults (voice/settings.py), with provider truth as data
  (P-053 discipline: known / verified / admission class /
  selected-via, imported from the registries, never copied);
- turns that PERSIST with the chat binding: P-065 recorded that
  orchestrator turns are ephemeral TurnRecords, never persisted,
  and P-091's citizens keep voice state in memory only. A
  session's completed turns are recorded here — through the
  S508 playback-truth discipline — and stored durably.

Storage follows the voice house pattern (settings.py, routing.py
S513): a versioned JSON document in the data dir
(``voice_sessions.json``), tolerant load — a corrupt store reads
as empty and never bricks the voice surface. NO migration.

Truth discipline:
- an unknown TTS backend in a character voice falls back whole
  to the defaults (S512 law: never an error, never resurrect a
  removed engine) and the fallback is NAMED in the truth record;
- a turn with no playback-ledger evidence claims NOTHING as
  certainly heard: without evidence the response is uncertain
  (some chunks played) or unplayed (none did) — INV-020.
- a turn's STT word confidences persist verbatim (P-105,
  VX-11): the backend's own per-word probability estimates,
  never recomputed; a turn recorded without them carries NO
  confidence evidence, a fact the mishearing views report
  as such — never as "all words confident".
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from runmal.voice.backends import TTS_REGISTRY
from runmal.voice.ledger import HeardReconstruction
from runmal.voice.orchestrator import TurnRecord
from runmal.voice.profiles import DEFAULT_VOICE, CharacterVoice
from runmal.voice.settings import VoiceSettings
from runmal.voice.stt_backends import DEFAULT_STT_BACKEND, STT_REGISTRY

SESSIONS_VERSION = 1
SESSIONS_FILENAME = "voice_sessions.json"

STATE_ACTIVE = "active"
STATE_STOPPED = "stopped"


class VoiceSessionError(ValueError):
    """A session operation the session's state forbids."""


def sessions_path(data_dir: Path | None = None) -> Path:
    base = data_dir or Path(os.environ.get("RUNMAL_DATA_DIR", ".runmal-data"))
    return base / SESSIONS_FILENAME


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


# ------------------------------------------------------------ truth


@dataclass(frozen=True)
class ProviderTruth:
    """One provider choice, as data (P-053 discipline)."""

    kind: str  # "tts" | "stt"
    backend: str
    known: bool
    verified: bool
    admission: str  # "default-shipped" | "user-installed" | "unknown"
    selected_via: str  # "character" | "default" | "fallback"
    note: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "backend": self.backend,
            "known": self.known,
            "verified": self.verified,
            "admission": self.admission,
            "selected_via": self.selected_via,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ProviderTruth:
        return cls(
            kind=str(data.get("kind", "")),
            backend=str(data.get("backend", "")),
            known=bool(data.get("known", False)),
            verified=bool(data.get("verified", False)),
            admission=str(data.get("admission", "unknown")),
            selected_via=str(data.get("selected_via", "default")),
            note=str(data.get("note", "")),
        )


def _truth(kind: str, backend: str, selected_via: str, note: str = "") -> ProviderTruth:
    registry = TTS_REGISTRY if kind == "tts" else STT_REGISTRY
    spec = registry.get(backend)
    if spec is None:
        return ProviderTruth(kind, backend, False, False, "unknown", selected_via, note)
    return ProviderTruth(
        kind=kind,
        backend=backend,
        known=True,
        verified=bool(spec.verified),
        admission="default-shipped" if spec.default_shipped else "user-installed",
        selected_via=selected_via,
        note=note,
    )


# --------------------------------------------------------- settings


@dataclass(frozen=True)
class SessionSettings:
    """The resolved voice of one session, snapshotted at start."""

    tts_backend: str
    stt_backend: str
    voice_id: str
    language: str
    tts_truth: ProviderTruth
    stt_truth: ProviderTruth

    def to_dict(self) -> dict:
        return {
            "tts_backend": self.tts_backend,
            "stt_backend": self.stt_backend,
            "voice_id": self.voice_id,
            "language": self.language,
            "tts_truth": self.tts_truth.to_dict(),
            "stt_truth": self.stt_truth.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> SessionSettings:
        return cls(
            tts_backend=str(data.get("tts_backend", "")),
            stt_backend=str(data.get("stt_backend", "")),
            voice_id=str(data.get("voice_id", "")),
            language=str(data.get("language", "")),
            tts_truth=ProviderTruth.from_dict(data.get("tts_truth") or {}),
            stt_truth=ProviderTruth.from_dict(data.get("stt_truth") or {}),
        )


def resolve_session_settings(
    *, defaults: VoiceSettings, character: CharacterVoice | None
) -> SessionSettings:
    """Resolve one session's voice, honestly (design section 2.2).

    Character equipment wins for TTS (VX-04 / S512); the ear is
    the user's default. An unknown backend falls back whole to
    the defaults and the truth record NAMES the fallback — it
    never raises and never resurrects a removed engine.
    """
    if character is not None and character.tts_backend in TTS_REGISTRY:
        tts_backend = character.tts_backend
        voice_id = character.voice_id or DEFAULT_VOICE.voice_id
        language = character.language or DEFAULT_VOICE.language
        tts_truth = _truth("tts", tts_backend, "character")
    elif character is not None:
        tts_backend = defaults.tts_backend
        voice_id = DEFAULT_VOICE.voice_id
        language = DEFAULT_VOICE.language
        tts_truth = _truth(
            "tts",
            tts_backend,
            "fallback",
            note=(
                f"character voice backend {character.tts_backend!r} is not a "
                "registered TTS backend; fell back to the default voice"
            ),
        )
    else:
        tts_backend = defaults.tts_backend
        voice_id = DEFAULT_VOICE.voice_id
        language = DEFAULT_VOICE.language
        tts_truth = _truth("tts", tts_backend, "default")
    if defaults.stt_backend in STT_REGISTRY:
        stt_backend = defaults.stt_backend
        stt_truth = _truth("stt", stt_backend, "default")
    else:
        stt_backend = DEFAULT_STT_BACKEND
        stt_truth = _truth(
            "stt",
            stt_backend,
            "fallback",
            note=(
                f"stored STT backend {defaults.stt_backend!r} is not a "
                "registered STT backend; fell back to the default ear"
            ),
        )
    return SessionSettings(
        tts_backend=tts_backend,
        stt_backend=stt_backend,
        voice_id=voice_id,
        language=language,
        tts_truth=tts_truth,
        stt_truth=stt_truth,
    )


# ------------------------------------------------------------ turns


@dataclass(frozen=True)
class WordConfidence:
    """One transcribed word and the STT backend's own
    probability estimate for it (P-105, VX-11), persisted
    verbatim on the turn record. The estimate is the
    backend's, never recomputed or upgraded here; a
    probability outside [0, 1] is not an estimate and is
    refused at the door."""

    text: str
    probability: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= float(self.probability) <= 1.0:
            raise ValueError(
                f"word probability outside [0, 1]: {self.probability!r}")

    def to_dict(self) -> dict:
        return {"text": self.text, "probability": self.probability}

    @classmethod
    def from_dict(cls, data: dict) -> WordConfidence:
        return cls(
            text=str(data.get("text", "")),
            probability=float(data.get("probability", 1.0)),
        )


@dataclass
class VoiceTurnRecord:
    """One completed voice turn, persisted with its session.

    The heard-* fields are the S508 truth split: only
    ``heard_certain`` may ever be claimed as heard.
    """

    turn_no: int
    transcript_text: str = ""
    transcript_language: str = ""
    stt_backend: str = ""
    response_text: str = ""
    heard_certain: str = ""
    heard_uncertain: str = ""
    heard_unplayed: str = ""
    interrupted: bool = False
    error: str = ""
    chunks_total: int = 0
    chunks_played: int = 0
    recorded_at: str = ""
    # Word-confidence evidence (P-105, VX-11): the STT
    # backend's own per-word probability estimates, verbatim.
    # Empty means NO evidence was recorded — not certainty.
    transcript_words: tuple[WordConfidence, ...] = ()
    # Projection state (P-103): the chat-message shadow of this
    # turn. ``projected`` means projection has fully considered
    # the turn; the per-side ids make a half-projected turn
    # resumable without duplicating the side that landed.
    projected: bool = False
    projected_user_message_id: str = ""
    projected_assistant_message_id: str = ""
    projected_at: str = ""

    @classmethod
    def from_orchestrator(
        cls,
        record: TurnRecord,
        heard: HeardReconstruction | None,
        *,
        turn_no: int,
        stt_backend: str,
        recorded_at: str,
    ) -> VoiceTurnRecord:
        """Convert an ephemeral orchestrator TurnRecord (P-065's
        carried limitation) into the persisted form. Without
        ledger evidence NOTHING is claimed certain (INV-020)."""
        transcript = record.transcript
        if heard is not None:
            certain, uncertain, unplayed = (
                heard.certain_text,
                heard.uncertain_text,
                heard.unplayed_text,
            )
        elif record.chunks_played > 0:
            certain, uncertain, unplayed = "", record.response_text, ""
        else:
            certain, uncertain, unplayed = "", "", record.response_text
        return cls(
            turn_no=turn_no,
            transcript_text=transcript.text if transcript else "",
            transcript_language=transcript.language if transcript else "",
            transcript_words=tuple(
                WordConfidence(w.text, float(w.probability))
                for w in (transcript.words if transcript else ())
            ),
            stt_backend=stt_backend,
            response_text=record.response_text,
            heard_certain=certain,
            heard_uncertain=uncertain,
            heard_unplayed=unplayed,
            interrupted=record.interrupted,
            error=record.error,
            chunks_total=record.chunks_total,
            chunks_played=record.chunks_played,
            recorded_at=recorded_at,
        )

    def history_text(self) -> str:
        """The text a chat history may store for this turn (S508)."""
        return HeardReconstruction(
            self.heard_certain, self.heard_uncertain, self.heard_unplayed
        ).history_text()

    def to_dict(self) -> dict:
        return {
            "turn_no": self.turn_no,
            "transcript_text": self.transcript_text,
            "transcript_language": self.transcript_language,
            "stt_backend": self.stt_backend,
            "response_text": self.response_text,
            "heard_certain": self.heard_certain,
            "heard_uncertain": self.heard_uncertain,
            "heard_unplayed": self.heard_unplayed,
            "interrupted": self.interrupted,
            "error": self.error,
            "chunks_total": self.chunks_total,
            "chunks_played": self.chunks_played,
            "recorded_at": self.recorded_at,
            "transcript_words": [w.to_dict() for w in self.transcript_words],
            "projected": self.projected,
            "projected_user_message_id": self.projected_user_message_id,
            "projected_assistant_message_id": self.projected_assistant_message_id,
            "projected_at": self.projected_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> VoiceTurnRecord:
        return cls(
            turn_no=int(data.get("turn_no", 0)),
            transcript_text=str(data.get("transcript_text", "")),
            transcript_language=str(data.get("transcript_language", "")),
            stt_backend=str(data.get("stt_backend", "")),
            response_text=str(data.get("response_text", "")),
            heard_certain=str(data.get("heard_certain", "")),
            heard_uncertain=str(data.get("heard_uncertain", "")),
            heard_unplayed=str(data.get("heard_unplayed", "")),
            interrupted=bool(data.get("interrupted", False)),
            error=str(data.get("error", "")),
            chunks_total=int(data.get("chunks_total", 0)),
            chunks_played=int(data.get("chunks_played", 0)),
            recorded_at=str(data.get("recorded_at", "")),
            transcript_words=tuple(
                WordConfidence.from_dict(w)
                for w in data.get("transcript_words") or []
                if isinstance(w, dict)
            ),
            projected=bool(data.get("projected", False)),
            projected_user_message_id=str(data.get("projected_user_message_id", "")),
            projected_assistant_message_id=str(
                data.get("projected_assistant_message_id", "")),
            projected_at=str(data.get("projected_at", "")),
        )


# ---------------------------------------------------------- session


@dataclass
class VoiceSession:
    """A voice session bound to one chat (the P-101 citizen)."""

    session_id: str
    chat_id: str
    user_id: str
    character_id: str | None
    settings: SessionSettings
    created_at: str
    state: str = STATE_ACTIVE
    stopped_at: str = ""
    stop_note: str = ""
    turns: list[VoiceTurnRecord] = field(default_factory=list)
    # Auto-projection opt-in (P-104): when True, the async host
    # roads project this session's turns into its chat as they
    # are recorded (P-103's service, called by the host). Default
    # False — projection stays explicit, exactly as P-103 left it.
    auto_project: bool = False

    @property
    def active(self) -> bool:
        return self.state == STATE_ACTIVE

    def stop(self, note: str = "", *, at: str = "") -> None:
        """First stop wins: a stopped session is history."""
        if not self.active:
            return
        self.state = STATE_STOPPED
        self.stopped_at = at or _now_iso()
        self.stop_note = note

    def record_turn(
        self,
        *,
        transcript_text: str = "",
        transcript_language: str = "",
        response_text: str = "",
        heard_certain: str = "",
        heard_uncertain: str = "",
        heard_unplayed: str = "",
        interrupted: bool = False,
        error: str = "",
        chunks_total: int = 0,
        chunks_played: int = 0,
        transcript_words: tuple[WordConfidence, ...] = (),
        recorded_at: str = "",
    ) -> VoiceTurnRecord:
        if not self.active:
            raise VoiceSessionError(
                f"session {self.session_id} is stopped; its turns are history"
            )
        if chunks_total < 0 or chunks_played < 0:
            raise VoiceSessionError("chunk counts must not be negative")
        if chunks_played > chunks_total:
            raise VoiceSessionError("chunks_played exceeds chunks_total")
        turn = VoiceTurnRecord(
            turn_no=len(self.turns) + 1,
            transcript_text=transcript_text,
            transcript_language=transcript_language,
            stt_backend=self.settings.stt_backend,
            response_text=response_text,
            heard_certain=heard_certain,
            heard_uncertain=heard_uncertain,
            heard_unplayed=heard_unplayed,
            interrupted=interrupted,
            error=error,
            chunks_total=chunks_total,
            chunks_played=chunks_played,
            transcript_words=tuple(transcript_words),
            recorded_at=recorded_at or _now_iso(),
        )
        self.turns.append(turn)
        return turn

    def append_orchestrator_turn(
        self,
        record: TurnRecord,
        heard: HeardReconstruction | None,
        *,
        recorded_at: str = "",
    ) -> VoiceTurnRecord:
        """Record a finished orchestrator turn (the live-host road)."""
        if not self.active:
            raise VoiceSessionError(
                f"session {self.session_id} is stopped; its turns are history"
            )
        turn = VoiceTurnRecord.from_orchestrator(
            record,
            heard,
            turn_no=len(self.turns) + 1,
            stt_backend=self.settings.stt_backend,
            recorded_at=recorded_at or _now_iso(),
        )
        self.turns.append(turn)
        return turn

    def summary_dict(self) -> dict:
        return {
            "session_id": self.session_id,
            "chat_id": self.chat_id,
            "user_id": self.user_id,
            "character_id": self.character_id,
            "state": self.state,
            "created_at": self.created_at,
            "stopped_at": self.stopped_at,
            "stop_note": self.stop_note,
            "turn_count": len(self.turns),
            "auto_project": bool(self.auto_project),
            "settings": self.settings.to_dict(),
        }

    def to_dict(self) -> dict:
        data = self.summary_dict()
        data["turns"] = [t.to_dict() for t in self.turns]
        return data

    @classmethod
    def from_dict(cls, data: dict) -> VoiceSession:
        return cls(
            session_id=str(data["session_id"]),
            chat_id=str(data["chat_id"]),
            user_id=str(data.get("user_id", "")),
            character_id=(str(data["character_id"]) if data.get("character_id") else None),
            settings=SessionSettings.from_dict(data.get("settings") or {}),
            created_at=str(data.get("created_at", "")),
            state=str(data.get("state", STATE_STOPPED)),
            stopped_at=str(data.get("stopped_at", "")),
            stop_note=str(data.get("stop_note", "")),
            turns=[VoiceTurnRecord.from_dict(t) for t in data.get("turns") or []],
            auto_project=bool(data.get("auto_project", False)),
        )


# ------------------------------------------------------------ store


class VoiceSessionStore:
    """Durable session store: voice_sessions.json (house pattern).

    Every mutation rewrites the whole versioned document. Load is
    tolerant: a missing file is an empty store; a corrupt or
    wrong-shaped document reads as empty; a malformed session
    entry is skipped — the store never bricks the voice surface.
    """

    def __init__(self, path: Path | None = None):
        self.path = path or sessions_path()
        self._sessions: dict[str, VoiceSession] = {}
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            doc = json.loads(self.path.read_text())
            entries = doc.get("sessions") if isinstance(doc, dict) else None
            if not isinstance(entries, list):
                return
            for entry in entries:
                try:
                    session = VoiceSession.from_dict(entry)
                except (KeyError, TypeError, ValueError):
                    continue  # one bad entry never sinks the store
                self._sessions[session.session_id] = session
        except (ValueError, TypeError, OSError):
            self._sessions = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        doc = {
            "version": SESSIONS_VERSION,
            "sessions": [
                s.to_dict()
                for s in sorted(
                    self._sessions.values(), key=lambda s: (s.created_at, s.session_id)
                )
            ],
        }
        self.path.write_text(json.dumps(doc, indent=2, sort_keys=True))

    # ---------------------------------------------------------- reads

    def get(self, session_id: str) -> VoiceSession | None:
        return self._sessions.get(session_id)

    def all_sessions(self) -> list[VoiceSession]:
        return sorted(
            self._sessions.values(),
            key=lambda s: (s.created_at, s.session_id),
            reverse=True,
        )

    def list_for_chat(self, chat_id: str) -> list[VoiceSession]:
        return [s for s in self.all_sessions() if s.chat_id == chat_id]

    def active_for_chat(self, chat_id: str) -> VoiceSession | None:
        for session in self.list_for_chat(chat_id):
            if session.active:
                return session
        return None

    # --------------------------------------------------------- writes

    def save_session(self, session: VoiceSession) -> VoiceSession:
        self._sessions[session.session_id] = session
        self.save()
        return session

    def drop_chat(self, chat_id: str) -> int:
        """chat.deleted housekeeping: remove a chat's sessions."""
        doomed = [sid for sid, s in self._sessions.items() if s.chat_id == chat_id]
        for sid in doomed:
            del self._sessions[sid]
        if doomed:
            self.save()
        return len(doomed)


def start_session(
    store: VoiceSessionStore,
    *,
    chat_id: str,
    user_id: str,
    character_id: str | None,
    settings: SessionSettings,
    now: str = "",
    auto_project: bool = False,
) -> VoiceSession:
    """Start a chat's voice session. One active session per chat:
    an existing active session is stopped as superseded first —
    never silently stacked, so "this chat's voice session" always
    has exactly one answer."""
    stamp = now or _now_iso()
    existing = store.active_for_chat(chat_id)
    if existing is not None:
        existing.stop("superseded", at=stamp)
        store.save_session(existing)
    session = VoiceSession(
        session_id=str(uuid.uuid4()),
        chat_id=chat_id,
        user_id=user_id,
        character_id=character_id,
        settings=settings,
        created_at=stamp,
        auto_project=bool(auto_project),
    )
    return store.save_session(session)
