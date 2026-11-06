"""Token budget + priority resolution for lorebook candidates (S204).

Pure-domain module: no DB, no I/O. After S202 (scan) and S203 (activation)
produce candidate entries, this module decides which ones fit in the token
budget.

Token counting: :func:`estimate_tokens` is a deterministic heuristic
(``max(1, len(text) // 4)``). It is an *estimate* -- good enough for budget
decisions, cheap, and dependency-free. A real tokenizer can replace it
later without changing this module's contract (S214's trace records which
estimator was used). The canonical implementation lives in
:mod:`runmal.tokens` and is re-exported here.

Resolution algorithm (deterministic for a fixed seed + context):
1. Candidates sort by priority descending; equal priorities tie-break by
   entry id ascending. The tie-break is stable: the same input set always
   yields the same order.
2. In that order, each candidate first faces its probability gate (if
   ``probability < 1.0``): ONE seeded, inspectable roll from
   :mod:`runmal.lorebooks.rng` (P-036). A failed roll discards it with
   reason ``"probability_skip"``. Every gated candidate's roll is
   recorded on the result (``BudgetResult.rolls``), pass or fail.
3. Survivors are greedily packed: a candidate whose estimated tokens exceed
   the remaining budget is discarded with reason ``"over_budget"``;
   smaller later candidates can still fit.
4. ``token_budget=None`` means unlimited: everything that passes its
   probability gate is included.

Probability & RNG honesty (P-036 supersedes S204's draw): S204 drew
from one shared ``random.Random(seed)`` in sorted order, so an
entry's outcome depended on how many draws preceded it and no roll
was recorded. P-036 derives each entry's roll independently from
(seed, context, entry_id) -- see ``lorebooks/rng.py`` for the
normative semantics. The same seed + context + candidate set
reproduces the same outcome, and each entry's outcome also
reproduces in isolation. Outcomes for a fixed seed may therefore
differ from pre-P-036 runs; the recorded roll is the source of
truth, not the old draw sequence. ``seed=None`` remains the
caller's honest unseeded choice: rolls are drawn from system
entropy and recorded with ``seeded=False``.

``probability`` lives on the candidate as a fraction in [0.0, 1.0];
the stored entry carries it as an integer percent (migration
0028, P-036) and callers convert with
``runmal.lorebooks.rng.probability_fraction`` / the percent
normalisers in that module.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from runmal.lorebooks.rng import ProbabilityRoll, roll_probability
from runmal.tokens import estimate_tokens

__all__ = [
    "estimate_tokens",
    "BudgetCandidate",
    "BudgetedEntry",
    "DiscardedEntry",
    "BudgetResult",
    "resolve_budget",
]


@dataclass(frozen=True)
class BudgetCandidate:
    entry_id: str
    content: str
    priority: int = 100
    probability: float = 1.0

    def __post_init__(self) -> None:
        if isinstance(self.probability, bool) or not isinstance(
            self.probability, (int, float)
        ):
            raise ValueError("probability must be a number in [0.0, 1.0]")
        if not 0.0 <= float(self.probability) <= 1.0:
            raise ValueError("probability must be in [0.0, 1.0]")


@dataclass(frozen=True)
class BudgetedEntry:
    entry_id: str
    tokens: int


@dataclass(frozen=True)
class DiscardedEntry:
    entry_id: str
    tokens: int
    reason: str  # "over_budget" | "probability_skip"


@dataclass(frozen=True)
class BudgetResult:
    included: tuple[BudgetedEntry, ...]
    discarded: tuple[DiscardedEntry, ...]
    budget: int | None
    tokens_used: int
    # P-036: the inspectable roll for every gated candidate
    # (probability < 1.0), in processing (sorted) order. Empty
    # when no candidate was gated. Ungated candidates (probability
    # == 1.0) make no roll and record none.
    rolls: tuple[ProbabilityRoll, ...] = ()


def resolve_budget(
    candidates: list[BudgetCandidate],
    token_budget: int | None,
    seed: int | None = None,
    *,
    context: str = "",
) -> BudgetResult:
    """Resolve which candidates fit.

    Deterministic for a fixed ``seed`` + ``context``: each gated
    candidate's roll derives from (seed, context, entry_id)
    alone, so the outcome reproduces per entry in isolation and
    does not depend on candidate order or on other candidates.
    """
    if token_budget is not None and token_budget < 1:
        raise ValueError("token_budget must be >= 1 or None")
    if not isinstance(context, str):
        raise ValueError("context must be a string")
    ordered = sorted(candidates, key=lambda c: (-c.priority, c.entry_id))

    included: list[BudgetedEntry] = []
    discarded: list[DiscardedEntry] = []
    rolls: list[ProbabilityRoll] = []
    used = 0
    for cand in ordered:
        tokens = estimate_tokens(cand.content)
        if cand.probability < 1.0:
            roll = roll_probability(
                cand.entry_id, float(cand.probability), seed=seed, context=context
            )
            rolls.append(roll)
            if not roll.passed:
                discarded.append(
                    DiscardedEntry(cand.entry_id, tokens, "probability_skip")
                )
                continue
        if token_budget is not None and tokens > token_budget - used:
            discarded.append(DiscardedEntry(cand.entry_id, tokens, "over_budget"))
            continue
        included.append(BudgetedEntry(cand.entry_id, tokens))
        used += tokens
    return BudgetResult(
        included=tuple(included),
        discarded=tuple(discarded),
        budget=token_budget,
        tokens_used=used,
        rolls=tuple(rolls),
    )
