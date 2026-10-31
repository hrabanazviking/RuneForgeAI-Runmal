# P-003 — The Voxta Census (2026-10-30)

*Voxta's current feature surface, feature by feature, stated as
observable behaviour in the same language as P-001's founding
audit, so P-004's delta table compares like with like. Every row
is numbered `VX-##` — P-004 cites these numbers, never a memory
of Voxta.*

## Method, sources, and the clean-room boundary

- **Sources are Voxta's official public site, its official
  public documentation, and its published release notes only** —
  the official site at `voxta.ai` (read in full on 2026-10-30),
  the official documentation at `doc.voxta.ai` (pages read in
  full on 2026-10-30: Scenarios, Events, Actions & tools,
  Buttons & controls, Contexts, Memory books, Scripting,
  Templates, Messages, Packages, HUD & stage effects), and
  Voxta's own published release notes for **v1.11.0**
  (2026-10-06, read in full), **v1.9.0** and **v1.9.3** (read in
  full). **No Voxta source code exists in public to read, and
  none was sought; no source-derived analysis was used as
  census evidence** — behaviour only, per the Two Mirrors
  clean-room law (§2 of the roadmap). Voxta is proprietary;
  that changes nothing about the boundary.
- **Version baseline:** the census reads the **v1.11 line**
  (v1.11.0, released 2026-10-06) as current, per the roadmap's
  commission, on top of the live documentation and site, which
  describe the current product. The live docs are not
  version-pinned: a behaviour attested only by the docs may
  post-date 1.11.0's notes, and such rows cite the doc page
  alone. Rows resting on a specific release's notes are marked
  `[RN-1.11]`, `[RN-1.9.0]` or `[RN-1.9.3]`; rows resting on the
  roadmap's own §1 survey are marked `[roadmap §1]` and are the
  weakest evidence in this census — P-004 should treat them as
  depth notes until read directly.
- One corroborating source is **not** official: the community
  Services overview at `voxta.axailotl.ai` (an unofficial docs
  mirror). It is cited on exactly one row (VX-15), flagged
  there, and no other row depends on it.
- Voxta is a **local server with a web interface**, not a
  hosted chat site: it installs on the user's PC, and the heavy
  models run either on the user's own hardware or on Voxta
  Cloud from the same interface [Site]. That shape — voice
  first, local first, cloud optional — is the first census
  fact, as SillyTavern's "interface, not a model" was for P-002.

## The census

### A. Platform shape, characters, and the user

| # | Feature (behaviour) | Source |
|---|---|---|
| VX-01 | **Local server + web UI, cloud optional** — installable software running on the user's own PC (Windows full app, Linux server + browser); Voxta Cloud can carry the models instead from the same interface; a free **Lite** tier runs on Voxta Cloud only with no local setup, subscriptions unlock the full local version | Site; [RN-1.11] |
| VX-02 | **Characters as the organising unit** — a character carries name, tags, description (appearance), personality, profile, and message examples as distinct fields, plus a culture that sets its language and its sense of date/time; templates and prompts are built per character from these fields | Templates |
| VX-03 | **Character assets & expressions** — a character's Assets tab holds its images; expression image assets can be generated there; **Emotes and States** (e.g. Normal, Sitting, Aggressive) work with no scenario attached | [RN-1.11] |
| VX-04 | **Voices are character equipment** — a Voices Studio and voice picker with favourites, a change-voice shortcut on the character menu, and culture filtering in the voices catalogue | [RN-1.11]; [RN-1.9.0] |
| VX-05 | **The user has an identity in the prompt** — `user` (name) and `user_description` (profile description) are template citizens; a scenario's **impersonation** can override who the user plays (name + description, e.g. "the detective"), and `{{ user }}` then renders that identity | Templates; Scenarios |
| VX-06 | **Multi-character chats** — several characters share one chat; a scenario can **share chat history with characters who were away**, so a returning character receives what it missed | Scenarios; [RN-1.11] |
| VX-07 | **Companions vs assistants are distinct kinds** — an Assistants page lists only assistants, marks the default, and can change it; companion characters carry a dedicated prompt to reduce hallucinations | [RN-1.11] |
| VX-08 | **Chat style & flow taxonomy** — every chat has a style (`Companion`, `Roleplay`, `Storytelling`, `Assistant`) and a scenario has a flow (`Chat` = normal turn-taking; `Story` = the user is excluded, the AI narrates and the user watches or triggers) | Templates; Scenarios |

### B. Voice — the core loop

| # | Feature (behaviour) | Source |
|---|---|---|
| VX-09 | **Real-time voice both ways, interruptible** — voice in, voice out, and the user can interrupt the character mid-sentence | Site |
| VX-10 | **Adaptive voice activity & turn detection** — an Adaptive VAD (rebuilt on NAudio 3, replacing a fixed RMS threshold) adapts to the room; turn detection gives the speaker headroom, a small CPU model (via LiveKit) decides end-of-turn, and filler interruptions ("yeah", "sure") are ignored rather than cutting the character off | [RN-1.9.3]; [RN-1.9.0] |
| VX-11 | **Mishearing is handled, not hidden** — characters can detect misheard words and ask the user to repeat; often-missed words are automatically replaced after transcription; the UI shows speech-to-text confidence markings | [RN-1.9.0] |
| VX-12 | **Expressive voices: prosody & affects** — voices carry emotion (anger, whispering, laughing) with proper prosody and affects, on by default for cloud LLMs; local LLMs can opt into Emotion Tags, with a benchmark for whether a model handles them; a TTS playground previews affects before committing | [RN-1.9.0] |
| VX-13 | **A narrator voice** — a scenario names a narrator voice that reads narrated events aloud; which message types are narrated is part of the message taxonomy (VX-41) | Scenarios; Messages |
| VX-14 | **Many ears** — voice-sample transcription can run through OpenAI, WhisperLive, AssemblyAI, Deepgram, or Voxta Cloud; Deepgram's service is at its Nova V3 / Flux generation in the current line | [RN-1.9.0]; [RN-1.9.3] |

### C. Services, modules, and backends

| # | Feature (behaviour) | Source |
|---|---|---|
| VX-15 | **Service-type architecture** — text generation, TTS, STT, action inference, and summarization are separately configured service slots; several services of one type can coexist under labels (e.g. a strong model for action inference, a cheaper one for conversation), and the first available fitting service is selected when none is specified | Unofficial docs mirror (corroboration only — see Method); pattern corroborated by [RN-1.11] Decisions and [RN-1.9.3] summarization services |
| VX-16 | **Local LLM backends** — llama.cpp and ExLlamaV3 are the named local engines in the current line, alongside Voxta Cloud and routed/cloud providers; prompt formatting templates are auto-detected best-effort, and structured output (GBNF/Formatron class) supports reliable tool calling and action inference on local models | [RN-1.9.0]; [RN-1.11] |
| VX-17 | **Decisions — a dedicated multiple-choice service** — a model returns an *option* instead of text for questions like who speaks next, which action to take, or whether a tool call may run, in well under a second; served via Voxta Cloud and OpenRouter's Decisions API, with a local Decisions mode for ExLlamaV3/llama.cpp; chat flow and tool-call review always use it when enabled | [RN-1.11] |
| VX-18 | **Reasoning is budgeted** — local thinking models get a reasoning budget separate from the reply-token budget, summarization services can think too, the prompt states the reply budget so the model paces itself, and reasoning controls live in the model picker | [RN-1.9.3]; [RN-1.11] |
| VX-19 | **VRAM awareness** — a VRAM estimator in the playground; estimated requirements shown for models, modules, and service tests; launching a module or chat is prevented when the estimate exceeds the GPU; a refused model load shows its VRAM breakdown | [RN-1.9.0]; [RN-1.11] |
| VX-20 | **A module system** — features arrive as installable modules with their own configuration pages; unconfigured modules are hidden, "Add features"/Add Module pages install more, and launching a character that needs an uninstalled augmentation says so and offers to install it | [RN-1.11]; Site |

### D. Memory

| # | Feature (behaviour) | Source |
|---|---|---|
| VX-21 | **Long-term memory across conversations** — the character remembers what the user told it in earlier conversations, not only inside one chat | Site |
| VX-22 | **Memory books (authored lore)** — entries of text + keywords stay inert until the recent conversation matches; the query is the **last ten messages**; entries are scored, ranked, and taken until a token budget fills, then rendered in a stable order so the prompt (and its caching) does not reshuffle each turn; an entry can be **pinned** (always recalled) and **weighted** | Memory books |
| VX-23 | **Private book & subject memory** — beyond authored books, the character fills a **private book** itself as you talk, in two kinds: **Memories** (events that happened; reached by recall) and **Understanding** (a standing model of each person — self, user, other characters — rewritten as it develops; always in the prompt). Memory is enabled per character | Memory books; [RN-1.9.0] |
| VX-24 | **Memory lifecycle is honest** — a fact that stopped being true is **superseded** (old wording stays as readable history, only the current one is recalled); a memory the Understanding now covers is **absorbed** so recall stops restating it (pinning exempts a memory); nothing is silently dropped — every entry stays visible and editable | Memory books |
| VX-25 | **Summarization feeds memory** — a hierarchical summarization system serves long chats; memories are extracted after a summarization pass and folded into the private book, with auto-correction of memory texts and weighting against frequency; chats get titles generated automatically (or on demand with `/title`) | [RN-1.9.0]; Memory books; [RN-1.9.3] |
| VX-26 | **Memory providers are pluggable** — scoring is done by a memory service: **Simple Memory** (lexical) or **Semantic Kernel** (lexical + embeddings, strongly recommended for subject memory) | Memory books; [RN-1.9.0] |
| VX-27 | **Book tooling & interop** — books attach to a character or to a scenario (a character can have several); they export as `.voxpak`, JSON, or YAML, import from Agnaistic lorebook JSON, can be **extracted from an existing chat** and **merged**; entries are editable while a chat is writing, and books carry thumbnails | Memory books; [RN-1.11] |

### E. Scenarios — the structured-experience engine

| # | Feature (behaviour) | Source |
|---|---|---|
| VX-28 | **The scenario as a unit** — a scenario defines the situation: where the characters are, who else is around, what fires when, what the AI should know, and what the host app should do; its editor has Overview, Scenario, Roles, Apps, Scripts, Interactions, Impersonation, Assets, and Package tabs; casual chats need no scenario | Scenarios |
| VX-29 | **Scenario core settings** — chat flow, chat style (which narrows which actions and tools are offered), a scenario template, bootstrap messages, a system-prompt override, bound memory books, a narrator, and initial flags | Scenarios |
| VX-30 | **Scenario template & system prompt** — a Scriban template can override the character's own scenario field, and the system prompt can be replaced or extended per scenario | Scenarios |
| VX-31 | **Roles are named slots** — templates and scripts reference characters by role (`{{ char }}` = first role; `{{ scenario_chars.role }}` = a specific role), never by name; a role can be disabled on start and enabled later by script (`setRoleEnabled`), or kept present but silent (`setCharacterCanSpeak`) | Scenarios |
| VX-32 | **Bootstrap messages** — how a chat opens is authored as a Scriban block where each line produces one typed message (character, user, role, event, note, secret, instructions); ending on a user line makes the chat wait for the user | Scenarios; Messages |
| VX-33 | **Parent scenarios** — a scenario can inherit from a parent; the parent's scripts are reachable under `../base/`, so a family of scenarios shares a library, a HUD, or a set of interactions | Scenarios |
| VX-34 | **Flags & variables are the state store** — flags are on/off state that conditions filter on; `chat.variables` hold values, persist with the chat, and survive resume; conditions can compare variables via `$name` | Scripting; Actions & tools |
| VX-35 | **Events fire on their own** — scripted beats evaluated after user / before assistant / after assistant / after any message, or manually; triggers are OR'd windows anchored to chat start, a flag, or another event, measured in messages and/or chat-time seconds, with a probability that ramps across the window and per-trigger and per-event max-fires caps (empty = cyclic); an event can let the next event evaluate in the same pass | Events |
| VX-36 | **Actions vs tools — one object, two deciders** — an **action** is chosen by a dedicated inference pass at a named timing (a classification: mood, gesture, room change); a **tool** is chosen by the character itself mid-reply and sees its result before finishing its sentence; the two modes are exclusive per object | Actions & tools |
| VX-37 | **Action layers, arguments & conditions** — actions group into mutually exclusive **layers** (one fire per layer per turn; each layer is a separate inference pass; a final layer stops later layers; an action can activate others); actions/tools declare typed arguments (`string/integer/double/boolean/array/void`, `required`, closed `choices` sets); conditions filter by flags, a regex match on the triggering message, role, once-only, chat styles, or disabled | Actions & tools |
| VX-38 | **Effects & display** — a fired action/tool/button/event can set flags, inject a note/secret/instructions/event/story message, trigger another event, add contexts, run a script, or cancel the reply being generated; a tool answers by returning `{ result }` (non-strings as JSON); how much chrome a call shows is chosen per call: card, pill, minimal, or hidden (failures and pending approvals always show) | Actions & tools; Events |
| VX-39 | **Buttons & controls are player input** — buttons appear during chat (conditionally, greyed rather than hidden under a disabled flag filter), run effects on press, have templated labels that re-render when watched variables change, and can be registered at runtime; **controls** (toggle/checkbox/slider) bind two-way to chat variables; **pinned HUD widgets** each watch one variable at an authored stage position | Buttons & controls |
| VX-40 | **Contexts ground the scene** — a context is a short conditional sentence injected into the prompt just before the character's reply (pose, mood, environmental fact), with a flag/`$variable` condition, a role filter, and a declared prompt position; contexts can be set at runtime by key, and a test-flags field shows which would activate | Contexts |
| VX-41 | **A typed message taxonomy** — char / user / role / event (narrated, triggers reply) / story (story-writer-generated, narrated) / note (both see, no reply) / secret (AI only) / instructions (user only) / `/noreply` / `/infer`, plus a full-control `/message` command (role, character, caps, reply/narrate switches); injected messages can **expire from the prompt after N turns** while staying visible in the chat explorer; Summary and Tool are system-produced roles, tool results never stored as messages | Messages |
| VX-42 | **JavaScript scripting, sandboxed** — scenario scripts are ES modules: handlers `export trigger` for the interaction they hang on, and an init (`index`) script registering listeners for chat lifecycle moments; timers run on chat time; the sandbox allows no host interop, `eval`, network, or filesystem (only `@voxta`, `@voxta/utils`, and sibling files), with recursion/statement/regex/promise caps so a runaway script becomes a script error, not a server crash | Scripting |
| VX-43 | **Scriban templates everywhere** — character, scenario, context, button, and bootstrap fields are templates over user/char/chars/role maps, scenario text, flags, variables, resolved contexts, the last vision description, and `now` (only for time-aware characters, floored to 15-minute buckets to protect prompt caching), with `has_flag` / `char_has_tag` functions; the prompt preview shows what actually resolved | Templates |
| VX-44 | **Apps are configured per scenario** — the Apps tab holds per-host-app configuration (background, default view, and whatever the host app declares), and scripts drive the host through app triggers (VX-46) | Scenarios |

### F. Stage, faces, and vision

| # | Feature (behaviour) | Source |
|---|---|---|
| VX-45 | **Visual-novel play** — a written character + scenario plays out as a visual novel with voices and generated images, from built-in scenarios or the user's own | Site |
| VX-46 | **HUD & stage effects** — script-driven app triggers turn the stage into a game screen: a HUD of typed sections (`bars`, `chips`, inventory `grid` with prices, `checklist`, footer `badge`), spawnable windows/panels, splash banners, modal notices and choices, screen effects (flash/glow/shake/blur/fade, sticky vignette/tint/daze), floating text and impact bursts, and per-character sprite effects; HUD state is player-only — none of it reaches the AI unless a context or note says it | HUD & stage effects |
| VX-47 | **Clickable maps, inventories, HUD widgets** — scenario play surfaces are clickable and scriptable, including item context menus on HUD/panel items that fire script events | Site; HUD & stage effects |
| VX-48 | **Portrait animation** — a character's still picture speaks along with its voice, driven by the new Ditto module, drawn in the app and testable from the service tests with a voice | [RN-1.11] |
| VX-49 | **Video & 3D avatars** — MP4/AVIF video avatars are part of the surface; VRM rendering is capped at 60 fps and the desktop VRM popout carries mic/voice toggles, resize, a lock button, and a saved position | [roadmap §1]; [RN-1.11] |
| VX-50 | **Vision on request** — the character can look at the user's screen or a photo when asked (a folder-watcher is also part of the surveyed surface); the last vision description is a template variable; the mobile vision playground is a step-by-step flow that opens the real camera; screen capture is one of the Windows-only features absent on Linux | Site; Templates; [RN-1.11]; [roadmap §1] |

### G. Image and video generation

| # | Feature (behaviour) | Source |
|---|---|---|
| VX-51 | **Image generation in the companion** — images are generated from inside chats and scenarios, locally or in the cloud; `/imagine` has a sprint mode for native-transparency output on supporting backends; generated images default to the character's avatar | Site; [RN-1.11] |
| VX-52 | **Video generation** — WAN 2.2 video generation inside Voxta; XAI and ComfyUI backends in the playground; the image viewer can edit any image with a prompt or turn it into a video; video supports cropping and resumable jobs | [RN-1.11]; [RN-1.9.0] |
| VX-53 | **Generation plumbing depth** — ComfyCloud supports img2img, video, workflow upload, and LoRA panels; Local Diffusers supports named current models with reduced memory under LoRAs; a dedicated **Upscaler** module (Spandrel/chaiNNer/ESRGAN class) and Voxta Cloud background-removal/upscaling services exist; image models and LoRAs show Civitai preview thumbnails | [RN-1.11] |

### H. Workspaces and the assistant that works

| # | Feature (behaviour) | Source |
|---|---|---|
| VX-54 | **Workspaces bind a chat to a real folder** — the AI reads, writes, and edits files in it, runs commands, and launches programs; the Work page starts/resumes workspace work with the folder chosen before the chat; a files browser in the right panel edits/deletes text files and views images | [RN-1.11] |
| VX-55 | **Coding-agent backends are built in** — Claude Code and OpenAI Codex run real coding work from a workspace; Claude Code has a tool-call permissions system, persistent memory across sessions, and a native harness; tool calls and their permissions render in the UI and are saved in the chat history | Site; [RN-1.9.3] |
| VX-56 | **Assistant tooling breadth** — shell commands (Bash and PowerShell) and a Python tool for assistants, web search, MCP tools, and the user's own scripts | [RN-1.11]; Site |
| VX-57 | **Tool calling got a security pass** — under Allow All, destructive calls are reviewed before running; calls are screened by what they actually read/write, secret reads the path rules missed are flagged; web fetch checks allow/deny lists and inspects redirect chains; tools can be granted/revoked ahead of time; API keys carry scopes and device sign-in asks only for the scopes it needs; tunnelled requests count as remote | [RN-1.11] |
| VX-58 | **Done means told** — an assistant finishing can fire a notification integrated with Windows and Android notifications | [RN-1.11] |

### I. The Hub, packages, and content custody

| # | Feature (behaviour) | Source |
|---|---|---|
| VX-59 | **The Content Hub** — browse, search, and install characters, scenarios, and packs from inside the app (and on the web at the Hub site), with creator profiles; share your own with the community; the module configuration chooses which kinds of content are allowed | [RN-1.11]; Site |
| VX-60 | **Content packages (`.voxpak`)** — one file bundles scenarios, characters, memory books, collections, and their assets (assets only travel inside a package); a resource belongs to one package at a time and deleting a package deletes its contents; `.voxpak` is a served-in-place container (a huge pack imports at no disk cost), the only format that can be encrypted or carry protected assets; **Publish** produces a protected, encrypted pack whose assets can be used but not re-exported (PNG/ZIP export disabled for it); `.png` serves Virt-A-Mate scenes, `.zip` is for inspection, legacy `.voxpkg`/`.vxz` still import | Packages |
| VX-61 | **Chats travel as packs too** — chats export as voxpak including generated images, with dependency support: importing a pack with missing dependencies warns | [RN-1.9.3] |

### J. Clients, accounts, inspector, and extensibility

| # | Feature (behaviour) | Source |
|---|---|---|
| VX-62 | **Clients** — Windows 10/11 full desktop app (recommended); Linux server + browser with a few Windows-only features absent; Android companion app for subscribers, paired to the PC by QR code; no macOS or iOS app | Site; [RN-1.11] |
| VX-63 | **The web UI is phone-shaped** — the whole web UI was reworked for phones: master-detail drawers, cards instead of tables, bottom sheets, step-by-step playground flows for vision/TTS/STT | [RN-1.11] |
| VX-64 | **Shared accounts** — several people can use one account, each with their own sign-in, when Users Management is enabled | [RN-1.11] |
| VX-65 | **The chat Inspector** — a per-chat inspector carries the script log and a code-snippet browser, with Flags and Contexts views beside it to answer "why didn't that fire?"; tool calls hidden from the transcript are still recorded and visible in the inspector | Scripting; Actions & tools |
| VX-66 | **An open extension surface** — a C# SDK on NuGet (the model library targets .NET Standard 2.1 for Unity), Python modules, MCP servers, JavaScript scripting, and an open API; the SDK carries workspaces support, ticket-based WebSocket authentication, a tool-calling control API, and API-key scopes | Site; [RN-1.11] |
| VX-67 | **Games, apps, and bots** — characters connect into games and apps the user plays; a **Discord bot** puts a character in Discord channels (a character and scenario per channel, a cost limit per channel) built on bot sessions (Chat Bridges) | Site; [RN-1.11] |

## Version note (not inventory)

The roadmap's §1 survey also names, for the v1.11 line: an
**Assistant view** (GPT-style, reasoning models with visible
thinking) and fuller **Inspector** coverage (events/actions/
flags debugging) than the doc pages read here spell out. VX-65
records only what the Scripting and Actions pages themselves
attest (script log, flags/contexts views, hidden-call records);
the Assistant-view shape and the Inspector's full event/action
surface should be read directly before P-004 weighs them, and
are recorded here as surveyed-but-not-yet-read, not as rows.

## What P-003 hands onward

- To P-004: rows VX-01–VX-67 are the Voxta half of the delta
  table's rows. A HAVE claim against any row must cite a P-001
  row; Voxta's centre of gravity is exactly where Rúnmál's
  founding road is thinnest — scriptable scenarios (VX-28–
  VX-44), stage/HUD play (VX-45–VX-47), workspaces (VX-54–
  VX-58), and the Hub (VX-59) — so HAVE-THIN and MISSING will
  concentrate there, and the sovereign-shape rows (the Hub
  above all) are where DELIBERATELY-DIFFERENT belongs.
- To P-010: VX-12, VX-14, and VX-15–VX-20 are the input ledger
  for the voice-provider census — Voxta's provider breadth
  (many pluggable STT/TTS services, local or cloud) is the
  widest single surface in this census.
- To P-026: VX-28–VX-44 plus VX-60 are the shape a
  Voxta-scenario interop slice must map from — structure and
  behaviour attested here, format details to be read from
  public specs at that slice, never from the product's code.
- To P-012: the source list in the Method section is this
  census's entry in the clean-room log — official site, public
  docs, and published release notes only, one flagged
  unofficial corroboration, no source code.
