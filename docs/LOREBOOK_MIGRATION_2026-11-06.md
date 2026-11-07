# Migration: existing lorebooks upgraded in place (P-047) — 2026-11-06

Roadmap line: *Migration: existing Runmal lorebooks upgraded
in place, behaviour-preserving, fixture-proven.* Part III
(Lorebook Depth).

## What was built

- `src/runmal/lorebooks/upgrade.py` — the explicit upgrade
  layer (report schema `runmal-p047-lorebook-upgrade-v1`,
  frozen for P-048's gate):
  - `inspect_lorebook(data)` — a frozen-key report on what an
    upgrade would do: detected format (interop's own
    detector, the only one), a derived-only generation label
    (`native-current` / `native-legacy` / `worldinfo`, never
    stored), entry count, book/entry missing-field sets with
    per-field counts, unknown fields and their preserved
    count, `defect_fixes`, `would_change`, and the behaviour
    verdict (`behaviour_preserving` + `behaviour_diffs`).
  - `upgrade_lorebook(data)` — the in-place upgrade, SAME
    format out as in. Native: raw-seeded + overlay of the
    interop layer's `native_fields()` (the canonical
    upgraded-native field set — neither stock exporter may
    build it; both drop book/entry `extra`). Every current
    field is materialised explicitly; `depth` is emitted as
    `None` (undeclared — the at-depth default 4 materialises
    at compose time only, never in the file), `token_budget`
    is copied verbatim (null stays null), mapped aliases
    (`vectorized`, `useProbability`) are canonicalised to
    `vectorised` / `use_probability` and the alias spelling
    dropped, and unknown keys survive verbatim. World-info:
    a raw-seeded refresh through interop's own
    `export_worldinfo` — uids, `originalData`, entry `extra`
    and unknown position codes ride back unchanged.
    Idempotent (exact dict equality); the input is never
    mutated.
  - `upgrade_database(db_path)` — the DB layer: raw-sqlite
    snapshots of `lorebooks` + `lore_entries` (by column
    name, raw (type, value), never through the ORM), the
    ordinary migration chain (`migrate_to_head`), a second
    snapshot, and the proof: every pre-existing row survives
    by id, every pre-existing column value is byte-identical,
    counts are unchanged, and each column revisions
    0024-0032 added holds exactly its behaviour-preserving
    default on pre-existing rows. A missing database reports
    `missing`; a database with no lore tables reports
    `no_lorebooks` and is left untouched (the revision read
    on that path is side-effect-free — see the defect note).
- `src/runmal/lorebooks/router.py` — two routes, registered
  immediately after `pack/inspect` and before the
  `/{book_id}` family (placement is load-bearing: appended
  at the end, `{book_id}` would swallow `upgrade`):
  `POST /lorebooks/upgrade/inspect` (report, no write) and
  `POST /lorebooks/upgrade` (returns `{lorebook, upgrade}`;
  writes nothing to the database). `upgrade_database` stays
  library-only — no route exposes it.
- Defect fix in `src/runmal/lorebooks/transfer.py` (below).

## Why same-format, and why no new migration

- The roadmap's antecedent is *existing Runmal lorebooks*:
  native files and stored books. A world-info file is a
  foreign import, not an existing Runmal book — converting
  it to native would destroy uids, `originalData`, `extra`
  and unknown position codes (the INV-009 preservation
  discipline) and fabricate book fields its source never
  had (`parse_import` reads only a name from it). The
  world-info leg is therefore an honest refresh in place,
  and the report names its generation `worldinfo`, not a
  migration.
- The DB schema already carries the upgrade machinery:
  revisions 0024-0032 are pure ADD COLUMN + new tables
  (zero UPDATEs, designer-verified), each default exactly
  the pre-Part-III behaviour. P-047's DB work is to *prove*
  that chain on a fixture frozen at 0023 — no new schema
  change exists to number. NO migration taken; head stays
  0032.

## The behaviour proof (fixture-proven)

- File layer: the invariant is stated over the interop
  layer (the lossless one): parsed old and parsed upgraded
  agree on `native_fields()` + `native_book_fields()`, with
  ONE enumerated exception — the defect-fix entries, whose
  stored-probability delta is asserted explicitly (below).
  `transfer.parse_import` equality is the secondary check.
  Two pre-existing leg divergences (stringly `keys`, a
  stringly `position`) are documented in the battery as
  divergences, not silently resolved: the upgrade does not
  rewrite values the two legs already read differently.
- DB layer: a fixture database built at revision 0023
  (migration modules + version rows exactly as the runner
  writes them, lore rows in 0004/0005 columns only) is
  upgraded to 0032; in addition to the snapshot proof, the
  full `preview_activation` result (fixed seed + roll
  context, no vector embedder, called directly — never via
  the HTTP route) over rows built from the pre-upgrade raw
  data equals the result over the upgraded ORM rows,
  dict-for-dict.

## Defects fixed in-slice

1. **`transfer._native_entry` dropped `use_probability`**
   (scout-confirmed): a native entry carrying
   `probability: 30, use_probability: false` imported with
   the gate live at 30, while the world-info leg and the
   character-book normaliser fold an explicit false to the
   gate-off effective percent 100 (the store carries the
   effective percent, not the flag). The native leg now
   folds both spellings (`use_probability` canonical, the
   `useProbability` alias accepted; snake wins on
   disagreement; an explicit None does not fold). The
   upgrade report counts such entries as `defect_fixes`,
   never as behaviour deltas. Pinned by 7 battery cases.
2. **`upgrade_database` touched a no-lorebook database**
   (battery-found): the revision read created the
   `schema_migrations` table inside an empty file,
   contradicting the report-and-stop promise. The
   no-lorebooks path now reads the revision raw and writes
   nothing.

## Carried discovery (not fixed here)

`binding.normalise_book_entry` returns no `depth` / `role`
keys: embedded character-book entries cannot carry P-038
placement into materialisation. Discovered by the P-047
scout; outside this slice's migration scope (fixing it
changes P-039 materialisation semantics and needs its own
battery) — recorded in the evidence file for the keeper to
commission.

## What deliberately did not change

- No migration: schema head stays 0032. `interop.py`,
  `packs.py`, the export shapes and every existing route
  are unchanged; the two new routes are additive.
- The native format stays version 1: old and new files are
  told apart by the inspect report's derived generation,
  never by a stored stamp.

## Tests

- `tests/test_p047_lorebook_migration.py` — see
  `hidden_files/P047_EVIDENCE.md` in the team worktree for
  the run counts (battery, neighbours, full suite) read
  back from the log files.
