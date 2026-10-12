"""Latency metrics (S510): monotonic per-stage metrics, p50/p95 report.

VOICE_ARCHITECTURE §10 stage list, in pipeline order:

VAD_SPEECH_ON → ENDPOINT → STT_FINAL → LLM_FIRST_TOKEN →
FIRST_SYNTH_CHUNK → TTS_FIRST_AUDIO → PLAYBACK_START → PLAYBACK_END,
with the interruption pair INTERRUPTION_DETECTED → PLAYBACK_STOPPED
recorded on interrupted turns.

Acceptance: every complete turn produces a coherent timing chain — all
required stages present, timestamps monotonic non-decreasing ALONG THE
PIPELINE ORDER (a later stage may never carry an earlier timestamp: no
negative or impossible stage durations), and derived durations are
computed from the chain, never stored separately where they could
disagree. Clocks are monotonic (``time.monotonic`` in production, an
injected deterministic clock in tests).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum


class Stage(StrEnum):
    VAD_SPEECH_ON = "vad_speech_on"
    ENDPOINT = "endpoint"
    STT_FINAL = "stt_final"
    LLM_FIRST_TOKEN = "llm_first_token"
    FIRST_SYNTH_CHUNK = "first_synth_chunk"
    TTS_FIRST_AUDIO = "tts_first_audio"
    PLAYBACK_START = "playback_start"
    PLAYBACK_END = "playback_end"
    INTERRUPTION_DETECTED = "interruption_detected"
    PLAYBACK_STOPPED = "playback_stopped"


#: Required stages for a complete (non-interrupted) turn, in order.
TURN_CHAIN: tuple[Stage, ...] = (
    Stage.VAD_SPEECH_ON, Stage.ENDPOINT, Stage.STT_FINAL,
    Stage.LLM_FIRST_TOKEN, Stage.FIRST_SYNTH_CHUNK, Stage.TTS_FIRST_AUDIO,
    Stage.PLAYBACK_START, Stage.PLAYBACK_END,
)

#: Derived durations: name -> (start stage, end stage).
DERIVED = {
    "endpointing": (Stage.VAD_SPEECH_ON, Stage.ENDPOINT),
    "stt": (Stage.ENDPOINT, Stage.STT_FINAL),
    "llm_ttft": (Stage.STT_FINAL, Stage.LLM_FIRST_TOKEN),
    "synth_to_first_audio": (Stage.FIRST_SYNTH_CHUNK, Stage.TTS_FIRST_AUDIO),
    "end_to_end_first_audio": (Stage.ENDPOINT, Stage.PLAYBACK_START),
    "playback": (Stage.PLAYBACK_START, Stage.PLAYBACK_END),
    "interruption_stop": (Stage.INTERRUPTION_DETECTED, Stage.PLAYBACK_STOPPED),
}


@dataclass
class TurnTiming:
    """One turn's stage timestamps (monotonic seconds)."""

    turn_id: int
    stages: dict[Stage, float] = field(default_factory=dict)

    def record(self, stage: Stage, at: float) -> None:
        self.stages[stage] = at

    def validate(self, *, require_complete: bool = True) -> list[str]:
        """Coherence violations: missing stages, impossible ordering."""
        problems: list[str] = []
        chain = [s for s in TURN_CHAIN if s in self.stages]
        if require_complete:
            for stage in TURN_CHAIN:
                if stage not in self.stages:
                    problems.append(f"missing stage: {stage.value}")
        for earlier, later in zip(chain, chain[1:], strict=False):
            if self.stages[later] < self.stages[earlier]:
                problems.append(
                    f"impossible ordering: {later.value} ({self.stages[later]:.4f}) "
                    f"< {earlier.value} ({self.stages[earlier]:.4f})")
        if Stage.INTERRUPTION_DETECTED in self.stages:
            detected = self.stages[Stage.INTERRUPTION_DETECTED]
            if Stage.PLAYBACK_STOPPED not in self.stages:
                problems.append("interruption without playback_stopped")
            elif self.stages[Stage.PLAYBACK_STOPPED] < detected:
                problems.append("playback stopped before interruption detected")
            if (Stage.PLAYBACK_START in self.stages
                    and detected < self.stages[Stage.PLAYBACK_START]):
                problems.append("interruption detected before playback started")
        return problems

    def duration(self, name: str) -> float | None:
        start, end = DERIVED[name]
        if start in self.stages and end in self.stages:
            return self.stages[end] - self.stages[start]
        return None


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile; deterministic, no interpolation tricks."""
    if not values:
        raise ValueError("percentile of empty series")
    ordered = sorted(values)
    rank = max(1, int(round(pct / 100 * len(ordered))))
    return ordered[min(rank, len(ordered)) - 1]


@dataclass
class LatencyReport:
    turns: int
    series: dict[str, dict[str, float]]  # metric -> {p50, p95, n}
    violations: list[str]

    def to_dict(self) -> dict:
        return {"turns": self.turns, "series": self.series,
                "violations": self.violations}


class MetricsCollector:
    """Collects TurnTimings and renders the p50/p95 report."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._turns: dict[int, TurnTiming] = {}

    def begin_turn(self, turn_id: int) -> TurnTiming:
        timing = TurnTiming(turn_id)
        self._turns[turn_id] = timing
        return timing

    def record(self, turn_id: int, stage: Stage) -> None:
        timing = self._turns.setdefault(turn_id, TurnTiming(turn_id))
        timing.record(stage, self._clock())

    def turn(self, turn_id: int) -> TurnTiming:
        return self._turns[turn_id]

    def report(self) -> LatencyReport:
        violations: list[str] = []
        per_metric: dict[str, list[float]] = {}
        for timing in self._turns.values():
            violations.extend(
                f"turn {timing.turn_id}: {p}" for p in timing.validate())
            for name in DERIVED:
                value = timing.duration(name)
                if value is not None:
                    per_metric.setdefault(name, []).append(value)
        series = {
            name: {"p50": percentile(values, 50), "p95": percentile(values, 95),
                   "n": len(values)}
            for name, values in sorted(per_metric.items())
        }
        return LatencyReport(turns=len(self._turns), series=series,
                             violations=violations)
