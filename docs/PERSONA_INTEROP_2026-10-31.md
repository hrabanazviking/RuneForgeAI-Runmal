# P-018 — Persona Interop (2026-10-31)

*Part II (Cards & Content Interop): ST-shaped persona files in/out;
Rúnmál personas gain the fields users expect (description
positions, depth) without breaking existing ones. Acceptance in
`tests/test_p018_persona_interop.py` (12 tests).*

## The measured gap this slice closes

On entry there was **no user-persona file importer at all**:
P-005's corpus pinned `persona_st.json` as well-formed and named
P-018 as its home, and the delta table (P-004) judged ST-09
(persona description positions) MISSING — no position or depth
setting existed anywhere in the tree. Rúnmál's word "persona"
meant two other things, both left untouched by this slice:
S110's character-card prompt assembly (`runmal.persona.slots`)
and S603's bridge persona switching (a chat's active *character*).

## What was built

`src/runmal/persona/interop.py`:

- `UserPersona` — the user's own identity (ST-08): `name`,
  `description`, `prompt`, `system_prompt`, `title`, plus the
  placement fields and the complete original mapping in `raw`.
- `parse_persona(bytes | str | dict)` — defensive import:
  invalid JSON, a non-object, a missing/empty name, a negative
  or non-numeric depth, an unknown role, and an unknown
  description position are each rejected with a typed
  `PersonaParseError`, never a bare exception and never a
  silent reinterpretation. Null depth stays `None`; numeric
  strings coerce (P-005's discipline).
- `export_persona(persona)` — export starts from `raw` and
  overlays the normalized known fields, so unknown-but-valid
  fields survive verbatim (INV-009). `depth`/`role` are written
  only when carried — never fabricated. Re-export is a fixed
  point (pinned byte-for-byte in the tests).
- Description positions (ST-09), canonical set
  `DESCRIPTION_POSITIONS`: `disabled`, `in_prompt`,
  `authors_note_top`, `authors_note_bottom`, `in_chat`.
  Import normalizes the fixture's attested spelling and plain
  synonyms of the census wording; anything else is rejected.
- The fixture's legacy numeric `position` is preserved verbatim
  with **no semantics claimed** — the canonical placement is
  `description_position`.
- `persona_description_slot(persona)` — the placement made real
  against Rúnmál's own prompt composer (S205/S206):
  `disabled` or an empty description → no slot; `in_prompt` →
  the baseline persona slot; Author's Note positions → an
  `authors_note` slot ordered just before/after the baseline
  Author's Note position; `in_chat` → a persona slot spliced
  at the persona's depth (default 0) with its role (default
  system). The position governs the *description* — the
  separate `prompt` field is preserved by interop and not
  substituted here.

## Not in this slice

Persona locking/default/session override (ST-10's depth),
persona lore scope (P-039/P-040), and batch re-attribution of
past user messages (ST-08's "sync") keep their later homes;
this slice is the file interop and the position/depth gain
the roadmap names for P-018. No database schema changes: the
interop model is a file model, like the card model.

## Clean-room basis

Own tree only, plus the shapes already logged: P-002's census
of SillyTavern's official public documentation (ST-08/ST-09)
and P-005's authored corpus fixture. No mirror source code
was read; no persona file was downloaded.
