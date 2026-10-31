# P-004 — The Delta Table (2026-10-30)

*Mirror feature × Rúnmál state. Every SillyTavern row (ST-01–ST-74,
from P-002) and every Voxta row (VX-01–VX-67, from P-003) judged
against the founding audit (P-001): **HAVE** / **HAVE-THIN** /
**MISSING** / **DELIBERATELY-DIFFERENT** (with the sovereign
reason). This table is the evidence the rest of the Two Mirrors
road is re-cut from at the Part I gate (P-014).*

## Method and evidence rules

- A HAVE or HAVE-THIN claim cites a P-001 row (founding slice
  `S###` or the extra UI campaign, marked `UIx`). Anything not in
  the P-001 inventory is MISSING or THIN until proven otherwise —
  that was P-001's own handover rule, and it is kept here.
- **HAVE** = the P-001 inventory proves essentially the whole row
  as observable behaviour. **HAVE-THIN** = the core is proven, and
  the row's named sub-depth is not — the missing depth is named in
  the row, never hidden inside the verdict. **MISSING** = the core
  behaviour is absent from the inventory (a named substrate, where
  one exists, is noted as substrate, not as the feature).
  **DELIBERATELY-DIFFERENT** = Rúnmál's sovereign shape replaces
  the mirror's shape by design (roadmap §2), and that replacement
  — not the mirror's form — is the shipped answer for the row.
- The "Road home" column names where the delta is addressed:
  a defined slice in Parts I–VI of the filed roadmap, a Part
  VII–XIV *title only* (those parts' slice definitions are not in
  the filed roadmap file — see the discrepancy recorded in
  `CAMPAIGN_STATE.md`), or **NO HOME — flagged for P-014**, meaning
  no defined slice in Parts I–VI addresses it and the Part I gate
  must assign it or explicitly drop it. Flagging is this slice's
  job; assigning is the gate's.
- Counts in the summary below are counted from the tables in this
  file (mechanically, after writing), never estimated.
- Clean-room law held throughout: this table compares behaviours
  attested by P-002/P-003 (public docs and release notes only)
  against P-001 (this repo's own tree). No mirror source was read.

## Summary (counted from the tables below)

Counted mechanically from the two tables in this file (every
ST row ST-01–ST-74 and every VX row VX-01–VX-67 present exactly
once — 141 mirror rows in total):

| Mirror | HAVE | HAVE-THIN | MISSING | DELIBERATELY-DIFFERENT | Rows |
|---|---|---|---|---|---|
| SillyTavern (Table A) | 11 | 45 | 18 | 0 | 74 |
| Voxta (Table B) | 3 | 24 | 37 | 3 | 67 |
| **Combined** | **14** | **69** | **55** | **3** | **141** |

The shape in one line: SillyTavern parity is a depth problem
(HAVE + HAVE-THIN = 56 of 74 rows; the cores exist, the deltas
are named sub-depths), Voxta parity is a territory problem
(37 of 67 rows MISSING, concentrated in scenarios, stage,
workspaces, and generation), and only 3 rows in either mirror
are closed by sovereign difference rather than by building.

## Re-cut assessment (roadmap §3 shape vs this table)

1. **Parts II–VI (P-015–P-100, defined) cover the SillyTavern
   deltas well.** Cards/interop (II), lorebook depth (III), prompt
   and sampler depth (IV), chat surgery (V), and the plugin row
   (VI) each correspond to real concentrations of THIN/MISSING
   rows below. No part in II–VI is made unnecessary by the table,
   and none needs re-cutting in shape — only additions (point 3).
2. **The Voxta deltas concentrate exactly where P-003 predicted:**
   scriptable scenarios (VX-28–VX-44), stage/HUD play
   (VX-45–VX-47), faces and generation (VX-48–VX-53), workspaces
   (VX-54–VX-58), and the Hub (VX-59). Those territories are
   Parts VII–XIV, which exist in the filed roadmap as titles and
   slice ranges only. Their slice lists therefore **cannot be
   re-validated by this table**; P-014 can re-validate Parts
   I–VI and must record VII–XIV as awaiting definitions, not as
   validated. This is the same discrepancy already recorded in
   `CAMPAIGN_STATE.md`; the delta table confirms it matters —
   the majority of MISSING rows live there.
3. **Rows with no home in the defined parts** (marked NO HOME
   in the tables): ST-26 (per-entry gating extras), ST-30
   (reasoning controls — nearest kin P-052), ST-40
   (token-probability viewer), ST-69 (user theme editing —
   the defined parts contain no UI-customisation slice),
   ST-70 (localised UI), ST-71 / VX-64 (multi-user accounts —
   the same delta seen by both mirrors), ST-73 (clean-up tool —
   nearest kin S804 `runmal doctor`), VX-11 (mishearing
   handling), and VX-18 (reasoning budget — kin ST-30). Four
   further rows are flagged as having only a kin home, not a
   dedicated slice: ST-27 (automation IDs — kin P-081/P-093),
   ST-44 (AI Horde — a wanted/unwanted judgement for P-008,
   not yet a slice), ST-50 (message inclusion toggle — kin
   P-068), and VX-19 (VRAM awareness — kin P-009's Aesir
   ledger). P-014 must assign or explicitly drop each; none is
   silently dropped here.
4. **Priority note for P-013:** the table supports the roadmap's
   own stated instinct (voice + scenarios early, hub late) —
   voice rows are mostly HAVE/HAVE-THIN (the founding road was
   voice-strong), scenario rows are almost uniformly MISSING,
   and the Hub row is DELIBERATELY-DIFFERENT, so its sovereign
   replacement (signed local packs, Part XII) is design work,
   not catch-up work, and can safely sit late.

## Table A — SillyTavern rows (P-002) × Rúnmál

| # | Feature (short) | State | P-001 evidence / missing depth | Road home |
|---|---|---|---|---|
| ST-01 | Character cards as organising unit | HAVE | S104 card model, S106 character service, S110 prompt assembly | — (depth in Part II) |
| ST-02 | Card import (file + URL), v2/v3 | HAVE-THIN | File import proven (S104, incl. v3/CHARX S113); External Import from a URL is not in the inventory | P-015, P-016 |
| ST-03 | Library-scale search/sort/tags-as-folders | HAVE-THIN | CRUD (S106) + gallery/editor shell (UI S303x); sort by usage/size, favourites, tag folders/manager not proven | P-024 |
| ST-04 | Card editing depth (stats, favourite, duplicate, gallery) | HAVE-THIN | Export (S105), CRUD (S106), token counts (S214/UI S214x); per-card usage stats, favourite toggle, duplicate not proven | P-023, P-024, P-025 |
| ST-05 | Extended card ops (link lore, scenario override, convert, rename-relink, source link, replace) | HAVE-THIN | Lorebook model/editor (S201/S209), scenario/greeting UI (UI S212x); convert character↔persona, source link, replace/update, rename-relink not proven | Part II (P-015–P-019, P-025, P-029) |
| ST-06 | Advanced definitions (prompt overrides, creator metadata, char note depth/role, talkativeness) | HAVE-THIN | Prompt assembly incl. creator-field handling (S110), Author's Note depth (S206), talkativeness (S211); per-card post-history override and character's-note depth/role not proven as card citizens | Part IV (P-049, P-057) |
| ST-07 | Alternate greetings | HAVE-THIN | Greeting UI exists (UI S212x); greetings as first-message swipes is later work | P-079 |
| ST-08 | Personas (switch mid-chat, batch re-attribution) | HAVE-THIN | Persona assembly (S110), persona UI (UI S212x), bridge persona switching (S603); batch "sync" re-attribution of past messages not proven | P-018 |
| ST-09 | Persona description positions (story string / AN depth & role / disabled) | MISSING | No persona position/depth setting in the inventory; P-018 names exactly this as the gain | P-018 |
| ST-10 | Persona locking/default/temp override/per-character picker, persona backup | HAVE-THIN | General archive/backup covers user data (S801/S802); locking to chat/character, session override, per-character picker not proven | P-018 |
| ST-11 | Group chats (members, mute, re-order, force-trigger) | HAVE | Group rooms/members/per-message speaker (S210), speaker policies incl. manual trigger and mute/talkativeness (S211) | — (depth in P-070) |
| ST-12 | Group reply-order strategies (Manual/Natural/List/Pooled) | HAVE | All four strategies named and seeded-tested (S211) | — |
| ST-13 | Group generation handling (swap vs join cards, join templates) | HAVE-THIN | Groups + composer exist (S210/S205); swap-vs-join card assembly modes and join prefix/suffix templates not proven | P-070 |
| ST-14 | Group extras (auto-mode, self-response, group scenario override, peek/edit member) | HAVE-THIN | Director seam (S212) is substrate; auto-mode delay loop, branched override inheritance, in-group card peek/edit not proven | P-070 |
| ST-15 | Keyword-triggered lore entries (regex keys, scan buffer) | HAVE-THIN | Keyword scanning with whole-word/case toggles (S202); regex keys and name-prefixed per-message scan buffer not proven | Part III (P-031 kin) |
| ST-16 | Selective logic AND ANY/ALL, NOT ANY/ALL | HAVE-THIN | Primary/secondary keys + selective activation (S202/S203); the full four-mode truth table is later work | P-032 |
| ST-17 | Entry strategies: constant / keyword / vectorised | HAVE-THIN | Constant + selective proven (S203), vector stack exists (S401–S403); vectorised as a lore entry strategy under all other checks not proven | P-035, P-041 |
| ST-18 | Insertion positions incl. Outlet macro | HAVE-THIN | Typed ordered slots/positions (S205), depth injection (S206); example-block positions and the Outlet pull-model not proven | P-038 |
| ST-19 | Probability (Trigger %) | HAVE | Seeded probability in budget/priority engine (S204), activation semantics (S203) | — (honesty deepened at P-036) |
| ST-20 | Inclusion groups (weight, priority, group scoring) | HAVE-THIN | Priority + deterministic tie-break (S204); mutually-exclusive groups, weight choice, and group scoring not proven | P-034 |
| ST-21 | Timed effects: sticky / cooldown / delay | HAVE | All three named in activation semantics, chat-scoped (S203) | — |
| ST-22 | Recursive scanning with per-entry controls | HAVE-THIN | Recursion + cycle detection + hard depth (S203); per-entry non-recursable / prevent-further / delay-until-recursion levels not proven | P-031 |
| ST-23 | Scan configuration (depth, Min Activations, names in buffer) | HAVE-THIN | Scan depth proven (S202); Min Activations deepening and participant-name buffer not proven | P-037 |
| ST-24 | Lore token budget (context-% or absolute, insertion order) | HAVE | Token budget + priority + deterministic order (S204), prompt budget ledger (S214) | — |
| ST-25 | Four lore scopes layered (global/character/persona/chat) | HAVE-THIN | Books + character binding substrate (S201, S104); persona lore, chat lore, and combined insertion strategies not proven as scopes | P-039, P-040 |
| ST-26 | Per-entry gating extras (character filter, generation-type triggers, extra scan sources) | MISSING | None of the three appears in the inventory | NO HOME — flagged for P-014 |
| ST-27 | Automation ID (entry firing runs a command) | MISSING | No automation-hook equivalent in the inventory; nearest future kin is the plugin/variables store | Part VI kin (P-081, P-093); no dedicated slice — flagged for P-014 |
| ST-28 | Prompt Manager (ordered editable blocks, roles, depth, gen triggers) | HAVE-THIN | Typed ordered prompt slots with roles/positions/budgets (S205) + inspector UI (S215); drag-and-drop manager, per-block generation triggers, preset-carried prompt sets not proven | P-049 |
| ST-29 | Prompt Manager utility surface (nudges, markers, squash, system merge…) | HAVE-THIN | Composer + presets substrate (S205/S207); most named utilities (group/continue nudges, markers, squash-system, quote-wrap, prefill) not proven individually | P-049 |
| ST-30 | Reasoning controls (visibility toggle, reasoning effort) | MISSING | Capability negotiation is generic (S310); no reasoning-specific control in the inventory | NO HOME — flagged for P-014 (nearest kin P-052) |
| ST-31 | Advanced Formatting (system/context/instruct templates, auto-derivation) | HAVE-THIN | Presets carry a prompt-template reference (S207), composer templates (S205); separately saveable template files and derivation from a backend template hash not proven | P-050, P-051 |
| ST-32 | Context template / story string (Handlebars anchors) | HAVE-THIN | Structured slot assembly (S205) is the same job in Rúnmál's own shape; the anchor/template file format and extension anchors not proven | P-051 |
| ST-33 | Instruct templates (ChatML/Llama-3/Alpaca class, per model) | HAVE-THIN | Template reference on presets (S207); named public shapes as selectable per-model data not proven | P-050 |
| ST-34 | Presets (shareable JSON bundles per API type) | HAVE-THIN | Named presets exist (S207); ST-shaped preset import/share is later work | P-021, P-054 |
| ST-35 | Sampler surface (temp, top-p/k, min-p, penalties, DRY/XTC class) | HAVE-THIN | Canonical parameter bag + capability filtering (S207/S208); completeness of the DRY/XTC class per backend not proven | P-052, P-053 |
| ST-36 | Macros ({{char}}/{{user}}/{{original}}/{{outlet::…}} + wider set) | HAVE-THIN | Core three proven (S110) + macro/variable helper UI (UI S307x); outlet and the wider documented set not proven | P-055 |
| ST-37 | Author's Note (per-chat, depth/frequency) | HAVE | Depth injection N messages from end (S206) | — (frequency deepened at P-056) |
| ST-38 | Post-history instructions (manager citizen, per-card override) | HAVE-THIN | Prompt assembly + depth tools UI substrate (S110, UI S213x); post-history as a first-class editable manager block not proven | P-057 |
| ST-39 | Multimodal & tool toggles (inline image/video, web search tool, function calling) | HAVE-THIN | Capability negotiation (S310) is the truth substrate; the prompt-level toggles themselves not proven | Part IV kin; vision in Part VIII (title only) — flagged for P-014 |
| ST-40 | Token probabilities viewer (alternatives, reroll from a token) | MISSING | Token counting/ledger exist (S214/S305) but no per-token probability surface in the inventory | NO HOME — flagged for P-014 |
| ST-41 | Two API paradigms (Chat Completion vs Text Completion) | HAVE-THIN | Chat-completion shape proven (S302/S303); a separate text-completion paradigm with its own presets/templates not proven as a citizen | P-008 (ledger judgement) |
| ST-42 | Chat Completion source breadth (OpenAI/Claude/Google/Mistral/DeepSeek/…) | HAVE-THIN | OpenRouter (S303) routes many of these and Custom-compatible is the adapter shape (S301); direct per-source adapters beyond Ollama/OpenRouter/Aesir not proven | P-008 |
| ST-43 | Text Completion backend breadth (llama.cpp/KoboldCpp/Tabby/NovelAI/Horde…) | HAVE-THIN | Ollama proven (S302); the other named engines are not in the inventory | P-008 |
| ST-44 | AI Horde out of the box (zero-setup free pool) | MISSING | Not in the inventory; whether Rúnmál wants it is a judgement, not yet made | P-008 (wanted/unwanted judgement) — no build slice, flagged for P-014 |
| ST-45 | Per-source secrets (server-side, never in chat data) | HAVE | Backend profiles + server-side secret references (S306), local auth boundary (S102) | — |
| ST-46 | Swipes (alternates kept on a message, navigated in place) | HAVE-THIN | Chat/generation/UI substrate (S107/S108/S109); unlimited alternates and navigation everywhere (incl. voice turns) is later work | P-065 |
| ST-47 | Message editing with movement (edit/copy/delete/move) | HAVE-THIN | Append/edit/delete with stable IDs proven (S107); move up/down and copy actions not proven | P-068 |
| ST-48 | Branches (fork at any message, linked child chat) | MISSING | No branch concept in the inventory | P-066 |
| ST-49 | Checkpoints (named snapshots, one-click return) | MISSING | Archive/backup machinery (S801/S802) is substrate only; named chat checkpoints not proven | P-067 |
| ST-50 | Message inclusion toggle (exclude from model's view, keep in chat) | MISSING | No exclusion flag in the inventory | P-068 kin; no dedicated slice — flagged for P-014 |
| ST-51 | Continue (extend last message, nudge/prefill) | HAVE-THIN | Generation seam (S307) + impersonation/depth tools UI (UI S213x) are substrate; continue as a named operation with nudge/postfix not proven | P-069 |
| ST-52 | Impersonate (model drafts the user's message) | HAVE | Impersonation controls landed in the extra UI campaign (UI S209x/S213x) | — (paired depth at P-069) |
| ST-53 | Regenerate (discard + re-roll as its own generation type) | HAVE-THIN | Streaming generation with cancellation (S108/S307); regenerate as a distinct generation type that lore/triggers key on not proven | Part V kin (P-065/P-069) |
| ST-54 | Chat file management (import/export/rename, chat→group conversion) | HAVE-THIN | List/rename/delete/export proven (S111); JSONL import shapes and in-place chat→group conversion not proven | P-020, P-078 |
| ST-55 | Welcome screen + Assistant (recent chats, quick uncarded chat, default Assistant) | HAVE-THIN | Chat UI + chat list (S109/S111); welcome surface, temporary uncarded chat, and a default Assistant character not proven | Part XIII (title only) — flagged for P-014 |
| ST-56 | Per-message utility actions (translate/image/narrate/prompt view) | HAVE-THIN | Prompt view exists via inspector (S215), narration via the voice stack (S504); per-message translate/image actions await the plugin row | Part VI (P-086, P-087 kin) |
| ST-57 | Extension system (UI extensions + server plugins, distribution channel) | MISSING | No plugin API or sandbox in the inventory | P-081, P-082, P-083 |
| ST-58 | Summarize extension (editable rolling summary, {{summary}} injection) | HAVE-THIN | Rolling auto-summarization engine proven (S404); summary as a user-editable chat citizen injected by template not proven | P-084 |
| ST-59 | Vector Storage / RAG extension (history, Data Bank, lore) | HAVE | Vector store + ingestion + hybrid retrieval proven (S401–S403); lore-side depth cross-ref ST-17 | — (plugin shape at P-085) |
| ST-60 | Data Bank (per-chat/global attached documents + scrapers) | MISSING | Memory ingestion (S402) serves the memory pipeline, not a per-chat document bank; scrapers absent | P-074 |
| ST-61 | Image generation extension | MISSING | No image generation in the inventory | P-087 |
| ST-62 | TTS extension (pluggable narration, per-message) | HAVE-THIN | TTS is a founding citizen, not an extension (S504, S512); per-message narration action and plugin shape are later work | P-091 |
| ST-63 | Speech recognition (voice input to chat) | HAVE-THIN | STT service proven (S503) inside the voice loop; chat-bar voice input as a surface not proven | P-091 |
| ST-64 | Chat translation extension | MISSING | No translation in the inventory | P-086 |
| ST-65 | Expressions / sprites + Visual Novel mode | MISSING | No sprite/expression surface in the inventory | P-092 (surface); Part X (title only) |
| ST-66 | Web search (extension + backend tool, opt-in) | MISSING | No web search in the inventory; off-by-default is the required shape when built | P-088 |
| ST-67 | Regex scripts (named, staged, per-character/global, test mode) | MISSING | No regex-script system in the inventory | P-090 |
| ST-68 | Quick Replies + STscript + slash commands | HAVE-THIN | Command palette + macro helper exist (UI S308x/S307x); user-defined Quick Replies are later work (P-089). The STscript *language* is not adopted: Rúnmál's sovereign equivalent is its own plugin/variables API (P-081/P-093), not a port of STscript | P-089, P-090 |
| ST-69 | Theme/UI customisation (colours, backgrounds, custom CSS, MovingUI, VN mode) | HAVE-THIN | Design tokens + layout shell (UI S301x), accessibility (UI S309x), responsive pass (UI S310x); user theme editing, custom CSS, backgrounds, movable UI not proven | NO HOME in defined parts — flagged for P-014 |
| ST-70 | Localised interface (UI in multiple languages) | MISSING | No UI localisation in the inventory (chat translation, ST-64, is a different row) | NO HOME — flagged for P-014 |
| ST-71 | User accounts (multi-user isolation, roles) | HAVE-THIN | Local auth + owner/user ownership model (S102/S103); multi-user isolated accounts with roles on one server not proven | NO HOME in defined parts — flagged for P-014 |
| ST-72 | Full user-data backup (download all of a user's data) | HAVE | Portable `.runmal` archive (S801) + backup/restore (S802/S114) | — (archive growth at P-028) |
| ST-73 | Clean-up tool (orphan/stale file scan with risk warnings) | MISSING | `runmal doctor` diagnoses (S804) but no orphan clean-up tool in the inventory | NO HOME — flagged for P-014 (nearest kin S804) |
| ST-74 | Token accounting surfaces (per-card, per-message usage) | HAVE-THIN | Prompt Trace + token ledger (S214), token counting (S305, UI S214x); per-character counts as a library surface thin, and the probability surface is ST-40 (missing) | Part IV kin (P-044 lore-side, P-059) |


## Table B — Voxta rows (P-003) × Rúnmál

| # | Feature (short) | State | P-001 evidence / missing depth | Road home |
|---|---|---|---|---|
| VX-01 | Local server + web UI, cloud optional / Lite tier | DELIBERATELY-DIFFERENT | The local half is proven (S102 localhost bind, S109 web UI). The cloud-carried and subscription/Lite tiers are not missing features: Rúnmál is sovereign local-first by founding design (roadmap §2) and builds no gated tier | — (sovereign shape shipped) |
| VX-02 | Characters (distinct fields + culture/language/date sense) | HAVE-THIN | Card fields proven (S104/S106/S110); a character culture setting its language and date/time sense not proven | Part II kin; template side in Part IX (title only) |
| VX-03 | Character assets & generated expressions, Emotes/States | HAVE-THIN | Asset storage/round-trip proven (S113 CHARX, S106); expression generation and scenario-free Emotes/States not proven | P-023; Part X (title only) |
| VX-04 | Voices as character equipment (Voices Studio, favourites, culture filter) | HAVE-THIN | Per-character voice profiles proven (S512); a voices studio/catalogue with favourites and culture filtering not proven | Part VII (title only); census at P-010 |
| VX-05 | User identity in prompt; scenario impersonation override | HAVE-THIN | Persona identity proven (S110, S603); a scenario overriding who the user plays not proven (scenarios themselves are VX-28) | P-018 kin; Part IX (title only) |
| VX-06 | Multi-character chats + history sharing with absent characters | HAVE-THIN | Group chats proven (S210/S211); the returning-character digest of missed history is later work | P-071 |
| VX-07 | Companions vs assistants as distinct kinds (default assistant) | MISSING | No assistant kind or default-assistant concept in the inventory (cross-ref ST-55) | Part XIII (title only) — flagged for P-014 |
| VX-08 | Chat style & flow taxonomy (Companion/Roleplay/Storytelling/Assistant; Chat/Story flow) | MISSING | No style/flow taxonomy in the inventory | Part IX (title only) — flagged for P-014 |
| VX-09 | Real-time voice both ways, interruptible mid-sentence | HAVE | Full loop proven: capture/VAD/STT/TTS/orchestrator/turn-taking/barge-in (S501–S507). Carried caveat (P-001): CosyVoice CPU speed is HAVE-THIN (p50 23.15 s / RTF 6.73 vs unmet GPU-reference thresholds) — a performance fact about one engine, not this row's behaviour | — (speed feeds P-009/P-010) |
| VX-10 | Adaptive VAD & learned turn detection, filler tolerance | HAVE-THIN | Silero VAD with hysteresis (S502), turn-taking (S506), backchannel tolerance in barge-in (S507); adaptive-to-room VAD and a learned end-of-turn model not proven | Part VII (title only) |
| VX-11 | Mishearing handled (repeat request, replacements, STT confidence marks) | MISSING | STT with word timestamps (S503) is substrate only; no mishearing detection, replacement list, or confidence surface in the inventory | NO HOME — flagged for P-014 (Part VII kin) |
| VX-12 | Expressive voices: prosody/affects, Emotion Tags, TTS playground | HAVE-THIN | TTS service + voice profiles proven (S504/S512); emotion/affect control, model emotion-tag support, and an affects playground not proven | P-010 (census); Part VII (title only) |
| VX-13 | Narrator voice (scenario-named, per message type) | MISSING | No narrator concept in the inventory; depends on scenarios (VX-28) | Part IX (title only) |
| VX-14 | Many ears (multiple STT services, local/cloud) | HAVE-THIN | One baseline STT service proven (S503, faster-whisper); a pluggable multi-service STT row is later work | P-010 (census); Part VII (title only) |
| VX-15 | Service-type architecture (labelled coexisting services per type, auto-select) | HAVE-THIN | Separate backend/embedding/profile seams proven (S301/S304/S306/S311); several labelled services of one type coexisting with first-fitting auto-selection not proven | P-008, P-010 (ledgers) |
| VX-16 | Local LLM engines (llama.cpp/ExLlama class) + structured output | HAVE-THIN | Ollama/OpenRouter/Aesir proven (S302/S303/S701); direct llama.cpp-class engines not proven, and grammar/JSON-mode is later work | P-008; P-061 |
| VX-17 | Decisions (dedicated multiple-choice service for speaker/action/tool gating) | MISSING | The pluggable director (S212) is a speaker-policy seam with a deterministic fake — substrate, not a Decisions service gating actions/tools | Part IX/XIII (titles only) — flagged for P-014 |
| VX-18 | Reasoning budgeted separately (reply budget stated, summarizer can think) | MISSING | Token budgets exist for prompt/lore (S204/S205) but no reasoning-budget control in the inventory (cross-ref ST-30) | NO HOME — flagged for P-014 |
| VX-19 | VRAM awareness (estimator, launch prevention, load breakdown) | MISSING | No VRAM estimation in the inventory; Aesir's own ledger is the neighbouring truth source | P-009 kin — flagged for P-014 |
| VX-20 | Module system (installable feature modules with config pages) | MISSING | No module/plugin system in the inventory; the plugin row is Rúnmál's shape of this idea | P-081, P-082, P-083 |
| VX-21 | Long-term memory across conversations | HAVE | Living-memory campaign proven end-to-end: vector store, ingestion, hybrid recall, nucleus, witness scoping (S401–S408) | — |
| VX-22 | Memory books (authored lore; last-10-messages query; pinned/weighted; stable order) | HAVE-THIN | Lorebooks with keyword scan, budget, priority proven (S201–S204); the exact query window, pin/weight as book citizens, and cache-stable rendering order not proven individually | Part III (P-031–P-048) |
| VX-23 | Private book & subject memory (Memories + always-on Understanding) | HAVE-THIN | Extraction (S405) + memory nucleus (S408) + browser (S410) prove the substance in Rúnmál's own shape; the two-kind private-book surface per character not proven as such | — (memory depth; no dedicated slice — noted for P-014) |
| VX-24 | Memory lifecycle honesty (superseded stays readable; absorbed stops restating) | HAVE | Supersession states with history kept (S413), consolidation preserving provenance (S412), inspectable memory browser (S410) | — |
| VX-25 | Summarization feeds memory; auto chat titles | HAVE-THIN | Summarization (S404) + extraction (S405) proven and linked in the memory architecture; extraction-after-summary as one pipeline, auto-correction, and auto-generated titles not proven | Part VI kin (P-084) |
| VX-26 | Memory providers pluggable (lexical vs lexical+embedding scoring) | HAVE-THIN | Hybrid retrieval fuses vector + FTS (S403) and embedding profiles are switchable (S311); a selectable memory-provider slot (lexical-only vs semantic) not proven | — (noted for P-014) |
| VX-27 | Book tooling & interop (attach to char/scenario, export/import shapes, extract from chat, merge) | HAVE-THIN | Books + archive export proven (S201/S801); ST-shaped lorebook file interop, extract-from-chat, and merge are later work; `.voxpak`/Agnaistic shapes are interop-spec questions for their slices | P-019, P-026 kin |
| VX-28 | The scenario as a unit (editor, tabs, casual chats need none) | MISSING | Scenario/greeting UI (UI S212x) edits card fields, not a scenario engine; no scenario unit in the inventory | Part IX (title only) |
| VX-29 | Scenario core settings (flow/style/template/bootstrap/narrator/flags) | MISSING | None in the inventory | Part IX (title only) |
| VX-30 | Scenario template & per-scenario system-prompt override | MISSING | Prompt templates are preset/global citizens (S205/S207), not per-scenario overrides | Part IX (title only) |
| VX-31 | Roles as named slots (templates/scripts reference roles, enable/silence by script) | MISSING | Group members are characters (S210), not named role slots | Part IX (title only) |
| VX-32 | Bootstrap messages (authored typed opening lines) | MISSING | Greetings (UI S212x) are substrate only; typed bootstrap blocks absent | Part IX (title only) |
| VX-33 | Parent scenarios (inheritance, shared script library) | MISSING | No scenario inheritance in the inventory | Part IX (title only) |
| VX-34 | Flags & variables as the scenario state store (persist with chat) | HAVE-THIN | Variables substrate exists (S307 variables, UI S307x macro/variable helper); a per-chat flags/variables store as a first-class citizen is later work, shared with scenarios | P-093; Part IX (title only) |
| VX-35 | Events (timed/probability windows, max-fires, chaining) | MISSING | Lore timed effects (S203) govern prompt entries, not scenario events; no event engine in the inventory | Part IX (title only) |
| VX-36 | Actions vs tools (inference-pass actions vs mid-reply tools) | MISSING | Director seam (S212) and bridge APIs are substrate; neither decider exists as scenario machinery | Part IX (title only) |
| VX-37 | Action layers, typed arguments, conditions | MISSING | No action system in the inventory | Part IX (title only) |
| VX-38 | Effects & display (fired actions set flags/inject/cancel; chrome levels) | MISSING | No action/effect system in the inventory | Part IX (title only) |
| VX-39 | Buttons & controls as player input (two-way variable binding, HUD widgets) | MISSING | Command palette (UI S308x) is a host UI surface, not in-chat player controls | Part IX (title only) |
| VX-40 | Contexts (conditional prompt sentences, runtime-set) | MISSING | Author's Note and lore entries are kin mechanisms (S206/S201) but contexts as scenario citizens are absent | Part IX (title only) |
| VX-41 | Typed message taxonomy (char/user/role/event/story/note/secret/instructions; expiry) | HAVE-THIN | Messages with per-message speaker proven (S107/S210) and bridge event types exist (S602/S609); the full taxonomy — secret/note/instructions visibility classes and prompt-expiry — not proven | Part IX (title only) |
| VX-42 | JavaScript scripting, sandboxed (ES-module scenario scripts) | DELIBERATELY-DIFFERENT | Rúnmál does not adopt arbitrary-code scenario scripting: its founding security shape is data + declared capabilities (roadmap Part VI, P-082). Scenario logic is to be rebuilt from declared events/actions/variables (Part IX), not ES modules with host-shaped imports | P-082 (the sandbox law); Part IX (title only) |
| VX-43 | Scriban templates everywhere (fields over user/char/flags/variables/now) | MISSING | Macros (S110) + composer templates (S205) are a different, narrower surface; per-field templating over scenario state absent | Part IX (title only) |
| VX-44 | Apps configured per scenario (host-app triggers) | MISSING | Bridges are host integrations (S601–S611) but are not configured per scenario, and no app-trigger surface exists | Part IX (title only) |
| VX-45 | Visual-novel play (authored scenario as VN with voices/images) | MISSING | Voice + chat substrates exist; no VN presentation in the inventory | Part IX/X (titles only) |
| VX-46 | HUD & stage effects (bars/chips/inventory/checklist, splash, screen effects, sprites) | MISSING | No stage/HUD system in the inventory | Part IX (title only) |
| VX-47 | Clickable maps, inventories, HUD widgets | MISSING | No clickable scenario surfaces in the inventory | Part IX (title only) |
| VX-48 | Portrait animation (still picture speaks with the voice) | MISSING | No portrait animation in the inventory | Part X (title only) |
| VX-49 | Video & 3D avatars (MP4/AVIF, VRM popout) | MISSING | No video/3D avatar surface in the inventory | Part X (title only) |
| VX-50 | Vision on request (screen/photo/webcam/folder watcher) | MISSING | No vision service in this repo's inventory (Aesir-side vision is a different project's ledger, counted at P-009, not here) | Part VIII (title only) |
| VX-51 | Image generation in the companion (`/imagine`, avatar defaults) | MISSING | No image generation in the inventory (cross-ref ST-61) | P-087; Part X (title only) |
| VX-52 | Video generation (WAN-class, img→video, resumable jobs) | MISSING | No video generation in the inventory | Part X (title only) — flagged for P-014 |
| VX-53 | Generation plumbing depth (ComfyUI/Diffusers backends, upscaler, LoRA panels) | MISSING | No generation backends in the inventory | Part X (title only) — flagged for P-014 |
| VX-54 | Workspaces (chat bound to a real folder; read/write/edit, run, launch) | MISSING | No workspace concept in the inventory | Part XI (title only) |
| VX-55 | Coding-agent backends (Claude Code / Codex class, permissioned) | MISSING | No coding-agent backend in the inventory | Part XI (title only) |
| VX-56 | Assistant tooling breadth (shell, Python, web search, MCP, user scripts) | MISSING | No assistant tooling in the inventory (bridge APIs are a different surface) | Part XI/XIII (titles only) |
| VX-57 | Tool-calling security pass (review destructive calls, path rules, scopes) | MISSING | Scoped/revocable bridge credentials (S601) and the secrets discipline (S306) are proven substrate, but they guard bridges, not workspace tool calls, which do not exist yet | Part XI (title only) |
| VX-58 | Done notifications (OS-integrated completion notices) | MISSING | No notification surface in the inventory | Part XI (title only) — flagged for P-014 |
| VX-59 | The Content Hub (browse/install/share, creator profiles) | DELIBERATELY-DIFFERENT | Roadmap §2 rules the sovereign shape: no central store — signed local packs + friend-instance exchange instead, with the parity matrix (Part XIV) stating the shape plainly. Creator-profile/central-catalogue form is not a gap to close | Part XII (title only) |
| VX-60 | Content packages (`.voxpak`: bundle, encryption, protected publish) | HAVE-THIN | The `.runmal` archive is the proven pack substrate (S801: versioned manifest, characters/chats/lorebooks/memories/presets/assets, secrets excluded); `.voxpak` interop, encrypted/protected packs, and publish semantics not proven | P-028; Part XII (title only) |
| VX-61 | Chats travel as packs (with images, dependency warnings) | HAVE-THIN | Chats are in the `.runmal` archive (S801); chat-as-pack with generated-image payload and missing-dependency warnings not proven | P-028 kin; Part XII (title only) |
| VX-62 | Clients (Windows desktop, Linux server+browser, Android companion) | HAVE-THIN | Linux + browser is the proven shape (S805 Linux leg, UI S310x responsive); native Windows desktop and Android companion apps are absent, and the sovereign client shape is a decision still to be recorded | P-011 (decision record) |
| VX-63 | Web UI phone-shaped (master-detail, cards, bottom sheets, step flows) | HAVE-THIN | Mobile/responsive pass proven (UI S310x); the 1.11-depth phone rework (bottom sheets, step-by-step playground flows) not proven | P-011 kin |
| VX-64 | Shared accounts (several sign-ins on one account, users management) | HAVE-THIN | Owner/user model proven (S102/S103); several distinct sign-ins sharing one account with a management surface not proven (cross-ref ST-71) | NO HOME in defined parts — flagged for P-014 |
| VX-65 | Chat Inspector (script log, flags/contexts views, hidden calls recorded) | MISSING | Prompt inspector + trace (S215/S214) answer "why this prompt", not "why didn't that event fire"; no scenario inspector exists because scenarios do not yet | Part XIII (title only) |
| VX-66 | Open extension surface (SDK, Python modules, MCP, API, scopes) | HAVE-THIN | A versioned, scoped bridge/conversation API is proven (S601–S611); SDK, module, and MCP surfaces await the plugin row and later parts | P-081; Part XIII (title only) |
| VX-67 | Games, apps & bots (incl. Discord bot per channel) | HAVE-THIN | Game bridges proven (VRChat S605, Conan S606, Skyrim S607); a Discord bot surface is absent | Part XIII (title only) |

## Cross-cutting findings

- **Where the mirrors agree, Rúnmál is usually already strong.**
  Both mirrors' memory rows (ST-58/ST-59, VX-21–VX-27) land
  mostly HAVE/HAVE-THIN on the founding Campaign IV — the
  founding road out-built both mirrors there, and the remaining
  work is surface shape (editable summary citizen, book interop),
  not engines.
- **Where Voxta is alone, Rúnmál is usually absent.** Scenarios
  and everything hanging off them (VX-28–VX-47) are 20 rows with
  no HAVE among them: 17 MISSING, 2 HAVE-THIN on substrates
  (VX-34 variables, VX-41 message types), 1
  DELIBERATELY-DIFFERENT (VX-42 scripting shape). This is the
  road's genuinely new territory, exactly as the roadmap's §1
  said — and it is the territory whose slice definitions are
  missing from the filed roadmap file.
- **The three DELIBERATELY-DIFFERENT rows are the sovereign
  spine:** no cloud/subscription tier (VX-01), no arbitrary-code
  scenario scripting (VX-42), no central content store (VX-59).
  Each names its replacement shape; none is a gap dressed up.
- **Depth, not breadth, is the SillyTavern story.** SillyTavern
  rows are dominated by HAVE-THIN: the founding road was born
  from studying this mirror, so cores exist and the deltas are
  named sub-depths (group scoring, outlet macros, persona
  positions, template files) with defined homes in Parts II–V.

## What P-004 hands onward

- To P-005: the interop corpus must stress the THIN rows of
  Part II first (ST-02/ST-05 card depth, ST-34 presets,
  VX-27 books) — fixtures that only test HAVE rows prove nothing
  new.
- To P-008/P-009/P-010: ST-41–ST-44 + VX-15/VX-16 (backends),
  VX-19 (VRAM, Aesir-side), and ST-35/VX-12/VX-14 (sampler and
  voice-provider breadth) are this table's ledger inputs.
- To P-013: the priority evidence in the re-cut assessment,
  point 4 (voice strong, scenarios absent, hub sovereign-late).
- To P-014: the flagged NO-HOME rows (re-cut point 3) plus the
  Parts VII–XIV validation limit (point 2) are the gate's
  explicit agenda. Nothing flagged here is closed by being
  flagged.

## F-04 follow-on (2026-10-31) — ST-73 is built

The P-014 gate homed this table's ST-73 row (clean-up tool,
MISSING, no home) as follow-on **F-04**, and F-04 is now
banked: `runmal cleanup` exists in this tree
(`diagnostics/cleanup.py` over the S804 doctor), scanning six
categories — orphan character assets, unreferenced character
files, chats of deleted characters, stale backups,
stale staging, and unrecognized backup-dir files — each item
carrying its category's risk warning, with dry-run-by-default
removal under re-validation, containment, and high-risk
gating. The one deliberate shape difference from the mirror
is recorded in the slice doc: Rúnmál's soft delete (S303)
means a deleted character's assets are retained-for-restore,
never orphans, and its chats are high-risk explicit removals.
This table's original ST-73 verdict above is the historical
record of the gap and is not rewritten; this note is the
gap's closing entry. Full record:
`docs/CLEANUP_TOOL_2026-10-31.md`.
