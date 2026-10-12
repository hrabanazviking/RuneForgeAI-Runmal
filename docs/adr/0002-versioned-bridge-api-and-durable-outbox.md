# ADR-0002 — Versioned bridge API and durable event outbox

Status: Accepted  
Date: 2026-10-12

## Context

VRChat/game/companion integrations will become external consumers of Rúnmál. Once outside software depends on an API, unversioned route/behavior changes become expensive. Companions may also initiate speech/events while a bridge is disconnected, so pure synchronous request/response is insufficient.

## Decision

- External bridge routes begin under `/api/v1/bridge/...` or carry an equivalent explicit protocol version.
- Bridge credentials are scoped and revocable.
- Retriable writes use idempotency keys.
- Proactive companion events use a durable/pollable outbox with ordered IDs, acknowledgement/checkpoint and replay semantics.
- Game-specific protocol details remain in adapters/reference bridges rather than Rúnmál core domains.

## Consequences

### Benefits

- bridges can evolve without accidental breaking changes;
- reconnects can recover missed proactive events;
- transport retries do not duplicate turns;
- bridge security is narrower than full application auth.

### Costs

- more protocol machinery than a few ad-hoc endpoints;
- event retention/checkpoint state must be stored;
- compatibility tests become part of bridge maintenance.

## Alternatives considered

**Unversioned internal-style API.** Rejected because it turns implementation details into accidental public contracts.

**Webhooks only.** Useful later, but not a sufficient durable source of truth when the receiver is offline.

**Game-specific endpoints in core.** Rejected because it couples Rúnmál domains to external game quirks.

## Evidence / references

- `../BRIDGE_PROTOCOL.md`
- `../DESIGN.md`
- `../ROADMAP.md`

## Supersession

None.