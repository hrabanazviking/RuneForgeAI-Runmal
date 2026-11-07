# Prompt manager: ordered, toggleable prompt blocks (P-049) — 2026-11-06

Roadmap line: *Prompt manager: ordered, toggleable prompt blocks
(system, persona, lore, memory, author's note, examples) as a
first-class editable structure.* Part IV (Prompt & Sampler Depth),
opener.

## What was built

- `src/runmal/prompt/manager.py` — the prompt manager proper.
  A `PromptLayout` is data: an ordered tuple of `PromptBlock`
  rows (`block`, `enabled`). Nine blocks, position-faithful to
  the composer's baseline: `system` (main_system), `persona`,
  `memory_nucleus`, `lore_before`, `memory_retrieved`,
  `examples`, `history`, `lore_after`, `authors_note`. Lore and
  memory each occupy two baseline positions, so each position is
  its own block — a grouped block could not reproduce the
  baseline interleaving (memory_nucleus < lore_before <
  memory_retrieved; history < lore_after), and the default
  layout must be a true identity. A UI may present the pairs as
  one lore / one memory group; the data stays honest.
  `post_history` is deliberately NOT a block yet — it becomes a
  prompt-manager citizen in P-057; until then it forms the
  unmanaged tail (`len(blocks)*100 + baseline_index`).
  - `layout_from_data(data)` validates and normalises the API
    shape (`{"blocks": [{"block": name, "enabled": bool}]}`
    or the bare list): unknown / duplicate / malformed entries
    raise `ValueError`; blocks the data does not mention are
    filled from the default at baseline-relative positions, so
    a partial layout still denotes a complete structure — and a
    future block never invalidates layouts written before it.
  - `apply_layout(slots, layout)` rewrites a slot list for the
    composer: a disabled block's slots are dropped (returned for
    the trace — including a `required` slot: the manager is the
    user's explicit instruction and outranks a slot's default
    required flag); a kept slot's order becomes
    `block_position * 100 + baseline_index(kind)` (baseline index
    is data, never encounter order). Depth slots keep the S206
    splice contract: order is raised to
    `max(assigned, history_assigned + 10)` whenever history is
    enabled; with history disabled a depth slot is a plain slot
    in block order and the composer falls through as it already
    does for a history-less prompt.
- `src/runmal/prompt/service.py` — `resolve_layout(explicit)`:
  precedence explicit > default, and no stored tier (see the
  scope note). `layout_echo` builds the result echo.
- `src/runmal/prompt/inspect.py` — the inspector honours the
  manager: `inspect_prompt(..., prompt_layout=None)` resolves
  the layout before slot building, applies it before `compose`,
  and records each dropped slot in the Prompt Trace as a discard
  with reason `prompt_manager_disabled` and its real token count
  (`build_trace` still receives the original full slot list, so
  kind/role/provenance join exactly). The result always carries
  `prompt_layout: {blocks, source}`. No layout in play = the
  pre-P-049 pipeline.
- `src/runmal/prompt/router.py` — `POST /debug/prompt-inspect`
  gains the optional `prompt_layout` field (an invalid layout is
  a 422, never a silent ignore); new
  `GET /debug/prompt-manager/default` returns the default layout
  for UI bootstrap. The inspect-with-layout call IS the preview:
  the inspector never sends and never writes.
- `src/runmal/prompt/__init__.py` — manager names join the
  public surface.

## Scope notes (honest boundaries)

- NO new DB migration; head stays 0032. Persisting a layout per
  owner or per chat is a named follow-up slice that owns its own
  migration: 0032 is pinned across the suite (including full
  revision lists and archive/restore schema pins), and a second
  campaign slice could take 0033 in parallel. P-049 ships the
  layout as validated, editable data on the API and honoured by
  the composer — it does not pretend to store one.
- Templates (P-050/P-051), samplers (P-052/P-053), preset
  bundles and per-chat overrides (P-054), macros (P-055),
  author's-note content/depth (P-056) and the post-history block
  (P-057) are later slices and are not built here.
- `tools/service.py compose_preview` is a stateless sandbox
  driver (no owner, no session; it composes caller-supplied raw
  strings) and does not resolve layouts; the inspector is the
  stored-data composition path and is where the manager is
  honoured. Carried as a finding in the slice evidence.

## Clean-room

Built from the roadmap line and Rúnmál's own prompt stack only;
no SillyTavern or Voxta source was read. See the P-049 entry in
`docs/CLEAN_ROOM_LOG_2026-10-30.md`.
