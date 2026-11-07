# Provenance on import (P-029) — 2026-11-06

Roadmap line: *Provenance on import: where a card came from and when, kept with it (creator credit survives in Rúnmál)*

## What was built

- Migration 0023 (**PROVISIONAL** — the keeper may renumber this
  migration at banking if P-028 takes 0023): one new column on
  `characters` — `provenance_json TEXT NOT NULL DEFAULT '{}'`.
  The ORM (`db/models.py`) gains the matching field.
- `src/runmal/characters/provenance.py` — the provenance record
  (version 1) and its builders.
  - A record is a small JSON object: `provenance_version`,
    `source_kind`, the card snapshot (`card_format`,
    `spec_version`, `creator`, `character_version`, `source`,
    `card_creation_date`, `card_modification_date`),
    `imported_at`, `original_filename` (basename only),
    `relpath` where a folder structure exists,
    `original_sha256`, `original_byte_length`, the import-time
    `content_hash`, and `parent_character_id` for copies.
  - `source_kind` is one of `library_folder`, `library_upload`,
    `api_json`, `copy`, `manual` (the funnel default).
  - The creator snapshot is taken from the parsed card at import
    time, so later editor rewrites of the card blob cannot
    rewrite the import record.
  - `parse_provenance` returns None for an empty / `'{}'` /
    unparseable record, so legacy rows serialise as no
    provenance rather than an empty object.
- Service funnel, in `create_character_from_card`:
  - New `provenance=` kwarg. `_resolve_provenance` merges the
    caller-supplied facts (source kind, filename / relpath,
    original byte facts) with the card snapshot, always stamps
    `content_hash` with the stored-form digest (the P-025
    identity), and stamps `imported_at` (UTC now) when the
    caller record lacks one. With no caller record the kind is
    `manual`, and when original bytes are in hand their real
    hash / length are recorded.
  - The record is written once, at row creation, as
    `provenance_json`. The exact-duplicate early return (P-025)
    runs before it, so a duplicate re-import stores no new
    record (see below).
- Import paths:
  - API create (`create_character`) passes
    `source_kind="api_json"` and no byte facts: the API receives
    an already-parsed dict, so there is no original file.
  - Library import (`library/service.py`): the batch carries a
    `source_kind` — `library_upload` for uploads,
    `library_folder` for folder imports — and `_finish_card`
    builds the record from the P-022 report entry's own facts
    (`entry.sha256`, `entry.size_bytes`, `entry.filename`,
    `entry.relpath`), which are the original file's bytes
    hashed at the import edge.
  - Copy (`duplicate_character`) builds a `copy` record with
    `parent_character_id` set to the source row's id and the
    source's stored-form hash as its `content_hash`.
- Read surface: `character_to_dict` gains `provenance`, and
  `versioning.version_to_dict` gains `provenance`, so the
  character read, the versions list, and the version detail all
  expose each row's own record.
- Honesty rule for byte fields: `original_sha256` /
  `original_byte_length` are present as null when the original
  file's bytes were never seen. They are null for `api_json`
  and `copy` by design — a re-serialisation is never hashed and
  passed off as the original file's bytes.
- Travel: provenance does NOT travel in card exports. The
  exporter is untouched, so exported v2 / v3 card bytes contain
  neither the original filename nor the `imported_at` stamp.
  The creator credit inside the card itself does travel — it is
  card content, not provenance. Provenance travels via the
  portable `.runmal` archive instead: it is a `characters`
  column, so the archive's row serialisation carries it and
  restore's name-matched row builder restores it verbatim.
- This closes the P-022 limitation: byte-level provenance,
  deferred there and in P-025 ("Byte-level provenance is
  P-029"), is now recorded on the library paths from the
  import edge's own hash of the original file.

## Test maintenance

- Adding the migration moves the schema head, so the
  head-revision pins in the existing tests were updated
  0022 -> 0023 in 11 test files. No assertion was weakened:
  each still pins the exact head.
- New battery: `tests/test_p029_provenance_on_import.py`
  (14 tests, all passing; output in
  `hidden_files/p029_battery.log`).

## Not in this slice

- No UI.
- Lorebooks are out of scope: provenance is recorded for
  characters only, even when a lorebook arrives in the same
  library batch.
- No per-import event log: provenance is one record per
  character row, written at creation. A duplicate re-import is
  not recorded as an event anywhere (see Carried limitations).
- No provenance search, filter, or merge across lineages.
- No backfill: pre-P-029 rows keep `provenance_json = '{}'`
  and serialise as null, forever (see Carried limitations).

## Clean-room basis

Shapes rest on P-002's census and public behaviour only.
No SillyTavern or Voxta source was inspected.

## Carried limitations (honest record)

- Migration 0023 is PROVISIONAL: the keeper renumbers it at
  banking if P-028 took 0023 first, and the head pins move
  with it.
- Byte fields are null for `api_json` and `copy`, permanently:
  those paths never held the original file, and the record
  says so rather than inventing a hash.
- A duplicate re-import stores no new record: the sibling's
  first-import provenance stands unchanged (first import
  wins), and the re-import itself leaves no trace.
- Legacy rows are null, never backfilled: a character imported
  before P-029 has no provenance, and none is reconstructed
  after the fact.
- The recorded `content_hash` is the import-time stored-form
  identity. In-place rewrites (update / editor / organise)
  change the live effective hash (P-025) but never the
  provenance snapshot — provenance records the import, not the
  current content.
- `imported_at` is the wall-clock time of the import that
  created the row. A `.runmal` restore preserves the original
  row (and its original `imported_at`) verbatim, by design:
  provenance is history, not a restore stamp.

## Evidence

Evidence: tests/test_p029_provenance_on_import.py — counts recorded in
the worktree hidden_files/ at banking.
