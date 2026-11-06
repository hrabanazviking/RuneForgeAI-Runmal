"""Inclusion groups for lorebook entries (P-034).

Pure-domain module: no DB, no I/O, no network, no randomness, no
wall-clock. It owns the inclusion-group vocabulary -- the group
label and the group weight -- and the single resolution function
the activation pipeline consults.

Semantics (normative):
- An entry may name ONE inclusion group (``inclusion_group``).
  The label is stripped of surrounding whitespace; an empty label
  (or None / a non-string at the tolerant layer) means the entry
  is ungrouped. Labels are case-sensitive: ``Weather`` and
  ``weather`` are different groups. (The world-info file field is
  a single string; a value containing commas is one label here,
  commas included -- multi-group membership is not modelled.)
- Entries that share a non-empty group are mutually exclusive:
  among the *activated* candidates of one group, exactly one is
  included and the rest are excluded for this tick.
- Resolution is deterministic. The winner of a group is chosen by,
  in order: highest ``group_weight``, then highest ``priority``,
  then lowest ``entry_id`` (ascending string order). No other
  input influences the choice -- in particular not the input
  order, not the time, and not any random draw -- so the same
  candidate set always resolves to the same winner, in any input
  order. (The public format's weighted-random group scoring is
  deliberately NOT reproduced: a random draw cannot be resolved
  deterministically, and seeded probabilistic choice is P-036's
  road, not this slice's.)
- Ungrouped candidates are always included (subject to the later
  budget pass, which is a separate concern).
- Duplicate ``entry_id`` rows: the first occurrence is the
  candidate; later duplicates are ignored entirely (an entry
  fires at most once per tick, the scanner's standing rule).

Result shape: winners are returned in the original input order
(callers keep their pipeline order); losers are returned in a
deterministic order -- group label ascending, then the same
ranking key that chose the winner (weight desc, priority desc,
entry_id asc) -- and each loser carries its provenance: the group,
the winner's id, and both sides' weight/priority, so an inspector
can answer "why did this entry not fire" without re-running
anything (P-043 consumes this).
"""

from __future__ import annotations

from dataclasses import dataclass

#: Default group weight (the public format's default).
DEFAULT_GROUP_WEIGHT = 100

#: Maximum stored length of an inclusion-group label.
MAX_GROUP_LENGTH = 200

__all__ = [
    "DEFAULT_GROUP_WEIGHT",
    "MAX_GROUP_LENGTH",
    "GroupCandidate",
    "GroupLoser",
    "GroupResolution",
    "check_group_weight",
    "check_inclusion_group",
    "normalise_group_weight",
    "normalise_inclusion_group",
    "resolve_inclusion_groups",
]


def check_inclusion_group(value) -> str:
    """Strict validation: a string label, stripped; '' = ungrouped.

    Raises ValueError for non-strings and over-long labels.
    """
    if not isinstance(value, str):
        raise ValueError(f"inclusion_group must be a string: {value!r}")
    label = value.strip()
    if len(label) > MAX_GROUP_LENGTH:
        raise ValueError(
            f"inclusion_group must be at most {MAX_GROUP_LENGTH} characters"
        )
    return label


def normalise_inclusion_group(value) -> str:
    """Tolerant label normaliser: strings strip; anything else -> ''."""
    if isinstance(value, str):
        return value.strip()[:MAX_GROUP_LENGTH]
    return ""


def check_group_weight(value) -> int:
    """Strict validation: a real int >= 0 (bools are not ints)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"group_weight must be an integer: {value!r}")
    if value < 0:
        raise ValueError("group_weight must be >= 0")
    return value


def normalise_group_weight(value) -> int:
    """Tolerant weight coercion for the file/import layer.

    Mirrors ``selective_logic_from_code``'s discipline: booleans and
    None mean the default, ints pass through, floats truncate,
    numeric strings parse (float-shaped strings included), and
    anything unparsable -- or negative, which the strict layer
    rejects -- falls back to the default weight.
    """
    if isinstance(value, bool) or value is None:
        return DEFAULT_GROUP_WEIGHT
    if isinstance(value, int):
        weight = value
    elif isinstance(value, float):
        weight = int(value)
    elif isinstance(value, str):
        try:
            weight = (
                int(float(value))
                if ("." in value or "e" in value.lower())
                else int(value)
            )
        except ValueError:
            return DEFAULT_GROUP_WEIGHT
    else:
        return DEFAULT_GROUP_WEIGHT
    return weight if weight >= 0 else DEFAULT_GROUP_WEIGHT


@dataclass(frozen=True)
class GroupCandidate:
    """One activated entry competing (or not) in its group."""

    entry_id: str
    inclusion_group: str = ""
    group_weight: int = DEFAULT_GROUP_WEIGHT
    priority: int = 100

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "inclusion_group", check_inclusion_group(self.inclusion_group)
        )
        check_group_weight(self.group_weight)
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise ValueError(f"priority must be an integer: {self.priority!r}")


@dataclass(frozen=True)
class GroupLoser:
    """One excluded candidate, with the provenance of its loss."""

    entry_id: str
    inclusion_group: str
    winner_id: str
    group_weight: int
    priority: int
    winner_group_weight: int
    winner_priority: int
    reason: str = "inclusion_group"


@dataclass(frozen=True)
class GroupResolution:
    """Outcome of :func:`resolve_inclusion_groups`."""

    winners: tuple[GroupCandidate, ...]
    losers: tuple[GroupLoser, ...]
    #: group label -> winner entry_id, for every contested group.
    winner_by_group: dict


def _rank_key(candidate: GroupCandidate) -> tuple:
    """Winner ranking: weight desc, priority desc, entry_id asc."""
    return (-candidate.group_weight, -candidate.priority, candidate.entry_id)


def resolve_inclusion_groups(candidates) -> GroupResolution:
    """Resolve mutual exclusion over one tick's activated candidates.

    Deterministic and input-order independent in outcome: the
    winner *set* depends only on the candidate set. Winners are
    returned in input order; losers in the documented
    deterministic order (see the module docstring).
    """
    unique: list[GroupCandidate] = []
    seen: set[str] = set()
    for cand in candidates:
        if cand.entry_id in seen:
            continue  # duplicate id row: an entry fires at most once
        seen.add(cand.entry_id)
        unique.append(cand)

    by_group: dict[str, list[GroupCandidate]] = {}
    for cand in unique:
        if cand.inclusion_group:
            by_group.setdefault(cand.inclusion_group, []).append(cand)

    winner_by_group: dict[str, str] = {}
    loser_rows: list[GroupLoser] = []
    for group in sorted(by_group):
        members = by_group[group]
        if len(members) == 1:
            continue  # uncontested: included, no winner recorded
        winner = min(members, key=_rank_key)
        winner_by_group[group] = winner.entry_id
        for member in members:
            if member.entry_id == winner.entry_id:
                continue
            loser_rows.append(
                GroupLoser(
                    entry_id=member.entry_id,
                    inclusion_group=group,
                    winner_id=winner.entry_id,
                    group_weight=member.group_weight,
                    priority=member.priority,
                    winner_group_weight=winner.group_weight,
                    winner_priority=winner.priority,
                )
            )
    loser_rows.sort(key=lambda row: (row.inclusion_group, -row.group_weight, -row.priority, row.entry_id))
    loser_ids = {row.entry_id for row in loser_rows}
    winners = tuple(c for c in unique if c.entry_id not in loser_ids)
    return GroupResolution(
        winners=winners,
        losers=tuple(loser_rows),
        winner_by_group=winner_by_group,
    )
