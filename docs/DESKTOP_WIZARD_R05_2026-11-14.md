# First-Run Setup Wizard — R-05 (2026-11-14)

The second UI slice of the windowed-shell redo: the setup wizard
plan §2.3 promises a fresh install. Before R-05, R-04 could only
*detect* the first-run state (zero backend profiles AND zero
characters) and say the wizard was coming. R-05 builds it: a
four-step `QWizard` that connects a mind, proves the connection in
plain words, introduces a first character, records the user's name,
and finishes into a greeted chat in the main window. It adds **no
engine routes** (route census unchanged at 365 paths / 455
operations) — every road it uses was banked by R-02/R-03 and is
reached through the R-04 client layer.

## Definition (before implementation, per repo law)

- **Owning subsystem:** `src/runmal/desktop/` — wizard widgets in
  `wizard.py`, all decisions in the Qt-free `wizard_logic.py`, all
  HTTP in `client/` (the R-04 boundary, unchanged in kind).
- **Inputs:** the R-02 backend-profile roads (CRUD, write-only
  secret set, health, models), the characters road + the library
  bulk-import road (card JSON/PNG), the chats roads (create with
  greeting seeding, backend-profile pin, message list), the R-03
  user-name roads, and the R-03 composed turn for the proof's final
  answer check.
- **Outputs:** a launchable wizard (auto-shown on first run by the
  app entry; File → First-Run Setup… any time), the client methods
  listed below, and a main window that lands in the greeted chat on
  completion.
- **Invariants honoured:** INV-023 (API keys are write-only end to
  end: password-masked field → one request body to the dedicated
  secret route → secret store; the value is never retained by the
  flow object, never in a profile shape, log, error, or proof
  output), INV-024 (Ollama/Aesir/Demo are fully local roads),
  INV-031 (this slice's evidence is the launch proof on real
  machines, not optimism).
- **Failure behaviour:** an unreachable backend is *data*, worded
  plainly ("Not reachable — …"), never a crash or a raw JSON dump;
  the user may go back and fix the connection, pick another mind,
  or continue anyway. A failed chat-profile pin never strands the
  user at the last step (the chat already exists and is greeted).
- **Compatibility:** additive only. R-04's window keeps every real
  behaviour; the First-Run action's status text now ends with
  "Opening the setup wizard." and the banner points at the wizard.

## The four steps (plan §2.3)

1. **Connect a mind.** Five choices, each titled and blurred in
   plain words (`wizard_logic.BACKEND_OPTIONS`):
   - **Ollama — on this computer.** Detection runs *through the
     R-02 roads*: the wizard creates a draft Ollama profile (or
     reuses an existing Ollama profile, updating its `base_url`),
     reads its health, and — when reachable — lists its models into
     a picker. Unreachable is a plain sentence with the next action
     named. If the user detects Ollama and then finishes with a
     different mind, the speculative draft profile is deleted —
     detection leaves no litter. Connecting writes the picked model
     back into that same profile (no duplicates).
   - **OpenRouter — online, many models.** API-key field
     (password-masked) → R-02 secret store via the write-only route;
     a model name is required. The key is never displayed back —
     the profile shape carries only `has_chat_secret`.
   - **OpenAI-compatible — your own server address.** Base URL +
     optional key + model.
   - **Aesir — Rúnmál's own local engine.** No key, no address;
     step 2 says honestly whether it answered.
   - **Demo mode — not a real model.** The `fake` backend, labelled
     as a canned responder in the radio title, the blurb, and the
     connected confirmation — never disguised as a model.
   Profile creation goes through new client methods
   (`create_backend_profile`, `update_backend_profile`,
   `delete_backend_profile`, `set_chat_secret`); secrets are never
   sent inline at creation, only via the dedicated route.
2. **Prove it.** On entry the page runs the profile's R-02 health
   probe, then its model list when healthy (a failing model list is
   worded, not fatal). `wizard_logic.health_words` renders the
   verdict: *Reachable — … answered in N milliseconds. It reports
   M model(s): …* or *Not reachable — …: reason. You can go back…*.
   Adapter detail strings are taxonomy text (INV-001); a detail
   that ever arrived as raw JSON is replaced by a plain sentence
   (`plain_reason`) — the user never sees braces.
3. **Meet someone.** Two roads: create-from-lines (name required;
   description, personality, first greeting as the character
   create road accepts them) or import a card file (JSON/PNG)
   through `POST /api/v1/library/imports` (new client method
   `import_character_file`, whose `ImportOutcome` collapses the
   bulk report to the landed character — created, repaired-in, or
   an exact duplicate — or a plain refusal reason). The step then
   opens the first chat (`create_chat` with `character_id`; the
   engine seeds the greeting), pins the step-1 profile to it
   (`set_chat_backend_profile`, best-effort), reads the greeting
   back (`list_chat_messages`), and shows it as a preview.
4. **Your name.** The persisted `{{user}}` name via the R-03 roads
   (`get_user_name` / `set_user_name` client methods), prefilled
   with the current effective name (default "User"). An empty field
   never clears the setting from the wizard — finishing keeps the
   current/default name.

**Finish** lands in the main window: `MainWindow` records the
setup result, titles the Chat Stage "Chat with <name>", shows the
greeting in the stage, refreshes the docks (the chat is listed,
first-run reads configured), and status-bars the completion.

## Architecture notes

- **Widgets → flow → client → HTTP.** `wizard.py` contains no
  engine imports and no decisions that can be tested without Qt;
  `wizard_logic.WizardFlow` holds the whole state machine (draft
  profile bookkeeping, pin-best-effort, greeting read-back) and is
  gated by MockTransport tests plus a live-engine end-to-end.
- **Off the GUI thread.** Every page runs its network step behind
  an explicit action button through `desktop/workers.run_async`
  and only then reports itself complete (`isComplete`), so
  Next/Finish never block on a request. The proof driver and tests
  use the same pages, driven programmatically.
- **Auto-show.** `MainWindow(auto_wizard=True)` — set only by the
  app entry (`desktop/app.py create_window`) — opens the wizard
  once when a refresh finds first-run state. Direct construction
  (tests, proof drivers for other slices) stays manual, exactly as
  R-04's proof expects.

## Verification

- `tests/test_r05_wizard_logic.py` — MockTransport: plain-words
  options + Demo honesty, `plain_reason`/`health_words` wording,
  Demo create+prove, secret write-only (canary reaches only the
  secret route; absent from profile/flow/words), Ollama detect
  reachable/unreachable + profile reuse + draft cleanup, failing
  model list during prove, client profile CRUD, character create
  → greeted chat with pin, import accepted/refused, user-name
  round trip (empty never clears), composed-turn SSE collection.
- `tests/test_r05_wizard_live.py` — the real in-process engine on
  a fresh data dir: the full Demo flow ends first run and the
  greeted chat answers composed (`X-Backend-Key: fake`, canned
  line); a second pass connects an **OpenAI-compatible profile to
  a local echo server** and the composed answer echoes the system
  prompt built from the character + persisted user name (the
  configured-backend path, R-03's road driven through the wizard
  flow); a junk card import is refused plainly.
- `tests/test_r05_desktop_wizard.py` — Qt: wizard structure (four
  pages, Demo label), a full programmatic drive against a mock
  engine (connect → prove → create → name → finish, completion
  signal carrying chat + name), and the window's open/landing
  wiring. Skips cleanly without PySide6.
- **Bug found and fixed in-slice (pre-existing, R-04 test):**
  `test_r04_desktop_window.py::test_apply_snapshot_renders_lists_and_first_run`
  asserts the first-run banner's *effective* visibility inside a
  window its fixture never shows — it fails identically at base
  `e3d4467` on a real Qt host (verified on purpleraider against a
  pristine `git archive` of the base; on the VM it had only ever
  skipped, for want of PySide6). The fixture now shows the window,
  which is what the test always intended to assert; no production
  code changed for it.
- **Launch proof** — `scripts/desktop_r05_proof.py` drives the
  real app (auto-wizard road): wizard appears on first run, Demo
  connected, proof in words, character created, name saved,
  Finish lands the window in the greeted chat, the chat answers
  through the configured backend, clean quit stops the engine.
  Venues: F15 (Windows), purpleraider (Linux x86-64, offscreen +
  real Wayland), Mimir (ARM, bonus). Logs live in the campaign's
  evidence folder, not the repo.
