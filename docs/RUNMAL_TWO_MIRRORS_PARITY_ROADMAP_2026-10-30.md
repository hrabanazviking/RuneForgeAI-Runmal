# Rúnmál — The Two Mirrors

*A clean-room parity roadmap: every feature SillyTavern and Voxta have,
rebuilt the Rúnmál way — studied as behaviour, never copied as code —
until Volmarr's own chat hall stands feature-whole beside both mirrors
and sovereign above them.*

Commissioned by Volmarr, 2026-10-30 ("continue all correct roadmaps for
this project, and also add an additional roadmap that clean room adds
all features that Voxta and SillyTavern has"). Governing repo:
`hrabanazviking/RuneForgeAI-Runmal`. This roadmap stands **after** the
founding 94-slice roadmap (complete 2026-10-13) and builds only the
deltas — what the two mirrors have that Rúnmál does not yet, plus the
depth where Rúnmál has the feature but not yet its full strength.

---

## 1. What stands today (measured, 2026-10-30)

- **The founding road is complete: 94/94 slices** (Campaigns I–VIII:
  foundation, backends, living memory, real-time voice loop, bridge
  APIs, Aesir cutover, sovereignty) **plus an extra UI campaign**,
  laptop-verified on purplelongship; the last full evidence run read
  **686 passed, 3 skipped** (`538c918`). The `.runmal` portable
  archive, staged restore, migration harness, `runmal doctor`, the
  self-hosted platform matrix, and the sovereign resurrection test all
  exist. **The Windows leg of the matrix is recorded not run** — by
  Volmarr's ruling no Windows machine will be rented; hosted CI was
  abandoned by the same ruling ("test it yourself").
- **The founding design already carries the SillyTavern shape** —
  personas, lorebooks, RAG, prompt composition (`docs/PROMPT_COMPOSER.md`),
  memory architecture, multi-backend TTS/STT ADRs, bridges (VRChat
  OSC, Skyrim, Conan) — because Rúnmál was *born* as a clean-room
  study of SillyTavern. Voxta was not part of the founding study; its
  surface (voice-first companions, scenarios, workspaces, the Hub) is
  the genuinely new territory.
- **The mirrors as they stand in October 2026** (census sources:
  Voxta's own site + v1.11.0 release notes, October 2026; SillyTavern's
  current release line and docs):
  - **SillyTavern** — character cards (v2/v3 spec), personas, world
    info with recursive scanning, selective logic, timed effects and
    token budgets; group chats; a deep prompt manager (instruct +
    context templates, advanced formatting); per-backend sampler
    presets; swipes, branches, checkpoints; regex scripts; Quick
    Replies; an extension row (long-term memory summarisation, vector
    storage, translation, image generation, TTS/STT, web search);
    a data bank; secrets management; heavy theme/UI customisation.
  - **Voxta (v1.11)** — real-time voice with mid-sentence
    interruption; many pluggable STT/TTS services, local or cloud;
    long-term memory; vision on request (screen, photo, webcam,
    folder-watcher); characters and **scriptable scenarios** (events,
    flags, variables, app triggers — backgrounds, avatars, music,
    ambient layers); visual-novel play with generated images,
    clickable maps, inventories, HUD widgets; **portrait animation**
    and MP4/AVIF video avatars; expression generation; image and
    video generation; **Workspaces** (a chat bound to a real folder,
    file tools, coding-agent backends); an **Assistant view**
    (GPT-style, reasoning models with visible thinking); an
    **Inspector** (events/actions/flags debugging); a **Content Hub**
    (browse/install/share characters, scenarios, packs; creator
    profiles); a module system + API; game integrations and a Discord
    bot; Windows/Linux/Android/browser clients.

## 2. The clean-room law (unchanged, restated for this road)

1. **Behaviour is studied; code is never read.** Features are learned
   from public docs, release notes, user guides, and using the
   products — never from their source. SillyTavern's AGPL never
   touches this repo; Voxta is proprietary and equally untouched.
2. **Interop formats are specifications, not code.** Character-card
   and lorebook file formats are implemented from their public spec
   documents so users' own content can move — a user's cards are the
   user's property.
3. **Every mirrored feature is rebuilt the Rúnmál way**: local-first,
   Aesir-ready, licence-clean (the founding TTS survey's discipline —
   no GPL-tainted engines), honest capability reporting.
4. **Where a mirror's feature depends on a cloud or a store, Rúnmál
   builds the sovereign shape instead** (the Hub becomes signed local
   packs + friend-instance exchange; cloud voices become pluggable
   providers with local defaults) — and the parity matrix (Part XIV)
   says plainly which shape shipped.

## 3. Shape of the whole

Fourteen parts, **232 slices**, prefix **P-**.

| Part | Name | Slices |
|---|---|---|
| I | The Delta Census — prove what is actually missing | P-001 – P-014 |
| II | Cards & Content Interop | P-015 – P-030 |
| III | Lorebook Depth | P-031 – P-048 |
| IV | Prompt & Sampler Depth | P-049 – P-064 |
| V | Chat Surgery | P-065 – P-080 |
| VI | The Extensions Row | P-081 – P-100 |
| VII | Voice, the Voxta Way | P-101 – P-116 |
| VIII | Vision Services | P-117 – P-130 |
| IX | Scenarios — the Visual Novel Engine | P-131 – P-154 |
| X | Faces That Speak | P-155 – P-168 |
| XI | Workspaces — the Companion That Works | P-169 – P-186 |
| XII | The Hub, Sovereign Shape | P-187 – P-202 |
| XIII | Assistant View, Inspector & Bots | P-203 – P-218 |
| XIV | The Proof Spine — the parity matrix, published | P-219 – P-232 |

---

## Part I — The Delta Census (P-001 – P-014)

*Goal: no slice in this road builds on a guess. Every claimed gap is
verified against Rúnmál's actual tree and the mirrors' actual current
behaviour, and every "we already have it" is proven, not remembered.*

- **P-001** The founding audit: Rúnmál's feature inventory from its own
  tree (94 slices + extra UI campaign), each feature stated as
  behaviour with its proving test named.
- **P-002** The SillyTavern census: its current feature surface from
  public docs/release notes, feature by feature, in the same behaviour
  language as P-001.
- **P-003** The Voxta census: likewise (v1.11 line as the baseline;
  the census records the version it read).
- **P-004** The delta table: mirror feature × Rúnmál state
  (HAVE / HAVE-THIN / MISSING / DELIBERATELY-DIFFERENT with the
  sovereign reason) — this road's parts are re-cut from the table if
  it disagrees with §3's shape.
- **P-005** Interop corpus: real-world character cards, lorebooks, and
  presets gathered from public user content (licences respected) as
  test fixtures — users' content must survive the trip.
- **P-006** The continuation audit ("all correct roadmaps"): every
  open thread in the repo's docs — STATUS, FORGE-LOG, the Evaluation
  Sitting brief in the goal workspace, ADR follow-ups — judged
  correct/stale/closed; correct ones are scheduled into this campaign
  first, before new parity work.
- **P-007** The fresh baseline: the full suite re-run on purplelongship
  at campaign start (counts from the runner only; the remembered
  686/3 is a rumour until re-measured).
- **P-008** Backend parity ledger: which inference backends the mirrors
  speak that Rúnmál doesn't yet (and vice versa), each judged
  wanted/unwanted with reasons.
- **P-009** The Aesir readiness check: what Aesir serves today for chat
  (its own ledger), so parity slices bind to truth, not hope.
- **P-010** Voice provider census: STT/TTS services the mirrors plug
  that pass Rúnmál's licence gate (the founding survey's method,
  refreshed for 2026's field).
- **P-011** Mobile reality check: what "Android/browser client" means
  for a Python local app (responsive web + PWA shape) — a decision
  record, not a hope.
- **P-012** The clean-room log opened: sources consulted per feature
  area, recorded as the road proceeds (the founding RESEARCH.md
  pattern) — the project's legal hygiene is a deliverable.
- **P-013** Priority order ratified: parts sequenced by Volmarr's
  likely daily use (voice + scenarios early, hub late) — the order in
  §3 stands unless the census moves it, with the move recorded.
- **P-014** Part I gate: delta table + continuation audit + fresh
  baseline all banked; every later part's slice list re-validated
  against the table.

## Part II — Cards & Content Interop (P-015 – P-030)

*Goal: a user's characters, personas, and worlds are their property.
Whatever the mirrors can hold, Rúnmál can receive, keep whole, and
hand back.*

- **P-015** Character card v2 import (PNG-embedded + JSON) with full
  field fidelity — nothing silently dropped; unknown fields preserved
  verbatim.
- **P-016** Character card v3 import: the newer spec's additions
  (assets, creator metadata, group-only fields) mapped to Rúnmál's
  model with a written mapping.
- **P-017** Card export v2 + v3: round-trip tests against the P-005
  corpus (import → export → field-diff clean).
- **P-018** Persona interop: ST-shaped persona files in/out; Rúnmál
  personas gain the fields users expect (description positions,
  depth) without breaking existing ones.
- **P-019** Lorebook file interop (ST world-info JSON in/out) —
  entries, keys, and settings preserved; Part III deepens behaviour.
- **P-020** Chat file interop: JSONL chat import/export in the shapes
  users actually have; branches and swipes survive as data even where
  the UI lands later (Part V).
- **P-021** Preset interop: sampler/prompt presets from ST files
  imported into Rúnmál's preset system (Part IV gives them depth).
- **P-022** Bulk library import: a whole folder of a user's cards +
  lorebooks imported as one act, with a report (accepted/repaired/
  refused with reasons).
- **P-023** Card thumbnails & assets: card art, alternate expressions
  and asset packs stored per character (Part X animates them).
- **P-024** Tags, favourites, and library organisation at card scale
  (hundreds of cards stay findable).
- **P-025** Duplicate and version handling: same-name cards versioned,
  never silently overwritten.
- **P-026** Scenario content interop (Voxta-shaped scenarios): read
  the public scenario format's structure and map what's mappable to
  Rúnmál scenarios (Part IX); unmappable scripting is reported, not
  faked.
- **P-027** Content safety rails: imported content is data, never
  code — importers parse defensively (the founding security model's
  kin).
- **P-028** The `.runmal` archive grows: cards/lorebooks/presets in
  the portable archive with the same checksum discipline.
- **P-029** Provenance on import: where a card came from and when,
  kept with it (creator credit survives in Rúnmál).
- **P-030** Part II gate: the P-005 corpus round-trips clean; a
  stranger's real library imports whole with an honest report.

## Part III — Lorebook Depth (P-031 – P-048)

*Goal: world info at the mirrors' full strength — the quiet engine
that makes long worlds stay true.*

- **P-031** Recursive scanning: entries triggering entries, with
  depth limits and cycle safety, token budget enforced.
- **P-032** Selective logic: AND/NOT/any-all key logic per entry, the
  full truth table tested.
- **P-033** Timed effects: sticky/cooldown/delay entries across a
  chat's life.
- **P-034** Inclusion groups: mutually exclusive entries resolved by
  weight/priority, deterministically.
- **P-035** Entry states: constant, selective, vectorised — the three
  activation kinds, one engine.
- **P-036** Probability & RNG honesty: probabilistic entries use a
  seeded, inspectable roll (the Sagnaskemma dice discipline's kin).
- **P-037** Scan depth & context windows: per-book scan settings
  (messages-deep, whole-chat, external context) as data.
- **P-038** Position & depth control: entries inject at declared
  positions/depths in the prompt (the composer contract honoured).
- **P-039** Character-book binding: a card's own lorebook travels with
  it and merges with the world's by declared precedence.
- **P-040** Global + persona + chat lore scopes, layered like the
  mirrors' (world → character → chat) with per-scope budgets.
- **P-041** Vectorised lore: embedding-matched entries for large
  books, on the founding RAG stack, with keyword fallback.
- **P-042** Lorebook editor depth: the UI reaches every field the
  engine honours (no engine-only settings).
- **P-043** Activation inspector: "why did this entry fire" — the
  matched keys and roll shown per message (Part XIII's Inspector
  consumes this).
- **P-044** Token accounting: lore's exact prompt cost per turn,
  visible before sending.
- **P-045** Book sharing: lorebooks as importable packs (Part XII's
  hub carries them).
- **P-046** Performance: a 10,000-entry book scans within a stated
  budget on Pi-class hardware.
- **P-047** Migration: existing Rúnmál lorebooks upgraded in place,
  behaviour-preserving, fixture-proven.
- **P-048** Part III gate: the ST-shaped lore test pack (logic,
  recursion, timing) passes on Rúnmál's engine; inspector explains
  every firing.

## Part IV — Prompt & Sampler Depth (P-049 – P-064)

*Goal: the prompt is the instrument. Players of the mirrors expect to
tune it to the string — Rúnmál's composer grows the full workshop.*

- **P-049** Prompt manager: ordered, toggleable prompt blocks
  (system, persona, lore, memory, author's note, examples) as a
  first-class editable structure.
- **P-050** Instruct templates: the public template shapes (ChatML,
  Llama-3, Alpaca, Vicuna…) as data, per-model selectable.
- **P-051** Context templates: story-string/context assembly formats
  imported and editable (P-021's presets land here).
- **P-052** Sampler surface complete: every common sampler (temp,
  top-p/k, min-p, repetition/presence/frequency, DRY, XTC-class)
  exposed where the backend supports it, hidden honestly where not.
- **P-053** Per-backend capability truth: sampler controls grey by
  measured backend support (Aesir's ledger included) — never fake
  sliders.
- **P-054** Presets: save/load/share sampler+prompt bundles; per-
  character and per-chat overrides.
- **P-055** Macros: {{char}}, {{user}}, time/date, random, and the
  mirrors' useful macro set — clean-room semantics, documented.
- **P-056** Author's note depth: per-chat note with depth/frequency
  controls.
- **P-057** Post-history instructions (the jailbreak-position block,
  neutrally named) as a prompt-manager citizen.
- **P-058** Token budget governor: the composer shows the whole
  prompt's budget (context, lore, memory, history) and trims by
  declared policy when over.
- **P-059** Prompt preview: the exact final prompt (per backend
  rendering) inspectable before send — the glass box the Inspector
  (Part XIII) also uses.
- **P-060** Logit bias & stop sequences: per-preset, backend-honest.
- **P-061** Grammar/JSON-mode where backends offer it, as a prompt
  citizen (structured replies for bridges/games).
- **P-062** Multi-model prompt profiles: one chat, swappable model
  profiles with their own templates/samplers (the mirrors' connection
  profiles, sovereign-shaped).
- **P-063** Prompt import/export packs (with Part XII sharing).
- **P-064** Part IV gate: an ST preset pack drives Rúnmál chats with
  visibly identical prompt assembly (preview-diffed), sampler truth
  table published per backend.

## Part V — Chat Surgery (P-065 – P-080)

*Goal: the conversation as a malleable document — every operation
the mirrors' users do a hundred times a day.*

- **P-065** Swipes deepened: unlimited alternates per message, swipe
  navigation everywhere (incl. voice turns), swipe-specific regen
  settings.
- **P-066** Branches: fork a chat at any message; branches listed,
  named, merged-back as a new branch (never destructive).
- **P-067** Checkpoints: named chat snapshots (bookmarks) with
  one-click return — implemented over Rúnmál's archive machinery.
- **P-068** Message actions complete: edit (with variant history),
  delete, move, copy-to-branch, pin-to-memory.
- **P-069** Continue & impersonate: nudge-generation and user-turn
  drafting by the model, the mirrors' pair.
- **P-070** Group chats deepened: activation strategies (natural
  order, list, pooled), per-member overrides, group lore/persona
  handling — measured against the delta census.
- **P-071** Multi-character scenes with absent-character history
  sharing (Voxta's shape): a returning character receives a digest of
  what it missed.
- **P-072** Chat search: full-text + semantic search across all chats,
  jump-to-message.
- **P-073** Chat metadata: titles, tags, summaries auto-generated and
  editable; the library view at scale.
- **P-074** Data bank: per-chat attached documents the model can read
  (the mirrors' file-attachment memory), scoped and budgeted.
- **P-075** Message-level provenance: which model/preset/lore produced
  each message — recorded (Inspector consumes; Yggdrasil receipts are
  kin).
- **P-076** Undo for chat operations (the coder's journal pattern at
  chat scale).
- **P-077** Long-chat performance: 10k-message chats stay fluid (the
  founding UI campaign's standards held).
- **P-078** Chat import surgery: P-020's imports become fully live
  chats (swipes/branches preserved where the format carried them).
- **P-079** Quiet/greeting controls: alternate greetings per card,
  first-message variants as swipes.
- **P-080** Part V gate: a surgery drill script (branch, checkpoint,
  swipe-storm, group scene) runs green; no operation loses data.

## Part VI — The Extensions Row (P-081 – P-100)

*Goal: the mirrors grow by extensions; Rúnmál grows by a plugin row
of its own — a real API, a real sandbox, and the beloved extensions
rebuilt as citizens.*

- **P-081** Plugin API v1: lifecycle, chat events, prompt hooks,
  UI slots — versioned, documented, the Samtal adapter pattern's kin.
- **P-082** Plugin sandbox: plugins are data+declared capabilities;
  no plugin touches the network/files/secrets uninvited (ADR-shaped).
- **P-083** Plugin manager: install/enable/update from local packs
  (Part XII carries them) with permission cards.
- **P-084** Memory Summarise plugin: rolling chat summary into memory
  (the mirrors' most-loved extension), on the founding memory stack.
- **P-085** Vector Storage plugin: per-chat/character vector memory
  with the founding sqlite-vec store.
- **P-086** Translate plugin: messages in/out via local models by
  default; provider-pluggable.
- **P-087** Image Generation plugin: prompt-from-scene + manual,
  local diffusion endpoints first (Part X consumes for avatars).
- **P-088** Web Search plugin: opt-in, per-chat, with results cited
  into context (off by default — sovereignty is the default state).
- **P-089** Quick Replies: user-defined one-tap macros incl. chained
  actions and input senders.
- **P-090** Regex scripts: ST-shaped find/replace rules (importable
  format) applied at declared stages, with a safe regex dialect and
  timeout discipline.
- **P-091** TTS/STT as plugins too: the founding voice stack refactored
  behind the same API (proof the API is real).
- **P-092** Expression/sprite plugin surface (Part X builds on it).
- **P-093** Variables & state plugin API: per-chat variables/flags
  (Part IX scenarios consume the same store).
- **P-094** Plugin data custody: a plugin's data is exportable and
  deletable with the plugin — no hostage state.
- **P-095** The gallery plugin: chat image gallery with generation
  history (Voxta users expect it; ST users bolt it on — here it's a
  citizen).
- **P-096** Dice & game-bridge plugin surface: Sagnaskemma rolls and
  bridge events (VRChat/Skyrim) exposed as plugin citizens.
- **P-097** Plugin conformance kit: a plugin must pass contract +
  sandbox tests to be listed (the node-kit pattern from Yggdrasil).
- **P-098** Plugin settings UI generated from declared schemas.
- **P-099** Failure manners: a crashing plugin disables itself with a
  plain report; the chat never dies with it.
- **P-100** Part VI gate: the row ships with P-084–P-090 + P-095 live;
  a third-party-shaped test plugin (written blind against the docs)
  installs and runs.

---
