"""Prompt template engine public surface (S205; P-050 instruct; P-051 context)."""

from runmal.prompt.authors_note import (
    FREQUENCY_REASON,
    AuthorsNote,
    has_content,
    is_active_for,
    note_from_data,
    note_to_data,
    slot_for,
)
from runmal.prompt.context import (
    BUILTIN_CONTEXT_TEMPLATES,
    CONTEXT_TEMPLATE_ORDER,
    SEGMENT_KINDS,
    SEGMENT_ORDER,
    ContextSegment,
    ContextTemplate,
    apply_context_template,
    context_from_data,
    context_to_data,
    context_template_from_preset,
    default_context_template,
    from_story_string,
    get_context_template,
    list_context_templates,
    to_story_string,
)
from runmal.prompt.context import (
    DISABLED_REASON as CONTEXT_DISABLED_REASON,
)
from runmal.prompt.composer import (
    ComposedMessage,
    ComposedPrompt,
    ImpossiblePromptError,
    PromptManifest,
    SlotDiscard,
    SlotUsage,
    compose,
)
from runmal.prompt.instruct import (
    BUILTIN_TEMPLATES,
    MODEL_TEMPLATE_DEFAULTS,
    TEMPLATE_ORDER,
    InstructTemplate,
    RoleWrapper,
    default_template_for_model,
    get_template,
    list_templates,
    template_from_data,
    template_to_data,
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
from runmal.prompt.post_history import (
    PostHistoryInstructions,
    instructions_from_data,
    instructions_to_data,
)
from runmal.prompt.post_history import has_content as post_history_has_content
from runmal.prompt.post_history import slot_for as post_history_slot_for
from runmal.prompt.render import RenderedPrompt, render_prompt
from runmal.prompt.slots import (
    BASELINE_ORDER,
    Slot,
    baseline_order,
    make_slot,
    slot_text,
    slot_tokens,
)

__all__ = [
    "AuthorsNote", "FREQUENCY_REASON", "has_content", "is_active_for", "note_from_data", "note_to_data", "slot_for",
    "PostHistoryInstructions", "instructions_from_data", "instructions_to_data", "post_history_has_content", "post_history_slot_for",
    "CONTEXT_TEMPLATE_ORDER", "SEGMENT_KINDS", "SEGMENT_ORDER", "BUILTIN_CONTEXT_TEMPLATES", "CONTEXT_DISABLED_REASON", "ContextSegment", "ContextTemplate", "apply_context_template", "context_from_data", "context_to_data", "context_template_from_preset", "default_context_template", "from_story_string", "get_context_template", "list_context_templates", "to_story_string",
    "TEMPLATE_ORDER",
    "RoleWrapper",
    "RenderedPrompt",
    "MODEL_TEMPLATE_DEFAULTS",
    "InstructTemplate",
    "BUILTIN_TEMPLATES",
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
    "template_to_data",
    "template_from_data",
    "render_prompt",
    "list_templates",
    "get_template",
    "default_template_for_model",
    "make_slot",
    "slot_text",
    "slot_tokens",
]
