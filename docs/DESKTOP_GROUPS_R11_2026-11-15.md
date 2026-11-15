# R-11 — Groups (desktop definition)

Date: 2026-11-15. Slice R-11 of the Interface Redo plan (Part 3):
"Group screen, roster/policy editors, persistent rooms.
*Verification:* launch proof — build a two-character group in the
window, run a turn per strategy." Plan §2.2 item 7: "Groups
(screen reusing the Chat Stage). Group list, roster editor
(add/remove members, per-member overrides, leave/return),
strategy + deepening settings, presence, persistent rooms."

## Ground truth (engine, read from source 2026-11-15)

- Persistent rooms (S210): `POST/GET /groups`,
  `GET/PATCH/DELETE /groups/{id}`. A group document carries
  `id`, `name`, `chat_id` (the room's backing chat), `members`,
  `member_count`, `message_count`, `speaker_policy`,
  `speaker_config` (a dict — the deepening document lives
  inside it under `p070`), `created_at`.
- Members: `POST /groups/{id}/members`,
  `DELETE …/members/{cid}`, `PATCH …/members/{cid}` with
  `talkativeness` ∈ [0.0, 1.0] and/or `muted`. Member rows:
  `character_id`, `name`, `position`, `talkativeness`, `muted`.
- Transcript: `POST/GET /groups/{id}/messages` (speaker is
  `"user"` or a member id); message rows carry `speaker_name`.
- Speaker policies (S211): `manual`, `natural`, `list`,
  `pooled` — validated engine-side on PATCH.
- Deepening (P-070): `GET/PUT /groups/{id}/deepening` — the
  document is `generation_mode` (`swap`/`join`), `join_prefix`,
  `join_suffix`, `scenario_override`, `allow_self_responses`,
  `auto_mode {enabled, max_turns}`, `member_overrides`, and
  `state` (engine-managed selection state — carried verbatim,
  never edited by the shell). Per-member override:
  `PATCH …/members/{cid}/override` with `activation`
  (`default`/`force`/`never`), `persona_override`,
  `lore_enabled`. Peek: `GET …/members/{cid}/peek` returns the
  member, its override, the persona source (override vs card)
  and the effective persona text.
- Presence: `POST …/members/{cid}/leave`, `POST …/return`
  (returns the missed digest), `GET …/members/{cid}/digest`,
  `GET /groups/{id}/presence` (one record per member).
- Turns: `POST /groups/{id}/next` (optional `user_text`,
  `manual_speaker_id`, `generate`) returns the strategy, the
  picked speaker and the reason in words; `POST …/run`
  (`turns`, `generate`) runs several. With `generate` on, the
  picked member's reply is generated through the default
  backend and appended to the transcript.

## The slice

- Client: group roads (CRUD, members + settings, messages,
  deepening get/put, override patch, peek, leave/return,
  digest, presence, next, run) and models `GroupView` (raw
  document carried), `GroupMemberView`, `GroupMessageView`.
  No new engine routes.
- `desktop/group_logic.py` (Qt-free): `GroupFlow` over the
  client; policy / generation-mode / activation words;
  deepening compose (form fields over the stored document —
  `state` and unknown keys carried verbatim); turn-result and
  presence words.
- Window: `GroupsDialog` (Chat ▸ Groups…, graduating the R-04
  placeholder) with a group list (create with a roster picked
  from the character library, rename, delete with an honest
  no-undo confirm) and, per group: a **Room** tab (transcript
  in words, say something as the user, Next turn with an
  optional line + manual speaker + generate toggle, Run turns,
  the last turn's pick and reason in words), a **Roster** tab
  (members with talkativeness + mute, add/remove, per-member
  override editor, peek, leave/return with the digest shown,
  presence in words), and a **Room Settings** tab (name,
  speaker strategy, deepening fields).
- Tests: logic (MockTransport), live (real engine: two-member
  group, a turn per strategy — list cycles the roster, manual
  honours the chosen speaker), window (real Qt, offscreen).
- Proof: `scripts/desktop_r11_proof.py` — build a two-character
  group in the window, set each strategy and run a turn,
  generate a reply, restart persistence.

## What was built

- Client roads (`client/core.py`, models `GroupView` —
  raw document carried — `GroupMemberView`,
  `GroupMessageView`): room CRUD, members add/remove/settings,
  transcript list/post, deepening get/put, per-member override
  patch, peek, leave/return, digest, presence, next, run.
  Census unchanged: 365 paths / 455 operations; no new engine
  routes.
- `src/runmal/desktop/group_logic.py` (new, Qt-free):
  `GroupFlow` over the client; strategy / generation-mode /
  activation words; `compose_deepening` laying the settings
  form over the stored document (`state` and unknown keys
  carried verbatim); turn/run result words; presence words
  for the engine's `present`-boolean records (with missed
  counts); digest words over the real digest shape
  (`entries` + `window.missed_count`); peek words.
- `window.py`: `GroupsDialog` (Room / Roster / Room Settings
  tabs) behind Chat ▸ Groups…, house dialog-lifetime pattern.
  The roster rebuild preserves the selected member (found by
  the window gate: a save used to bounce the selection to the
  first member, so a following override save landed on the
  wrong member).
- Tests: `tests/test_r11_group_logic.py` (12),
  `tests/test_r11_group_live.py` (2 — a turn per strategy on
  the real engine: in-order cycles the roster, manual honours
  the pick, generation lands in the transcript; a "never"
  override removes a member from selection; peek persona
  source flips card → override), `tests/test_r11_desktop_window.py`
  (3).
- Proof: `scripts/desktop_r11_proof.py` — 31 checks driving
  the real app: room built in the window from the roster
  checklist, a turn per strategy, roster editors, leave/return,
  rename + deepening save, restart persistence (room, members,
  transcript, strategy, deepening), clean quit.

### Gate evidence (2026-11-15, seat purplelongship)

- Logic 12/12, live 2/2 (venv312 + PYTHONPATH), window 3/3
  (shell venv, PySide6-Essentials 6.8.0.2, offscreen).
- Neighbours: R-02…R-11 logic/live 145 passed (7 skipped) +
  the groupchat engine batteries (P-070, P-208, P-212, P-213,
  P-216, P-217, S210 ×2, S211 policies) 165 passed = **310
  passed**; window neighbours (R-08…R-11) 12 passed; the
  P-232 file shows only the known pre-existing H1 footprint
  failure. Full suite collects **6,665** (R-10: 6,651; +14
  Qt-free tests). Ruff clean on the whole desktop package and
  all new files. README.md untouched.
- Launch proof 31/31 PASS: purplelongship (Linux x86-64,
  offscreen) and Mimir (Linux ARM aarch64, offscreen).
  Evidence: goal `hidden_files/r11-evidence/`.
- **Deferred venues:** purpleraider (offscreen + workshop
  Wayland) — deferred under Volmarr's purpleraider pause.
  F15 Windows (offscreen) — deferred: the machine was
  unreachable on 2026-11-15 (powered off or asleep); the
  R-09 + R-10 + R-11 proofs are owed on the F15 when it
  wakes, and in any case at R-17.
- Transport: authored on the VM clone, carried to the seat
  over a git transfer branch (`yrsa/r11-transfer`, deleted at
  banking); main moved only at banking, from the seat, after
  gates.
