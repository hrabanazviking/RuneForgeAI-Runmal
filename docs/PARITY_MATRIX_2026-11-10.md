# P-219 - The Parity Matrix, founded (2026-11-10)

*Part XIV (The Proof Spine) opening slice, DERIVED scope. The
parity matrix, published: the full 141-row mirror universe of
the P-004 Delta Table, carried verbatim with its opening
verdicts and road homes, and re-judged at the close of the
road - in this founding slice for tranche 1 only (the rows
whose road home was Part II), every other row printed with
the explicit NOT-YET-REJUDGED marker.*

## §0 Method

- Principle 4 (roadmap section 2) is the founding duty: where
a mirror's feature depends on a cloud or a store, Runmal
builds the sovereign shape instead - and the parity matrix
(Part XIV) says plainly which shape shipped. This document
is that matrix.
- DERIVED scope, stated plainly: the governing roadmap gives
Part XIV only its part-table line ("The Proof Spine - the
parity matrix, published", P-219 to P-232) plus founding
principle 4. There is no per-slice roadmap text for
P-219 onward; this slice's scope is derived from those two
texts, the Part I census heritage (P-001/P-002/P-003/P-004/
P-008) and the banked trail in CAMPAIGN_STATE.md, and is
labelled derived wherever the artefact repeats it. Nothing
here is roadmap verbatim.
- Base truth at founding: HEAD c8a054d (the P-218 banking
record), migration head 0042, route census 356/439, suite
6223 passed / 5 skipped / 0 failed.
- Evidence rule (P-001's handover rule, kept by P-004): every
closing verdict cites a proving test file or banked slice
doc in THIS repo; citations must resolve to real paths. No
citation may point at a mirror source (clean-room law).
- The row universe, mirror feature names, opening verdicts
and road homes are carried verbatim from
docs/DELTA_TABLE_2026-10-30.md (the P-004 Delta Table):
141 rows, ST-01 to ST-74 and VX-01 to VX-67, each present
exactly once.

## §1 Verdict vocabulary

Opening verdicts are P-004's, unchanged: **HAVE** (the
inventory proves essentially the whole row), **HAVE-THIN**
(the core is proven; the missing depth is named in the row,
never hidden), **MISSING** (the core behaviour is absent),
**DELIBERATELY-DIFFERENT** (Runmal's sovereign shape
replaces the mirror's shape by design; an opening verdict
only - closing rows never carry it).

Closing verdicts: HAVE / HAVE-THIN / MISSING in the same
senses, plus **SHIPPED-SOVEREIGN** (a named sovereign shape
shipped in place of a cloud- or store-dependent mirror
shape - principle 4's "says plainly which shape shipped";
the shape is named in the row) and **NOT-YET-REJUDGED**
(the explicit tranche marker: no closing judgement is
claimed for this row yet). A tranche-1 row judged
HAVE-THIN names its still-missing depth in the closing
cell, in the P-004 discipline.

## §2 The tranche map

A sketch, labelled a sketch and re-derived per slice:
P-219 founding (this slice; tranche 1 = Part II rows);
P-220 Part III; P-221 Part IV; P-222 Part V; P-223 Part VI;
P-224 Part VII; P-225 Part VIII; P-226 Part IX; P-227
Part X; P-228 Part XI; P-229 Part XII; P-230 Part XIII;
P-231 reconciliation (whole-matrix mechanical recount, the
principle-4 sovereign-shape statements audited end to end,
a generated machine-readable twin is a named candidate);
P-232 the Part XIV gate, in the established two-battery
gate form.

## §3 Summary counts

Opening counts, counted mechanically from the P-004
tables and carried in section 0's universe: SillyTavern
11 HAVE / 45 HAVE-THIN / 18 MISSING / 0
DELIBERATELY-DIFFERENT; Voxta 3 / 24 / 37 / 3;
combined 14 HAVE / 69 HAVE-THIN / 55 MISSING / 3
DELIBERATELY-DIFFERENT, of 141 rows.

Tranche 1 closing counts: HAVE 2, HAVE-THIN 10,
MISSING 0, SHIPPED-SOVEREIGN 0, NOT-YET-REJUDGED 0,
of 12 rows.

Unjudged remainder: 129 rows NOT-YET-REJUDGED.

## Table A - SillyTavern rows (P-002) at the close

| # | Feature (short) | Opening verdict | Road home | Closing verdict | Evidence |
|---|---|---|---|---|---|
| ST-01 | Character cards as organising unit | HAVE | — (depth in Part II) | NOT-YET-REJUDGED | - |
| ST-02 | Card import (file + URL), v2/v3 | HAVE-THIN | P-015, P-016 | HAVE-THIN - External Import from a URL still absent (grep-verified at founding: no URL path into card import exists in the tree); file import is full for v2 and v3 incl. CHARX | `tests/test_p015_card_v2.py`, `tests/test_p016_card_v3.py` |
| ST-03 | Library-scale search/sort/tags-as-folders | HAVE-THIN | P-024 | HAVE-THIN - sort by usage/size not proven and no collections or folders exist (the tag folder/manager depth is absent, P-024 record); search, tag filtering, favourites and the named sorts are proven | `tests/test_p024_library_organisation.py` |
| ST-04 | Card editing depth (stats, favourite, duplicate, gallery) | HAVE-THIN | P-023, P-024, P-025 | HAVE-THIN - per-card usage stats still not proven; favourite toggle, duplicate/version handling and card assets/gallery are proven | `tests/test_p024_library_organisation.py`, `tests/test_p025_character_versions.py`, `tests/test_p023_card_assets.py` |
| ST-05 | Extended card ops (link lore, scenario override, convert, rename-relink, source link, replace) | HAVE-THIN | Part II (P-015–P-019, P-025, P-029) | HAVE-THIN - convert character/persona and rename-relink not proven; lorebook link, scenario carriage, source/provenance and replace-as-version are proven | `tests/test_p029_provenance_on_import.py`, `tests/test_p025_character_versions.py`, `tests/test_p026_scenario_interop.py`, `docs/CHARACTER_BOOK_BINDING_2026-11-06.md` |
| ST-06 | Advanced definitions (prompt overrides, creator metadata, char note depth/role, talkativeness) | HAVE-THIN | Part IV (P-049, P-057) | NOT-YET-REJUDGED | - |
| ST-07 | Alternate greetings | HAVE-THIN | P-079 | NOT-YET-REJUDGED | - |
| ST-08 | Personas (switch mid-chat, batch re-attribution) | HAVE-THIN | P-018 | HAVE-THIN - batch sync re-attribution of past messages still absent (grep-verified at founding); the persona citizen and its file interop are proven | `tests/test_p018_persona_interop.py` |
| ST-09 | Persona description positions (story string / AN depth & role / disabled) | MISSING | P-018 | HAVE | `tests/test_p018_persona_interop.py` |
| ST-10 | Persona locking/default/temp override/per-character picker, persona backup | HAVE-THIN | P-018 | HAVE-THIN - locking to chat/character, session/temp override and a per-character picker still not proven; personas remain a file citizen with no persona store (P-030 gate section 8), riding the general archive | `tests/test_p018_persona_interop.py` |
| ST-11 | Group chats (members, mute, re-order, force-trigger) | HAVE | — (depth in P-070) | NOT-YET-REJUDGED | - |
| ST-12 | Group reply-order strategies (Manual/Natural/List/Pooled) | HAVE | — | NOT-YET-REJUDGED | - |
| ST-13 | Group generation handling (swap vs join cards, join templates) | HAVE-THIN | P-070 | NOT-YET-REJUDGED | - |
| ST-14 | Group extras (auto-mode, self-response, group scenario override, peek/edit member) | HAVE-THIN | P-070 | NOT-YET-REJUDGED | - |
| ST-15 | Keyword-triggered lore entries (regex keys, scan buffer) | HAVE-THIN | Part III (P-031 kin) | NOT-YET-REJUDGED | - |
| ST-16 | Selective logic AND ANY/ALL, NOT ANY/ALL | HAVE-THIN | P-032 | NOT-YET-REJUDGED | - |
| ST-17 | Entry strategies: constant / keyword / vectorised | HAVE-THIN | P-035, P-041 | NOT-YET-REJUDGED | - |
| ST-18 | Insertion positions incl. Outlet macro | HAVE-THIN | P-038 | NOT-YET-REJUDGED | - |
| ST-19 | Probability (Trigger %) | HAVE | — (honesty deepened at P-036) | NOT-YET-REJUDGED | - |
| ST-20 | Inclusion groups (weight, priority, group scoring) | HAVE-THIN | P-034 | NOT-YET-REJUDGED | - |
| ST-21 | Timed effects: sticky / cooldown / delay | HAVE | — | NOT-YET-REJUDGED | - |
| ST-22 | Recursive scanning with per-entry controls | HAVE-THIN | P-031 | NOT-YET-REJUDGED | - |
| ST-23 | Scan configuration (depth, Min Activations, names in buffer) | HAVE-THIN | P-037 | NOT-YET-REJUDGED | - |
| ST-24 | Lore token budget (context-% or absolute, insertion order) | HAVE | — | NOT-YET-REJUDGED | - |
| ST-25 | Four lore scopes layered (global/character/persona/chat) | HAVE-THIN | P-039, P-040 | NOT-YET-REJUDGED | - |
| ST-26 | Per-entry gating extras (character filter, generation-type triggers, extra scan sources) | MISSING | NO HOME — flagged for P-014 | NOT-YET-REJUDGED | - |
| ST-27 | Automation ID (entry firing runs a command) | MISSING | Part VI kin (P-081, P-093); no dedicated slice — flagged for P-014 | NOT-YET-REJUDGED | - |
| ST-28 | Prompt Manager (ordered editable blocks, roles, depth, gen triggers) | HAVE-THIN | P-049 | NOT-YET-REJUDGED | - |
| ST-29 | Prompt Manager utility surface (nudges, markers, squash, system merge…) | HAVE-THIN | P-049 | NOT-YET-REJUDGED | - |
| ST-30 | Reasoning controls (visibility toggle, reasoning effort) | MISSING | NO HOME — flagged for P-014 (nearest kin P-052) | NOT-YET-REJUDGED | - |
| ST-31 | Advanced Formatting (system/context/instruct templates, auto-derivation) | HAVE-THIN | P-050, P-051 | NOT-YET-REJUDGED | - |
| ST-32 | Context template / story string (Handlebars anchors) | HAVE-THIN | P-051 | NOT-YET-REJUDGED | - |
| ST-33 | Instruct templates (ChatML/Llama-3/Alpaca class, per model) | HAVE-THIN | P-050 | NOT-YET-REJUDGED | - |
| ST-34 | Presets (shareable JSON bundles per API type) | HAVE-THIN | P-021, P-054 | HAVE | `tests/test_p021_preset_interop.py`, `docs/PRESET_BUNDLES_2026-11-06.md` |
| ST-35 | Sampler surface (temp, top-p/k, min-p, penalties, DRY/XTC class) | HAVE-THIN | P-052, P-053 | NOT-YET-REJUDGED | - |
| ST-36 | Macros ({{char}}/{{user}}/{{original}}/{{outlet::…}} + wider set) | HAVE-THIN | P-055 | NOT-YET-REJUDGED | - |
| ST-37 | Author's Note (per-chat, depth/frequency) | HAVE | — (frequency deepened at P-056) | NOT-YET-REJUDGED | - |
| ST-38 | Post-history instructions (manager citizen, per-card override) | HAVE-THIN | P-057 | NOT-YET-REJUDGED | - |
| ST-39 | Multimodal & tool toggles (inline image/video, web search tool, function calling) | HAVE-THIN | Part IV kin; vision in Part VIII (title only) — flagged for P-014 | NOT-YET-REJUDGED | - |
| ST-40 | Token probabilities viewer (alternatives, reroll from a token) | MISSING | NO HOME — flagged for P-014 | NOT-YET-REJUDGED | - |
| ST-41 | Two API paradigms (Chat Completion vs Text Completion) | HAVE-THIN | P-008 (ledger judgement) | NOT-YET-REJUDGED | - |
| ST-42 | Chat Completion source breadth (OpenAI/Claude/Google/Mistral/DeepSeek/…) | HAVE-THIN | P-008 | NOT-YET-REJUDGED | - |
| ST-43 | Text Completion backend breadth (llama.cpp/KoboldCpp/Tabby/NovelAI/Horde…) | HAVE-THIN | P-008 | NOT-YET-REJUDGED | - |
| ST-44 | AI Horde out of the box (zero-setup free pool) | MISSING | P-008 (wanted/unwanted judgement) — no build slice, flagged for P-014 | NOT-YET-REJUDGED | - |
| ST-45 | Per-source secrets (server-side, never in chat data) | HAVE | — | NOT-YET-REJUDGED | - |
| ST-46 | Swipes (alternates kept on a message, navigated in place) | HAVE-THIN | P-065 | NOT-YET-REJUDGED | - |
| ST-47 | Message editing with movement (edit/copy/delete/move) | HAVE-THIN | P-068 | NOT-YET-REJUDGED | - |
| ST-48 | Branches (fork at any message, linked child chat) | MISSING | P-066 | NOT-YET-REJUDGED | - |
| ST-49 | Checkpoints (named snapshots, one-click return) | MISSING | P-067 | NOT-YET-REJUDGED | - |
| ST-50 | Message inclusion toggle (exclude from model's view, keep in chat) | MISSING | P-068 kin; no dedicated slice — flagged for P-014 | NOT-YET-REJUDGED | - |
| ST-51 | Continue (extend last message, nudge/prefill) | HAVE-THIN | P-069 | NOT-YET-REJUDGED | - |
| ST-52 | Impersonate (model drafts the user's message) | HAVE | — (paired depth at P-069) | NOT-YET-REJUDGED | - |
| ST-53 | Regenerate (discard + re-roll as its own generation type) | HAVE-THIN | Part V kin (P-065/P-069) | NOT-YET-REJUDGED | - |
| ST-54 | Chat file management (import/export/rename, chat→group conversion) | HAVE-THIN | P-020, P-078 | HAVE-THIN - in-place chat-to-group conversion still absent (grep-verified at founding); JSONL import/export and rename are proven | `tests/test_p020_chat_import.py` |
| ST-55 | Welcome screen + Assistant (recent chats, quick uncarded chat, default Assistant) | HAVE-THIN | Part XIII (title only) — flagged for P-014 | NOT-YET-REJUDGED | - |
| ST-56 | Per-message utility actions (translate/image/narrate/prompt view) | HAVE-THIN | Part VI (P-086, P-087 kin) | NOT-YET-REJUDGED | - |
| ST-57 | Extension system (UI extensions + server plugins, distribution channel) | MISSING | P-081, P-082, P-083 | NOT-YET-REJUDGED | - |
| ST-58 | Summarize extension (editable rolling summary, {{summary}} injection) | HAVE-THIN | P-084 | NOT-YET-REJUDGED | - |
| ST-59 | Vector Storage / RAG extension (history, Data Bank, lore) | HAVE | — (plugin shape at P-085) | NOT-YET-REJUDGED | - |
| ST-60 | Data Bank (per-chat/global attached documents + scrapers) | MISSING | P-074 | NOT-YET-REJUDGED | - |
| ST-61 | Image generation extension | MISSING | P-087 | NOT-YET-REJUDGED | - |
| ST-62 | TTS extension (pluggable narration, per-message) | HAVE-THIN | P-091 | NOT-YET-REJUDGED | - |
| ST-63 | Speech recognition (voice input to chat) | HAVE-THIN | P-091 | NOT-YET-REJUDGED | - |
| ST-64 | Chat translation extension | MISSING | P-086 | NOT-YET-REJUDGED | - |
| ST-65 | Expressions / sprites + Visual Novel mode | MISSING | P-092 (surface); Part X (title only) | NOT-YET-REJUDGED | - |
| ST-66 | Web search (extension + backend tool, opt-in) | MISSING | P-088 | NOT-YET-REJUDGED | - |
| ST-67 | Regex scripts (named, staged, per-character/global, test mode) | MISSING | P-090 | NOT-YET-REJUDGED | - |
| ST-68 | Quick Replies + STscript + slash commands | HAVE-THIN | P-089, P-090 | NOT-YET-REJUDGED | - |
| ST-69 | Theme/UI customisation (colours, backgrounds, custom CSS, MovingUI, VN mode) | HAVE-THIN | NO HOME in defined parts — flagged for P-014 | NOT-YET-REJUDGED | - |
| ST-70 | Localised interface (UI in multiple languages) | MISSING | NO HOME — flagged for P-014 | NOT-YET-REJUDGED | - |
| ST-71 | User accounts (multi-user isolation, roles) | HAVE-THIN | NO HOME in defined parts — flagged for P-014 | NOT-YET-REJUDGED | - |
| ST-72 | Full user-data backup (download all of a user's data) | HAVE | — (archive growth at P-028) | NOT-YET-REJUDGED | - |
| ST-73 | Clean-up tool (orphan/stale file scan with risk warnings) | MISSING | NO HOME — flagged for P-014 (nearest kin S804) | NOT-YET-REJUDGED | - |
| ST-74 | Token accounting surfaces (per-card, per-message usage) | HAVE-THIN | Part IV kin (P-044 lore-side, P-059) | NOT-YET-REJUDGED | - |

## Table B - Voxta rows (P-003) at the close

| # | Feature (short) | Opening verdict | Road home | Closing verdict | Evidence |
|---|---|---|---|---|---|
| VX-01 | Local server + web UI, cloud optional / Lite tier | DELIBERATELY-DIFFERENT | — (sovereign shape shipped) | NOT-YET-REJUDGED | - |
| VX-02 | Characters (distinct fields + culture/language/date sense) | HAVE-THIN | Part II kin; template side in Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-03 | Character assets & generated expressions, Emotes/States | HAVE-THIN | P-023; Part X (title only) | HAVE-THIN - expression generation as a character pipeline not proven as such; character assets and expression sets/states are proven | `tests/test_p023_card_assets.py`, `tests/test_p092_expressions.py` |
| VX-04 | Voices as character equipment (Voices Studio, favourites, culture filter) | HAVE-THIN | Part VII (title only); census at P-010 | NOT-YET-REJUDGED | - |
| VX-05 | User identity in prompt; scenario impersonation override | HAVE-THIN | P-018 kin; Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-06 | Multi-character chats + history sharing with absent characters | HAVE-THIN | P-071 | NOT-YET-REJUDGED | - |
| VX-07 | Companions vs assistants as distinct kinds (default assistant) | MISSING | Part XIII (title only) — flagged for P-014 | NOT-YET-REJUDGED | - |
| VX-08 | Chat style & flow taxonomy (Companion/Roleplay/Storytelling/Assistant; Chat/Story flow) | MISSING | Part IX (title only) — flagged for P-014 | NOT-YET-REJUDGED | - |
| VX-09 | Real-time voice both ways, interruptible mid-sentence | HAVE | — (speed feeds P-009/P-010) | NOT-YET-REJUDGED | - |
| VX-10 | Adaptive VAD & learned turn detection, filler tolerance | HAVE-THIN | Part VII (title only) | NOT-YET-REJUDGED | - |
| VX-11 | Mishearing handled (repeat request, replacements, STT confidence marks) | MISSING | NO HOME — flagged for P-014 (Part VII kin) | NOT-YET-REJUDGED | - |
| VX-12 | Expressive voices: prosody/affects, Emotion Tags, TTS playground | HAVE-THIN | P-010 (census); Part VII (title only) | NOT-YET-REJUDGED | - |
| VX-13 | Narrator voice (scenario-named, per message type) | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-14 | Many ears (multiple STT services, local/cloud) | HAVE-THIN | P-010 (census); Part VII (title only) | NOT-YET-REJUDGED | - |
| VX-15 | Service-type architecture (labelled coexisting services per type, auto-select) | HAVE-THIN | P-008, P-010 (ledgers) | NOT-YET-REJUDGED | - |
| VX-16 | Local LLM engines (llama.cpp/ExLlama class) + structured output | HAVE-THIN | P-008; P-061 | NOT-YET-REJUDGED | - |
| VX-17 | Decisions (dedicated multiple-choice service for speaker/action/tool gating) | MISSING | Part IX/XIII (titles only) — flagged for P-014 | NOT-YET-REJUDGED | - |
| VX-18 | Reasoning budgeted separately (reply budget stated, summarizer can think) | MISSING | NO HOME — flagged for P-014 | NOT-YET-REJUDGED | - |
| VX-19 | VRAM awareness (estimator, launch prevention, load breakdown) | MISSING | P-009 kin — flagged for P-014 | NOT-YET-REJUDGED | - |
| VX-20 | Module system (installable feature modules with config pages) | MISSING | P-081, P-082, P-083 | NOT-YET-REJUDGED | - |
| VX-21 | Long-term memory across conversations | HAVE | — | NOT-YET-REJUDGED | - |
| VX-22 | Memory books (authored lore; last-10-messages query; pinned/weighted; stable order) | HAVE-THIN | Part III (P-031–P-048) | NOT-YET-REJUDGED | - |
| VX-23 | Private book & subject memory (Memories + always-on Understanding) | HAVE-THIN | — (memory depth; no dedicated slice — noted for P-014) | NOT-YET-REJUDGED | - |
| VX-24 | Memory lifecycle honesty (superseded stays readable; absorbed stops restating) | HAVE | — | NOT-YET-REJUDGED | - |
| VX-25 | Summarization feeds memory; auto chat titles | HAVE-THIN | Part VI kin (P-084) | NOT-YET-REJUDGED | - |
| VX-26 | Memory providers pluggable (lexical vs lexical+embedding scoring) | HAVE-THIN | — (noted for P-014) | NOT-YET-REJUDGED | - |
| VX-27 | Book tooling & interop (attach to char/scenario, export/import shapes, extract from chat, merge) | HAVE-THIN | P-019, P-026 kin | HAVE-THIN - extract-from-chat is absent and book merge is not built (packs never merge into an existing book); attach and ST-shaped import/export are proven | `tests/test_p019_lorebook_interop.py`, `docs/LOREBOOK_PACKS_2026-11-06.md` |
| VX-28 | The scenario as a unit (editor, tabs, casual chats need none) | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-29 | Scenario core settings (flow/style/template/bootstrap/narrator/flags) | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-30 | Scenario template & per-scenario system-prompt override | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-31 | Roles as named slots (templates/scripts reference roles, enable/silence by script) | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-32 | Bootstrap messages (authored typed opening lines) | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-33 | Parent scenarios (inheritance, shared script library) | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-34 | Flags & variables as the scenario state store (persist with chat) | HAVE-THIN | P-093; Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-35 | Events (timed/probability windows, max-fires, chaining) | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-36 | Actions vs tools (inference-pass actions vs mid-reply tools) | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-37 | Action layers, typed arguments, conditions | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-38 | Effects & display (fired actions set flags/inject/cancel; chrome levels) | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-39 | Buttons & controls as player input (two-way variable binding, HUD widgets) | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-40 | Contexts (conditional prompt sentences, runtime-set) | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-41 | Typed message taxonomy (char/user/role/event/story/note/secret/instructions; expiry) | HAVE-THIN | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-42 | JavaScript scripting, sandboxed (ES-module scenario scripts) | DELIBERATELY-DIFFERENT | P-082 (the sandbox law); Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-43 | Scriban templates everywhere (fields over user/char/flags/variables/now) | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-44 | Apps configured per scenario (host-app triggers) | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-45 | Visual-novel play (authored scenario as VN with voices/images) | MISSING | Part IX/X (titles only) | NOT-YET-REJUDGED | - |
| VX-46 | HUD & stage effects (bars/chips/inventory/checklist, splash, screen effects, sprites) | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-47 | Clickable maps, inventories, HUD widgets | MISSING | Part IX (title only) | NOT-YET-REJUDGED | - |
| VX-48 | Portrait animation (still picture speaks with the voice) | MISSING | Part X (title only) | NOT-YET-REJUDGED | - |
| VX-49 | Video & 3D avatars (MP4/AVIF, VRM popout) | MISSING | Part X (title only) | NOT-YET-REJUDGED | - |
| VX-50 | Vision on request (screen/photo/webcam/folder watcher) | MISSING | Part VIII (title only) | NOT-YET-REJUDGED | - |
| VX-51 | Image generation in the companion (`/imagine`, avatar defaults) | MISSING | P-087; Part X (title only) | NOT-YET-REJUDGED | - |
| VX-52 | Video generation (WAN-class, img→video, resumable jobs) | MISSING | Part X (title only) — flagged for P-014 | NOT-YET-REJUDGED | - |
| VX-53 | Generation plumbing depth (ComfyUI/Diffusers backends, upscaler, LoRA panels) | MISSING | Part X (title only) — flagged for P-014 | NOT-YET-REJUDGED | - |
| VX-54 | Workspaces (chat bound to a real folder; read/write/edit, run, launch) | MISSING | Part XI (title only) | NOT-YET-REJUDGED | - |
| VX-55 | Coding-agent backends (Claude Code / Codex class, permissioned) | MISSING | Part XI (title only) | NOT-YET-REJUDGED | - |
| VX-56 | Assistant tooling breadth (shell, Python, web search, MCP, user scripts) | MISSING | Part XI/XIII (titles only) | NOT-YET-REJUDGED | - |
| VX-57 | Tool-calling security pass (review destructive calls, path rules, scopes) | MISSING | Part XI (title only) | NOT-YET-REJUDGED | - |
| VX-58 | Done notifications (OS-integrated completion notices) | MISSING | Part XI (title only) — flagged for P-014 | NOT-YET-REJUDGED | - |
| VX-59 | The Content Hub (browse/install/share, creator profiles) | DELIBERATELY-DIFFERENT | Part XII (title only) | NOT-YET-REJUDGED | - |
| VX-60 | Content packages (`.voxpak`: bundle, encryption, protected publish) | HAVE-THIN | P-028; Part XII (title only) | HAVE-THIN - .voxpak interop not proven and encrypted/protected packs not built - pack signing and friend-instance exchange stayed declined through Part XII (the hub census record); the .runmal pack substrate is proven and grew at P-028 | `tests/test_p028_portable_archive_growth.py` |
| VX-61 | Chats travel as packs (with images, dependency warnings) | HAVE-THIN | P-028 kin; Part XII (title only) | NOT-YET-REJUDGED | - |
| VX-62 | Clients (Windows desktop, Linux server+browser, Android companion) | HAVE-THIN | P-011 (decision record) | NOT-YET-REJUDGED | - |
| VX-63 | Web UI phone-shaped (master-detail, cards, bottom sheets, step flows) | HAVE-THIN | P-011 kin | NOT-YET-REJUDGED | - |
| VX-64 | Shared accounts (several sign-ins on one account, users management) | HAVE-THIN | NO HOME in defined parts — flagged for P-014 | NOT-YET-REJUDGED | - |
| VX-65 | Chat Inspector (script log, flags/contexts views, hidden calls recorded) | MISSING | Part XIII (title only) | NOT-YET-REJUDGED | - |
| VX-66 | Open extension surface (SDK, Python modules, MCP, API, scopes) | HAVE-THIN | P-081; Part XIII (title only) | NOT-YET-REJUDGED | - |
| VX-67 | Games, apps & bots (incl. Discord bot per channel) | HAVE-THIN | Part XIII (title only) | NOT-YET-REJUDGED | - |

## §4 Carried items

Named with their standing dispositions. None is claimed
resolved by this slice; none is silently dropped.

- **D1 - stateless SSE error-swallowing: FENCED.** The
  ruling is outstanding; P-219 does not fix, re-judge or
  quietly absorb it. It is named here only.
- **Per-swipe thinking browsing: DECLINED-PENDING-WORD.**
  Volmarr's word only, under the P-206 ruling. The matrix
  records the absence; building it is not taken.
- **K-A binding label update: NAMED OPEN.** Volmarr-
  reserved; named, not resolved or pre-judged.
- **K-B history retention / bulk clear: NAMED OPEN.**
  Volmarr-reserved; named, not resolved or pre-judged.
- **K-C unified-search history retention: NAMED OPEN.**
  Volmarr-reserved; named, not resolved or pre-judged.
- **Bot runtime: substrateless.** chat.write stays
  RESERVED (the sandbox law); no substrate is founded.
  The absence is recorded as deliberate.
- **The three opening DELIBERATELY-DIFFERENT rows** keep
  their standing dispositions, unjudged at close until
  their own tranches: VX-01 (the sovereign shape is
  local-first with no gated tier), VX-42 (the sovereign
  shape is data plus declared capabilities in place of
  arbitrary-code scripting, the P-082 sandbox law), VX-59
  (the sovereign shape is signed local packs plus friend-
  instance exchange in place of a central store).
- **The Evaluation Sitting** is Volmarr's to call: never
  queued, not a matrix row, not P-219 business.

None is claimed resolved.

