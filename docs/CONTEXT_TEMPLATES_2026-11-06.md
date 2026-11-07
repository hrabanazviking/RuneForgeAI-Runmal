# Context templates: story-string assembly as data (P-051) — 2026-11-06

Roadmap line: *Context templates: story-string/context assembly
formats imported and editable (P-021's presets land here).*
Part IV (Prompt & Sampler Depth). Census basis: ST-32 (context
template / story string — a template assembling the preamble
from named anchors, with example separators, a chat-start
separator, and separators optionally acting as stop strings),
recorded from public behaviour in the in-tree census; no mirror
source was read (clean-room log, P-051 entry).

## What was built

- `src/runmal/prompt/context.py` — context templates as
  first-class editable data, in the P-049/P-050 spirit. A
  `ContextTemplate` is an ordered tuple of `ContextSegment`
  rows — one per assembly anchor, each carrying `enabled`,
  `prefix` and `suffix` — plus a `separator` between segments,
  an `example_separator`, a `chat_start_separator`, and
  `stops_from_separators` (the census ST-32 separator
  behaviours as data). Anchors are position-faithful to the
  S205 slot kinds, so lore and memory appear at both of their
  baseline positions exactly as P-049's blocks do:
  `system` (main_system), `persona`, `memory_nucleus`,
  `world_before` (lore_before), `memory_retrieved`,
  `examples`, `history`, `world_after` (lore_after),
  `authors_note`, `post_history`.
  - `context_from_data` / `context_to_data` validate and
    serialise the API shape (unknown keys/anchors, duplicates
    and bad types raise `ValueError`); anchors the data does
    not mention fill in ENABLED at their baseline-relative
    positions (the P-049 fill rule — a partial edit never
    silently drops the rest of the assembly).
  - Story-string form: `to_story_string` renders a template
    as `{{anchor}}` placeholders joined by its separator,
    with segment prefixes/suffixes as the literal text around
    them; `from_story_string` parses that form back (aliases
    `main`, `worldInfoBefore`, `worldInfoAfter`,
    `chatHistory`, `dialogueExamples`, `mesExamples`,
    `authorsNote` accepted — spellings from the in-tree
    census and P-005/P-021 fixtures). A story string is the
    WHOLE assembly: anchors it does not mention fill in
    DISABLED, the deliberate asymmetry with the JSON fill
    rule. Unknown or duplicated placeholders raise.
  - `apply_context_template` rewrites a slot list through a
    template before composition, mirroring
    `manager.apply_layout` (segment-position order arithmetic,
    the S206 depth guard keyed on the history slot's assigned
    order, unmanaged kinds on the tail): a disabled segment's
    slots are dropped for the trace to record with reason
    `context_template_disabled`, and segment prefix/suffix
    wrap the slot's content (a splittable history slot wraps
    its first/last parts; the chat-start separator prefixes
    the history segment).
  - There is NO second render path: story-string assembly
    IS `apply_context_template` + the composer + the P-050
    render, and this module never flattens content itself.
    `example_separator` is carried data only in P-051 — it
    has no apply effect (the examples slot arrives
    pre-joined), exactly as P-050 left stop-string wiring
    to P-052. When `stops_from_separators` is set, the
    non-empty separators are the template's stop strings,
    surfaced as data in the echo only.
  - `context_template_from_preset` is where P-021's presets
    land: given an `ImportedPreset` or a stored preset dict,
    a carried `context_template` (a data dict, or a string
    parsed as a story string) wins — looked for at the top
    level first, then in the carried `raw` — then a carried
    `story_string`, then the `prompt_order` carriage maps
    onto anchors — `main` →
    system, `worldInfoBefore`/`worldInfoAfter` →
    world_before/world_after, `personaDescription` /
    `charDescription` / `charPersonality` / `scenario` →
    persona (first occurrence wins: position and enabled
    flag), `dialogueExamples` → examples, `chatHistory` →
    history, `jailbreak` → post_history.
    `enhanceDefinitions` is deliberately unmapped: it is an
    auxiliary definitions block, not a character field, and
    mapping it to persona would enable that segment on its
    say-so alone. Anchors no identifier names fill ENABLED
    at their baseline-relative positions (the P-049 fill
    rule: a prompt_order may be partial — character-scoped
    orders name only the rows they move — so an unmentioned
    anchor keeps its baseline place rather than vanishing;
    fill-DISABLED belongs to story strings alone, where the
    text is the whole document). When the flat order maps
    nothing, a grouped raw `prompt_order` (entries carrying
    an `order` list) is flattened and tried. A preset
    carrying nothing mappable returns None. Prompt CONTENT is
    never copied into a template: the prompt manager owns
    content blocks; P-051 owns assembly shape only.
  - The DEFAULT template lists every anchor enabled in
    baseline order with empty framing and empty separators,
    and applying it reproduces today's assembly exactly
    (composer order, contents, and the plain render all
    pinned by the battery) — the honest default, like
    P-050's PLAIN.
- The inspector also accepts preset DATA directly
  (`context_preset` — a stored preset dict or imported
  preset shape supplied by the caller), so the preset tier
  of the resolution is reachable through the honoured path
  with no database coupling; looking a preset up by id is
  P-054 bundle territory and is not built here.
- `src/runmal/prompt/service.py` — `resolve_context_template
  (explicit, preset)`: precedence explicit (builtin name, a
  story string, or full template data) > preset-derived >
  nothing in play, reported as `(None, "default")` so the
  no-template pipeline stays byte-identical to pre-P-051.
  `context_echo` builds the whitelist echo: source, one
  `{anchor, enabled}` row per segment, and the derived stop
  strings — no affix or separator literals, no content.
- `src/runmal/prompt/inspect.py` — the inspector honours the
  template: `inspect_prompt(..., context_template=None)`
  applies it AFTER the P-049 layout (layout governs block
  order/toggles; the context template governs assembly
  segments and their literal framing), records disabled
  segments as trace discards, and the result carries the
  `context_template` echo. The assembled/rendered TEXT never
  enters the result (S214 contract).
- `src/runmal/prompt/router.py` — `POST /debug/prompt-inspect`
  gains an optional `context_template` field (invalid data is
  a 422 through the existing ValueError mapping); new
  `GET /debug/context-templates` lists the registry as data
  and `GET /debug/context-templates/default` returns the
  resolved default echo plus its story-string form.

## Finisher reconciliation (2026-11-06)

The inherited build followed the lead sketch in four places
where the designer review (hidden_files/P051_DESIGN.md,
corrections C1/C5/C6 + S5/S6) had pinned the corrected form;
the finisher reconciled them before banking: the default
template's separators are empty (C1) and `example_separator`
has no apply effect; the sketch's direct-assembly helper (a
second render path) was removed (S6); the echo is the pinned
whitelist shape (S6); preset precedence is context_template
> story_string > prompt_order with top-level lookup before
`raw`, and `jailbreak` maps unconditionally (S5). One real
bug fell out of the review: the inspector applied the
resolved template only when the raw `context_template`
request field was present, so a preset-tier template was
echoed but never applied — the apply condition now keys on
the resolved template, and the battery pins the preset tier
end-to-end through the API.

## Scope notes

- NO migration (head stays 0032): like P-049/P-050, the
  template is request/service data. Persisting a chosen
  context template per owner or per chat is a named
  follow-up slice owning its own migration.
- Samplers are P-052 (the separators-as-stops set is
  returned as data here; wiring stops into a backend's
  sampling request is P-052's surface) and presets as
  bundles are P-054 (the preset import above is a pure
  derivation over P-021's carriage; no preset storage or
  router shape changed).
- Wrapping is idempotent (a fragment already carrying its
  segment prefix/suffix is not wrapped again), so applying
  a template twice is stable; P-049's order-only rewrite
  needed no such guard. One honest seam: the composer trims
  a splittable history slot's OLDEST parts first, and the
  prefix rides the first part — a history trimmed past its
  first part loses the chat-start framing with it, exactly
  as a depth splice already rewrites history parts.
- Carried finding F1 (P-049/P-050) stands: `tools/service.py`
  compose_preview is stateless and resolves neither layouts,
  instruct templates, nor context templates; the inspector
  is the honoured path.
