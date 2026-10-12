"""Group chat core (S210): participants, strategy, mention gating, turns.

Multiple personas converse over one shared message history. A turn strategy
decides who speaks:

- MENTION -- only participants @-mentioned in the latest user message speak
  (mention gating: no mention, no speech).
- ROUND_ROBIN -- one speaker per turn, rotating in participant order.
- BROADCAST -- every participant speaks, in order, each seeing the answers
  already added to the shared state by earlier speakers in the same turn.

Prompt shaping: a participant sees its own past messages as assistant
turns, the user's as user turns, and other participants' messages as user
turns labeled ``Name: text`` -- one shared state, per-persona viewpoint.
The responder is injected (the API layer adapts the generation service);
the core itself is pure orchestration.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable

USER_AUTHOR = "user"


@dataclass(frozen=True)
class Participant:
    character_id: str
    name: str
    persona: str = ""


@dataclass(frozen=True)
class GroupMessage:
    author: str  # USER_AUTHOR or a participant name
    content: str


class Strategy(Enum):
    MENTION = "mention"
    ROUND_ROBIN = "round_robin"
    BROADCAST = "broadcast"


Responder = Callable[[Participant, list[dict]], str]


@dataclass
class GroupChat:
    participants: list[Participant]
    history: list[GroupMessage] = field(default_factory=list)
    _rr_cursor: int = 0  # next round-robin speaker index

    def post_user(self, text: str) -> GroupMessage:
        msg = GroupMessage(USER_AUTHOR, text)
        self.history.append(msg)
        return msg

    # -- strategy ---------------------------------------------------------
    def speakers_for(self, strategy: Strategy) -> list[Participant]:
        if strategy is Strategy.BROADCAST:
            return list(self.participants)
        if strategy is Strategy.ROUND_ROBIN:
            if not self.participants:
                return []
            return [self.participants[self._rr_cursor % len(self.participants)]]
        if strategy is Strategy.MENTION:
            last_user = next(
                (m for m in reversed(self.history) if m.author == USER_AUTHOR),
                None,
            )
            if last_user is None:
                return []
            return [
                p
                for p in self.participants
                if _is_mentioned(last_user.content, p.name)
            ]
        raise ValueError(f"unknown strategy: {strategy!r}")

    # -- turns ------------------------------------------------------------
    def build_prompt(self, participant: Participant) -> list[dict]:
        messages: list[dict] = []
        if participant.persona:
            messages.append({"role": "system", "content": participant.persona})
        for msg in self.history:
            if msg.author == participant.name:
                messages.append({"role": "assistant", "content": msg.content})
            elif msg.author == USER_AUTHOR:
                messages.append({"role": "user", "content": msg.content})
            else:
                messages.append(
                    {"role": "user", "content": f"{msg.author}: {msg.content}"}
                )
        return messages

    def run_turn(
        self, responder: Responder, strategy: Strategy = Strategy.MENTION
    ) -> list[GroupMessage]:
        """Let the strategy's speakers answer; appends to shared history."""
        speakers = self.speakers_for(strategy)
        replies: list[GroupMessage] = []
        for speaker in speakers:
            # Each speaker's prompt is built AFTER earlier speakers in this
            # same turn appended theirs: genuinely shared state.
            prompt = self.build_prompt(speaker)
            text = responder(speaker, prompt)
            msg = GroupMessage(speaker.name, text)
            self.history.append(msg)
            replies.append(msg)
            if strategy is Strategy.ROUND_ROBIN:
                idx = self.participants.index(speaker)
                self._rr_cursor = (idx + 1) % len(self.participants)
        return replies


def _is_mentioned(text: str, name: str) -> bool:
    """True when ``text`` contains an @-mention of ``name`` (any case)."""
    return (
        re.search(rf"@{re.escape(name)}(?![A-Za-z0-9_])", text, re.IGNORECASE)
        is not None
    )
