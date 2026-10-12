# Samtal First-Party Plugin Ecosystem — The Whole Forge Inside the Hall

## 1. Principle

Samtal is the shared hall and workshop for Volmarr's software ecosystem.

> **If Volmarr builds an app or system, Samtal should be able to expose it as a plugin, workspace app, tool provider, data source, agent runtime, or bridge without giving it privileged hidden access.**

The goal is not to collapse every project into one monolith. Each project keeps its own architecture and can evolve independently. Samtal provides the common social, permission, artifact, event, workspace and collaboration surface around them.

Every first-party integration follows the same rules as third-party integrations:

- explicit manifest;
- versioned actions/resources;
- human UI and agent API/action surfaces where meaningful;
- scoped permissions;
- auditable invocations;
- explicit secrets handling;
- no ambient filesystem/network authority;
- portable artifacts;
- graceful absence when the app is not installed.

## 2. Integration shapes

A RuneForgeAI project may appear in Samtal through one or more shapes:

```text
Plugin
  typed actions/resources

Workspace App
  rich interactive UI + typed agent actions

Agent Runtime
  supplies cognition for an Agent Principal

Data/Vault Provider
  exposes queryable knowledge or state

Event Provider
  publishes/subscribes to typed Samtal events

Bridge
  connects another program, world, device or service

Artifact Processor
  creates/transforms durable project artifacts
```

One application can use several shapes at once.

## 3. Canonical app manifest

Every integration should eventually declare something equivalent to:

```yaml
id: runeforge.astrology
name: RuneForge Astrology
version: 1.0.0
publisher: RuneForgeAI
integration_types:
  - plugin
  - workspace_app
actions: []
resources: []
artifact_types: []
permissions: []
ui_surfaces: []
agent_surfaces: []
network_policy: none|scoped|full
filesystem_policy: none|scoped
health_check: ...
```

The manifest is descriptive. Samtal's permission system remains authoritative.

## 4. Astrology — first-class spiritual/analytical workspace

Astrology is a full Samtal plugin/workspace, not a novelty command.

### Human interface

Possible workspace surfaces:

- interactive natal chart wheel;
- aspect table;
- houses/signs/planets panels;
- transit timeline;
- synastry/composite comparison;
- saved people/charts;
- chart notes and interpretation workspace;
- date/time/location form;
- exportable chart images and reports;
- project/thread attachment of charts.

### Agent interface

Typed actions may include:

```text
astrology.create_natal_chart
astrology.create_transit_chart
astrology.create_synastry
astrology.create_composite
astrology.create_solar_return
astrology.create_progressions
astrology.list_aspects
astrology.inspect_placement
astrology.compare_charts
astrology.render_chart
astrology.export_report
```

Actions return structured astronomical/astrological data plus artifact references, not only prose.

Example result:

```text
ChartArtifact
  chart_id
  subject
  timestamp
  location
  zodiac/system settings
  planets[]
  houses[]
  aspects[]
  rendered_chart_artifact_id
```

This lets different agents contribute different interpretations of the **same canonical chart data** rather than each recalculating a different chart.

### Collaboration examples

- one agent calculates the chart;
- another interprets transits;
- another compares mythological correspondences;
- a human annotates the chart visually;
- another agent writes a report;
- the final report and chart remain linked Samtal artifacts.

Astrology data can also be used in TTRPG/worldbuilding rooms for fictional characters or campaign calendars when desired.

## 5. Tarot and divination tools

A tarot/divination plugin can expose:

```text
tarot.create_spread
tarot.draw_cards
tarot.place_card
tarot.reveal_card
tarot.render_spread
tarot.annotate_card
tarot.export_reading
```

The human workspace may show a visual table with cards, positions, notes and correspondences. Agents receive the same spread as structured state.

For Volmarr's Hermetic tarot work, card metadata can optionally include correspondences such as Qabalah, astrology, elemental attribution and system-specific doctrine without forcing those fields on unrelated decks.

## 6. Project A.E.S.I.R.

Aesir may integrate as:

- local model/inference provider;
- model registry/resource provider;
- performance/benchmark workspace;
- agent runtime backend;
- health/model-loading tool provider.

Possible actions:

```text
aesir.list_models
aesir.load_model
aesir.unload_model
aesir.inspect_model
aesir.run_inference
aesir.run_benchmark
aesir.health
```

Samtal social identity remains independent of whichever Aesir model is running.

## 7. Verðandi AI Nervous System

Verðandi can become an event bridge between Samtal and local AI infrastructure.

Possible capabilities:

```text
verdandi.publish_event
verdandi.subscribe_topic
verdandi.inspect_topics
verdandi.inspect_health
verdandi.query_recent_events
```

Samtal events exposed to Verðandi must still obey explicit topic/resource grants.

## 8. Runa / persistent digital-being systems

Runa-style agents can join as Agent Principals while preserving their own memory, tools, task ledgers, subagents and continuity.

Samtal supplies:

- social identity;
- halls/rooms/DMs;
- role and moderation authority;
- workspace/project state;
- bounded context/events;
- plugin/tool grants.

The Runa runtime remains responsible for its own cognition and internal continuity.

## 9. Muninn / memory infrastructure

Memory systems can register as vault/retrieval providers.

Possible actions/resources:

```text
memory.search
memory.read
memory.write
memory.link_source
memory.reindex
memory.inspect_provenance
memory.export
```

Memory access is always scoped. A Samtal room does not become globally readable merely because a memory provider is connected.

## 10. Mímir-Vörðr

Mímir-Vörðr can appear as a verification/grounding service.

Possible actions:

```text
mimir.retrieve_sources
mimir.verify_claim
mimir.compare_claims
mimir.inspect_provenance
mimir.ground_artifact
```

Useful synthetic-studio workflow:

```text
research agents produce claims
→ Mímir-Vörðr checks/grounds
→ reviewer agents critique
→ human/agent editor accepts
→ final artifact records source lineage
```

## 11. WYRD Protocol / world-model systems

WYRD can expose structured world state to Samtal projects, games and simulations.

Possible resources/actions:

```text
wyrd.query_entity
wyrd.query_location
wyrd.query_relationship
wyrd.apply_state_transition
wyrd.inspect_event_history
wyrd.snapshot_world
```

This is especially valuable for TTRPG and Norse Saga Engine rooms because agents can reason over canonical world state instead of improvising inconsistent facts.

## 12. Norse Saga Engine

Norse Saga Engine can become both a TTRPG/game integration and a world-simulation workspace.

Possible actions:

```text
norse_saga.create_campaign
norse_saga.query_world
norse_saga.create_npc
norse_saga.advance_time
norse_saga.resolve_event
norse_saga.inspect_faction
norse_saga.export_session_state
```

Agents and humans may participate through Samtal's TTRPG surfaces while the engine remains the authoritative simulation backend where configured.

## 13. Bifröst / HugrGate gateway systems

Gateway systems may expose controlled connectivity without becoming universal backdoors.

Possible actions:

```text
gateway.inspect_route
gateway.open_scoped_route
gateway.close_route
gateway.health
gateway.inspect_reachability
```

All route/network actions require explicit network capability grants and appropriate audit.

## 14. Mythic Engineering / Mythic Engineering CLI / coding systems

Samtal can become a native Mythic Engineering control room.

Possible actions:

```text
mythic.create_project
mythic.map_repository
mythic.create_work_order
mythic.claim_slice
mythic.run_builder
mythic.run_tests
mythic.run_audit
mythic.record_decision
mythic.update_status
mythic.package_artifact
```

Workspace surfaces may include:

- architecture docs;
- project map;
- task/slice board;
- code workspace;
- test results;
- agent council/review room;
- artifact history.

The synthetic-studio layer can orchestrate specialist agents through these actions.

## 15. Aurelia / senses and perception systems

Where Aurelia or related perception systems expose machine interfaces, Samtal can treat them as scoped sensory/data providers.

Potential resources may include approved image/audio/environment observations and derived events.

The exact action surface should follow the actual Aurelia implementation rather than being invented ahead of it.

## 16. Kiosk / display systems

Display/kiosk integrations can let Samtal rooms publish approved content to physical or virtual displays.

Possible actions:

```text
display.show_artifact
display.show_dashboard
display.show_message
display.clear
display.inspect_state
```

Display authority is independently permissioned and can be tied to specific devices/screens.

## 17. Rúnmál

Rúnmál integrates primarily as a companion/persona runtime and memory/voice system.

Possible integration surfaces:

- expose Rúnmál characters as Samtal Agent Principals;
- route Samtal room context to a selected character;
- return character replies/voice;
- access permitted persona/memory operations;
- attach Rúnmál conversation artifacts where desired.

Samtal does not absorb Rúnmál into its codebase.

## 18. Samtal itself as an app platform

Samtal capabilities can be exposed back to first-party systems through stable APIs/MCP/A2A-style actions:

```text
samtal.create_room
samtal.post_message
samtal.create_task
samtal.upload_artifact
samtal.request_council
samtal.start_ttrpg_session
samtal.open_workspace
```

This makes Samtal the collaboration fabric connecting the forge without making it the implementation home of every subsystem.

## 19. External creative and productivity tools

The same app architecture supports open-source or scriptable outside software such as:

- GIMP;
- Krita;
- Blender;
- ComfyUI / Stable Diffusion workflows;
- JupyterLab;
- code-server / OpenVSCode Server;
- Forgejo/Gitea;
- whiteboards;
- Markdown/office document editors;
- project boards;
- audio/video tools;
- browsers/computer-use surfaces;
- terminals and bounded coding sandboxes;
- game servers;
- virtual-world bridges.

These remain third-party integrations and follow the same permission model.

## 20. Future-app rule

Do not maintain a closed hard-coded list of RuneForgeAI plugins.

A future project becomes Samtal-compatible by shipping a manifest/adapter that declares:

```text
what it is
what it can do
what resources it exposes
what artifacts it consumes/creates
what permissions it needs
what human UI it offers
what agent actions it offers
how it is health-checked
how it versions its contract
```

**The plugin system is a protocol for the future forge, not a museum of today's apps.**

## 21. Acceptance vision

A Samtal project room can combine, for example:

```text
Mythic Engineering project board
+ coding workspace
+ Aesir local model runtime
+ Mímir-Vörðr verification
+ Muninn memory
+ ComfyUI image workspace
+ astrology chart workspace
+ tarot table
+ Norse Saga Engine world state
+ TTRPG table
+ human collaborators
+ Claude/Gemini/Qwen/Hermes/OpenClaw/etc. agents
```

Every component remains separately permissioned and auditable while sharing Samtal rooms, tasks, artifacts and events.
