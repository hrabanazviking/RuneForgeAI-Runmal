# Entry states (P-035) — 2026-11-06

Roadmap line: *Entry states: constant, selective, vectorised — the
 three activation kinds, one engine.*

## What was built

- src/runmal/lorebooks/states.py — the pure entry-states module
  (no DB, no I/O, no network, no randomness, no wall-clock). It
  owns the activation-kind vocabulary — KIND_CONSTANT,
  KIND_SELECTIVE, KIND_VECTORISED, ACTIVATION_KINDS — the strict
  checker check_activation_kind, the tolerant normalisers
  normalise_activation_kind / normalise_vectorised, and the one
  derivation function activation_kind_for(constant, vectorised).
  Every entry has exactly ONE kind, derived from its flags and
  never stored: constant=True means constant (always fires);
  else vectorised=True means vectorised (fires only on a vector
  hit supplied to the engine); else selective (fires on keyword
  scan hits, gated by selective logic). Precedence constant >
  vectorised > selective is Runmal's own: constant means
  always-inserted, so it dominates; a both-flags entry (the
  P-005 corpus Harbour Law entry carries constant=True and
  vectorized=True) behaves as constant, and its vectorised flag
  is still stored, carried and reported — never silently
  dropped. Naming note: states.py (the kind vocabulary) is not
  state.py (P-033's per-chat timed-effect counters); the two
  modules are never imported unaliased into one module.
- Activation (activation.py, additive): ActivatableEntry gains
  vectorised (adapted tolerantly by from_orm, so rows or fakes
  without the attribute read as False) and a read-only
  activation_kind property. activate() gains the keyword
  argument vector_hit_ids — the ids vector matching hit this
  tick, computed elsewhere and handed in, exactly the P-031
  recursive seam shape. _tick_entry dispatches on the derived
  kind at the trigger step: a selective entry triggers only
  from a key hit (via key), a vectorised entry only from a
  vector hit (via vector); the two hit kinds never cross.
  Everything around the trigger is shared, which is what one
  engine means: cooldown suppresses a vector hit like a key
  hit, a vector hit on a delay entry arms the delay (and later
  fires via delay — trigger provenance is not carried across
  ticks, the recursive precedent), sticky carryover fires via
  sticky for either kind, inclusion groups resolve vector
  activations like every via kind, and the budget pass treats
  them identically. With vector_hit_ids absent, behaviour is
  exactly pre-P-035.
- Scan (scan.py, additive): ScanEntry gains vectorised (from
  the ORM row's own attribute). The scanner skips vectorised
  entries exactly as it skips constant ones: a vectorised
  entry is never keyword-scanned, and recursive rounds inherit
  the skip because they call scan_entries. Its hits arrive
  from vector matching, never from keys.
- Preview (preview.py, additive): preview_activation gains
  vector_hit_ids, passed to activate() on both the plain and
  recursive paths. Every row reports vectorised and the derived
  activation_kind. A vector-fired row honestly reports
  matched_primary / matched_secondary empty (no keyword
  matched) with via vector. The prompt inspector maps via
  generically, so vector rows surface in traces with no
  inspector change.
- Per-chat seam (state.py, additive): run_activation_tick
  gains vector_hit_ids and passes it through to activate(),
  so the persisted-counter tick honours the same one engine.
- Storage: migration 0027 (PROVISIONAL — P-036 is building
  concurrently from the same base with a provisional later
  number; the keeper reconciles at banking) adds
  lore_entries.vectorised INTEGER NOT NULL DEFAULT 0; the ORM
  gains the matching field. Existing rows read back False —
  exactly their old behaviour (kind selective, unless constant).
- Service + API: create_entry / update_entry carry the flag;
  entry_to_dict exposes vectorised plus the derived read-only
  activation_kind; the entry create/update API shapes gain
  vectorised (create default False); the preview request gains
  vector_hit_ids (a list of entry ids; empty means no vector
  hits). activation_kind is never accepted as input — it is
  derived, and a client-sent value is not a schema field.
- Import/export: the flag is modelled on both file legs, so
  vectorized leaves the pinned dropped-field sets (see Test
  maintenance).
  - transfer.py: native entries carry vectorised; world-info
    entries map vectorized through bool coercion; a legacy
    native file spelling vectorized is accepted as an alias;
    export_book emits vectorised; validate_parsed_book carries
    it into the transactional import's prepared rows, so the
    transactional and library paths honour it like the plain
    service path.
  - interop.py: WorldInfoEntry.vectorised is a first-class
    field (promoted out of extra, like selective_logic in
    P-032 and the group fields in P-034); world-info export
    writes vectorized under the no-fabrication rule — only
    when the source file carried it or the flag is True — so
    the corpus fixed-point round-trip holds (Gale-Bell:
    vectorized false in, modelled, false out; Harbour Law:
    true in, modelled, true out; Sunken Tithe: absent in,
    absent out). One defect found and fixed in-slice: the new
    derived activation_kind API key leaked through
    worldinfo_from_native into world-info exports as a file
    field; it is now in that function's bookkeeping exclusion
    set (derived data has no file spelling), pinned by the
    battery.
- Archive: no code change — the .runmal archive serialises
  lore entries by table columns, so vectorised rides along;
  the battery pins export carriage and a restore round-trip
  (a pre-0027 archive restores with the model default False).

## Test maintenance

- The P-005/P-019/P-030 dropped-field pins shrink by exactly
  the one field this slice lands: vectorized moves from the
  dropped sets (20 -> 19 fields) to the mapped sets in
  tests/test_p005_interop_corpus.py,
  tests/test_p019_lorebook_interop.py and
  tests/test_p030_part2_gate.py; the P-030 store-leg exact
  entry key set and mapped-keys tuple gain vectorised. The
  Harbour Law assertions now read the modelled flag
  (vectorised True, constant True, kind constant). No
  assertion was weakened; each pin's own comment instructs a
  landing slice to make exactly this edit.
- Adding migration 0027 moves the schema head, so the head
  pins across the suite (migration lists, applied[-1],
  MIGRATIONS[-1], current_revision, archive/restore
  schema_revision, and the P-032/P-033/P-034 slices' own
  head tests) move 0026 -> 0027 in fifteen test files, and
  the revision lists gain 0027 after 0026. Historical pins
  that assert a migration's own facts (0024's column,
  0025's table, 0026's columns and old-database upgrade)
  were left untouched apart from the applied-tail truth.
- New battery: tests/test_p035_entry_states.py (59 tests,
  all passing; output in hidden_files/p035_battery.log).

## Clean-room basis

Built from Runmal's own roadmap line, its own S202/S203/S204
lorebook pipeline, the public entry-strategy behaviour
recorded by P-002's census (ST-17: constant = always
inserted; keyword-triggered; vectorised = inserted by
embedding similarity via the vector extension, subject to
all other checks), and the public world-info field name
vectorized as P-005's authored corpus already carries it.
No SillyTavern or Voxta source was inspected; the slice's
 test fixtures are authored fresh in the test module (P-005
 discipline). The kind derivation, precedence, via vector
 dispatch and caller-supplied hit seam are Runmal's own
 semantics for the roadmap line.

## Carried limitations (honest record)

- No embedding matcher in this slice: vector hits are
  caller-supplied ids. Embedding-matched lore on the founding
  RAG stack is P-041, which also owns the keyword fallback
  and the ST-17 per-extension max-entries cap (a matcher
  config with no ranked hit list to cap until then; the
  interim bound on vector activations is the ordinary S204
  token-budget pass, which already applies to them).
- Dormant in live paths until P-041: inspect_prompt takes no
  vector hits and no live pipeline calls run_activation_tick
  yet (P-033's standing seam note), so in the inspector and
  real chats a vectorised entry shows as kind-labelled
  not_triggered; preview with caller-supplied vector_hit_ids
  is the firing path this slice proves.
- Kind exclusivity: a vectorised entry NEVER fires from a
  keyword hit in this slice, even one whose keys match —
  the keyword fallback is P-041's deliberate design, not an
  accident of this one.
- The world-info selective boolean stays unpromoted, by
  fixture proof: entry 1 carries selective true on a
  constant entry and entry 2 (a textbook selective entry)
  omits it, so it is neither derivable from nor consistent
  with the kind model; it rides verbatim in extra at file
  level (round-trips losslessly) and the DB kind is fully
  recoverable by derivation. Promoting it would create a
  second, conflicting source of truth beside the derived
  kind and a naming trap beside selective_logic (P-032, an
  unrelated axis).
- ST-26 character-filter and generation-type triggers
  (mentioned near this slice in the Part I gate record) are
  NOT part of this roadmap line and were not built: the
  characterFilter and triggers fields remain in the pinned
  dropped sets for a future slice to claim deliberately.
- Reference expansion is exempt from kind dispatch:
  lore references pulled in by an activated entry fire via
  reference regardless of their kind — an explicit authorial
  inclusion, the inclusion-group precedent (P-034).
- Migration 0027 is provisional: P-036 is building
  concurrently from the same base and may also hold a
  provisional number; the keeper reconciles at banking.
- No editor/UI surface: the lorebook editor does not yet
  expose the vectorised flag or the kind (P-042 owns the
  editor-depth pass); both are reachable through the API,
  the service, preview and file import today.
- F1 (native lorebook at_depth entries cannot enter the DB
  store) is P-038's road and was expressly out of scope.

## Evidence

- Battery: 59 passed / 0 failed
  (hidden_files/p035_battery.log).
- Neighbours (S202/S203/S204 scan, activation, budget,
  S209 editor, S213 hardening, S214 trace, S215 inspector
  and e2e, S103/S107/S801/S802 storage/archive, S201,
  P-005, P-019, P-027, P-030, P-031, P-032, P-033, P-034):
  562 passed / 0 failed (hidden_files/p035_neighbours.log).
- Full suite in the team-02 worktree: 1665 passed / 4
  skipped / 0 failed (hidden_files/p035_fullsuite.log) —
  the banked base's 1606 plus this battery's 59. No
  failures at all this run; the known test_s503 contention-
  noise pattern did not occur.
