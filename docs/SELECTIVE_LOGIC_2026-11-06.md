# Selective logic (P-032) — 2026-11-06

Roadmap line: *Selective logic: AND/NOT/any-all key logic per entry, the
full truth table tested.*

## What was built

- `src/runmal/lorebooks/logic.py` — the pure selective-logic module
  (no I/O, no runmal imports; every other layer shares it). It holds
  the four canonical mode names — `and_any` (the default), `and_all`,
  `not_any`, `not_all` — the world-info integer codes
  (`and_any` 0, `not_all` 1, `not_any` 2, `and_all` 3; the code order
  is the file format's documented order, *not* the prose order of
  census ST-16, and codes 2/3 are pinned by unit tests because no
  fixture discriminates them), and three helpers per layer:
  - `check_selective_logic` — strict validation for the service/API
    layer (a canonical name or `ValueError`, mirroring
    `_check_position`).
  - `normalise_selective_logic` / `selective_logic_from_code` —
    tolerant coercion for the file/import layer (unknown names,
    out-of-range codes, nulls and booleans become `and_any`; numeric
    strings/floats coerce like `transfer._as_int`). Tolerance lives
    only here, so only canonical strings ever reach the strict layer.
  - `secondary_gate(mode, *, secondary_count, matched_count)` — the
    truth table as a pure function of counts: `and_any` fires when at
    least one secondary matched, `and_all` when every secondary
    matched, `not_any` when none matched, `not_all` when at least one
    secondary did not match. The scanner owns matching mechanics
    (whole-word, case, escaping); the gate owns only the logic.
- The empty-secondary rule: when an entry has **no usable secondary
  keys** (none defined, or all blank after the scanner's existing
  usable-key filtering), the logic is not applied in any mode — a
  primary match alone decides. This preserves the S202 invariant
  bit-for-bit (every pre-P-032 entry is `and_any` with exactly the
  old behaviour), matches the public behaviour (the logic is only
  consulted when secondary keys exist), and avoids the vacuous-truth
  trap in which a `not_all` entry whose secondaries were deleted
  would silently never fire. A primary match remains required in
  every mode — the NOT modes can never fire on their own.
- Scanner (`scan.py`, three small hunks, nothing else): `ScanEntry`
  gains `selective_logic` (adapted from the ORM row tolerantly, so
  rows or fakes without the attribute read as `and_any`); the
  secondary gate now asks `secondary_gate` instead of requiring a
  secondary hit; `ScanHit` gains `selective_logic`, echoing the mode
  that produced the hit — the forward hook for the activation
  inspector (P-043). Activation and preview are untouched: activation
  consumes hit ids only, and preview surfaces hits, so both inherit
  the new logic with zero edits.
- Storage: migration 0024 (**PROVISIONAL** — the keeper may renumber
  it at banking if P-031 takes 0024 first) adds
  `lore_entries.selective_logic TEXT NOT NULL DEFAULT 'and_any'`;
  the ORM gains the matching field. Existing rows read back as
  `and_any`, i.e. exactly their old behaviour.
- Service + API: `create_entry` / `update_entry` carry
  `selective_logic` under strict validation; `entry_to_dict` exposes
  it; the entry create/update API shapes gain the field (default
  `and_any`).
- Import/export: the field is modelled on both file legs, so
  `selectiveLogic` leaves the pinned dropped-field sets (see Test
  maintenance).
  - `transfer.py`: native entries carry the `selective_logic` name;
    world-info entries map `selectiveLogic` through the code table;
    `export_book` emits the name; `validate_parsed_book` carries it
    into the transactional import's prepared rows.
  - `interop.py`: `WorldInfoEntry.selective_logic` is a first-class
    field (promoted out of `extra`, like `depth`/`role` in P-019);
    world-info export writes `selectiveLogic` under the module's
    no-fabrication rule — only when the source file carried it or the
    mode is not the default — so a file that never named the field
    does not gain it, and the corpus fixed-point round-trip holds
    (the Gale-Bell entry: code 1 in, `not_all` inside, code 1 out).

## Test maintenance

- The P-005/P-019/P-030 dropped-field pins shrink exactly by the one
  field this slice lands: `selectiveLogic` moves from
  `WORLDINFO_DROPPED_TODAY` (23 → 22 fields) to the mapped sets in
  `tests/test_p005_interop_corpus.py`,
  `tests/test_p019_lorebook_interop.py`, and
  `tests/test_p030_part2_gate.py`; the P-030 store-leg exact entry
  key set grows 13 → 14 keys with `selective_logic`. The Gale-Bell
  assertions now read the modelled field
  (`gale.selective_logic == "not_all"`) instead of the `extra`
  carriage. No assertion was weakened; each pin's own comment
  instructs a landing slice to make exactly this edit.
- Adding migration 0024 moves the schema head, so the head pins
  across the suite (migration lists, `applied[-1]`,
  `current_revision`, archive/restore `schema_revision`) move
  0023 → 0024 in twelve test files. Historical pins that assert the
  P-030 gate record's own text ("migration head remains 0023") are
  records of their slice, not head pins, and were left untouched.

## Carried findings

- **Overlap with P-031 (banking note for the keeper):** team-01's
  P-031 (recursive scanning) concurrently edits `scan.py`,
  `activation.py`, and `preview.py` in its own worktree. P-032
  touches neither `activation.py` nor `preview.py`, and its
  `scan.py` diff is three small, non-adjacent hunks (one import, two
  appended dataclass fields, the single secondary-gate block), shaped
  to compose with P-031's hunks in either merge order. P-031 banks
  first; the keeper reconciles `scan.py` at P-032's banking and
  should re-run `test_s202_scan.py`, P-031's battery, and
  `tests/test_p032_selective_logic.py` together at the merged tree.
- Migration 0024 is provisional for the same reason: if P-031 takes
  a migration of its own, the keeper renumbers at banking (the 0023
  precedent).
- The unrelated world-info boolean `selective` is not this slice; it
  remains preserved-as-data in `extra`, untouched.
