"""Per-turn voice latency evidence (P-110, Part VII).

VOICE_ARCHITECTURE section 2 logs every orchestrator state
transition with a monotonic timestamp "for latency
measurement", and section 10 names the metrics to record
with p50/p95 reporting. Until this slice nothing consumed
that log: the S510 MetricsCollector behind the founding
/voice/status was never fed, and the persisted session turn
(P-101) carried no timing at all, so a session's latency
evidence died with the process.

This module derives per-turn durations ONLY from the
orchestrator's own clock-stamped transitions for that turn
and shapes the persisted evidence into views:

- ``stt_seconds`` — FINALIZING_STT -> THINKING;
- ``response_seconds`` — THINKING -> SYNTHESIZING (the whole
  responder call as stamped; generation duration, NOT a
  time-to-first-token — the first token is never stamped
  and is never claimed);
- ``synth_to_first_audio_seconds`` — SYNTHESIZING -> SPEAKING;
- ``playback_seconds`` — SPEAKING -> the turn's closing
  transition (LISTENING, or INTERRUPTING where stamped);
- ``turn_seconds`` — the turn's first -> last stamped
  transition.

A duration appears only when BOTH endpoints were stamped
for that turn; a negative span (impossible under a
monotonic clock) is dropped, never clamped. Stages the
transition log cannot prove — VAD speech-on, endpoint
hangover, LLM first-token, interruption detection->stop —
are not recorded here and are named unclaimed in the slice
doc. Speak turns (P-102) honestly yield only the stages
they took; manually recorded turns yield none and say so.
"""

from __future__ import annotations

from runmal.voice.metrics import percentile
from runmal.voice.orchestrator import Transition, VoiceState

#: The only duration keys this slice ever claims, in order.
DURATION_KEYS: tuple[str, ...] = (
    "stt_seconds",
    "response_seconds",
    "synth_to_first_audio_seconds",
    "playback_seconds",
    "turn_seconds",
)

#: Where a turn's durations came from (None when none exist).
SOURCE_ORCHESTRATOR = "orchestrator_transitions"


def _span(start: float | None, end: float | None) -> float | None:
    if start is None or end is None:
        return None
    value = end - start
    return value if value >= 0 else None


def turn_durations(transitions, turn_id: int) -> dict[str, float]:
    """Derive one turn's durations from the transition log.

    Only transitions stamped with ``turn_id`` are evidence
    for the turn. Repeated entries into a state keep the
    FIRST stamp (the stage began when it was first entered).
    """
    stamps: list[Transition] = [t for t in transitions if t.turn_id == turn_id]
    if not stamps:
        return {}
    first_at: dict[VoiceState, float] = {}
    for t in stamps:
        first_at.setdefault(t.to_state, t.at)
    out: dict[str, float] = {}
    stt = _span(first_at.get(VoiceState.FINALIZING), first_at.get(VoiceState.THINKING))
    if stt is not None:
        out["stt_seconds"] = stt
    response = _span(
        first_at.get(VoiceState.THINKING), first_at.get(VoiceState.SYNTHESIZING)
    )
    if response is not None:
        out["response_seconds"] = response
    synth = _span(
        first_at.get(VoiceState.SYNTHESIZING), first_at.get(VoiceState.SPEAKING)
    )
    if synth is not None:
        out["synth_to_first_audio_seconds"] = synth
    speaking_at = first_at.get(VoiceState.SPEAKING)
    if speaking_at is not None:
        closing = None
        seen_speaking = False
        for t in stamps:
            if t.to_state is VoiceState.SPEAKING:
                seen_speaking = True
            elif seen_speaking and t.to_state in (
                VoiceState.LISTENING,
                VoiceState.INTERRUPTING,
            ):
                closing = t.at
                break
        playback = _span(speaking_at, closing)
        if playback is not None:
            out["playback_seconds"] = playback
    total = _span(stamps[0].at, stamps[-1].at)
    if total is not None:
        out["turn_seconds"] = total
    return {k: out[k] for k in DURATION_KEYS if k in out}


def clean_durations(data) -> dict[str, float]:
    """Tolerant read of a stored durations mapping (house law:
    a stored session never bricks). Only known keys with a
    finite number >= 0 survive; anything else is dropped."""
    if not isinstance(data, dict):
        return {}
    out: dict[str, float] = {}
    for key in DURATION_KEYS:
        value = data.get(key)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        value = float(value)
        if value >= 0 and value == value and value != float("inf"):
            out[key] = value
    return out


def turn_latency_view(turn) -> dict:
    """One persisted turn's latency evidence as surface data."""
    durations = clean_durations(getattr(turn, "durations", None) or {})
    return {
        "turn_no": turn.turn_no,
        "has_latency_evidence": bool(durations),
        "durations": durations,
        "source": SOURCE_ORCHESTRATOR if durations else None,
    }


def session_latency_view(session) -> dict:
    """A session's latency record: per-turn evidence plus the
    section-10 aggregate (count + p50/p95 per duration key,
    over exactly the turns that carry that duration)."""
    turns = [turn_latency_view(t) for t in session.turns]
    aggregate: dict[str, dict] = {}
    for key in DURATION_KEYS:
        series = [t["durations"][key] for t in turns if key in t["durations"]]
        if series:
            aggregate[key] = {
                "count": len(series),
                "p50": percentile(series, 50),
                "p95": percentile(series, 95),
            }
    return {
        "session_id": session.session_id,
        "chat_id": session.chat_id,
        "turn_count": len(turns),
        "turns_with_evidence": sum(1 for t in turns if t["has_latency_evidence"]),
        "turns": turns,
        "aggregate": aggregate,
    }
