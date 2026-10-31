# P-002 — The SillyTavern Census (2026-10-30)

*SillyTavern's current feature surface, feature by feature, stated
as observable behaviour in the same language as P-001's founding
audit, so P-004's delta table compares like with like. Every row is
numbered `ST-##` — P-004 cites these numbers, never a memory of
SillyTavern.*

## Method, sources, and the clean-room boundary

- **Sources are public documentation and release notes only** —
  the official documentation at `docs.sillytavern.app` (pages read
  in full on 2026-10-30: What is SillyTavern, Characters, Personas,
  Group Chats, World Info, Prompt Manager, Context Template,
  Advanced Formatting, Chatting, Chat Completions, User Settings,
  Regex, Summarize, Writing Extensions) and the project's published
  release notes (the 1.13.0 notes read in full; the current release
  line corroborated below). **No SillyTavern source code was read,
  and no source-derived analysis (e.g. code-wiki summaries of its
  repository) was used as census evidence** — behaviour only, per
  the Two Mirrors clean-room law (§2 of the roadmap).
- **Version baseline:** the census reads the **1.19 release line**
  (1.19.0, released 2026-09-14) as current — that version is
  corroborated by multiple independent October-2026 guides citing
  the official release notes and by the project's official
  container image tag — on top of the live documentation, which
  describes the current release. The `staging` branch moves faster
  than the release line and is **not** the baseline; where the
  1.13.0 release notes are the newest full notes read, the row is
  marked `[RN-1.13]` and the behaviour is also present in the live
  docs unless noted. Items reported for 1.19 itself (a side-by-side
  swipe picker, improved World Info sorting) rest on secondary
  guides citing the release notes and are recorded in the version
  note at the end, **not** as inventory rows.
- SillyTavern is an interface, not a model: it supplies no
  inference of its own and requires a connected backend [What-is].
  That shape — not any single feature — is the first census fact.

## The census

### A. Characters, personas, groups

| # | Feature (behaviour) | Source |
|---|---|---|
| ST-01 | **Character cards as the organising unit** — a character is a named bundle of prompt fields (description, personality, scenario, first message, example dialogue) with an avatar; unlimited characters, switchable at any time, usable solo or in groups | Characters; What-is |
| ST-02 | **Card import** from file, plus **External Import** from a URL; cards are PNG-embedded or JSON, on the Character Card v2 spec with v3 data read when present (v3 additions per the public spec, cf. founding RESEARCH.md) | Characters; roadmap §1 |
| ST-03 | **Character management at library scale** — search by name/attributes; sort alphabetically, chronologically, by usage (recent / most / least chats), by size (token count), favourites, random; filter by favourites, groups, and **tags organised as folders** with a tag manager | Characters |
| ST-04 | **Card editing depth** — token count per card, chat/usage statistics, favourite toggle, export, duplicate, delete, gallery view of a character's images | Characters |
| ST-05 | **Extended card operations** — link World Info to the card, import a card's embedded lore, scenario override for a chat, convert character ↔ persona, rename (with lorebook relinking offered on lorebook rename), record a source link, replace/update an existing card, import tags | Characters; World Info |
| ST-06 | **Advanced definitions** — per-card prompt overrides (main prompt with `{{original}}`, post-history instructions), creator metadata (creator, version, creator's notes, embedded tags — none of it prompt material by default), character's note injected at a selectable depth and role, talkativeness slider for groups, example messages | Characters |
| ST-07 | **Alternate greetings** — multiple first messages per card, swiped between when a chat starts | Characters |
| ST-08 | **Personas** — the user's own identities: name + avatar + description text (macros allowed), switchable mid-chat without re-attributing past user messages; batch re-attribution ("sync") on request | Personas |
| ST-09 | **Persona description positions** — per persona: disabled, in story string / prompt manager, top/bottom of Author's Note, or in-chat at a chosen depth and role | Personas |
| ST-10 | **Persona connections / locking** — a persona can be locked to a chat, locked to a character, or set as the single default; temporary (session-only) persona override; multiple personas per character with a picker on chat open (opt-in setting); persona list backup/restore | Personas |
| ST-11 | **Group chats** — multiple characters in one shared-history conversation; members can be added, removed, muted, re-ordered; a particular member can be force-triggered even while muted | Group Chats |
| ST-12 | **Group reply-order strategies** — Manual (user picks, or `/trigger`), Natural Order (name mentions in the last message, then talkativeness probability, then random), List Order, Pooled Order (one random member who has not spoken since the last user message) | Group Chats |
| ST-13 | **Group generation handling** — Swap character cards (only the speaker's card is in context) or Join character cards (all members' description/scenario/personality/examples/notes combined in list order, with include/exclude-muted sub-modes and join prefix/suffix templates) | Group Chats |
| ST-14 | **Group extras** — auto-mode (members keep replying on a delay until the user types), self-response allowance for Natural Order, a group-wide scenario override inherited by branched chats, peek/edit a member's card from inside the group | Group Chats |

### B. World Info (lorebooks)

| # | Feature (behaviour) | Source |
|---|---|---|
| ST-15 | **Keyword-triggered entries** — an entry's content is inserted into the prompt only when its keys appear in scanned context; keys are case-insensitive and whole-word by default (both overridable globally and per entry), and a key may itself be a regex (macros resolvable inside it, per-message matching against a name-prefixed scan buffer) | World Info |
| ST-16 | **Selective logic** — an optional filter key list combined with the primary key as AND ANY / AND ALL / NOT ANY / NOT ALL | World Info |
| ST-17 | **Entry strategies** — constant (always inserted), keyword-triggered, or **vectorised** (inserted by embedding similarity via the Vector Storage extension, subject to all other checks; a per-extension max-entries cap applies) | World Info |
| ST-18 | **Insertion positions** — before/after character definitions, before/after example messages (parsed as example blocks), top/bottom of Author's Note, at a chosen in-chat depth with a chosen role (system/user/assistant), or **Outlet** (not auto-injected; pulled in by a `{{outlet::Name}}` macro, entries sharing a name combined in insertion order) | World Info |
| ST-19 | **Probability (Trigger %)** — an activated entry is inserted only with the stated probability | World Info |
| ST-20 | **Inclusion groups** — simultaneously triggered entries sharing a group label compete: exactly one is inserted, chosen by group weight, by deterministic priority (highest insertion order) when Prioritize Inclusion is set, or narrowed first by **group scoring** (most key matches wins the subset) | World Info |
| ST-21 | **Timed effects** — per entry, measured in messages and scoped to the chat (branches inherit): **sticky** (stays active N messages, ignoring probability while stuck), **cooldown** (cannot re-activate for N messages after activation), **delay** (cannot activate until the chat has at least N messages); editing an entry clears its active effect; re-triggering does not refresh a running effect | World Info |
| ST-22 | **Recursive scanning** — activated entries' content is itself scanned, so entries trigger entries; per-entry controls: non-recursable, prevent-further-recursion, delay-until-recursion with recursion levels; global max recursion steps | World Info |
| ST-23 | **Scan configuration** — scan depth in messages (per book, overridable per entry; 0 = only recursed entries and Author's Note), participant names includable in the scan buffer, **Min Activations** (scan deeper, up to Max Depth, until N entries have triggered; mutually exclusive with Max Recursion Steps) | World Info |
| ST-24 | **Token budget** — World Info as a whole is capped by a context-% or an absolute token budget; when exhausted, no further entries activate; constants insert first, then higher insertion order, direct mentions before recursively triggered ones | World Info |
| ST-25 | **Four lore scopes, layered** — global selector, character lore (primary book embeds into the exported card; additional books linkable), persona lore, chat lore; combined under a chosen insertion strategy (sorted evenly / character first / global first), chat and persona lore ahead of both | World Info |
| ST-26 | **Per-entry gating extras** — character filter (allow-list or exclude mode, by name or tag), generation-type triggers (normal / continue / impersonate / swipe / regenerate / quiet), and additional matching sources (character description, personality, scenario, persona description, character's note, creator's notes can all be scanned for keys) | World Info |
| ST-27 | **Automation ID** — an entry can carry an ID that runs the matching STscript/Quick Reply command when the entry activates (once per ID per generation) | World Info |

### C. Prompt construction and sampling

| # | Feature (behaviour) | Source |
|---|---|---|
| ST-28 | **Prompt Manager (Chat Completion)** — the outgoing prompt is an ordered, drag-and-drop list of named prompt blocks, each editable with a role (system/assistant/user), generation-type triggers, and a position: relative in the list, or in-chat at a chosen depth with an order among same-depth prompts; presets carry their own prompt sets, insertable from a dropdown | Prompt Manager |
| ST-29 | **Prompt Manager utility surface** — quick-edit of main prompt, auxiliary prompt and post-history instructions; format templates wrapping World Info / scenario / personality; group nudge, continue nudge, new-chat / new-group / new-example markers; character-names behaviour strategies; squash consecutive system messages; wrap user message in quotes; continue prefill as an assistant message; a system-prompt mode that merges leading system messages into the backend's system field | Prompt Manager |
| ST-30 | **Reasoning controls** — for reasoning models: a visibility toggle for returned reasoning and a separate Reasoning Effort control for the request (the 1.13 notes record the split of these two concerns as a breaking change) | Prompt Manager; [RN-1.13] |
| ST-31 | **Advanced Formatting (Text Completion)** — system prompt templates, context templates, instruct templates, tokenizer choice, and custom stopping strings as separately saveable/resettable template files; templates can be **derived automatically** from a backend-reported model chat-template hash (llama.cpp / KoboldCpp) | Advanced Formatting |
| ST-32 | **Context Template / story string** — a Handlebars template assembling the preamble from named anchors (system, character fields, World Info before/after, example dialogues raw or formatted, extension anchors for Author's Note, summaries, Data Bank/vectorisation, STscript, web search), placeable at the prompt start or in-chat at a depth, with example separators, chat-start separator, and separators optionally acting as stop strings | Context Template |
| ST-33 | **Instruct templates** — per-model input/output/system sequence formats for instruction-tuned text-completion models (the Alpaca / ChatML / Llama-3 class of shapes), selectable per preset | Advanced Formatting; roadmap §1 |
| ST-34 | **Presets** — named, shareable JSON bundles per API type carrying sampler settings plus prompt/template configuration; community presets are a primary way users configure behaviour | Prompt Manager; What-is |
| ST-35 | **Sampler surface** — temperature, top-p/top-k, min-p, repetition/presence/frequency penalties, DRY- and XTC-class samplers where the backend supports them, with backend-specific support and ordering (per-backend differences are documented behaviour, e.g. the 1.12.5 notes adding min-p + penalties for one source); unsupported parameters are a per-backend fact, not a UI promise | roadmap §1; release notes |
| ST-36 | **Macros** — `{{char}}`, `{{user}}`, `{{original}}`, `{{outlet::…}}`, chat-start/separator macros and a wider documented macro set substituted across prompts, cards, personas and templates | Prompt Manager; Context Template; Personas |
| ST-37 | **Author's Note** — a per-chat instruction block inserted at a chosen depth and frequency, doubling as an anchor position for persona text and World Info entries | Chatting; World Info; Personas |
| ST-38 | **Post-history instructions** — a prompt block placed after the chat history (system prompt settings for Text Completion; a Prompt Manager citizen and per-card override for Chat Completion) | Prompt Manager; Characters; [RN-1.13] |
| ST-39 | **Multimodal and tool toggles (Chat Completion)** — send inline images / inline videos to capable models, request inline images back, backend-provided web search, and function calling, each as prompt-level settings | Prompt Manager |
| ST-40 | **Token probabilities viewer** — for the most recent message, on backends that report them: click any token to see the alternatives and their probabilities, pick an alternative to regenerate from that point (reroll semantics documented per paradigm); not saved to the chat, unavailable with smooth streaming | Chatting |

### D. Backends and connections

| # | Feature (behaviour) | Source |
|---|---|---|
| ST-41 | **Two API paradigms** — Chat Completion (structured role messages) and Text Completion (single assembled prompt string), each with its own settings, presets and templates | Chat Completions; Advanced Formatting |
| ST-42 | **Chat Completion sources** — OpenAI, Claude, Google AI Studio, Google Vertex AI (Express mode, added in the 1.13 notes), Mistral AI, DeepSeek, AI21, Cohere, Perplexity, Fireworks AI, Electron Hub, OpenRouter-class routers, and a **Custom (OpenAI-compatible)** endpoint (model list pulled from `/v1/models` when the endpoint offers it) | Chat Completions; [RN-1.13] |
| ST-43 | **Text Completion backends** — llama.cpp, Text Generation WebUI (oobabooga), TabbyAPI, KoboldCpp, NovelAI, Ollama, AI Horde and peers, with per-backend template derivation and token-probability support varying by backend | Chatting; Advanced Formatting |
| ST-44 | **AI Horde out of the box** — a free, shared inference pool usable with no account or key, as the zero-setup first connection | What-is |
| ST-45 | **Per-source secrets** — an API key per connection source, held by the server side, never part of character/chat data | Chat Completions |

### E. Chat surgery

| # | Feature (behaviour) | Source |
|---|---|---|
| ST-46 | **Swipes** — alternate generations kept on a message and navigated in place; alternate greetings are the same mechanism at chat start | Chatting; Characters |
| ST-47 | **Message editing with movement** — edit any message's content in place; copy, delete, move up/down within the chat from the edit panel | Chatting |
| ST-48 | **Branches** — start an alternate story path from any message (a message action); the branch is its own chat, linked back to its parent ("Back to parent chat") | Chatting |
| ST-49 | **Checkpoints** — a named story checkpoint created from a message or the chat options; clicking opens the checkpoint chat, shift-click updates the existing checkpoint | Chatting |
| ST-50 | **Message inclusion toggle** — any message can be excluded from what the model sees without deleting it, and re-included | Chatting |
| ST-51 | **Continue** — extend the last message (with a configurable nudge prompt and postfix, optionally as an assistant prefill) | Chatting; Prompt Manager |
| ST-52 | **Impersonate** — the model drafts the *user's* next message | Chatting |
| ST-53 | **Regenerate** — discard and re-roll the last reply (a distinct generation type that prompts, lore and triggers can key on) | Chatting; Prompt Manager |
| ST-54 | **Chat file management** — import, export and rename chat files; a temporary (unsaved) chat can be restored by importing its saved file; chats convert to group chats in place | Chatting; [RN-1.13] |
| ST-55 | **Welcome screen + Assistant** — a redesigned welcome screen with recent chats, quick uncarded chat (temporary, unsaved), and a permanent Assistant character (any character can be set as the default Assistant) | [RN-1.13]; What-is |
| ST-56 | **Per-message utility actions** — translate this message, generate an image from it, narrate it (TTS), view the exact generation prompt and token usage for it, embed/attach files or images to it | Chatting |

### F. The extensions row

| # | Feature (behaviour) | Source |
|---|---|---|
| ST-57 | **Extension system (UI extensions + server plugins)** — third-party extensions hook events and APIs in the browser context and can add settings panels and persistent settings; server plugins extend the Node server; an official "Download Extensions & Assets" channel distributes them; installation supports choosing a branch [RN-1.13] | Writing Extensions; What-is; [RN-1.13] |
| ST-58 | **Summarize (built-in extension)** — automatically generated, user-editable rolling chat summary stored in the chat file's metadata and injected by template (`{{summary}}`); summary sources: the main API (classic prompt builder, or raw blocking / raw non-blocking modes), with message-count and buffer controls | Summarize |
| ST-59 | **Vector Storage / RAG (built-in extension)** — embedding-based retrieval over chat history, Data Bank files and World Info entries (see ST-17), from multiple embedding sources | World Info; What-is |
| ST-60 | **Data Bank** — documents attached per chat or globally for the model to reference, with extension-registered **scrapers** that import content from custom sources (web pages, APIs, file formats) | Writing Extensions; What-is |
| ST-61 | **Image generation (extension)** — generate images from scene/message content through external image engines, invoked per message or by command | What-is; Chatting |
| ST-62 | **Text-to-speech (extension)** — narrate replies through pluggable TTS voice services; per-message narration from the message actions | What-is; Chatting |
| ST-63 | **Speech recognition** — voice input to the chat bar through a speech-to-text service (part of the documented extension surface) | roadmap §1 |
| ST-64 | **Chat translation (extension)** — automatic UI-and-chat translation of messages, distinct from the UI language setting | User Settings; What-is |
| ST-65 | **Expressions / sprites (extension)** — characters display emotion-classified sprite expressions; Visual Novel mode presents chats with sprites | What-is; User Settings |
| ST-66 | **Web search (extension + backend tool)** — opt-in enrichment of prompts with live search results, as an extension and, on supporting Chat Completion backends, as a provider tool | What-is; Prompt Manager |
| ST-67 | **Regex (built-in extension)** — named find/replace scripts, global or per-character, applied at declared stages of chat text, with a test mode, macro resolution inside patterns, and triggering from Quick Replies / STscript | Regex |
| ST-68 | **Quick Replies + STscript + slash commands** — user-defined buttons that send text or run scripts; an extensive slash-command subsystem and its own scripting language (STscript) with variables, closures and automation hooks (World Info Automation IDs, generation-type triggers); commands exist for personas, groups, lore and most features above | World Info; Regex; What-is; Personas; Group Chats |

### G. Interface, accounts, data custody

| # | Feature (behaviour) | Source |
|---|---|---|
| ST-69 | **Theme and UI customisation** — theme colours, background images (including video backgrounds converted to animated WebP via a converter extension [RN-1.13]), custom CSS, avatar styles, a movable/resizable UI (MovingUI), Visual Novel mode | User Settings; What-is; [RN-1.13] |
| ST-70 | **Localised interface** — the UI itself is available in multiple languages (separate from chat translation) | User Settings |
| ST-71 | **User accounts (multi-user mode)** — per-user isolated data on one server, profile display name/avatar, password management, user roles/permissions in multi-user setups | User Settings |
| ST-72 | **Full user-data backup** — download a complete backup of all of a user's data from the account dialog | User Settings |
| ST-73 | **Clean-up tool** — scans for and removes orphaned files, images, chats of deleted characters, and stale chat backups, with per-category risk warnings | User Settings |
| ST-74 | **Token accounting surfaces** — per-character token counts, per-message prompt/token-usage view, token-probability inspection (ST-40) | Characters; Chatting |

## Version note (not inventory)

Independent October-2026 guides that cite the official 1.19.0
release notes report, for 1.19 itself: a side-by-side **swipe
picker**, improved **World Info sorting**, new model-list additions
on several Chat Completion sources, and provider errors returned
with HTTP 200 now surfacing the provider's own error text. These
are refinements of ST-46, ST-24/25, ST-42 and ST-45 respectively,
not new feature areas; P-004 should treat them as depth notes on
those rows until the 1.19 notes are read directly.

## What P-002 hands onward

- To P-004: rows ST-01–ST-74 are the SillyTavern half of the delta
  table's rows. A HAVE claim against any row must cite a P-001 row;
  depth differences inside a row (e.g. ST-20 group scoring, ST-27
  automation IDs, ST-40 token probabilities) are exactly what
  HAVE-THIN exists for.
- To P-008: ST-41–ST-45 are the input ledger for the backend parity
  slice — the mirror's backend breadth is the widest single
  surface in this census.
- To P-012: the source list in the Method section is this census's
  entry in the clean-room log — public docs and release notes
  only, no source code, no source-derived analysis.
