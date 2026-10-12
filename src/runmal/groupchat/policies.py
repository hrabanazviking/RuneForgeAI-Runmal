"""Speaker policies (roadmap S211): who talks next in a group room.

Four policies over the room's roster, each deterministic for a fixed
seed + state (seeded tests pin exact selections):

- ``manual``  -- only the explicitly designated speaker talks. No
  designation, an unknown id, or a muted designee means silence: manual
  never substitutes a different speaker (fallback = nobody).
- ``natural`` -- an @-mentioned unmuted member talks (roster order when
  several are mentioned). Otherwise a talkativeness-weighted pick among
  unmuted members; when every weight is 0 the pick is uniform. All muted
  means silence.
- ``list``    -- cycles a configured order of character ids, skipping
  ids that left the roster or are muted. Empty effective order = silence.
- ``pooled``  -- picks uniformly from the pool of unmuted members who
  have not spoken since the pool last reset; when the pool empties it
  resets to the full eligible roster. All muted = silence.

Mute is absolute in every policy: a muted member is never selected.
Policies are pure selection over a :class:`SelectionContext`; callers
report the outcome back through :meth:`SpeakerPolicy.note_selected` so
stateful policies (list cursor, pool membership) advance.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from runmal.groupchat.core import _is_mentioned


@dataclass(frozen=True)
class MemberState:
    character_id: str
    name: str
    muted: bool = False
    talkativeness: float = 0.5

    def __post_init__(self) -> None:
        if not 0.0 <= self.talkativeness <= 1.0:
            raise ValueError("talkativeness must be in [0.0, 1.0]")


@dataclass
class SelectionContext:
    members: list[MemberState]
    seed: int = 0
    last_user_text: str = ""
    manual_speaker_id: str | None = None
    list_order: list[str] = field(default_factory=list)
    list_cursor: int = 0
    pool_spoken: set[str] = field(default_factory=set)
    # Character ids in speaking order, oldest first ("user" for the owner).
    history_speakers: list[str] = field(default_factory=list)

    def eligible(self) -> list[MemberState]:
        return [m for m in self.members if not m.muted]

    def member(self, character_id: str) -> MemberState | None:
        return next((m for m in self.members if m.character_id == character_id), None)


class SpeakerPolicy:
    """Informal protocol; S212 formalizes the pluggable interface."""

    name: str = ""

    def select(self, ctx: SelectionContext) -> str | None:
        raise NotImplementedError

    def note_selected(self, ctx: SelectionContext, character_id: str) -> None:
        """Advance policy state after ``character_id`` spoke (default: none)."""


class ManualPolicy(SpeakerPolicy):
    name = "manual"

    def select(self, ctx: SelectionContext) -> str | None:
        if ctx.manual_speaker_id is None:
            return None
        member = ctx.member(ctx.manual_speaker_id)
        if member is None or member.muted:
            return None
        return member.character_id


class NaturalPolicy(SpeakerPolicy):
    name = "natural"

    def select(self, ctx: SelectionContext) -> str | None:
        eligible = ctx.eligible()
        if not eligible:
            return None
        if ctx.last_user_text:
            mentioned = [m for m in eligible if _is_mentioned(ctx.last_user_text, m.name)]
            if mentioned:
                return mentioned[0].character_id
        rng = random.Random(ctx.seed)
        weights = [m.talkativeness for m in eligible]
        if any(w > 0 for w in weights):
            return rng.choices(eligible, weights=weights, k=1)[0].character_id
        return rng.choice(eligible).character_id


class ListPolicy(SpeakerPolicy):
    name = "list"

    def _effective_order(self, ctx: SelectionContext) -> list[str]:
        eligible_ids = {m.character_id for m in ctx.eligible()}
        return [cid for cid in ctx.list_order if cid in eligible_ids]

    def select(self, ctx: SelectionContext) -> str | None:
        order = self._effective_order(ctx)
        if not order:
            return None
        return order[ctx.list_cursor % len(order)]

    def note_selected(self, ctx: SelectionContext, character_id: str) -> None:
        order = self._effective_order(ctx)
        if character_id in order:
            ctx.list_cursor = order.index(character_id) + 1


class PooledPolicy(SpeakerPolicy):
    name = "pooled"

    def _pool(self, ctx: SelectionContext) -> list[MemberState]:
        eligible = ctx.eligible()
        pool = [m for m in eligible if m.character_id not in ctx.pool_spoken]
        return pool if pool else eligible  # empty pool -> reset to full roster

    def select(self, ctx: SelectionContext) -> str | None:
        pool = self._pool(ctx)
        if not pool:
            return None
        return random.Random(ctx.seed).choice(pool).character_id

    def note_selected(self, ctx: SelectionContext, character_id: str) -> None:
        ctx.pool_spoken.add(character_id)
        eligible_ids = {m.character_id for m in ctx.eligible()}
        if eligible_ids and eligible_ids <= ctx.pool_spoken:
            ctx.pool_spoken.clear()


POLICIES: dict[str, SpeakerPolicy] = {
    policy.name: policy
    for policy in (ManualPolicy(), NaturalPolicy(), ListPolicy(), PooledPolicy())
}


def get_policy(name: str) -> SpeakerPolicy:
    try:
        return POLICIES[name]
    except KeyError:
        raise ValueError(f"unknown speaker policy: {name!r} (valid: {sorted(POLICIES)})") from None


# -- Pluggable director interface (roadmap S212) ---------------------------
#
# A SpeakerDirector is anything with the policy shape: ``select(ctx)``
# returning a character id (or None for silence) plus an optional
# ``note_selected`` state hook. The S211 policies already conform. Custom
# directors register by name at runtime and immediately become valid
# group speaker-policy values -- the group service validates names
# against this registry, so plugging one in needs no group-service
# change. An LLM-backed director implements the same shape later; the
# deterministic FakeDirector below is the testable seam stand-in.


@runtime_checkable
class SpeakerDirector(Protocol):
    """The director shape: choose the next speaker, then be told who
    spoke. Implementations also carry a ``name`` attribute (not part of
    the checked protocol -- data members cannot be runtime-checked)."""

    def select(self, ctx: SelectionContext) -> str | None: ...

    def note_selected(self, ctx: SelectionContext, character_id: str) -> None: ...


DIRECTORS: dict[str, SpeakerDirector] = dict(POLICIES)


def register_director(name: str, director: SpeakerDirector, replace: bool = False) -> None:
    """Plug a custom director in under ``name``. Refuses to shadow an
    existing registration unless ``replace`` is set."""
    if not name or not isinstance(name, str):
        raise ValueError("director name must be a non-empty string")
    if not callable(getattr(director, "select", None)):
        raise ValueError("director must provide select(ctx)")
    if name in DIRECTORS and not replace:
        raise ValueError(f"director already registered: {name!r}")
    DIRECTORS[name] = director
    POLICIES[name] = director  # group-service validation reads POLICIES


def get_director(name: str) -> SpeakerDirector:
    if name in DIRECTORS:
        return DIRECTORS[name]
    valid = ", ".join(sorted(DIRECTORS))
    raise ValueError(f"unknown speaker director: {name!r} (valid: {valid})")


class FakeDirector:
    """Deterministic fake-LLM director: the seam an LLM director will fill.

    Stands in for a model that reads the room and names the next speaker.
    Its "judgment" is a fixed, explainable heuristic -- an @-mention wins;
    otherwise the member who has spoken least recently (never-spoken
    first, roster order breaks ties, talkativeness breaks remaining
    ties). No randomness: the same room state always yields the same
    speaker, so tests can pin its behavior exactly.
    """

    name = "fake-director"

    def select(self, ctx: SelectionContext) -> str | None:
        eligible = ctx.eligible()
        if not eligible:
            return None
        if ctx.last_user_text:
            mentioned = [m for m in eligible if _is_mentioned(ctx.last_user_text, m.name)]
            if mentioned:
                return mentioned[0].character_id

        def rank(item: tuple[int, MemberState]) -> tuple[int, int, float, int]:
            roster_index, member = item
            spoken = [i for i, s in enumerate(ctx.history_speakers) if s == member.character_id]
            times_spoken = len(spoken)
            last_spoke = spoken[-1] if spoken else -1
            # Least-spoken first; among equals, the one idle longest
            # (never-spoke = -1 beats any real index); then chattier;
            # then roster order. Fully deterministic.
            return (times_spoken, last_spoke, -member.talkativeness, roster_index)

        return min(enumerate(eligible), key=rank)[1].character_id

    def note_selected(self, ctx: SelectionContext, character_id: str) -> None:
        ctx.history_speakers.append(character_id)


register_director(FakeDirector.name, FakeDirector())
