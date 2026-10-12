# Samtal First-Party Plugin Roadmap

*Detailed sub-roadmap for making the RuneForgeAI ecosystem usable inside Samtal. These slices elaborate the plugin/workspace work owned broadly by Samtal Campaign VI and Campaign XI.*

## Rules

Each slice includes implementation, tests, permissions, dual-interface behavior and documentation.

A first-party app is **not** allowed to bypass Samtal's plugin/capability system merely because Volmarr owns both projects.

## Phase A — Plugin foundation

- **FP001 Manifest schema** — Builds: versioned plugin/app manifest with actions, resources, artifacts, permissions, UI surfaces, agent surfaces and health metadata. Acceptance: valid fixtures load; malformed/unknown-required fields fail legibly.
- **FP002 Plugin registry** — Builds: discover/install/enable/disable/update/remove registry. Acceptance: registry survives restart and disabled app exposes no actions.
- **FP003 Action schema registry** — Builds: typed JSON-schema-like action definitions discoverable by authorized agents and human UI. Acceptance: agent can enumerate only permitted actions.
- **FP004 Resource schema** — Builds: typed read/list/query resources separate from mutating actions. Acceptance: read permission does not imply mutation.
- **FP005 Dual-interface adapter contract** — Builds: common binding from domain action to human control and agent action. Acceptance: one fixture operation works from UI and API and creates identical canonical event/state.
- **FP006 Artifact contract** — Builds: input/output artifact references, revisions, lineage and MIME/custom type declarations. Acceptance: artifact produced by one plugin can be consumed by a second without manual copy/paste.
- **FP007 Event contract** — Builds: plugin subscribe/publish topics through Samtal's event bus. Acceptance: plugin receives only granted topics and duplicate delivery is idempotent.
- **FP008 Secret binding** — Builds: secret references injected server-side, never embedded in plugin manifest or room content. Acceptance: negative leak tests.
- **FP009 Capability scopes** — Builds: action/resource/network/filesystem/device scopes. Acceptance: denied scope blocks execution even for Hall Owner unless explicitly granted.
- **FP010 Invocation ledger** — Builds: request/approval/start/progress/result/failure/cancel history. Acceptance: every mutation is attributable to the acting Principal and plugin version.
- **FP011 Health/version compatibility** — Builds: plugin health probes and API compatibility ranges. Acceptance: incompatible update is refused rather than silently breaking a workspace.
- **FP012 App directory UI + API** — Builds: searchable human app directory and machine-readable registry API. Acceptance: humans and agents can discover the same installable capabilities.

## Phase B — RuneForgeAI core infrastructure

- **FP101 Project A.E.S.I.R. plugin** — Builds: model listing/loading/health/inference/benchmark actions and optional runtime-provider registration. Acceptance: Samtal agent uses Aesir without social schema depending on Aesir.
- **FP102 Verðandi event bridge** — Builds: scoped event publish/subscribe/query integration. Acceptance: Samtal project event reaches permitted local subscriber and unauthorized topic does not.
- **FP103 Muninn memory provider** — Builds: scoped search/read/write/provenance operations. Acceptance: two Principals with different grants see different allowed memory sets.
- **FP104 Mímir-Vörðr verification plugin** — Builds: retrieve/verify/ground/compare operations with evidence artifact output. Acceptance: verification result links claims to source lineage.
- **FP105 Bifröst/HugrGate gateway plugin** — Builds: health/routing/reachability and explicitly scoped route operations. Acceptance: no route opens without matching network capability.
- **FP106 WYRD world-state provider** — Builds: entity/location/relationship/state-transition/snapshot resources. Acceptance: TTRPG/project agent queries canonical world state through typed resource API.
- **FP107 Runa/persistent-agent bridge** — Builds: Runa Principal connector preserving its native memory/tools/subagents while using Samtal social identity. Acceptance: runtime restart does not create duplicate Samtal Principal.
- **FP108 Rúnmál bridge** — Builds: character-as-Principal, bounded room context, reply/voice hooks and permitted memory/persona actions. Acceptance: a Rúnmál character joins a Samtal mixed-agent room under normal roles.

## Phase C — Mythic Engineering studio

- **FP201 Mythic project plugin** — Builds: create/map/status/project resources. Acceptance: Samtal project room links to Mythic project state.
- **FP202 Work-order actions** — Builds: create/claim/assign/complete work orders and slices. Acceptance: human and agent can claim through equal interfaces.
- **FP203 Builder orchestration** — Builds: invoke configured coding/research/audit agents with bounded task/artifact context. Acceptance: multi-agent job produces linked artifact revisions.
- **FP204 Test/verification integration** — Builds: run tests, ingest results, create failures/tasks. Acceptance: failed test produces structured artifact and optional task.
- **FP205 Architecture/decision workspace** — Builds: docs/ADR/project-map surfaces. Acceptance: changes from UI and agent actions share revision history.
- **FP206 Council review workflow** — Builds: fan-out specialist review, independent results, synthesis/acceptance. Acceptance: no reviewer sees other draft before independent phase unless configured.

## Phase D — Spiritual, symbolic and creative apps

- **FP301 Astrology engine core** — Builds: canonical chart calculation adapter and saved ChartArtifact. Acceptance: same input yields deterministic canonical chart data independent of interpreting agent.
- **FP302 Astrology human workspace** — Builds: chart wheel, placements, aspects, houses, notes, saved charts. Acceptance: chart can be created/edited/exported without API console.
- **FP303 Astrology agent actions** — Builds: natal/transit/synastry/composite/solar-return/progression/aspect/render/export actions. Acceptance: agent creates chart and human immediately sees identical workspace state.
- **FP304 Astrology collaboration** — Builds: multi-agent interpretations linked to one chart, comparison and synthesis. Acceptance: three agents produce separately attributable interpretations without duplicating canonical calculations.
- **FP305 Tarot engine** — Builds: decks, spreads, draws, positions, reveal state and SpreadArtifact. Acceptance: deterministic seeded test and ordinary random-use path both work.
- **FP306 Tarot human table** — Builds: visual spread/table/notes/correspondences. Acceptance: human edits and agent observations share state.
- **FP307 Tarot agent actions** — Builds: draw/place/reveal/annotate/render/export actions. Acceptance: Agent Reader can run permitted spread through API.
- **FP308 Hermetic correspondence layer** — Builds: optional Qabalah/astrology/element/system metadata for Volmarr's deck/workflows. Acceptance: optional layer does not contaminate unrelated deck schemas.
- **FP309 Norse Saga Engine plugin** — Builds: campaign/world/NPC/time/event/faction integration. Acceptance: one Samtal TTRPG room uses engine state without core Samtal knowing Norse-specific schema.
- **FP310 Spiritual artifact interchange** — Builds: charts, spreads, ritual/reference notes and related artifacts can be attached to rooms/projects/vaults. Acceptance: permissions/content visibility preserved across plugins.

## Phase E — Displays, senses and creative tooling

- **FP401 Aurelia adapter** — Builds only against actual exposed Aurelia sensory interfaces; image/audio/environment resources where supported. Acceptance: no invented unsupported capabilities; permitted observation becomes typed artifact/event.
- **FP402 Kiosk/display plugin** — Builds: show artifact/dashboard/message/clear/state actions with per-device scope. Acceptance: one agent can control allowed display and cannot reach another.
- **FP403 ComfyUI/Stable Diffusion workspace** — Builds: workflow execution, input/output artifacts, visual queue and agent actions. Acceptance: human and agent use same saved workflow with scoped model/filesystem access.
- **FP404 GIMP/Krita bridge** — Builds: file/plugin/automation integration for image artifacts. Acceptance: agent transform and human visual edit create one revision chain.
- **FP405 Blender bridge** — Builds: approved scripted operations, artifact/render outputs and later remote UI option. Acceptance: arbitrary unrestricted script execution remains disabled by default.
- **FP406 Jupyter workspace** — Builds: notebooks as project artifacts, kernel action policy and agent-run cells under scoped environment. Acceptance: notebook lineage and outputs survive session restart.
- **FP407 Code workspace** — Builds: code-server/OpenVSCode-style human workspace plus typed repository actions for agents. Acceptance: same project tree/artifacts visible from both surfaces.
- **FP408 Whiteboard/diagram workspace** — Builds: Excalidraw/tldraw/diagram integration with machine-readable board state where feasible. Acceptance: human creates shape and agent can inspect/modify permitted board objects.

## Phase F — Future forge protocol

- **FP501 Plugin SDK** — Builds: Python reference SDK plus protocol documentation. Acceptance: sample external plugin implements action/resource/artifact/event surfaces without core changes.
- **FP502 Conformance suite** — Builds: automated tests for auth, permissions, dual interfaces, secrets, cancellation, artifacts, events, updates and uninstall. Acceptance: intentionally broken fixture plugins fail expected gates.
- **FP503 Generated bindings** — Builds: OpenAPI/action-schema helpers for agent and UI clients. Acceptance: reference client invokes sample plugin with generated types.
- **FP504 Plugin templates** — Builds: templates for workspace app, tool plugin, data provider, agent bridge and artifact processor. Acceptance: each template launches and passes smoke conformance.
- **FP505 Plugin marketplace/catalog format** — Builds: decentralized/self-hostable catalog metadata without requiring a single corporate store. Acceptance: two catalogs can provide installable manifests to one hall.
- **FP506 Sovereign plugin export/restore** — Builds: plugin config/grants/workspace state export with secrets excluded. Acceptance: restore on clean Samtal node recreates integrations after secrets are rebound.

## Final acceptance

A single Samtal project room can use at least:

- one RuneForgeAI infrastructure plugin;
- the Mythic Engineering studio;
- astrology;
- tarot;
- one world/TTRPG integration;
- one external creative workspace;
- humans and agents using both interfaces;

while preserving one shared permission, artifact, event and audit model.

The success criterion is not that Samtal contains all apps. It is that **all apps can become citizens of the same workshop without surrendering their independence.**
