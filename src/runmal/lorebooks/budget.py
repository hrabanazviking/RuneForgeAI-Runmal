"""Token budget + priority resolution for lorebook candidates (S204).

Pure-domain module: no DB, no I/O. After S202 (scan) and S203 (activation)
produce candidate entries, this module decides which ones fit in the token
budget.

Token counting: :func:`estimate_tokens` is a deterministic heuristic
(``max(1, len(text) // 4)``). It is an *estimate* -- good enough for budget
decisions, cheap, and dependency-free. A real tokenizer can replace it
later without changing this module's contract (S214's trace records which
estimator was used).

Resolution algorithm (deterministic):
1. Candidates sort by priority descending; equal priorities tie-break by
   entry id ascending. The tie-break is stable: the same input set always
   yields the same order.
2. In that order, each candidate first faces its probability gate (if
   ``probability < 1.0``): a draw from ``random.Random(seed)``; a failed
   draw discards it with reason ``"probability_skip"``. With a fixed seed
   the draws -- and therefore the outcome -- are identical every run.
   (``seed=None`` leaves the RNG unseeded: callers that need
   reproducibility must pass a seed.)
3. Survivors are greedily packed: a candidate whose estimated tokens exceed
   the remaining budget is discarded with reason ``"over_budget"``;
   smaller later candidates can still fit.
4. ``token_budget=None`` means unlimited: everything that passes its
   probability gate is included.

``probability`` lives on the candidate, not (yet) on the stored entry:
persistence of per-entry probability is a future slice's concern.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field


def estimate_tokens(text: str) -> int:
    """Deterministic token estimate for budget decisions."""
    if not isinstance(text, str):
        raise ValueError("text must be a string")
    return max(1, len(text) // 4)


@dataclass(frozen=True)
class BudgetCandidate:
    entry_id: str
    content: str
    priority: int = 100
    probability: float = 1.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.probability <= 1.0:
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


def resolve_budget(
    candidates: list[BudgetCandidate],
    token_budget: int | None,
    seed: int | None = None,
) -> BudgetResult:
    """Resolve which candidates fit. Deterministic for a fixed seed."""
    if token_budget is not None and token_budget < 1:
        raise ValueError("token_budget must be >= 1 or None")
    rng = random.Random(seed)
    ordered = sorted(candidates, key=lambda c: (-c.priority, c.entry_id))

    included: list[BudgetedEntry] = []
    discarded: list[DiscardedEntry] = []
    used = 0
    for cand in ordered:
        tokens = estimate_tokens(cand.content)
        if cand.probability < 1.0 and rng.random() >= cand.probability:
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
    )
