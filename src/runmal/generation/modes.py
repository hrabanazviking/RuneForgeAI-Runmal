"""Generation mode state machine (S209): swipe / regenerate / impersonate.

Distinct modes with distinct commit semantics:

- NORMAL / SWIPE / REGENERATE produce *assistant* messages.
- IMPERSONATE produces a *user* message (the model writes as the user).

Candidates persist inside the session: swiping never destroys them and
regenerating appends a new candidate instead of replacing history.
Regeneration demands a stable prompt identity -- the caller recomposes the
prompt and the machine refuses if its fingerprint changed, so a regenerate
can never silently reuse a stale prompt. Sessions serialize to plain dicts
(``to_dict``/``from_dict``) so candidate state survives a round trip.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from enum import Enum


class Mode(Enum):
    NORMAL = "normal"
    SWIPE = "swipe"
    REGENERATE = "regenerate"
    IMPERSONATE = "impersonate"


#: Which chat role a committed candidate becomes, per mode.
TARGET_ROLE: dict[Mode, str] = {
    Mode.NORMAL: "assistant",
    Mode.SWIPE: "assistant",
    Mode.REGENERATE: "assistant",
    Mode.IMPERSONATE: "user",
}


class State(Enum):
    IDLE = "idle"
    PROMPT_READY = "prompt_ready"
    GENERATING = "generating"
    CANDIDATE_READY = "candidate_ready"
    COMMITTED = "committed"
    ABORTED = "aborted"


class InvalidTransitionError(Exception):
    """A state-machine transition that is not allowed from the current state."""


class PromptChangedError(Exception):
    """Regenerate was attempted with a different prompt than the original."""


def prompt_fingerprint(messages: list[dict]) -> str:
    """Stable identity of a composed prompt: sha256 of canonical JSON."""
    canonical = json.dumps(messages, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass
class Candidate:
    content: str
    mode: Mode
    sequence: int

    def to_dict(self) -> dict:
        return {"content": self.content, "mode": self.mode.value,
                "sequence": self.sequence}

    @classmethod
    def from_dict(cls, data: dict) -> "Candidate":
        return cls(content=data["content"], mode=Mode(data["mode"]),
                   sequence=data["sequence"])


@dataclass
class GenerationSession:
    """One message's generation lifecycle, across swipes and regenerates."""

    mode: Mode = Mode.NORMAL
    state: State = State.IDLE
    fingerprint: str | None = None
    candidates: list[Candidate] = field(default_factory=list)
    active_index: int = -1

    # -- transitions ------------------------------------------------------
    def compose(self, messages: list[dict]) -> str:
        """IDLE -> PROMPT_READY. Fixes the prompt identity for this session."""
        self._require(State.IDLE, "compose")
        self.fingerprint = prompt_fingerprint(messages)
        self.state = State.PROMPT_READY
        return self.fingerprint

    def begin(self) -> None:
        """PROMPT_READY -> GENERATING."""
        self._require(State.PROMPT_READY, "begin")
        self.state = State.GENERATING

    def complete(self, content: str) -> Candidate:
        """GENERATING -> CANDIDATE_READY; appends and activates a candidate."""
        self._require(State.GENERATING, "complete")
        candidate = Candidate(
            content=content, mode=self.mode, sequence=len(self.candidates)
        )
        self.candidates.append(candidate)
        self.active_index = len(self.candidates) - 1
        self.state = State.CANDIDATE_READY
        return candidate

    def regenerate(self, messages: list[dict]) -> None:
        """CANDIDATE_READY -> PROMPT_READY, same prompt identity required.

        The session keeps its origin mode (an impersonation stays an
        impersonation); regeneration is an action, not a mode change.
        """
        self._require(State.CANDIDATE_READY, "regenerate")
        if prompt_fingerprint(messages) != self.fingerprint:
            raise PromptChangedError(
                "regenerate requires the identical prompt; compose a fresh "
                "session for a changed prompt"
            )
        self.state = State.PROMPT_READY

    def swipe(self, delta: int) -> bool:
        """Move the active candidate by ``delta`` (clamped). True if moved."""
        self._require(State.CANDIDATE_READY, "swipe")
        if not self.candidates:
            return False
        target = self.active_index + delta
        target = max(0, min(target, len(self.candidates) - 1))
        moved = target != self.active_index
        self.active_index = target
        return moved

    def commit(self) -> tuple[str, str]:
        """CANDIDATE_READY -> COMMITTED; returns (role, content)."""
        self._require(State.CANDIDATE_READY, "commit")
        self.state = State.COMMITTED
        return TARGET_ROLE[self.active().mode], self.active().content

    def abort(self) -> None:
        """Any non-terminal state -> ABORTED."""
        if self.state in (State.COMMITTED, State.ABORTED):
            raise InvalidTransitionError(f"cannot abort from {self.state.value}")
        self.state = State.ABORTED

    # -- accessors --------------------------------------------------------
    def active(self) -> Candidate:
        if not (0 <= self.active_index < len(self.candidates)):
            raise InvalidTransitionError("no active candidate")
        return self.candidates[self.active_index]

    def _require(self, expected: State, action: str) -> None:
        if self.state is not expected:
            raise InvalidTransitionError(
                f"cannot {action} from {self.state.value} (needs {expected.value})"
            )

    # -- persistence ------------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "mode": self.mode.value,
            "state": self.state.value,
            "fingerprint": self.fingerprint,
            "candidates": [c.to_dict() for c in self.candidates],
            "active_index": self.active_index,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GenerationSession":
        return cls(
            mode=Mode(data["mode"]),
            state=State(data["state"]),
            fingerprint=data["fingerprint"],
            candidates=[Candidate.from_dict(c) for c in data["candidates"]],
            active_index=data["active_index"],
        )
