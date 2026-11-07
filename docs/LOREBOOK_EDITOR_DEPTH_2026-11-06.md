# Lorebook editor depth (P-042) — 2026-11-06

Roadmap line: *Lorebook editor depth: the UI reaches every field
the engine honours (no engine-only settings).*

## What was built

- `src/runmal/lorebooks/editor.py` — the editor census, as data.
  For each surface the editor owns (book, entry, scope assignment,
  preview) it declares every engine-honoured field, the API model
  that carries it, the editor element that edits it, and the
  select vocabulary where one applies. Served verbatim at
  `GET /api/v1/lorebooks/editor-schema`.
- The census: book 6 fields (name, description, scan_depth,
  token_budget, scan_mode, scan_external_context); entry 20
  authored fields (name, content, keys, secondary_keys,
  selective_logic, inclusion_group, group_weight, probability,
  priority, position, depth, role, enabled, constant,
  vectorised, case_sensitive, whole_word, sticky_prompts,
  cooldown_prompts, delay_prompts) plus the derived
  `activation_kind` shown read-only; scope 4 fields (scope_kind,
  owner_id, token_budget, position); preview 13 controls.
- Editor page (`web/templates/lorebooks.html` +
  `web/static/lorebooks.js`), following the existing S304
  patterns — no parallel UI stack:
  - a book-settings form (the page previously offered only a
    name prompt on creation; description, scan depth, token
    budget, scan mode and external-context admission were
    API-only);
  - the entry form completed: selective-logic select (all four
    P-032 modes), inclusion group + group weight (P-034),
    probability (P-036), the `at_depth` position plus depth and
    role (P-038 — the position select previously offered only
    two of the engine's three positions), enabled / vectorised /
    case-sensitive / whole-word flags (P-035/P-041), and the
    derived activation kind displayed as it will fire;
  - a scope panel (P-040): assign / list / remove a book's layer
    assignments against the existing scope endpoints;
  - the preview panel completed: seed, roll context, scan-mode
    override, external context (toggle + texts), vector hit ids,
    vector threshold / max entries — and recursion (below).
- API gap closed (`lorebooks/router.py`): `recursive_scan` and
  `max_recursion_depth` were honoured by
  `preview.preview_activation` (P-031) but carried by no API
  shape — the one genuinely engine-only setting pair. They are
  `PreviewRequest` fields now, passed through to the engine;
  an unset max depth resolves to the engine cap
  `MAX_RECURSIVE_SCAN_DEPTH`.
- Golden fixture: the S311 structural golden for the lorebooks
  page was deliberately regenerated
  (`RUNMAL_UPDATE_GOLDENS=1`); no other page's golden moved.

## Deliberate boundaries

- No migration: P-042 adds no stored field (the reserved 0033
  was not needed); the migration head stays 0032 and every head
  pin in the tree remains truthful.
- Out of census: the P-039 character-book binding `precedence`
  is a field of the character aggregate, edited through the
  characters API surface P-039 shipped — not a lorebook or
  lore-entry field. Per-chat timed-effect counters (P-033) are
  runtime engine state, not authored fields.
- Book `token_budget` clearing follows the update convention
  shared by every update shape in the codebase: an unset field
  leaves the stored value unchanged, so the form sets/changes
  the budget; returning a book to unlimited is the one value
  transition the PATCH convention cannot express.
- The preview panel's external-context toggle sends an explicit
  `true` when checked and omits the field when unchecked, so an
  unchecked toggle keeps the book default (the panel's standing
  blank-means-book-default rule).

## Proof

`tests/test_p042_lorebook_editor_depth.py` (15 tests) derives
the engine's field set independently — SQLAlchemy model columns,
engine vocabularies (positions, roles, selective logics, scan
modes, scope kinds, activation kinds), service dict keys and
router model fields — and fails if any field is missing from
the census, from its API model, from the shipped page (element +
select vocabulary), or from the JS wiring. Round-trips set every
book/entry field to a non-default value through the API and read
it back; the scope round-trip runs through the editor's API
shapes; preview tests prove recursion fires via `recursive`
only when opted in (and is capped at depth 0), and that seed,
roll context and caller-supplied vector hits reach the engine.
