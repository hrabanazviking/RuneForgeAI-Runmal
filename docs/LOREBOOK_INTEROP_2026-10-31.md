# P-019 — Lorebook File Interop (2026-10-31)

*Part II (Cards & Content Interop): ST world-info JSON in/out —
entries, keys, and settings preserved; Part III deepens
behaviour. Acceptance in `tests/test_p019_lorebook_interop.py`.*

## The measured gap this slice closes

On entry, lorebook file interop was **half a road**:

- Import existed (S304's `transfer.parse_import`) but mapped
  only a subset: P-005 pinned **23 entry fields dropped** on
  world-info import (selective logic, probability, recursion
  flags, groups, depth/role, scan depth, filters, triggers,
  decorators, budget/outlet fields, source id/displayIndex),
  the at-depth position (code 4) **collapsed** to `before_char`,
  and book-level settings beyond the name (including
  `originalData`) were dropped.
- **No world-info export existed at all**: the only export
  shape was Rúnmál's native one, so a file that arrived as
  world-info could never be handed back in its own shape.

## What was built

`src/runmal/lorebooks/interop.py` — a file model in the P-018
persona pattern (no database schema changes):

- `parse_lorebook_file(bytes | str | dict)` — defensive import
  of both shapes (world-info dict-keyed or list entries; native
  list shape with or without the format marker). Invalid JSON,
  a non-object, missing/wrong-typed `entries`, a non-object
  entry, and a nameless native book are each rejected with a
  typed `LorebookParseError`. World-info name tolerance matches
  `parse_import` ("Imported lorebook"); numeric fields keep
  P-005's tolerant coercion (nulls → defaults, numeric strings
  coerced, never a bare `TypeError`).
- `LorebookFile` / `WorldInfoEntry` — the whole file as data:
  the natively-modelled fields (the P-005 mapped set) plus
  everything else carried, never interpreted:
  - the 21 remaining P-005-dropped fields verbatim in `extra`
    (per entry) and book-level unknowns + `originalData`
    verbatim at book level;
  - `depth` / `role` (the at-depth companions, ST-18) as
    first-class preserved data — `depth` tolerantly coerced,
    `role` verbatim (its code table is Part III's to define),
    neither fabricated when absent;
  - every entry's complete original mapping in `raw`.
- Position codes attested in-tree are mapped as data:
  0 → `before_char`, 1 → `after_char`, 4 → `at_depth`. Any
  other code is preserved verbatim in `position_code` with no
  semantics claimed and hands back unchanged.
- `export_worldinfo(book)` / `export_worldinfo_bytes(book)` —
  export starts from `raw` and overlays the normalized known
  fields (INV-009), so unknowns survive verbatim and
  re-export is a **fixed point** (pinned byte-for-byte).
  Optional fields are written only when they arrived or carry
  a non-default value — never fabricated.
- `export_native(book)` — the native shape from the same
  model, so a world-info file can also land in Rúnmál's own
  shape with its mapped fields intact.
- The export endpoint gained the second shape:
  `GET /lorebooks/{id}/export?format=worldinfo` (default
  `native` unchanged; an unknown format is a 422). On the DB
  side only natively-modelled fields exist, so only they are
  written — DB bookkeeping (ids, timestamps) is stripped and
  never leaks into the file.

## What deliberately did not change

- `transfer.parse_import` and the DB import path are
  **unchanged**: the database still stores the natively-
  modelled subset, and the at-depth code still collapses
  there (pinned side-by-side in the P-019 tests). Preservation
  is a file-layer guarantee in this slice, exactly as P-018's
  was; Part III slices (P-031–P-038) deepen the behaviour and
  the storage of the fields this slice preserves as data.
- P-005's corpus test is untouched: its dropped-set pin still
  describes the DB-path importer exactly, and the P-019 tests
  pin the file layer against the same 23-field set.

## Clean-room basis

Own tree only, plus the shapes already logged: P-002's census
of SillyTavern's official public documentation (ST-15–ST-27)
and P-005's authored corpus fixtures. No mirror source code
was read; no lorebook file was downloaded.
