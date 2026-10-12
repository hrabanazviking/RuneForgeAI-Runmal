# Rúnmál Security Model

Rúnmál is local-first, but local-first is not the same thing as security-by-assumption. This document defines the phase-one threat boundary and how it changes when the user exposes the service beyond localhost.

## 1. Default deployment boundary

- Bind HTTP service to `127.0.0.1` by default.
- Generate a high-entropy local application credential on first run.
- Do not listen on LAN/WAN merely because a machine has a network interface.
- Treat deliberate non-loopback binding as a security-mode change that requires explicit configuration.

## 2. Assets being protected

- cloud/provider API keys;
- bridge tokens;
- chats and private character conversations;
- memory/provenance database;
- personas/lorebooks/assets;
- local filesystem paths and diagnostics;
- model/provider routing configuration.

## 3. Secrets storage

Application settings store **references** to secrets, not raw secret values.

Phase-one acceptable implementations may include a permission-restricted local secret file or OS credential facility, but the chosen mechanism must document its threat model. Plaintext secrets inside the main SQLite content database are not the default design merely because `/api/secrets` hides them.

Secrets must never appear in:

- API responses;
- normal logs;
- prompt traces;
- portable exports/backups intended for sharing;
- exception pages;
- telemetry (Rúnmál has no mandatory telemetry);
- committed test fixtures.

## 4. Browser authentication

Bearer-token API authentication alone does not fully define browser behavior.

Before the UI is treated as hardened, specify one supported browser session model. If cookies are used, apply HttpOnly/SameSite/Secure rules appropriate to deployment and CSRF protection for state-changing requests. If a local bootstrap token is used, do not persist it in browser localStorage by default.

## 5. CSRF and origin handling

State-changing browser routes must have a deliberate CSRF/origin strategy. CORS is not an authentication mechanism.

Localhost deployments should reject unexpected origins rather than automatically allowing `*`.

## 6. LAN/WAN exposure

Non-loopback binding must surface a clear configuration state. Remote use should add encrypted transport/reverse-proxy guidance rather than exposing plaintext bearer credentials across a network.

Do not build a false sense of safety around "it's only my LAN." Shared networks and compromised peers exist.

## 7. Bridge tokens

Bridge credentials are scoped, revocable and independently auditable. A bridge credential is never interchangeable with the primary admin credential.

Store only a verifier/hash where feasible for tokens that do not need to be recovered in plaintext.

## 8. Extension model

Python extensions execute with server process privileges unless isolated. Therefore extension installation is a code-execution trust decision, not merely a UI customization.

The extension registry should record:

- extension ID/version;
- declared hook/API capabilities;
- source/install provenance;
- enabled state.

Do not imply sandboxing unless a real sandbox boundary exists.

## 9. Imports and assets

Character cards, CHARX archives, lorebooks and uploaded assets are untrusted input.

Requirements include:

- bounded archive extraction;
- path traversal rejection;
- content-size limits;
- safe generated filenames/object IDs;
- no execution of imported scripts/macros by default;
- preservation of unknown metadata without executing it.

## 10. Logs and diagnostics

Logs use structured redaction. Request headers, authorization values and provider API keys are denied by default rather than individually remembered later.

Debug bundles should contain an explicit manifest and redaction pass.

## 11. Database security

SQLite file permissions should restrict access to the owning user. Backups inherit equivalent protection.

Enable foreign-key enforcement and use migrations rather than ad-hoc schema mutation.

## 12. Dependency/supply-chain posture

- Pin direct dependencies in release artifacts/lockfiles.
- Generate an SBOM for releases.
- Scan dependency licenses against the project's permissive-only policy.
- Treat models/weights and runtime dependencies as separately licensed artifacts.
- Do not assume a permissive top-level wrapper makes its entire runtime dependency tree permissive.

## 13. Security acceptance mindset

Security tests should include negative cases: secret absent from serialization/logs, wrong bridge scope denied, archive traversal rejected, unexpected origin rejected, revoked credential denied, and export proven not to contain secret material.