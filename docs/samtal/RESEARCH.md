# Samtal Research Notes — Open Standards Worth Learning From

*Verified 2026-10-12. Prefer current primary specifications at implementation time; protocol versions can move.*

## 1. Agent2Agent (A2A)

A2A is an open standard for communication/collaboration between AI agents built on different frameworks/vendors. The current official documentation describes it as a common language for agent interoperability and explicitly positions it alongside MCP: agents communicate through A2A and use tools/data through MCP.

Useful Samtal ideas:

- agent discovery/cards;
- tasks and task lifecycle;
- remote agent interoperability;
- framework neutrality;
- streaming/push-style task updates where supported.

Samtal should use A2A as an **adapter/interoperability protocol**, not replace its richer social model with A2A.

Official: https://a2a-protocol.org/

## 2. Model Context Protocol (MCP)

Current official MCP SDK documentation describes the protocol as an open standard connecting AI applications to systems where tools and data live. Current stable v2 TypeScript SDK documentation implements the `2026-07-28` MCP spec revision and exposes core concepts including tools, resources and prompts.

Useful Samtal ideas:

- interoperable tool servers;
- resource retrieval;
- typed tool schemas;
- authorization building blocks;
- MCP Apps for interactive embedded tool UI;
- Skills extension for workflow instructions.

Samtal should sit **above** MCP for identity, hall permissions, per-agent grants, approval and audit.

Official docs: https://modelcontextprotocol.io/
SDK docs: https://ts.sdk.modelcontextprotocol.io/v2/
MCP Apps: https://apps.extensions.modelcontextprotocol.io/

## 3. Matrix

Matrix defines open APIs for decentralized communication and federation. Its official specification uses users/devices, typed events, rooms, room state, client-server APIs and server-server federation. Event bodies are explicitly treated as untrusted data, and custom event types are supported.

Useful Samtal ideas:

- event-oriented communication;
- opaque identifiers;
- room-state concepts;
- custom namespaced events;
- sync/backfill;
- federation signatures;
- protocol/version discipline;
- bridge/application-service lessons.

Things not to inherit blindly:

- complexity accumulated from global-scale federation;
- state-resolution machinery before Samtal genuinely needs equivalent behavior;
- identifiers or semantics chosen for Matrix compatibility rather than Samtal's use cases.

Official: https://spec.matrix.org/

## 4. WebAuthn / passkeys

Web Authentication Level 3 became a W3C Recommendation on **2026-08-25**. It defines public-key credentials scoped to relying parties and mediated by authenticators/user agents.

Samtal direction:

- make passkeys a first-class human login option;
- keep username/password available where appropriate;
- do not make wallet/DID login mandatory.

Official: https://www.w3.org/TR/webauthn-3/

## 5. Decentralized Identifiers (DIDs)

W3C DID Core v1.0 is a Recommendation; DID Core v1.1 is in the 2026 standards process.

Useful Samtal direction:

- optional DID binding for a human, agent or server Principal;
- cryptographic proof independent of a corporate account;
- possible federation identity portability.

Do not confuse decentralized identity with mandatory blockchain use. DID methods vary.

Official: https://www.w3.org/TR/did-core/

## 6. Discord / Slack feature anatomy to learn from

Conceptual product lessons worth matching or adapting:

### Discord-class

- server/hall + category + channel hierarchy;
- rich custom roles and permission overrides;
- voice rooms;
- stage/event spaces;
- reactions, custom emoji/stickers;
- threads/forums;
- strong community moderation;
- expressive profiles/presence;
- bots/apps as community participants.

### Slack-class

- workspaces/channels/DMs;
- threads;
- search;
- files;
- workflows/apps;
- work/task integrations;
- rich link/app cards;
- enterprise-style audit/administration concepts.

Samtal's implementation remains independent. We are learning product/problem shapes, not copying code.

## 7. TTRPG platform lessons

Virtual tabletops converge on a useful primitive set:

- scenes/maps;
- grid/gridless canvas;
- tokens;
- fog of war;
- character sheets;
- dice;
- initiative;
- journals/handouts;
- GM-private state;
- system/rules modules.

Samtal's differentiator is not merely embedding a VTT: **agents are native players/GMs using the same identity, room, permission, voice and tool infrastructure as humans.**

## 8. Architectural conclusions

1. Use one `Principal` social abstraction for humans and agents.
2. Keep provenance type separate from role/rank.
3. Build an event-based internal protocol.
4. Keep IDs opaque.
5. Separate event delivery from expensive agent wake/inference.
6. Build explicit context envelopes.
7. Keep social permissions separate from external tool capabilities.
8. Use A2A for agent interoperability and MCP for tools/resources where they help.
9. Learn federation from Matrix but delay it.
10. Make passkeys easy; make DIDs optional.
11. Treat TTRPG state as first-class structured data.
12. Make profile expression far richer than ordinary chat apps.
13. Enforce content preferences before media delivery, including for multimodal agents.

## 9. Questions to verify before implementation campaigns

- Which Python/JS WebAuthn libraries have the best current maintenance/license posture?
- Which A2A SDK version/profile should the reference adapter target at build time?
- Which MCP SDK/runtime best fits Samtal's Python-first implementation?
- Whether to hand-roll WebRTC signaling/media topology first or use a permissively licensed SFU/framework.
- Which Markdown renderer/sanitizer combination provides the desired GFM richness safely.
- Object/media storage strategy once deployments outgrow local filesystem.
- Whether federation should be original Samtal protocol, Matrix-compatible bridge, or both.
- Which D&D rules content is legally redistributable in a first-party rules pack; keep the tabletop engine system-neutral regardless.
