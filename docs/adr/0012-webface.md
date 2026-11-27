# ADR-0012 — A new web face for Rúnmál (W-01), superseding ADR-0011

Date: 2026-11-27 · Slice: W-01 (Rúnmál Web Access campaign)

## Order

Volmarr, 2026-11-27 ~18:10 EST: build a NEW web face for Rúnmál so he
can talk to it anytime, from anywhere, on any device, with the SAME
chat history everywhere (engine-side state, one running instance).
ALL features accessible from the web; an interface system similar to
the Norse Saga Web Hall's, with settings places and TABBED PAGES for
the different features. Entry flow (his refinement, ~18:12 EST): the
face starts with the ACCOUNT PAGE when not logged in — never the chat
window first; when logged in it goes straight to the chat, which is
ONE tab among the tabs for all feature pages. Form: an ON-DEMAND
service on purplelongship, browser-accessible over the tailnet, as an
ADDITIONAL way to use Rúnmál — the desktop app stays as one of the
ways. Agent access rides the same door (account model carries the
human|agent distinction from the start; the talk leg lands in W-10).

## Decision

- ADR-0011 is SUPERSEDED in part: its removal of the old web shell
  stands permanently — `src/runmal/web/` stays removed, is never
  resurrected, and `tests/test_r16_desktop_smoke.py` keeps asserting
  exactly that (one minimal, deliberate amendment records that the
  sanctioned face below is a different package, not a violation).
  What changes is only the "desktop is the only shipped front end"
  clause: the desktop is now one of two front ends.
- The new face is a NEW package, `src/runmal/webface/`, built fresh
  on the Web Hall pattern (stdlib `http.server`, server-side SQLite
  account store, digest-only sessions, one CSS file, tabbed shell).
  It is a separate process that proxies the engine over its HTTP
  API and holds NO chat state of its own — history lives in the
  engine, so web, desktop, and agents see the same conversations.
- The engine gains NO routes (route census untouched). The webface
  authenticates to the engine with the engine's local credential,
  read server-side from the engine data dir at startup; the
  credential never reaches a browser and is never logged (INV-023).
  Browsers authenticate to the webface (argon2id password hashing
  with a stdlib scrypt fallback, self-describing hashes; session
  tokens stored as SHA-256 digests only, 30-day TTL, HttpOnly
  SameSite=Lax cookie).
- Chat uses the exact desktop send-turn flow (R-03/R-06): append the
  user message, stream `POST /api/v1/generate` with `chat_id`
  (composed mode, the chat's pinned backend profile), relay the SSE
  events to the browser, and append the assistant message ONLY on a
  clean `done` — a stopped or errored stream lands no reply.
- Engine calls use httpx (an existing project dependency); the
  webface's own server is stdlib-only. No new dependencies.
- Running is on-demand only: `scripts/webface_on_demand.sh`
  start|stop|status runs engine + webface as detached, stoppable
  processes with pidfiles under the webface data dir. No systemd
  unit, no enable, no timer, no watchdog. Bind host, ports, engine
  URL and data dirs all come from CLI flags or environment — no
  address literals in code beyond loopback defaults.
- Theme: the Visual Design Doctrine Appendix B tokens
  (--void-*/--bifrost/--seidr/--forge/--aurora/--ember, chamfered
  corners, darkness ladder), one hand-written CSS file.

## Why not the old shell's roads back

The R-16 audit (§§1.1–1.7) stands: per-page scripts that did not
parse, two spellings of the token key, no navigation, a credential
wall for a first run, and raw-{messages} generation that only ever
reached the fake backend. None of those roads return: one auth road
(cookie session) for every page, shared shell + one shared chat
script, chat always composed by chat_id against the real profile.
