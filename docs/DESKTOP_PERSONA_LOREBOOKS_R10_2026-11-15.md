# R-10 — Persona & Lorebooks (windowed shell)

## Definition (before implementation)

**Slice:** R-10 of the Interface Redo plan (Part 3): "Persona panel
(R-03 routes) + schema-driven lorebook editor, scopes, preview,
character bindings."

**Owning subsystem:** the desktop shell (`src/runmal/desktop/`)
over existing engine routes. No new engine routes; the route
census (365 paths / 455 operations) is unchanged.

### What "persona" honestly is in this engine

The plan (§1.4) is explicit: there is no persona store. Persona
resolves to exactly two mechanisms, both shipped as routes by
R-03 (`persona/router.py`):

- the persisted `{{user}}` name — `GET /user-name` (the stored
  name or the default "User", with `is_set` saying which) and
  `PUT /user-name` (an empty name clears back to the default);
- a chat's active persona — `GET /chats/{id}/persona` and
  `POST /chats/{id}/persona` over `chats.service.set_chat_persona`:
  the character card the chat speaks with, an explicit state
  change affecting FUTURE turns only (stored messages keep their
  original speaker snapshots).

The engine library also carries a persona-file interop format
(`persona/interop.py`, ST-shaped `UserPersona`) — but **no route
serves it**, so the shell does not offer persona import/export;
the panel names this rather than dressing up a decoy (plan §1.4:
"surface what exists and name it honestly").

**Persona panel (Characters ▸ Persona…):** the `{{user}}` name
with set/clear; the open chat's persona with switch-to-character
and clear, labelled with the future-turns-only semantics; an
explainer of what persona means here.

### Lorebooks

Engine surface (`lorebooks/router.py`, all existing): book CRUD
(`POST/GET/PATCH/DELETE /lorebooks[/{id}]`), import
(`POST /lorebooks/import`) and export
(`GET /lorebooks/{id}/export`), entries CRUD
(`POST/GET/PATCH/DELETE /lorebooks/{id}/entries[/{entry_id}]`),
scopes (`PUT/DELETE /lorebooks/{id}/scope`,
`GET /lorebooks/{id}/scopes`, `GET /lore-scopes`), the
activation preview (`POST /lorebooks/{id}/preview`), the layered
per-chat preview (`POST /chats/{id}/lore-preview`), and the
editor census (`GET /lorebooks/editor-schema`, P-042).

**Schema-driven editor (World ▸ Lorebooks…):** the book and
entry forms are GENERATED from the editor-schema census — field
order, kinds (text / longtext / int / int_or_null / keys / bool /
select with the census options) come from the engine's own
schema, never a hand-copied list; the shell adds human labels
and help per field name. One honest exception: `activation_kind`
is a derived census field (computed from `constant` /
`vectorised`); the form shows it as read-only words and never
sends it. Unknown fields on a stored entry (forward-compatible
data) are carried verbatim on save, as with R-09's open bags.

**Scopes:** assign/unassign a book to global / character /
persona / chat scopes with an owner picker (characters roster /
open chat), a per-assignment token budget and position; the
book's assignments are listed in words. Scopes are named as
their own mechanism — distinct from the card editor's P-039
lorebook binding (R-08), which stays where it is.

**Preview:** sample messages (one per line) run through the
book's own activation preview and, for the open chat, the
layered lore-preview; every entry's verdict is rendered in
words — Included (matched keys, via, tokens), Not triggered,
Discarded (with the budget reason), Disabled, Group-excluded —
plus the layered scopes summary (per layer: books, budget
enforced, tokens used, included/discarded counts). This is the
shell-side stand-in for the Inspector's lore trace until R-12
lands the full trace view (the plan's R-10 note).

### Failure behaviour

- Every road's failure surfaces as plain words in the dialog's
  status line (the R-08/R-09 pattern); nothing fails silently.
- Entry/book saves validate client-side against the census
  kinds (ints parse, probability 0–100 by the model's own
  bounds surfaced as words) and still surface engine 422s
  verbatim in plain form.
- Deleting a book or entry asks first (the house confirm
  pattern); there is no undo road for lorebooks, and the
  confirm says so.

## Acceptance contract

- Logic tests (Qt-free, fake transport): schema-driven form
  model (fields follow the census, kinds map, derived
  `activation_kind` read-only), book/entry save payloads exact,
  unknown entry fields carried, scope assign/unassign payloads,
  preview verdict words for every status, persona flow
  (user-name set/clear, chat persona switch/clear).
- Live tests (real engine in-process): create a book + keyworded
  entry through the flow; assign a character scope; the layered
  lore-preview for a chat of that character reports the entry
  **included** with its matched key when the sample message
  carries the keyword, and **not_triggered** without it;
  user-name round trip; chat persona switch round trip.
- Window tests (real Qt, offscreen): the dialogs open from the
  window with the open chat's context; the entry form renders
  one editor per census field; persona switch updates the
  Session dock's persona line.
- Launch proof (`scripts/desktop_r10_proof.py`): in the real
  app — set the user name; create a character + chat; create a
  lorebook with a keyworded entry through the dialog; assign the
  character scope; ask about the keyworded fact (send the
  keyword in a message); the dialog's chat lore-preview shows
  the entry fired (included, matched key named); switch the
  chat's persona and see the Session dock agree; restart →
  book, entry, scope, and user name persist; clean quit.
- Neighbour gates: R-02…R-09 batches + the lorebook engine
  batteries (S209/P-037/P-039/P-041/P-042/P-044 families) stay
  green; the P-232 file shows only the known pre-existing H1
  footprint failure; full-suite collection count tracked; ruff
  clean on new files.

## What was built

- Client roads (`client/core.py`, models `LorebookView`,
  `LoreEntryView`, `LoreScopeView`, `PreviewRow`,
  `LayerScopeSummary`): lorebook list/get/create/update
  (PATCH)/delete/import/export, the editor-schema census,
  entry list/create/update/delete, book scopes
  list/assign (PUT)/unassign (DELETE with query params), the
  book activation preview, the layered chat lore-preview
  (rows + per-layer summaries + shadowed), and
  `set_chat_persona` (the R-03 road the panel switches with).
  Census unchanged: 365 paths / 455 operations; no new engine
  routes.
- `src/runmal/desktop/persona_logic.py` (new, Qt-free):
  `PersonaFlow` (user-name read/set/clear with the engine's
  default semantics; chat persona read/switch/clear) and the
  panel's words.
- `src/runmal/desktop/lore_logic.py` (new, Qt-free): the
  census form model (`SchemaField`, `schema_fields` — the
  census's own `derived` kind honoured for `activation_kind`),
  human labels/help per field, `collect_fields` composing
  saves over the stored document (unknown fields survive;
  identity/read-only keys stripped before sending), plain-words
  validation mirroring the models' bounds, scope words, and
  preview verdict words for every engine status plus the
  layered scope summaries. `LoreFlow` over the client.
- `window.py`: `SchemaFormWidget` (one generated form for the
  book and entry surfaces; typed value round-trip; the derived
  activation-kind label recomputed live from the Always-on /
  Vectorised toggles), `PersonaDialog`, `LorebooksDialog`
  (Book / Entries / Scopes / Preview tabs), real
  World ▸ Lorebooks… and Characters ▸ Persona… actions.
- Tests: `tests/test_r10_lore_logic.py` (12),
  `tests/test_r10_lore_live.py` (2 — the character scope fires
  in the layered preview on the real engine; persona roads
  round trip), `tests/test_r10_desktop_window.py` (3).
- Proof: `scripts/desktop_r10_proof.py` — 34 checks driving
  the real app: user name + persona switch through the dialog
  (Session dock follows), book + keyworded entry through the
  census forms, character scope assigned, a real send asking
  about the keyword, the layered preview showing the entry
  fired (Included, matched key named), restart persistence
  (name, book, entry, scope, persona), clean quit.

### Gate evidence (2026-11-15, seat purplelongship)

- Logic 12/12, live 2/2 (venv312 + PYTHONPATH), window 3/3
  (shell venv, PySide6-Essentials 6.8.0.2, offscreen).
- Neighbours: R-02…R-09 logic/live + the lorebook engine
  batteries (S201, S209 ×2, S304, P-019, P-037, P-039, P-040,
  P-041, P-042, P-044, P-045, P-047) + P-207 + S806 + S807 =
  430 passed; window neighbours (R-04…R-10) 22 passed; the
  P-232 file shows only the known pre-existing H1 footprint
  failure. Full suite collects 6,651 (R-09: 6,637; +14
  Qt-free tests). Ruff clean on the whole desktop package and
  all new files.
- Launch proof 34/34 PASS: purplelongship (Linux x86-64,
  offscreen) and Mimir (Linux ARM aarch64, offscreen).
  Evidence: goal `hidden_files/r10-evidence/`.
- **Deferred venues:** purpleraider (offscreen + workshop
  Wayland) — deferred under Volmarr's purpleraider pause.
  F15 Windows (offscreen) — deferred: the machine was
  unreachable on 2026-11-15 (powered off or asleep; see the
  R-09 record); the R-09 + R-10 proofs are owed on the F15
  when it wakes, and in any case at R-17.
- Transport: authored on the VM clone, carried to the seat
  over a git transfer branch (`yrsa/r10-transfer`, deleted at
  banking); main moved only at banking, from the seat, after
  gates.
