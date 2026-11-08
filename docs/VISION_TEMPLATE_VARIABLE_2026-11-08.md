# P-118 — The Last Vision Description Reaches the Prompt (Part VIII, Vision Services — DERIVED scope)

## Derivation statement (binding honesty)

The governing roadmap (docs/RUNMAL_TWO_MIRRORS_PARITY_ROADMAP_
2026-10-30.md) gives Part VIII only its part-table line —
"VIII | Vision Services | P-117 – P-130" — and no per-slice
entries. This slice's scope is therefore DERIVED, not
roadmap-verbatim, from Runmal's own in-tree record only:
P-117's slice doc (docs/VISION_FOUNDATION_2026-11-08.md),
which names two open items that share one store — (3) the
last description is retrievable as data but the prompt
composer does not yet consume it as the VX-43/VX-50 template
variable, and (5) descriptions are never deleted by chat
housekeeping, custody on chat deletion named open — and the
census rows behind them (VX-43: Scriban templates over "...
the last vision description, and now ..."; VX-50: "the last
vision description is a template variable"). P-118 is items
3 + 5, one store, one slice. The keeper reviews this derived
scope at banking.

Base: ee235a2 (P-116 banking record, PART VII COMPLETE).
P-117 is NOT in this base (banked concurrently by team-02);
the keeper merges P-117 first at banking and reconciles.
This slice therefore reads P-117's store FORMAT
(vision_descriptions.json, version 1) as data and never
imports runmal.vision. Migration: NONE — head stays 0041.

## 1. What landed

- src/runmal/prompt/vision_link.py (NEW) — the read/custody
  side of P-117's store, format-pinned, import-free of
  runmal.vision:
  - descriptions_path(data_dir=None) — RUNMAL_DATA_DIR /
    vision_descriptions.json, the same resolution P-117's
    service and router use (data_dir or $RUNMAL_DATA_DIR,
    default .runmal-data).
  - load_descriptions(data_dir=None) -> list[dict] — tolerant
    load, exactly the store's own law: a missing, corrupt,
    or wrong-shaped file reads as NO descriptions; non-dict
    rows are skipped. Never an exception, never an invented
    row.
  - last_for_chat(chat_id, ...) -> dict | None — the last row
    in store append order bound to the chat;
    last_description_text(chat_id, ...) -> str — its
    description text, or "" when none.
  - purge_chat(chat_id, ...) -> int — custody: rewrites the
    store without that chat's rows, preserving the document
    version and all other chats' rows, in P-117's own write
    shape (json indent=2, sort_keys). A missing store purges
    0 and creates no file; a store with nothing to purge is
    left byte-untouched.
- src/runmal/prompt/variables.py — the S307 registry gains
  Variable("last_vision_description", "The chat's last vision
  description (empty when the chat has none)", "").
  resolve_variables(..., last_vision_description: str = "")
  substitutes the supplied value; the variable is KNOWN, so
  it never lands in unknown, and with no value supplied it
  resolves to the empty string — an honest empty, never a
  fabricated caption (P-075 no-content law). New
  resolve_variables_for_chat(text, *, chat_id, data_dir=None,
  **kw) fills the value from vision_link; an explicit
  last_vision_description in kw wins over the store lookup.
- src/runmal/tools/router.py — ResolveIn gains
  last_vision_description: str = "" and chat_id: str = "".
  The resolve road passes the explicit text, or — when a
  chat_id is given and no explicit text — the store's last
  description for that chat, so the preview shows what
  actually resolved (VX-43).
- src/runmal/chats/service.py — delete_chat() gains one
  guarded custody block in the house pattern (lazy import,
  try/except, never raises), after the undo block and before
  the chat.deleted plugin dispatch:
  vision_link.purge_chat(chat_id). A dead chat's descriptions
  no longer outlive it in the store — the voice-custody
  precedent (VoiceSessionStore.drop_chat) applied to vision.
- tests/test_s307_variables.py — the registry pin updated:
  the exact list gains "last_vision_description" (growth,
  not weakening; no assertion removed or loosened).
- Battery: tests/test_p118_vision_template_variable.py
  (17 tests) — registry, resolver (supplied value, honest
  empty, case-insensitivity, unknowns still flagged),
  vision_link (missing/corrupt/wrong-shape tolerance, last
  is the append-order last per chat, purge counts and
  preserves, purge idempotence and no-file creation),
  resolver+store glue (fill from store, explicit wins),
  the tools road (explicit text and chat_id roads), chat
  deletion custody end to end, and the migration pin
  (head stays 0041).

## 2. Laws held

- P-075 no-content law: no description is ever fabricated.
  Absence resolves to "" everywhere — resolver, for-chat
  glue, and the tools preview alike.
- Clean-room: built from Runmal's own record only (P-117's
  store format as data, the S307 variable model, the house
  guarded-custody pattern). No SillyTavern or Voxta source
  was read; nothing was downloaded.
- Format pinned in ONE place: if the keeper's P-117 merge
  ever moves the store format, vision_link is the single
  module to re-pin. Its purge write shape was verified
  byte-identical to P-117's VisionStore._save shape.
- No migration, no new store, no writer: vision_link never
  appends descriptions — P-117's VisionStore stays the
  only writer.

## 3. Honest limitations

- No semantic caption provider lands here, and
  Capabilities.vision is still declared by no backend:
  P-117's named-open items 1 (semantic providers, local
  first) and 2 (Capabilities.vision backend truth in
  provider selection) stay open for later Part VIII slices.
- No screen capture, folder watcher, camera flow, OCR, or
  image attachments on chat messages (P-117 open item 4
  stays open).
- The variable surface wired is the S307 composer variable
  model plus its tools preview road — the in-tree
  prompt-variable surface. Per-field Scriban templating
  (VX-43 in its full form) remains Part IX scope.
- The tools road treats an empty explicit text as "no
  explicit text": with a chat_id also given, the store
  value resolves. Callers who need a forced empty use the
  resolver directly (resolve_variables, where an explicit
  "" always wins by construction).
