# Inclusion groups (P-034) — 2026-11-06

Roadmap line: *Inclusion groups: mutually exclusive entries resolved by
weight/priority, deterministically.*

## What was built

- `src/runmal/lorebooks/groups.py` — the pure inclusion-group module
  (no DB, no I/O, no network, no randomness, no wall-clock). It holds
  the vocabulary — `inclusion_group` (one label per entry, stripped,
  case-sensitive; empty means ungrouped) and `group_weight` (default
  100) — strict checkers for the service/API layer, tolerant
  normalisers for the file/import layer (mirroring P-032's
  selective-logic discipline: booleans/None/unparsable/negative all
  fall back to the default weight; non-string groups mean ungrouped),
  and `resolve_inclusion_groups(candidates)`.
- Resolution semantics (normative): among the *activated* candidates
  sharing a non-empty group, exactly one is included. The winner is
  chosen by highest `group_weight`, then highest `priority`, then
  lowest `entry_id`. Nothing else influences the choice — not input
  order, not time, not a random draw — so the same candidate set
  always resolves to the same winner in any input order (the battery
  proves the winner set over all 720 permutations of a mixed set,
  and byte-identical previews over 25 repeated scans of the same
  book + chat). Winners are returned in input order; losers in a
  deterministic order (group, then the winner ranking key), each
  carrying its provenance: group, winner id, and both sides'
  weight/priority — the forward hook for the activation inspector
  (P-043). Duplicate entry-id rows: the first row is the candidate,
  later duplicates are ignored (an entry fires at most once).
- Activation (`activation.py`, additive): `ActivatableEntry` gains
  `inclusion_group` / `group_weight` / `priority` (adapted tolerantly
  by `from_orm`, so rows or fakes without the attributes read as
  ungrouped / 100 / 100). `activate()` runs the resolver over the
  direct activations — every via kind competes, constants included —
  before `{{lore:...}}` reference expansion. The result gains
  `group_losers` (provenance rows) and `group_suppressed` (the losers'
  would-be activations, via/depth as fired, content unexpanded).
  With no grouped entry among the direct activations both are empty
  and behaviour is exactly pre-P-034.
- Preview (`preview.py`, additive): every row reports
  `inclusion_group` and `group_weight`. A loser shows as
  `group_excluded` — a status of its own, NOT the budget pass's
  `discarded`, whose `discard_reason` vocabulary stays S204's alone
  (`over_budget` / `probability_skip`). The row keeps the via it
  fired with, carries `group_winner_id`, keeps `discard_reason`
  None, and contributes no content or tokens. When any group was
  contested the result gains `inclusion_group_winners` (label ->
  winner entry id). The prompt inspector maps any non-included
  status to its trace reason generically, so group-excluded entries
  surface there as `group_excluded` with no inspector change.
- Storage: migration 0026 (**PROVISIONAL** — 0025 is reserved for
  P-033, building concurrently from the same base; the keeper
  renumbers at banking if the reservation changes) adds
  `lore_entries.inclusion_group TEXT NOT NULL DEFAULT ''` and
  `lore_entries.group_weight INTEGER NOT NULL DEFAULT 100`; the ORM
  gains the matching fields. Existing rows read back ungrouped with
  weight 100 — exactly their old behaviour.
- Service + API: `create_entry` / `update_entry` carry both fields
  under strict validation; `entry_to_dict` exposes them; the entry
  create/update API shapes gain them (create default `''` / 100;
  update rejects a negative weight with 422 at the schema).
- Import/export: the fields are modelled on both file legs, so
  `group` / `groupWeight` leave the pinned dropped-field sets (see
  Test maintenance).
  - `transfer.py`: native entries carry `inclusion_group` /
    `group_weight`; world-info entries map `group` /
    `groupWeight` through the tolerant normalisers;
    `export_book` emits the native names;
    `validate_parsed_book` carries both into the transactional
    import's prepared rows.
  - `interop.py`: `WorldInfoEntry.inclusion_group` /
    `group_weight` are first-class fields (promoted out of `extra`,
    like `selective_logic` in P-032); world-info export writes
    `group` / `groupWeight` under the no-fabrication rule — only
    when the source file carried them or the values differ from
    the defaults — so the corpus fixed-point round-trip holds
    (the Gale-Bell entry: `weather` / 75 in, modelled, 75 out).

## Test maintenance

- The P-005/P-019/P-030 dropped-field pins shrink by exactly the
  two fields this slice lands: `group` and `groupWeight` move from
  the dropped sets (22 -> 20 fields) to the mapped sets in
  `tests/test_p005_interop_corpus.py`,
  `tests/test_p019_lorebook_interop.py`, and
  `tests/test_p030_part2_gate.py`; the P-030 store-leg exact entry
  key set grows by `inclusion_group` + `group_weight`, and its
  mapped-keys tuple gains both. The Gale-Bell assertions now read
  the modelled fields (`gale.inclusion_group == "weather"`,
  `gale.group_weight == 75`) instead of the `extra` carriage.
  No assertion was weakened; each pin's own comment instructs a
  landing slice to make exactly this edit.
- Adding migration 0026 moves the schema head, so the head pins
  across the suite (migration lists, `applied[-1]`,
  `current_revision`, archive/restore `schema_revision`) move
  0024 -> 0026 in twelve test files, and the revision lists gain
  `"0026"` after `"0024"` (0025 does not exist in this tree yet —
  it is P-033's reserved number). Historical pins that assert a
  migration's own facts (0024's column, 0023's records) were left
  untouched.
- New battery: `tests/test_p034_inclusion_groups.py` (57 tests,
  all passing; output in `hidden_files/p034_battery.log`).

## Clean-room basis

Built from Rúnmál's own roadmap line, its own S202/S203/S204
lorebook pipeline, the public world-info field names recorded by
P-005's authored corpus (`group`, `groupWeight`, `groupOverride`,
`useGroupScoring` on the Gale-Bell fixture entry) and P-002's
census. No SillyTavern or Voxta source was inspected; the slice's
test fixtures are authored fresh in the test module (P-005
discipline). Deterministic resolution is Rúnmál's own semantics
for the roadmap line, chosen over the public format's
weighted-random draw (see Carried limitations).

## Carried limitations (honest record)

- Single-label membership: each entry belongs to at most one
  group, stored as one `inclusion_group` string (stripped,
  case-sensitive, max 200 characters). A world-info `group`
  value containing commas is treated as one label (commas are
  literal) — multi-group membership is not modelled. Changing
  this would require a schema revision and revised resolution
  semantics.
- The world-info boolean fields `groupOverride` and
  `useGroupScoring` are preserved verbatim in `extra` on
  file-level import/export but never reach the store and drive
  no behaviour; a future slice must promote them deliberately.
- Reference expansion is exempt: `{{lore:...}}` references pulled
  in by an activated winner are never group-resolved, and group
  labels play no role in reference resolution. A reference is an
  explicit authorial inclusion, not a group activation.
- Losers' timers still advance: group resolution runs after the
  activation tick has processed every direct candidate, so a
  group loser's armed sticky/cooldown/delay state advances as
  if it had fired for timing purposes, even though it delivers
  nothing. (They receive no tokens and no cost. Recursive
  *discovery* is a separate, earlier scan phase: a loser's
  content can still discover recursive children, exactly as a
  delay-armed or budget-doomed parent's can — P-031's standing
  two-phase rule; the group pass governs activation inclusion,
  not scan discovery.)
- Duplicate ids keep the first row: repeated `entry_id`s resolve
  on the first input occurrence and later duplicates are silently
  ignored, not reported as losers.
- Migration 0026 is provisional: 0025 is reserved for the
  concurrent P-033 timed-effects slice. The keeper may renumber
  0026 (module, REVISION/DESCRIPTION, registration, and head
  pins) at banking. In this worktree the revision sequence jumps
  0024 -> 0026 until P-033 banks.
- Weighted-random group scoring was deliberately not
  reproduced: the public format's per-group random draw is
  non-deterministic by construction and sits outside the
  roadmap's "deterministically" requirement. By the same token,
  seeded probabilistic choice belongs to P-036, not this slice;
  nothing here consumes a seed or an RNG.
- Group resolution applies per book per tick: activation and
  preview operate on one book's entries, so identically named
  groups in different books never interact. Cross-book group
  precedence, if ever wanted, belongs with the scope-layering
  slice (P-040).
- No editor/UI surface: the lorebook editor does not yet expose
  group fields (P-042 owns the editor-depth pass); the fields are
  reachable through the API, the service, and file import today.

## Evidence

- Battery: 57 passed / 0 failed (`hidden_files/p034_battery.log`).
- Neighbours (S201/S202/S203/S204/S209/S213/S214/S215 scan,
  activation, budget, editor, hardening, trace, e2e and inspector
  tests, S103/S107/S801/S802 storage/archive, P-005, P-019, P-027,
  P-030, P-031, P-032): 442 passed / 0 failed
  (`hidden_files/p034_neighbours.log`).
- Full suite in the team-01 worktree: 1537 passed / 4 skipped /
  0 failed (`hidden_files/p034_fullsuite.log`) — the P-032 banked
  base's 1480 passed / 4 skipped plus this battery's 57. No
  failures at all this run; the known test_s503 contention-noise
  pattern did not occur.
