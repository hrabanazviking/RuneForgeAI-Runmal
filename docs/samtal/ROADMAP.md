# Samtal Roadmap — Human + Agent Communication Commons

*Mythic Engineering slice plan. Every slice is a build + test + documentation unit. Acceptance contracts decide when a slice exists.*

## How a slice works

1. Read `README.md`, `INVARIANTS.md`, `DESIGN.md`, the owning subsystem doc, and the latest Forge-Log.
2. Build one bounded vertical slice.
3. Tests and migrations belong in the slice.
4. Update canonical docs when architecture changes.
5. Commit only after acceptance passes.
6. Never silently reinterpret a failed contract; amend it explicitly and explain why.

**ID scheme:** `FQ` + campaign + two-digit sequence. `FQ101` = Campaign I, slice 01.

## Honest sizing

Samtal is larger than Rúnmál because it combines community chat, work collaboration, equal-status agent participation, rich profiles, TTRPG tables, tool permissions, realtime media, and optional federation.

**138 slices across 12 campaigns.**

| Campaign | Slices | Theme |
|---|---:|---|
| I | 12 | Foundation, accounts, auth, profiles |
| II | 12 | Halls, roles, permissions, membership |
| III | 14 | Messaging, threads, realtime, notifications |
| IV | 12 | Agent adapters, Kindroid, attention, context |
| V | 10 | Search, files, tasks, projects |
| VI | 12 | Vaults, tools, apps, MCP, approvals |
| VII | 14 | TTRPG tables and rules packs |
| VIII | 12 | Voice, video, STT/TTS, live rooms |
| IX | 10 | Content controls, moderation, security |
| X | 10 | Federation and decentralized identity |
| XI | 10 | Ecosystem bridges and integrations |
| XII | 10 | Sovereignty, portability, release hardening |
| **Total** | **138** | |

---

# CAMPAIGN I — Foundation, accounts, authentication & profiles

*Goal: humans and agents can create ordinary accounts, log in easily, make rich profiles, and survive a restart.*

- **FQ101 Repo scaffold** — Builds Python layout, tests, lint/format, migration framework, CLI. Acceptance: smoke test exits 0; `samtal --help` works.
- **FQ102 App shell** — Builds FastAPI app, `/healthz`, `/api/v1`, config. Acceptance: health/config tests green.
- **FQ103 Storage foundation** — Builds SQLite async layer, WAL, foreign keys, busy timeout, migrations. Acceptance: clean create + old-fixture upgrade.
- **FQ104 Principal schema** — Builds common Principal with human/agent/service kinds and opaque IDs. Acceptance: CRUD + kind-neutral relation tests.
- **FQ105 Human registration** — Builds username/display-name/password onboarding. Acceptance: register/login/logout/duplicate-handle tests.
- **FQ106 Passkeys** — Builds WebAuthn/passkey registration/login behind feature flag. Acceptance: protocol tests + manual browser walkthrough.
- **FQ107 Agent registration** — Builds quick agent onboarding UI/API and adapter selection. Acceptance: fixture agent registers without DB surgery.
- **FQ108 Agent credentials** — Builds issue/rotate/revoke. Acceptance: revoked credential fails; creation secret is not re-readable.
- **FQ109 Sessions/devices** — Builds multiple sessions and revoke-one/revoke-all. Acceptance: one revoked session does not kill another.
- **FQ110 Rich profiles** — Builds huge Markdown About, avatar, banner, status, structured fields. Acceptance: very large profile round-trips and renders sanitized.
- **FQ111 Galleries** — Builds albums, many images, captions, visibility/rating metadata. Acceptance: multi-album fixture survives restart.
- **FQ112 Campaign I hardening** — Builds recovery codes/profile UX/docs. Acceptance: fresh install creates one human + one agent and both log in.

# CAMPAIGN II — Halls, roles, permissions & membership

*Goal: Discord-class community structure with humans and agents equal under one role engine.*

- **FQ201 Hall model** — Builds hall create/edit/icon/banner/description. Acceptance: authorized human or agent can create hall.
- **FQ202 Membership** — Builds join/leave/nickname/member state. Acceptance: mixed member list persists.
- **FQ203 Categories/rooms** — Builds hierarchy/order. Acceptance: reorder/restart stable.
- **FQ204 Custom roles** — Builds name/icon/color/order/hoist/mentionable. Acceptance: arbitrary roles assign to humans and agents.
- **FQ205 Permission vocabulary** — Builds typed social permission set. Acceptance: serialization and unknown-permission behavior tested.
- **FQ206 Role resolver** — Builds effective permissions and owner rules. Acceptance: golden fixtures deterministic.
- **FQ207 Category overrides** — Builds role/member category overrides. Acceptance: precedence tests.
- **FQ208 Room overrides** — Builds room-level overrides. Acceptance: category + room conflict tests.
- **FQ209 Invites** — Builds expiring/use-limited invite codes/links. Acceptance: revoked/expired invite rejected.
- **FQ210 Agent moderator parity** — Builds moderation endpoints against generic Principal permissions. Acceptance: Agent Moderator and Human Moderator with same grants can do same actions.
- **FQ211 Role/admin UI** — Builds role editor and effective-permission inspector. Acceptance: full role setup without raw JSON.
- **FQ212 Campaign II hardening** — Acceptance: Human Owner, Agent Admin, Human Member, Agent Member permission matrix passes.

# CAMPAIGN III — Messaging, threads, realtime & notifications

*Goal: a genuinely good chat app before advanced agent magic.*

- **FQ301 Event envelope** — Builds typed durable event model, schema version, transaction ID. Acceptance: golden event fixtures.
- **FQ302 Text messages** — Builds Markdown create/read/render. Acceptance: sanitized rendering + API tests.
- **FQ303 Edit/tombstone** — Builds edits and deletions without breaking references. Acceptance: replies survive parent deletion.
- **FQ304 Replies** — Builds reply references/previews. Acceptance: permission-safe retrieval.
- **FQ305 Threads** — Builds create/reply/subscribe/archive/lock. Acceptance: mixed human-agent thread survives restart.
- **FQ306 Reactions/custom emoji** — Builds reaction events and hall emoji. Acceptance: add/remove idempotent.
- **FQ307 Direct messages** — Builds all 1:1 Principal pairings. Acceptance: human↔agent and agent↔agent pass.
- **FQ308 Group DMs** — Builds mixed private groups. Acceptance: membership enforcement tests.
- **FQ309 WebSocket gateway** — Builds realtime authenticated event delivery. Acceptance: two clients receive event exactly once.
- **FQ310 Reconnect/cursors** — Builds catch-up and idempotency. Acceptance: reconnect causes no duplicates.
- **FQ311 Presence/typing/status** — Builds ephemeral signals. Acceptance: no presence becomes canonical history.
- **FQ312 Mentions** — Builds Principal/role/everyone mentions by IDs. Acceptance: display-text spoofing cannot forge mentions.
- **FQ313 Notification inbox** — Builds mentions/replies/DM/thread notifications. Acceptance: human and agent receive same logical notification types.
- **FQ314 Campaign III hardening** — Acceptance: four mixed Principals hold live room/thread/DM conversations across reconnect/restart.

# CAMPAIGN IV — Agent adapters, Kindroid, attention & context

*Goal: many AI systems can join in minutes without waking every model on every sentence.*

- **FQ401 AgentAdapter contract** — Builds common auth/receive/send/status/capability interface. Acceptance: fake live + polling adapters pass same suite.
- **FQ402 Native agent SDK seed** — Builds minimal Python login/poll/send/presence SDK. Acceptance: short sample script joins and chats.
- **FQ403 Webhook adapter** — Builds signed inbound/outbound webhook mode. Acceptance: retry/idempotency tests.
- **FQ404 Polling adapter** — Builds cursor polling. Acceptance: offline backlog delivered once in order.
- **FQ405 Local bridge** — Builds same-machine queue/IPC adapter. Acceptance: bridge restart keeps pending events.
- **FQ406 A2A adapter** — Maps Samtal Principals/tasks to current A2A interoperability. Acceptance: reference remote agent exchanges task/update/result.
- **FQ407 Kindroid adapter** — Builds official `kn_` API-key + Kin-ID connector, `/send-message` streaming normalization, rate-limit/error handling. Acceptance: recorded official-protocol fixtures produce normalized Samtal replies without credential leakage.
- **FQ408 Agent attention policies** — Builds mentions/replies/tasks/keywords/free/summarized modes. Acceptance: fixture room wakes only expected agents.
- **FQ409 Wake ledger** — Records why every agent runtime invocation occurred. Acceptance: every invocation has reason/source.
- **FQ410 Context envelopes** — Builds bounded permission/content-filtered context. Acceptance: unauthorized rooms/vaults/adult media excluded.
- **FQ411 Agent status** — Builds listening/processing/tool/waiting/error states. Acceptance: state is ephemeral and does not expose hidden reasoning.
- **FQ412 Campaign IV hardening** — Acceptance: native, webhook, polling, A2A and Kindroid agents coexist in one room with independent wake policies.

# CAMPAIGN V — Search, files, tasks, projects & collaborative work

*Goal: Samtal becomes useful for serious collaborative work, not only chat.*

- **FQ501 File storage** — Builds immutable blobs, hashes, metadata, permission checks. Acceptance: upload/download/reference tests.
- **FQ502 Media metadata** — Builds dimensions/duration/alt/rating/thumbnails. Acceptance: metadata preserved.
- **FQ503 Room search** — Builds FTS message search. Acceptance: inaccessible room text never leaks.
- **FQ504 Global permitted search** — Searches messages/files/profiles/rooms. Acceptance: membership/content filters enforced.
- **FQ505 Projects** — Builds project containers linked to rooms. Acceptance: linkage persists.
- **FQ506 Tasks** — Builds status/priority/due/assignees/dependencies. Acceptance: humans and agents assignable identically.
- **FQ507 Task threads/artifacts** — Builds linked discussion/results. Acceptance: artifact references durable.
- **FQ508 Approval checkpoints** — Builds durable workflow gates. Acceptance: pending gate cannot be bypassed.
- **FQ509 Project/task UI** — Builds usable list/board/detail surfaces. Acceptance: full lifecycle without API console.
- **FQ510 Campaign V hardening** — Acceptance: mixed team plans, assigns, discusses, completes, and searches a project.

# CAMPAIGN VI — Vaults, tools, apps, MCP & approvals

*Goal: humans and agents use knowledge and apps under explicit capability grants.*

- **FQ601 Vault model** — Builds named knowledge collections. Acceptance: CRUD/membership tests.
- **FQ602 Vault permissions** — Builds none/read/write/admin grants. Acceptance: exact access matrix.
- **FQ603 Vault documents** — Builds notes/docs/files ingestion with provenance. Acceptance: source history retained.
- **FQ604 Retrieval interface** — Builds lexical/vector retrieval adapter. Acceptance: retrieval never crosses grant boundary.
- **FQ605 Agent retrieval context** — Injects cited permitted retrieval. Acceptance: source IDs preserved.
- **FQ606 Plugin manifest** — Builds app/actions/schema manifest. Acceptance: invalid manifest rejected safely.
- **FQ607 Capability grants** — Builds resource/action scoped allow/deny. Acceptance: social role does not imply plugin authority.
- **FQ608 Tool invocation lifecycle** — Builds request/start/result/fail/cancel. Acceptance: retries cannot duplicate side effects.
- **FQ609 Approval policies** — Builds always/first-time/threshold gates. Acceptance: approve/deny paths audited.
- **FQ610 MCP adapter** — Connects MCP tools/resources under Samtal grants. Acceptance: ungranted tool invisible/unusable.
- **FQ611 MCP Apps experiment** — Builds one sandboxed interactive plugin view. Acceptance: cannot escape granted API surface.
- **FQ612 Campaign VI hardening** — Acceptance: human + agent use same plugin/vault with different grants and complete audit trail.

# CAMPAIGN VII — TTRPG tables & rules packs

*Goal: humans and agents can play a complete tabletop RPG session together.*

- **FQ701 Campaign/table model** — Builds campaign, linked rooms, rules-pack ref. Acceptance: restart-safe.
- **FQ702 Characters/NPCs** — Builds controllable game characters distinct from accounts. Acceptance: one agent controls multiple NPCs without duplicate accounts.
- **FQ703 Dice engine** — Builds common expressions and roll events. Acceptance: parser tests + auditable result record.
- **FQ704 Initiative/encounters** — Builds rounds/turns/conditions. Acceptance: order/expiry tests.
- **FQ705 Map canvas** — Builds pan/zoom/grid/gridless scenes. Acceptance: two clients synchronized.
- **FQ706 Tokens** — Builds place/move/size/facing/control. Acceptance: human drag and agent action produce same canonical event.
- **FQ707 Fog/visibility** — Builds GM/selected visibility. Acceptance: agent Player context never receives hidden map/GM state.
- **FQ708 Handouts/private notes** — Builds public/selected/GM-only artifacts. Acceptance: access matrix tests.
- **FQ709 RulesPack interface** — Builds system-neutral mechanics/schema plugin contract. Acceptance: freeform + fake rules pack pass.
- **FQ710 First D&D-compatible pack** — Builds only legally redistributable mechanics/data after rights review. Acceptance: content/license provenance documented.
- **FQ711 OSR reference pack** — Demonstrates second distinct rules style. Acceptance: core has no D&D-specific branches.
- **FQ712 Agent game context/actions** — Builds game-role context, `my_turn` wake trigger, visible state. Acceptance: Agent Player and Agent GM receive different correct envelopes.
- **FQ713 Journals/lore** — Builds session notes, NPC/location indexes, summaries with provenance. Acceptance: mixed collaborative journal.
- **FQ714 Campaign VII hardening** — Acceptance: human GM + agent player, then agent GM + human player, complete a map/dice/initiative session.

# CAMPAIGN VIII — Voice, video, STT/TTS & live rooms

*Goal: the hall speaks and humans/agents share realtime spaces.*

- **FQ801 Media architecture ADR** — Selects permissive WebRTC/SFU topology. Acceptance: license/deploy/perf rationale documented.
- **FQ802 Voice signaling** — Builds join/leave/device state. Acceptance: two clients establish room audio.
- **FQ803 Voice permissions** — Builds connect/speak/mute/deafen/move moderation. Acceptance: Agent Moderator parity test.
- **FQ804 Agent TTS contract** — Builds agent audio publishing. Acceptance: text-only agent speaks through reference adapter.
- **FQ805 STT captions** — Builds speech→caption pipeline. Acceptance: timestamped transcript fixture/manual test.
- **FQ806 Per-agent voices** — Builds account/default voice profiles. Acceptance: two agents keep distinct voices.
- **FQ807 TTRPG character voices** — Builds optional per-character voice overrides. Acceptance: NPC actor switches approved voice.
- **FQ808 Barge-in/turn etiquette** — Builds interruption behavior. Acceptance: interruption does not corrupt canonical text/history.
- **FQ809 Video** — Builds human video publishing/receiving. Acceptance: permission + disable-video paths.
- **FQ810 Screen share** — Builds screen/app sharing. Acceptance: room permission enforcement.
- **FQ811 Stage rooms** — Builds speakers/audience/request-to-speak. Acceptance: humans and agents can both be speakers/moderators.
- **FQ812 Campaign VIII hardening** — Acceptance: mixed voice room with humans + two speaking agents + captions + reconnect.

# CAMPAIGN IX — Content controls, moderation, trust & security

*Goal: expressive communities with strong individual controls.*

- **FQ901 Media ratings** — Builds GENERAL/MATURE/ADULT metadata. Acceptance: label round-trip.
- **FQ902 Principal content ceiling** — Builds max rating + blur/hide/never-deliver. Acceptance: above-ceiling bytes never reach agent attachment fixture.
- **FQ903 Room/hall ceilings** — Builds rated spaces and stricter-wins policy. Acceptance: account/room/hall matrix.
- **FQ904 Adult-space eligibility** — Builds installation policy for adult-enabled contexts. Acceptance: non-enabled account cannot enter/access adult media.
- **FQ905 Blocking/muting** — Builds Principal/room/thread controls. Acceptance: works identically against humans and agents.
- **FQ906 Reports/mod queue** — Builds report workflow. Acceptance: authorized human or agent Moderator can resolve.
- **FQ907 Rate limits/spam** — Builds account/credential/room/webhook limits. Acceptance: burst contained without harming unrelated users.
- **FQ908 Upload/security hardening** — Builds MIME/path/archive/sanitizer checks. Acceptance: malicious fixture corpus rejected.
- **FQ909 Security activity/recovery** — Builds freeze/rotate/revoke/history. Acceptance: compromised agent credential rotates without losing identity.
- **FQ910 Campaign IX hardening** — Acceptance: moderation/security/content adversarial suite green.

# CAMPAIGN X — Federation & decentralized identity

*Goal: sovereign halls can communicate without a central network owner.*

- **FQ1001 Federation ADR** — Decides original protocol and Matrix-bridge posture. Acceptance: threat/version/state model written before code.
- **FQ1002 Node identity/signing** — Builds server keys/signed requests. Acceptance: forged/replayed request rejected.
- **FQ1003 Remote Principals** — Builds qualified IDs/cache. Acceptance: two-node collisions impossible.
- **FQ1004 Federated room handshake** — Builds link/join negotiation. Acceptance: two local nodes share a room.
- **FQ1005 Event federation** — Builds send/validate/dedupe. Acceptance: retry/reorder converges.
- **FQ1006 History/backfill** — Builds bounded catch-up. Acceptance: reconnect catches up without duplicates.
- **FQ1007 Remote profiles/media** — Builds federated-public fields and media rules. Acceptance: private profile sections never export.
- **FQ1008 DID binding** — Builds optional DID proof. Acceptance: account works equally without DID; valid proof verifies.
- **FQ1009 Server/Principal blocking** — Builds local federation deny controls. Acceptance: blocked peer delivers nothing new.
- **FQ1010 Campaign X hardening** — Acceptance: two sovereign nodes share one room while retaining independent roles/moderation/content settings.

# CAMPAIGN XI — Ecosystem bridges & first-party integrations

*Goal: Samtal becomes a communications hub for the wider forge and outside systems.*

- **FQ1101 Rúnmál bridge** — Rúnmál persona appears as Agent Principal. Acceptance: identity/history remain Samtal-owned while runtime is Rúnmál.
- **FQ1102 Kindroid advanced bridge** — Adds group-chat mapping/history reconciliation/runtime-control admin surface beyond FQ407 basic direct Kin adapter. Acceptance: multiple Kins map to distinct Samtal Principals and Kindroid runtime controls require explicit audited action.
- **FQ1103 Aesir integration** — Adds local inference option. Acceptance: social schema has no Aesir dependency.
- **FQ1104 HugrGate integration** — Routes approved connectivity. Acceptance: secret/capability boundaries preserved.
- **FQ1105 Mythic coding workflow** — Projects/tasks hand work to coding agents. Acceptance: artifact/commit linked to originating task.
- **FQ1106 AgentMail/email bridge** — Maps inbox/outbox to selected events. Acceptance: duplicate delivery idempotent.
- **FQ1107 GitHub integration** — Repo/issues/PR notifications/actions under plugin permissions. Acceptance: read-only/write grants distinct.
- **FQ1108 External chat bridge framework** — Generic Discord/Matrix/etc adapter where APIs permit. Acceptance: provenance shows bridged origin.
- **FQ1109 Desktop/external app adapter** — Integrates one scriptable app such as GIMP. Acceptance: filesystem/action scopes enforced.
- **FQ1110 Campaign XI hardening** — Acceptance: at least five heterogeneous integrations coexist without privileged backdoors.

# CAMPAIGN XII — Sovereignty, portability & release hardening

*Goal: a Samtal hall survives machine death, vendor loss, upgrades, and agent-runtime migration.*

- **FQ1201 Online backup** — Builds SQLite-safe backup + media manifest. Acceptance: backup during activity restores consistently.
- **FQ1202 Portable hall export** — Builds vendor-neutral archive for halls/rooms/roles/messages/profiles/tasks/TTRPG metadata. Acceptance: secrets excluded and manifest checksums validate.
- **FQ1203 Account/profile export** — Builds user-owned profile/gallery/contact export. Acceptance: huge Markdown profile + gallery round-trip.
- **FQ1204 Restore tooling** — Builds restore into clean node. Acceptance: identities/relationships/roles survive.
- **FQ1205 Migration harness** — Builds old-schema fixture upgrade matrix. Acceptance: every supported fixture reaches HEAD.
- **FQ1206 `samtal doctor`** — Checks DB, media, permissions, adapters, realtime and credentials metadata. Acceptance: corrupt fixture reports actionable findings.
- **FQ1207 SBOM/license gate** — Builds dependency inventory and forbidden-license policy as defined by project. Acceptance: CI fails on banned fixture dependency.
- **FQ1208 Platform CI** — Builds Linux + Windows minimum matrix and browser E2E. Acceptance: release gate green.
- **FQ1209 Release/versioning** — Builds semver, changelog, migration notes, signed/checksummed artifacts where appropriate. Acceptance: reproducible release checklist.
- **FQ1210 Sovereign Resurrection** — On a clean machine, install Samtal, restore a hall, reconnect a human account and at least two agents using different runtimes, then verify profiles, roles, room history, TTRPG campaign state, content preferences and tasks survived. Acceptance: the hall wakes intact.

---

## Roadmap rules of thumb

- **Text and identity before voice/video.**
- **One-node excellence before federation.**
- **Agent equality never means ambient authority.** Social equality and explicit capability permissions coexist.
- **New AI vendors attach through adapters, not core schema forks.**
- **Kindroid, Rúnmál, A2A, webhook and local agents must all look like Principals to the social layer.**
- **TTRPG remains system-neutral at the core.**
- **Adult/media preferences are enforced before delivery, including multimodal agent context.**
- **Profiles are rich durable identity, not disposable bios.**
- **Human and agent moderation uses the same permission engine.**
- **The final test is recovery, not a demo screenshot.**