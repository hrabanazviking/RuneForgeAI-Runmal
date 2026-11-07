# Instruct templates: public chat formats as data (P-050) — 2026-11-06

Roadmap line: *Instruct templates: the public template shapes
(ChatML, Llama-3, Alpaca, Vicuna…) as data, per-model selectable.*
Part IV (Prompt & Sampler Depth).

## What was built

- `src/runmal/prompt/instruct.py` — instruct templates as
  first-class data. An `InstructTemplate` declares: `bos`
  (emitted once), per-role `wrappers` (`prefix`/`suffix` around
  each message's content; the literal `{role}` is replaced with
  the message's role), `separator` between messages,
  `generation_prefix` (appended to open the assistant's turn),
  `stop_strings` (the template's stop behaviour as data), and
  `preamble` (the format's customary system text, used when the
  conversation carries no system message). Builtins, from the
  PUBLIC format specifications:
  - `plain` — the honest default: contents joined by blank
    lines, no wrappers, no stops. A model nothing is known
    about gets exactly this; the default never invents framing.
  - `chatml` — `<|im_start|>{role}\n … <|im_end|>\n` turns,
    generation prefix `<|im_start|>assistant\n`, stops
    `<|im_end|>` / `<|im_start|>`.
  - `llama3` — `<|begin_of_text|>`,
    `<|start_header_id|>{role}<|end_header_id|>\n\n … <|eot_id|>`
    turns, stops `<|eot_id|>` / `<|end_of_text|>`.
  - `alpaca` — `### Instruction:` / `### Response:` sections
    with the format's customary "Below is an instruction…"
    preamble as system text when none is carried.
  - `vicuna` — `USER:` / `ASSISTANT:` turns, assistant turns
    closed by `</s>`, with the format's customary "A chat
    between a curious user…" preamble likewise.
  `template_from_data` / `template_to_data` validate and
  serialise the API shape (unknown keys, unknown roles and bad
  types raise `ValueError` — a misspelled wrapper is never
  silently dropped). `MODEL_TEMPLATE_DEFAULTS` is per-model
  selection as data: (lowercase model-name substring → template)
  pairs, first match wins — llama-3/llama3 → llama3, vicuna →
  vicuna, alpaca → alpaca, chatml/qwen → chatml, everything else
  (or no model) → plain.
- `src/runmal/prompt/render.py` — the rendering path:
  `render_prompt(messages, template)` flattens structured
  messages (composer `ComposedMessage`, backend `ChatMessage`,
  or plain mappings) into one model-facing string through the
  selected template and returns the template's stop strings
  alongside it, so stop behaviour travels with the render.
- `src/runmal/prompt/service.py` — `resolve_template(explicit,
  model_id)`: precedence explicit (builtin name, or a full
  custom template as data) > per-model default > plain.
  `template_echo` builds the metadata-only result echo.
- `src/runmal/prompt/inspect.py` — the inspector honours the
  selection: `inspect_prompt(..., model_id=None,
  instruct_template=None)` resolves the template, renders the
  composed messages through it, and the result carries
  `instruct_template: {name, source, stop_strings}` plus
  `rendered_tokens` (the rendered string's own token estimate,
  so framing cost is visible before sending). The rendered TEXT
  never enters the result — the S214 trace contract (traces
  carry no prompt content) outranks the convenience, and the
  battery pins that no content or content-framing leaks.
- `src/runmal/prompt/router.py` — `POST /debug/prompt-inspect`
  gains optional `model_id` / `instruct_template` fields (an
  unknown name or invalid template data is a 422); new
  `GET /debug/instruct-templates` lists the registry as data
  and `GET /debug/instruct-templates/default?model=…` returns
  the resolved default for a model.
- `src/runmal/presets/service.py` — docstring only: the
  `template_ref` note that called this registry "a future
  slice's work" now records that P-050 built it. The preset
  still carries the reference as a plain string; resolving it
  stays the render path's job.

## Scope notes

- NO migration (head stays 0032): like P-049, the selection is
  request/service data. Persisting a chosen template per owner
  or per chat is a named follow-up slice owning its own
  migration — not faked here.
- Context templates (story-string assembly) are P-051 and
  sampler surfaces are P-052; neither is built here. The
  template's stop strings are data the render returns; wiring
  them into a specific backend's sampling request is P-052's
  surface, not this slice's.
- Carried finding F1 (P-049): `tools/service.py`
  compose_preview is stateless and resolves neither layouts
  nor instruct templates; the inspector is the honoured path.
- Stop behaviour contract (designer review, accepted): the
  template's `stop_strings` are its DECLARED format stops.
  When a generation layer (P-052) also carries user/preset
  stops, the two sets MERGE (union) — a selected template
  never silently discards a caller's stops, and caller stops
  never replace the format stops a model needs to end its
  turn. This slice returns the set as data; the merge lands
  with the sampler surface that consumes it.
- Format variants (designer review, recorded): each builtin
  pins the format's canonical published form (Vicuna v1.x
  USER:/ASSISTANT:, Alpaca instruction/response without the
  optional `### Input:` section). Family variants are new
  registry entries when a slice needs them, not parameters
  of these entries.
