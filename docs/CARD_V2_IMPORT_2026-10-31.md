# P-015 — Character Card v2 Import, Full Field Fidelity (2026-10-31)

*Part II (Cards & Content Interop), first slice: character card v2
import (PNG-embedded + JSON) with full field fidelity — nothing
silently dropped; unknown fields preserved verbatim. Acceptance in
`tests/test_p015_card_v2.py` (12 tests).*

## The measured gap this slice closes

The public v2 spec (public spec summaries and spec examples,
read 2026-10-31 — see the clean-room log entry) wraps the card's
fields in an envelope:

```json
{"spec": "chara_card_v2", "spec_version": "2.0", "data": { ...fields... }}
```

Rúnmál's founding importer read v2 **flat only** (fields at the top
level). Measured on entry to this slice, with a spec-shaped card:

- wrapped v2 JSON → **rejected**, `CardParseError: card has no name`;
- wrapped v2 PNG (`chara` tEXt chunk) → **rejected** the same way;
- flat v2 (the founding fixtures' shape) → imported fine.

So the most standard v2 shape in the wild could not enter Rúnmál
at all, while P-005's corpus — authored flat — travelled well and
hid the gap. This slice fixes the importer, not the fixtures.

## Field-source rule (the written mapping)

`parser._field_source` resolves where fields live:

| Input | Field source |
|---|---|
| v3 | `data` object, authoritative and required (unchanged) |
| v2 / v1 with a dict `data` | `data` primary; any field it omits falls back to the top-level value (data wins per key) |
| v2 / v1 with no `data`, or a non-dict `data` | flat top level; a non-dict `data` is an unknown field, not an envelope, and survives verbatim |

The fallback mirrors the resolution public card readers document
for v2 (data first, top-level fallback). An empty `data: {}` never
shadows flat fields.

## The v2 field mapping (spec field → normalized model)

All fields land on `CharacterCard` under their spec names:
`name`, `description`, `personality`, `scenario`, `first_mes`,
`mes_example`, `creator_notes`, `system_prompt`,
`post_history_instructions`, `alternate_greetings`, `tags`,
`creator`, **`character_version`**, `character_book`,
`extensions`. One model change: `character_version` is now a
first-class normalized field — before this slice it survived only
as an opaque unknown in `raw`. Everything else in the file —
unknown fields of every JSON type, at the data level *and* the
top level — is kept verbatim in `raw` (INV-009).

## Export preservation (import fidelity is a round trip)

Storing a character re-exports it (`characters/service.py` stores
`export_json(card, "2")`), so import fidelity that the exporter
then drops would be fake. The exporter now preserves the envelope
a card arrived in:

- wrapped v2 → v2 export stays wrapped: data-level unknowns
  verbatim inside `data`, top-level unknowns verbatim outside,
  known fields overlaid from the normalized card inside `data`;
- wrapped v2 → v3 export: data unknowns stay at the data level,
  top-level unknowns stay at the top level (previously the
  conversion read unknowns from the top level only and would
  have dropped the wrapped card's data-level unknowns);
- flat v2 → v2 export stays flat, byte-shape as founded
  (existing S105/P-005 pins untouched);
- PNG export carries the same v2 payload, so wrapped cards
  round-trip through PNG too;
- a flat card whose top-level `data` is not an object keeps that
  value verbatim on flat v2 export instead of the envelope key
  swallowing it.

No existing pin was changed by this slice: the flat-shape tests
(S104/S105/P-005) pass unmodified.

## Clean-room basis

Behaviour and format shape only, from public sources: public
character-card v2 spec summaries and spec examples showing the
`data` envelope and the v2 field set, and public card-reader
documentation of the data-first/top-level-fallback resolution.
No SillyTavern or Voxta source code was read (neither is the
source of the spec), and no card file was downloaded — the test
cards are authored fresh in the test module, P-005's discipline.
Full entry appended to `docs/CLEAN_ROOM_LOG_2026-10-30.md`.

## Suite

Full suite re-run this tick on the VM (sanitised proxy env, per
the P-007 standing instruction) — counts recorded in
`CAMPAIGN_STATE.md`. This slice adds 12 tests.
