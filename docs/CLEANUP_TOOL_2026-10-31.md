# F-04 — Clean-Up Tool (2026-10-31)

*Part I follow-on F-04, homed by the P-014 gate from ST-73:
"the orphan and stale file scan with risk warnings, built over
the existing `runmal doctor` diagnostics (S804), which diagnose
but do not clean." This record is that build. No external source
was consulted and no mirror was read for this slice: ST-73's
behaviour was already recorded by P-002's census from
SillyTavern's official public documentation and judged MISSING
by P-004; the categories below are Rúnmál's own data shapes.*

## What was built

- **The tool** — `src/runmal/diagnostics/cleanup.py`:
  `scan_cleanup()` judges the installation and returns a
  `CleanupReport`; `clean_cleanup()` plans or performs removal
  from that report. The CLI is `runmal cleanup` (scan + dry-run
  plan by default; `--apply` removes; `--category` restricts,
  repeatable; `--allow-high-risk` unlocks the high-risk
  category; `--stale-backup-days` / `--stale-staging-days` set
  the age thresholds, defaults 30 / 7; `--json` prints the scan
  and the result; an unknown category exits 2).
- **Six categories**, each carrying its risk level and warning
  as data on every item (ST-73's per-category risk warnings):
  1. `orphan_character_assets` (medium) — a directory under
     `assets/characters/` whose id has **no character row at
     all** in the database.
  2. `unreferenced_character_files` (medium) — files inside a
     character's asset directory that are not the avatar the
     database references for that character, plus stray files
     directly under `assets/characters/`.
  3. `chats_of_deleted_characters` (high) — chats whose
     character is soft-deleted, or whose character row no longer
     exists, with the message count named per chat.
  4. `stale_backups` (medium) — `runmal-backup-*.db` and
     `runmal-full-backup-*.zip` files older than the threshold,
     **never the newest of their kind** (the newest is kept
     however old it is: an old recovery point beats none).
  5. `stale_staging` (low) — top-level staging entries older
     than the threshold; staging is verified restore scratch,
     never live data.
  6. `unrecognized_backup_files` (high) — files in `backups/`
     matching no Rúnmál backup naming; reported because a user
     may be storing something there, and **never removable** by
     this tool, whatever flags it is given.

## Removal discipline

- **Dry-run by default.** Scan and plan delete nothing; removal
  requires explicit apply (function argument / CLI flag).
- **Re-validation at delete time.** Each item is re-checked
  against the live tree immediately before removal: the
  character is still absent (or still deleted), the file is
  still unreferenced, the backup is still expired and still
  not the newest of its kind. Changed facts mean skipped,
  never deleted — pinned by the test where a character row
  re-created between scan and apply saves its directory.
- **Containment and symlinks.** Only paths resolving inside
  the data dir are removed; symlinks are never followed or
  removed (a symlinked asset directory is reported as skipped,
  and its target is untouched).
- **Database honesty.** The scan reads the database read-only
  raw SQLite, like the doctor, so it works on a broken
  install; if the database is missing or unreadable, the three
  database categories are recorded as **skipped, not judged** —
  nothing is called an orphan without the database's word —
  while the filesystem-only categories (backups, staging)
  still scan. Chat removal, the tool's only write, runs in
  one transaction with foreign keys enforced: messages and
  chat events cascade as they do in the app's own chat
  deletion, and `chat_summaries` (no foreign key, S404) are
  deleted explicitly. Memory rows are **not** touched:
  memories whose provenance pointed at a removed chat keep
  their statements and surface in the doctor's existing
  dangling-source warning — recorded here, not hidden.
- **No secret ever prints**: ids, paths, counts, sizes only.

## The doctor bug the scan exposed — fixed in-slice

The doctor's `assets_orphaned` test counted a directory as
orphaned unless its character **currently had an avatar**:
a live (or soft-deleted) character with no avatar but files on
disk was warned as orphaned, and following the doctor's own
"delete after confirming" action on that warning would have
removed a living character's files. `check_assets` now takes
every character row as owning its directory (avatar-bearing or
not, soft-deleted included — S303 retains those assets for
restore on purpose), and only a directory with no row at all
is orphaned. The doctor's other findings are unchanged; the
fix is pinned by an F-04 test beside the S804 suite, which
stays green.

## Coverage claim, stated exactly

ST-73 is covered in Rúnmál's shape: the mirror's four named
targets map to categories 1–4 above (orphaned files → 1/2,
images → 2, chats of deleted characters → 3, stale chat
backups → 4, with 5–6 as Rúnmál's own additions from its own
layout: staging scratch and unrecognized backup-dir files).
One deliberate difference: in the mirror the clean-up acts on
hard-deleted characters' remains; in Rúnmál deletion is soft
and restorable (S303), so a soft-deleted character's **assets
are never orphans here** and its chats are high-risk,
explicit-allowance removals — the sovereign shape keeps the
undo path intact until the owner knowingly spends it.
Thresholds are caller-set parameters with stated defaults,
not a hidden retention law: the tool invents no policy about
how many backups a user should keep beyond never removing
the newest of a kind.

## What this slice does not do

- It adds no web UI for clean-up; the CLI is the surface,
  matching the doctor it builds over.
- It touches no README.md, pushes nothing, and calls no
  live endpoint; all evidence is fixture installs under
  pytest temporary directories.
