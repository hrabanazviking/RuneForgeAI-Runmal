"""Playback truth ledger (S508) — VOICE_ARCHITECTURE §4, INV-020.

Generated text is NOT heard text. Every synthesized chunk gets a
playback record (turn, text span, frames, start/stop timestamps,
interrupted flag), and the heard-text reconstruction is CONSERVATIVE:

- a chunk that played to completion contributes its full span as
  CERTAIN;
- a chunk interrupted mid-play contributes certain words ONLY when
  word alignment exists and a word's end time is within the played
  duration; the straddling word and everything after it in that chunk
  are UNCERTAIN, never certain;
- without alignment, a partially played chunk contributes NOTHING as
  certain — its whole span is uncertain;
- chunks never started contribute nothing and are reported as unplayed.

So a known-unplayed suffix is never recorded as certainly heard, and
insufficient alignment is represented as uncertainty, not hidden.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from runmal.voice import SAMPLE_RATE
from runmal.voice.tts import AudioChunk


@dataclass
class ChunkPlaybackRecord:
    turn_id: int
    chunk_index: int
    text: str
    total_frames: int
    frames_played: int = 0
    started_at: float | None = None
    stopped_at: float | None = None
    completed: bool = False
    interrupted: bool = False
    word_timings: tuple[tuple[str, float, float], ...] = ()

    @property
    def played_s(self) -> float:
        return self.frames_played * 512 / SAMPLE_RATE

    @property
    def fraction_played(self) -> float:
        return self.frames_played / self.total_frames if self.total_frames else 0.0


@dataclass(frozen=True)
class HeardReconstruction:
    """What history may claim about one companion turn."""

    certain_text: str  # words proven played to their end
    uncertain_text: str  # possibly-heard span (partial chunk remainder)
    unplayed_text: str  # spans never started / after the interruption

    @property
    def is_fully_certain(self) -> bool:
        return not self.uncertain_text and not self.unplayed_text

    def history_text(self) -> str:
        """The text a chat history may store for this turn: certain text
        plus an explicit uncertainty marker when a partial chunk exists.
        Unplayed text is NEVER included."""
        if self.uncertain_text:
            return f"{self.certain_text} [uncertain: {self.uncertain_text}…]".strip()
        return self.certain_text


@dataclass
class _TurnLedger:
    records: list[ChunkPlaybackRecord] = field(default_factory=list)
    open_record: ChunkPlaybackRecord | None = None


class PlaybackLedger:
    """Subscribes to orchestrator chunk hooks (S505) or is driven
    directly by a PlaybackQueue-style player."""

    def __init__(self, clock: Callable[[], float] = time.monotonic):
        self._clock = clock
        self._turns: dict[int, _TurnLedger] = {}

    # ------------------------------------------------------------ driving

    def chunk_started(self, turn_id: int, chunk: AudioChunk) -> ChunkPlaybackRecord:
        turn = self._turns.setdefault(turn_id, _TurnLedger())
        total_frames = max(1, len(chunk.pcm) // (512 * 2))
        record = ChunkPlaybackRecord(
            turn_id=turn_id,
            chunk_index=chunk.index,
            text=chunk.text,
            total_frames=total_frames,
            started_at=self._clock(),
            word_timings=chunk.word_timings,
        )
        turn.records.append(record)
        turn.open_record = record
        return record

    def chunk_progress(self, turn_id: int, frames_played: int) -> None:
        turn = self._turns.get(turn_id)
        if turn and turn.open_record is not None:
            turn.open_record.frames_played = max(turn.open_record.frames_played, frames_played)

    def chunk_finished(self, turn_id: int, chunk: AudioChunk, frames_played: int) -> None:
        turn = self._turns.get(turn_id)
        if not turn:
            record = self.chunk_started(turn_id, chunk)
            turn = self._turns[turn_id]
            _ = record
        record = turn.open_record or self.chunk_started(turn_id, chunk)
        record.frames_played = frames_played
        record.stopped_at = self._clock()
        record.completed = frames_played >= record.total_frames
        record.interrupted = not record.completed
        turn.open_record = None

    def records(self, turn_id: int) -> list[ChunkPlaybackRecord]:
        turn = self._turns.get(turn_id)
        return list(turn.records) if turn else []

    def playback_spans(self) -> list[tuple[float, float | None]]:
        """(start, end) clock spans of every started chunk, all turns.

        ``end`` is None for a chunk still playing. Consumers that must
        avoid hearing the companion's own voice (room ingress, S611)
        test capture frames against these spans.
        """
        spans: list[tuple[float, float | None]] = []
        for turn in self._turns.values():
            for record in turn.records:
                if record.started_at is not None:
                    spans.append((record.started_at, record.stopped_at))
        return spans

    # ------------------------------------------------------- reconstruction

    def heard_text(self, turn_id: int, full_response_text: str = "") -> HeardReconstruction:
        turn = self._turns.get(turn_id)
        if turn is None:
            return HeardReconstruction("", "", full_response_text)
        certain: list[str] = []
        uncertain: list[str] = []
        played_indices: set[int] = set()
        for record in turn.records:
            played_indices.add(record.chunk_index)
            if record.completed:
                certain.append(record.text)
                continue
            # Partial chunk: alignment decides what (if anything) is certain.
            if record.word_timings:
                played_s = record.played_s
                certain_words = [w for (w, _s, e) in record.word_timings if e <= played_s]
                rest = [w for (w, _s, e) in record.word_timings if e > played_s]
                if certain_words:
                    certain.append(" ".join(certain_words))
                if rest:
                    uncertain.append(" ".join(rest))
            else:
                uncertain.append(record.text)
        unplayed: list[str] = []
        if full_response_text:
            from runmal.voice.tts import split_text_into_chunks

            pieces = split_text_into_chunks(full_response_text)
            by_index = {r.chunk_index: r for r in turn.records}
            for i, piece in enumerate(pieces):
                if i not in played_indices:
                    unplayed.append(piece)
                elif by_index[i].interrupted and not by_index[i].word_timings:
                    pass  # whole span already counted as uncertain
        return HeardReconstruction(
            certain_text=" ".join(certain).strip(),
            uncertain_text=" ".join(uncertain).strip(),
            unplayed_text=" ".join(unplayed).strip(),
        )
