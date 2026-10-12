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


def _depth_inject(
    slot: Slot,
    messages: list[ComposedMessage],
    included: list[SlotUsage],
    discarded: list[SlotDiscard],
    history_ref: tuple[int, list[str], int] | None,
    used: int,
    input_budget: int,
) -> tuple[int | None, tuple[int, list[str], int] | None]:
    """S206: splice a depth-note N messages from the end of history.

    Returns ``(tokens_consumed, new_history_ref)``. ``tokens_consumed`` is
    None when there is no history to splice into (caller emits normally).
    """
    tokens = estimate_tokens(slot.content)
    if history_ref is None:
        return None, None
    if tokens > input_budget - used:
        discarded.append(SlotDiscard(slot.id, tokens, "over_input_budget"))
        return 0, history_ref
    msg_idx, parts, usage_idx = history_ref
    split_at = max(0, len(parts) - slot.depth)
    head, tail = parts[:split_at], parts[split_at:]
    hist_msg = messages[msg_idx]
    replacement: list[ComposedMessage] = []
    if head:
        replacement.append(
            ComposedMessage(hist_msg.role, "\n".join(head), hist_msg.slot_id)
        )
    replacement.append(ComposedMessage(slot.role, slot.content, slot.id))
    tail_idx: int | None = None
    if tail:
        tail_idx = msg_idx + (1 if head else 0) + 1
        replacement.append(
            ComposedMessage(hist_msg.role, "\n".join(tail), hist_msg.slot_id)
        )
    messages[msg_idx : msg_idx + 1] = replacement
    hist_tokens = sum(estimate_tokens("\n".join(p)) for p in (head, tail) if p)
    old_usage = included[usage_idx]
    included[usage_idx] = SlotUsage(
        old_usage.slot_id, hist_tokens, trimmed_parts=old_usage.trimmed_parts
    )
    included.append(SlotUsage(slot.id, tokens))
    new_ref = (
        (tail_idx, tail, usage_idx) if tail_idx is not None else None
    )
    return tokens, new_ref


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
    # S206: (message index, surviving parts, usage index) of the history
    # slot, so depth-notes can splice N messages from its end.
    history_ref: tuple[int, list[str], int] | None = None

    for slot in ordered:
        if slot.slot_budget is not None and slot_tokens(slot) > slot.slot_budget:
            discarded.append(
                SlotDiscard(slot.id, slot_tokens(slot), "over_slot_budget")
            )
            continue
        if slot.depth is not None:
            consumed, history_ref = _depth_inject(
                slot, messages, included, discarded, history_ref, used,
                input_budget,
            )
            if consumed is None:
                pass  # no history: fall through to normal emission
            else:
                used += consumed
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
            if slot.kind == "history" and history_ref is None:
                history_ref = (len(messages) - 1, parts, len(included) - 1)
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
