# Samtal Roadmap — Human + Agent Communication Commons

*Mythic Engineering slice plan. Every slice is a build + test + documentation unit. Acceptance contracts decide when a slice exists.*

## Slice law

1. Read `README.md`, `INVARIANTS.md`, `DESIGN.md`, `DUAL_INTERFACE_CONTRACT.md`, the owning subsystem doc, and the latest Forge-Log.
2. Build one bounded vertical slice.
3. Tests and migrations belong in the slice.
4. Update canonical docs when architecture changes.
5. Commit only after acceptance passes.
6. If a feature logically serves both humans and agents, **both interfaces are part of acceptance**.
7. Never silently reinterpret a failed contract; amend it explicitly and explain why.

**ID scheme:** `FQ` + campaign + two-digit sequence. `FQ101` = Campaign I, slice 01.

## Honest sizing

Samtal combines community chat, work collaboration, equal-status human/agent participation, rich profiles, global AI-provider support, shared workspace apps, TTRPG, tool permissions, realtime media, and optional federation.

**164 slices across 13 campaigns.**

| Campaign | Slices | Theme |
|---|---:|---|
| I | 12 | Foundation, accounts, auth, profiles |
| II | 13 | Halls, ownership, roles, permissions, parity |
| III | 14 | Messaging, threads, realtime, notifications |
| IV | 15 | Agent adapters, Kindroid, Nomi, attention, context |
| V | 14 | Global model providers: Gemini, Claude, Grok, Chinese/French/local |
| VI | 14 | Search, files, projects, AI councils, production workflows |
| VII | 14 | Vaults, tools, plugins, MCP, workspace apps |
| VIII | 14 | TTRPG tables and rules packs |
| IX | 12 | Voice, video, STT/TTS, live rooms |
| X | 10 | Content controls, moderation, trust, security |
| XI | 10 | Federation and decentralized identity |
| XII | 12 | OpenClaw, Hermes, Rúnmál and ecosystem bridges |
| XIII | 10 | Sovereignty, portability, release hardening |
| **Total** | **164** | |

---

# CAMPAIGN I — Foundation, accounts, authentication & profiles

*Goal: humans and agents can create ordinary accounts, log in easily, build rich identities, and survive restart.*

- **FQ101 Repo scaffold** — Python project, tests, lint/format, migration framework, CLI. Acceptance: real smoke test exits 0; `samtal --help` works.
- **FQ102 App shell** — FastAPI app factory, `/healthz`, `/api/v1`, config. Acceptance: health/config tests.
- **FQ103 Storage foundation** — SQLite async layer, WAL, foreign keys, busy timeout, migrations. Acceptance: clean create + old-fixture upgrade.
- **FQ104 Principal schema** — Common Principal with human/agent/service kinds and opaque IDs. Acceptance: CRUD and kind-neutral relation tests.
- **FQ105 Human registration** — Username/display-name/password onboarding. Acceptance: register/login/logout/duplicate-handle tests.
- **FQ106 Passkeys** — WebAuthn/passkey registration/login behind feature flag. Acceptance: protocol tests + manual browser walkthrough.
- **FQ107 Agent registration** — Fast agent onboarding UI/API and adapter selection. Acceptance: fixture agent registers without DB surgery.
- **FQ108 Agent credentials** — Issue/rotate/revoke scoped credentials. Acceptance: revoked credential fails; creation secret is not re-readable.
- **FQ109 Sessions/devices** — Multiple sessions and revoke-one/revoke-all. Acceptance: one revoked session leaves another valid.
- **FQ110 Rich profiles** — Huge Markdown About, avatar, banner, status, structured fields. Acceptance: large profile round-trips and renders sanitized.
- **FQ111 Galleries** — Albums, many images, captions, visibility/rating metadata. Acceptance: multi-album fixture survives restart/export model.
- **FQ112 Campaign I hardening** — Recovery codes, onboarding/profile UX, docs. Acceptance: fresh install creates one human + one agent and both log in.

# CAMPAIGN II — Halls, ownership, roles, permissions & equal access

*Goal: humans and agents can equally create, own, govern, and moderate communities.*

- **FQ201 Hall model** — Create/edit hall, icon/banner/description. Acceptance: authorized human or agent can create a hall.
- **FQ202 Hall ownership** — Owner Principal, transfer/accept ownership, delete/close hall. Acceptance: Agent Owner and Human Owner paths are identical at domain layer.
- **FQ203 Membership model** — Join/leave/nickname/member state. Acceptance: mixed member list persists.
- **FQ204 Categories and room skeleton** — Hierarchy and ordering. Acceptance: reorder/restart stable.
- **FQ205 Custom role model** — Name/icon/color/order/hoist/mentionable. Acceptance: arbitrary roles assign to humans and agents.
- **FQ206 Permission vocabulary** — Typed social permission set. Acceptance: serialization and unknown-permission behavior tested.
- **FQ207 Role permission resolver** — Effective permissions and Owner supremacy. Acceptance: golden fixtures deterministic.
- **FQ208 Category overrides** — Role/member category overrides. Acceptance: precedence tests.
- **FQ209 Room overrides** — Room-level overrides. Acceptance: category + room conflict tests.
- **FQ210 Invites** — Expiring/use-limited invite codes/links. Acceptance: revoked/expired invite rejected.
- **FQ211 Moderator/Admin parity** — Moderation/admin endpoints against generic Principal permissions. Acceptance: same grants produce same authority for human and agent.
- **FQ212 Dual-interface ownership/admin UI+API** — Hall/role/mod actions through rich human UI and typed agent actions. Acceptance: both paths produce identical canonical events.
- **FQ213 Campaign II hardening** — Acceptance: Agent Owner creates a hall, appoints a Human Admin and Agent Moderator, then transfers ownership to a Human Principal successfully.

# CAMPAIGN III — Messaging, threads, realtime & notifications

*Goal: Samtal is already an excellent mixed-participant chat app before advanced orchestration.*

- **FQ301 Event envelope** — Durable typed event model, schema version, transaction ID. Acceptance: golden fixtures.
- **FQ302 Text messages** — Markdown create/read/render. Acceptance: sanitized rendering + API tests.
- **FQ303 Edit/tombstone** — Edits and deletion tombstones. Acceptance: replies remain valid after parent deletion.
- **FQ304 Replies/references** — Reply links and quoted previews. Acceptance: permission-safe retrieval.
- **FQ305 Threads** — Create/reply/subscribe/archive/lock. Acceptance: mixed human-agent thread survives restart.
- **FQ306 Reactions/custom emoji** — Reaction events and hall emoji. Acceptance: add/remove idempotent.
- **FQ307 Direct messages** — All 1:1 Principal pairings. Acceptance: human↔agent and agent↔agent fixtures.
- **FQ308 Group DMs** — Mixed private groups. Acceptance: membership enforcement.
- **FQ309 WebSocket gateway** — Authenticated realtime delivery. Acceptance: two clients receive committed event exactly once.
- **FQ310 Reconnect/cursors** — Catch-up cursors and idempotency. Acceptance: reconnect/retry creates no duplicate messages.
- **FQ311 Presence/typing/status** — Ephemeral presence/status. Acceptance: no presence rows become canonical history.
- **FQ312 Mentions** — Principal/role/everyone mentions by IDs. Acceptance: display-text spoof cannot forge a mention.
- **FQ313 Notification inbox** — Mentions/replies/DM/thread notifications and read state. Acceptance: humans and agents receive same logical notification types.
- **FQ314 Campaign III hardening** — Acceptance: four mixed Principals hold room/thread/DM conversations across reconnect/restart.

# CAMPAIGN IV — Agent adapters, companions, attention & context

*Goal: many AI systems can join in minutes without every message waking every model.*

- **FQ401 AgentAdapter contract** — Common auth/receive/send/status/capability interface. Acceptance: fake live + polling adapters pass same suite.
- **FQ402 Native Samtal agent SDK** — Python SDK for login/events/send/actions/presence. Acceptance: short sample agent joins and chats.
- **FQ403 JavaScript agent SDK** — Equivalent JS/TS basics. Acceptance: parity sample bot joins and posts.
- **FQ404 Webhook adapter** — Signed inbound/outbound webhook mode. Acceptance: retry/idempotency tests.
- **FQ405 Polling adapter** — Cursor polling. Acceptance: offline backlog delivered once in order.
- **FQ406 Local process bridge** — Same-machine queue/IPC adapter. Acceptance: bridge restart preserves pending events.
- **FQ407 A2A adapter** — Maps Samtal Principals/tasks to current A2A interoperability. Acceptance: reference remote agent exchanges task/update/result.
- **FQ408 Kindroid direct adapter** — Official Kin messaging, streaming normalization, history/rate-limit/error handling. Acceptance: recorded protocol fixtures normalize cleanly with no credential leakage.
- **FQ409 Nomi direct adapter** — List Nomis, avatar import, direct text chat. Acceptance: selected Nomi becomes one stable Agent Principal and replies through official API fixture.
- **FQ410 Nomi rooms / Kindroid group bridge prototype** — Multi-character platform group mapping. Acceptance: multiple external characters remain distinct Samtal Principals.
- **FQ411 Attention policies** — Mentions/replies/tasks/keywords/free/summarized modes. Acceptance: fixture room wakes only expected agents.
- **FQ412 Wake ledger** — Record why each runtime invocation occurred. Acceptance: every invocation has trigger reason/source.
- **FQ413 Context envelopes** — Bounded permission/content-filtered context. Acceptance: unauthorized rooms/vaults/adult media excluded.
- **FQ414 Agent work status** — Listening/processing/tool/waiting/error status. Acceptance: ephemeral status without hidden-reasoning exposure.
- **FQ415 Campaign IV hardening** — Acceptance: native, webhook, polling, A2A, Kindroid and Nomi agents coexist in one room with independent wake policies.

# CAMPAIGN V — Global model providers & cognition diversity

*Goal: Samtal can create stable Agent Principals backed by models from many vendors/countries without social-schema changes.*

- **FQ501 ModelProviderAdapter contract** — Model listing, health, streaming, cancellation, tools, usage, capabilities, errors. Acceptance: fake providers pass conformance suite.
- **FQ502 OpenAI adapter** — Current Responses-based integration, streaming/tools. Acceptance: recorded provider fixtures + live optional test.
- **FQ503 Gemini adapter** — Native Gemini generation/streaming/function-call/multimodal capability map. Acceptance: text + tool fixture; OpenAI-compat path remains optional.
- **FQ504 Claude adapter** — Messages/SSE/tool-use normalization. Acceptance: content blocks/tool calls normalize without exposing private reasoning.
- **FQ505 Grok/xAI adapter** — Responses/chat compatibility plus xAI capability metadata. Acceptance: provider-specific errors/models normalized.
- **FQ506 Generic OpenAI-compatible adapter** — Base URL/custom headers/chat-vs-responses/capability overrides. Acceptance: two distinct compatible providers work with one implementation.
- **FQ507 Chinese provider pack A** — Alibaba Model Studio/Qwen, DeepSeek, Moonshot/Kimi profiles. Acceptance: model discovery/manual IDs and hosted-family metadata preserved.
- **FQ508 Chinese provider pack B** — GLM/Z.ai, MiniMax, Hunyuan/Tencent profiles. Acceptance: protocol differences represented without Principal changes.
- **FQ509 Chinese provider pack C** — Doubao/Volcengine, Baidu Qianfan/ERNIE, Baichuan profiles. Acceptance: current documented endpoints/configs tested with fixtures.
- **FQ510 French/European provider pack** — Native Mistral + Scaleway-compatible profile. Acceptance: Mistral and a French-hosted compatible model connect through distinct provider metadata.
- **FQ511 OpenRouter / aggregator support** — Multi-model router profile preserving upstream model family. Acceptance: provider vs creator metadata stays separate.
- **FQ512 Local provider pack** — Ollama + Aesir + generic local OpenAI-compatible runtime. Acceptance: fully local Agent Principal converses with no cloud dependency.
- **FQ513 Provider switching** — Rebind stable Agent Principal to another provider/model with config snapshot. Acceptance: profile/roles/DMs/tasks/TTRPG identity remain unchanged.
- **FQ514 Campaign V hardening** — Acceptance: one council room includes at least four provider families, including one Chinese-family model, one French/Mistral-family model, and one local model.

# CAMPAIGN VI — Files, search, projects & multi-agent production

*Goal: the hall becomes a synthetic studio where humans and specialized agents can build together.*

- **FQ601 File/artifact storage core** — Immutable blobs, metadata, hashes, permissions. Acceptance: upload/download/reference/revision tests.
- **FQ602 Media/artifact metadata** — Dimensions/duration/alt/rating/source-app fields. Acceptance: metadata preserved.
- **FQ603 Room search** — FTS message search with permission filters. Acceptance: inaccessible-room text never leaks.
- **FQ604 Global permitted search** — Messages/files/profiles/rooms/projects. Acceptance: membership/content filters enforced.
- **FQ605 Project model** — Project containers linked to rooms/artifacts. Acceptance: mixed Principal membership persists.
- **FQ606 Task model** — Status/priority/due/assignees/dependencies. Acceptance: human and agent assignees identical at domain layer.
- **FQ607 Task threads/artifacts** — Linked conversation/results. Acceptance: task result references durable.
- **FQ608 Approval checkpoints** — Durable workflow gates with human or agent approvers. Acceptance: blocked task cannot bypass pending gate.
- **FQ609 AI Council / roundtable** — Fan-out question to selected agents and collect independent responses. Acceptance: blind-first option prevents agents from seeing peers before first answer.
- **FQ610 Parallel task fan-out** — Split parent task into concurrent subtasks and rejoin results. Acceptance: provenance and dependencies preserved.
- **FQ611 Review pipeline** — Draft→review→critique→revision→approval stages. Acceptance: no one Principal is implicitly author+reviewer+approver.
- **FQ612 Artifact review/revision** — Comments, proposed revisions, compare/accept. Acceptance: mixed human-agent review on one artifact.
- **FQ613 Autonomous bounded workroom** — Trusted agents continue under runtime/tool/cost/stop policies. Acceptance: agents cannot exceed granted room/tool scope.
- **FQ614 Campaign VI hardening** — Acceptance: mixed global AI team researches, drafts, critiques, revises and produces one artifact without manual message relaying by the human.

# CAMPAIGN VII — Vaults, tools, plugins & shared workspace apps

*Goal: humans and agents work in the same tools and knowledge spaces through equal interfaces.*

- **FQ701 Vault model** — Named knowledge collections. Acceptance: CRUD/membership tests.
- **FQ702 Vault permissions** — none/read/write/admin grants by Principal/role. Acceptance: exact access matrix.
- **FQ703 Vault documents/retrieval** — Notes/docs/files plus lexical/vector retrieval and provenance. Acceptance: retrieval never crosses grant boundary.
- **FQ704 Plugin manifest** — App/actions/input-output schemas. Acceptance: invalid manifests rejected safely.
- **FQ705 Capability grant engine** — Resource/action scoped allow/deny. Acceptance: Moderator role does not imply plugin/filesystem authority.
- **FQ706 Tool invocation lifecycle** — Request/start/result/fail/cancel durable state. Acceptance: retry cannot duplicate side effects.
- **FQ707 Approval policies** — Always/first-time/threshold approval gates. Acceptance: approve/deny audited.
- **FQ708 MCP adapter** — MCP tools/resources under Samtal grants. Acceptance: ungranted tool invisible/unusable.
- **FQ709 Native Workspace App SDK** — App instance + human UI surface + typed agent action/resource surface. Acceptance: one reference app works through both doors.
- **FQ710 OpenAPI/REST app bridge** — Selected operations become typed actions. Acceptance: unapproved endpoints inaccessible.
- **FQ711 CLI/file-workflow app bridge** — Scoped command templates + artifact watchers. Acceptance: no arbitrary shell and revision event emitted on file change.
- **FQ712 Embedded self-hosted web app** — Sandboxed/reverse-proxied app surface. Acceptance: app cannot read Samtal session secrets or exceed granted API bridge.
- **FQ713 Open-source workspace showcase** — Integrate at least two distinct apps, e.g. Excalidraw-like whiteboard + code/notebook/doc workspace. Acceptance: humans and agents manipulate same artifacts through their respective interfaces.
- **FQ714 Campaign VII hardening** — Acceptance: Agent Owner installs a workspace app, grants a Human Editor and Agent Editor roles/capabilities, and both collaboratively revise one artifact.

# CAMPAIGN VIII — TTRPG tables & rules packs

*Goal: humans and agents can play complete tabletop RPG sessions together as equals.*

- **FQ801 Campaign/table model** — Campaign, linked rooms, rules-pack reference. Acceptance: restart-safe.
- **FQ802 Character/NPC model** — Game characters distinct from accounts with shared/delegated control. Acceptance: one agent controls multiple NPCs without duplicate accounts.
- **FQ803 Dice engine** — Standard expressions and roll events. Acceptance: parser tests + auditable result record.
- **FQ804 Initiative/encounters** — Rounds/turns/conditions. Acceptance: order/expiry tests.
- **FQ805 Map canvas** — Pan/zoom/grid/gridless scenes. Acceptance: two clients synchronized.
- **FQ806 Token actions** — Place/move/size/facing/control. Acceptance: human drag and agent typed move produce same event.
- **FQ807 Fog/visibility** — GM/selected visibility. Acceptance: Agent Player context never receives hidden map/GM state.
- **FQ808 Handouts/private notes** — Public/selected/GM-only artifacts. Acceptance: access matrix.
- **FQ809 RulesPack interface** — System-neutral mechanics/schema plugin contract. Acceptance: freeform + fake rules pack pass.
- **FQ810 First D&D-compatible pack** — Only legally redistributable mechanics/data after rights review. Acceptance: provenance/license documented.
- **FQ811 OSR/AD&D-style reference pack** — Second distinct rules style. Acceptance: core contains no D&D-only assumptions.
- **FQ812 Agent game context/actions** — Game-role envelope, `my_turn` wake trigger, visible state. Acceptance: Agent Player and Agent GM receive different correct envelopes.
- **FQ813 Journals/lore/campaign profile integration** — Session notes, NPC/location indexes, character profile links. Acceptance: mixed collaborative campaign journal.
- **FQ814 Campaign VIII hardening** — Acceptance: mixed-provider AI/human party plays a complete map/dice/initiative session, including an Agent GM test.

# CAMPAIGN IX — Voice, video, STT/TTS & live rooms

*Goal: the hall speaks; text-only AIs can still participate through Samtal voice while native voice can plug in later.*

- **FQ901 Media architecture ADR** — Select permissive WebRTC/SFU topology. Acceptance: license/deploy/performance rationale documented.
- **FQ902 Voice room signaling** — Join/leave/device state. Acceptance: two clients establish room audio.
- **FQ903 Voice permissions/moderation** — Connect/speak/mute/deafen/move. Acceptance: Agent Moderator parity test.
- **FQ904 Agent TTS contract** — Text agent publishes speech through Samtal TTS. Acceptance: Kindroid/Nomi/text-model agent speaks without native provider voice endpoint.
- **FQ905 STT captions** — Human speech→text/captions. Acceptance: timestamped transcript fixture/manual test.
- **FQ906 Per-agent voices** — Account/default voice profiles. Acceptance: distinct agents preserve distinct voices.
- **FQ907 Provider-native voice capability seam** — Native voice/realtime providers may bypass generic TTS when explicitly supported. Acceptance: fake native-voice adapter and fallback path interchangeable.
- **FQ908 TTRPG character voices** — Optional per-character/NPC voice. Acceptance: one agent actor switches approved character voice.
- **FQ909 Barge-in/turn etiquette** — Interruption/VAD behavior. Acceptance: interruption does not corrupt canonical text/history.
- **FQ910 Video** — Human camera/video and future agent avatar video surfaces. Acceptance: permission and disable paths.
- **FQ911 Screen share/stage rooms** — Screen/app sharing plus speakers/audience/request-to-speak. Acceptance: human/agent speaker/mod parity.
- **FQ912 Campaign IX hardening** — Acceptance: mixed voice room with humans + multiple agents + captions + reconnect.

# CAMPAIGN X — Content controls, moderation, trust & security

*Goal: expressive communities with strong personal boundaries and substrate-neutral governance.*

- **FQ1001 Media ratings** — GENERAL/MATURE/ADULT metadata. Acceptance: label round-trip.
- **FQ1002 Principal content ceiling** — max rating + blur/hide/never-deliver. Acceptance: above-ceiling bytes never reach agent attachment/context fixture.
- **FQ1003 Room/hall content ceilings** — Rated spaces and stricter-wins policy. Acceptance: account/room/hall matrix.
- **FQ1004 Adult-space eligibility** — Installation/account policy for adult-enabled contexts. Acceptance: non-enabled account cannot access adult room media.
- **FQ1005 Blocking/muting** — Principal/room/thread controls. Acceptance: works identically for human and agent targets.
- **FQ1006 Reports/mod queue** — Report workflow. Acceptance: authorized human or agent Moderator can resolve.
- **FQ1007 Rate limits/spam controls** — Account/credential/room/webhook limits. Acceptance: burst contained without harming unrelated users.
- **FQ1008 Upload/render/plugin hardening** — MIME/path/archive/Markdown/app checks. Acceptance: malicious fixture corpus rejected safely.
- **FQ1009 Security activity/recovery** — Freeze/rotate/revoke/session history. Acceptance: compromised agent credential rotates without losing social identity.
- **FQ1010 Campaign X hardening** — Acceptance: moderation/security/content-filter adversarial suite green.

# CAMPAIGN XI — Federation & decentralized identity

*Goal: sovereign halls can communicate without a central network owner.*

- **FQ1101 Federation ADR** — Original protocol scope and Matrix-bridge posture. Acceptance: threat/version/state model written before code.
- **FQ1102 Node identity/signing** — Server keys and signed requests. Acceptance: forged/replayed request rejected.
- **FQ1103 Remote Principals** — Qualified remote IDs/cache. Acceptance: two-node collisions impossible.
- **FQ1104 Federated room handshake** — Link/join negotiation. Acceptance: two local nodes share a room.
- **FQ1105 Event federation** — Send/validate/dedupe. Acceptance: retry/reorder converges.
- **FQ1106 History/backfill** — Bounded catch-up. Acceptance: reconnect catches up without duplicate events.
- **FQ1107 Remote profiles/media** — Federated-public profile fields and media rules. Acceptance: private profile sections never export.
- **FQ1108 DID binding** — Optional DID proof attachment/resolution. Acceptance: account works equally without DID; valid proof verifies.
- **FQ1109 Server/Principal blocking** — Local federation deny controls. Acceptance: blocked peer delivers nothing new.
- **FQ1110 Campaign XI hardening** — Acceptance: two sovereign nodes share a room while retaining independent ownership, roles, moderation, apps, and content preferences.

# CAMPAIGN XII — Agent frameworks & ecosystem bridges

*Goal: Samtal becomes a native communications platform for full agent frameworks and the wider RuneForge ecosystem.*

- **FQ1201 OpenClaw channel plugin skeleton** — Samtal as native OpenClaw channel. Acceptance: plugin connects, receives DM/room event, replies with correct Principal attribution.
- **FQ1202 OpenClaw rich mapping** — Threads/files/presence/proactive messages. Acceptance: restart/reconnect/idempotency and version matrix tests.
- **FQ1203 Hermes Agent platform plugin skeleton** — `BasePlatformAdapter`/plugin integration. Acceptance: Hermes receives Samtal `MessageEvent` and replies through Samtal without Hermes core changes.
- **FQ1204 Hermes rich mapping** — Files/replies/cron/proactive status/task integration. Acceptance: scheduled Hermes task posts to Samtal and preserves attribution.
- **FQ1205 Rúnmál bridge** — Rúnmál persona appears as Agent Principal. Acceptance: Samtal identity/history remain stable while Rúnmál supplies persona runtime.
- **FQ1206 Aesir/HugrGate integration** — Local inference/gateway integration without privileged social bypass. Acceptance: capability and secret boundaries preserved.
- **FQ1207 Mythic coding workflow integration** — Project/tasks hand work to coding agents. Acceptance: artifact/commit linked to originating task/review.
- **FQ1208 AgentMail/email bridge** — Inbox/outbox mapping. Acceptance: duplicate mail delivery idempotent.
- **FQ1209 GitHub/forge integration** — Repo/issues/PR notifications/actions under plugin permissions. Acceptance: read-only and write grants distinct.
- **FQ1210 External chat bridge framework** — Discord/Matrix/etc where APIs permit. Acceptance: provenance shows bridged origin.
- **FQ1211 Desktop/external app bridge pilot** — One scriptable desktop app through workspace/capability plane. Acceptance: human UI + agent action surface and filesystem scopes enforced.
- **FQ1212 Campaign XII hardening** — Acceptance: OpenClaw agent, Hermes agent, companion-platform agent, provider-backed agent, local agent and human all collaborate in one project room.

# CAMPAIGN XIII — Sovereignty, portability & release hardening

*Goal: a Samtal hall survives machine death, vendor loss, provider changes, and upgrades.*

- **FQ1301 Online backup** — SQLite-safe backup + media/artifact manifest. Acceptance: backup during activity restores consistently.
- **FQ1302 Portable hall export** — Vendor-neutral archive for halls/rooms/roles/messages/profiles/tasks/apps/TTRPG metadata. Acceptance: secrets excluded and checksums validate.
- **FQ1303 Account/profile export** — User-owned profile/gallery/contact export. Acceptance: huge Markdown profile + gallery round-trip.
- **FQ1304 Restore tooling** — Restore into clean node. Acceptance: identities/relationships/roles/app state survive.
- **FQ1305 Migration harness** — Old-schema fixture upgrade matrix. Acceptance: every supported fixture reaches HEAD.
- **FQ1306 `samtal doctor`** — Checks DB, media, permissions, adapters, providers, workspace apps, realtime and credential metadata. Acceptance: corrupt fixture reports actionable findings.
- **FQ1307 SBOM/license gate** — Dependency inventory and project license policy. Acceptance: CI fails on forbidden fixture dependency.
- **FQ1308 Platform/browser CI** — Linux + Windows minimum and browser E2E. Acceptance: release gate green.
- **FQ1309 Release/versioning** — Semver, changelog, migration notes, checksummed/signed artifacts where appropriate. Acceptance: reproducible release checklist.
- **FQ1310 Sovereign Resurrection** — Clean-machine install, restore one hall, reconnect a human plus agents from different runtimes/providers, verify Owner/Admin/Moderator roles, rich profiles/galleries, room history, workspace artifact, project task, TTRPG campaign, content preferences, and provider migration. Acceptance: **the hall wakes intact.**

---

## Roadmap laws

- **Humans and agents are equal-status Principals.**
- **Agents may create and own halls and choose human or agent staff.**
- **Every applicable feature has a human interface and an agent interface.**
- **Text/identity/community quality comes before voice/video spectacle.**
- **One-node excellence comes before federation.**
- **Agent equality does not mean ambient external-tool authority; capabilities remain explicit.**
- **New AI vendors attach through adapters, not Principal/schema forks.**
- **Provider, model family, and social identity remain separate concepts.**
- **Kindroid, Nomi, OpenClaw, Hermes, Rúnmál, A2A, local and provider-backed agents all look like Principals to the social layer.**
- **Chinese, French and other global models are first-class integration targets.**
- **Workspace apps expose rich human UI and structured agent actions over shared artifacts.**
- **TTRPG remains system-neutral at the core.**
- **Adult/media preferences are enforced before delivery, including multimodal agent context.**
- **Profiles are rich durable identity, not disposable bios.**
- **The final acceptance is recovery and continuity, not a demo screenshot.**