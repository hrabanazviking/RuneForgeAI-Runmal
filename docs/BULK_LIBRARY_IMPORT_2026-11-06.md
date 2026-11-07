# Bulk library import (P-022) — 2026-11-06

Roadmap line: *a whole folder of a user's cards + lorebooks imported as
one act, with a report (accepted/repaired/refused with reasons).*

## What was built

- `src/runmal/library/` — new package.
  - `service.py`: `import_library_folder` (a folder on disk, recursive
    by default) and `import_library_uploads` (an uploaded file set)
    share one batch driver. Every file seen is accounted for exactly
    once in the report: accepted, repaired, refused (with a closed
    refusal-code list and a human reason), or skipped (symlinks never
    followed, unsupported extensions, path traversal on uploads).
  - Classification is content-first, never extension-first: PNG and
    ZIP/CHARX by signature, JSON by shape — card, lorebook (native or
    world-info), ambiguous (both shapes → refused), or a recognised
    foreign shape (preset → P-021, chat → P-020, persona → P-018),
    which is refused as `unsupported_kind` pointing at its home slice.
  - Repairs come from a closed list only: `bom_stripped`,
    `content_sniffed`, `lorebook_name_from_filename`,
    `name_whitespace_trimmed`. Nothing else is silently fixed.
  - Exact duplicates are refused, against the existing library and
    within the batch; same-name/different-content imports are accepted
    and noted (`name_collision:<id>`) — versioning is P-025.
  - Each file is its own transaction: one file's failure never undoes
    another's, and a lorebook is pre-validated whole before any row is
    written, so a bad entry leaves no partial book.
  - Limits: 1000 files, 512 MiB total, depth 8, per-file card-parser
    size limit (oversize folder files are refused from `stat`, never
    read whole). Dry run runs the full validation path and stores
    nothing; its verdicts match a real run's.
  - `models.py`: the report carries names, sizes, hashes, verdicts and
    reasons only — never file contents. Totals are recomputed from the
    entries on serialisation.
- `router.py`: `POST /api/v1/library/imports` (multipart `files`,
  optional `dry_run`). Folder paths are never accepted over HTTP —
  folder import is CLI-only. A filename that escapes the picked folder
  becomes a skipped report entry, not an error; an unrecognised
  `dry_run` value is a 400 (fail closed, never a silent real import).
  400 only when no files are supplied at all; partial success is 200.
- CLI: `runmal library import <folder> [--dry-run] [--json]
  [--user-id ID]` — exit 0 when nothing was refused, 1 on refusals,
  2 when the act could not run.
- Helpers: `characters/service.create_character_from_card` (the stored
  bytes are exactly what `create_character` always stored) and
  `lorebooks/transfer.import_book_transactional` +
  `validate_parsed_book`.

## Not in this slice

- Card asset bytes are noted (`assets_deferred_p023:<n>`) but not
  persisted — asset storage is P-023.
- Duplicate detection hashes the normalised stored form, so two files
  that differ only in fields the stored form drops count as exact
  duplicates. Byte-level provenance is P-029.
- World-info lorebook fields with no Rúnmál home yet (selective logic,
  probability, recursion, groups) are dropped by the lorebook path
  exactly as in P-005/P-019; P-019's interop module lands on this
  branch when the keeper merges slices in roadmap order.
- A flat file that is simultaneously a minimal persona shape and a
  minimal card shape is refused as a persona (the P-018 census shape
  wins); envelope/spec cards are never affected.

## Clean-room basis

Shapes rest on the P-002 census and the P-005 authored corpus
(public behaviour and specs only). No SillyTavern or Voxta source was
inspected.

## Evidence

`tests/test_p022_bulk_library_import.py` — battery in the worktree's
`hidden_files/` logs (battery, neighbours, full suite).
