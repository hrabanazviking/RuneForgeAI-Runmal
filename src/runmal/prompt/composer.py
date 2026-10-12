"""Prompt template engine (S205).

The Prompt Composer is the only domain that turns persona, lore, memory,
examples, history and instructions into model-facing messages
(PROMPT_COMPOSER.md). Other subsystems provide structured candidates; they
never secretly append text.

Composition contract:
1. Determine the model context limit (or a conservative configured limit).
2. FIRST reserve the response budget, then provider/system overhead.
3. The remainder is the input budget; slots are admitted against it.
4. Slots are typed and ordered (see :mod:`runmal.prompt.slots`).
5. Overflow is deterministic: required slots stay (or the request is
   declared impossible); optional slots admit greedily by
   ``(order, -priority, id)``; splittable slots (history) trim oldest
   parts first; every discard records a reason for the Prompt Trace
   (S214).

The composer never exceeds ``context_limit - reserved_response - overhead``
input tokens. Golden tests assert this on fixed manifests.
"""

from __future__ import annotations

from dataclasses import dataclass

from runmal.prompt.slots import Slot, slot_text, slot_tokens
from runmal.tokens import TokenQuality, estimate_tokens


class ImpossiblePromptError(ValueError):
    """Required slots alone exceed the effective input budget."""


@dataclass(frozen=True)
class ComposedMessage:
    role: str
    content: str
    slot_id: str


@dataclass(frozen=True)
class SlotUsage:
    slot_id: str
    tokens: int
    trimmed_parts: int = 0  # splittable slots: how many oldest parts dropped


@dataclass(frozen=True)
class SlotDiscard:
    slot_id: str
    tokens: int
    reason: str  # "over_input_budget" | "over_slot_budget"


@dataclass(frozen=True)
class PromptManifest:
    context_limit: int
    reserved_response: int
    overhead: int
    input_budget: int
    total_input_tokens: int
    count_quality: TokenQuality
    included: tuple[SlotUsage, ...]
    discarded: tuple[SlotDiscard, ...]


@dataclass(frozen=True)
class ComposedPrompt:
    messages: tuple[ComposedMessage, ...]
    manifest: PromptManifest


def _order_key(slot: Slot) -> tuple:
    return (slot.order, -slot.priority, slot.id)


def compose(
    slots: list[Slot],
    context_limit: int,
    reserve_response: int,
    overhead: int = 0,
) -> ComposedPrompt:
    """Compose model-facing messages from ordered slots."""
    if context_limit < 1:
        raise ValueError("context_limit must be >= 1")
    if reserve_response < 0:
        raise ValueError("reserve_response must be >= 0")
    if overhead < 0:
        raise ValueError("overhead must be >= 0")
    input_budget = context_limit - reserve_response - overhead
    if input_budget < 1:
        raise ImpossiblePromptError(
            "no input budget remains after reservation"
        )

    required = [s for s in slots if s.required]
    required_tokens = sum(slot_tokens(s) for s in required)
    if required_tokens > input_budget:
        raise ImpossiblePromptError(
            f"required slots need {required_tokens} tokens "
            f"but only {input_budget} are available"
        )

    ordered = sorted(slots, key=_order_key)
    messages: list[ComposedMessage] = []
    included: list[SlotUsage] = []
    discarded: list[SlotDiscard] = []
    used = 0

    for slot in ordered:
        if slot.slot_budget is not None and slot_tokens(slot) > slot.slot_budget:
            discarded.append(
                SlotDiscard(slot.id, slot_tokens(slot), "over_slot_budget")
            )
            continue
        if slot.splittable and slot.parts:
            # Newest-first packing: drop oldest parts until it fits.
            parts = list(slot.parts)
            trimmed = 0
            while parts and estimate_tokens("\n".join(parts)) > input_budget - used:
                parts.pop(0)
                trimmed += 1
            if not parts:
                discarded.append(
                    SlotDiscard(slot.id, slot_tokens(slot), "over_input_budget")
                )
                continue
            text = "\n".join(parts)
            tokens = estimate_tokens(text)
            used += tokens
            messages.append(ComposedMessage(slot.role, text, slot.id))
            included.append(SlotUsage(slot.id, tokens, trimmed_parts=trimmed))
            continue
        tokens = slot_tokens(slot)
        if tokens > input_budget - used:
            discarded.append(
                SlotDiscard(slot.id, tokens, "over_input_budget")
            )
            continue
        used += tokens
        messages.append(ComposedMessage(slot.role, slot_text(slot), slot.id))
        included.append(SlotUsage(slot.id, tokens))

    manifest = PromptManifest(
        context_limit=context_limit,
        reserved_response=reserve_response,
        overhead=overhead,
        input_budget=input_budget,
        total_input_tokens=used,
        count_quality=TokenQuality.ESTIMATED,
        included=tuple(included),
        discarded=tuple(discarded),
    )
    assert used <= input_budget  # the acceptance invariant, enforced
    return ComposedPrompt(messages=tuple(messages), manifest=manifest)
