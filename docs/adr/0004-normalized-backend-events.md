# ADR-0004 — Normalized backend events and cancellation

Status: Accepted
Date: 2026-10-12

## Context

Campaign III introduces the `ChatBackend` seam (S301). Two shapes competed:
the S108 generation stub emits SSE dicts like `{"type": "token"}`, while
BACKEND_CONTRACT section 3 defines a normalized event vocabulary
(`TextDelta`, `UsageUpdate`, `Done`, `Error`).

## Decision

- Backends yield typed normalized events (`TextDelta`, `UsageUpdate`,
  `Done`); each has a `to_dict()` with `type` values `text_delta`, `usage`,
  `done`, `error`.
- Failures inside `chat_stream` RAISE `BackendError` subclasses from
  `backends/errors.py`; `ErrorEvent` is the serializable form the
  API/service layer produces from a raised error.
- Cancellation is signalled by an `asyncio.Event`; a backend observing it
  set raises `GenerationCancelled` and closes its upstream stream.
- The S108 SSE dict shape is unchanged in this slice. S307 bridges
  normalized events to the SSE the web UI consumes, at the seam.

## Consequences

Adapters are testable without HTTP/SSE plumbing; error handling is typed
instead of stringly; the UI bridge is a single deliberate translation point.
