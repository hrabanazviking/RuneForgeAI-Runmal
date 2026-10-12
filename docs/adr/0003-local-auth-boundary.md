# ADR-0003 — Local auth boundary

**Status:** accepted (S102, 2026-10-12)

## Context

Rúnmál is a loopback-first local app (INV-024). Its HTTP API must be
usable by the local UI and local bridges, but must not be an open port
for anything else on the machine or network to drive.

## Decision

1. The server binds `127.0.0.1` by default (`runmal serve --host/--port`
   can override explicitly; the default never changes silently).
2. Every `/api/v1/*` route requires a bearer credential: a 32-byte
   `secrets.token_urlsafe` token generated on first run, stored
   owner-only (`0o600`) in the data dir, compared with
   `hmac.compare_digest`.
3. `/healthz` stays public (liveness only, no data).
4. **Browser-origin / session decision (initial):** no cookie sessions yet.
   The future browser UI (S109) will call same-origin with the bearer
   credential; CORS stays disabled by default. If a cookie session is
   ever introduced, it gets its own ADR and the bearer scheme remains
   for bridges/scripts.

## Consequences

- Local scripts and bridges present `Authorization: Bearer <token>`.
- The credential must never appear in responses, logs, traces, exports
  or diagnostics (INV-023); S102 tests assert absence.
- Losing the credential file means re-authenticating locally; there is
  no remote recovery by design.
