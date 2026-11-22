# R-13 — Voice & Vision (desktop definition)

Date: 2026-11-22. Slice R-13 of the Interface Redo plan
(Part 3): "Voice & Vision. Voice settings/status/sessions
panels; vision describe/attachments/watch folders; composer
image attach. *Verification:* launch proof — describe an
image from the window; voice panel reports backend/device
state truthfully (no fake 'ready')."

## Ground truth (engine, read from source 2026-11-22)

- **Voice** (`src/runmal/voice/`): `GET /voice/status`
  (session state, turns, the metrics report — turns, series,
  violations — which is absent when no collector is attached),
  `GET /voice/devices` (the provider's device list + role
  assignments + per-role resolution), `PUT
  /voice/devices/roles/{role}` (assign a device to a role; a
  saved device that has gone missing resolves as
  `remap_required` — the engine never silently substitutes
  the OS default), `GET /voice/backends` (TTS/STT registries:
  shipped-by-default vs user-installed, installed yes/no,
  install audit), `POST /voice/backends/{kind}/{key}/install`,
  `GET/PUT /voice/settings/defaults`, and the session routes
  (`GET/POST /voice/sessions`, `GET/DELETE
  /voice/sessions/{id}`, latency and live views). There is no
  microphone in a headless seat and no backend is installed
  on a fresh engine — the panel's job is to say exactly that,
  in words, never to dress absence up as readiness.
- **Vision** (`src/runmal/vision/`): `GET /vision/providers`
  (provider rows + the semantic-caption note), `POST
  /vision/describe` (by bytes, by path, or by attachment),
  `GET /vision/chats/{id}/descriptions`, `GET
  /vision/history`, `DELETE /vision/descriptions/{id}`,
  attachments (`POST /vision/chats/{id}/attachments`, list,
  `GET …/attachments/{id}/thumbnail`, `DELETE
  …/attachments/{id}` — deleting an attachment purges its
  derived descriptions and reports the count), and watch
  folders (`GET/POST /vision/watch-folders`, `PATCH/DELETE
  /vision/watch-folders/{id}`, `POST
  /vision/watch-folders/{id}/scan`, `GET
  /vision/watch-folders/{id}/ingested`). **No semantic
  caption provider exists in-tree**: the only provider is
  `runmal.vision.metadata` (sniffed truth about the bytes —
  format, dimensions, size, sha256), and a request for a
  semantic caption is refused plainly. The window repeats
  the engine's note verbatim instead of implying otherwise.
- **Chats**: the history payload joins attachment views onto
  message dicts (P-120), so a message that carries an image
  says so in the transcript and the message list.

## The slice

- Client: the full voice surface (status, devices + provider
  from the one devices read, roles, role assignment,
  backends parsed to views with raw defaults, install,
  defaults get/put carrying only non-None keys, sessions
  list/start/detail/stop/latency/live) and the full vision
  surface (providers, describe with source-key/provider
  omission rules, chat descriptions, history, description
  delete, attach → outcome view, attachments list, thumbnail
  bytes, attachment delete, watch-folder list/create/
  partial-PATCH/delete, scan always sending a JSON body,
  ingested rows raw). Models `VoiceDeviceView`,
  `VoiceBackendView`, `VoiceSessionView`,
  `VisionProviderView`, `VisionDescriptionView`,
  `VisionAttachmentView`, `VisionAttachOutcome`,
  `WatchFolderView`; `MessageView` gains `attachments`
  parsed from the history payload (absent → empty). No new
  engine routes.
- Qt-free flows: `desktop/voice_logic.py`,
  `desktop/vision_logic.py` — every renderer speaks in
  words: status (state, turns, metrics or "No metrics
  collector is attached to this engine."), device lines,
  role lines carrying the remap warning, backend lines with
  the install audit (binding vs "information only — your
  choice, your terms"), session lines/detail/latency, and
  for vision the provider lines with the semantic note
  verbatim, description/attachment/watch lines, and the
  scan report.

## What was built

Two dialogs and a composer affordance, all over existing
engine routes (census unchanged at 365 paths / 455
operations):

- **Voice** (Tools ▸ Voice…): three tabs. *Status &
  Devices* — the status words, the provider line, the
  device list, and one row per role with a direction-filtered
  device combo and Assign; the remap warning stands as its
  own label whenever a saved device is missing. *Backends &
  Defaults* — TTS and STT lists (kind + key ride the rows),
  the audit/notice detail pane, Install Selected enabled
  only for installable backends and rendering the engine's
  verdict words (a refusal shows as the engine's refusal),
  and the defaults combos with Save Defaults. *Sessions* —
  a chat combo preselecting the window's open chat, the
  session list, Start (with the auto-project switch), Stop
  Selected, and a detail pane joining the session words,
  the latency words, and the live view.
- **Vision** (Tools ▸ Vision…): a chat combo driving four
  tabs. *Describe* — file chooser, question field, provider
  combo ("Engine default" first), the providers pane with
  the semantic note, and the description in words.
  *Attachments* — the chat's attachments, a thumbnail
  preview, Attach File…, Describe Selected, and Delete with
  a custody-naming confirm that reports how many derived
  descriptions were purged. *Descriptions* — the chat's
  descriptions plus history search, detail, delete.
  *Watch Folders* — register (path + recursive), enable/
  disable and recursive toggles, Scan Now with the report
  in words, the ingested list, and Remove reporting how
  many ingested records went with the folder.
- **Composer image attach**: an "Attach Image…" button and
  a "Clear Image" button beside the composer; a staged
  image announces itself ("Image ready: {filename} — it
  will ride with your next message.") and rides the next
  send — `ChatFlow.send_turn` attaches it to the user
  message *after* the message lands and *before* streaming,
  so a failed attach is reported in words and the message
  is never lost (the image stays staged for a retry). A
  landed attachment clears the stage. The transcript marks
  each attachment ("[Image attached: {filename} — {FORMAT},
  {w}×{h}]") and the message list counts them.

**Gates (VM seat, this campaign's swift standard):** slice
logic 10/10 + live 4/4; neighbours (R-12 tools logic+live,
R-07 chat actions logic+live, R-04 desktop client, P-207
census file) inside a 65-test green batch; P-232 gate file
34 passed with only the known pre-existing H1 tree-law
failure; window tests R-13 + R-12 neighbours 16/16 under
real PySide6 offscreen; full-suite collection 6,689 (was
6,675); ruff clean. Launch proof
`scripts/desktop_r13_proof.py`: **38/38 PASS** on the VM
(Linux x86-64, Qt 6.8.0 / PySide6 6.8.0.2, offscreen) — the
voice panel reported "State: LISTENING" with no metrics
collector attached and roles "not assigned" (no fake
ready), backends stated "installed: no", defaults were
saved through the dialog (tts_backend → openai) and
persisted across a restart, a session started and stopped
on the open chat, an image was described from the window
by the metadata provider ("Metadata road only: no semantic
caption was produced"), a watch-folder scan ingested the
picture, and a composer-staged image landed on the sent
user message (verified through the API) and cleared.

**Venue record:** the proof ran on the VM because the
fleet seats were not reachable from the coordinator's
sandbox this session — purplelongship carries no SSH
server (connection closed) and Mimir refused the VM's key
(publickey) — so the purplelongship (Linux x86) and Mimir
(ARM) launch proofs are **deferred**, to be run by the
keeper road on the devices themselves. purpleraider stays
deferred under Volmarr's pause; the F15 (Windows) proof
for R-13 rides with the owed R-09…R-12 Windows proofs at
R-17.
