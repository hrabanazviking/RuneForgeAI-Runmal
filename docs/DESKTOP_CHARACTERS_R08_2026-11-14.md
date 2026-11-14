# Desktop Characters (R-08) — 2026-11-14

Slice R-08 of the interface redo: the Characters library and the
full card editor in the native windowed shell, over the engine's
existing characters / library / assets roads. **No new engine
routes** — the route census is unchanged (365 paths / 455
operations).

## What ships

- **Library (Characters dock tab).** Search text, a tag filter
  fed by the library tag census (`GET /library/tags`), a
  favourites-only filter, and sort, all over `GET /library/cards`
  (P-024). Rows render name + favourite as a word (★ favourite) +
  tags + avatar presence — never colour alone. Roster-changing
  actions drop a filtered view back to the full roster rather
  than rendering a stale page as if it were current.
- **Full card editor dialog** (`CharacterEditorDialog`, five
  tabs). Card: name, description, personality, scenario,
  system_prompt, mes_example, post_history_instructions,
  first_mes, creator_notes, creator, character_version, nickname,
  tags. Greetings: the alternate-greetings list editor (add /
  update / remove, full text kept per item) and the group-only
  greeting count, labelled as preserved (group chats are R-11).
  Avatar & Assets: avatar preview from the real bytes, avatar
  upload, the asset list, asset upload. Book & Binding: the
  travelling character-book's entry count, the lorebook binding
  (picker over `GET /lorebooks`, precedence, bind / unbind) —
  lorebook *entry* editing is the R-10 screen and is labelled as
  such in the tab. Versions: the P-025 history with restore.
- **Create-from-scratch** is the same dialog, empty: Save creates
  the character (flat card dict through the existing create
  road), then its tags through the organisation road.
- **Duplicate** (engine copy road), **delete-with-undo** (the
  engine's soft delete, S303 — the confirmation box says in
  words that the card and files are kept and Undo Delete
  restores it), **export** (the stored card serialised to a JSON
  file), **bulk import** (`POST /library/imports`, refusals and
  duplicates reported as data with reasons).

## Roads composed, honestly (no route added)

- **Full card read.** `GET /characters/{id}` returns only the
  summary row; the whole stored card rides the version road
  (`GET /characters/{id}/versions/{n}` → `card`). The client
  joins the two (`RunmalClient.get_character_card`).
- **Card save.** Editor fields are overlaid onto the *stored*
  card dict at whichever level the stored shape keeps them
  (`data` for wrapped cards, top level for flat ones — the real
  engine stores API-created cards flat, importer-created ones
  wrapped; the live test caught this and both shapes are now
  covered), so unknown-but-valid fields and extensions survive
  (INV-009), then PATCHed. Tags are saved through the library
  organisation road afterwards, only when changed — it is the
  road that keeps tag rows and the card's own tag list in step.
- **Version restore.** No restore-version route exists; a
  restore PATCHes the version's stored card back as the current
  card (the R-07 Regenerate composition pattern). The character
  keeps its id, avatar, assets, tags and binding.
- **Export.** No character-export route exists; export is the
  stored card dict serialised — exactly the bytes a re-import
  reads (INV-025).

## Boundaries kept

Widgets hold no decisions: the Qt-free
`desktop/character_logic.py` (`CharacterFlow`, `EditorBundle`,
`apply_card_edits`, `parse_tags`, `BulkImportOutcome`) drives
everything through the typed client layer (new R-08 roads in
`client/core.py`, new views in `client/models.py`, incl. the
binary avatar/asset roads); all network work runs off the GUI
thread via `desktop/workers.py`.

## Findings

- **Stored-card shape is not uniform** (found by the R-08 live
  test): API-created cards store flat (fields at top level),
  wrapped imports store under `data`. The shell's card parsing
  and edit overlay are level-tolerant by construction
  (`card_data_of`); a test assertion that assumed the wrapped
  shape was corrected — no engine change, the engine's shapes
  are both deliberate.
- The dock's filtered library view could go stale after a
  roster-changing action (the refresh re-rendered the old
  filtered page). Fixed in-slice: every roster-changing road
  resets the library view to the full roster first.
- **The proof's 1×1 PNG constant was not a decodable image**
  (found by the first device proof run): its IDAT inflates to
  2 bytes — too short for one RGBA scanline (5) — so `QPixmap`
  rightly refused it and the editor's preview label reported
  "cannot be previewed here" (the label logic was correct; the
  fixture was not). Replaced with a verified 1×1 PNG (IDAT
  inflates to exactly filter+RGBA) in the proof and the live
  test.
- **Second-window `show()` segfaults intermittently under the
  live KWin Wayland session** (found by the first real-display
  proof run; R-08's proof is the first in the campaign to open
  a second top-level window in one process, for the restart
  check). Native backtrace places the crash inside Qt 6.8.0's
  own Wayland client (`QWaylandWindow::shellSurface()` →
  `QWaylandXdgSurface::requestActivate()` during
  `QWindowPrivate::setVisible`) — a null shell surface race in
  the pinned toolkit under KWin, not shell code: the identical
  proof passes deterministically offscreen and on the headless
  Weston workshop display (the standing real-Wayland venue
  since Volmarr's 2026-11-14 order), and a minimal two-window
  Qt repro + the app's own engine lifecycle bisect both pass
  under KWin intermittently. Verdict: upstream toolkit/
  compositor race; no shell change made. The two-windows-in-
  one-process pattern is a proof artifact — a real restart is
  a fresh process.
- **Proof/test sequencing race on the async delete** (found by
  a device proof run): the delete lands in the engine before
  the window's async done-callback arms Undo, so a caller that
  blocks on the roster alone can call Undo with no id stored
  (restore of `""` → 404). The window is correct — Undo arms
  only when the delete is confirmed — the proof and the window
  test now wait for the armed button state, as a user would
  see it, before invoking Undo.

## Verification

- R-08 logic tests (mock engine): full-card join, lossless
  overlay (wrapped + flat), create, save + tag sync, library
  search/tags/favourites, bundle (binding/assets/avatar),
  versions + composed restore, duplicate/delete/undo,
  export/import.
- R-08 live tests (real in-process engine): the same surface end
  to end, incl. avatar/asset byte round trips, the embedded
  character book materialising as a binding, a world-lorebook
  bind/unbind, and v2 lineage restore.
- R-08 window tests (real QMainWindow, mock engine): structure
  honesty (no R-08 placeholders left), create/edit through the
  dialog, library controls, duplicate + delete-box + undo, and
  chatting with an editor-made character.
- Launch proof `scripts/desktop_r08_proof.py`: create in the
  dialog → chat → edit → avatar/asset → bind/unbind → versions /
  restore → duplicate → delete-box → undo → export → import →
  **restart the app on the same data dir and confirm the
  character, its edited card, tags, avatar and the chat history
  persist** → clean quit. Run on F15 (Windows, offscreen),
  purpleraider (Linux x86-64, offscreen + real Wayland), and
  Mimir (ARM aarch64, offscreen, bonus venue); evidence in the
  goal's `hidden_files/r08-evidence/`.
