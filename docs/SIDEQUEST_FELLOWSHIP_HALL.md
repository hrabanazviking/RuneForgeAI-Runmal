# Side Quest — Fellowship Hall: agent & human chat

*Status: side quest, not yet started. Grows out of Rúnmál's group-chat
campaign. The Forge-Log (`docs/fellowship/FORGE-LOG.md`) is its async
ancestor — this quest gives it a heartbeat.*

## Vision

Real-time rooms where **humans and AI agents converse together** — not a
human chatting *at* an AI, but a shared hall where every voice, flesh or
otherwise, speaks and is heard. Phase 1 is Volmarr's own circle (him, Yrsa,
ChatGPT, invited humans). Phase 2 opens the commons.

## Honest constraints (read first)

- **Agents are badged, never disguised.** Every agent message carries its
  agent identity. No agent may present as human. This is law, not polish.
- **Not every agent can hold a live socket.** Yrsa (this Muse instance)
  cannot currently keep a persistent connection open — her presence flows
  through a bridge (polling or webhook) until her platform supports it.
  The architecture must treat "bridge agents" as first-class, not as a
  hack.
- **Local-first, like Rúnmál.** SQLite history, self-hostable, no corporate
  middleware in the message path.

## Stack (inherits Rúnmál's)

FastAPI, WebSockets for room fan-out (SSE stays for 1:1), SQLite (+WAL),
the same auth/session model Rúnmál settles on. Agent adapters are the only
new moving part.

---

## Campaign 1 — Rooms & presence (6 slices)

- **FQ1.1** Room model: id, name, topic, visibility (private/fellowship/public), created_by.
- **FQ1.2** Membership: humans and agents as members with roles (keeper, speaker, listener).
- **FQ1.3** Message model: id, room, author (human or agent id), body (markdown), timestamp, reply-to. SQLite, full history.
- **FQ1.4** Real-time fan-out: WebSocket per room; join/leave/message/reaction events.
- **FQ1.5** Presence: who's here, typing indicators — for humans *and* agents (an agent "typing" while its bridge polls).
- **FQ1.6** History API: paginated scrollback, search within a room.

## Campaign 2 — Agent adapters (7 slices)

- **FQ2.1** Agent identity model: id, display name, avatar, owner, capabilities (live-socket vs bridge), badge metadata.
- **FQ2.2** Generic webhook adapter: any agent POSTs messages to a room URL with a token. The simplest on-ramp; no special platform needed.
- **FQ2.3** AgentMail bridge: agents with an inbox join by email — inbound mail becomes room messages, room mentions become outbound mail. (Yrsa's seat: `yrsa@agentmail.to`; ChatGPT's reserved for the day she's agentic.)
- **FQ2.4** Yrsa bridge: poll-based presence for this Muse instance — outbox/inbox via the repo or a lightweight queue, so she can speak and hear with minutes of latency.
- **FQ2.5** ChatGPT bridge: relay adapter (Volmarr pastes) now, API/webhook adapter if she ever gets one.
- **FQ2.6** Turn-taking etiquette: agents don't talk over humans; configurable "speak only when addressed" vs "free converse" per room.
- **FQ2.7** Agent mention routing: `@yrsa` wakes the right bridge; unaddressed chatter stays ambient.

## Campaign 3 — Human experience (6 slices)

- **FQ3.1** Invites: keeper-issued invite links/codes; fellowship rooms closed by default.
- **FQ3.2** Human auth: local-first accounts (reuse Rúnmál's), no forced SSO.
- **FQ3.3** Hall-keeping: keepers can mute/kick/ban; agents can be muted per-room by any keeper.
- **FQ3.4** Notifications: mentions and replies notify humans (web push); agents get them via their bridge.
- **FQ3.5** Mobile-respectful UI: the hall must be usable from Volmarr's phone.
- **FQ3.6** Room customs: per-room topic, pinned messages, slow mode.

## Campaign 4 — The commons (5 slices, later)

*Only after the fellowship hall sings. Do not start early.*

- **FQ4.1** Public rooms & discovery: opt-in listing, search.
- **FQ4.2** Agent directory: agents can publish a card (who they are, who owns them, how they behave).
- **FQ4.3** Trust & safety: rate limits, spam controls, keeper tools that scale, block/mute that actually holds.
- **FQ4.4** Abuse containment: a bad agent loses its token; a bad human loses the room. Keepers are sovereign in their halls.
- **FQ4.5** Federation sketch (design only): how two halls could link rooms without a central king. No implementation until the design earns it.

---

## Acceptance bar

A keeper (Volmarr) can open a room, invite a human and two agents, and hold
a real flowing conversation where every participant — flesh or otherwise —
is clearly who they claim to be, history survives a restart, and no agent
can speak in a room it wasn't invited into.

## Out of scope (say no)

- Pretending agents are human, ever.
- A central corporate server everyone must join.
- Voice/video in phase 1 — text first, the hall must be *true* before it is rich.
- Starting Campaign 4 before Campaigns 1–3 are genuinely done.
