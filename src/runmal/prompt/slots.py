"""Typed prompt slots (S205).

A slot is the composer's unit of prompt material. Baseline order follows
PROMPT_COMPOSER.md §2; a preset may reorder explicitly by assigning
different ``order`` values -- ordering stays data, never hidden branches.

Roles are limited to ``system`` / ``user`` / ``assistant`` (provider
equivalents map at the backend seam, never here).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from runmal.tokens import estimate_tokens

VALID_ROLES = frozenset({"system", "user", "assistant"})

# Baseline conceptual order (PROMPT_COMPOSER.md §2).
BASELINE_ORDER = (
    "main_system",
    "persona",
    "memory_nucleus",
    "lore_before",
    "memory_retrieved",
    "examples",
    "history",
    "lore_after",
    "authors_note",
    "post_history",
)

BASELINE_INDEX = {kind: i for i, kind in enumerate(BASELINE_ORDER)}


@dataclass(frozen=True)
class Slot:
    id: str
    kind: str
    role: str
    content: str = ""
    order: int = 500
    priority: int = 100
    required: bool = False
    # Hard per-slot token cap; the slot is discarded (never truncated)
    # when its full text exceeds it. None = no cap.
    slot_budget: int | None = None
    provenance: str = ""
    # Splittable slots (conversation history): parts are packed newest-first
    # and oldest parts trim first on overflow.
    splittable: bool = False
    parts: tuple[str, ...] = ()
    # Depth injection (S206): when set, this slot is spliced N messages from
    # the end of the surviving history parts instead of taking its normal
    # order position. None = normal ordered slot.
    depth: int | None = None

    def __post_init__(self) -> None:
        if self.role not in VALID_ROLES:
            raise ValueError(f"invalid role: {self.role!r}")
        if self.slot_budget is not None and self.slot_budget < 1:
            raise ValueError("slot_budget must be >= 1 or None")
        if self.splittable and not self.parts:
            raise ValueError("splittable slots require parts")
        if self.depth is not None and self.depth < 0:
            raise ValueError("depth must be >= 0 or None")


def baseline_order(kind: str) -> int:
    """Baseline order index for a slot kind; unknown kinds sort last."""
    return BASELINE_INDEX.get(kind, len(BASELINE_ORDER))


def slot_text(slot: Slot) -> str:
    if slot.splittable:
        return "\n".join(slot.parts)
    return slot.content


def slot_tokens(slot: Slot) -> int:
    return estimate_tokens(slot_text(slot))


def make_slot(kind: str, role: str, content: str, **kw) -> Slot:
    """Convenience: baseline order filled in from the kind."""
    kw.setdefault("order", baseline_order(kind))
    return Slot(kind=kind, role=role, content=content, **kw)
