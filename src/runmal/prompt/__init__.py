"""Prompt template engine public surface (S205)."""

from runmal.prompt.composer import (
    ComposedMessage,
    ComposedPrompt,
    ImpossiblePromptError,
    PromptManifest,
    SlotDiscard,
    SlotUsage,
    compose,
)
from runmal.prompt.slots import (
    BASELINE_ORDER,
    Slot,
    baseline_order,
    make_slot,
    slot_text,
    slot_tokens,
)

__all__ = [
    "BASELINE_ORDER",
    "ComposedMessage",
    "ComposedPrompt",
    "ImpossiblePromptError",
    "PromptManifest",
    "Slot",
    "SlotDiscard",
    "SlotUsage",
    "baseline_order",
    "compose",
    "make_slot",
    "slot_text",
    "slot_tokens",
]
