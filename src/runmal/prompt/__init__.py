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
from runmal.prompt.manager import (
    BLOCK_KINDS,
    BLOCK_ORDER,
    DISABLED_REASON,
    PromptBlock,
    PromptLayout,
    apply_layout,
    block_for_kind,
    default_layout,
    layout_from_data,
    layout_to_data,
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
    "BLOCK_KINDS",
    "BLOCK_ORDER",
    "DISABLED_REASON",
    "PromptBlock",
    "PromptLayout",
    "ComposedMessage",
    "ComposedPrompt",
    "ImpossiblePromptError",
    "PromptManifest",
    "Slot",
    "SlotDiscard",
    "SlotUsage",
    "apply_layout",
    "block_for_kind",
    "default_layout",
    "layout_from_data",
    "layout_to_data",
    "baseline_order",
    "compose",
    "make_slot",
    "slot_text",
    "slot_tokens",
]
