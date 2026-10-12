"""Activation semantics for lorebook entries (S203).

Pure-domain module: no DB, no I/O. It layers per-entry activation policy on
top of S202's keyword scan hits. One :func:`activate` call represents one
prompt tick; callers pass in the runtime state dict and get it back mutated,
so sticky/cooldown/delay counters survive across prompts. Persisting that
state (per chat) is a later pipeline slice's concern -- see DATA_MODEL.md.

Activation modes (the two modes an entry can be in):
- ``constant``: the entry is always active, no keys required.
- ``selective`` (the default, ``constant=False``): the entry activates only
  when the pipeline selects it -- a keyword hit, sticky carryover, a fired
  delay, or a ``{{lore:...}}`` reference from another active entry.

Per-entry timing knobs (all in prompts, all default 0 = off):
- ``sticky_prompts``: after a key trigger, the entry stays active for this
  many further prompts without needing another key hit.
- ``cooldown_prompts``: after a key trigger, the entry is suppressed for
  this many prompts even if its keys match again.
- ``delay_prompts``: after a key match, wait this many prompts before the
  entry activates (the match arms the countdown; it fires D ticks later).

Tick order per entry (deterministic; entries processed in input order):
1. Disabled entries are skipped entirely.
2. Constant entries activate immediately (``via="constant"``).
3. If ``cooldown_remaining > 0``: decrement, suppress this tick.
4. Else if a delay is armed: decrement; on reaching zero, activate
   (``via="delay"``) and arm sticky/cooldown from the config.
5. Else if keys hit this tick: with ``delay_prompts > 0`` arm the delay;
   otherwise activate (``via="key"``) and arm sticky/cooldown.
6. Else if ``sticky_remaining > 0``: decrement, activate (``via="sticky"``).

Recursion: entry content may reference other entries of the same book with
``{{lore:Entry Name}}``. References resolve depth-first after direct
activation. Cycles terminate deterministically: a reference that would
re-enter an entry already on the resolution path is left as literal text.
``MAX_RECURSION_DEPTH`` (5) is a hard cap; deeper references are left
literal. Unknown names are left literal. Referenced entries must be enabled;
they activate with ``via="reference"`` regardless of keys or timing knobs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

MAX_RECURSION_DEPTH = 5

LORE_REF_RE = re.compile(r"\{\{\s*lore\s*:\s*([^{}]+?)\s*\}\}")


def _check_non_negative(name: str, value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{name} must be an integer")
    if value < 0:
        raise ValueError(f"{name} must be >= 0")
    return value


@dataclass
class ActivatableEntry:
    """Scannable + activatable view of a lorebook entry."""

    id: str
    name: str = ""
    content: str = ""
    enabled: bool = True
    constant: bool = False
    sticky_prompts: int = 0
    cooldown_prompts: int = 0
    delay_prompts: int = 0

    def __post_init__(self) -> None:
        _check_non_negative("sticky_prompts", self.sticky_prompts)
        _check_non_negative("cooldown_prompts", self.cooldown_prompts)
        _check_non_negative("delay_prompts", self.delay_prompts)

    @classmethod
    def from_orm(cls, entry) -> "ActivatableEntry":
        return cls(
            id=str(entry.id),
            name=str(entry.name or ""),
            content=str(entry.content or ""),
            enabled=bool(entry.enabled),
            constant=bool(entry.constant),
            sticky_prompts=int(entry.sticky_prompts or 0),
            cooldown_prompts=int(entry.cooldown_prompts or 0),
            delay_prompts=int(entry.delay_prompts or 0),
        )


@dataclass
class EntryState:
    """Runtime counters for one entry. Mutated in place by :func:`activate`."""

    sticky_remaining: int = 0
    cooldown_remaining: int = 0
    delay_remaining: int = 0
    delay_armed: bool = False


@dataclass(frozen=True)
class ResolvedActivation:
    entry_id: str
    content: str  # with {{lore:...}} references expanded
    via: str  # "constant" | "key" | "sticky" | "delay" | "reference"
    depth: int  # recursion depth; 0 = directly activated


@dataclass
class ActivationResult:
    activations: list[ResolvedActivation]
    states: dict[str, EntryState]  # the (mutated) state mapping passed in


def _arm_post(state: EntryState, entry: ActivatableEntry) -> None:
    if entry.sticky_prompts > 0:
        state.sticky_remaining = entry.sticky_prompts
    if entry.cooldown_prompts > 0:
        state.cooldown_remaining = entry.cooldown_prompts


def _tick_entry(
    entry: ActivatableEntry,
    key_hit: bool,
    states: dict[str, EntryState],
) -> str | None:
    """Process one entry for one tick. Returns the via-tag or None."""
    if not entry.enabled:
        return None
    if entry.constant:
        states.setdefault(entry.id, EntryState())
        return "constant"
    state = states.setdefault(entry.id, EntryState())

    if state.cooldown_remaining > 0:
        state.cooldown_remaining -= 1
        return None
    if state.delay_armed:
        state.delay_remaining -= 1
        if state.delay_remaining <= 0:
            state.delay_armed = False
            _arm_post(state, entry)
            return "delay"
        return None
    if key_hit:
        if entry.delay_prompts > 0:
            state.delay_armed = True
            state.delay_remaining = entry.delay_prompts
            return None
        _arm_post(state, entry)
        return "key"
    if state.sticky_remaining > 0:
        state.sticky_remaining -= 1
        return "sticky"
    return None


def _resolve_content(
    entry: ActivatableEntry,
    by_name: dict[str, ActivatableEntry],
    visiting: tuple[str, ...],
    depth: int,
) -> tuple[str, list[ResolvedActivation]]:
    """Expand {{lore:...}} refs depth-first. Returns (text, new activations)."""
    found: list[ResolvedActivation] = []

    def _expand(match: "re.Match[str]") -> str:
        name = match.group(1).strip()
        target = by_name.get(name) or by_name.get(name.lower())
        if (
            target is None
            or not target.enabled
            or target.id in visiting
            or depth >= MAX_RECURSION_DEPTH
        ):
            return match.group(0)  # literal: unknown, disabled, cyclic, too deep
        text, deeper = _resolve_content(
            target, by_name, visiting + (target.id,), depth + 1
        )
        found.append(
            ResolvedActivation(
                entry_id=target.id, content=text, via="reference", depth=depth + 1
            )
        )
        found.extend(deeper)
        return text

    return LORE_REF_RE.sub(_expand, entry.content), found


def activate(
    entries: list[ActivatableEntry],
    hit_ids: set[str],
    states: dict[str, EntryState] | None = None,
) -> ActivationResult:
    """Run one activation tick.

    ``entries``: candidate entries in deterministic (priority) order.
    ``hit_ids``: entry ids with keyword hits this tick (from S202).
    ``states``: runtime counters, mutated in place and returned.
    """
    states = {} if states is None else states
    by_id = {e.id: e for e in entries}
    by_name: dict[str, ActivatableEntry] = {}
    for e in entries:
        by_name.setdefault(e.name, e)
        by_name.setdefault(e.name.lower(), e)

    direct: list[tuple[ActivatableEntry, str]] = []
    for entry in entries:
        via = _tick_entry(entry, entry.id in hit_ids, states)
        if via is not None:
            direct.append((entry, via))

    activations: list[ResolvedActivation] = []
    seen: set[str] = set()
    for entry, via in direct:
        text, referred = _resolve_content(entry, by_name, (entry.id,), 0)
        activations.append(
            ResolvedActivation(
                entry_id=entry.id, content=text, via=via, depth=0
            )
        )
        seen.add(entry.id)
        for ref in referred:
            if ref.entry_id not in seen:
                seen.add(ref.entry_id)
                activations.append(ref)
    return ActivationResult(activations=activations, states=states)
