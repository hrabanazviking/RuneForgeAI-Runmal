# Chat Stage I — R-06 (2026-11-14)

The first real conversation surface of the windowed shell: the
centre stage streams a composed turn, the Chats dock manages
chats, and the Session dock shows the open chat's truth at a
glance. Before R-06 the centre was R-04's placeholder and the
wizard's landing could only print the greeting; every road R-06
uses was banked by R-02/R-03 and is reached through the R-04
client layer. R-06 adds **no engine routes** (route census
unchanged at 365 paths / 455 operations).

## Definition (before implementation, per repo law)

- **Owning subsystem:** `src/runmal/desktop/` — stage widgets in
  `window.py`, all decisions in the Qt-free `chat_logic.py`
  (`ChatFlow`), all HTTP in `client/` (the R-04 boundary,
  unchanged in kind), streaming delivery via `workers.run_stream`.
- **Inputs:** the chats roads (create with greeting seeding,
  get/list, message append/list, rename, delete, export, preset
  pin, backend-profile pin), the R-03 persona road
  (`GET /chats/{id}/persona`), the characters roads, the presets
  list/get roads (names only — the editor is R-09), the R-02
  profile list, and the generation roads (`POST /generate`
  composed streaming + `POST /generate/cancel`).
- **Outputs:** a launchable Chat Stage (history view, composer,
  Send/Stop), a working Chats dock (open/new/rename/delete/
  export + the character picker on New Chat), and a Session dock
  resolved from live API data.
- **Invariants honoured:** INV-003 (Stop propagates through the
  engine's cancel registry by request id), INV-023 (no secret
  ever crosses this slice — the stage reads profiles as
  references + booleans only), INV-025 (chat export is the
  engine's portable S111 document), INV-031 (the slice's evidence
  is the launch proof on real machines, not optimism).
- **Failure behaviour:** an unreachable backend or a stream error
  is *data*, worded plainly in the stage status and the status
  bar; a failed send reloads the authoritative history so the
  window never claims a line was saved that was not.
- **Compatibility:** additive only. R-04's snapshot chrome and
  R-05's wizard keep every behaviour; the wizard's completion now
  lands by *opening* the greeted chat in the real stage (its
  title/greeting landing is preserved verbatim on top).

## The composed turn (landing discipline)

`/generate` never persists (R-03). The stage therefore lands a
turn exactly the way the bridge does
(`bridge.conversation.stream_generation`):

1. The user's line is persisted first (`POST /chats/{id}/messages`),
   so the server-side composition includes it.
2. The composed stream runs (`POST /generate` with `chat_id` and
   a client-chosen `request_id`, registered before the turn starts
   so Stop can name it from the first moment); token events
   accumulate into a `StreamDraft` the window renders live.
3. The reply is persisted **only** after a clean finish (a `done`
   that is not `cancelled`/`error`, with text). A stopped or
   errored stream stores **nothing**: the partial stays visible in
   the window, labelled "stopped, not saved", and never enters the
   stored history. Reasoning events are collected, never rendered
   live and never merged into the answer text.

## Pieces

- **Client layer (Qt-free).** New roads: `get_chat`,
  `rename_chat`, `delete_chat`, `export_chat`, `append_message`,
  `set_chat_preset`, `get_chat_persona`, `get_character`,
  `list_presets`/`get_preset`, `stream_composed` (incremental
  `StreamEvent` generator: `started` carries the `X-Backend-Key` /
  `X-Generation-Mode` headers), `cancel_generate`,
  `new_request_id`. New view-models: `PresetSummary`,
  `PersonaView`, `StreamEvent`. `generate_composed` (R-05) is
  untouched.
- **`chat_logic.ChatFlow`.** `open_chat` (history + Session view),
  `create_chat` (character picker → greeting seeded by the
  engine), `rename_chat` (empty titles refused), `delete_chat`,
  `export_text`, `send_turn` (the discipline above, with an
  `on_event` hook the window's stream worker forwards),
  `cancel_active`. `resolve_session` is a pure function over
  fetched data; `transcript_html` renders escaped history + the
  draft with its state in words.
- **Session view honesty.** Character and persona come from the
  chat row + the R-03 persona road; profile/model from the chat's
  *pinned* profile — an unpinned chat says "No profile pinned —
  the engine default answers" and names that default (the fake
  backend), because that is what generation will actually use; a
  dangling preset/profile id says it no longer exists. Nothing is
  carried by colour alone; every line is words.
- **Window.** Centre stage: header (chat title + counts), the
  greeting-capable first-run banner (unchanged), `QTextBrowser`
  history, a stage status line, and the composer (Enter sends,
  Shift+Enter adds a line) with Send/Stop. Chats dock: list +
  New… (dialog with the character picker) / Rename… (dialog) /
  Delete (two-step confirmation, irreversible wording, S111
  semantics) / Export… (save dialog over the export road).
  Characters dock: double-click (or the button) starts a New Chat
  with that character. Chat menu's Stop Generating and File's New
  Chat are real actions now. All network/stream work runs off the
  GUI thread (`workers.run_async` / `run_stream`); after a turn
  the stage reloads the authoritative history.

## Scope honesty (what R-06 is not)

Per-message actions (edit/delete/swipes/branch/pin), Regenerate /
Continue / Impersonate, the Author's Note editor, chat search,
and checkpoints/undo are **R-07** — the menus and the Chats dock
note label them with that slice and build none of them here.
Preset *editing* and profile management stay R-09; R-06 only
displays the applied names. The full character library/editor is
R-08; R-06's picker reads the roster only.

## Verification

- `tests/test_r06_chat_logic.py` — MockTransport: Qt-freedom of
  the new layer, every new client road, stream events + headers,
  cancel road, Session resolution (pinned / unbound / dangling),
  transcript escaping + draft states, the flow's landing
  discipline (clean → landed; cancelled → not landed; error →
  not landed), dock roads.
- `tests/test_r06_chat_live.py` — the real in-process engine:
  greeted Demo chat, preset applied and named in the Session
  view, composed turn landed in history, rename/export/delete;
  and a **real mid-flight Stop**: a slow OpenAI-compatible echo
  backend (8 chunks × 0.4 s) is cancelled from another thread —
  the result is stopped, the partial is absent from history.
- `tests/test_r06_desktop_window.py` — Qt: stage structure,
  R-07 placeholder honesty, the full dock drive (dialog create →
  greeting rendered → Session values → composer send → reply
  landed → dialog rename → export file → confirmation delete),
  dock-list reopen. Skips cleanly without PySide6.
- **Launch proof** — `scripts/desktop_r06_proof.py` drives the
  real app on a fresh data dir: seeds a Demo profile, a character
  and a preset through the real API, creates a chat through the
  New Chat dialog's picker, sends and watches the composed reply
  stream in, stops a slow-echo stream mid-flight from the Stop
  button (partial not persisted), reopens the chat and verifies
  the persisted history, renames and exports from the dock,
  checks the Session dock's real values, and clean-quits (engine
  stops). Venues: F15 (Windows), purpleraider (Linux x86-64,
  offscreen + real Wayland), Mimir (ARM, bonus). Logs live in the
  campaign's evidence folder, not the repo.
