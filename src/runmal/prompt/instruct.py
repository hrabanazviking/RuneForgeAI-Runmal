"""Instruct templates (P-050): chat formats as first-class data.

Until P-050 the tree had no instruct-template concept at all: the
composer emits structured messages (role + content), the backends
ship them to chat APIs, and a preset's ``template_ref`` was an
opaque string naming a registry that did not exist. Nothing in the
tree could say how a conversation should look as raw text for a
model that consumes a single formatted string -- the ChatML /
Llama-3 / Alpaca / Vicuna shapes that decide whether a local model
answers in character or rambles past its turn.

This module makes those shapes data. An :class:`InstructTemplate`
is a declared value, never a code branch:

- ``bos`` -- text emitted once at the very start;
- ``wrappers`` -- per-role ``prefix`` / ``suffix`` around each
  message's content (the literal ``{role}`` in a prefix or suffix
  is replaced with the message's role);
- ``separator`` -- text between consecutive messages;
- ``generation_prefix`` -- text appended after the last message to
  open the assistant's turn (``{role}`` here means ``assistant``);
- ``stop_strings`` -- the template's stop behaviour as data: the
  strings a backend must stop on so the model cannot run past its
  turn into a fabricated next one;
- ``preamble`` -- the format's customary system text, used as the
  system message when the conversation carries none (Alpaca's
  "Below is an instruction..." and Vicuna's "A chat between..."
  are part of those public formats, not content Rúnmál invents).

The builtin shapes are the PUBLIC formats, from their public
specifications: ChatML (the ``<|im_start|>`` / ``<|im_end|>``
turn framing), Llama-3 instruct (``<|begin_of_text|>``,
``<|start_header_id|>`` ... ``<|eot_id|>``), Alpaca
(``### Instruction:`` / ``### Response:``), and Vicuna
(``USER:`` / ``ASSISTANT:`` with ``</s>`` turn ends). No mirror
source was read for any of them (clean-room log, P-050 entry).

Selection is per model and honestly defaulted:
:data:`MODEL_TEMPLATE_DEFAULTS` maps model-name patterns to
templates as data; a model nothing matches -- or no model at
all -- gets :data:`PLAIN`, a template that joins message contents
with blank lines and declares NO wrappers and NO stops, so the
default never invents framing a model was never shown to expect.
Persisting a chosen template per owner/chat is, like P-049's
layout persistence, a named follow-up slice owning its own
migration; P-050 ships the data, the registry, the per-model
defaults, and the rendering path that honours them.
"""

from __future__ import annotations

from dataclasses import dataclass

from runmal.prompt.slots import VALID_ROLES


@dataclass(frozen=True)
class RoleWrapper:
    prefix: str = ""
    suffix: str = ""


@dataclass(frozen=True)
class InstructTemplate:
    name: str
    description: str = ""
    bos: str = ""
    wrappers: tuple[tuple[str, RoleWrapper], ...] = ()
    separator: str = ""
    generation_prefix: str = ""
    stop_strings: tuple[str, ...] = ()
    preamble: str = ""

    def wrapper_for(self, role: str) -> RoleWrapper:
        for name, wrapper in self.wrappers:
            if name == role:
                return wrapper
        return RoleWrapper()

def _wrappers(**by_role) -> tuple[tuple[str, RoleWrapper], ...]:
    """Build a wrappers tuple from role=(prefix, suffix) pairs."""
    return tuple(
        (role, RoleWrapper(prefix, suffix))
        for role, (prefix, suffix) in by_role.items()
    )


#: The honest default: contents joined by blank lines, no invented
#: framing, no stops. Unknown models get exactly this.
PLAIN = InstructTemplate(
    name="plain",
    description="Message contents joined by blank lines; no wrappers, no stops.",
    wrappers=_wrappers(
        system=("", ""), user=("", ""), assistant=("", "")
    ),
    separator="\n\n",
)

#: ChatML: every turn is <|im_start|>role, content, <|im_end|>.
CHATML = InstructTemplate(
    name="chatml",
    description="ChatML turn framing (<|im_start|>/<|im_end|>).",
    wrappers=_wrappers(
        system=("<|im_start|>{role}\n", "<|im_end|>\n"),
        user=("<|im_start|>{role}\n", "<|im_end|>\n"),
        assistant=("<|im_start|>{role}\n", "<|im_end|>\n"),
    ),
    generation_prefix="<|im_start|>assistant\n",
    stop_strings=("<|im_end|>", "<|im_start|>"),
)

#: Llama-3 instruct: header-id role blocks closed by <|eot_id|>.
LLAMA3 = InstructTemplate(
    name="llama3",
    description="Llama-3 instruct header framing (<|start_header_id|>/<|eot_id|>).",
    bos="<|begin_of_text|>",
    wrappers=_wrappers(
        system=("<|start_header_id|>{role}<|end_header_id|>\n\n", "<|eot_id|>"),
        user=("<|start_header_id|>{role}<|end_header_id|>\n\n", "<|eot_id|>"),
        assistant=("<|start_header_id|>{role}<|end_header_id|>\n\n", "<|eot_id|>"),
    ),
    generation_prefix="<|start_header_id|>assistant<|end_header_id|>\n\n",
    stop_strings=("<|eot_id|>", "<|end_of_text|>"),
)

#: Alpaca: ### Instruction: / ### Response: sections; the format's
#: customary preamble serves as system text when none is carried.
ALPACA = InstructTemplate(
    name="alpaca",
    description="Alpaca instruction/response sections.",
    wrappers=_wrappers(
        system=("", "\n\n"),
        user=("### Instruction:\n", "\n\n"),
        assistant=("### Response:\n", "\n\n"),
    ),
    generation_prefix="### Response:\n",
    stop_strings=("### Instruction:", "### Response:"),
    preamble=(
        "Below is an instruction that describes a task. "
        "Write a response that appropriately completes the request."
    ),
)

#: Vicuna: USER:/ASSISTANT: turns, assistant turns closed by </s>;
#: the format's customary system text when none is carried.
VICUNA = InstructTemplate(
    name="vicuna",
    description="Vicuna USER:/ASSISTANT: turns closed by </s>.",
    wrappers=_wrappers(
        system=("", "\n\n"),
        user=("USER: ", "\n"),
        assistant=("ASSISTANT: ", "</s>\n"),
    ),
    generation_prefix="ASSISTANT: ",
    stop_strings=("</s>", "USER:"),
    preamble=(
        "A chat between a curious user and an artificial "
        "intelligence assistant. The assistant gives helpful, "
        "detailed, and polite answers to the user's questions."
    ),
)

#: Builtin registry, in presentation order.
BUILTIN_TEMPLATES: tuple[InstructTemplate, ...] = (
    PLAIN, CHATML, LLAMA3, ALPACA, VICUNA,
)
TEMPLATE_ORDER: tuple[str, ...] = tuple(t.name for t in BUILTIN_TEMPLATES)
_BY_NAME: dict[str, InstructTemplate] = {t.name: t for t in BUILTIN_TEMPLATES}

#: Per-model defaults as data: (lowercase substring of the model
#: name, template name), first match wins. A model matching
#: nothing -- or no model at all -- falls through to PLAIN.
MODEL_TEMPLATE_DEFAULTS: tuple[tuple[str, str], ...] = (
    ("llama-3", "llama3"),
    ("llama3", "llama3"),
    ("vicuna", "vicuna"),
    ("alpaca", "alpaca"),
    ("chatml", "chatml"),
    ("qwen", "chatml"),
)


def get_template(name: str) -> InstructTemplate:
    """The builtin template called ``name``; ValueError if none."""
    template = _BY_NAME.get(name)
    if template is None:
        raise ValueError(f"unknown instruct template: {name!r}")
    return template


def list_templates() -> tuple[InstructTemplate, ...]:
    return BUILTIN_TEMPLATES


def default_template_for_model(model_id: str | None) -> InstructTemplate:
    """The honestly-defaulted template for a model name."""
    if model_id:
        lowered = model_id.lower()
        for pattern, template_name in MODEL_TEMPLATE_DEFAULTS:
            if pattern in lowered:
                return _BY_NAME[template_name]
    return PLAIN


_TEMPLATE_KEYS = frozenset({
    "name", "description", "bos", "wrappers", "separator",
    "generation_prefix", "stop_strings", "preamble",
})
_TEXT_KEYS = ("description", "bos", "separator", "generation_prefix", "preamble")


def template_to_data(template: InstructTemplate) -> dict:
    return {
        "name": template.name,
        "description": template.description,
        "bos": template.bos,
        "wrappers": {
            role: {"prefix": w.prefix, "suffix": w.suffix}
            for role, w in template.wrappers
        },
        "separator": template.separator,
        "generation_prefix": template.generation_prefix,
        "stop_strings": list(template.stop_strings),
        "preamble": template.preamble,
    }


def template_from_data(data: object) -> InstructTemplate:
    """Validate + build a template from API/stored data.

    Mirrors :func:`runmal.prompt.manager.layout_from_data`: bad
    shapes raise ValueError (the API maps it to 422). Unknown keys
    and unknown roles fail rather than being silently dropped, so
    a misspelled wrapper is never a template that quietly renders
    without it.
    """
    if not isinstance(data, dict):
        raise ValueError("instruct template must be an object")
    unknown = set(data) - _TEMPLATE_KEYS
    if unknown:
        raise ValueError(f"unknown instruct template keys: {sorted(unknown)}")
    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError("instruct template name must be a non-empty string")
    text: dict[str, str] = {}
    for key in _TEXT_KEYS:
        value = data.get(key, "")
        if not isinstance(value, str):
            raise ValueError(f"instruct template {key} must be a string")
        text[key] = value
    raw_wrappers = data.get("wrappers", {})
    if not isinstance(raw_wrappers, dict):
        raise ValueError("instruct template wrappers must be an object")
    wrappers: list[tuple[str, RoleWrapper]] = []
    for role, raw in raw_wrappers.items():
        if role not in VALID_ROLES:
            raise ValueError(f"unknown instruct template role: {role!r}")
        if not isinstance(raw, dict) or set(raw) - {"prefix", "suffix"}:
            raise ValueError(f"wrapper for role {role!r} must be an object with prefix/suffix")
        prefix, suffix = raw.get("prefix", ""), raw.get("suffix", "")
        if not isinstance(prefix, str) or not isinstance(suffix, str):
            raise ValueError(f"wrapper for role {role!r} prefix/suffix must be strings")
        wrappers.append((role, RoleWrapper(prefix, suffix)))
    stops = data.get("stop_strings", [])
    if not isinstance(stops, list) or not all(isinstance(s, str) for s in stops):
        raise ValueError("instruct template stop_strings must be a list of strings")
    return InstructTemplate(
        name=name, wrappers=tuple(wrappers),
        stop_strings=tuple(stops), **text,
    )
