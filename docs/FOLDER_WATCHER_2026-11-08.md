# P-121 — Folder Watcher: Watched Folders Ingest as Attachments (Part VIII)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part VIII only its part-table line —
"VIII | Vision Services | P-117 – P-130" — and no per-slice
entries. This slice's scope is therefore DERIVED, not
roadmap-verbatim, from in-tree sources only: P-117's named-open
folder watcher item, and P-120's own evidence naming the
watcher as the natural follow-on once image attachments exist
— attachments are the watcher's first-class destination, and
until P-120 the watcher had nowhere honest to deliver. The
keeper reviews this derived scope at banking.

Base: 09dc4dd (P-119 banking record). Migration: NONE — head
stays 0041; the provisional 0042 was eyed only if a table
proved unavoidable and is NOT taken.

## Watcher honesty — the bound, stated plainly

There is NO watcher daemon in this slice: no background
thread, service or OS watcher observes any folder between
scans. No watcher/daemon machinery exists in-tree (no watchdog
dependency, no in-app background-task framework), and
inventing one would fake a service. What lands is an explicit
POLLING SCAN road: a "watch folder" is a registration (data),
and a scan is a deliberate operation that ingests what is new
since the recorded ingestions. Nothing claims more.

## What landed

New module `src/runmal/vision/watcher.py`:

- **Records** — `WatchFolder` (id, owner_id, chat_id — the
  designated chat, path as data, recursive + enabled flags,
  created_at) and `IngestedRecord` (watch_id, source_path,
  sha256, size, attachment_id, ingested_at): the dedupe memory
  of scans.
- **Store** — `WatchStore` on the P-117 house pattern: a
  versioned JSON index `vision_watcher.json` in the data dir,
  tolerant load (corrupt reads as empty, never bricks). NO
  migration.
- **Registration** — `register_watch` refuses plainly and
  stores nothing on an empty path, an empty chat, or an exact
  duplicate (same owner + chat + path). Registration does NOT
  require the folder to exist: existence is a scan-time fact,
  reported by the scan, never faked at registration.
- **Scan** — `scan_watch` refuses plainly (nothing ingested)
  on a disabled watch or a missing / not-a-directory folder.
  Candidates are files only, sorted by path, top-level or
  recursive per the registration, capped at
  `MAX_FILES_PER_SCAN` (200) with truncation named in the
  report. Per file: an unreadable file, bytes over the house
  16 MiB cap, and an attacher refusal are each a named skip
  storing nothing; the sha256 of the actual bytes is the
  dedupe truth — a (watch, path, sha256) already ingested
  skips as `already_ingested`, so an unchanged file never
  duplicates and a changed file at the same path ingests anew.
  Ingestion is P-120's `attach_image` as a chat-level
  attachment (message_id None; filename = the file's name, the
  operator's label, data only). The report names watch/chat,
  the scanned count, the ingested attachment ids, every skip
  with its reason, and the truncation flag. Only successful
  ingestions are recorded.
- **The lazy attacher (P-118 precedent)** — this slice's base
  predates P-120, so `attach_image` is resolved lazily at scan
  time and never imported at module load; when the attachments
  module is absent, a scan with no injected attacher raises a
  plain `WatchError` naming the absence and stores nothing.
  The keeper reconciles at banking, exactly as P-118 built
  against P-117's store format as data.
- **Custody** — `purge_chat` removes a chat's registrations
  and their ingested records, returning the registration
  count; `remove_watch` removes one registration with its
  records. The attachments themselves remain P-120 custody.

HTTP (vision/router.py, additive, bearer-gated, owner-scoped —
unknown OR foreign chat/watch = 404):

- `POST /vision/watch-folders` {chat_id, path, recursive?} →
  201 + the registration.
- `GET /vision/watch-folders?chat_id=` → the chat's watches.
- `DELETE /vision/watch-folders/{watch_id}` → removes it.
- `POST /vision/watch-folders/{watch_id}/scan` → the scan
  report; `WatchError` rides 422.
- `GET /vision/watch-folders/{watch_id}/ingested` → the
  ingested records for the watch.

Battery: tests/test_p121_folder_watcher.py (19 tests) — the
scan is exercised through an injected attacher with P-120's
shape and refusal discipline (this base carries no P-120
module), plus the absence-honesty case for the lazy road.

## Declined, with reasons

- **A live watcher daemon**: no machinery in-tree; inventing
  one would fake a service (above). Named open still — a real
  daemon road is its own slice if the machinery ever lands.
- **A real semantic caption provider**: no backend declares
  Capabilities.vision, no image wire, no local model (P-119).
- **OCR**: no engine in-tree.
- **Screen capture / camera flow**: no client surface or
  consent story in this server-side tree.
- **Wiring purge_chat into chat deletion in this slice**:
  P-120's own custody hooks are landing in chats/service.py in
  the sibling slice; this slice ships the purge in the P-118
  idiom for the keeper to wire at banking reconciliation,
  rather than editing the same function concurrently.

## Honest limitations

- Polling only: files are seen when a scan is called, never
  before. A file deleted between scans is simply absent; a
  file mid-write at scan time is judged by the bytes read.
- Watch registrations and ingested records are NOT
  SQL-queryable and do not ride DB backups; they live and die
  with the data dir, like the vision stores they mirror.
- Scanning generates no description or caption and performs
  no safety scan; ingestion inherits P-120's sniff-only
  stance, and no record claims a moderation result.
- The ingested index dedupes by (path, sha256): the same bytes
  at two different paths are two attachments, plainly.
