"""Probability & RNG honesty for lorebook entries (P-036).

Pure-domain module: no DB, no I/O, no network, no wall-clock.
Deterministic seeded rolls use only hashlib; the unseeded path
is the single place system entropy enters, and it is labelled
as unseeded on the record it produces.

The dishonesty this slice removes (S204's standing note): the
budget pass used to draw from one shared ``random.Random(seed)``
in priority order, so an entry's outcome depended on how many
draws other entries had consumed before it, and no roll was
ever recorded -- a ``probability_skip`` said *that* an entry was
dropped but never *by what roll*, and the outcome could not be
reproduced for one entry in isolation.

Semantics (normative):
- An entry's probability is stored as an integer percent,
  ``probability`` in 0..100 (the public world-info shape);
  100 is the default and means the gate is off -- the entry
  always passes and NO roll is made or recorded. 0 means the
  entry never passes (a roll is still made and recorded, so
  the inspector can show it).
- A gated entry (probability < 100) faces exactly one roll per
  tick. The roll is a pure function of (seed, context,
  entry_id): SHA-256 over the canonical material
  ``runmal-p036-roll-v1`` + seed + context + entry_id, first
  eight digest bytes as an unsigned integer divided by 2**64,
  giving a float in [0.0, 1.0). The entry passes iff
  ``roll < probability / 100``.
- The roll does NOT depend on the probability itself, on any
  other entry, on the candidate order, or on how many other
  entries were gated: the same seed + context + entry always
  reproduces the same roll, in isolation, forever (algorithm
  version is part of the material, so a future algorithm
  change is a new version, never a silent drift). Changing
  only the probability re-judges the SAME recorded roll
  against the new threshold.
- ``context`` is the caller's per-tick variation string (a
  chat/tick identifier, a message hash -- the caller's
  choice, recorded verbatim on the roll). The default is the
  empty string: with a fixed seed and no context, a gated
  entry passes or fails the same way every tick, which is
  exactly what a preview/inspector wants and exactly what a
  live caller must vary if it wants per-tick chance.
- ``seed=None`` is the honest unseeded path: the roll is drawn
  from system entropy and the record carries ``seed=None``
  and ``seeded=False``. An unseeded roll can be *inspected*
  after the fact (the value is recorded) but never
  *reproduced* -- the record says so, instead of pretending.
- Strict vs tolerant probability discipline mirrors P-034:
  the service/API layer validates strictly (a real int in
  0..100, bools rejected); the file/import layer normalises
  tolerantly (bools/None/unparsable/out-of-range fall back
  to the default 100 -- out-of-range is never clamped into
  a different gate the author did not write).
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass

#: Algorithm version, part of the roll material. Bump only by
#: adding a new version; never change v1's derivation.
ROLL_ALGORITHM = "runmal-p036-roll-v1"

#: Default stored probability (percent): gate off.
DEFAULT_PROBABILITY = 100

__all__ = [
    "ROLL_ALGORITHM",
    "DEFAULT_PROBABILITY",
    "ProbabilityRoll",
    "check_probability",
    "normalise_probability",
    "probability_fraction",
    "derive_roll",
    "roll_probability",
    "explain_roll",
]


def check_probability(value) -> int:
    """Strict validation: a real int in 0..100 (bools rejected)."""
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"probability must be an integer percent: {value!r}")
    if not 0 <= value <= 100:
        raise ValueError("probability must be in 0..100")
    return value


def normalise_probability(value) -> int:
    """Tolerant percent coercion for the file/import layer.

    Booleans and None mean the default; ints pass through;
    floats truncate; numeric strings parse (float-shaped
    strings included); anything unparsable -- or outside
    0..100, which the strict layer rejects -- falls back to
    the default (gate off), never a clamped invention.
    """
    if isinstance(value, bool) or value is None:
        return DEFAULT_PROBABILITY
    if isinstance(value, int):
        percent = value
    elif isinstance(value, float):
        percent = int(value)
    elif isinstance(value, str):
        try:
            percent = (
                int(float(value))
                if ("." in value or "e" in value.lower())
                else int(value)
            )
        except ValueError:
            return DEFAULT_PROBABILITY
    else:
        return DEFAULT_PROBABILITY
    return percent if 0 <= percent <= 100 else DEFAULT_PROBABILITY


def probability_fraction(percent) -> float:
    """Stored percent -> gate fraction in [0.0, 1.0] (strict)."""
    return check_probability(percent) / 100.0


def _check_seed(seed) -> int | None:
    if seed is None:
        return None
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError(f"seed must be an integer or None: {seed!r}")
    return seed


def derive_roll(entry_id: str, seed: int, context: str = "") -> float:
    """The seeded roll for one entry, in [0.0, 1.0). Pure."""
    _check_seed(seed)
    if not isinstance(entry_id, str) or not entry_id:
        raise ValueError("entry_id must be a non-empty string")
    if not isinstance(context, str):
        raise ValueError("context must be a string")
    material = "\x00".join([ROLL_ALGORITHM, str(seed), context, entry_id])
    digest = hashlib.sha256(material.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(1 << 64)


@dataclass(frozen=True)
class ProbabilityRoll:
    """One inspectable probability roll, as made for one entry."""

    entry_id: str
    probability: float  # gate fraction in [0.0, 1.0]
    roll: float  # the drawn value in [0.0, 1.0)
    passed: bool  # roll < probability
    seed: int | None
    seeded: bool  # False = system-entropy roll, not reproducible
    context: str = ""
    algorithm: str = ROLL_ALGORITHM

    def to_dict(self) -> dict:
        return {
            "entry_id": self.entry_id,
            "probability": self.probability,
            "roll": self.roll,
            "passed": self.passed,
            "seed": self.seed,
            "seeded": self.seeded,
            "context": self.context,
            "algorithm": self.algorithm,
        }


def roll_probability(
    entry_id: str,
    probability: float,
    seed: int | None = None,
    context: str = "",
) -> ProbabilityRoll:
    """Make (or reproduce) the roll for one gated entry.

    ``probability`` is the gate fraction in [0.0, 1.0]. With an
    integer ``seed`` the roll is :func:`derive_roll` -- the
    same seed + context + entry always reproduces it. With
    ``seed=None`` the roll is drawn from system entropy and
    the record is labelled unseeded.
    """
    if isinstance(probability, bool) or not isinstance(probability, (int, float)):
        raise ValueError(f"probability must be a number in [0.0, 1.0]: {probability!r}")
    if not 0.0 <= float(probability) <= 1.0:
        raise ValueError("probability must be in [0.0, 1.0]")
    if not isinstance(context, str):
        raise ValueError("context must be a string")
    _check_seed(seed)
    if seed is None:
        value = random.Random().random()
        seeded = False
    else:
        value = derive_roll(entry_id, seed, context)
        seeded = True
    return ProbabilityRoll(
        entry_id=str(entry_id),
        probability=float(probability),
        roll=value,
        passed=value < float(probability),
        seed=seed,
        seeded=seeded,
        context=context,
    )


def explain_roll(
    entry_id: str,
    probability: float,
    seed: int | None = None,
    context: str = "",
) -> dict:
    """JSON-shaped roll record (what an inspector shows)."""
    return roll_probability(entry_id, probability, seed=seed, context=context).to_dict()
