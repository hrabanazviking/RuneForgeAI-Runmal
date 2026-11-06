# Probability & RNG honesty (P-036) — 2026-11-06

Roadmap line: *P-036 Probability & RNG honesty: probabilistic
entries use a seeded, inspectable roll (the Sagnaskemma dice
discipline's kin).*

Part III (Lorebook Depth), from
`docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_2026-10-30.md`.

## The dishonesty this removes

S204's budget pass had a probability gate in name only:

- The draw came from one shared `random.Random(seed)` consumed
  in priority order, so an entry's fate depended on how many
  draws other entries had taken before it. Remove a neighbour
  and the same seed dealt a different roll to the same entry.
- No roll was ever recorded. A `probability_skip` said *that*
  an entry was dropped, never *by what roll* — nothing could
  be inspected, explained, or reproduced for one entry alone.
- `probability` lived only on the transient budget candidate.
  The stored entry had no probability at all, and the preview
  built its candidates with the default 1.0 — so in the one
  place a user can look, the gate never fired at all.

## What was built

- The roll module — new `src/runmal/lorebooks/rng.py`, pure
  (no DB, no I/O, no network, no wall-clock; hashlib only on
  the seeded path):
  - Stored vocabulary: probability is an integer percent
    0..100 (the public world-info shape), default 100.
    `check_probability` validates strictly (real int in range,
    bools rejected — the service/API layer);
    `normalise_probability` coerces tolerantly for the
    file/import layer (bools/None/unparsable fall back to 100;
    out-of-range also falls back to 100 — never clamped into a
    gate the author did not write); `probability_fraction`
    converts percent to the budget's [0.0, 1.0] fraction.
  - `derive_roll(entry_id, seed, context="")` — the seeded
    roll, a pure function of (seed, context, entry_id):
    SHA-256 over the canonical material
    `runmal-p036-roll-v1` + seed + context + entry_id, first
    eight digest bytes / 2**64, a float in [0.0, 1.0). The
    algorithm version is part of the material, so a future
    algorithm change is a new version, never silent drift.
  - `roll_probability(...)` returns a frozen `ProbabilityRoll`
    record — entry_id, probability, roll, passed, seed,
    seeded, context, algorithm — with `to_dict()` for
    inspectors (P-043 consumes this shape). The entry passes
    iff `roll < probability`.
  - The roll does NOT depend on the probability itself, on
    any other entry, or on candidate order: the same seed +
    context + entry reproduces the same roll in isolation,
    and re-judging that recorded roll against a changed
    threshold flips the outcome predictably (the battery
    proves both, including all 720 permutations of a mixed
    candidate set at the budget layer).
  - `context` is the caller's per-tick variation string,
    recorded verbatim on the roll. Default `""`: with a fixed
    seed and no context a gated entry passes or fails the
    same way every tick — what a preview/inspector wants,
    and exactly what a live caller must vary for per-tick
    chance.
  - `seed=None` is the honest unseeded path: the roll is
    drawn from system entropy and the record carries
    `seed=None, seeded=False` — inspectable after the fact,
    labelled not reproducible, instead of pretending.
- Budget (`budget.py`, additive): `resolve_budget` gains a
  keyword `context` and makes each gated candidate's roll via
  `rng.roll_probability`; `BudgetResult` gains `rolls` — the
  record for every gated candidate (probability < 1.0), pass
  or fail, in processing order. Ungated candidates make and
  record no roll. `probability_skip` is unchanged. Outcomes
  for a fixed seed may differ from pre-P-036 runs (the old
  sequential draw is superseded); the recorded roll is now
  the source of truth.
- Storage: migration 0028 (**PROVISIONAL** — 0027 is reserved
  for P-035, entry states, building concurrently from the
  same base and banking first; the keeper renumbers at
  banking if the reservation changes) adds
  `lore_entries.probability INTEGER NOT NULL DEFAULT 100`;
  the ORM gains the matching field. Existing rows read back
  100 — gate off, exactly their old behaviour.
- Service + API: `create_entry` / `update_entry` carry
  `probability` under strict validation; `entry_to_dict`
  exposes it; the entry create/update API shapes gain it
  (create default 100; update out-of-range is 422 at the
  schema). The preview request gains `roll_context`
  (default `""`), passed through to the roll derivation.
- Preview (`preview.py`, additive): candidates finally carry
  the stored probability (percent → fraction), so the gate
  is live in preview for the first time. Every row reports
  `probability` (percent) and `probability_roll` (the roll
  record dict, or None when ungated); the result reports
  `seed` and `roll_context` always, and `probability_rolls`
  (every gated roll this tick) when any roll was made. With
  the same seed + context the preview reproduces roll for
  roll (battery: 10 repeats byte-identical).
- Import/export: the field is modelled on both file legs, so
  `probability` / `useProbability` leave the pinned
  dropped-field sets (see Test maintenance).
  - `transfer.py`: native entries carry `probability`;
    world-info entries map `probability` through the tolerant
    normaliser, and an explicit `useProbability=false` folds
    to the effective percent 100 (the store carries the
    effective percent, not the flag); `export_book` emits
    `probability`; `validate_parsed_book` carries it into the
    transactional import's prepared rows. The Gale-Bell
    entry: 80 in, modelled, 80 stored; Harbour Law: 100 with
    `useProbability=false` in, 100 (gate off) stored.
  - `interop.py`: `WorldInfoEntry.probability` /
    `use_probability` are first-class fields (promoted out of
    `extra`, like `group` in P-034); world-info export writes
    `probability` / `useProbability` under the no-fabrication
    rule — only when the source file carried them or the
    values differ from the defaults — so the corpus
    fixed-point round-trip holds (Gale 80/true and Harbour
    100/false both ride back verbatim).

## What was deliberately NOT wired

- No second stored column for `useProbability`: the DB store
  carries the *effective* percent (false folds to 100). The
  flag itself survives losslessly at the file layer
  (`interop.py` raw + first-class fields); only a DB
  round-trip collapses the distinction between "100 with the
  gate armed" and "gate off" — behaviourally identical
  today, recorded here honestly. A future slice that needs
  the distinction in the store must promote it deliberately.
- No live generation wiring: the generation pipeline still
  does not run lore activation for real chats (no chat↔book
  binding exists yet — the P-033 seam note). Callers that run
  the budget pass today (preview, prompt inspection, tests)
  get honest rolls now; the future pipeline slice chooses
  the per-tick seed/context policy (e.g. seed per chat,
  context per tick) when it lands.
- No editor/UI surface: the lorebook editor does not yet
  expose the probability field (P-042 owns editor depth);
  it is reachable through the API, the service, preview, and
  file import today.
- Activation (`activation.py`) is untouched: probability is
  a budget-pass gate, as it has been since S204 — it does
  not interact with P-035's entry states, and this slice's
  footprint in the activation area is zero by design.

## Test maintenance

- The P-005/P-019/P-030 dropped-field pins shrink by exactly
  the two fields this slice lands: `probability` and
  `useProbability` move from the dropped sets (20 → 18 fields)
  to the mapped sets in `tests/test_p005_interop_corpus.py`,
  `tests/test_p019_lorebook_interop.py`, and
  `tests/test_p030_part2_gate.py`; the P-030 store-leg exact
  entry key set grows by `probability`, and its mapped-keys
  tuple gains it. The Gale-Bell assertions now read the
  modelled fields (`gale.probability == 80`,
  `gale.use_probability is True`) instead of the `extra`
  carriage. No assertion was weakened; each pin's own comment
  instructs a landing slice to make exactly this edit.
- Adding migration 0028 moves the schema head, so the head
  pins across the suite move 0026 → 0028 in fifteen test
  files (migration lists gain `"0028"` after `"0026"` —
  0027 does not exist in this tree; it is P-035's reserved
  number): `tests/test_s103_storage.py`,
  `tests/test_s106_characters.py`, `tests/test_s107_chats.py`,
  `tests/test_s201_lorebooks.py`,
  `tests/test_s210_group_chats.py`,
  `tests/test_s801_archive.py`, `tests/test_s802_restore.py`,
  `tests/test_p021_preset_interop.py`,
  `tests/test_p023_card_assets.py`,
  `tests/test_p025_character_versions.py`,
  `tests/test_p026_scenario_interop.py`,
  `tests/test_p029_provenance_on_import.py`,
  `tests/test_p032_selective_logic.py`,
  `tests/test_p033_timed_effects_persistence.py`, and
  `tests/test_p034_inclusion_groups.py` (its head test
  renamed, its [-2]/[-3] positions and old-DB applied list
  updated). Historical pins asserting a migration's own
  facts (0026's columns, 0025's table, 0024's column, the
  P-030 gate record's historical text) were left untouched.
- S204's own battery is unmodified and passes: its seeded
  reproducibility test now exercises per-entry rolls (seed
  1234 over 20 candidates at 0.5 yields 8 in / 12 out).

## Evidence

- Battery: 30 passed / 0 failed —
  `tests/test_p036_probability_rng.py`
  (`hidden_files/p036_battery.log`).
- Neighbours: 770 passed / 0 failed — S201/S202/S203/S204/
  S209/S213/S214/S215 lorebook pipeline, S103/S106/S107/
  S210/S801/S802 storage/archive, P-005, P-019, P-021, P-023,
  P-025, P-026, P-029, P-030, P-031, P-032, P-033, P-034 and
  the P-036 battery (`hidden_files/p036_neighbours.log`).
- Full suite: recorded in `hidden_files/P036_EVIDENCE.md`;
  no full-suite count is claimed here.

## Carried findings/limitations (honest record)

- Migration 0028 is provisional: 0027 is reserved for the
  concurrent P-035 entry-states slice, which banks first.
  The keeper may renumber 0028 (module, REVISION/DESCRIPTION,
  registration, and head pins) at banking. In this worktree
  the revision sequence jumps 0026 → 0028 until P-035 banks.
- `useProbability` is not a stored column (see NOT wired):
  the DB store keeps the effective percent only.
- Fixed-seed determinism cuts both ways: a caller that
  passes the same seed and the same (empty) context every
  tick gets the same outcome every tick. That is the
  honest, inspectable behaviour the roadmap demands; live
  per-tick chance is a caller policy (vary seed or context
  per tick), and no caller in the tree runs the gate live
  yet, so no policy is prejudged here.
- Unseeded rolls remain available (`seed=None`) for callers
  that choose them, now honestly labelled `seeded=False` on
  every record instead of silently irreproducible.
- Gate finding F1 — a native lorebook carrying `at_depth`
  entries cannot enter the DB store — is untouched. That is
  expressly P-038's road, not this slice's.

## Clean-room basis

Built from Rúnmál's own roadmap line, its own S204 budget
semantics, and the public world-info field names recorded by
P-005's authored corpus (`probability` 80 / `useProbability`
true on the Gale-Bell fixture entry). The roll derivation
(SHA-256 over seed/context/entry, algorithm-versioned) is
Rúnmál's own design for the roadmap line — the dice discipline's kin: a roll you can show, name, and re-roll to
the same face. No SillyTavern or Voxta source was inspected;
the slice's test entries are authored fresh in the test
module (P-005discipline).
