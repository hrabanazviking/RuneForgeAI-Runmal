# Content safety rails (P-027) — 2026-11-06

Roadmap line: *P-027 Content safety rails: imported content is data, never code — importers parse defensively* (founding security model `docs/SECURITY_MODEL.md` §9/§13 kin).

## The measured gap

Seven findings, each an unbounded or silently lenient parse of
untrusted imported content:

1. Unbounded PNG `zTXt` zlib decompression in the card parser:
   a small compressed chunk could expand without limit.
2. Deep JSON produced a bare `RecursionError` instead of a
   typed refusal.
3. Duplicate JSON keys silently resolved last-wins, so the
   field a validator saw could differ from the field a later
   reader used.
4. CHARX duplicate and symlink members were silently accepted.
5. Lorebook and persona interop had NO byte cap at all.
6. The portable `.runmal` `validate_archive` had no member,
   per-member, or total caps, and `restore.py` wrote assets
   without a containment re-check.
7. Three upload endpoints read request bodies unbounded
   (`await upload.read()`) before any downstream cap ran.

## What was built

- New package `src/runmal/safety/` — the single home for the
  defensive-parse guards. Importers call the guards first, so
  a hostile or merely broken file is refused for a typed,
  testable reason before any recursive or unbounded parser
  touches it.
  - `guards.py`:
    - `SafetyError` / `SafetyErrorKind` — the typed refusal.
      Kinds cover input too large, nesting too deep,
      duplicate key, invalid JSON, decompression too large,
      duplicate member, link member, and archive member /
      total caps. Error messages name limits, member names
      and key names only; they never include payload body
      content, so a refusal is safe to log or surface.
    - `check_bytes` — refuse input over a byte limit.
    - `safe_json_loads` — size cap, then an iterative depth
      pre-scan (`MAX_JSON_DEPTH = 100`, bracket counting that
      skips strings and escapes, never recursing), then
      `json.loads` with duplicate-key rejection; a parser
      `RecursionError` is still converted to a typed
      `NESTING_TOO_DEEP` refusal as a belt-and-braces measure,
      and decode failures become `INVALID_JSON`.
    - `validate_json_tree` — iterative depth check of an
      already-decoded tree, using an explicit stack.
    - `bounded_zlib_decompress` — decompress with at most
      `limit + 1` bytes ever materialised; output over the
      limit is `DECOMPRESSION_TOO_LARGE`.
    - `audit_zip_members` — audit an archive member table
      before anything is extracted: duplicate names, link
      members, member count, per-member size and total
      declared size.
  - `uploads.py`:
    - `read_upload_capped` — chunked streaming read of an
      upload that refuses the moment the running total passes
      the caller's limit, so at most roughly
      `limit + chunk_size` bytes are ever held.
  - `__init__.py` re-exports the guards and the capped reader.
- Adapters translate `SafetyError` into each house typed
  error — the card parser keeps using its existing
  `CardErrorKind` values (`INPUT_TOO_LARGE`, `INVALID_JSON`,
  `TRUNCATED`, `ASSET_TOO_LARGE`, `BAD_ARCHIVE`); there is
  NO new `CardErrorKind`. Lorebook, persona and preset
  interop likewise surface their own house parse errors, and
  the portable archive surfaces `ArchiveError`.
- Wiring, per importer:
  - `cards/parser` — PNG `zTXt` decompression is bounded at
    32 MiB (`MAX_INPUT_BYTES`) via `bounded_zlib_decompress`;
    JSON cards parse via `safe_json_loads` under the same
    cap (the existing truncated-vs-invalid distinction is
    preserved); CHARX archives are audited with
    `audit_zip_members` before members are read.
  - `lorebooks/interop` — new `MAX_LOREBOOK_BYTES` (32 MiB)
    byte cap plus `safe_json_loads`.
  - `lorebooks/transfer` — `validate_json_tree` depth check
    on the already-decoded import shape.
  - `presets/interop` — `safe_json_loads` under the existing
    `MAX_PRESET_BYTES` (8 MiB) cap.
  - `persona/interop` — new `MAX_PERSONA_BYTES` (8 MiB)
    byte cap plus `safe_json_loads`.
  - `chats/fileimport` — per-line and whole-file parses use
    `safe_json_loads` under the existing per-line and
    whole-chat byte caps.
  - `portable/archive` — `validate_archive` now enforces
    declared caps via `audit_zip_members`: 100,000 members,
    64 MiB per member, 512 MiB total declared size, plus
    link-member rejection.
  - `portable/restore` — asset writes re-check containment:
    each target is resolved and must stay inside the resolved
    staging root before any bytes are written (defence in
    depth; the validator's name check is never trusted alone
    before touching the filesystem).
  - `characters` / `assets` / `library` routers — uploads
    are read with `read_upload_capped` (avatar, asset and
    library total caps respectively) and a `SafetyError`
    becomes HTTP 413 before the generic `ValueError`
    handling, instead of an unbounded read followed by a
    downstream size check.

## Not in this slice

- No content moderation or censoring — out of scope, and it
  would break INV-009 preservation of imported content.
- No semantic prompt-injection filtering (see Honest
  limitations (b)).
- No new endpoints.
- NO migration — the schema head stays 0021.

## Honest limitations

- (a) HTTP dict-body routes are pre-parsed by
  FastAPI/Starlette, so duplicate keys there collapse before
  Rúnmál code runs: duplicate-key refusal is guaranteed on
  the file parsers; JSON-body routes get depth validation
  only.
- (b) Fields whose format purpose IS prompt text remain
  prompt text. The rails police privilege — execution,
  filesystem, network, and extra prompt privilege — not
  wording.
- (c) The zip caps trust central-directory declared sizes
  for the cheap pre-check. Symlink detection uses the unix
  `external_attr`; the load-bearing rail is that no
  extraction path creates links, plus the restore
  containment re-check.
- (d) The depth pre-scan is structural: malformed JSON still
  fails in `json.loads`, surfaced with the house typed
  errors.
- (e) JS render safety is evidenced by the node battery only.

## Clean-room basis

The requirements rest on the repo's own
`docs/SECURITY_MODEL.md` (§9: imports and assets are
untrusted input — bounded archive extraction, content-size
limits, no execution of imported scripts/macros by default;
§13: security acceptance mindset — negative cases are
first-class tests), the roadmap's P-027 line, and public
behaviour only. No SillyTavern or Voxta source was
inspected.

## Evidence

- Battery: `tests/test_p027_content_safety_rails.py` —
  36 passed.
- Neighbours: 327 passed.
- JS renderer tests: ALL PASS.
- Full suite: 1086 passed / 4 skipped (P-024 base was
  1050 passed / 4 skipped; +36 new battery, zero
  regressions).
- `test_s503` passed inside the full suite this run, so the
  classified-noise solo re-run was not needed.
- Builder neighbour runs during construction:
  108 + 66 + 73 passed.
- Guards smoke: 38/38.
