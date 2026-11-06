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

Recursive scanning (P-031): entries hit by P-031 recursive scanning
(their key found in another fired entry's content) activate
via="recursive" at their discovery depth when they fire immediately
on that hit. Timing knobs still apply first: a recursive hit on a
delay-configured entry only arms the delay (the entry later fires
via="delay" -- recursive provenance is not carried across ticks),
and a hit landing during cooldown is suppressed like any key hit.

Inclusion groups (P-034): after direct activation, entries that
share a non-empty ``inclusion_group`` are mutually exclusive --
:func:`runmal.lorebooks.groups.resolve_inclusion_groups` keeps
exactly one winner per contested group (highest ``group_weight``,
then highest ``priority``, then lowest entry id),
deterministically, and the losers are
reported on the result as ``group_losers`` (with provenance) and
``group_suppressed`` (their would-be activations). Group
resolution applies to direct activations of every via kind
(constant included); entries pulled in by ``{{lore:...}}``
reference expansion are NOT group-resolved -- a reference is an
explicit authorial inclusion, not a group activation. A loser's
timing state has already advanced this tick (its sticky/cooldown
were armed when it fired), exactly as a budget-discarded entry's
have: group exclusion is an inclusion decision, not an un-firing.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from runmal.lorebooks.groups import (
    DEFAULT_GROUP_WEIGHT,
    GroupCandidate,
    check_group_weight,
    check_inclusion_group,
    normalise_group_weight,
    normalise_inclusion_group,
    resolve_inclusion_groups,
)
from runmal.lorebooks.states import (
    KIND_VECTORISED,
    activation_kind_for,
    normalise_vectorised,
)

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
    vectorised: bool = False
    sticky_prompts: int = 0
    cooldown_prompts: int = 0
    delay_prompts: int = 0
    # Inclusion groups (P-034): one group label ('' = ungrouped),
    # a group weight, and the entry priority the group tie-break
    # consults after weight (the same priority S204 budgets by).
    inclusion_group: str = ""
    group_weight: int = DEFAULT_GROUP_WEIGHT
    priority: int = 100

    def __post_init__(self) -> None:
        _check_non_negative("sticky_prompts", self.sticky_prompts)
        _check_non_negative("cooldown_prompts", self.cooldown_prompts)
        _check_non_negative("delay_prompts", self.delay_prompts)
        self.inclusion_group = check_inclusion_group(self.inclusion_group)
        check_group_weight(self.group_weight)
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise ValueError("priority must be an integer")

    @property
    def activation_kind(self) -> str:
        """The entry's single derived activation kind (P-035)."""
        return activation_kind_for(self.constant, self.vectorised)

    @classmethod
    def from_orm(cls, entry) -> "ActivatableEntry":
        return cls(
            id=str(entry.id),
            name=str(entry.name or ""),
            content=str(entry.content or ""),
            enabled=bool(entry.enabled),
            constant=bool(entry.constant),
            vectorised=normalise_vectorised(getattr(entry, "vectorised", None)),
            sticky_prompts=int(entry.sticky_prompts or 0),
            cooldown_prompts=int(entry.cooldown_prompts or 0),
            delay_prompts=int(entry.delay_prompts or 0),
            inclusion_group=normalise_inclusion_group(
                getattr(entry, "inclusion_group", None)
            ),
            group_weight=normalise_group_weight(
                getattr(entry, "group_weight", None)
            ),
            priority=int(getattr(entry, "priority", 100) or 0)
            if getattr(entry, "priority", None) is not None
            else 100,
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
    via: str  # constant|key|sticky|delay|reference|recursive|vector|vector_fallback
    depth: int  # recursion depth; 0 = directly activated


@dataclass
class ActivationResult:
    activations: list[ResolvedActivation]
    states: dict[str, EntryState]  # the (mutated) state mapping passed in
    # Inclusion groups (P-034): losers' provenance rows, and the
    # losers' would-be activations (via/depth as fired, content
    # unexpanded -- reference expansion never runs for losers).
    group_losers: tuple = ()
    group_suppressed: tuple = ()


def _arm_post(state: EntryState, entry: ActivatableEntry) -> None:
    if entry.sticky_prompts > 0:
        state.sticky_remaining = entry.sticky_prompts
    if entry.cooldown_prompts > 0:
        state.cooldown_remaining = entry.cooldown_prompts


def _tick_entry(
    entry: ActivatableEntry,
    key_hit: bool,
    vector_hit: bool,
    states: dict[str, EntryState],
    fallback_hit: bool = False,
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
    # Trigger dispatch on the derived kind (P-035): a vectorised
    # entry fires only from a vector hit, a selective entry only
    # from a key hit -- the two hit kinds never cross. P-041 adds
    # exactly one sanctioned crossing: a keyword-fallback hit,
    # which the matcher supplies ONLY when embeddings were
    # unavailable or matched nothing at/above threshold; it fires
    # via "vector_fallback", honestly labelled, never "vector".
    is_vectorised = entry.activation_kind == KIND_VECTORISED
    triggered = (vector_hit or fallback_hit) if is_vectorised else key_hit
    if triggered:
        if entry.delay_prompts > 0:
            state.delay_armed = True
            state.delay_remaining = entry.delay_prompts
            return None
        _arm_post(state, entry)
        if is_vectorised:
            return "vector" if vector_hit else "vector_fallback"
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
    *,
    recursive_hit_ids: set[str] | None = None,
    hit_depths: dict[str, int] | None = None,
    vector_hit_ids: set[str] | None = None,
    vector_fallback_ids: set[str] | None = None,
) -> ActivationResult:
    """Run one activation tick.

    ``entries``: candidate entries in deterministic (priority) order.
    ``hit_ids``: entry ids with keyword hits this tick (from S202).
    ``states``: runtime counters, mutated in place and returned.
    ``recursive_hit_ids`` / ``hit_depths``: P-031 recursive-scan hits;
    a plain key firing for such an entry is relabelled "recursive"
    and reported at its discovery depth. Supply the two together
    (``recursive_hit_ids`` a subset of ``hit_ids``, depths > 0);
    ``hit_depths`` is consulted only for entries actually relabelled
    "recursive", so other firings always report depth 0.
    Absent/None = pre-P-031 behaviour, unchanged.

    ``vector_hit_ids``: entry ids hit by vector matching this tick
    (P-035; the embedding matcher itself is P-041 --
    ``runmal.lorebooks.vector_match`` computes these in the live
    paths now). Absent/None = no vector hits.

    ``vector_fallback_ids`` (P-041): entry ids hit by the keyword
    fallback -- supplied by the matcher only when embeddings were
    unavailable or no vector score reached the threshold. A
    fallback hit fires a vectorised entry via "vector_fallback";
    it never fires a selective entry (those use ``hit_ids``) and
    a real vector hit on the same entry wins the "vector" label.

    Entry states (P-035): one engine dispatches on the derived
    kind (``activation_kind``: constant / selective / vectorised);
    timing knobs apply identically to key and vector triggers (a
    vector hit during cooldown is suppressed, a vector hit on a
    delay entry arms the delay and later fires via="delay" --
    trigger provenance is not carried across ticks, the recursive
    precedent); inclusion groups apply to vector activations like
    every via kind.

    Inclusion groups (P-034) need no extra arguments: they ride on
    the entries themselves (``inclusion_group`` / ``group_weight`` /
    ``priority``) and the outcome rides back on the result's
    ``group_losers`` / ``group_suppressed``. With no grouped entry
    among the direct activations both are empty and behaviour is
    exactly pre-P-034.
    """
    states = {} if states is None else states
    by_id = {e.id: e for e in entries}
    by_name: dict[str, ActivatableEntry] = {}
    for e in entries:
        by_name.setdefault(e.name, e)
        by_name.setdefault(e.name.lower(), e)

    direct: list[tuple[ActivatableEntry, str]] = []
    for entry in entries:
        via = _tick_entry(
            entry,
            entry.id in hit_ids,
            entry.id in (vector_hit_ids or set()),
            states,
            fallback_hit=entry.id in (vector_fallback_ids or set()),
        )
        if (
            via == "key"
            and recursive_hit_ids is not None
            and entry.id in recursive_hit_ids
        ):
            via = "recursive"
        if via is not None:
            direct.append((entry, via))

    # Inclusion groups (P-034): mutually exclusive direct
    # activations resolve to one winner per contested group,
    # deterministically, before reference expansion. Losers keep
    # their fired via for provenance but never expand references
    # and never reach the budget pass.
    group_losers: tuple = ()
    group_suppressed: list[ResolvedActivation] = []
    if any(entry.inclusion_group for entry, _via in direct):
        resolution = resolve_inclusion_groups(
            GroupCandidate(
                entry_id=entry.id,
                inclusion_group=entry.inclusion_group,
                group_weight=entry.group_weight,
                priority=entry.priority,
            )
            for entry, _via in direct
        )
        group_losers = resolution.losers
        loser_ids = {row.entry_id for row in group_losers}
        if loser_ids:
            kept: list[tuple[ActivatableEntry, str]] = []
            for entry, via in direct:
                if entry.id in loser_ids:
                    depth = 0
                    if (
                        via == "recursive"
                        and hit_depths is not None
                        and recursive_hit_ids is not None
                        and entry.id in recursive_hit_ids
                    ):
                        depth = hit_depths.get(entry.id, 0)
                    group_suppressed.append(
                        ResolvedActivation(
                            entry_id=entry.id, content=entry.content, via=via, depth=depth
                        )
                    )
                else:
                    kept.append((entry, via))
            direct = kept

    activations: list[ResolvedActivation] = []
    seen: set[str] = set()
    for entry, via in direct:
        text, referred = _resolve_content(entry, by_name, (entry.id,), 0)
        depth = 0
        if (
            via == "recursive"
            and hit_depths is not None
            and entry.id in recursive_hit_ids
        ):
            depth = hit_depths.get(entry.id, 0)
        activations.append(
            ResolvedActivation(
                entry_id=entry.id, content=text, via=via, depth=depth
            )
        )
        seen.add(entry.id)
        for ref in referred:
            if ref.entry_id not in seen:
                seen.add(ref.entry_id)
                activations.append(ref)
    return ActivationResult(
        activations=activations,
        states=states,
        group_losers=group_losers,
        group_suppressed=tuple(group_suppressed),
    )
