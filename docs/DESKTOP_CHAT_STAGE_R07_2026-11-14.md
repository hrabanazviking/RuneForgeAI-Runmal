# Desktop Chat Stage II — R-07 (2026-11-14)

Slice R-07 of the interface-redo plan (`RUNMAL_INTERFACE_REDO_PLAN_2026-11-14.md`
§2.3 screen 1, Part 3): the Chat Stage gains its full action
surface — per-message actions, regenerate / continue /
impersonate, the Author's Note editor, chat search, and
checkpoints/undo surfacing — over the engine's EXISTING chats
roads. **No new engine routes** (route census unchanged at
365 paths / 455 operations).

## What was built

Same architecture as R-04…R-06: decisions in the Qt-free logic
layer, typed roads in the client layer, widgets in `window.py`,
no engine imports in widgets, no network on the GUI thread.

- **Client layer** (`desktop/client/core.py`, Qt-free): message
  edit/delete; swipe add/select/delete; pin/unpin +
  pinned-messages list; branch fork + family read; Author's Note
  get/set; continue; impersonate draft/accept/discard; chat
  search; checkpoints list/create/restore/delete; undo journal
  list + undo-last. New view models in `client/models.py`:
  `MessageView` gains the swipe deck (`swipes`, `swipe_id`) and
  `pinned`; new `AuthorsNoteView`, `CheckpointView`,
  `UndoEntryView`, `SearchHitView`.
- **Logic layer** (`desktop/chat_logic.py`): `ChatFlow` gains
  the action surface with the validation and honesty words the
  window renders (`ContinueOutcome`, `ImpersonateDraft`,
  `RegenResult`, `SearchOutcome`); pin state is always verified
  by re-reading the pinned list, never assumed; the transcript
  and the message-list rows carry pin + swipe position as words
  ("pinned", "swipe 2 of 3"), never colour alone.
- **Window** (`desktop/window.py`): a message list under the
  transcript picks the message an action lands on; the action
  bar offers Edit…, Delete (confirmed, journaling named),
  Swipe ◀ ▶, Swipes… (list/select/delete dialog), Branch…,
  Pin/Unpin, Copy (clipboard). The chat row offers Regenerate,
  Continue, Impersonate… (draft dialog: edit, accept as a real
  user message, or discard storing nothing), Author's Note…
  (text/depth/frequency/role/enabled editor), Search Chats…
  (results open their chat), and Checkpoints & Undo… (create /
  restore-as-new-chat / delete checkpoints; undo journal with
  Undo Last). Chat/Edit menu placeholders for these are now the
  real actions. Dialogs fetch and act OFF the GUI thread
  (worker + callback, the R-06 pattern).

## Regenerate — composed from existing roads, losslessly

There is no engine regenerate route for chats, and R-07 adds
none. `ChatFlow.regenerate` composes the roads that exist with
the R-06 landing discipline:

1. The last message must be the assistant's reply. It is
   deleted first — the delete is journaled (P-076), and the
   R-03 composed prompt then ends at the user line the reply
   answers, exactly the prompt the original reply saw.
2. A fresh composed turn streams (no new user line is added).
3. On a clean finish the new reply lands as a fresh assistant
   message. On ANY other ending (stopped, errored, empty) the
   old reply is restored — via the undo journal first (exact
   before-image, original id), falling back to re-appending its
   text — and the result words say the previous reply was
   restored unchanged.

## Verification

- VM venv (clean `no_proxy`): R-07 logic tests (MockTransport)
  + live tests (real in-process engine: every action above,
  state verified via the API) pass; neighbour batches R-02+R-03,
  R-04 client+engine, R-05, R-06, S806+S807, P-207 census green
  (the known pre-existing P-232 H1 footprint failure excepted —
  it fails identically at base and is recorded, not healed).
- Real-Qt window tests on purpleraider offscreen.
- Launch proof `scripts/desktop_r07_proof.py` — every R-07
  action driven once in the real window, state verified via the
  API afterwards — on F15 Windows (offscreen), purpleraider
  (offscreen + real Wayland display), and Mimir ARM (offscreen).
  Evidence in the campaign's `hidden_files/r07-evidence/`.

## Findings fixed in-slice

- **P-065 swipe semantics (proof-caught):** adding a swipe
  alternate makes the NEW alternate active (`chats/service.py`
  `add_swipe`: "The new alternate becomes the active one"). The
  first proof draft and both test mocks assumed the active swipe
  was unchanged; the real engine (live test + F15/purpleraider
  proof) showed `swipe_id` advancing to the new alternate. The
  mocks and the proof now encode the real semantics, and the
  live test asserts them explicitly. No engine change — the
  shell's assumption was the bug.
- **Proof seeding bug (proof-caught, proof-side only):** the
  first proof run created its character after the window's
  roster cache was filled and never refreshed, so the New Chat
  dialog's picker had no character to pick and the chat was
  created unbound (no greeting). The proof now refreshes after
  seeding, like R-06's proof did. No product code changed.

## Superseded test

`tests/test_r06_desktop_window.py` asserted Regenerate/Continue
were still R-07 placeholders; R-07 makes them real, so that
assertion now asserts the landed actions instead (same pattern
as the R-05 fix of the R-04 window test).
